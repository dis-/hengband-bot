"""Extract tests/fixtures/n1c-221-q33-mixed-1123/ (n1c-221-q33-mixed-1123).

Source: n1-c life-221's stop of 2026-11-23 13:58:24 (Quest 33, floor (0, 45, 33), bot main 2e85676a9,
``loop-detected`` on [(11, 38), (12, 37), (13, 37), (14, 37), (15, 38), (15, 39)]), the server's capture
``~/hengbot-soak/n1-c/life-221/captures/20261123-135824-loop-detected``, with the floor's records read
beside it:

- ``boards.json.xz``: the capture's state.jsonl.gz boards of the player's turn from FIRST_TURN on (the
  Detect Evil at [1,43], the walk to [15,39] and the 33 casts there), as the game wrote them.
- ``decisions.json.xz``: the capture's decision rows from FIRST_TURN on, reduced to the turn, the
  position, the key and the reason.
- ``sweep-kills.json``: the room sweep's restart record at the stop (jsonlog/sweep-kills.json,
  quest_sweep_record): It 393 x2, Bokrug 489 x2, Dagon 595 x3, Queen 581 x2.
- ``me-power-uses.json``: the absorbed powers' landed uses of the floor from 4492300 on (the capture's
  policy-state ``_me_power_floor.uses``): the Rod of Detection's Powerful Activation at [7,72] on
  4492322, the Staff of Detect Evil at [1,43] and the 30 casts at [15,39].

    python tests/extract_n1c_221_q33_mixed_1123_fixture.py CAPTURE EXTRACTS

EXTRACTS holds sweep-kills.json (as read on the server) and me-power-uses.json (from the capture).
"""
import gzip
import json
import lzma
import shutil
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-q33-mixed-1123"
FIRST_TURN = 4492832  # the last walk before the Detect Evil at [1,43]


def lines(capture, name):
    with gzip.open(capture / name, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


if __name__ == "__main__":
    capture, extracts = Path(sys.argv[1]), Path(sys.argv[2])
    boards = [board for board in lines(capture, "state.jsonl.gz")
              if board.get("type") == "player_turn" and board["turn"] >= FIRST_TURN]
    decisions = [{"turn": int(row["turn"]), "position": row.get("position"), "key": row.get("key"),
                  "reason": row.get("reason")}
                 for row in lines(capture, "bot-decisions.jsonl.gz") if int(row.get("turn") or 0) >= FIRST_TURN]
    FIXTURE.mkdir(parents=True, exist_ok=True)
    for name, value in (("boards.json.xz", boards), ("decisions.json.xz", decisions)):
        (FIXTURE / name).write_bytes(lzma.compress(
            json.dumps(value, ensure_ascii=False).encode("utf-8", "surrogateescape"), preset=PRESET))
    for name in ("sweep-kills.json", "me-power-uses.json"):
        shutil.copyfile(extracts / name, FIXTURE / name)
    print(len(boards), len(decisions), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
