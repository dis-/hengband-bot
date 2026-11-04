"""Extract tests/fixtures/q25-warning-1105.json.gz: the boards of Q25's first real play where
the weapon warning refused a step (n1-b life-310, build bot-e0a97bcb5, 2026-11-05 08:12-08:13).

Each stop is the walk's board and the next board, which carries the warning prompt.

    python tests/extract_q25_warning_1105_fixture.py <cap>/jsonlog/snapshots/snapshots-current.jsonl.gz
"""
import gzip
import json
import sys
import zlib
from pathlib import Path

TARGET = Path(__file__).with_name("fixtures") / "q25-warning-1105.json.gz"
PROMPT = "本当にこのまま進むか"
PROMPT_TURNS = {"choke": 11651532, "corridor": 11651660}
WALK_TURNS = {"choke": 11651531, "corridor": 11651659}


def _members(data: bytes):
    """A multi-member gzip tail: decode from the first member header on."""
    position = data.find(b"\x1f\x8b\x08")
    while position >= 0 and position < len(data):
        stream = zlib.decompressobj(31)
        yield stream.decompress(data[position:])
        position = len(data) - len(stream.unused_data)
        if not stream.unused_data:
            return


def main() -> None:
    boards = []
    for line in b"".join(_members(Path(sys.argv[1]).read_bytes())).split(b"\n"):
        try:
            board = json.loads(line)
        except ValueError:
            continue
        if board.get("type") == "player_turn" and board["floor"].get("quest_id") == 25:
            boards.append(board)
    fixture = {}
    for name, turn in PROMPT_TURNS.items():
        prompt = next(board for board in boards if board["turn"] == turn
                      and any(PROMPT in message for message in board["messages"]))
        walk = [board for board in boards if board["turn"] == WALK_TURNS[name]][-1]
        fixture[name] = {"walk": walk, "prompt": prompt}
    with gzip.open(TARGET, "wt", encoding="utf-8") as stream:
        json.dump(fixture, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
