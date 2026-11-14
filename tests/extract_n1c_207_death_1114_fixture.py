"""Extract tests/fixtures/n1c-207-death-1114.jsonl.gz.

Source: n1-c life-207 (zombie Magic-Eater Lv49, 金鉱 80F) boards copied read-only from the viewing
server (jsonlog/snapshots/snapshots-current.jsonl.gz, its last 600 lines) to
C:/hengband-backups/pdca/captures/n1c-207-death-1114/boards/tail600.jsonl.gz: the player turns
8350401 (the arrival on 80F by Recall, 2026-11-14 22:57:1x) to 8350944 (the death, 22:57:21).

    python tests/extract_n1c_207_death_1114_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/n1c-207-death-1114/boards/tail600.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1c-207-death-1114.jsonl.gz"
LOW, HIGH = 8350401, 8350944


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
