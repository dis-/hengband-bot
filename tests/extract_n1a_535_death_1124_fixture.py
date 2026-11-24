"""Extract tests/fixtures/n1a-535-death-1124/.

Source: n1-a life-535's player-death capture of 2026-11-24 14:41:42 (Warrior Lv50, Mountain 45F,
build 98cbab5ed), copied read-only from the viewing server's
incident-captures/20261124-144142-player-death/ (its town-arrival checkpoint and
snapshots/snapshots-current.jsonl.gz, the last 16 MiB of the generation) to
C:/hengband-backups/pdca/n1a-535-death-1124/20261124-144142-player-death/.

The fixture keeps the town-arrival checkpoint of 14:35:47 (turn 10670071, ``policy.pkl``), the
visit's 190 journal rows (the town visit up to the Recall to the Mountain's 48F, waited for) and the
sidecar files (tests/support/town_arrival_fixture.extract), and ``boards.jsonl.xz``: the
player-turn lines of the capture's snapshots for these turns: the first 48F board the copy holds
(10672945), the 45F arrival (10673707) and every 45F board from the Teleportation read that left
three scrolls (10679224) to the death (10679565).

    python tests/extract_n1a_535_death_1124_fixture.py
"""
import json
import lzma
import zlib
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/n1a-535-death-1124/20261124-144142-player-death")
VISIT = SOURCE / "town-arrival"
SNAPSHOTS = SOURCE / "snapshots" / "snapshots-current.jsonl.gz"
TARGET = Path(__file__).with_name("fixtures") / "n1a-535-death-1124"
ROWS = 190
FIRST_48, ARRIVAL_45, THREE_LEFT, DEATH = 10672945, 10673707, 10679224, 10679565


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
                or not (turn in (FIRST_48, ARRIVAL_45) or THREE_LEFT <= turn <= DEATH)):
            continue
        seen.add(turn)
        kept.append(line.decode("utf-8"))
    (TARGET / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(kept) + "\n").encode("utf-8"), preset=PRESET))
    print(len(kept), sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
