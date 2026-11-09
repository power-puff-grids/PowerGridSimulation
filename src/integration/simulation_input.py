# archive a pre-generated weather run without copying simulation source code.
import csv
import hashlib
import json
from math import isfinite
from pathlib import Path
from powergrid_sim.build_grid import build_grid
from powergrid_sim.publish_telemetry import load_messages
from powergrid_sim.telemetry import snapshot_messages

def archive_weather_input(source: Path, destination: Path) -> dict:
    source = Path(source).resolve()
    names = ("physical_results.csv", "mqtt_telemetry.csv", "weather_inputs.csv", "summary.json")
    
    # checks and archived bytes refer to the same source contents.
    blobs = {name: (source/name).read_bytes() for name in names}
    summary = json.loads(blobs["summary.json"])
    if summary.get("all_converged") is not True or not summary.get("pv_model"):
        raise ValueError("Input must be a completed documented-PV weather run")
    def rows(name):
        return list(csv.DictReader(blobs[name].decode("utf-8").splitlines()))
    physical, weather = rows("physical_results.csv"), rows("weather_inputs.csv")
  
    # use the publisher's full schema/number validation on the captured bytes.
    telemetry_path = destination / "mqtt_telemetry.csv"
    telemetry_path.write_bytes(blobs["mqtt_telemetry.csv"])
    messages = load_messages(telemetry_path)
    if not physical or len(physical) != summary["snapshots"] or len(messages) != summary["messages"]:
        raise ValueError("Source summary counts differ from saved outputs")
    physical_by_id = {row["snapshot_id"]: row for row in physical}
    weather_by_id = {row["snapshot_id"]: row for row in weather}
    if len(physical_by_id) != len(physical) or len(weather_by_id) != len(weather) or set(physical_by_id) != set(weather_by_id):
        raise ValueError("Weather/physical snapshot coverage mismatch or duplicate IDs")
    net = build_grid()
    nominal = {f"bus_{n}": float(net.bus.loc[net.bus.name == name, "vn_kv"].item())
        for n, name in enumerate(("Bus 1 - Utility", "Bus 2 - Solar", "Bus 3 - Battery", "Bus 4 - Irrigation"), 1)}
    expected = {}
    run_ids = set()
   
    for snapshot_id, row in physical_by_id.items():
        if row["converged"].lower() != "true":
            raise ValueError("Unconverged physical row")
        run_ids.add(row["run_id"])
        context = weather_by_id[snapshot_id]
        if any(context[key] != row[key] for key in ("run_id", "timestamp", "scenario")):
            raise ValueError("Weather/physical identity mismatch")
        converted = dict(row, converged=True)
        for key in row:
            if key not in {"run_id","snapshot_id","timestamp","scenario","description","converged"}:
                value = float(row[key])
                if not isfinite(value):
                    raise ValueError("Nonfinite physical value")
                converted[key] = value
        for message in snapshot_messages(converted, nominal):
            expected[(snapshot_id, message["device"])] = message
    if run_ids != {summary["run_id"]} or len(expected) != len(messages):
        raise ValueError("Input run identity or snapshot/device count mismatch")
    seen = set()
    for message in messages:
        key = (message["snapshot_id"], message["device"])
        if key in seen or key not in expected:
            raise ValueError("Duplicate or unresolved snapshot/device")
        seen.add(key)
        actual = {k:v for k,v in message.items() if k != "message_id"}
        reference = {k:v for k,v in expected[key].items() if k != "message_id"}
        if actual != reference:
            raise ValueError("Telemetry differs from original physical results")
    
    # archive underlying weather source too, so no sibling-workspace link is needed later.
    raw = Path(summary["source_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != summary["source_sha256"]:
        raise ValueError("Weather source hash mismatch")
    for name, blob in blobs.items():
        target = "simulation_summary.json" if name == "summary.json" else name
        (destination/target).write_bytes(blob)
    (destination/"weather_source.json").write_bytes(raw)
    provenance = {"mode":"saved_weather", "source_directory":str(source),
        "simulation_run_id":summary["run_id"], "snapshots":len(physical),
        "original_messages":len(messages), "source_sha256":summary["source_sha256"],
        "files_sha256":{name:hashlib.sha256(blob).hexdigest() for name,blob in blobs.items()}}
    (destination/"simulation_input.json").write_text(json.dumps(provenance,indent=2)+"\n")
    
    return provenance
