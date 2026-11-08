import argparse
import json
from pathlib import Path
from src.attacks.attacks import false_data_injection

def main():
    parser = argparse.ArgumentParser(
        description="Demonstrate false-data injection."
    )
    parser.add_argument(
        "--offset",
        type=float,
        default=30.0,
        help="Offset in the selected measurement's units (default: 30).",
    )
    parser.add_argument(
        "--measurement",
        default="active_power_kw",
        help="Measurement to manipulate (default: active_power_kw).",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "data/sample/telemetry_example.json"
        ),
        help="Path to a telemetry JSON message (default: solar sample).",
    )
    args = parser.parse_args()

    original = json.loads(args.input.read_text(encoding="utf-8"))
    changed, record = false_data_injection(
        original, args.offset, measurement=args.measurement
    )

    print("Original message:")
    print(json.dumps(original, indent=2))
    print("\nManipulated message:")
    print(json.dumps(changed, indent=2))
    print("\nAttack record:")
    print(json.dumps(record, indent=2))

if __name__ == "__main__":
    main()
    
