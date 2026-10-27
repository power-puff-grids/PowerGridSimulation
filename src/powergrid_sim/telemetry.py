import csv
import json
from math import isfinite
from pathlib import Path
from uuid import uuid4

ENVELOPE_FIELDS = ["schema_version", "run_id", "snapshot_id", "message_id",
                   "timestamp", "device", "measurements", "scenario"]


def snapshot_messages(row: dict, nominal_kv: dict[str, float]) -> list[dict]:
    # Convert one validated physical row to ten device messages.
    # nominal_kv must come from the same network configuration as the physical row.
    # Identity and simulated event time are copied unchanged from physical truth.
    if row["converged"] is not True:
        raise ValueError("Telemetry requires a validated, converged physical row.")

    def number(value):
        if isinstance(value, bool):
            raise ValueError("Boolean is not a measurement.")
        value = float(value)
        if not isfinite(value):
            raise ValueError("Telemetry measurements must be finite.")
        return value

    voltages = {}
    for n in range(1, 5):
        bus = f"bus_{n}"
        nominal = number(nominal_kv[bus])
        if nominal <= 0:
            raise ValueError("Nominal voltage must be positive.")
        voltages[bus] = number(row[f"{bus}_voltage_pu"]) * nominal

    devices = {bus: {"voltage_kv": value} for bus, value in voltages.items()}
    for n in range(1, 4):
        devices[f"line_{n}"] = {"loading_percent": number(row[f"line_{n}_loading_percent"])}
    devices["solar_pv"] = {
        "active_power_kw": number(row["solar_output_mw"]) * 1000,
        "voltage_kv": voltages["bus_2"],
    }
    devices["irrigation_pump"] = {
        "active_power_kw": number(row["pump_demand_mw"]) * 1000,
        "reactive_power_kvar": number(row["pump_reactive_demand_mvar"]) * 1000,
        "voltage_kv": voltages["bus_4"],
    }
    devices["battery"] = {
        "active_power_kw": number(row["battery_power_mw"]) * 1000,
        "soc_percent": number(row["battery_soc_percent"]),
        "voltage_kv": voltages["bus_3"],
    }
    messages = []
    for device, measurements in devices.items():
        if not all(isfinite(value) for value in measurements.values()):
            raise ValueError("Unit conversion produced a nonfinite measurement.")
        messages.append({
            "schema_version": "1.0",
            "run_id": row["run_id"],
            "snapshot_id": row["snapshot_id"],
            "message_id": str(uuid4()),
            "timestamp": row["timestamp"],
            "device": device,
            "measurements": measurements,
            "scenario": row["scenario"],
        })
    return messages

def write_telemetry_csv(messages: list[dict], output: Path) -> None:
    rows = []
    for message in messages:
        row = dict(message)
        row["measurements"] = json.dumps(message["measurements"], allow_nan=False)
        rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=ENVELOPE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
