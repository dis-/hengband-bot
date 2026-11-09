"""Freeze the boards of the n1-a life-501 death (2026-11-09 19:26, イークの洞穴13階).

Source, copied read-only from the analysis folder
C:/hengband-backups/pdca/captures/n1a-501-death-1109 (REPORT.txt):

  state-tail400.jsonl            the last state rows of the life (player_turn boards)
  decision-tail-last3MB.jsonl    the live decision rows of the same window

The fixture keeps the player_turn boards of the last 13F visit (from game turn 419161, the
arrival, to 419662, the last board: 'o1' opened the door behind which the ゲイザー and
ボルドールの息子『オルファックス』 stood; no board shows either) and, for each, the decision row
of its turn (sequence, turn, reason, key).  One board per decision row: the last board of the
row's game turn, its messages replaced by the row's messages (the live process merges the
messages of a board it did not decide on into the next decision).  Only this tool reads the copies; the tests read the fixture.

    python tests/extract_n1a_501_fixture.py <capture-dir>
"""

from __future__ import annotations

import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "death-n1a-501-1109.json.xz"
ARRIVAL_TURN = 419161


def main() -> None:
    capture = Path(sys.argv[1])
    with (capture / "state-tail400.jsonl").open(encoding="utf-8") as stream:
        states = [json.loads(line) for line in stream]
    boards = [raw for raw in states
              if raw.get("type") == "player_turn" and raw["turn"] >= ARRIVAL_TURN]
    rows = []
    with (capture / "decision-tail-last3MB.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:  # the tail's first line is cut
                continue
    decided, decisions = [], []
    for row in rows:
        if row.get("turn", 0) < ARRIVAL_TURN:
            continue
        same = [raw for raw in boards if raw["turn"] == row["turn"]]
        if not same:
            continue
        decided.append(dict(same[-1], messages=row["messages"]))
        decisions.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                          "reason": row["reason"], "key": row["key"]})
    payload = {"boards": decided, "decisions": decisions}
    FIXTURE.write_bytes(lzma.compress(
        json.dumps(payload, ensure_ascii=False).encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
