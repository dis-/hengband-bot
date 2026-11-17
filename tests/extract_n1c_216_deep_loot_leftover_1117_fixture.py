"""Extract tests/fixtures/n1c-216-deep-loot-leftover-1117.jsonl.gz.

Source: n1-c life-216 (Lv47 Magic-Eater), the snapshot log (one board per decision) of two 50F+
visits copied read-only from the viewing server to C:/hengband-backups/pdca/deep-loot-leftover-1117:
- ``castle``: Castle (dungeon 12) 64F, 2026-11-16 23:00-23:05, the boards from turn 3506476 (five
  boards before the item detection) to turn 3506682 (31 boards);
- ``angband``: Angband 80F, 2026-11-17 13:57, the last three boards of the visit (turns 5367782,
  5367793, 5367798: the up stair under the player on the last; the next board was 79F).
Also ``me-lists``: the absorbed power lists of the 2026-11-17 15:50 town-arrival checkpoint (the
nearest recorded ones; the visits' own were not recorded) with every count at its maximum and the
list turns at 1 (DECLARED CONSTRUCTED; me-device-lists-155033.json).

    python tests/extract_n1c_216_deep_loot_leftover_1117_fixture.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/deep-loot-leftover-1117")
TARGET = Path(__file__).with_name("fixtures") / "n1c-216-deep-loot-leftover-1117.jsonl.gz"
WINDOWS = {
    "castle": (ROOT / "n1c-216-castle64-20261116-2305.jsonl.gz", 3506476, 3506682),
    "angband": (ROOT / "n1c-216-angband80-20261117-1357.jsonl.gz", 5367782, 5367798),
}


def _boards(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                board = json.loads(line)
                if board.get("type") == "player_turn":
                    yield board


def main() -> None:
    rows = [{"role": "me-lists",
             "lists": json.loads((ROOT / "me-device-lists-155033.json").read_text(encoding="utf-8"))}]
    for role, (path, first, last) in WINDOWS.items():
        rows.extend({"role": role, "board": board} for board in _boards(path)
                    if first <= board["turn"] <= last)
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
