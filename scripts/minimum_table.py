"""Stream captured last town boards without restoring an invented checkpoint.

The board supplies the recall target/depth. A fresh policy supplies defaults:
unrecorded transfer debt and supplier history cannot be reconstructed. This is
a board minimum inventory, not a sequential replay or proof of settled debt.
"""
from __future__ import annotations

import argparse
from collections import Counter
from functools import cache
import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.monrace_knowledge import load_monrace_knowledge


def last_row(path):
    last = None
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue  # preserved tails may start with a partial row
    return last


@cache
def monster_knowledge():
    return load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))


def board_policy(board):
    snapshot = parse_snapshot(board, monster_knowledge())
    policy = HengbotPolicy()
    policy._target_dungeon_id = snapshot.recall_dungeon_id
    depth = policy._dungeon_entry_depth(snapshot, snapshot.recall_dungeon_id, via_recall=True)
    # DECLARED CONSTRUCTED: no optimizer/checkpoint is present in these tails.
    # Evaluate ordinary supplies at the board's landing, not a fresh 1F plan.
    policy._equipment_optimization_last_depth = depth
    policy._deepest_level = max(0, depth - 1)
    return policy, snapshot, depth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("C:/hengband/bot-client/jsonlog"))
    args = parser.parse_args()
    # Freeze the filename set before streaming; later live captures are excluded.
    paths = sorted(args.root.glob("autorecover-*.bot-state-fixed.jsonl.gz"))
    counts = Counter()
    for path in paths:
        board = last_row(path)
        if board is None:
            continue
        policy, snapshot, depth = board_policy(board)
        if not snapshot.in_town:
            continue
        reason = path.name[28:].removesuffix(".bot-state-fixed.jsonl.gz")
        minimum = policy._departure_minimum(snapshot, depth)
        verdict = "holds" if minimum["holds"] else "unknown" if minimum["unknown"] else "fails"
        counts[reason, verdict] += 1
        print(json.dumps({"capture": path.name, "reason": reason, "depth": depth,
                          "verdict": verdict, **minimum}, ensure_ascii=False))
    print("reason\tholds\tfails\tunknown")
    for reason in sorted({reason for reason, _ in counts}):
        print(reason, *(counts[reason, verdict] for verdict in ("holds", "fails", "unknown")), sep="\t")
    print(f"total town={sum(counts.values())} frozen captures={len(paths)}")


if __name__ == "__main__":
    main()
