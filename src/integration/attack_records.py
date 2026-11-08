"""Read current nested FDI records and earlier flat experiment archives."""

from math import isfinite


def fdi_details(record: dict) -> dict:
    """Return FDI values without rewriting source records or inferring labels.

    Earlier flat records did not store the requested offset; it is returned as
    None. Replay records require different reference bookkeeping and are rejected.
    """
    if not isinstance(record, dict) or record.get("attack_type") != "false_data_injection":
        raise ValueError("Expected a false_data_injection attack record")
    if "false_data_injection" in record:
        details = record["false_data_injection"]
        required = {"measurement", "original_value", "manipulated_value", "offset"}
        if not isinstance(details, dict) or not required.issubset(details):
            raise ValueError("Incomplete nested false_data_injection details")
        if "replay" not in record or record["replay"] is not None:
            raise ValueError("FDI records must have replay=null")
        if {"original_value", "manipulated_value"} & set(record):
            raise ValueError("Ambiguous mixed flat/nested attack record")
        details = dict(details)
        for field in ("original_value", "manipulated_value", "offset"):
            value = details[field]
            try:
                valid = not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"FDI {field} must be a finite number")
    else:
        target = record.get("attack_target")
        if "replay" in record or not isinstance(target, str) or not target.startswith("measurements."):
            raise ValueError("Unrecognized legacy FDI record")
        if not {"original_value", "manipulated_value"}.issubset(record):
            raise ValueError("Incomplete legacy FDI record")
        details = {"measurement": target.removeprefix("measurements."),
                   "original_value": record["original_value"],
                   "manipulated_value": record["manipulated_value"], "offset": None}
    measurement = details["measurement"]
    if not isinstance(measurement, str) or not measurement.strip():
        raise ValueError("FDI measurement must be a nonempty string")
    if record.get("attack_target") != f"measurements.{measurement}":
        raise ValueError("FDI target and nested measurement do not match")
    return details
