"""Extract tests/fixtures/n1c-221-q33-sweep-1123/ (n1c-221-sweep-1123).

Source: n1-c life-221's stop of 2026-11-23 13:00:04 (Quest 33, floor (0, 45, 33), bot main 57a80bc0a,
``quest:blocked:sweep-nothing-comes``), the server's capture
``~/hengbot-soak/n1-c/life-221/captures/20261123-130004-quest-blocked-sweep-nothing-comes``, with three
files read from the same life's jsonlog beside it:

- ``boards.json.xz``: the capture's state.jsonl.gz boards of the player's turn from FIRST_TURN on (the
  walk after the Dagons, the teleport to [7,72], the detection there and the stop), as the game wrote them.
- ``decisions.json.xz``: the capture's decision rows from FIRST_TURN on, reduced to the turn, the
  position, the key and the reason.
- ``sweep-kills.json``: the room sweep's restart record at the stop (jsonlog/sweep-kills.json,
  quest_sweep_record): the kills its kill lines credited, It 393 x2, Bokrug 489 x2, Dagon 595 x3.
- ``kill-lines.json``: every line of the floor's decisions (jsonlog/bot-decisions.jsonl, turn 4484600 on)
  that names a death, (turn, text): the unnamed 「何かは死んだ。」 at 4485506 and 「何かを倒した。」 at 4491012.
- ``detections.json``: the boards after the floor's detections (jsonlog/snapshots/snapshots-current), the
  player's cell and the monsters detected (race, y, x, by telepathy): the It last on 4485142, one Bokrug
  from 4486914 on, none of either on 4492306.

    python tests/extract_n1c_221_q33_sweep_1123_fixture.py CAPTURE JSONLOG_EXTRACTS

JSONLOG_EXTRACTS holds sweep-kills.json, kill-lines.json and detections.json as read on the server.
"""
import gzip
import json
import lzma
import shutil
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-q33-sweep-1123"
FIRST_TURN = 4492262  # the last walk before the Boshin's death and the summons that sent the teleport


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
    for name in ("sweep-kills.json", "kill-lines.json", "detections.json"):
        shutil.copyfile(extracts / name, FIXTURE / name)
    print(len(boards), len(decisions), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
