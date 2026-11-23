"""Extract the kill-before-leave fixtures of 2026-11-23 (n1-b life-416, Angband 95F).

tests/test_kill_before_leave_1123_recorded.py replays them.  Copied read-only from the viewing
server's snapshot files (~/hengbot-soak/n1-b/life-416/jsonlog/snapshots, the player-turn boards
only):

- snapshots-20261123-164646-9c6c76.jsonl.gz, player turns 4201590-4201633: 光なき闇の大蜘蛛
  『ウンゴリアント』 (DROP_GOOD, UNIQUE, a summoner; T2 alone, nothing else in view) erased by
  *Destruction* at 4201633 (decision 12817, ``emergency:destruction:before-teleport-away``).

The copies (``SOURCE``, ``<name>.jsonl.gz``, wider windows) are kept beside the worktree that made
the fix; only this tool reads them, the committed test reads the fixtures.

    python tests/extract_kill_before_leave_1123_fixtures.py [SOURCE]
"""
import gzip
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / ".scratch"
FIXTURES = Path(__file__).with_name("fixtures")
WINDOWS = (
    ("ungo2.jsonl.gz", "kill-before-leave-1123-ungoliant-n1b-416.jsonl.gz", 4201590, 4201633),
)


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    for name, target, low, high in WINDOWS:
        with gzip.open(source / name, "rt", encoding="utf-8") as stream:
            boards = [board for board in map(json.loads, stream)
                      if board.get("type") == "player_turn" and low <= board["turn"] <= high]
        boards.sort(key=lambda board: board["turn"])
        path = FIXTURES / target
        with gzip.GzipFile(path, "wb", mtime=0) as out:
            for board in boards:
                out.write((json.dumps(board, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        print(path, path.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
