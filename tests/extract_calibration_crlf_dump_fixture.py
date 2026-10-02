"""Freeze the live 2026-10-02 16:58 equipped C-sheet dump and its inputs.

Sources (read-only, live checkout and game):
- ``C:/hengband/lib/user/bot-test.txt``: the game's dump (CP932, CRLF line
  ends), mtime 16:58, the last dump before the 17:00-17:01 town stops.
- ``jsonlog/bot-state-fixed.jsonl`` of the live checkout: the ``character``
  response at turn 3957292 (the C macro of that dump), the ``player_turn``
  decision board recorded right after it, and the last ``knowledge`` skill
  list (``~f``, turn 3942991) the same process read before it.

The rows are copied verbatim, one JSON line each, in the order
skill knowledge, character response, decision board.  The dump bytes are
stored gzip-compressed so no checkout rewrites its CRLF line ends.

Only this tool reads the live files; the committed test reads the frozen ones.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path("C:/hengband/bot-client/jsonlog/bot-state-fixed.jsonl")
DUMP = Path("C:/hengband/lib/user/bot-test.txt")
FIXTURES = ROOT / "tests" / "fixtures"
ROWS_OUT = FIXTURES / "calibration-crlf-dump-20261002.jsonl.gz"
DUMP_OUT = FIXTURES / "calibration-crlf-dump-20261002.bot-test.txt.gz"
SKILL_OFFSET = 221063338
CHARACTER_OFFSET = 250621022


def _row_at(stream, offset: int) -> bytes:
    stream.seek(offset)
    return stream.readline()


def main() -> None:
    with STATE.open("rb") as stream:
        skill = _row_at(stream, SKILL_OFFSET)
        character = _row_at(stream, CHARACTER_OFFSET)
        board = stream.readline()
    decoded = [json.loads(row) for row in (skill, character, board)]
    assert "skills" in decoded[0]["knowledge"], decoded[0].keys()
    assert decoded[1]["type"] == "character" and decoded[1]["turn"] == 3957292
    assert decoded[2]["type"] == "player_turn" and decoded[2]["turn"] == 3957292
    ROWS_OUT.write_bytes(gzip.compress(
        b"".join(row.rstrip(b"\r\n") + b"\n" for row in (skill, character, board)),
        mtime=0))
    raw = DUMP.read_bytes()
    assert b"\r\n" in raw
    DUMP_OUT.write_bytes(gzip.compress(raw, mtime=0))
    for path in (ROWS_OUT, DUMP_OUT):
        data = path.read_bytes().replace(b"\r\n", b"\n")
        print(path.name, hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
