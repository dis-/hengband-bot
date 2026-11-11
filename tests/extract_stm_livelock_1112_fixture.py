"""Extract the Stone to Mud pocket of n1-b life-370 (2026-11-12 00:50, Angband 80F, loop-detected).

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-370-stm-livelock-1112/:

  20261112-005048-loop-detected/state.jsonl.gz       the floor's state rows (boards and the
                                                     power_list reply), turns 8674881 on
  20261112-005048-loop-detected/bot-decisions.jsonl.gz  the live decision rows
  me-lists.json                                      the absorbed device lists the game last
                                                     displayed (the incident's town-arrival
                                                     checkpoint ``_me_device_lists``: kind ->
                                                     [turn, rows]), read with the bot's own code

Output: {"rows": the state rows from the floor's arrival (8674881) to the board after the sixth
use (8675192), "decisions": [sequence, turn, reason, key] of the live rows of the same floor up to
the stop, "lists": the device lists}.  Only this tool reads the copies; the tests read the fixture.

    python tests/extract_stm_livelock_1112_fixture.py <capture-dir> <me-lists.json>
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "stm-livelock-1112.json.xz"
FIRST_TURN, LAST_BOARD_TURN = 8674881, 8675192


def main() -> None:
    capture, lists = Path(sys.argv[1]), Path(sys.argv[2])
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8", errors="surrogateescape") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    rows = [row for row in rows if FIRST_TURN <= row["turn"] <= LAST_BOARD_TURN]
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8", errors="surrogateescape") as stream:
        decided = [json.loads(line) for line in stream if line.strip()]
    decisions = [[row["decision_sequence"], row["turn"], row["reason"], row["key"]]
                 for row in decided if row["turn"] >= FIRST_TURN]
    payload = {"rows": rows, "decisions": decisions,
               "lists": json.loads(lists.read_text(encoding="utf-8"))}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    FIXTURE.write_bytes(lzma.compress(data.encode("utf-8", "surrogateescape")))
    print(FIXTURE, FIXTURE.stat().st_size, len(rows), len(decisions))


if __name__ == "__main__":
    main()
