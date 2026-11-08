"""Freeze n1-c life-176's Quest 25 boards (2026-11-09 04:18:17-04:18:34) for the trap-search test.

Source: n1-c life-176 (life-174 resumed, build 47982d326) on hengband.net, the three loop-detected
stops of 04:18:20, 04:18:25 and 04:18:32 (~/hengbot-soak/n1-c/life-176/incident-captures/),
copied to C:/hengband-backups/pdca/captures/n1c-174-q25-loops-1109/life176/incident/.  The game
was resumed from turn 4088202 (the board life-174's 03:17:00 process started on), so the ring holds
two sets of boards of the same turns; the later rows are the resumed process's.

Three processes are kept, in order, one board per recorded decision on the quest floor (the
decisions of one turn take that turn's last rows in order), each board with its decision row's
messages and the recorded reason and key:
 * ``first``: 04:18:17, decisions 0-102 (turns 4088202-4088791);
 * ``second``: 04:18:24, decisions 0-39 (turns 4088803-4089187);
 * ``third``: 04:18:31, decisions 0-39 (turns 4089201-) through its stop.
``lists`` are the magic-eater lists of the life's town-arrival checkpoint (03:16:03).

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import pickle
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_174_q25_loops_1109_fixture import decision_rows, ring_rows
import collections


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-174-q25-loops-1109/life176/incident")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-176-q25-trap-search-1109.json.gz"
QUEST = 25
RING = "20261109-041832-loop-detected"
PROCESSES = (
    ("first", "20261109-041820-loop-detected", "2026-11-09T04:18:17"),
    ("second", "20261109-041825-loop-detected", "2026-11-09T04:18:24"),
    ("third", "20261109-041832-loop-detected", "2026-11-09T04:18:31"),
)


def main():
    rows = ring_rows(ROOT / RING / "snapshots" / "snapshots-current.jsonl.gz")
    by_turn = collections.defaultdict(list)
    for row in rows:
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
    case = {"source": "n1c-176-q25-trap-search-1109"}
    starts = [start for _, _, start in PROCESSES] + ["9999"]
    for (part, directory, start), end in zip(PROCESSES, starts[1:]):
        decisions = [row for row in decision_rows(ROOT / directory / "decision-tail.jsonl")
                     if start <= row.get("time", "") < end
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
                             "reason": row["reason"], "key": row["key"]})
        case[part] = dict(boards=boards, recorded=recorded)
    knowledge = {}
    for row in rows:
        if row.get("type") == "knowledge":
            knowledge[row["knowledge"]["category"]] = row
    case["skill"], case["home"] = knowledge.get("skill_exp"), knowledge.get("home")
    # The checkpoint was pickled on Linux; its runtime paths are PosixPath.
    pathlib.PosixPath = pathlib.WindowsPath if sys.platform == "win32" else pathlib.PosixPath
    with (ROOT / PROCESSES[0][1] / "town-arrival" / "policy.pkl").open("rb") as stream:
        state = pickle.load(stream)
    case["lists"] = {kind: [turn, list(rows)] for kind, (turn, rows) in state["_me_device_lists"].items()}
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for part, _, _ in PROCESSES for board in case[part]["boards"]
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case["monraces"] = {key: asdict(races[key]) for key in sorted(ids) if key in races}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sizes = {part: len(case[part]["boards"]) for part, _, _ in PROCESSES}
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {sizes}\n")


if __name__ == "__main__":
    main()
