"""Extract tests/fixtures/n1a-531-climb-fix-1122/.

Source: n1-a life-531's player-death capture of 2026-11-22 13:40:13 (Warrior Lv50, Mountain 49F,
build 57ba99c2c), copied read-only from the viewing server's
incident-captures/20261122-134013-player-death/ to
C:/hengband-backups/pdca/n1a-531-death/20261122-134013-player-death/.

The fixture keeps the town-arrival checkpoint of 13:38:55 (turn 31975071: the town board after the
Recall read on Mountain 47F, ``policy.pkl``), the visit's 112 journal rows (the Home, the shops, the
Tower's recharge trip and the Recall back to the Mountain) and the sidecar files
(tests/support/town_arrival_fixture.extract), and ``boards.jsonl.xz``: the player-turn lines of
the capture's snapshots-current.jsonl.gz for these turns: the Mountain 50F landing
(31976311), the last 50F board before the up stairs (31977956) and every 49F board from the
arrival (31977957) to the death (31978806).

    python tests/extract_n1a_531_climb_fix_1122_fixture.py
"""
import json
import lzma
import zlib
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/n1a-531-death/20261122-134013-player-death")
VISIT = SOURCE / "town-arrival"
SNAPSHOTS = SOURCE / "snapshots" / "snapshots-current.jsonl.gz"
TARGET = Path(__file__).with_name("fixtures") / "n1a-531-climb-fix-1122"
ROWS = 112
LANDING, ASCEND, ARRIVAL_49, DEATH = 31976311, 31977956, 31977957, 31978806


def _members(data: bytes):
    """The lines of a multi-member gzip file whose copy may start inside a member."""
    start = data.find(b"\x1f\x8b")
    pending = b""
    while 0 <= start < len(data):
        stream = zlib.decompressobj(31)
        try:
            chunk = stream.decompress(data[start:])
        except zlib.error:
            start = data.find(b"\x1f\x8b", start + 1)
            continue
        lines = (pending + chunk).split(b"\n")
        pending = lines.pop()
        yield from lines
        if not stream.unused_data:
            break
        start = len(data) - len(stream.unused_data)


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    kept, seen = [], set()
    for line in _members(SNAPSHOTS.read_bytes()):
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        turn = raw.get("turn")
        if (raw.get("type") != "player_turn" or turn in seen
                or not (turn in (LANDING, ASCEND) or ARRIVAL_49 <= turn <= DEATH)):
            continue
        seen.add(turn)
        kept.append(line.decode("utf-8"))
    (TARGET / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(kept) + "\n").encode("utf-8"), preset=PRESET))
    print(len(kept), sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
