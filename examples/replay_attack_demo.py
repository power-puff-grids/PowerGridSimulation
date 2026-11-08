import argparse
import json
from pathlib import Path

from src.attacks.attacks import replay_attack


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a whole-message replay from a saved JSON message."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "data/sample/telemetry_example.json"
        ),
        help="Path to an earlier telemetry JSON message (default: solar sample).",
    )
    args = parser.parse_args()

    earlier = json.loads(args.input.read_text(encoding="utf-8"))
    replayed, record = replay_attack(earlier)

    print("Replay preparation only; no messages are published.")
    print("\nEarlier message:")
    print(json.dumps(earlier, indent=2))
    print("\nReplayed earlier message:")
    print(json.dumps(replayed, indent=2))
    print("\nAttack record:")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
