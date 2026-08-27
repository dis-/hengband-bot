"""Measure additive future-seeding telemetry bytes on frozen decisions."""

import argparse
import json
from pathlib import Path
import tempfile

from hengbot.cli import _write_decision
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from replay_key_equality import CAPTURES


ADDITIVE_RECORD_KEYS = {
    "equipment_transaction_session", "town_visit_ledger",
    "equipment_transaction_owned_items",
    "store_visit_state",
    "town_claim_categories", "town_errand_plan_state",
}
ADDITIVE_ARBITER_KEYS = {
    "observed_owner", "tenure", "no_progress_counts", "vectors",
    "owner_vectors", "retired_owners", "recurrences", "visit_vector_id",
    "last_pair", "visit_transfer_counts", "last_transfer_sequence",
    "last_transfer_pair", "pending_transfer", "transfer_exhausted",
    "transferred_visit",
}
ADDITIVE_VISIT_KEYS = set()


def encoded_size(row):
    return len(json.dumps(row, ensure_ascii=False).encode("utf-8")) + 1


def measure(capture):
    path = CAPTURES[capture]
    definitions = find_monrace_definitions(path, None)
    knowledge = load_monrace_knowledge(definitions)
    policy = HengbotPolicy(monrace_knowledge=knowledge)
    growth = []
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "decisions.jsonl"
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                snapshot = parse_snapshot(json.loads(line), knowledge)
                key = policy.choose_key(snapshot)
                _write_decision(output, snapshot, key, policy.last_reason, policy)
        for line in output.read_text(encoding="utf-8").splitlines():
            current = json.loads(line)
            previous = json.loads(line)
            for key in ADDITIVE_RECORD_KEYS:
                previous.pop(key)
            for key in ADDITIVE_ARBITER_KEYS:
                if previous.get("arbiter") is not None:
                    previous["arbiter"].pop(key)
            for key in ADDITIVE_VISIT_KEYS:
                if previous.get("store_visit") is not None:
                    previous["store_visit"].pop(key)
            growth.append(encoded_size(current) - encoded_size(previous))
    return len(growth), sum(growth), min(growth), max(growth)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", choices=CAPTURES)
    args = parser.parse_args()
    count, total, minimum, maximum = measure(args.capture)
    print(
        f"{args.capture}: records={count} total_growth={total} "
        f"per_record={total / count:.2f} min={minimum} max={maximum}"
    )
