"""Extract tests/fixtures/n1c-221-me-ranged-ev-1123.json.gz.

Source: n1-c life-221 (Magic-Eater Lv39, Quest 25, build main 13f0777c9), copied read-only from
the viewing server's ``~/hengbot-soak/n1-c/life-221/jsonlog/``:

* ``bot-decisions.jsonl`` (and ``.1``), the rows of 2026-11-23 05:00:00-05:04:59 (``decisions``);
* ``snapshots/snapshots-current.jsonl.gz``, the boards of game turns 3191400-3207100 (``boards``);
* ``snapshots/snapshots-20261123-045542-dfb09c.jsonl.gz``, the ``~f`` skill list board of game
  turn 3152422, the last before the fight (``skill``).

Kept: the ``player_turn`` boards of turns 3191524-3191870 (05:00:39-05:00:48: the stairway to
hell beside the player on [13,29], its theft and blink, and the five Healing potions), the skill
board, and of every decision row of 05:00:39-05:00:48 its sequence, turn, key, reason, HP and
messages.

    python tests/extract_n1c_221_me_ranged_ev_1123_fixture.py <raw dir>

``<raw dir>`` holds ``decisions-0500.jsonl``, ``snapshots-0500.jsonl.gz`` and
``skill-3152422.json.gz`` (the three cuts above).
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-me-ranged-ev-1123.json.gz"
FIRST_TURN, LAST_TURN = 3191524, 3191870
FIRST_TIME, LAST_TIME = "2026-11-23T05:00:39", "2026-11-23T05:00:48"


def main() -> None:
    raw = Path(sys.argv[1])
    with gzip.open(raw / "snapshots-0500.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [board for board in map(json.loads, stream)
                  if board["type"] == "player_turn" and FIRST_TURN <= board["turn"] <= LAST_TURN]
    with gzip.open(raw / "skill-3152422.json.gz", "rt", encoding="utf-8") as stream:
        skill = json.loads(stream.read())
    decisions = []
    with open(raw / "decisions-0500.jsonl", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if FIRST_TIME <= row["time"][:19] <= LAST_TIME:
                decisions.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                                  "key": row["key"], "reason": row["reason"],
                                  "hp": row["player"]["hp"], "messages": row["messages"]})
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump({"boards": boards, "skill": skill, "decisions": decisions}, stream,
                  ensure_ascii=False)


if __name__ == "__main__":
    main()
