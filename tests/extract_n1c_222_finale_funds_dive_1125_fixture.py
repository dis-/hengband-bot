"""Extract tests/fixtures/n1c-222-finale-funds-dive-1125.json.gz (tests/test_n1c_222_finale_funds_dive_1125_recorded.py).

Source: n1-c life-222 (Magic-Eater Lv49, Angband recall depth 95), the live decision log's
snapshots ``jsonlog/snapshots/snapshots-20261125-202243-b360e4.jsonl.gz`` (turns 8306109-8378549).
The board kept is the last ``player_turn`` board of turn 8354703 (2026-11-25 20:10:50, decision
5183, Home's rings just sold, 42,504 gold): the board the Black Markets' circuit handed a mining run
over on (``town:entrance-step-off:town:finale-hold:bm-funds-fundraise:49993``).

    python tests/extract_n1c_222_finale_funds_dive_1125_fixture.py <snapshots-....jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-finale-funds-dive-1125.json.gz"
TURN = 8354703


def main(source: Path) -> None:
    kept = None
    with gzip.open(source, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if raw.get("type") == "player_turn" and raw.get("turn") == TURN:
                kept = raw  # the last board of a turn is the decision's
    assert kept is not None, TURN
    with gzip.GzipFile(FIXTURE, "wb", mtime=0) as out:
        out.write(json.dumps(kept, ensure_ascii=False, sort_keys=True)
                  .encode("utf-8", "surrogateescape"))
    print(FIXTURE, FIXTURE.stat().st_size)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
