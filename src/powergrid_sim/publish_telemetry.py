# publish saved original telemetry to the local experiment's MQTT broker.
import argparse
import csv
from datetime import datetime
import json
from math import isfinite
from pathlib import Path
import time
from typing import Callable, Protocol
from mqtt_telemetry import Comms
from .telemetry import ENVELOPE_FIELDS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data/generated/mqtt_telemetry.csv"

class PublishReceipt(Protocol):
    @property
    def rc(self) -> int: ...
    def wait_for_publish(self, timeout: float) -> None: ...
    def is_published(self) -> bool: ...

class ConnectionState(Protocol):
    def is_connected(self) -> bool: ...

class PublisherTransport(Protocol):
    # Interface shared by the MQTT transport and test doubles.
    @property
    def client(self) -> ConnectionState: ...
    def m_send(self, message: dict, qos: int = 0) -> PublishReceipt | None: ...
    def close(self) -> None: ...

def load_messages(path: Path) -> list[dict]:
    # validate the entire saved batch before making a broker connection.
    with (PROJECT_ROOT / "data/metadata/telemetry_measurements.csv").open(newline="") as source:
        device_keys = {}
        for item in csv.DictReader(source):
            device_keys.setdefault(item["device"], set()).add(item["measurement"])
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ENVELOPE_FIELDS:
            raise ValueError("Telemetry CSV header does not match the shared schema.")
        messages = list(reader)
    if not messages:
        raise ValueError("Telemetry CSV contains no messages.")
    seen = set()
    
    for line, message in enumerate(messages, 2):
        try:
            if set(message) != set(ENVELOPE_FIELDS):
                raise ValueError("unexpected columns")
            for field in ENVELOPE_FIELDS:
                if not isinstance(message[field], str) or not message[field].strip():
                    raise ValueError(f"missing {field}")
            if message["schema_version"] != "1.0":
                raise ValueError("unsupported schema version")
            timestamp = message["timestamp"]
            if not timestamp.endswith("Z") or "T" not in timestamp:
                raise ValueError("simulated timestamp must be UTC ISO 8601 with Z suffix")
            datetime.fromisoformat(timestamp[:-1] + "+00:00")
            message["measurements"] = json.loads(message["measurements"])
            measurements = message["measurements"]
            device = message["device"]
            if device not in device_keys or not isinstance(measurements, dict):
                raise ValueError("unsupported device or invalid measurements")
            if set(measurements) != device_keys[device]:
                raise ValueError("measurement keys do not match the device schema")
            for value in measurements.values():
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                    raise ValueError("measurements must be finite numbers")
            if message["message_id"] in seen:
                raise ValueError("duplicate original message_id")
            seen.add(message["message_id"])
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"Invalid telemetry CSV row {line}: {exc}") from exc
    return messages

def publish_messages(messages: list[dict], *, host="localhost", port=1883,timeout=10.0, comms_factory: Callable[..., PublisherTransport] = Comms) -> int:
    # Send originals unchanged, waiting for each QoS 1 broker acknowledgment.
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be finite and positive.")
    comms = comms_factory(host=host, port=port)
    acknowledged = 0
    
    try:
        deadline = time.monotonic() + timeout
        while not comms.client.is_connected():
            if time.monotonic() >= deadline:
                raise TimeoutError("Broker connection was not accepted before timeout.")
            time.sleep(0.01)
        for message in messages:
            info = comms.m_send(message, qos=1)
            if info is None or info.rc != 0:
                raise RuntimeError(f"Publish was not queued for {message['message_id']}")
            info.wait_for_publish(timeout=timeout)
            if not info.is_published():
                raise TimeoutError(f"No broker acknowledgment for {message['message_id']}")
            acknowledged += 1
    
    except Exception as exc:
        raise RuntimeError(
            f"Publishing failed after {acknowledged}/{len(messages)} broker acknowledgments: {exc}. "
            "Some messages may already have been delivered; preserve receipt logs before retrying."
        ) from exc
    finally:
        comms.close()
    return acknowledged

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="Connection/individual acknowledgment timeout in seconds")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        messages = load_messages(args.input)
        count = publish_messages(messages, host=args.host, port=args.port, timeout=args.timeout)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Publisher error: {exc}\n")
    print(f"Broker acknowledged {count}/{len(messages)} messages on grid/telemetry/<device>.")
    print("Subscriber receipt must be verified separately; source identifiers were preserved.")



if __name__ == "__main__":
    main()
