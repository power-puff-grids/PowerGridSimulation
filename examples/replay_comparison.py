import argparse
import json
from pathlib import Path


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Display a replacement replay from saved experiment logs."
    )
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()
    folder = args.experiment

    attacks = [
        record for record in read_jsonl(folder / "attack_records.jsonl")
        if record["attack_type"] == "replay_attack"
    ]
    if len(attacks) != 1:
        raise ValueError("This display requires exactly one replay attack.")
    attack = attacks[0]

    current = [
        item for item in read_jsonl(folder / "relay_input.jsonl")
        if item["meta"]["delivery_id"] == attack["relay_delivery_id"]
    ]
    links = [
        item for item in read_jsonl(folder / "attack_deliveries.jsonl")
        if item["attack_id"] == attack["attack_id"]
    ]
    delivery_ids = {item["delivery_id"] for item in links}
    received = [
        item for item in read_jsonl(folder / "received_messages.jsonl")
        if item["meta"]["delivery_id"] in delivery_ids
    ]

    if len(current) != 1 or not delivery_ids:
        raise ValueError("Missing or ambiguous replay linkage.")
    if {item["meta"]["delivery_id"] for item in received} != delivery_ids:
        raise ValueError("A linked replay receipt is missing.")

    print("CURRENT MESSAGE THAT WAS REPLACED:")
    print(json.dumps(current[0]["message"], indent=2))

    for item in received:
        print("\nACTUAL RECEIVED REPLAY:")
        print(json.dumps(item["message"], indent=2))
        print("Received delivery ID:", item["meta"]["delivery_id"])

    print("\nSEPARATE ATTACK RECORD:")
    print(json.dumps(attack, indent=2))


if __name__ == "__main__":
    main()
