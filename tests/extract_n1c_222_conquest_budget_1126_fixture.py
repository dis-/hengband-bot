"""Extract tests/fixtures/n1c-222-conquest-budget-1126.json.gz (tests/test_n1c_222_conquest_budget_1126_recorded.py).

Source: n1-c life-222 (Zombie Magic-Eater Lv45, Angband recall depth 80, the Mountain's 50F its
last floor), the loop-detected capture of 2026-11-25 13:21 (incident-captures/
20261125-132149-loop-detected/snapshots/snapshots-20261125-131826-7d3031.jsonl.gz).  The board
kept is the last ``player_turn`` board of turn 6754081: the town board after one of the 119
Recalls to the Mountain 50F hunting its guardian 大鷲王『ソロンドール』 (race 468).

    python tests/extract_n1c_222_conquest_budget_1126_fixture.py <snapshots-....jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-conquest-budget-1126.json.gz"
TURN = 6754081


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
