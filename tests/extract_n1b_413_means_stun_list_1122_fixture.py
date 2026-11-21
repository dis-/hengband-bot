"""Extract tests/fixtures/n1b-413-means-stun-list-1122.jsonl.gz.

Source: n1-b life-413 (Magic-Eater Lv39, Angband 80F, 2026-11-22 04:02:29), the snapshot file
~/hengbot-soak/n1-b/life-413/jsonlog/snapshots/snapshots-20261122-040941-2507a3.jsonl.gz, its
player turns 2929500-2933500 copied read-only to
C:/hengband-backups/pdca/deep80-defects-1122/b-e.jsonl.gz.  Kept: the player-turn boards 2932972
(stunned, its own *Destruction* due) to 2933001 (the means-spent Recall).

    python tests/extract_n1b_413_means_stun_list_1122_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/deep80-defects-1122/b-e.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1b-413-means-stun-list-1122.jsonl.gz"
LOW, HIGH = 2932972, 2933001


def main() -> None:
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        boards = [board for board in map(json.loads, stream)
                  if board.get("type") == "player_turn" and LOW <= board["turn"] <= HIGH]
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for board in boards:
            out.write((json.dumps(board, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
