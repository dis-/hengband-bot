"""Freeze incident boundaries; only this extractor reads operator logs.

The 40 MB tail begins mid-row. State rows are matched by turn AND position,
using the last matching observation (same-turn duplicate boards are possible).
The pins use independent boundaries, not an invented full-process replay.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("C:/hengband-backups/state-logs/starving-town-20261006-0904")
OUTPUT = ROOT / "tests/fixtures/starving-town-20261006.json.gz"
SELECTED = (10741, 10766, 10818, 10846, 10848, 10850, 10856,
            10837, 10861)


def main():
    decisions_path = SOURCE / "bot-decisions.jsonl"
    states_path = SOURCE / "bot-state-tail.jsonl"
    decisions = [json.loads(line) for line in
                 decisions_path.read_text(encoding="utf-8").splitlines()]
    states = []
    for line in states_path.read_text(encoding="utf-8").splitlines():
        try:
            states.append(json.loads(line))
        except ValueError:
            pass  # truncated first row of the tail
    pins = []
    for index in SELECTED:
        decision = decisions[index]
        matches = [(j, row) for j, row in enumerate(states)
                   if row.get("turn") == decision["turn"]
                   and row.get("player", {}).get("x") == decision["position"]["x"]
                   and row.get("player", {}).get("y") == decision["position"]["y"]]
        state_index, board = matches[-1]
        assert board["player"]["hp"] == decision["player"]["hp"]
        assert board["player"]["food_state"] == decision["player"]["food_state"]
        context = {}
        for row in states[:state_index]:
            if row.get("type") == "knowledge":
                category = row.get("knowledge", {}).get("category")
                if category in {"home", "skill_exp"}:
                    context[category] = row
        pins.append(dict(decision_index=index, state_row_index=state_index,
                         decision=decision, board=board, knowledge=context))
    OUTPUT.write_bytes(gzip.compress(
        (json.dumps(pins, ensure_ascii=True) + "\n").encode(), mtime=0,
    ))
    metadata = dict(
        source=str(SOURCE), base="694bbdfa",
        source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (decisions_path, states_path)},
        fixture_sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        decision_indices=list(SELECTED),
        state_row_index="zero-based after skipping the truncated first row",
        boundaries="Independent recorded boards; no later board is the effect of a fixed key.",
    )
    OUTPUT.with_suffix("").with_suffix(".provenance.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Frozen {len(pins)} independent boards; sha256={metadata['fixture_sha256']}")


if __name__ == "__main__":
    main()
