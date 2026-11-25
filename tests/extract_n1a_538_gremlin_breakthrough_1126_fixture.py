"""Freeze n1-a life-538's latched グレムリン floor: the breakthrough's first and last boards.

Source: n1-a life-538 (Zombie warrior Lv30, bot-b6ea88538) on hengband.net, owner-halted
2026-11-26 07:18:37 (loop-detected) on dungeon 12 29F.  The incident capture
~/hengbot-soak/n1-a/life-538/incident-captures/20261126-071832-loop-detected and
jsonlog/breeder-floor.json were copied to
C:/hengband-backups/pdca/captures/n1a-538-gremlin-breakthrough-1126 (``cap/`` and
``breeder-floor.json``).  ``cap/snapshots/snapshots-current.jsonl.gz`` is the tail of an appended
gzip stream (flight_recorder.freeze copies its last bytes), so it is read from its first whole
gzip member.  Boards are matched to the rows of ``cap/decision-tail.jsonl`` by turn.

Kept: the board of the breakthrough's first decision (turn 1339312, seek-upstairs) and of the
last (1339651, clear-escape-path, the loop detector's stop), their recorded rows, the floor's
emergency teleport row (1334738), the breeder record and the capture's policy-state flags the
test restores.

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
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-538-gremlin-breakthrough-1126.json.gz"
BOARD_TURNS = (1339312, 1339651)
EMERGENCY_TURN = 1334738
FLAGS = ("_emergency_return_active", "_returning_to_town", "_fundraising_mode")
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
            if row.get("turn") in (*BOARD_TURNS, EMERGENCY_TURN) and row.get("reason") != "loop-detected":
                rows.setdefault(row["turn"], {field: row.get(field) for field in ROW_FIELDS})
    state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
    flags = {name: state["modes_and_latches"].get(name) for name in FLAGS}
    flags["_breeder_breakthrough_floor"] = state["state"]["_breeder_breakthrough_floor"]
    case = {
        "source_capture": "n1-a/life-538/incident-captures/20261126-071832-loop-detected",
        "boards": [boards[turn] for turn in BOARD_TURNS],
        "board_sha256": [hashlib.sha256(boards[turn].encode("utf-8")).hexdigest() for turn in BOARD_TURNS],
        "recorded": [rows[turn] for turn in BOARD_TURNS],
        "emergency_row": rows[EMERGENCY_TURN],
        "breeder_floor": json.loads((ROOT / "breeder-floor.json").read_text(encoding="utf-8")),
        "policy_state_flags": flags,
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(OUTPUT, [row["reason"] for row in case["recorded"]])


if __name__ == "__main__":
    main()
