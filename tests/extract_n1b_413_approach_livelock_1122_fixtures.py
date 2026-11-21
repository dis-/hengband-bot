"""Extract the n1-b life-413 sensed-T1 approach livelock fixtures (Angband 80F, 2026-11-22).

Source: ~/hengbot-soak/n1-b/life-413/jsonlog/snapshots/snapshots-20261122-040941-2507a3.jsonl.gz,
two windows copied read-only to C:/hengband-backups/pdca/deep80-defects-1122/:

- b-c1.jsonl.gz (player turns 2935000-2938300): 04:03:42 pingpong-escalate
  explore/sensed-t1:approach-destruction, livelock:recall-escape at 2938158.  Kept 2937400-2938160.
- b-c2.jsonl.gz (player turns 2998500-3002000): 04:07:09 the same pair, livelock:recall-escape at
  3001855.  Kept 3000600-3001860.

The Magic-Eater's power lists (tests/fixtures/n1b-413-me-lists-0417-1122.json) are the town-arrival
checkpoint's of 04:17:07 (turn 3054123), the closest the life kept.

    python tests/extract_n1b_413_approach_livelock_1122_fixtures.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/deep80-defects-1122")
FIXTURES = Path(__file__).with_name("fixtures")
WINDOWS = (
    ("b-c1.jsonl.gz", "n1b-413-approach-unreached-subject-1122.jsonl.gz", 2937400, 2938160),
    ("b-c2.jsonl.gz", "n1b-413-approach-lost-memory-1122.jsonl.gz", 3000600, 3001860),
)


def main() -> None:
    for source, target, low, high in WINDOWS:
        with gzip.open(ROOT / source, "rt", encoding="utf-8") as stream:
            boards = [board for board in map(json.loads, stream)
                      if board.get("type") == "player_turn" and low <= board["turn"] <= high]
        path = FIXTURES / target
        with gzip.GzipFile(path, "wb", mtime=0) as out:
            for board in boards:
                out.write((json.dumps(board, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        print(path, path.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
