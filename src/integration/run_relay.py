"""Generate and relay a bounded physical experiment through an existing broker."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from uuid import uuid4

from attacks.attacks import false_data_injection
from mqtt_telemetry import Comms
from mqtt_telemetry.communication import TELEMETRY, PROCESSED
from mqtt_telemetry.handlers import AttackRelay, AttackRouter, DEVICE_KEYS, Recorder, validate_envelope
from powergrid_sim.publish_telemetry import load_messages, publish_messages

ROOT = Path(__file__).resolve().parents[2]


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def subscribe_ready(comms, topic, callback, timeout):
    deadline = time.monotonic() + timeout
    while not comms.client.is_connected():
        if time.monotonic() >= deadline:
            raise TimeoutError("Broker connection was not accepted")
        time.sleep(0.01)
    ready = threading.Event()
    accepted = []
    def on_subscribe(client, userdata, mid, reasons, properties):
        accepted.append(bool(reasons) and all(reason.value < 128 for reason in reasons))
        ready.set()
    comms.client.on_subscribe = on_subscribe
    rc, _ = comms.subscribe(topic, callback, qos=1)
    if rc != 0 or not ready.wait(timeout) or not accepted[0]:
        raise TimeoutError(f"Subscription not accepted: {topic}")


class ConfirmedForwarder:
    """Run only on the relay worker, never on the MQTT network thread."""
    def __init__(self, comms, path, timeout):
        self.comms = comms
        self.timeout = timeout
        self.expected = {}
        self.lock = threading.Lock()
        self.file = path.open("w", encoding="utf-8")
        self.meta = None

    def h_send(self, topic, message):
        # Register the exact proposed payload before a subscriber can receive it.
        with self.lock:
            self.expected[message["message_id"]] = deepcopy(message)
        info = self.comms.h_send(topic, message, qos=1)
        if info.rc != 0:
            raise RuntimeError("Forwarded publish was not queued")
        info.wait_for_publish(timeout=self.timeout)
        if not info.is_published():
            raise TimeoutError("Forwarded publish was not acknowledged")
        self.file.write(json.dumps({"relay_delivery_id": self.meta["delivery_id"],
                                   "forwarded_at": utc_now(), "topic": topic,
                                   "message": message}, allow_nan=False) + "\n")
        self.file.flush()

    def close(self):
        self.file.close()


def run_experiment(output_root, *, host="localhost", port=1883, timeout=20.0,
                   attack_device=None, measurement="active_power_kw", offset=30.0):
    if not isfinite(timeout) or timeout <= 0 or not isfinite(offset):
        raise ValueError("Timeout must be positive and offset must be finite")
    if attack_device is not None and (attack_device not in DEVICE_KEYS or measurement not in DEVICE_KEYS[attack_device]):
        raise ValueError("Select an existing measurement on the attack device")
    if attack_device is not None and offset == 0:
        raise ValueError("An enabled attack must use a nonzero offset")
    experiment_id = str(uuid4())
    folder = Path(output_root).resolve() / experiment_id
    folder.mkdir(parents=True, exist_ok=False)
    summary = {"experiment_id": experiment_id, "status": "running", "started_at": utc_now(),
               "attack_device": attack_device, "measurement": measurement if attack_device else None,
               "offset": offset if attack_device else None, "host": host, "port": port}
    def save_summary():
        (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    save_summary()
    relay = receiver = forwarder = raw_log = received_log = None
    worker = None
    stop = threading.Event()
    work = queue.Queue()
    failures = []
    received = []
    received_ids = set()
    processed_ids = set()
    state_lock = threading.Lock()
    try:
        # Reuse the simulation's existing entry point and exact output schema.
        simulation = subprocess.run(
            [sys.executable, "-m", "powergrid_sim.run_scenarios", "--output", str(folder / "physical_results.csv"),
             "--telemetry-output", str(folder / "mqtt_telemetry.csv")],
            capture_output=True, text=True, timeout=60, cwd=ROOT)
        (folder / "simulation.stdout.log").write_text(simulation.stdout)
        (folder / "simulation.stderr.log").write_text(simulation.stderr)
        if simulation.returncode != 0:
            raise RuntimeError("Simulation failed; see simulation.stderr.log")
        originals = load_messages(folder / "mqtt_telemetry.csv")
        summary["simulation_run_id"] = originals[0]["run_id"]
        source = {message["message_id"]: message for message in originals}
        raw_log = Recorder(folder / "relay_input.jsonl", folder / "relay_quarantine.jsonl", folder / "attack_records.jsonl")
        received_log = Recorder(folder / "received_messages.jsonl", folder / "receiver_quarantine.jsonl")
        relay = Comms(host=host, port=port)
        receiver = Comms(host=host, port=port)
        forwarder = ConfirmedForwarder(relay, folder / "forwarded_messages.jsonl", timeout)
        base_attack_relay = AttackRelay(forwarder, PROCESSED, raw_log)
        def linked_attack_relay(message, meta, record):
            base_attack_relay(message, meta, {**record, "relay_delivery_id": meta["delivery_id"]})
        router = AttackRouter(forwarder, PROCESSED, linked_attack_relay,
                              {"false_data_injection": false_data_injection}, raw_log.quarantine)
        if attack_device:
            router.grabfn("false_data_injection", device=attack_device, measurement=measurement, offset=offset)

        def relay_callback(message, meta):
            work.put((message, meta))

        def receive_callback(message, meta):
            try:
                errors = validate_envelope(message)
                if errors:
                    received_log.quarantine(message, meta, errors)
                    raise ValueError("Invalid forwarded message")
                with forwarder.lock:
                    expected = deepcopy(forwarder.expected.get(message["message_id"]))
                if expected is None or message != expected:
                    received_log.quarantine(message, meta, ["Unresolved or mismatched forwarded payload"])
                    raise ValueError("Received payload does not match trusted forwarding bookkeeping")
                received_log(message, meta)
                with state_lock:
                    received.append({"meta": deepcopy(meta), "message": deepcopy(message)})
                    received_ids.add(message["message_id"])
            except Exception as exc:
                with state_lock:
                    failures.append(str(exc))

        def process_queue():
            while not stop.is_set() or not work.empty():
                try:
                    message, meta = work.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    errors = validate_envelope(message)
                    if errors:
                        raw_log.quarantine(message, meta, errors)
                        raise ValueError("Invalid original envelope")
                    if message != source.get(message["message_id"]):
                        raw_log.quarantine(message, meta, ["Message does not match this experiment's publisher log"])
                        raise ValueError("Unexpected original message")
                    raw_log(message, meta)
                    if message["message_id"] in processed_ids:
                        continue  # Log duplicate raw deliveries; forward each original identity once.
                    forwarder.meta = meta
                    router(message, meta)
                    with state_lock:
                        processed_ids.add(message["message_id"])
                except Exception as exc:
                    with state_lock:
                        failures.append(str(exc))
                finally:
                    work.task_done()

        worker = threading.Thread(target=process_queue, name="relay-worker")
        worker.start()
        subscribe_ready(receiver, f"{PROCESSED}/+", receive_callback, timeout)
        subscribe_ready(relay, f"{TELEMETRY}/+", relay_callback, timeout)
        acknowledged = publish_messages(originals, host=host, port=port, timeout=timeout)
        deadline = time.monotonic() + timeout
        while True:
            with state_lock:
                if failures:
                    raise RuntimeError(failures[0])
                complete = processed_ids == set(source) and received_ids == set(source)
            if complete:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for all forwarded deliveries")
            time.sleep(0.02)
        relay.close(); relay = None
        stop.set()
        worker.join(timeout=timeout + 1)
        if worker.is_alive():
            raise TimeoutError("Relay worker did not stop")
        receiver.close(); receiver = None
        # Link labels after receipt, using controlled bookkeeping, not payload labels.
        records = [json.loads(line) for line in (folder / "attack_records.jsonl").read_text().splitlines()]
        by_original = {record["original_message_id"]: record for record in records}
        with (folder / "attack_deliveries.jsonl").open("w") as output:
            for item in received:
                record = by_original.get(item["message"]["message_id"])
                if record:
                    output.write(json.dumps({**record, "delivery_id": item["meta"]["delivery_id"]}) + "\n")
        summary.update(status="completed", original_messages=len(source), broker_acknowledged=acknowledged,
                       forwarded_messages=len(processed_ids), received_deliveries=len(received),
                       attacked_messages=len(records), finished_at=utc_now())
    except Exception as exc:
        summary.update(status="failed", error=str(exc), finished_at=utc_now())
        raise
    finally:
        stop.set()
        if worker and worker.is_alive():
            worker.join(timeout=timeout + 1)
        for resource in (relay, receiver, forwarder, raw_log, received_log):
            if resource is not None:
                resource.close()
        save_summary()
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/generated/experiments")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--attack-device", choices=sorted(DEVICE_KEYS))
    parser.add_argument("--measurement", default="active_power_kw")
    parser.add_argument("--offset", type=float, default=30.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        folder = run_experiment(args.output_root, host=args.host, port=args.port, timeout=args.timeout,
                                attack_device=args.attack_device, measurement=args.measurement, offset=args.offset)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Experiment failed: {exc}\n")
    print(f"Completed relay experiment. Saved records to {folder}")


if __name__ == "__main__":
    main()
