from copy import deepcopy # creates a copy so that the original message is not modified
from datetime import datetime, timezone 
from math import isfinite
from uuid import uuid4 # used to generate unique identifiers for each attack record


def false_data_injection(message, offset_kw): # offset_kw is the amount to manipulate by.
    # reject invalid inputs for offset_kw.
    if isinstance(offset_kw, bool) or not isinstance(offset_kw, (int, float)):
        raise ValueError("offset_kw must be a number.")

    if not isfinite(offset_kw):
        raise ValueError("offset_kw must be finite.")

    manipulated_message = deepcopy(message)
    manipulated_message["measurements"]["active_power_kw"] += offset_kw

    attack_record = {
        "attack_id": str(uuid4()),
        "injected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "original_message_id": message["message_id"],
        "attack_type": "false_data_injection",
        "attack_target": "measurements.active_power_kw",
        "original_value": message["measurements"]["active_power_kw"],
        "manipulated_value": manipulated_message["measurements"]["active_power_kw"],
    }

    return manipulated_message, attack_record
