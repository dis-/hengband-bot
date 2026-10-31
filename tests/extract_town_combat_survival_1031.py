"""Freeze the 2026-10-31 19:26 n1-c life-067 town fight (D49 stop 1).

Source: C:/hengband-backups/pdca/captures/n1c-churn-1031-19/life-067/
incident-captures/20261031-192615-town-blocked-owner-retired-burst (viewing
Magic-Eater n1-c, Lv8, Outpost, build cfc32e192).  After a shop errand the
bot closed with わめくキチガイ (town:kill-mob-approach) and meleed it eleven
times, every blow missing (「ミス！…<x4>」); the arbiter charged the melee to
misc, retired it four blows in, and three retirements stopped the bot on
town:blocked:owner-retired-burst.

Frozen: ring rows 2020-2034 (one board per turn), the last skill-proficiency
and Home knowledge rows before them, the policy-state ``_me_staff_sequence``
record and the monster knowledge of their monsters.  The snapshot ring copy
is the tail of a multi-member gzip: decoding starts at the first member
header and keeps whole members only.  Only this extraction tool reads the
capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


CAPTURE = Path(
    "C:/hengband-backups/pdca/captures/n1c-churn-1031-19/life-067/"
    "incident-captures/20261031-192615-town-blocked-owner-retired-burst")
OUTPUT = Path(__file__).with_name("fixtures") / "town-combat-survival-20261031.json.gz"


def main():
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns = [], set()
    for row in rows[2020:2035]:
        if row["type"] == "player_turn" and row["turn"] not in turns:
            turns.add(row["turn"])
            boards.append(row)
    assert (boards[0]["turn"], boards[-1]["turn"]) == (157188, 157325)
    state = json.loads((CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    fixture = dict(
        source="incident-20261031-192615-town-blocked-owner-retired-burst (n1-c life-067)",
        boards=boards,
        skill=knowledge(rows, 2020, "skill_exp"),
        home=knowledge(rows, 2020, "home"),
        sequence=state["state"]["_me_staff_sequence"],
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
