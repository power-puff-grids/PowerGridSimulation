# handlers for Comms.subscribe(), the subscription facilitator

import copy, json, logging
form math import isfinite

log = logging.getLogger(__name__)

# requirements per schema
DEVICE_KEYS = {
        "bus_1": {"voltage_kv"},
        "bus_2": {"voltage_kv"},
        "bus_3": {"voltage_kv"},
        "bus_4": {"voltage_kv"},

        "line_1": {"loading_percent"},
        "line_2": {"loading_percent"},
        "line_3": {"loading_percent"},

        "solar_pv": {"active_power_kw", "voltage_kv"},
        "irrigation_pump": {"active_power_kw", "reactive_power_kvar", "voltage_kv"},
        "battery": {"active_power_kw", "soc_percent", "voltage_kv"}
        }
ENVELOPE_STRINGS = ["schema_version", "run_id", "snapshot_id", "message_id", "timestamp", "device", "scenario"]

def validate_envelope(message) -> list[str]:
#returns list of issues with message, empty = good message no issues
    if not isinstance(message, dict):
        return = ["this message is not JSON."]
    errors=[]
    for field in ENVELOPE_STRINGS:
        value = message.get(field)
        if not isinstance(value, str) or value == "":
            errors.append(f"{field} is empty or not a string.")
    if message.get("schema_version") != "1.0":
        errors.append("message is based on outdated/unsupported schema version")
    if isinstance(message.get("timestamp"), str) and not message["timestamp"].endswith("Z"): 
        errors.append("timestamp is not strictly UTC")
    extra = set(message) - set(ENVELOPE_STRINGS) - {"measurements"}
    if extra:
        errors.append(f"unsupported envelope fields: {extra}")
    measurements = message.get("measurements")
    device = message.get("device")
    if not isinstance(measurements, dict):
        errors.append("measurements must be dict")
    elif device not in DEVICE_KEYS:
        errors.append(f"unrecognized/unsupported device: {device}")
    else:
        if set(measurements) != DEVICE_KEYS[device]:
            errors.append(f"measurements for {device} must be {(DEVICE_KEYS[device])}")
            for key, value in measurements.items():
                if isinstance(value, bool) or not isinstance(value, (int,float)) or not isfinite(value):
                    errors.append(f"{key} must be a number")
    return errors

def validated(good, quarantine=None)
        
