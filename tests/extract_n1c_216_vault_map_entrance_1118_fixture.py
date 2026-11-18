"""Extract tests/fixtures/n1c-216-vault-map-entrance-1118.jsonl.gz.

Source: n1-c life-216 (Lv47 Magic-Eater), the snapshot log (one board per decision) of its Castle
(dungeon 12) 64F visit of 2026-11-17 (turns 3717271-3726964; the server's snapshot files
snapshots-20261117-005243-8f376f and snapshots-20261117-012227-6ac4c8, the "01:22" scene), copied
read-only from the viewing server to C:/hengband-backups/pdca/vault-map-entrance-1118.  The rows
are the 23 boards from turn 3719474 to turn 3719559: the item detection of the first board
shows an amulet of the Magi at (38,18) inside a vault whose outside the map did not know, and no
hostile was seen or sensed on the last board.

    python tests/extract_n1c_216_vault_map_entrance_1118_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/vault-map-entrance-1118/n1c-216-castle64-20261117-0122.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1c-216-vault-map-entrance-1118.jsonl.gz"
FIRST, LAST = 3719474, 3719559


def main() -> None:
    rows = []
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            board = json.loads(line)
            if board.get("type") == "player_turn" and FIRST <= board["turn"] <= LAST:
                rows.append({"role": "castle", "board": board})
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
