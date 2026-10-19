import json, random, time
from datetime import datetime
import paho.mqtt.client as mqtt

BROKER, PORT ="localhost", 1883
TBASE = "grid/telemetry"

class TelemPublisher:
    def __init__(self, drop_prob=0.0, max_delay=0.0):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.connect(BROKER, PORT)
        self.client.loop_start()
        self.seq = {}
        self.drop_prob = drop_prob
        self.max_delay = max_delay

    def send(self, device, measurements, step, scenario = "normal", attack_type = None):
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
        self.client.publish(f"{TBASE}/{device}", json.dumps(msg))
        


    
