"""Freeze n1-a life-508's Quest 25 boards (2026-11-11 04:39:13-04:39:29) for the trap-walk test.

Source: n1-a life-508 (build 0850e2334) on hengband.net, the loop-detected stop of 04:39:29
(~/hengbot-soak/n1-a/life-508/incident-captures/20261111-043929-loop-detected and
captures/20261111-043930-loop-detected), copied to
C:/hengband-backups/pdca/captures/n1a-508-q25-trapsearch-1111/.

One process: every recorded decision on the Q25 floor, from the first (decision 3902, the floor
entered in this process) through the last before the stop (4130), one board per decision (the
decisions of one turn take that turn's last rows in order) with its decision row's messages and
the recorded reason and key.  The ring's two last generations hold the boards
(snapshots-20261111-043916-880e82 up to turn 3873377, snapshots-current from 3873382).

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_174_q25_loops_1109_fixture import decision_rows, ring_rows

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-508-q25-trapsearch-1111/incident")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-508-q25-trap-walk-1111.json.gz"
QUEST = 25
RINGS = ("snapshots-20261111-043916-880e82.jsonl.gz", "snapshots-current.jsonl.gz")


def main():
    rows = [row for ring in RINGS for row in ring_rows(ROOT / "snapshots" / ring)]
    by_turn = collections.defaultdict(list)
    for row in rows:
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
    decisions = [row for row in decision_rows(ROOT / "decision-tail.jsonl")
                 if row.get("floor", {}).get("quest_id") == QUEST]
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
    case = {"source": "n1a-508-q25-trap-walk-1111", "boards": boards, "recorded": recorded}
    knowledge = {}
    for row in rows:
        if row.get("type") == "knowledge" and row["turn"] <= recorded[0]["turn"]:
            knowledge[row["knowledge"]["category"]] = row
    case["skill"], case["home"] = knowledge.get("skill_exp"), knowledge.get("home")
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case["monraces"] = {key: asdict(races[key]) for key in sorted(ids) if key in races}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} boards "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']}\n")


if __name__ == "__main__":
    main()
