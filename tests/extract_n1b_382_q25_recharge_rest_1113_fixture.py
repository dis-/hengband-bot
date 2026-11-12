"""Freeze n1-b life-382's Quest 25 boards 04:42:47-04:42:54 (2026-11-13) for the recharge-rest test.

Source: n1-b life-382 (Magic-Eater Lv37, the resumed life-378) on hengband.net, the loop-detected
stop ~/hengbot-soak/n1-b/life-382/captures/20261113-044257-loop-detected (state.jsonl.gz and
bot-decisions.jsonl.gz), copied to the implementer's scratch: the last decisions before the stop
from decision 5124 ([7,1], the haste and the walk to [5,1], ten shots at the pen, then eleven
rounds of the three list reads and 'R100' quest25:rest-recharge).

One board per recorded decision (the decisions of one turn take that turn's last rows in order)
with its decision row's messages and the recorded reason and key.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
from pathlib import Path

from tests.extract_n1c_174_q25_loops_1109_fixture import ring_rows

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-382-q25-recharge-rest-1113.json.gz"
FIRST = 5124


def main():
    rows = ring_rows(ROOT / "state.jsonl.gz")
    decisions = []
    with gzip.open(ROOT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("decision_sequence", -1) >= FIRST and row.get("reason") not in (None, "loop-detected"):
                decisions.append(row)
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
        assert (board["player"]["y"], board["player"]["x"]) == (row["position"]["y"], row["position"]["x"])
        boards.append(dict(board, messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(dict(source="n1b-382-q25-recharge-rest-1113", boards=boards, recorded=recorded),
                  stream, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']}\n")


if __name__ == "__main__":
    main()
