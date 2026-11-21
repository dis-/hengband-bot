"""Extract the n1-b life-413 esp-threat Recall fixtures (Angband 80F, 2026-11-22).

Sources (~/hengbot-soak/n1-b/life-413/jsonlog/snapshots/, copied read-only to
C:/hengband-backups/pdca/deep80-defects-1122/):

- b-f2.jsonl.gz (snapshots-20261122-030935-28a359, player turns 2618400-2621500): 02:56:03
  esp-threat:leave-recall at 2621415, HP 480/748, 『サウロンの口』 (T1) sensed 28 off.  Kept
  2620300-2621415.

    python tests/extract_n1b_413_esp_rest_1122_fixtures.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/deep80-defects-1122")
FIXTURES = Path(__file__).with_name("fixtures")
WINDOWS = (
    ("b-f2.jsonl.gz", "n1b-413-esp-rest-sensed-t1-1122.jsonl.gz", 2620300, 2621415),
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
