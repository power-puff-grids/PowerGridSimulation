#filename - communication.py
import json, random, time, uuid
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

#THESE ARE THE TOPICS, USE THEM BECAUSE MQTT WILL JUST PUBLISH TO WHATEVER 

#FLOW:  PHYSICAL MEASUREMENTS (PUBLISH) -> [grid/telemetry/{device}] -> (SUBSCRIBE) INTERCEPTOR (PUBLISH) -> 
#       [grid/processed/{device}] -> (SUBSCRIBE) DETECTOR (PUBLISH) -> [grid/alerts] (?end for now).
#                                 |
#                                 v
#                         (SUBSCRIBE) CONTROLLER implemented in the future (PUBLISH) -> [grids/commands]

TELEMETRY = "grid/telemetry"
PROCESSED = "grid/processed"
ALERTS = "grid/alerts"
COMMANDS = "grid/commands"

class Comms:
    def __init__(self, drop_prob=0.0, max_delay=0.0):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.connect("localhost", 1883)
        self.client.loop_start()
        self.drop_prob = drop_prob
        self.max_delay = max_delay

    #used for sensors/devices (things we're not directly messing with) 
    def m_send(self, message):
        if random.random() < self.drop_prob:
            return
        if self.max_delay:
            time.sleep(random.uniform(0.0, self.max_delay))
        self.client.publish(f"{TELEMETRY}/{message['device']}", json.dumps(message))
        
    #generic sender, no artificial drop or delay, mayhaps use in the relay section
    def h_send(self, topic, payload):
        msg = dict(payload)
        self.client.publish(topic, json.dumps(msg))

    def subscribe(self, topic, callback):
        def on_message(client, userdata, msg):
            try:
                message= json.loads(msg.payload.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                return
            meta = {
                    "delivery_id": str(uuid.uuid4()),
                    "received_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    }
            callback(message, meta)

        self.client.message_callback_add(topic, on_message)
        self.client.subscribe(topic)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()
