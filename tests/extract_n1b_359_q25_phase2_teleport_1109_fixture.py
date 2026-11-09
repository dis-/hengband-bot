"""Freeze n1-b life-359's Quest 25 visit (2026-11-09 14:23:55-14:24:03) for the phase-2 teleport test.

Source: n1-b life-359 on hengband.net, the loop-detected capture of 14:24:24
(~/hengbot-soak/n1-b/life-359/incident-captures/20261109-142424-loop-detected), copied to
C:/hengband-backups/pdca/captures/q25-phase2-teleport-1109/.  One process decided the whole
visit: it arrived in town at 14:22:33 (the capture's town-arrival checkpoint), entered the Q25
floor at decision 642 (turn 2610817) and read Teleportation on [5,1] in phase 2 at decisions 833
(14:24:00) and 927 (14:24:03), reason ``quest25:teleport``.

Kept, one board per recorded decision on the Q25 floor from the entry (642) through 927 (the
decisions of one turn take that turn's last rows of the ring in order), each with its decision
row's messages and the recorded reason and key beside it; ``lists``: the magic-eater lists the
process held at the town arrival (the checkpoint's ``_me_device_lists``).

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import gzip
import json
import pathlib
import pickle
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_174_q25_loops_1109_fixture import decision_rows, ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/q25-phase2-teleport-1109")
INCIDENT = ROOT / "20261109-142424-loop-detected"
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-359-q25-phase2-teleport-1109.json.gz"
QUEST = 25
FIRST, LAST = 642, 927


def main():
    rows = ring_rows(INCIDENT / "snapshots" / "snapshots-current.jsonl.gz")
    by_turn = collections.defaultdict(list)
    for row in rows:
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
    decisions = [row for row in decision_rows(INCIDENT / "decision-tail.jsonl")
                 if FIRST <= row["decision_sequence"] <= LAST
                 and row.get("floor", {}).get("quest_id") == QUEST]
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
                         "reason": row["reason"], "key": row["key"],
                         "hp": row["player"]["hp"], "max_hp": row["player"]["max_hp"]})
    knowledge = {}
    for row in rows:
        if row.get("type") == "knowledge":
            knowledge[row["knowledge"]["category"]] = row
    # The checkpoint was pickled on Linux; its runtime paths are PosixPath.
    pathlib.PosixPath = pathlib.WindowsPath if sys.platform == "win32" else pathlib.PosixPath
    with (INCIDENT / "town-arrival" / "policy.pkl").open("rb") as stream:
        state = pickle.load(stream)
    lists = {kind: [turn, list(rows)] for kind, (turn, rows) in state["_me_device_lists"].items()}
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    ids |= {571, 508, 665}
    case = dict(source="n1b-359-q25-phase2-teleport-1109", boards=boards, recorded=recorded, lists=lists,
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
