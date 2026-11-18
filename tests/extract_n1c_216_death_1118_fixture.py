"""Extract tests/fixtures/n1c-216-death-1118.jsonl.gz.

Source: n1-c life-216 (Magic-Eater Lv50, Angband 80F, build bot-42d7a304e), the death's records
copied read-only to C:/hengband-backups/pdca/n1c-216-death-1118: ``state.jsonl.gz`` (the state
ring, player turns 7228345-7228558).  Kept: the player turns 7228502 (five boards before the
first unseen hit) to 7228558 (the last board before the death, 2026-11-18 13:36).

    python tests/extract_n1c_216_death_1118_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/n1c-216-death-1118/state.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1c-216-death-1118.jsonl.gz"
LOW, HIGH = 7228502, 7228558


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
