"""Freeze the n1-b life-315 granite dig (2026-11-05) for the dig cap.

Source: the viewing Magic-Eater n1-b life-315 (Lv7), copied to
C:/hengband-backups/pdca/captures/mining-oil-1106/n1-b/life-315/:
decision-tail-135047.jsonl (decision rows 1059-2213 of the session that dug)
and the town-arrival checkpoints of the incidents 20261105-135017-loop-detected
(turn 94640, the Short Sword worn, digging 18) and
20261105-135047-town-blocked-survival-recall_departure_ready (turn 666059, the
same Short Sword in the pack and the Shovel worn, digging 36).  Mining on Yeek
cave 1F, 'ta' and 'wg' swapped the Shovel in at turns 111276-111281, and
fundraise:dig-to-treasure posted T9 at (5, 55) into the granite wall at
(4, 56) from turn 111300 on: each post was 99 tries (the board's
「花崗岩の壁に穴を掘っている。 <x99>」, about 990 game turns at speed 110).

Frozen: the two boards, the two-weapon and shield skill_exp the checkpoint's
policy cached from ~f (``_skill_exp_cache`` of policy.pkl, pickled on Linux),
and the recorded decision rows of the swap, of the
first four T9 posts and of the light swap (decision sequences 1664-1670 and
2197-2198).  Only this extraction tool reads the capture; the committed test
reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import pickle
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/mining-oil-1106/n1-b/life-315")
TAIL = CAPTURE / "decision-tail-135047.jsonl"
ARRIVALS = CAPTURE / "incident-captures"
BOARDS = {
    "sword": ARRIVALS / "20261105-135017-loop-detected/town-arrival/board.json",
    "shovel": ARRIVALS
    / "20261105-135047-town-blocked-survival-recall_departure_ready/town-arrival/board.json",
}
OUTPUT = Path(__file__).with_name("fixtures") / "dig-cap-life315-20261105.json.gz"
SEQUENCES = frozenset({1664, 1665, 1666, 1667, 1668, 1669, 1670, 2197, 2198})
DECISION_FIELDS = (
    "decision_sequence", "turn", "reason", "key", "position", "floor", "player",
    "messages", "fundraising", "mining", "light_radius",
)
# The town map and the operation receipt of the arrival are not the dig's.
DROPPED = ("grid_map", "_completed_operation_owner", "_completed_operation_receipt",
           "_completed_operation_sequence")


def decisions() -> list[dict]:
    found = []
    with TAIL.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # the tail starts inside a row
            if row.get("decision_sequence") in SEQUENCES:
                found.append({name: row.get(name) for name in DECISION_FIELDS})
    return found


def skill_exp() -> list[int]:
    pathlib.PosixPath = pathlib.WindowsPath  # the checkpoint was pickled on Linux
    with (BOARDS["shovel"].parent / "policy.pkl").open("rb") as stream:
        two_weapon, shield, level, _epoch = pickle.load(stream)["_skill_exp_cache"]
    assert level == 7
    return [two_weapon, shield]


def main():
    boards = {}
    for name, path in BOARDS.items():
        board = json.loads(path.read_text(encoding="utf-8"))
        boards[name] = {field: value for field, value in board.items() if field not in DROPPED}
    rows = decisions()
    assert [row["decision_sequence"] for row in rows] == sorted(SEQUENCES)
    assert boards["sword"]["player"]["skill_ratings"]["digging"]["value"] == 18
    assert boards["shovel"]["player"]["skill_ratings"]["digging"]["value"] == 36
    case = {
        "source": str(CAPTURE),
        "boards": boards,
        "decisions": rows,
        "skill_exp": skill_exp(),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT, len(rows))


if __name__ == "__main__":
    main()
