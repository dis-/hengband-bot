"""Freeze n1-a life-539's shrieker board: the warrior aimed a 1% wand at a 1-HP target.

Source: n1-a life-539 (Zombie warrior Lv25, bot-c992d3a6b) on hengband.net, stopped
2026-11-26 12:24:19 (loop-detected) on Angband 17F.  The incident capture
~/hengbot-soak/n1-a/life-539/incident-captures/20261126-122419-loop-detected was copied to
C:/hengband-backups/pdca/captures/n1a-539-wand-fail-loop-1126 (``cap/``).
``cap/snapshots/snapshots-current.jsonl.gz`` is the tail of an appended gzip stream
(flight_recorder.freeze copies its last bytes), so it is read from its first whole gzip member.
Boards are matched to the rows of ``cap/decision-tail.jsonl`` by turn.

Kept: the board of the first ``supply-fight:aim-wand`` decision (turn 683577) and of the last one
before the stop (683911), with their recorded rows.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import zlib
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-539-wand-fail-loop-1126.json.gz"
BOARD_TURNS = (683577, 683911)
ROW_FIELDS = ("decision_sequence", "turn", "key", "reason", "rung", "position", "floor")


def _members(data: bytes) -> str:
    """The whole gzip members of a stream that begins mid-member."""
    out = []
    pos = data.find(b"\x1f\x8b\x08")
    while 0 <= pos < len(data):
        stream = zlib.decompressobj(31)
        try:
            out.append(stream.decompress(data[pos:]))
        except zlib.error:
            pos = data.find(b"\x1f\x8b\x08", pos + 1)
            continue
        if not stream.eof:
            break   # the live member was cut
        pos = len(data) - len(stream.unused_data)
    return b"".join(out).decode("utf-8", "replace")


def main():
    capture = ROOT / "cap"
    boards = {}
    for line in _members((capture / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()).splitlines():
        try:
            board = json.loads(line)
        except json.JSONDecodeError:
            continue
        if board.get("type") == "player_turn" and board.get("turn") in BOARD_TURNS:
            boards[board["turn"]] = line
    rows = {}
    with (capture / "decision-tail.jsonl").open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("turn") in BOARD_TURNS and row.get("reason") != "loop-detected":
                rows.setdefault(row["turn"], {field: row.get(field) for field in ROW_FIELDS})
    case = {
        "source_capture": "n1-a/life-539/incident-captures/20261126-122419-loop-detected",
        "boards": [boards[turn] for turn in BOARD_TURNS],
        "board_sha256": [hashlib.sha256(boards[turn].encode("utf-8")).hexdigest() for turn in BOARD_TURNS],
        "recorded": [rows[turn] for turn in BOARD_TURNS],
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
