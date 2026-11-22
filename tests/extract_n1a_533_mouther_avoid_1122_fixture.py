"""Extract tests/fixtures/n1a-533-mouther-avoid-1122/ (n1-a life-533, Orc Cave 19F, 百目口).

Source: n1-a life-533 (Warrior Lv22, build 53f7a340e), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1a-532-533/:

 - the town-arrival checkpoint is tests/fixtures/n1a-533-cure-mushroom-1122 (the same capture's,
   tests/extract_n1a_533_cure_mushroom_1122_fixture.py), not copied again;
 - ``life-533/incident-captures/20261122-151509-player-death/snapshots/snapshots-current.jsonl.gz``
   -- the player-turn boards of Orc Cave 19F from the arrival (turn 437411) to the first board the
   百目口 is seen on (442397, decision 16767), the last board of each turn a decision was taken on;
 - ``533-decisions-tail.jsonl`` -- the decision rows 16322 (the arrival) to 16767 of those turns
   (the live bot's decision log), kept with the boards as ``floor.json.xz``.

    python tests/extract_n1a_533_mouther_avoid_1122_fixture.py
"""
import json
import lzma
import zlib
from pathlib import Path

from support.town_arrival_fixture import PRESET

ROOT = Path("C:/hengband-backups/pdca/n1a-532-533")
SNAPSHOTS = (ROOT / "life-533" / "incident-captures" / "20261122-151509-player-death" / "snapshots"
             / "snapshots-current.jsonl.gz")
DECISIONS = ROOT / "533-decisions-tail.jsonl"
TARGET = Path(__file__).with_name("fixtures") / "n1a-533-mouther-avoid-1122"
FIRST_SEQUENCE, LAST_SEQUENCE = 16322, 16767


def _members(data: bytes):
    """The lines of a multi-member gzip file whose copy may start inside a member."""
    start = data.find(b"\x1f\x8b")
    out = b""
    while 0 <= start < len(data):
        stream = zlib.decompressobj(31)
        try:
            out += stream.decompress(data[start:])
        except zlib.error:
            start = data.find(b"\x1f\x8b", start + 1)
            continue
        if not stream.unused_data:
            break
        start = len(data) - len(stream.unused_data)
    return out.split(b"\n")


def main() -> None:
    decisions = [{"decision_sequence": row["decision_sequence"], "turn": row["turn"],
                  "key": row["key"], "reason": row["reason"]}
                 for row in map(json.loads, DECISIONS.read_text(encoding="utf-8").splitlines())
                 if FIRST_SEQUENCE <= row["decision_sequence"] <= LAST_SEQUENCE]
    turns = {row["turn"] for row in decisions}
    last = {}
    for line in _members(SNAPSHOTS.read_bytes()):
        if not line.strip():
            continue
        try:
            row = json.loads(line.decode("utf-8", "surrogateescape"))
        except ValueError:
            continue
        if row.get("type") == "player_turn" and row["turn"] in turns:
            last[row["turn"]] = row
    boards = [last[row["turn"]] for row in decisions]
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "floor.json.xz").write_bytes(lzma.compress(json.dumps(
        {"boards": boards, "decisions": decisions}, ensure_ascii=False).encode(
            "utf-8", "surrogateescape"), preset=PRESET))
    print(len(boards), sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
