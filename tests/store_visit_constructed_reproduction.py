"""Construct the two frozen incidents' proximate foreign-visit refusal state."""

import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = (
    ("armour-swap", "equip-swap-loop-20260826", 1172362, 0,
     StoreVisitPhase.ENTERING, 413),
    ("no-actionable", "no-actionable-claim-20260827", 1249445, 6,
     StoreVisitPhase.APPROACHING, 1896),
)


def _snapshot(capture, turn):
    path = ROOT / "jsonlog" / f"incident-{capture}.snapshots.jsonl"
    definitions = find_monrace_definitions(path, None)
    if definitions is None:
        raise RuntimeError("MonraceDefinitions.jsonc was not found")
    monraces = load_monrace_knowledge(definitions)
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        raw = json.loads(line)
        snapshot = parse_snapshot(raw, monraces)
        if snapshot.turn == turn:
            return snapshot, monraces
    raise RuntimeError(f"turn {turn} absent from {path.name}")


def measure():
    results = []
    for name, capture, turn, open_store, phase, opened_sequence in INCIDENTS:
        snapshot, monraces = _snapshot(capture, turn)
        policy = HengbotPolicy(monrace_knowledge=monraces)
        policy._store_visit = StoreVisit(
            owner="town-errand",
            purpose="shopping",
            store_type=open_store,
            phase=phase,
            opened_sequence=opened_sequence,
        )
        step = policy._shopping_approach_step(snapshot, 7)
        results.append((name, step is None))
    return results


if __name__ == "__main__":
    results = measure()
    for name, refused in results:
        print(f"{name}: refused={refused}")
    raise SystemExit(any(refused for _, refused in results))
