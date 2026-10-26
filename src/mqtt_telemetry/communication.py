#filename - publish.py
import json, random, time, uuid
from datetime import datetime
import paho.mqtt.client as mqtt


class Comms:
    def __init__(self, drop_prob=0.0, max_delay=0.0):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.connect("localhost", 1883)
        self.client.loop_start()
        self.drop_prob = drop_prob
        self.max_delay = max_delay

    #used for sensors/devices (things we're not directly messing with) 
    def m_send(self, device, measurements, step, scenario = "normal", attack_type = "none"):
        msg = {
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "device": device,
                "measurements": measurements,
                "scenario": scenario,
                "attack_type": attack_type,
                "step": step
                }
        if random.random() < self.drop_prob:
            return
        if self.max_delay:
            time.sleep(random.uniform(0.0, self.max_delay))
        self.client.publish(f"grid/telemetry/{device}", json.dumps(msg))
        
    #generic / more freedom, build your own payload
    def h_send(self, topic, payload):
        msg = dict(payload)
        msg.setdefault("message_id", str(uuid.uuid7())) # allows for msgs to pass through interceptor with data from original sender
        msg.setdefault("timestamp", datetime.now().isoformat(timespec="milliseconds"))
        if random.random() < self.drop_prob:
            return
        if self.max_delay:
            time.sleep(random.uniform(0.0, self.max_delay))
        self.client.publsih(topic, json.dumps(msg))

    def subscribe(self, topic, callback=None)

