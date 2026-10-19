#filename - subscriber.py
import json
from datetime import datetime
import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("grid/telemetry/#")

def on_message(client, userdata, msg):
    try:
        m = json.loads(msg.payload)
    except json.JSONDecodeError:
        print("something went wrong with json load in onmessage ", msg.topic)
        return
#more extensive input validation wip
    difference = datetime.now() - datetime.fromisoformat(m["timestamp"])
    latency_ms = (difference.total_seconds() * 1000)
    print(json.dumps(m, indent = 2))
    print(f"latency: {latency_ms:.1f} ms \n")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1883)

try:
    client.loop_forever()
except KeyboardInterrupt:
    client.disconnect()
    

