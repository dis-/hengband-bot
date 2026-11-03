"""Freeze the n1-b life-306 Q14 recall bounce boards (recall-bounce-1104).

Source (read-only): C:/hengband-backups/pdca/captures/stops-1103-night/n1-b/
life-306/incident-captures/20261103-213349-town-blocked-unmet-home_candidate_resolved
(build e9e2c1262, the same arrival checkpoint as town-stops-1103/temple-loop).

- town-read: the board of decision 20758 (town:recall-to-yeek-cave, 'rgb'),
  4 Teleportation and 7 Recall carried.
- landing: the board of decision 20783 (return:recall, 'rg') on Yeek cave 5F.
- alchemist: the last Alchemist page the ring holds before the read.

Only this tool reads the capture; the test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import decisions_by_turn, sha, tail_rows
from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURE = Path(
    "C:/hengband-backups/pdca/captures/stops-1103-night/n1-b/life-306/incident-captures/"
    "20261103-213349-town-blocked-unmet-home_candidate_resolved")
OUTPUT = Path(__file__).with_name("fixtures") / "recall-bounce-1104.json.gz"
TOWN_READ_TURN = 1574351
LANDING_TURN = 1574621
STORE_ALCHEMIST = 4


def main():
    ring = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
    tail = CAPTURE / "decision-tail.jsonl"
    rows = ring_rows(ring.read_bytes())
    decisions = decisions_by_turn(tail_rows(tail))
    by_type_turn = {(row.get("type"), row.get("turn")): row for row in rows}
    alchemist = [row for row in rows
                 if row.get("type") == "store" and row["store"]["store_type"] == STORE_ALCHEMIST
                 and row["turn"] <= TOWN_READ_TURN][-1]
    case = dict(
        source=CAPTURE.name,
        sources={ring.name: sha(ring), tail.name: sha(tail)},
        town_read=by_type_turn["player_turn", TOWN_READ_TURN],
        landing=by_type_turn["player_turn", LANDING_TURN],
        alchemist=alchemist,
        landing_decision=decisions[LANDING_TURN],
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
