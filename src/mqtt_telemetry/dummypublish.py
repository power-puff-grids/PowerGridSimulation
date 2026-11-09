import json
import time

from mqtt_telemetry import Comms
def main():
    comms = Comms(drop_prob=0.0, max_delay=0.0)

    try:
        with open("snapshots.jsonl", "r", encoding="utf-8") as file:
            snapshots = json.load(file)
        if not snapshots:
            raise ValueError("No snapshots found.")

        while True:
            for message in snapshots:
                comms.m_send(message)
                print(f"Published: {message['device']}")
                time.sleep(1)

    finally:
        comms.close()

if __name__ == "__main__":
    main()

