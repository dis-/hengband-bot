"""Extract the fixture of n1-a life-537's death on Angband 50F (2026-11-26 02:04, Warrior Lv48).

* tests/fixtures/n1a-537-angband50-1126.jsonl.gz: the boards (``type`` ``player_turn``, the last
  board of a turn) of floor (1,50,0), from the floor's arrival (turn 4410921, (37,71)) to the last
  board (4414701, (38,14), recorded '3' onto the unvisited (39,15), after which the character died
  to the dragon pack).  Source: the incident capture
  ``n1-a/life-537/incident-captures/20261126-020442-player-death/snapshots/snapshots-current.jsonl.gz``.

    PYTHONPATH="src;tests;." python tests/extract_n1a_537_deep_detection_1126_fixture.py <capture-dir>
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "n1a-537-angband50-1126.jsonl.gz"
FLOOR = (1, 50)


def boards(capture: Path) -> None:
    kept = {}
    source = capture / "snapshots" / "snapshots-current.jsonl.gz"
    with gzip.open(source, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        try:
            for line in stream:
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                floor = raw.get("floor") or {}
                if (raw.get("type") == "player_turn"
                        and (floor.get("dungeon_id"), floor.get("level")) == FLOOR):
                    kept[raw["turn"]] = raw  # the last board of a turn is the decision's
        except (EOFError, OSError):
            pass  # the live generation's unfinished tail
    with gzip.GzipFile(FIXTURE, "wb", mtime=0) as out:
        for turn in sorted(kept):
            out.write((json.dumps(kept[turn], ensure_ascii=False, sort_keys=True) + "\n")
                      .encode("utf-8", "surrogateescape"))
    print(FIXTURE, FIXTURE.stat().st_size, len(kept))


if __name__ == "__main__":
    boards(Path(sys.argv[1]))
