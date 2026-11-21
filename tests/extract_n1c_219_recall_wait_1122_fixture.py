"""Extract tests/fixtures/n1c-219-recall-wait-1122.jsonl.gz (n1-c life-219, Angband 80F, 2026-11-22).

Source: the viewing server's ``~/hengbot-soak/n1-c/life-219/state.jsonl`` (read-only), the boards
(``type`` ``player_turn``, the last board of a turn) of

* turns 2751340-2751460 (decisions 14388-14403, 05:56:03-05:56:06): 混沌 (race 815: MULTIPLY,
  KILL_WALL, BR_CHAO) met, the first absorbed *Destruction* (14393, turn 2751382) and the
  second (14398, 2751421) on the swarm that bred back;
* turns 2751560-2751726 (decisions 14414-14443): the last uses, the Recall read with none left
  (14418), the countdown, the Teleportation landing at (37,17) and 『マダム・デビ』 awake behind
  the telepathy (14437-14443).

The policy checkpoint is tests/fixtures/n1c-219-death-1122.pkl.xz's (extract_n1c_219_death_1122_fixture).

    python tests/extract_n1c_219_recall_wait_1122_fixture.py <state.jsonl>
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-219-recall-wait-1122.jsonl.gz"
WINDOWS = ((2751340, 2751460), (2751560, 2751726))


def main(state_path: str) -> None:
    boards = {}
    opener = gzip.open if state_path.endswith(".gz") else open
    with opener(state_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if raw.get("type") == "player_turn" and any(
                    low <= raw.get("turn", 0) <= high for low, high in WINDOWS):
                boards[raw["turn"]] = raw  # the last board of a turn is the decision's
    with gzip.GzipFile(FIXTURE, "wb", mtime=0) as out:
        for turn in sorted(boards):
            out.write((json.dumps(boards[turn], ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(FIXTURE, FIXTURE.stat().st_size, len(boards))


if __name__ == "__main__":
    main(sys.argv[1])
