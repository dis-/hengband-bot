"""Extract tests/fixtures/n1c-217-least-visited-1118.jsonl.gz.

Source: n1-c life-217 (Magic-Eater Lv26, Orc cave 20F, build bot-9a3390b4e), the loop stop's
capture 20261118-150934-loop-detected copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-217-least-visited-1118 (``state.jsonl.gz``, the state ring,
player turns 1194026-1194458; ``bot-decisions.jsonl.gz``).  Kept: the boards of player turns
1194146 (the last seek-loot step before 混沌の獣人 came beside) to 1194267, and the recorded
decision (turn, key, reason, position) of each.

    python tests/extract_n1c_217_least_visited_1118_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/n1c-217-least-visited-1118")
TARGET = Path(__file__).with_name("fixtures") / "n1c-217-least-visited-1118.jsonl.gz"
LOW, HIGH = 1194146, 1194267


def main() -> None:
    with gzip.open(SOURCE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [board for board in map(json.loads, stream)
                  if board.get("type") == "player_turn" and LOW <= board["turn"] <= HIGH]
    decisions = {}
    with gzip.open(SOURCE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if LOW <= row["turn"] <= HIGH and row["reason"] != "loop-detected":
                decisions[row["turn"]] = {field: row[field]
                                          for field in ("turn", "key", "reason", "position")}
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for board in boards:
            row = {"board": board, "decision": decisions[board["turn"]]}
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
