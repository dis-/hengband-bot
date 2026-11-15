"""Extract tests/fixtures/n1a-525-stops-1115/{home-take,kill-mob,yeek-recall}/.

Source: n1-a life-525's three stops of 2026-11-15 (Lv37 Warrior, build 3b52c43f0), the
incident captures copied read-only from the viewing server to
C:/hengband-backups/pdca/n1a-525-stops-1115/inc/:

- ``home-take``: 20261115-134036-unhandled-exception (ValueError "Home errand is not
  composable").  The town-arrival checkpoint of the 13:40:30 visit and its whole journal
  (19 rows; the crash board is the board after row 18, where the journal stops), the
  loadout report left out; and ``after-take.jsonl.xz``, the six response records after
  row 18's board in the capture's snapshot tail (snapshots/snapshots-current.jsonl.gz):
  the stay key's entrance board, the four Home pages of the take and the outside board
  the bot crashed on, all on game turn 8552723.
- ``kill-mob``: 20261115-133059-loop-detected (town blocked).  The town-arrival
  checkpoint of the 13:24:31 visit and its first 123 journal rows (row 91 the first
  detected:prepare-choke from the 殺人蜂, row 122 the first of the alternation).
- ``yeek-recall``: 20261115-124746-loop-detected (Yeek cave 1F).  The journal of the
  12:46:14 town visit ends at its descent (8 rows), so the dungeon decisions were replayed
  from the town-arrival checkpoint over the snapshot tail (each decision's board the
  record matching the decision log's turn and position, its inputs the records since the
  previous board) with .scratch/replay_dungeon.py; they match the record through decision
  82622.  ``policy.pkl.xz`` is that policy before decision 82623's inputs, and
  ``boards.jsonl.xz`` holds decisions 82623-82690 (the decision log's key and reason) with
  their inputs.

    PYTHONPATH="src;tests" python tests/extract_n1a_525_stops_1115_fixtures.py
"""
import json
import lzma
import sys
import zlib
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

CAPTURES = Path("C:/hengband-backups/pdca/n1a-525-stops-1115/inc")
CRASH = CAPTURES / "20261115-134036-unhandled-exception"
TOWN = CAPTURES / "20261115-133059-loop-detected"
DUNGEON_REPLAY = Path(__file__).resolve().parent.parent / ".scratch" / "dungeon-before-82623"
TARGET = Path(__file__).with_name("fixtures") / "n1a-525-stops-1115"


def snapshot_tail(path: Path) -> list[dict]:
    """The JSON records of a snapshot ring file whose head was cut (gzip members)."""
    data = path.read_bytes()
    position = data.find(b"\x1f\x8b\x08")
    chunks = []
    while position != -1 and position < len(data):
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            chunks.append(stream.decompress(data[position:]))
        except zlib.error:
            position = data.find(b"\x1f\x8b\x08", position + 1)
            continue
        position = len(data) - len(stream.unused_data) if stream.eof else -1
    records = []
    for line in b"".join(chunks).decode("utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl_xz(path: Path, rows) -> None:
    path.write_bytes(lzma.compress("".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"),
        preset=PRESET))


def board_of(record: dict, row: dict) -> bool:
    player = record.get("player") or {}
    return (record.get("type") == "player_turn" and record.get("turn") == row["turn"]
            and (player.get("y"), player.get("x"))
            == (row["position"]["y"], row["position"]["x"]))


def dungeon_boards() -> list[dict]:
    """Each logged decision with its inputs (replay_dungeon.py's matching)."""
    ring = [json.loads(line) for line in
            (DUNGEON_REPLAY / "ring.jsonl").read_text(encoding="utf-8").splitlines() if line]
    rows = [json.loads(line) for line in
            (DUNGEON_REPLAY / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    boards, index = [], -1
    for number, row in enumerate(rows):
        board = index + 1
        while not board_of(ring[board], row):
            board += 1
        following = rows[number + 1] if number + 1 < len(rows) else None
        while (board + 1 < len(ring) and board_of(ring[board + 1], row)
               and not (following is not None and board_of(ring[board + 1], following))):
            board += 1
        boards.append({"decision": row, "inputs": ring[index + 1:board + 1]})
        index = board
    return boards


if __name__ == "__main__":
    home_take = TARGET / "home-take"
    extract(CRASH / "town-arrival", home_take, 19, frozenset({"_loadout_report_path"}))
    write_jsonl_xz(home_take / "after-take.jsonl.xz",
                   snapshot_tail(CRASH / "snapshots" / "snapshots-current.jsonl.gz")[-6:])
    extract(TOWN / "town-arrival", TARGET / "kill-mob", 123,
            frozenset({"_loadout_report_path"}))
    yeek = TARGET / "yeek-recall"
    yeek.mkdir(parents=True, exist_ok=True)
    (yeek / "policy.pkl.xz").write_bytes(
        lzma.compress((DUNGEON_REPLAY / "policy.pkl").read_bytes(), preset=PRESET))
    write_jsonl_xz(yeek / "boards.jsonl.xz", dungeon_boards())
    for path in sorted(TARGET.rglob("*")):
        if path.is_file():
            print(path.relative_to(TARGET), path.stat().st_size, file=sys.stderr)
