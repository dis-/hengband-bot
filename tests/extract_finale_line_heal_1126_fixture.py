"""Build tests/fixtures/finale-line-heal-n1c-222-1126.jsonl.gz (n1-c life-222's Angband 100F
floor, the battle with the Serpent of Chaos, 2026-11-26 03:09-03:13).

Source: the player_turn lines of the floor's snapshot rings (jsonlog/snapshots
snapshots-20261126-030958-69e75a.jsonl.gz and snapshots-20261126-032405-37b774.jsonl.gz): every
100F board from the arrival to turn 10184060 (the first two teleports and the recoveries after
them), then the windows ``WINDOWS`` (the walks to a stand beyond the Serpent that ended in the
teleport within distance 2).  Each row keeps only the fields that differ from the previous row and
names the rest in ``_same`` (tests/support/finale_416 ``boards``).

Usage: python tests/extract_finale_line_heal_1126_fixture.py <ring 03:09:58> <ring 03:24:05>
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OUT = "finale-line-heal-n1c-222-1126.jsonl.gz"
ARRIVAL_UNTIL = 10184060
WINDOWS = ((10185930, 10185966), (10186330, 10186368))


def wanted(turn: int, first: int) -> bool:
    if first <= turn <= ARRIVAL_UNTIL:
        return True
    return any(low <= turn <= high for low, high in WINDOWS)


def ring_lines(path: str):
    """The ring's lines, streamed (gzip reads its members one after another; the ring being
    written may end in a cut member, whose lines before the cut are kept)."""
    with gzip.open(path, "rb") as stream:
        try:
            for line in stream:
                yield line
        except (EOFError, OSError):
            return


def main(*rings: str) -> None:
    rows, first = [], None
    for ring in rings:
        for line in ring_lines(ring):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") != "player_turn" or (row.get("floor") or {}).get("level") != 100:
                continue
            if first is None:
                first = row["turn"]
            if wanted(row["turn"], first):
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
