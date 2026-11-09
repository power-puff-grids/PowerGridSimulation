# weather-driven pilot: independent counterfactual scenarios at every UTC hour.
import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import platform
import json
from pathlib import Path
from uuid import uuid4
from .fetch_weather import DEFAULT
from .physical_export import physical_row, write_physical_csv
from .run_scenarios import run_scenario
from .scenarios import get_scenarios, DUST_SOLAR_REDUCTION
from .telemetry import snapshot_messages, write_telemetry_csv
from .weather import weather_rows
from .pv_model import pv_profile, model_config

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT / "response.json")
    parser.add_argument("--output-root", type=Path,
        default=Path(__file__).resolve().parents[2] / "data/generated/weather_pilot")

    args = parser.parse_args()
    raw = args.input.read_bytes()
    weather = pv_profile(weather_rows(json.loads(raw)))
    run_id = str(uuid4())
    physical, messages, inputs = [], [], []


    for hour in weather:
        for base in get_scenarios():
            dust = DUST_SOLAR_REDUCTION if base.scenario == "dust_reduced_solar" else 0.0
            solar = hour["solar_clean_ac_mw"] * (1.0 - dust)
            scenario = replace(base, solar_setpoint_mw=solar,
                description=base.description + " Weather-driven pvlib/PVWatts-based solar; independent counterfactual.")
           
            net = run_scenario(scenario)
            row = physical_row(net, scenario, run_id, hour["timestamp"])
            nominal = {f"bus_{n}": float(net.bus.loc[net.bus.name == name, "vn_kv"].item())
                for n, name in enumerate(("Bus 1 - Utility", "Bus 2 - Solar", "Bus 3 - Battery", "Bus 4 - Irrigation"), 1)}
            
            physical.append(row)
            messages.extend(snapshot_messages(row, nominal))
            inputs.append(dict(run_id=run_id, snapshot_id=row["snapshot_id"],
                scenario=scenario.scenario, **hour, dust_fraction=dust,
                solar_setpoint_mw=solar, pump_setpoint_mw=scenario.pump_setpoint_mw,
                pump_reactive_setpoint_mvar=scenario.pump_reactive_setpoint_mvar))

    # outputs only after ALL snapshots pass the existing electrical validation.
    output = args.output_root / run_id
    output.mkdir(parents=True, exist_ok=False)

    write_physical_csv(physical, output / "physical_results.csv")
    write_telemetry_csv(messages, output / "mqtt_telemetry.csv")

    with (output / "weather_inputs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(inputs[0]))
        writer.writeheader()
        writer.writerows(inputs)

    summary = dict(run_id=run_id, created_at=datetime.now(timezone.utc).isoformat(),
        source_path=str(args.input.resolve()), source_sha256=hashlib.sha256(raw).hexdigest(),
        software={"python": platform.python_version(), **{name: version(name) for name in ("pandapower", "numpy", "pandas", "scipy", "pvlib")}},
        model_source_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("weather.py", "pv_model.py", "run_weather.py", "build_grid.py", "scenarios.py", "pump_parameters.py", "validation.py")},
        pv_model=model_config(),
        masked_ghi_wh_m2=sum(r["masked_ghi_wh_m2"] for r in weather),
        weather_hours=len(weather), snapshots=len(physical), messages=len(messages),
        scalar_measurements=sum(len(m["measurements"]) for m in messages),
        all_converged=all(row["converged"] for row in physical),
        solar_range_mw=[min(r["solar_output_mw"] for r in physical), max(r["solar_output_mw"] for r in physical)],
        temperature_range_c=[min(r["temperature_2m_c"] for r in weather), max(r["temperature_2m_c"] for r in weather)],
        limitations=["Pilot, not calibrated farm data", "Three counterfactual pump/dust cases per weather hour; no irrigation schedule",
            "Generic fixed array; no farm calibration; DNI/DHI estimated from GHI",
            "Assumed constant module-height wind; generic temperature and loss parameters",
            "Hourly midpoint solar geometry; inspect masked sunrise/sunset radiation",
            "Battery idle at 50%; independent power flows, no state evolution"])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    
    print(json.dumps(summary, indent=2))
    print(f"Saved pilot: {output}")





if __name__ == "__main__":
    main()
