"""Build tests/fixtures/finale-resurvey-n1c-221-1124.jsonl.gz (n1-c life-221's Angband 100F floor
from the 11:02:30 restart to the halt, 2026-11-24 11:04:40, stationary:exhausted:angband-finale:hold).

Source: the player_turn lines of the halt capture's snapshot ring
(incident-captures/20261124-110440-stationary-exhausted-angband-finale-hold/snapshots/
snapshots-current.jsonl.gz) from turn 6266122 (the restart's first board) on.  The ring was copied
while it was written: its first member may be cut, so the decoder skips to the next gzip header.
Each row keeps only the fields that differ from the previous row and names the rest in ``_same``
(tests/support/finale_416.boards).

Usage: python tests/extract_finale_resurvey_1124_fixture.py <snapshots-current.jsonl.gz>
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OUT = "finale-resurvey-n1c-221-1124.jsonl.gz"
FIRST = 6266122


def main(ring: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.extract_finale_serpent_death_1124_fixture import ring_lines
    rows = []
    for line in ring_lines(Path(ring)):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") == "player_turn" and row["turn"] >= FIRST:
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
    main(sys.argv[1])
