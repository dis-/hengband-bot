"""Extract the sensed-group *Destruction* fixtures (Angband 80F, 2026-11-22; owner 11-22 「倒して利益のない
場合は破壊する」).

Sources (~/hengbot-soak/<bot>/life-<n>/jsonlog/snapshots/, copied read-only to
C:/hengband-backups/pdca/deep80-defects-1122/); each window ends on the board before the recorded
esp-threat Recall (the first board ``recalling``):

- c-f7.jsonl.gz (n1-c life-219, snapshots-20261122-044037, player turns 2530201-2533400): 04:32:05,
  a hound pack (エア・ハウンド 8, エナジー・ハウンド 4, 重力ハウンド 2, 魔力・カオス・ハウンド) sensed;
  Recall read at 2533286.  Kept 2532300-2533283.
- c-f11.jsonl.gz (n1-c life-219, snapshots-20261122-051458, 2624564-2627598): 05:08:20, nine
  モアイ sensed; Recall read at 2627465.  Kept 2626500-2627460.
- b-f5.jsonl.gz (n1-b life-413, snapshots-20261122-041405, 3044781-3047795): 04:16:00, three
  ティンダロスの猟犬 sensed; Recall read at 3047668.  Kept 3046700-3047662.
- c-f10.jsonl.gz (n1-c life-219, snapshots-20261122-051458, 2618183-2621298): the dragon group
  (古代万色ドラゴン 6, 万色ドラゴン 3, ...; DROP_GOOD races) sensed; Recall read at 2621181.  Kept
  2620200-2621174.

The n1-c Magic-Eater's power lists (tests/fixtures/n1c-219-me-lists-0550-1122.json) are the
town-arrival checkpoint's of 05:50:29 (turn 2732552), the closest the life kept.

    python tests/extract_group_destroy_no_profit_1122_fixtures.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/deep80-defects-1122")
FIXTURES = Path(__file__).with_name("fixtures")
WINDOWS = (
    ("c-f7.jsonl.gz", "n1c-219-group-hounds-1122.jsonl.gz", 2532300, 2533283),
    ("c-f11.jsonl.gz", "n1c-219-group-moai-1122.jsonl.gz", 2626500, 2627460),
    ("b-f5.jsonl.gz", "n1b-413-group-tindalos-1122.jsonl.gz", 3046700, 3047662),
    ("c-f10.jsonl.gz", "n1c-219-group-dragons-1122.jsonl.gz", 2620200, 2621174),
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
