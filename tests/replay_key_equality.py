"""Replay a frozen snapshot window and pin its key/reason trajectory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy


ROOT = Path(__file__).resolve().parents[1]
CAPTURES = {
    "equip-swap": ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl",
    "no-actionable": ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.snapshots.jsonl",
}
BASELINES = {
    name: ROOT / "tests" / "fixtures" / f"t1-key-baseline-{name}.json"
    for name in CAPTURES
}


def replay(path: Path) -> list[list[str]]:
    definitions = find_monrace_definitions(path, None)
    if definitions is None:
        raise RuntimeError("MonraceDefinitions.jsonc was not found")
    knowledge = load_monrace_knowledge(definitions)
    policy = HengbotPolicy(monrace_knowledge=knowledge)
    decisions: list[list[str]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            snapshot = parse_snapshot(json.loads(line), knowledge)
            key = policy.choose_key(snapshot)
            decisions.append([key, policy.last_reason])
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", choices=CAPTURES)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args()
    actual = replay(CAPTURES[args.capture])
    baseline = args.record or BASELINES[args.capture]
    if args.record:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"recorded {len(actual)} decisions: {baseline}")
        return 0
    expected = json.loads(baseline.read_text(encoding="utf-8"))
    if actual != expected:
        for index, (wanted, got) in enumerate(zip(expected, actual)):
            if wanted != got:
                print(f"mismatch at decision {index}: expected={wanted!r} actual={got!r}")
                break
        if len(actual) != len(expected):
            print(f"length mismatch: expected={len(expected)} actual={len(actual)}")
        return 1
    print(f"identical {len(actual)} decisions: {args.capture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
