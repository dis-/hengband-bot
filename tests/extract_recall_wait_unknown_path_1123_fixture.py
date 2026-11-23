"""Extract tests/fixtures/recall-wait-unknown-path-1123/ (tests/test_recall_wait_unknown_path_1123_recorded.py).

Source: n1-c life-221 (Magic-Eater, the Mountain 50F) on 2026-11-23 18:43, read-only copies in
C:/hengband-backups/pdca/captures/recall-wait-unknown-path-1123/:

  n1c-221-50F-4695000.jsonl                 the viewing server's snapshot log (also in
                                            loot-pick-1123/), turns 4694951-4695080: the hunt, the
                                            absorbed area mapping (live 4694954), the Word of Recall
                                            read under deep-teleport:recall (live 4695000) and the
                                            wait at (23,153)/(22,152) (live ``return:wait-recall``
                                            from 4695002) with an item 16 cells off at (25,168) and
                                            no known floor to it
  n1c-221-me-device-lists-4894953.json      the absorbed-power lists (policy.pkl
                                            ``_me_device_lists``) of the same life's town-arrival
                                            checkpoint 20261123-211151 (turn 4894953), the earliest
                                            one the server keeps: the lists are read from the
                                            screen, not carried by the snapshot log

Kept: the player-turn boards up to 4695002 and the lists, xz-compressed.

    python tests/extract_recall_wait_unknown_path_1123_fixture.py
"""
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/recall-wait-unknown-path-1123")
FIXTURE = Path(__file__).with_name("fixtures") / "recall-wait-unknown-path-1123"
LAST = 4695002


def main():
    FIXTURE.mkdir(exist_ok=True)
    rows = [json.loads(line) for line in
            (ROOT / "n1c-221-50F-4695000.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    boards = [json.dumps(row, ensure_ascii=False) for row in rows
              if row.get("type") == "player_turn" and row["turn"] <= LAST]
    (FIXTURE / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(boards) + "\n").encode("utf-8"), preset=9))
    lists = (ROOT / "n1c-221-me-device-lists-4894953.json").read_text(encoding="utf-8")
    (FIXTURE / "me-device-lists.json.xz").write_bytes(lzma.compress(lists.encode("utf-8"), preset=9))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
