#!/usr/bin/env python3
"""Write a room sweep's restart record (quest_sweep_record) from earlier processes' decision logs.

For a floor visit whose kills were read by processes that wrote no record (n1-c life-217's Quest 33:
the Its, Dagons and Bokrugs killed 18:30-20:26 2026-11-19, before quest_sweep_record existed).  It reads
the tracked races of the quest's ``room_sweep.alignment_split`` and, from each decision log given (the
decision rows of the bot, ``.jsonl`` or ``.jsonl.gz``), every kill line of those races on that quest's
floor, each board once (by its game turn and messages), as the restarted process would have counted
them (q2_kill_credit ``_killed``).  The record is written beside the decision log the bot will run with
(``sweep-kills.json``); nothing is written when no kill is found.

Run (from the repository root):
  PYTHONPATH=src python scripts/seed_sweep_kill_record.py --quest 33 --out <dir>/sweep-kills.json LOG...
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hengbot.monrace_knowledge import load_monrace_knowledge  # noqa: E402
from hengbot.q2_kill_credit import _killed  # noqa: E402
from hengbot.quest_strategies import load_quest_strategies  # noqa: E402
from hengbot.quest_sweep_record import VERSION  # noqa: E402


def _rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quest", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--monraces", type=Path, default=ROOT.parent / "lib" / "edit" / "MonraceDefinitions.jsonc")
    parser.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args(argv)
    profile = load_quest_strategies(ROOT / "strategy" / "quests")[args.quest]
    split = profile.engagement_plan["room_sweep"]["alignment_split"]
    knowledge = load_monrace_knowledge(args.monraces)
    names = {name: race for race in split["tracked_races"] for name in knowledge[race].names if name}
    kills, floor, turn = [], None, 0
    for log in args.logs:
        seen = set()
        for row in _rows(log):
            floor_data = row.get("floor") or {}
            if floor_data.get("quest_id") != args.quest or "turn" not in row:
                continue
            read = (row["turn"], tuple(row.get("messages") or ()))
            if read in seen:
                continue
            seen.add(read)
            floor = [int(floor_data.get("dungeon_id", 0)), int(floor_data.get("level", 0)), args.quest]
            turn = max(turn, int(row["turn"]))
            for message in row.get("messages") or ():
                killed = _killed(message)
                if killed is not None and killed[0] in names:
                    kills.extend([[names[killed[0]], int(row["turn"])]] * killed[1])
    if not kills:
        print("no kill line of the tracked races found; nothing written", file=sys.stderr)
        return 1
    entry = {"version": VERSION, "floor": floor, "turn": turn, "kills": kills, "board": None}
    args.out.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.out, len(kills))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
