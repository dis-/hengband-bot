"""Extract the fixture of n1-c life-224's wait for the Rod of Detection on Angband 95F (2026-11-28
16:45:45, stationary:exhausted:deep-detection-rod:wait-recharge, zombie Magic-Eater CL44).

* tests/fixtures/n1c-224-detect-rod-wait-1128.jsonl.gz: the player_turn boards (the last board of
  a turn) of the process restarted at 16:44:35 (the first board whose turn drops below the one
  before it, 7556967) up to the stop (7560220), 770 boards; a row lists in ``_same`` the fields
  equal to the previous row's and leaves them out (tests/support/finale_416.boards expands them).
  Source: the instance's live generation ``n1-c/life-224/jsonlog/snapshots/snapshots-current.jsonl.gz``
  (the incident capture holds only its last 16 MiB, cut mid-stream).

    PYTHONPATH="src;tests;." python tests/extract_n1c_224_detect_rod_wait_1128_fixture.py <snapshots-current.jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "n1c-224-detect-rod-wait-1128.jsonl.gz"
STOP = 7560220


def boards(source: Path) -> None:
    rows = []
    with gzip.open(source, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        try:
            for line in stream:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        except (EOFError, OSError):
            pass  # the live generation's unfinished tail
    restart = next(n for n in range(1, len(rows))
                   if rows[n].get("turn", 0) < rows[n - 1].get("turn", 0))
    kept = {}
    for raw in rows[restart:]:
        if raw.get("type") == "player_turn" and raw["turn"] <= STOP:
            kept[raw["turn"]] = raw  # the last board of a turn is the decision's
    previous = None
    with gzip.GzipFile(FIXTURE, "wb", mtime=0) as out:
        for turn in sorted(kept):
            raw = kept[turn]
            row = dict(raw)
            if previous is not None:
                same = sorted(key for key in raw if key in previous and previous[key] == raw[key]
                              and key not in ("turn", "type"))
                for key in same:
                    del row[key]
                if same:
                    row["_same"] = same
            previous = raw
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                      .encode("utf-8", "surrogateescape"))
    print(FIXTURE, FIXTURE.stat().st_size, len(kept))


if __name__ == "__main__":
    boards(Path(sys.argv[1]))
