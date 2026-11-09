#filename - subscriber1.py
import json
from datetime import datetime
import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("grid/processed/solar_pv")

def on_message(client, userdata, msg):
    try:
        m = json.loads(msg.payload)
    except json.JSONDecodeError:
        print("something went wrong with json load in onmessage ", msg.topic)
        return
#more extensive input validation wip
    print(json.dumps(m, indent = 2))

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1883)

try:
    client.loop_forever()
except KeyboardInterrupt:
    client.disconnect()
    

