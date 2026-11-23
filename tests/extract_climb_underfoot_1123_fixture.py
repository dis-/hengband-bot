"""Extract tests/fixtures/climb-underfoot-1123.jsonl.xz (tests/test_climb_underfoot_1123_recorded.py).

Source: n1-a life-535 (Warrior Lv50, the Castle's climb to the band 38-42F) on 2026-11-23, the viewing
server's snapshot log ``jsonlog/snapshots/snapshots-20261123-165517-cc4639.jsonl.gz``, cut read-only
to C:/hengband-backups/pdca/captures/loot-pick-1123/:

  n1a-535-45F-7925931.jsonl  Castle 45F, 16:47:57-16:47:59: the climb's search for the up stairs
                             walked over the piles of a room (a Potion of Restore Intelligence at
                             (1,44) on 7925931) and stood on two items dropped at its feet in a
                             fight (4,49) on 7925886
  n1a-535-45F-7936513.jsonl  Castle 45F, 16:51:21: a Potion of Restore Intelligence dropped under
                             the player at (13,80) beside a フレイム・コボルド (7936505, melee) and
                             after it died (7936513)

The player-turn boards of the two windows are kept, xz-compressed.

    python tests/extract_climb_underfoot_1123_fixture.py
"""
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/loot-pick-1123")
FIXTURE = Path(__file__).with_name("fixtures") / "climb-underfoot-1123.jsonl.xz"
CUTS = (("n1a-535-45F-7925931.jsonl", 7925842, 7925931),
        ("n1a-535-45F-7936513.jsonl", 7936486, 7936513))


def main():
    rows = []
    for source, first, last in CUTS:
        for line in (ROOT / source).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("type") == "player_turn" and first <= row["turn"] <= last:
                rows.append(json.dumps(row, ensure_ascii=False))
    FIXTURE.write_bytes(lzma.compress(("\n".join(rows) + "\n").encode("utf-8"), preset=9))
    print(FIXTURE.name, len(rows), FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
