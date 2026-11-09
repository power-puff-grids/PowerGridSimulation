"""Shared JSON telemetry envelope for the simulator and MQTT branches."""
from __future__ import annotations

import math
from typing import Mapping


def build_telemetry_message(
    *,
    timestamp: str,
    run_id: str,
    sequence: int,
    device_id: str,
    bus_id: str,
    measurements: Mapping[str, int | float],
) -> dict:
    """Build and validate the agreed wire-message shape.

    Scenario and attack labels are intentionally excluded. Store them in a
    separate trusted ground-truth log and join after the detector runs.
    """
    if not timestamp.endswith("Z") and "+" not in timestamp:
        raise ValueError("timestamp must include a UTC marker or timezone offset")
    if sequence < 0:
        raise ValueError("sequence must be non-negative")
    if not all((run_id, device_id, bus_id)):
        raise ValueError("run_id, device_id, and bus_id must be non-empty")
    clean_measurements: dict[str, float] = {}
    for name, value in measurements.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"measurement {name!r} must be numeric")
        if not math.isfinite(float(value)):
            raise ValueError(f"measurement {name!r} must be finite")
        clean_measurements[name] = float(value)
    return {
        "timestamp": timestamp,
        "run_id": run_id,
        "sequence": int(sequence),
        "device_id": device_id,
        "bus_id": bus_id,
        "measurements": clean_measurements,
    }


def validate_telemetry_message(message: dict) -> None:
    """Raise ValueError when a received message does not match the envelope."""
    required = {"timestamp", "run_id", "sequence", "device_id", "bus_id", "measurements"}
    if set(message) != required:
        missing = sorted(required - set(message))
        extra = sorted(set(message) - required)
        raise ValueError(f"invalid telemetry keys; missing={missing}, extra={extra}")
    if not isinstance(message["measurements"], dict) or not message["measurements"]:
        raise ValueError("measurements must be a non-empty object")
    if "scenario_label" in message or "attack_type" in message:
        raise ValueError("ground-truth labels must not be included in telemetry")
