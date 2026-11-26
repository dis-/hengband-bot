"""Build tests/fixtures/finale-bank-food-n1c-222-1126.jsonl.gz (n1-c life-222's Angband 100F
floor, the battle with the Serpent of Chaos, 2026-11-26 10:00-10:04).

Source: the player_turn lines of the floor's snapshot rings (jsonlog/snapshots
snapshots-20261126-100358-0820ce.jsonl.gz and snapshots-current.jsonl.gz): every 100F board from
the arrival (turn 12320309) to turn 12320600 (the first meal at 12320551 and the first food wand
drained by 竜殺しの始祖『ミラーク』's UN_POWER blow at 12320596), and the window ``WINDOW`` (the last
food wand drained at 12324520; hungry with nothing to eat and the recall at 12325001).  Each row
keeps only the fields that differ from the previous row and names the rest in ``_same``
(tests/support/finale_416 ``boards``).

Usage: python tests/extract_finale_bank_food_1126_fixture.py <ring> [<ring> ...]
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OUT = "finale-bank-food-n1c-222-1126.jsonl.gz"
ARRIVAL_UNTIL = 12320600
WINDOW = (12324500, 12325010)


def wanted(turn: int, first: int) -> bool:
    return first <= turn <= ARRIVAL_UNTIL or WINDOW[0] <= turn <= WINDOW[1]


def ring_lines(path: str):
    """The ring's lines, streamed (a ring being written may end in a cut member, whose lines
    before the cut are kept)."""
    with gzip.open(path, "rb") as stream:
        try:
            for line in stream:
                yield line
        except (EOFError, OSError):
            return


def main(*rings: str) -> None:
    rows, first, seen = [], None, set()
    for ring in rings:
        for line in ring_lines(ring):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") != "player_turn" or (row.get("floor") or {}).get("level") != 100:
                continue
            if row["turn"] < 12320309 or row["turn"] > WINDOW[1]:
                continue
            if first is None:
                first = row["turn"]
            identity = hash(line)  # a ring repeats no board, two rings may overlap
            if wanted(row["turn"], first) and identity not in seen:
                seen.add(identity)
                rows.append(row)
    previous = None
    with gzip.open(FIXTURES / OUT, "wt", encoding="utf-8") as stream:
        for row in rows:
            written = row
            if previous is not None:
                same = [key for key in row if key in previous and previous[key] == row[key]
                        and key not in ("type", "turn")]
                written = {key: value for key, value in row.items() if key not in same}
                if same:
                    written["_same"] = same
            stream.write(json.dumps(written, ensure_ascii=False, separators=(",", ":")) + "\n")
            previous = row
    print(len(rows), rows[0]["turn"], rows[-1]["turn"])


if __name__ == "__main__":
    main(*sys.argv[1:])
