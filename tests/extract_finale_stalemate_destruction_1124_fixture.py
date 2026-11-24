"""Build tests/fixtures/finale-stalemate-destruction-n1c-221-1124.jsonl.gz (n1-c life-221's Angband 100F
floor from the 13:39:23 restart to the halt, 2026-11-24 13:39:36,
stationary:exhausted:angband-finale:hold, the wait on the outflank's wait cell (59,45)).

Source: the player_turn lines of the halt capture's snapshot ring
(incident-captures/20261124-133936-stationary-exhausted-angband-finale-hold/snapshots/
snapshots-current.jsonl.gz) from the restart's first board on: turn 6268877 is the board of the
13:02:26 halt and again the restart's first board; the ring's first row of that turn (the 13:02
run's) is left out.  Each row keeps only the fields that differ from the previous row and names the
rest in ``_same`` (tests/support/finale_416.boards).

Usage: python tests/extract_finale_stalemate_destruction_1124_fixture.py <snapshots-current.jsonl.gz>
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OUT = "finale-stalemate-destruction-n1c-221-1124.jsonl.gz"
FIRST = 6268877


def main(ring: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.extract_finale_serpent_death_1124_fixture import ring_lines
    rows, skipped = [], False
    for line in ring_lines(Path(ring)):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") != "player_turn" or row["turn"] < FIRST:
            continue
        if row["turn"] == FIRST and not skipped:
            skipped = True  # the 13:02:26 halt's board, before the restart
            continue
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
