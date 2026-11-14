"""Freeze the boards of n1-a life-522's death (2026-11-14 19:35, floor (1, 49, 0)).

Source, read-only, the analysis folder C:/hengband-backups/pdca/captures/n1a-522-death-1114:

  20261114-193514-exit-no-marker/state.jsonl.gz          the player_turn boards of the last visit
                                                         (turns 2915002-2916691)
  20261114-193514-exit-no-marker/bot-decisions.jsonl.gz  the live decision rows of the same turns

One board per decision row from ``FIRST_TURN`` on (the fight: the first shot at the hounds, the
cornered attack, the three heals): the last board of the row's game turn, its messages replaced
by the row's messages (the live process merges the messages of a board it did not decide on into
the next decision).  The rows keep sequence, turn, reason, key and the recorded threat_tiers'
tier / instant_death.  ``town`` keeps the last town visit's board before Home (turn 2915372, the
travel to Home after the recovery) and its Home page (turn 2915708, the one ``store`` row of
store_type 7): the shelf held the Rod of Teleport Other and two Wands of Teleport Other.  Only
this tool reads the copies; the tests read the fixture.

    python tests/extract_teleport_follower_n1a_522_fixture.py <capture directory>
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "teleport-follower-n1a-522-1114.json.xz"
STOP = "20261114-193514-exit-no-marker"
FIRST_TURN = 2916444
TOWN_TURN = 2915372
HOME_TURN = 2915708


def main() -> None:
    capture = Path(sys.argv[1]) / STOP
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        states = list(map(json.loads, stream))
    boards = [row for row in states if row.get("type") == "player_turn"]
    town = {
        "board": [raw for raw in boards if raw["turn"] == TOWN_TURN][-1],
        "home": next(raw for raw in states if raw.get("type") == "store"
                     and raw["turn"] == HOME_TURN and raw["store"]["store_type"] == 7),
    }
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    decided, decisions = [], []
    for row in rows:
        if row["turn"] < FIRST_TURN:
            continue
        board = [raw for raw in boards if raw["turn"] == row["turn"]][-1]
        decided.append(dict(board, messages=row["messages"]))
        tiers = row.get("threat_tiers") or {}
        decisions.append({
            "sequence": row["decision_sequence"], "turn": row["turn"], "reason": row["reason"],
            "key": row["key"], "tier": tiers.get("tier"),
            "instant_death": tiers.get("instant_death"),
        })
    FIXTURE.write_bytes(lzma.compress(
        json.dumps({"boards": decided, "decisions": decisions, "town": town},
                   ensure_ascii=False).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
