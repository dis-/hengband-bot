"""Freeze the n1-c life-116 Q31 recall boards of 2026-11-03 (once-quest-recall-1103).

Source, copied read-only from the viewing Magic-Eater n1-c to
C:/hengband-backups/pdca/captures/q31-n1c-116-1103/: the snapshot generation that
holds turn 1986976 (decision 4142, emergency:recall), the last skill and Home
knowledge rows before the floor, and the decision row of that turn.  Every frozen field is measured.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures/q31-n1c-116-1103")
SNAPSHOTS = ROOT / "n1-c/life-116/jsonlog/snapshots/snapshots-20261103-114850-6cb238.jsonl.gz"
DECISIONS = ROOT / "decisions-q31.jsonl"
TURNS = (1986976,)
FLOOR_ENTRY_TURN = 1982713
OUTPUT = Path(__file__).with_name("fixtures") / "once-quest-recall-20261103.json.gz"


def rows(path):
    with gzip.open(path, "rb") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except ValueError:
                continue  # blank or torn line of the multi-member ring


def main():
    boards, skill, home = {}, None, None
    for row in rows(SNAPSHOTS):
        if row.get("type") == "player_turn" and row["turn"] in TURNS:
            boards[row["turn"]] = row
        elif row.get("type") == "knowledge" and row["turn"] <= FLOOR_ENTRY_TURN:
            category = row["knowledge"]["category"]
            skill = row if category == "skill_exp" else skill
            home = row if category == "home" else home
    with DECISIONS.open(encoding="utf-8") as stream:
        decisions = [
            {name: row[name] for name in ("decision_sequence", "turn", "reason", "key", "rung")}
            for row in map(json.loads, stream) if row["turn"] in TURNS]
    races = load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))
    ids = {monster["race_id"] for board in boards.values() for monster in board["visible_monsters"]}
    fixture = dict(
        source="n1-c life-116 snapshots and decision log (copied from the viewing server)",
        boards=[boards[turn] for turn in TURNS],
        decisions=decisions,
        skill=skill,
        home=home,
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
