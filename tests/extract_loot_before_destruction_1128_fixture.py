"""Extract tests/fixtures/loot-before-destruction-1128/ (tests/test_loot_before_destruction_1128_recorded.py).

Source: n1-b life-419 (Magic-Eater Lv50, Angband 80F), read-only copies in
C:/hengband-backups/pdca/captures/loot-before-destruction-1128/:

  n1b-419-80F-13909172-13911500.jsonl   the viewing server's snapshot log
                                        ``snapshots-20261128-022324-c8d21a.jsonl.gz``, 2026-11-28
                                        02:17-02:19: the 80F floor from its arrival (13909180) to
                                        the town (13910762); the Ring of Speed at (8,80) deleted by
                                        the *Destruction* decided on 13909797, the pack-full Recall
                                        read on 13910555 with the Rings of Speed at (16,120) and
                                        (29,48) left behind
  n1b-419-80F-13066000-13067200.jsonl   ``snapshots-20261127-221546-7a2404.jsonl.gz``, 2026-11-27
                                        22:14: the 80F arrival (13066831), the walk toward the Ring
                                        of Speed at (27,60) and the *Destruction* decided on
                                        13066914 beside 『死神ももえ』 after a hit of 163
  ckpt/n1b-419-me-device-lists-14346611.json
                                        the absorbed-power lists of the same life's town-arrival
                                        checkpoint 20261128-050851 (policy.pkl ``_me_device_lists``)

Kept: the player-turn boards of the two floors, and the lists, xz-compressed.

    python tests/extract_loot_before_destruction_1128_fixture.py
"""
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/loot-before-destruction-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "loot-before-destruction-1128"
FLOORS = (
    ("n1b-419-80F-13909172-13911500.jsonl", 13909180, 13910700, "boards-0218.jsonl.xz"),
    ("n1b-419-80F-13066000-13067200.jsonl", 13066831, 13066915, "boards-2214.jsonl.xz"),
)


def main():
    FIXTURE.mkdir(exist_ok=True)
    for source, first, last, target in FLOORS:
        rows = [json.loads(line) for line in
                (ROOT / source).read_text(encoding="utf-8").splitlines() if line.strip()]
        boards = [json.dumps(row, ensure_ascii=False) for row in rows
                  if row.get("type") == "player_turn" and first <= row["turn"] <= last]
        (FIXTURE / target).write_bytes(
            lzma.compress(("\n".join(boards) + "\n").encode("utf-8"), preset=9))
    lists = (ROOT / "ckpt" / "n1b-419-me-device-lists-14346611.json").read_text(encoding="utf-8")
    (FIXTURE / "me-device-lists.json.xz").write_bytes(lzma.compress(lists.encode("utf-8"), preset=9))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
