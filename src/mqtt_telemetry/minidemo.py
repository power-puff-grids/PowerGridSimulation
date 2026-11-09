from math import isfinite
from mqtt_telemetry import Comms, TELEMETRY, PROCESSED
from handlers import AttackRelay, AttackRouter, Recorder, Validated

# this will be an import in the future i hope
## for now this is literally just audreys attack fn 
from copy import deepcopy # creates a copy so that the original message is not modified
from datetime import datetime, timezone 
from uuid import uuid4 # used to generate unique identifiers for each attack record


def false_data_injection(message, offset, measurement="active_power_kw"): # offset is the amount to manipulate by.
    # reject invalid inputs for offset.
    if isinstance(offset, bool) or not isinstance(offset, (int, float)):
        raise ValueError("offset must be a number.")

    if not isfinite(offset):
        raise ValueError("offset must be finite.")

    measurements = message.get("measurements")

    if not isinstance(measurements, dict):
        raise ValueError("message must contain a measurements dictionary.")

    if not isinstance(measurement, str) or measurement not in measurements:
        raise ValueError("measurement must name an existing measurement.")

    value = measurements[measurement]

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("selected measurement must be a number.")

    if not isfinite(value):
        raise ValueError("selected measurement must be finite.")

    manipulated_value = value + offset

    if not isfinite(manipulated_value):
        raise ValueError("manipulated measurement must be finite.")

    manipulated_message = deepcopy(message)
    manipulated_message["measurements"][measurement] = manipulated_value

    attack_record = {
        "attack_id": str(uuid4()),
        "injected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "original_message_id": message["message_id"],
        "attack_type": "false_data_injection",
        "attack_target": f"measurements.{measurement}",
        "original_value": message["measurements"][measurement],
        "manipulated_value": manipulated_message["measurements"][measurement],
    }

    return manipulated_message, attack_record
#################

attacks = { "x":false_data_injection }

def main():
    comms = Comms()
    recorder = Recorder("logs/straight.jsonl", "logs/quarantine.jsonl", "logs/attacklog.jsonl")
    attackrelay = AttackRelay(comms, PROCESSED, recorder)
    router = AttackRouter(comms=comms, outtopic=PROCESSED, attack_relay = attackrelay, attacks=attacks, quarantine=recorder.quarantine)
    def goodmsg(message, meta):
        recorder(message, meta)
        router(message, meta)

    validated = Validated(goodmsg, recorder.quarantine)
    comms.subscribe(f"{TELEMETRY}/#", validated)
    try:
        while True:
            # people might not listen so maybe try to make this hard to break (ignore spaces lower 
            #case, anything that isnt the keys i have ready
            key = input("x: data injeciton attack\nn: no attack\nq: quit\n")

            if key == "q":
                break
            elif key == "n":
                router.disable()
            elif key == "x":
                device = input("target device: ")
                measurement = (input("measurement to change (attacks active_power_kw if empty):") or
                               "active_power_kw")
                offset = float(input("Offset: "))
                router.grabfn("x", device=device, offset=offset, measurement=measurement)
    finally:
        recorder.close()
        comms.close()

if __name__ == "__main__":
    main()
