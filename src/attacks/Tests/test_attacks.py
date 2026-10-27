import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import pytest
from src.attacks.attacks import false_data_injection

def test_false_data_injection():
    # load a normal message and save its original information.
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())
    before = deepcopy(original)

    # run the attack.
    changed, record = false_data_injection(original, 30.0)

    print("\nOriginal power:", original["measurements"]["active_power_kw"])
    print("Changed power:", changed["measurements"]["active_power_kw"])
    print("Attack record:", json.dumps(record, indent=2))

    # check the result.
    expected = deepcopy(before)
    expected["measurements"]["active_power_kw"] += 30.0

    assert original == before
    assert changed == expected
    assert record["original_message_id"] == original["message_id"]
    assert record["attack_type"] == "false_data_injection"
    assert record["attack_target"] == "measurements.active_power_kw"
    assert record["original_value"] == before["measurements"]["active_power_kw"]
    assert record["manipulated_value"] == changed["measurements"]["active_power_kw"]

# test that invalid offsets are rejected.
@pytest.mark.parametrize(
    "offset",
    ["30", None, True, False, float("inf"), float("-inf"), float("nan")],
)
def test_rejects_invalid_offsets(offset):
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())
    before = deepcopy(original)

    with pytest.raises(ValueError):
        false_data_injection(original, offset)

    assert original == before

# test that attack IDs are unique for each attack.
def test_attack_ids_are_unique():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())

    _, first_record = false_data_injection(original, 30.0)
    _, second_record = false_data_injection(original, 30.0)

    assert first_record["attack_id"] != second_record["attack_id"]

# test that the injected_at timestamp is in UTC and within the expected range.
def test_injected_at_is_current_utc():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())

    before = datetime.now(timezone.utc)
    _, record = false_data_injection(original, 30.0)
    after = datetime.now(timezone.utc)

    timestamp = record["injected_at"]

    assert timestamp.endswith("Z")

    injected_at = datetime.fromisoformat(
        timestamp.replace("Z", "+00:00")
    )

    assert injected_at.utcoffset().total_seconds() == 0
    assert before <= injected_at <= after


def test_can_target_voltage():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())
    before = deepcopy(original)

    changed, record = false_data_injection(
        original, -0.5, measurement="voltage_kv"
    )

    expected = deepcopy(before)
    expected["measurements"]["voltage_kv"] -= 0.5

    assert original == before
    assert changed == expected
    assert record["attack_target"] == "measurements.voltage_kv"
    assert record["original_value"] == before["measurements"]["voltage_kv"]
    assert record["manipulated_value"] == changed["measurements"]["voltage_kv"]


def test_can_target_battery_soc():
    original = {
        "schema_version": "1.0",
        "run_id": "test-run",
        "snapshot_id": "test-snapshot",
        "message_id": "test-battery-message",
        "timestamp": "2026-10-18T14:00:00Z",
        "device": "battery",
        "measurements": {
            "active_power_kw": 0.0,
            "soc_percent": 50.0,
            "voltage_kv": 12.47,
        },
        "scenario": "normal",
    }
    before = deepcopy(original)

    changed, record = false_data_injection(
        original, -10.0, measurement="soc_percent"
    )

    expected = deepcopy(before)
    expected["measurements"]["soc_percent"] = 40.0

    assert original == before
    assert changed == expected
    assert record["original_message_id"] == original["message_id"]
    assert record["attack_target"] == "measurements.soc_percent"
    assert record["original_value"] == 50.0
    assert record["manipulated_value"] == 40.0


def test_rejects_unknown_measurement():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())
    before = deepcopy(original)

    with pytest.raises(
        ValueError,
        match="measurement must name an existing measurement",
    ):
        false_data_injection(
            original, 10.0, measurement="voltage_typo"
        )

    assert original == before


def test_rejects_nonfinite_result():
    original = {
        "message_id": "test-overflow-message",
        "measurements": {"active_power_kw": 1e308},
    }
    before = deepcopy(original)

    with pytest.raises(
        ValueError,
        match="manipulated measurement must be finite",
    ):
        false_data_injection(original, 1e308)

    assert original == before
