"""Extract tests/fixtures/deep-recall-loot-1123/ (tests/test_deep_recall_loot_1123_recorded.py).

Source: n1-c life-220 (Magic-Eater, Angband 80F) on 2026-11-22 17:33, read-only copies in
C:/hengband-backups/pdca/captures/loot-pick-1123/:

  n1c-220-80F-3002050.jsonl                 the viewing server's snapshot log
                                            ``snapshots-20261122-173746-227b0e.jsonl.gz``, turns
                                            3001980-3002070: the town's recall wait, the 80F
                                            arrival (5,91) with an item 2 cells off at (4,89), the
                                            absorbed *Destruction* that failed, the Word of Recall
                                            read under deep-teleport:recall (live 3002050) and the
                                            *Destruction* cast on the next board (live 3002058)
                                            that deleted the item
  ckpt/n1c-220-me-device-lists-3132181.json the absorbed-power lists of the same life's town-arrival
                                            checkpoint 20261122-181908 (policy.pkl
                                            ``_me_device_lists``): the lists are read from the
                                            screen, not carried by the snapshot log

Kept: the player-turn boards up to 3002058 and the lists, xz-compressed.

    python tests/extract_deep_recall_loot_1123_fixture.py
"""
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/loot-pick-1123")
FIXTURE = Path(__file__).with_name("fixtures") / "deep-recall-loot-1123"
LAST = 3002058


def main():
    FIXTURE.mkdir(exist_ok=True)
    rows = [json.loads(line) for line in
            (ROOT / "n1c-220-80F-3002050.jsonl").read_text(encoding="utf-8").splitlines()]
    boards = [json.dumps(row, ensure_ascii=False) for row in rows
              if row.get("type") == "player_turn" and row["turn"] <= LAST]
    (FIXTURE / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(boards) + "\n").encode("utf-8"), preset=9))
    lists = (ROOT / "ckpt" / "n1c-220-me-device-lists-3132181.json").read_text(encoding="utf-8")
    (FIXTURE / "me-device-lists.json.xz").write_bytes(lzma.compress(lists.encode("utf-8"), preset=9))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
