"""Freeze n1-c life-178's last Quest 25 boards (2026-11-09 07:37:32-07:37:38) for the death test.

Source: n1-c life-178 (life-174/176 resumed, build a4a23664a) on hengband.net, the player-death
capture of 07:37:38 (~/hengbot-soak/n1-c/life-178/incident-captures/20261109-073738-player-death),
copied to C:/hengband-backups/pdca/captures/n1c-178-q25-death-1109/.  The process started at
07:27 on the Q25 floor (the resume of turn 4089201) and died at decision 5226 (turn 4141063).

Kept, one board per recorded decision (decision-tail.jsonl holds decisions 5180-5226; the
decisions of one turn take that turn's last rows of the ring in order), each with its decision
row's messages, and the recorded reason and key beside it:
 * ``boards`` / ``recorded``: decisions 5180-5226 (the tome phase on [5,5] through the death);
 * ``lists``: the magic-eater lists of the life's town-arrival checkpoint (03:16:03), the same
   counts the death dump lists (ドラゴンの火炎 5, 体力回復 4 at 32%, テレポート 15);
 * ``battle``: the Q25 battle record the process left (jsonlog/q25-battle.json at the death);
 * ``process_keys``: every key the 07:27 process posted (bot-stdout.log), the evidence that it
   never browsed (``b``) nor cast (``m``) an absorbed power.

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


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-178-q25-death-1109")
INCIDENT = ROOT / "20261109-073738-player-death"
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-178-q25-death-1109.json.gz"
QUEST = 25
RINGS = ("snapshots-20261109-073552-52b655.jsonl.gz", "snapshots-current.jsonl.gz")
# Fetched read-only beside the capture: the process's stdout (its posted keys) and the battle
# record (jsonlog/q25-battle.json) of ~/hengbot-soak/n1-c/life-178/.
STDOUT = ROOT / "server" / "bot-stdout.log"
BATTLE = ROOT / "server" / "q25-battle.json"


def main():
    rows = []
    for name in RINGS:
        rows += ring_rows(INCIDENT / "snapshots" / name)
    by_turn = collections.defaultdict(list)
    for row in rows:
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
    decisions = [row for row in decision_rows(INCIDENT / "decision-tail.jsonl")
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
    keys = STDOUT.read_text(encoding="utf-8", errors="replace").split("\n")
    keys = [key for key in keys if key]
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    ids |= {557, 480, 748, 571, 739}
    case = dict(source="n1c-178-q25-death-1109", boards=boards, recorded=recorded, lists=lists,
                battle=json.loads(BATTLE.read_text(encoding="utf-8")),
                process_keys=keys,
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} {len(keys)} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
