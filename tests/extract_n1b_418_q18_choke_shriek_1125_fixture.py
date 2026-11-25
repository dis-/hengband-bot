"""Extract the fixture of n1-b life-418's Q18 floor from its entry (2026-11-25, Magic-Eater Lv38).

* tests/fixtures/n1b-418-q18-floor-1125.jsonl.gz: the boards (``type`` ``player_turn``, the last
  board of a turn) of turns 3416674-3419883 on floor (0,35,18): the entry onto (1,2), the siren's
  shriek on (2,6) (3417300), and the walks back from the choke (1,19) to (1,15), (1,12) and (1,5)
  over (2,18) (1,17) (1,16) and (2,6), shrieked at on them (3419105, 3419447, 3419507, 3419865).
  Source: the incident capture ``incident-captures/20261125-062225-livelock-exhausted/snapshots``
  (``snapshots-20261125-061545-3c18bf.jsonl.gz`` and ``snapshots-current.jsonl.gz``).  The
  absorbed power lists are the 1125 ping-pong fixture's (tests/fixtures/n1b-418-me-lists-1125.json).

    PYTHONPATH="src;tests;." python tests/extract_n1b_418_q18_choke_shriek_1125_fixture.py <capture-dir>
"""
import gzip
import json
import sys
from pathlib import Path

BOARDS = Path(__file__).parent / "fixtures" / "n1b-418-q18-floor-1125.jsonl.gz"
WINDOW = (3416674, 3419883)
SOURCES = ("snapshots-20261125-061545-3c18bf.jsonl.gz", "snapshots-current.jsonl.gz")


def boards(capture: Path) -> None:
    kept = {}
    for name in SOURCES:
        with gzip.open(capture / "snapshots" / name, "rt", encoding="utf-8", errors="surrogateescape") as stream:
            for line in stream:
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                if (raw.get("type") == "player_turn" and (raw.get("floor") or {}).get("quest_id") == 18
                        and WINDOW[0] <= raw.get("turn", 0) <= WINDOW[1]):
                    kept[raw["turn"]] = raw  # the last board of a turn is the decision's
    with gzip.GzipFile(BOARDS, "wb", mtime=0) as out:
        for turn in sorted(kept):
            out.write((json.dumps(kept[turn], ensure_ascii=False, sort_keys=True) + "\n")
                      .encode("utf-8", "surrogateescape"))
    print(BOARDS, BOARDS.stat().st_size, len(kept))


if __name__ == "__main__":
    boards(Path(sys.argv[1]))
