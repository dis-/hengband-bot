"""Extract the destruction_loot / explore livelock fixtures of 2026-11-23 (Angband 80F and 95F).

tests/test_destruction_loot_livelock_1123_recorded.py replays them.  The measurement
C:/hengband-backups/pdca/deep-efficiency-effect-1123/REPORT.md counted 11 of the 12
``livelock:recall-escape`` visit ends on Angband 80F/82-95F as destruction-loot:place/fetch
against explore; these are two of them, copied read-only from the viewing server's snapshot
files (~/hengbot-soak/<bot>/<life>/jsonlog/snapshots, the player-turn boards only):

- n1-c life-221 (Magic-Eater Lv45, Angband 80F), snapshots-20261123-115655-9d5df7.jsonl.gz, player
  turns 4404900-4405300 (the visit of 11:39:38; livelock:recall-escape at 4405279, 11:42:21).
- n1-b life-416 (Magic-Eater Lv49, Angband 95F), snapshots-20261123-150850-02ba52.jsonl.gz, player
  turns 4074501-4074880 (the visit of 15:10:36; livelock:recall-escape at 4074861, 15:13:32).

The copies (``SOURCE``, ``<name>-boards.jsonl.gz``) are kept beside the worktree that made the
fix; only this tool reads them, the committed test reads the fixtures.

    python tests/extract_destruction_loot_livelock_1123_fixtures.py [SOURCE]
"""
import gzip
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / ".incident"
FIXTURES = Path(__file__).with_name("fixtures")
WINDOWS = (
    ("c221-boards.jsonl.gz", "destruction-loot-livelock-n1c-221-1123.jsonl.gz", 4404900, 4405279),
    ("b416-boards.jsonl.gz", "destruction-loot-livelock-n1b-416-1123.jsonl.gz", 4074501, 4074861),
)


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    for name, target, low, high in WINDOWS:
        with gzip.open(source / name, "rt", encoding="utf-8") as stream:
            boards = [board for board in map(json.loads, stream)
                      if board.get("type") == "player_turn" and low <= board["turn"] <= high]
        path = FIXTURES / target
        with gzip.GzipFile(path, "wb", mtime=0) as out:
            for board in boards:
                out.write((json.dumps(board, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        print(path, path.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
