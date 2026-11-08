from copy import deepcopy # creates a copy so that the original message is not modified
from datetime import datetime, timezone 
from math import isfinite
from uuid import uuid4 # used to generate unique identifiers for each attack record

# FALSE DATA INJECTION FUNCTION #
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
        "false_data_injection": {
            "measurement": measurement,
            "original_value": value,
            "manipulated_value": manipulated_value,
            "offset": offset,
        },
        "replay": None,
    }

    return manipulated_message, attack_record

# REPLAY ATTACK FUNCTION #
def replay_attack(previous_message):

    # reject invalid inputs for previous_message.
    if not isinstance(previous_message, dict):
        raise ValueError("previous_message must be a dictionary.")
    
    # validate that required fields are present and of the correct type.
    for field in ("message_id", "timestamp"):
        value = previous_message.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a nonempty string.")
        
    # validate the timestamp format and ensure it is a valid UTC date-time.
    timestamp = previous_message["timestamp"]
    if "T" not in timestamp or not timestamp.endswith("Z"):
        raise ValueError("timestamp must be a UTC date-time ending in Z.")

    try:
        datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError:
        raise ValueError(
            "timestamp must be a valid UTC date-time."
        ) from None

    # validate that measurements is a nonempty dictionary with valid names and numeric values.
    measurements = previous_message.get("measurements")
    if not isinstance(measurements, dict) or not measurements:
        raise ValueError("measurements must be a nonempty dictionary.")

    for name, value in measurements.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("measurement names must be nonempty strings.")

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("measurement values must be numbers.")

        if isinstance(value, float) and not isfinite(value):
            raise ValueError("measurement values must be finite.")

    replayed_message = deepcopy(previous_message)

    attack_record = {
        "attack_id": str(uuid4()),
        "injected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "original_message_id": previous_message["message_id"],
        "attack_type": "replay_attack",
        "attack_target": "message",
        "false_data_injection": None,
        "replay": {
            "replayed_id": previous_message["message_id"],
            "replayed_timestamp": previous_message["timestamp"],
            "replayed_measurements": deepcopy(
                previous_message["measurements"]
            ),
        },
    }

    return replayed_message, attack_record
