import csv
from pathlib import Path
from uuid import uuid4
from .scenarios import Scenario
from .validation import validate_results

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data/generated/physical_results.csv"
DEFAULT_TIMESTAMP = "2026-10-18T14:00:00Z"  # Synthetic event time, not an observation

def physical_row(net, scenario: Scenario, run_id: str, timestamp: str) -> dict:
    # Read solved quantities
    validate_results(net)
    def device_index(table, name):
        matches = table.index[table.name == name]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one device named {name!r}.")
        return matches[0]
    row = {
        "run_id": run_id,
        "snapshot_id": str(uuid4()),
        "timestamp": timestamp,
        "scenario": scenario.scenario,
        "description": scenario.description,
        "converged": bool(net.converged),
    }
    for number, name in enumerate(("Bus 1 - Utility", "Bus 2 - Solar", "Bus 3 - Battery", "Bus 4 - Irrigation"), 1):
        index = device_index(net.bus, name)
        row[f"bus_{number}_voltage_pu"] = float(net.res_bus.at[index, "vm_pu"])
        
    for number, name in enumerate(("Line 1-2", "Line 2-3", "Line 3-4"), 1):
        index = device_index(net.line, name)
        row[f"line_{number}_loading_percent"] = float(net.res_line.at[index, "loading_percent"])
    solar = device_index(net.sgen, "Solar PV")
    pump = device_index(net.load, "Irrigation Pump")
    battery = device_index(net.storage, "Battery Storage")
    row.update(
        solar_output_mw=float(net.res_sgen.at[solar, "p_mw"]),
        pump_demand_mw=float(net.res_load.at[pump, "p_mw"]),
        pump_reactive_demand_mvar=float(net.res_load.at[pump, "q_mvar"]),
        battery_power_mw=float(net.res_storage.at[battery, "p_mw"]),
        battery_soc_percent=float(net.storage.at[battery, "soc_percent"]),
    )
    return row

def write_physical_csv(rows: list[dict], output: Path) -> None:
    with (PROJECT_ROOT / "data/sample/physical_results_header.csv").open(newline="") as source:
        fields = next(csv.reader(source))
    for row in rows:
        if set(row) != set(fields):
            raise ValueError("Physical result fields do not match the shared schema.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


