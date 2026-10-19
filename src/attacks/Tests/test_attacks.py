import json
from copy import deepcopy
from pathlib import Path
from src.attacks.attacks import false_data_injection

def test_false_data_injection():
    # load a normal message and save its original information.
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())
    before = deepcopy(original)

    # Act: run the attack.
    changed, record = false_data_injection(original, 30.0)

    print("\nOriginal power:", original["measurements"]["active_power_kw"])
    print("Changed power:", changed["measurements"]["active_power_kw"])
    print("Attack record:", json.dumps(record, indent=2))

    # Assert: check the result.
    expected = deepcopy(before)
    expected["measurements"]["active_power_kw"] += 30.0

    assert original == before
    assert changed == expected
    assert record["original_message_id"] == original["message_id"]
    assert record["attack_type"] == "false_data_injection"
    assert record["attack_target"] == "measurements.active_power_kw"
    assert record["original_value"] == before["measurements"]["active_power_kw"]
    assert record["manipulated_value"] == changed["measurements"]["active_power_kw"]

