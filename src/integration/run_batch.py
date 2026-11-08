"""Run a fixed nine-configuration relay batch and verify its saved artifacts."""

import argparse
from copy import deepcopy
import csv
from dataclasses import asdict, dataclass
import importlib.metadata
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from .run_relay import ROOT, run_experiment, utc_now
from .attack_records import fdi_details
from powergrid_sim.publish_telemetry import load_messages


@dataclass(frozen=True)
class BatchCase:
    case_id: str
    attack_device: str | None = None
    measurement: str = "active_power_kw"
    offset: float = 0.0


def batch_cases() -> tuple[BatchCase, ...]:
    cases = [BatchCase("benign")]
    for offset in (-30, -15, -5, 5, 15, 30):
        direction = "minus" if offset < 0 else "plus"
        cases.append(BatchCase(f"solar_{direction}_{abs(offset)}kw", "solar_pv", "active_power_kw", offset))
    cases.extend((BatchCase("battery_soc_minus_10pp", "battery", "soc_percent", -10),
                  BatchCase("battery_soc_plus_10pp", "battery", "soc_percent", 10)))
    return tuple(cases)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def verify_experiment(folder: Path, case: BatchCase) -> dict:
    """Check values, complete coverage and attack lineage; not a detector."""
    def require(condition, message):
        if not condition:
            raise ValueError(f"Artifact verification failed: {message}")

    summary = json.loads((folder / "summary.json").read_text())
    require(summary["status"] == "completed", "experiment did not complete")
    require(summary["attack_device"] == case.attack_device, "attack device differs from plan")
    if case.attack_device:
        require(summary["measurement"] == case.measurement and summary["offset"] == case.offset,
                "attack measurement/offset differs from plan")
    originals = load_messages(folder / "mqtt_telemetry.csv")
    source = {m["message_id"]: m for m in originals}
    require(len(source) == 30, "expected 30 original device messages")
    require(sum(len(m["measurements"]) for m in originals) == 45, "expected 45 original scalar values")
    require({m["scenario"] for m in originals} == {"normal", "high_irrigation_demand", "dust_reduced_solar"},
            "missing physical scenario")
    for scenario in {m["scenario"] for m in originals}:
        require(len([m for m in originals if m["scenario"] == scenario]) == 10, "expected ten messages per scenario")
    raw = read_jsonl(folder / "relay_input.jsonl")
    received = read_jsonl(folder / "received_messages.jsonl")
    forwarded = read_jsonl(folder / "forwarded_messages.jsonl")
    records = read_jsonl(folder / "attack_records.jsonl")
    links = read_jsonl(folder / "attack_deliveries.jsonl")
    raw_by_delivery = {r["meta"]["delivery_id"]: r for r in raw}
    require(len(raw_by_delivery) == len(raw), "duplicate relay delivery IDs")
    require({r["message"]["message_id"] for r in raw} == set(source), "original delivery coverage mismatch")
    for item in raw:
        require(item["message"] == source.get(item["message"]["message_id"]), "original payload was changed")
    expected = deepcopy(source)
    attacked_ids = set()
    for message_id, message in expected.items():
        if case.attack_device and message["device"] == case.attack_device:
            message["measurements"][case.measurement] += case.offset
            attacked_ids.add(message_id)
    require(len(forwarded) == 30 and {r["message"]["message_id"] for r in forwarded} == set(source),
            "forwarding count/identity mismatch")
    for item in forwarded:
        message_id = item["message"]["message_id"]
        require(item["message"] == expected[message_id], "incorrect forwarded value or envelope")
        require(item["topic"] == f"grid/processed/{item['message']['device']}", "incorrect forwarded topic")
        raw_item = raw_by_delivery.get(item["relay_delivery_id"])
        require(raw_item is not None and raw_item["message"]["message_id"] == message_id,
                "forwarded source-delivery linkage mismatch")
    received_by_delivery = {r["meta"]["delivery_id"]: r for r in received}
    require(len(received_by_delivery) == len(received), "duplicate downstream delivery IDs")
    require({r["message"]["message_id"] for r in received} == set(source), "missing downstream messages")
    for item in received:
        require(item["message"] == expected[item["message"]["message_id"]], "incorrect downstream value or envelope")
    by_original = {r["original_message_id"]: r for r in records}
    require(len(records) == len(by_original) == len(attacked_ids), "incorrect attack-record count")
    require(set(by_original) == attacked_ids, "attack-record target mismatch")
    require(len({r["attack_id"] for r in records}) == len(records), "duplicate attack IDs")
    for message_id, record in by_original.items():
        require(record["attack_type"] == "false_data_injection", "unexpected attack type")
        require(record["attack_target"] == f"measurements.{case.measurement}", "incorrect attack target")
        details = fdi_details(record)
        require(details["measurement"] == case.measurement, "incorrect nested attack measurement")
        if details["offset"] is not None:
            require(details["offset"] == case.offset, "incorrect recorded attack offset")
        require(details["original_value"] == source[message_id]["measurements"][case.measurement], "incorrect original attack value")
        require(details["manipulated_value"] == expected[message_id]["measurements"][case.measurement], "incorrect modified attack value")
        raw_item = raw_by_delivery.get(record["relay_delivery_id"])
        require(raw_item is not None and raw_item["message"]["message_id"] == message_id, "attack source-delivery mismatch")
    attacked_deliveries = {delivery for delivery, item in received_by_delivery.items()
                           if item["message"]["message_id"] in attacked_ids}
    require(len(links) == len(attacked_deliveries) and {r["delivery_id"] for r in links} == attacked_deliveries,
            "downstream attack links incomplete or duplicated")
    for link in links:
        original_id = received_by_delivery[link["delivery_id"]]["message"]["message_id"]
        require({k: v for k, v in link.items() if k != "delivery_id"} == by_original[original_id],
                "downstream attack record mismatch")
    for name in ("relay_quarantine.jsonl", "receiver_quarantine.jsonl"):
        require(not read_jsonl(folder / name), f"nonempty {name}")
    require(summary["original_messages"] == summary["broker_acknowledged"] == summary["forwarded_messages"] == 30,
            "summary source/forward counts mismatch")
    require(summary["received_deliveries"] == len(received) and summary["attacked_messages"] == len(records),
            "summary receipt/attack counts mismatch")
    return {"original_messages": len(source), "received_deliveries": len(received),
            "measurement_rows": sum(len(r["message"]["measurements"]) for r in received),
            "attacked_messages": len(attacked_ids), "modified_scalar_values": len(attacked_ids),
            "attack_labeled_rows": sum(len(r["message"]["measurements"]) for r in received
                                       if r["message"]["message_id"] in attacked_ids)}


def save_manifest(folder: Path, manifest: dict):
    # Replace only complete JSON documents, so interrupted runs retain a readable index.
    temporary = folder / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    temporary.replace(folder / "manifest.json")
    fields = ["case_id", "attack_device", "measurement", "offset", "status", "experiment_dir",
              "original_messages", "received_deliveries", "measurement_rows", "attacked_messages",
              "modified_scalar_values", "attack_labeled_rows", "error"]
    temporary_csv = folder / "manifest.csv.tmp"
    with temporary_csv.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(manifest["experiments"])
    temporary_csv.replace(folder / "manifest.csv")


def run_batch(output_root, *, host="localhost", port=1883, timeout=20.0,
              continue_on_error=False, experiment_runner=run_experiment):
    if not isfinite(timeout) or timeout <= 0 or not 1 <= port <= 65535:
        raise ValueError("Use a positive finite timeout and a valid broker port")
    batch_id = str(uuid4())
    folder = Path(output_root).resolve() / batch_id
    folder.mkdir(parents=True, exist_ok=False)
    cases = batch_cases()
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    manifest = {"batch_id": batch_id, "status": "running", "started_at": utc_now(),
                "host": host, "port": port, "timeout_seconds": timeout,
                "code_revision": revision, "working_tree_dirty": dirty,
                "python_version": sys.version.split()[0],
                "versions": {name: importlib.metadata.version(name) for name in ("pandapower", "paho-mqtt")},
                "physical_diversity_note": "Nine configurations repeat the same three deterministic physical states; no new physical samples or time dynamics.",
                "planned_counts_without_duplicates": {"experiments": 9, "original_messages": 270,
                  "measurement_rows": 405, "attacked_messages": 24, "attack_labeled_rows": 54},
                "experiments": [{**asdict(case), "status": "pending", "experiment_dir": None, "error": None} for case in cases]}
    save_manifest(folder, manifest)
    try:
        for case, entry in zip(cases, manifest["experiments"]):
            entry.update(status="running", started_at=utc_now())
            save_manifest(folder, manifest)
            case_root = folder / case.case_id
            try:
                experiment = experiment_runner(case_root, host=host, port=port, timeout=timeout,
                                               attack_device=case.attack_device, measurement=case.measurement,
                                               offset=case.offset)
                experiment = Path(experiment).resolve()
                entry["experiment_dir"] = str(experiment.relative_to(folder))
                entry.update(verify_experiment(experiment, case), status="completed")
            except Exception as exc:
                candidates = list(case_root.glob("*/summary.json"))
                if entry["experiment_dir"] is None and len(candidates) == 1:
                    entry["experiment_dir"] = str(candidates[0].parent.relative_to(folder))
                entry.update(status="failed", error=str(exc))
            entry["finished_at"] = utc_now()
            save_manifest(folder, manifest)
            print(f"{case.case_id}: {entry['status']}", flush=True)
            if entry["status"] == "failed" and not continue_on_error:
                break
        for entry in manifest["experiments"]:
            if entry["status"] == "pending":
                entry.update(status="not_run", error="Stopped after an earlier failure")
        manifest["status"] = "completed" if all(e["status"] == "completed" for e in manifest["experiments"]) else "failed"
    except BaseException:
        manifest["status"] = "interrupted"
        for entry in manifest["experiments"]:
            if entry["status"] == "running":
                entry["status"] = "interrupted"
            elif entry["status"] == "pending":
                entry.update(status="not_run", error="Batch interrupted")
        raise
    finally:
        manifest["finished_at"] = utc_now()
        manifest["totals_verified"] = {key: sum(e.get(key, 0) for e in manifest["experiments"] if e["status"] == "completed")
            for key in ("original_messages", "received_deliveries", "measurement_rows", "attacked_messages",
                        "modified_scalar_values", "attack_labeled_rows")}
        save_manifest(folder, manifest)
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/generated/batches")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        folder = run_batch(args.output_root, host=args.host, port=args.port, timeout=args.timeout,
                           continue_on_error=args.continue_on_error)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Batch error: {exc}\n")
    manifest = json.loads((folder / "manifest.json").read_text())
    print(f"Batch {manifest['status']}. Manifest: {folder / 'manifest.json'}")
    if manifest["status"] != "completed":
        parser.exit(1)


if __name__ == "__main__":
    main()
