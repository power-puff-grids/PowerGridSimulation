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
        help="Power offset in kW (default: 30).",
    )
    args = parser.parse_args()

    sample_path = (
        Path(__file__).resolve().parents[1]
        / "data/sample/telemetry_example.json"
    )
    original = json.loads(sample_path.read_text())
    changed, record = false_data_injection(original, args.offset)

    print("Original message:")
    print(json.dumps(original, indent=2))
    print("\nManipulated message:")
    print(json.dumps(changed, indent=2))
    print("\nAttack record:")
    print(json.dumps(record, indent=2))

if __name__ == "__main__":
    main()
    
