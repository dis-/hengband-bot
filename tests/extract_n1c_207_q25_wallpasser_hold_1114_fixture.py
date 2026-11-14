"""Freeze n1-c life-207's Quest 25 boards (2026-11-14 17:23-17:54) for the wall-passers' hold test.

Source: n1-c life-207 (Magic-Eater Lv49) on hengband.net.  The stop: the capture
~/hengbot-soak/n1-c/life-207/captures/20261114-175423-stall-floor-dwell-quest-strategy-hold (its
state ring and decisions 17171-17331 of the process started 17:23; the ring holds 17232-17331), copied to
C:/hengband-backups/pdca/q25-hold-1114/capture-175423 with jsonlog/warning-cells.json as the stop
left it (``warning-cells-1754.json``).  Before it, the process held without a stop: the decision
log ~/hengbot-soak/n1-c/life-207/jsonlog/bot-decisions.jsonl (.2, .1 and the current one) and
the snapshot logs jsonlog/snapshots/snapshots-20261114-173247-c43fda.jsonl.gz and
snapshots-current.jsonl.gz, cut on the server to their Quest 25 rows
(``decisions``: the decision rows' sequence, turn, reason, key, messages, position; ``boards``: the
``player_turn`` rows; ``knowledge``: the knowledge rows) and copied with jsonlog/q25-battle.json
and jsonlog/warning-cells.json (17:42, the process still holding) to
C:/hengband-backups/pdca/q25-hold-1114.

One board per recorded decision (each decided turn has one ``player_turn`` row here):

 * ``refusal``: decisions 3973-3975, the ambush's step onto [9,1] (``quest25:engage``), the weapon
   warning's prompt on the next board and the board after it, whole.
 * ``stop``: the capture's decisions whose boards its ring holds (17:54:0x-17:54:23), cut as
   tests/extract_n1b_382_q25_patrol_owner_1113_fixture.py cuts a capture (its ``process``).
 * ``close``: the restarted process of 18:49 (decisions 0-4, to its stuck-prompt stop at 18:49:13),
   from the capture 20261114-184915-stuck-prompt-quest25-close-door (copied to capture-184915),
   cut the same way (``restarted``), with jsonlog/q25-battle.json as that process left it
   (``q25-battle-1849.json``: phase 0, no kills; the reloaded save's turn 8010826).
 * ``hold``: decisions 4072-4211 (17:24:04-17:24:2x), the wall-passers' phase holding on [10,1]
   (``quest-strategy:hold`` '5', nothing in view, the nine shadow demons sensed in the walls).
   Between these boards (and between the stop's) only ``turn``, ``clock``, ``messages``,
   ``detected_monsters`` and the player's ``speed`` / ``speed_display`` change, so the first is
   kept whole (``base``) and every board as those fields (``changes``); the extraction checks each
   rebuilds to the recorded row.

Only this extraction tool reads the copies; the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests import extract_n1b_382_q25_patrol_owner_1113_fixture as capture

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/q25-hold-1114")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-207-q25-wallpasser-hold-1114.json.gz"
REFUSAL = (3973, 3974, 3975)
HOLD = range(4072, 4212)
CHANGED = ("turn", "clock", "messages", "detected_monsters")
PLAYER_CHANGED = ("speed", "speed_display")


def changes(board: dict) -> dict:
    return {**{key: board[key] for key in CHANGED},
            "player": {key: board["player"][key] for key in PLAYER_CHANGED}}


def rebuilt(base: dict, change: dict) -> dict:
    board = dict(base, **{key: change[key] for key in CHANGED})
    board["player"] = dict(base["player"], **change["player"])
    return board


def compact(boards) -> dict:
    """``boards`` as the first whole and each one's changing fields (checked to rebuild)."""
    base = boards[0]
    found = [changes(board) for board in boards]
    for board, change in zip(boards, found):
        assert rebuilt(base, change) == board, board["turn"]
    return dict(base=base, changes=found)


def main():
    with gzip.open(ROOT / "q25-rows.json.gz", "rt", encoding="utf-8") as stream:
        rows = json.load(stream)
    by_turn = collections.defaultdict(list)
    for board in rows["boards"]:
        by_turn[board["turn"]].append(board)
    # The 17:23 process's decisions (an earlier process reused the sequence numbers off Q25).
    decisions = {row["decision_sequence"]: row for row in rows["decisions"]
                 if row["time"] < "2026-11-14T17:27"}

    def cut(sequence):
        row = decisions[sequence]
        same = by_turn[row["turn"]]
        board = same[-1]
        position = row["position"]
        assert (board["player"]["y"], board["player"]["x"]) == (position["y"], position["x"]), row
        recorded = {"sequence": sequence, "turn": row["turn"], "reason": row["reason"],
                    "key": row["key"], "messages": row["messages"]}
        return dict(board, messages=row["messages"]), recorded

    refusal = [cut(sequence) for sequence in REFUSAL]
    hold = [cut(sequence) for sequence in HOLD]
    assert all(row["key"] == "5" and row["reason"] == "quest-strategy:hold" for _board, row in hold)
    capture.ROOT = ROOT
    stop_boards, stop_recorded, _knowledge = capture.process("capture-175423", restarted=False)
    assert all(row["key"] == "5" and row["reason"] == "quest-strategy:hold" for row in stop_recorded)
    close_boards, close_recorded, _knowledge = capture.process("capture-184915", restarted=True)
    assert [row["sequence"] for row in close_recorded] == [0, 1, 2, 3, 4], close_recorded
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    boards = (*(board for board, _row in refusal), *(board for board, _row in hold), *stop_boards,
              *close_boards)
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1c-207-q25-wallpasser-hold-1114",
                refusal=dict(boards=[board for board, _row in refusal],
                             recorded=[row for _board, row in refusal]),
                hold=dict(compact([board for board, _row in hold]),
                          recorded=[row for _board, row in hold]),
                stop=dict(compact(stop_boards), recorded=stop_recorded),
                close=dict(boards=close_boards, recorded=close_recorded,
                           battle_record=json.loads(
                               (ROOT / "q25-battle-1849.json").read_text(encoding="utf-8"))),
                skill=rows["knowledge"]["skill_exp"][-1],
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
                warning_record=json.loads((ROOT / "warning-cells.json").read_text(encoding="utf-8")),
                stop_warning_record=json.loads(
                    (ROOT / "warning-cells-1754.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(refusal)} {len(hold)} {len(stop_boards)} "
                     f"{stop_recorded[0]['sequence']}-{stop_recorded[-1]['sequence']}\n")


if __name__ == "__main__":
    main()
