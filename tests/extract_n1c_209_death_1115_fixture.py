"""Extract tests/fixtures/n1c-209-death-1115.jsonl.gz.

Source: n1-c life-209 (zombie Magic-Eater Lv8, Yeek cave 1F) incident capture copied read-only
from the viewing server to C:/hengband-backups/pdca/n1c-209-death-1115/incident-captures/
20261115-045254-player-death/snapshots/snapshots-current.jsonl.gz: the player turns 129046 (the
walk-out to the up-stair, return:seek-upstairs, 2026-11-15 04:52:4x) to 129075 (the second flee
step away from it).

    python tests/extract_n1c_209_death_1115_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/n1c-209-death-1115/incident-captures/"
              "20261115-045254-player-death/snapshots/snapshots-current.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1c-209-death-1115.jsonl.gz"
LOW, HIGH = 129046, 129075


def _boards(stream):
    for line in stream:
        try:
            board = json.loads(line)
        except json.JSONDecodeError:  # the ring's cut first line
            continue
        if board.get("type") == "player_turn" and LOW <= board["turn"] <= HIGH:
            yield board


def main() -> None:
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        boards = list(_boards(stream))
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for board in boards:
            out.write((json.dumps(board, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
