"""Extract the destruction_loot frontier fetch fixtures of 2026-11-23 (Angband 80F and 95F).

tests/test_destruction_loot_frontier_1123_recorded.py replays them.  The loot yield study
C:/hengband-backups/pdca/loot-yield-1123 traced the non-urgent *Destruction* uses that deleted
valuables while no hostile was in view; every one replayed had refused the fetch for want of a
known way to the piles.  Two of them, copied read-only from the viewing server's snapshot files
(~/hengbot-soak/<bot>/<life>/jsonlog/snapshots, the player-turn boards only):

- n1-c life-221 (Magic-Eater, Angband 80F), snapshots-20261123-113830-c6edb2.jsonl.gz, player
  turns 4392651-4392698 (the use at 4392698 deleted 器用さの薬, *鑑定*の巻物 and two rods).
- n1-b life-416 (Magic-Eater, Angband 95F), snapshots-20261123-145249-482bc2.jsonl.gz, player
  turns 4038420-4038441 (the use at 4038441 deleted two スピードの指輪 {未鑑定} and a potion).
- n1-b life-416 (Magic-Eater, resist curse, Angband 95F), snapshots-20261123-150850-02ba52.jsonl.gz,
  player turns 4054730-4054751 (the use at 4054751 erased アンバーの狂気の夢想家『ブランド』;
  tests/test_amberite_readings_1123_recorded.py).

The copies (``SOURCE``, ``<name>-boards.jsonl.gz``, wider windows) are kept beside the worktree that
made the fix; only this tool reads them, the committed test reads the fixtures.

    python tests/extract_loot_yield_1123_fixtures.py [SOURCE]
"""
import gzip
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / ".scratch"
FIXTURES = Path(__file__).with_name("fixtures")
WINDOWS = (
    ("c221-4392698-boards.jsonl.gz", "loot-yield-1123-fetch-frontier-n1c-221.jsonl.gz", 4392651, 4392698),
    ("b416-4038441-boards.jsonl.gz", "loot-yield-1123-fetch-frontier-n1b-416.jsonl.gz", 4038420, 4038441),
    ("b416-4054751-boards.jsonl.gz", "loot-yield-1123-amberite-n1b-416.jsonl.gz", 4054730, 4054751),
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
