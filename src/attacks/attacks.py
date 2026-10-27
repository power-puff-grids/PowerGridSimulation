from copy import deepcopy # creates a copy so that the original message is not modified
from datetime import datetime, timezone 
from math import isfinite
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

    manipulated_message = deepcopy(message)
    manipulated_message["measurements"][measurement] += offset

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
