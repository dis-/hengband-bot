"""Freeze n1-c life-174's Quest 25 boards (2026-11-09 03:16:34-03:17:01) for the loop test.

Source: n1-c life-174 on hengband.net, the three loop-detected stops of 03:16:46, 03:16:55
and 03:17:01, copied to C:/hengband-backups/pdca/captures/n1c-174-q25-loops-1109/.  Each
incident-* directory holds the tail of the snapshot ring (snapshots/snapshots-current.jsonl.gz,
appended gzip members, so the copy starts mid-member) and the tail of the decision log
(decision-tail.jsonl).

Two processes are kept, in order, one board per recorded decision on the quest floor:
 * ``first``: the process that took the floor (decision 783, turn 4085691) through its loop stop
   (decision 1099, turn 4087781);
 * ``second``: the restarted process (decisions 0-69, turns 4087781-4088197) through its stop;
 * ``third``: the next restart (decisions 0-39, turns 4088202-4088492) through its stop.
The magic-eater lists (``_me_device_lists``) the first process held at its town arrival
(03:16:03, incident-*/town-arrival/policy.pkl, the same process) are kept as ``lists``: the ring's
boards do not carry the lists the executor read from the screen after each ``b``.
The ring holds one row per decision (a board the game showed the bot); the decisions of one turn
take that turn's last rows in order.  Each board carries the decision row's messages; the
recorded reason and key are kept beside it.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import gzip
import json
import pathlib
import pickle
import sys
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-174-q25-loops-1109")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-174-q25-loops-1109.json.gz"
QUEST = 25
FIRST = ("incident-20261109-031646-loop-detected", 783, 1099)
SECOND = ("incident-20261109-031655-loop-detected", 0, 69)
SECOND_START_TURN = 4087781
THIRD = ("incident-20261109-031701-loop-detected", 0, 39)
THIRD_START_TURN = 4088202
MAGIC = b"\x1f\x8b\x08"


def ring_rows(path: Path) -> list[dict]:
    """Every row of the copied ring tail (its first member may be cut)."""
    data = path.read_bytes()
    data = data[data.find(MAGIC):]
    rows, position = [], 0
    while 0 <= position < len(data):
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            out = stream.decompress(data[position:])
        except zlib.error:
            position = data.find(MAGIC, position + 1)
            continue
        for line in out.decode("utf-8", "replace").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        if not stream.eof:
            break
        position = len(data) - len(stream.unused_data)
    return rows


def decision_rows(path: Path) -> list[dict]:
    found = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "decision_sequence" in row and row.get("reason") != "loop-detected":
                found.append(row)
    return found


def process(directory: str, first: int, last: int, *, after_turn: int = 0):
    incident = ROOT / directory
    rows = ring_rows(incident / "snapshots" / "snapshots-current.jsonl.gz")
    decisions = [row for row in decision_rows(incident / "decision-tail.jsonl")
                 if first <= row["decision_sequence"] <= last and row["turn"] >= after_turn
                 and row.get("floor", {}).get("quest_id") == QUEST]
    by_turn = collections.defaultdict(list)
    for row in rows:
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
    knowledge = {}
    for row in rows:
        if row.get("type") == "knowledge":
            knowledge[row["knowledge"]["category"]] = row
    return boards, recorded, knowledge


def main():
    first_boards, first_recorded, knowledge = process(*FIRST)
    second_boards, second_recorded, _ = process(*SECOND, after_turn=SECOND_START_TURN)
    third_boards, third_recorded, _ = process(*THIRD, after_turn=THIRD_START_TURN)
    # The checkpoint was pickled on Linux; its runtime paths are PosixPath.
    pathlib.PosixPath = pathlib.WindowsPath if sys.platform == "win32" else pathlib.PosixPath
    with (ROOT / FIRST[0] / "town-arrival" / "policy.pkl").open("rb") as stream:
        state = pickle.load(stream)
    lists = {kind: [turn, list(rows)] for kind, (turn, rows) in state["_me_device_lists"].items()}
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in (*first_boards, *second_boards, *third_boards)
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1c-174-q25-loops-1109",
                first=dict(boards=first_boards, recorded=first_recorded),
                second=dict(boards=second_boards, recorded=second_recorded),
                third=dict(boards=third_boards, recorded=third_recorded), lists=lists,
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(first_boards)} {len(second_boards)} {len(third_boards)} "
                     f"{sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
