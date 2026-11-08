import json
from copy import deepcopy
from pathlib import Path
from src.attacks.attacks import replay_attack


def main():
    sample_path = (
        Path(__file__).resolve().parents[1]
        / "data/sample/telemetry_example.json"
    )
    earlier = json.loads(sample_path.read_text(encoding="utf-8"))

    # Illustrative current reading, not a solved simulation result.
    current = deepcopy(earlier)
    current["snapshot_id"] = "example-current-snapshot"
    current["message_id"] = "example-current-message"
    current["timestamp"] = "2026-10-18T14:05:00Z"
    current["measurements"]["active_power_kw"] = 90.0

    replayed, record = replay_attack(earlier)

    print("Synthetic demonstration; no messages are published.")
    print("\nEarlier message:")
    print(json.dumps(earlier, indent=2))
    print("\nCurrent message for comparison:")
    print(json.dumps(current, indent=2))
    print("\nReplayed earlier message:")
    print(json.dumps(replayed, indent=2))
    print("\nAttack record:")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
