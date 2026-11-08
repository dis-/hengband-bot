"""Extract tests/fixtures/n1c-174-hazard-loop-1109.json.gz: n1-c life-174's steps from the
notch above the poison-puddle room into the puddle, Orc cave 23F (2026-11-09).

Sources: the state.jsonl.gz of the two loop-detected captures of hengband.net
~/hengbot-soak/n1-c/life-174/captures/ (20261109-003105 and 20261109-003623), copied
locally; their directories are given on the command line in that order.  Only this tool
reads the copies; the committed test reads the fixture: for each crossing, the notch
board and the next board (the player on the puddle, moved as recorded).
"""
import gzip
import json
import sys
from pathlib import Path

from tests.extract_n1c_loops_0336_1102_fixtures import write


# (capture, notch turn, puddle turn)
CROSSINGS = (
    (0, 3413736, 3413747),  # (18,154) -> (19,155)
    (0, 3413977, 3413987),  # (18,153) -> (19,152)
    (1, 3429342, 3429356),  # (18,154) -> (19,155), 00:36 recurrence
    (1, 3429729, 3429737),  # (18,153) -> (19,152), 00:36 recurrence
)


def main(first: str, second: str) -> None:
    captures = []
    for directory in (first, second):
        with gzip.open(Path(directory) / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        captures.append({row["turn"]: row for row in rows if row["type"] == "player_turn"})
    write(Path(__file__).with_name("fixtures") / "n1c-174-hazard-loop-1109.json.gz", [
        [captures[capture][notch], captures[capture][puddle]]
        for capture, notch, puddle in CROSSINGS])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
