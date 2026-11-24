"""Freeze n1-c life-222's Quest 25 tome-phase boards of the walk / walk-to-sight alternation.

Source: n1-c life-222 (Zombie Magic-Eater Lv37) on hengband.net, owner-halted 2026-11-25 00:31:03
with ``livelock-exhausted`` in Quest 25 (floor (0,48,25)).  The incident capture
~/hengbot-soak/n1-c/life-222/incident-captures/20261125-003056-livelock-exhausted is copied to
C:/hengband-backups/pdca/captures/n1c-222-q25-walk-pingpong-1125: ``decision-tail.jsonl`` (the
last decisions), ``snapshots-current.jsonl.gz`` (the boards from turn 3028277),
``snapshots-20261125-002751-964312.jsonl.gz`` (the generation before it: the last ``skill_exp``
row), ``q25-battle.json`` (jsonlog/q25-battle.json, the record the process left at the halt) and
``town-arrival-me-lists.json`` (the magic-eater lists of the life's last town-arrival pickle,
turn 2913263-2914139; no board carries them, the client reads them off the screen).

Boards are matched to decisions by turn as tests/extract_n1a_536_q25_pen_seen_1124_fixture.py
matches them; the cut is decisions ``FIRST``-``LAST`` (the walk to a sight onto [4,8] through the
halt).  Only this extraction tool reads the capture; the committed test reads the fixture alone.

    python tests/extract_n1c_222_q25_walk_pingpong_1125_fixture.py <copy directory>
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-222-q25-walk-pingpong-1125.json.gz"
QUEST = 25
FIRST, LAST = 41220, 41234


def _rows(path: Path, opener=gzip.open):
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue   # a live file's line may be cut


def main():
    decisions = [row for row in _rows(ROOT / "decision-tail.jsonl", open)
                 if row.get("floor", {}).get("quest_id") == QUEST and FIRST <= row["decision_sequence"] <= LAST]
    sequences = [row["decision_sequence"] for row in decisions]
    assert sequences == list(range(FIRST, LAST + 1)), sequences
    first_turn = decisions[0]["turn"]
    skill = None
    for row in _rows(ROOT / "snapshots-20261125-002751-964312.jsonl.gz"):
        if (row.get("type") == "knowledge" and row["knowledge"].get("category") == "skill_exp"
                and row.get("turn", 0) <= first_turn):
            skill = row
    by_turn = collections.defaultdict(list)
    for row in _rows(ROOT / "snapshots-current.jsonl.gz"):
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
    need = collections.Counter(row["turn"] for row in decisions)
    used = collections.Counter()
    boards, recorded = [], []
    for row in decisions:
        same = by_turn[row["turn"]]
        board = same[len(same) - need[row["turn"]] + used[row["turn"]]]
        used[row["turn"]] += 1
        position = row["position"]
        assert (board["player"]["y"], board["player"]["x"]) == (position["y"], position["x"]), row
        boards.append(dict(board, messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    assert skill is not None
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    ids |= {557}   # the tome the phase aims at
    lists = json.loads((ROOT / "town-arrival-me-lists.json").read_text(encoding="utf-8"))
    case = dict(source="n1c-222-q25-walk-pingpong-1125", second=dict(boards=boards, recorded=recorded),
                skill=skill, monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
                me_lists=lists)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']}\n")


if __name__ == "__main__":
    main()
