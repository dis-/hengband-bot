"""Freeze the n1-b life-339 Angband 30F boards of 2026-11-08 (the Devilfish out of sight).

Source: the viewing Magic-Eater n1-b life-339, 鉄獄30階 (floor (1, 30, 0)), stopped at
02:39:38 with ``loop-detected``: at [37,84] ``threat:avoid-engagement`` stepped '3' away
from a Devilfish (race 918, BR_DISE, no disenchant resistance) swimming at [37,81]/[38,81],
and at [38,85], where the wall hid it, ``explore`` stepped '7' straight back.  Copied
read-only from the viewing server:

  CAPTURE/state.jsonl.gz          the last 98 boards before the stop (turns 2438512-2439224)
  CAPTURE/bot-decisions.jsonl.gz  their decision rows
  INCIDENT/policy-state.json      the stop's policy summary (the deferred loot)

The fixture keeps boards 40-61 of the capture (turns 2438809-2438958: the explore walk
back from [39,84] to the retreat at [37,84] and the first board out of sight at [38,85]),
their compact decision rows, the stop's deferred loot and the monster knowledge
(lib/edit/MonraceDefinitions.jsonc) of every race on the boards.  Only this extraction tool
reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge


LIFE = Path("C:/Users/user/AppData/Local/Temp/claude/n1b-stops/life-339")
CAPTURE = LIFE / "captures/20261108-023938-loop-detected"
INCIDENT = LIFE / "incident-captures/20261108-023936-loop-detected"
GAME = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "disenchant-out-of-sight-20261108.json.gz"
FIRST, LAST = 40, 61


def main():
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream][FIRST:LAST + 1]
    turns = {board["turn"] for board in boards}
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") in turns:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"]})
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))["state"]
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    fixture = {
        "source": f"{LIFE} (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
        "deferred_loot": state["_nav_ledger_deferred_loot"],
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main()
