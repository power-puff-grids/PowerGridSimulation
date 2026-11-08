import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import pytest
from src.attacks.attacks import false_data_injection, replay_attack

# ***FALSE DATA INJECTION TESTS*** #
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
    assert record["false_data_injection"] == {
        "measurement": "active_power_kw",
        "original_value": before["measurements"]["active_power_kw"],
        "manipulated_value": changed["measurements"]["active_power_kw"],
        "offset": 30.0,
    }
    assert record["replay"] is None
    assert "original_value" not in record
    assert "manipulated_value" not in record

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

# test that the voltage measurement can be targeted and manipulated.
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
    assert record["false_data_injection"] == {
        "measurement": "voltage_kv",
        "original_value": before["measurements"]["voltage_kv"],
        "manipulated_value": changed["measurements"]["voltage_kv"],
        "offset": -0.5,
    }
    assert record["replay"] is None

# test that the state of charge (soc_percent) can be targeted and manipulated.
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
    assert record["false_data_injection"] == {
        "measurement": "soc_percent",
        "original_value": 50.0,
        "manipulated_value": 40.0,
        "offset": -10.0,
    }
    assert record["replay"] is None

# test that an unknown measurement name is rejected.
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

# ***REPLAY ATTACK TESTS*** #
# test that replay_attack preserves the original message and returns a new copy.
def test_replay_preserves_message_and_original():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))
    before = deepcopy(original)

    replayed, record = replay_attack(original)

    assert original == before
    assert replayed == before
    assert replayed is not original
    assert replayed["measurements"] is not original["measurements"]

    assert record["original_message_id"] == before["message_id"]
    assert record["attack_type"] == "replay_attack"
    assert record["attack_target"] == "message"
    assert record["false_data_injection"] is None
    assert record["replay"] == {
        "replayed_id": before["message_id"],
        "replayed_timestamp": before["timestamp"],
        "replayed_measurements": before["measurements"],
    }
    assert (
        record["replay"]["replayed_measurements"]
        is not original["measurements"]
    )
    assert (
        record["replay"]["replayed_measurements"]
        is not replayed["measurements"]
    )

    replayed["measurements"]["active_power_kw"] += 10.0
    assert record["replay"]["replayed_measurements"] == before["measurements"]
    assert original == before


@pytest.mark.parametrize("message", [None, [], "telemetry", 123, True])
def test_replay_rejects_non_dictionary_messages(message):
    before = deepcopy(message)

    with pytest.raises(
        ValueError,
        match="previous_message must be a dictionary",
    ):
        replay_attack(message)

    assert message == before


@pytest.mark.parametrize("field", ["message_id", "timestamp"])
@pytest.mark.parametrize("value", [None, "", "   ", 123, True])
def test_replay_rejects_invalid_required_strings(field, value):
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))
    original[field] = value
    before = deepcopy(original)

    with pytest.raises(
        ValueError,
        match=f"{field} must be a nonempty string",
    ):
        replay_attack(original)

    assert original == before


@pytest.mark.parametrize("field", ["message_id", "timestamp"])
def test_replay_rejects_missing_required_strings(field):
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))
    del original[field]
    before = deepcopy(original)

    with pytest.raises(
        ValueError,
        match=f"{field} must be a nonempty string",
    ):
        replay_attack(original)

    assert original == before


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-18T14:00:00",
        "2026-10-18T14:00:00+00:00",
        "2026-10-18",
        "2026-02-30T14:00:00Z",
        "2026-10-18T25:00:00Z",
        "not-a-timeZ",
    ],
)
def test_replay_rejects_invalid_timestamps(timestamp):
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))
    original["timestamp"] = timestamp
    before = deepcopy(original)

    with pytest.raises(ValueError, match="timestamp must be"):
        replay_attack(original)

    assert original == before


@pytest.mark.parametrize(
    "measurements",
    [
        None,
        [],
        {},
        {"": 150.0},
        {"   ": 150.0},
        {123: 150.0},
        {"active_power_kw": True},
        {"active_power_kw": "150"},
        {"active_power_kw": None},
        {"active_power_kw": float("inf")},
        {"active_power_kw": float("-inf")},
        {"active_power_kw": float("nan")},
    ],
)
def test_replay_rejects_invalid_measurements(measurements):
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))
    original["measurements"] = measurements
    before = deepcopy(original)

    with pytest.raises(ValueError, match="measurement"):
        replay_attack(original)

    assert original == before


def test_replay_rejects_missing_measurements():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))
    del original["measurements"]
    before = deepcopy(original)

    with pytest.raises(
        ValueError,
        match="measurements must be a nonempty dictionary",
    ):
        replay_attack(original)

    assert original == before


def test_replay_attack_ids_are_distinct():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))

    _, first_record = replay_attack(original)
    _, second_record = replay_attack(original)

    assert first_record["attack_id"] != second_record["attack_id"]
    assert first_record["original_message_id"] == original["message_id"]
    assert second_record["original_message_id"] == original["message_id"]


def test_replay_injected_at_is_current_utc():
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text(encoding="utf-8"))

    before = datetime.now(timezone.utc)
    replayed, record = replay_attack(original)
    after = datetime.now(timezone.utc)

    timestamp = record["injected_at"]
    assert timestamp.endswith("Z")

    injected_at = datetime.fromisoformat(
        timestamp.replace("Z", "+00:00")
    )

    assert injected_at.utcoffset().total_seconds() == 0
    assert before <= injected_at <= after
    assert replayed["timestamp"] == original["timestamp"]
    assert record["replay"]["replayed_timestamp"] == original["timestamp"]
