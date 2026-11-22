"""Extract tests/fixtures/n1c-220-q33-rest-loop-1122/ (q33-rest-loop-1122).

Source: n1-c life-220's stop of 2026-11-22 18:29:56 (loop-detected on Quest 33, floor (0, 45, 33),
bot main 5c5f6c353), the capture captures/20261122-182956-loop-detected (copied to
C:/hengband-backups/pdca/n1c-220-detect-loop/):

- ``decisions.json.xz``: every decision row of the capture's bot-decisions.jsonl.gz (the stop is the
  last), reduced to what the driver's cell loop guard reads (cli._cell_loop_guard_applies,
  cli._is_looping): the key, the reason, the floor, the position, the HP and MP, the board's messages.
- ``boards.json.xz``: the capture's state.jsonl.gz boards from FIRST_TURN on (the rests and the board
  after the stop), as the game wrote them.

    python tests/extract_n1c_220_q33_rest_loop_1122_fixture.py [CAPTURE]
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

CAPTURE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "C:/hengband-backups/pdca/n1c-220-detect-loop/20261122-182956-loop-detected")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-220-q33-rest-loop-1122"
FIRST_TURN = 3147946  # the first rest decision of the stretch (decision 24459)


def lines(name):
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


if __name__ == "__main__":
    reduced = [{
        "turn": row.get("turn"), "key": row.get("key"), "reason": row.get("reason"),
        "floor": row.get("floor"), "position": row.get("position"),
        "hp": row["player"].get("hp"), "mp": row["player"].get("mp"),
        "messages": row.get("messages") or [],
    } for row in lines("bot-decisions.jsonl.gz")]
    boards = [board for board in lines("state.jsonl.gz") if board["turn"] >= FIRST_TURN]
    FIXTURE.mkdir(parents=True, exist_ok=True)
    for name, value in (("decisions.json.xz", reduced), ("boards.json.xz", boards)):
        (FIXTURE / name).write_bytes(
            lzma.compress(json.dumps(value, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(len(reduced), len(boards), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
