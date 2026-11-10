"""Freeze n1-b life-362's two loop stops of 2026-11-10 (Orc cave 23F, build bot-f6b56516a).

Sources: the automatic incident captures copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-362-loops-1110/ (the stops' captures/ next to them for
the decision logs):

  a  20261110-093208-loop-detected (captures/20261110-093210-loop-detected): the step off the
     cold zone alternating '1' and '9' between (38,44) and (39,43).  Ring boards of turns
     5136333 (the player on (36,49), the last safe cell before the corridor) to 5136546.
  b  20261110-093231-loop-detected (captures/20261110-093232-loop-detected): the restarted
     process, from its first board (turn 5136550) to 5136646: the ESP hunt '4' at (34,53)
     and the exploration '6' at (34,52).

The 09:32:50 stop (captures/20261110-093250-loop-detected, incident 093244) is b again after
the second restart; it is not frozen.  Each case keeps every player board of the ring (one per decision) and the
recorded decision rows of the same turns.  Only this tool reads the captures; the committed
tests read the frozen fixtures alone.
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1b-362-loops-1110")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-362-loops-1110"
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")
CASES = {
    "a": ("20261110-093208-loop-detected", "20261110-093210-loop-detected", (5136333, 5136546)),
    "b": ("20261110-093231-loop-detected", "20261110-093232-loop-detected", (5136550, 5136646)),
}


def freeze(name, incident, capture, span):
    first, last = span
    boards, turns = [], set()
    for row in ring_rows(ROOT / incident / "snapshots" / "snapshots-current.jsonl.gz"):
        if row["type"] == "player_turn" and first <= row["turn"] <= last:
            turns.add(row["turn"])
            boards.append(row)
    assert {first, last} <= turns, (name, first, last)
    decisions = []
    with gzip.open(ROOT / capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("turn") in turns and row.get("reason") not in (None, "loop-detected"):
                decisions.append({field: row.get(field) for field in DECISION_FIELDS})
    fixture = {"source": f"{incident} (copied from the viewing server)",
               "boards": boards, "decisions": decisions}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{name}.json.xz"
    output.write_bytes(lzma.compress(json.dumps(
        fixture, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
    return output


def main():
    for name, (incident, capture, span) in CASES.items():
        output = freeze(name, incident, capture, span)
        print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
