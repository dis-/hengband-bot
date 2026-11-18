"""Extract tests/fixtures/n1b-411-t1-walk-approach-1118.jsonl.gz.

Source: n1-b life-411 (Magic-Eater Lv50, Castle 65F, build bot-54196e30b), stopped with
``loop-detected`` at 2026-11-18 21:29:51: ``sensed-t1:walk`` '9' at (10,73) and
``sensed-t1:approach-destruction`` '1' at (9,74) in turn.  The capture
(captures/20261118-212951-loop-detected) copied read-only to
C:/hengband-backups/pdca/n1b-411-t1-walk-approach-1118: ``state.jsonl.gz`` (player turns
7411301-7411554).  Kept: the player turns 7411511 (two boards before the pair began) to
7411528 (the approach stepping back into (10,73)).

    python tests/extract_n1b_411_t1_walk_approach_1118_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/n1b-411-t1-walk-approach-1118/state.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1b-411-t1-walk-approach-1118.jsonl.gz"
LOW, HIGH = 7411511, 7411528


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
