"""Run independent steady-state scenarios on the same four-bus design."""
import argparse
from datetime import datetime
import logging
from pathlib import Path
from uuid import uuid4
import pandapower as pp
from .build_grid import build_grid
from .scenarios import Scenario, get_scenarios
from .validation import validate_results
from .physical_export import DEFAULT_OUTPUT, DEFAULT_TIMESTAMP, physical_row, write_physical_csv
from .telemetry import snapshot_messages, write_telemetry_csv

def apply_scenario(net: pp.pandapowerNet, scenario: Scenario) -> None:
    # inputs for the single PV, pump equivalent, and battery.
    for table in (net.sgen, net.load, net.storage):
        if len(table) != 1:
            raise ValueError("Expected exactly one solar generator, pump load, and battery.")

    solar = net.sgen.index[0]
    pump = net.load.index[0]
    battery = net.storage.index[0]
    net.sgen.loc[solar, "p_mw"] = scenario.solar_setpoint_mw
    net.load.loc[pump, "p_mw"] = scenario.pump_setpoint_mw
    net.load.loc[pump, "q_mvar"] = scenario.pump_reactive_setpoint_mvar
    net.storage.loc[battery, "p_mw"] = scenario.battery_setpoint_mw
    net.storage.loc[battery, "soc_percent"] = scenario.battery_soc_percent

def run_scenario(scenario: Scenario) -> pp.pandapowerNet:
    # rebuild the network (from start), apply inputs, and return its solved results.
    net = build_grid()
    apply_scenario(net, scenario)
    pp.runpp(net, numba=False) 
    validate_results(net)
    return net

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=DEFAULT_TIMESTAMP,
                        help="Synthetic event time in UTC with Z suffix. shared by independent snapshots")
    parser.add_argument("--telemetry-output", type=Path,
                        default=DEFAULT_OUTPUT.with_name("mqtt_telemetry.csv"))
    args = parser.parse_args()
    if args.output.resolve() == args.telemetry_output.resolve():
        parser.error("Physical and telemetry output paths must differ")
    try:
        if not args.timestamp.endswith("Z"):
            raise ValueError("UTC Z suffix required")
        datetime.fromisoformat(args.timestamp[:-1] + "+00:00")
    except ValueError:
        parser.error("--timestamp must be a valid UTC ISO 8601 timestamp ending in Z")

    run_id = str(uuid4())
    rows = []
    messages = []
    for scenario in get_scenarios():
        try:
            net = run_scenario(scenario)
            row = physical_row(net, scenario, run_id, args.timestamp)
            # Read nominal voltages from this grid, not from an assumed pu-to-kV factor.
            nominal_kv = {}
            for n, name in enumerate(("Bus 1 - Utility", "Bus 2 - Solar", "Bus 3 - Battery", "Bus 4 - Irrigation"), 1):
                nominal_kv[f"bus_{n}"] = float(net.bus.loc[net.bus.name == name, "vn_kv"].item())
            messages.extend(snapshot_messages(row, nominal_kv))
            rows.append(row)
        except Exception:
            logging.exception("Run %s failed in scenario %s! CSV was not written.", run_id, scenario.scenario)
            raise
        print(f"\nScenario: {scenario.scenario}")
        print(scenario.description)
        print(f"Converged: {net.converged}")
        print("Numerical validation: passed")
        print("Bus voltages (pu):")
        print(net.res_bus[["vm_pu"]].to_string())
        print("Line loading (%):")
        print(net.res_line[["loading_percent"]].to_string())
        print(f"Solar output (MW): {net.res_sgen.p_mw.sum():.9f}")
        print(f"Pump demand (MW): {net.res_load.p_mw.sum():.9f}")
        print(f"Pump reactive demand (MVAr): {net.res_load.q_mvar.sum():.9f}")
        print(f"Battery power (MW): {net.res_storage.p_mw.sum():.9f}")
        print(f"Battery SOC (%): {net.storage.soc_percent.iloc[0]:.1f}")
        print(f"Utility power (MW; positive import, negative export): {net.res_ext_grid.p_mw.sum():.9f}")
        print(f"Active line losses (MW): {net.res_line.pl_mw.sum():.9f}")

    # Do not overwrite the previous CSV unless every scenario passed.
    write_physical_csv(rows, args.output)
    write_telemetry_csv(messages, args.telemetry_output)
    print(f"\nSaved {len(rows)} validated snapshots to {args.output}")
    print(f"Saved {len(messages)} original device messages to {args.telemetry_output}")


if __name__ == "__main__":
    main()
