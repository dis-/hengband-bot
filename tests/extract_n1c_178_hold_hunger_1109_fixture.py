"""Freeze n1-c life-178's Quest 25 hold boards (turns 4100808-4101016) for the hold-hunger test.

Source: n1-c life-178 on hengband.net (~/hengbot-soak/n1-c/life-178), read 2026-11-09 07:33:
 * ``slice-state.jsonl``: the state.jsonl rows of turns 4100800-4101099;
 * ``slice-dec.jsonl``: the bot-decisions.jsonl rows of the same turns;
 * ``skill-row.json``: state.jsonl row 2 (the skill list of turn 4089201),
copied to C:/hengband-backups/pdca/captures/n1c-178-hold-hunger-1109/life178/.  The Home
knowledge is the character's town-arrival list frozen in n1c-176-q25-trap-search-1109.json.gz
(the same character; no town since).  The boards run through the third hungry board.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-178-hold-hunger-1109/life178")
FIXTURES = Path(__file__).with_name("fixtures")
OUTPUT = FIXTURES / "n1c-178-hold-hunger-1109.json.gz"
LAST_TURN = 4101016


def rows(name):
    with open(ROOT / name, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def main():
    decisions = {row["turn"]: row for row in rows("slice-dec.jsonl")}
    boards = [row for row in rows("slice-state.jsonl") if row["turn"] <= LAST_TURN]
    recorded = [{"turn": raw["turn"], "reason": decisions[raw["turn"]]["reason"],
                 "key": decisions[raw["turn"]]["key"],
                 "food_state": decisions[raw["turn"]]["player"].get("food_state")}
                for raw in boards]
    with open(ROOT / "skill-row.json", encoding="utf-8") as stream:
        skill = json.load(stream)
    with gzip.open(FIXTURES / "n1c-176-q25-trap-search-1109.json.gz", "rt", encoding="utf-8") as stream:
        home = json.load(stream)["home"]
    case = {"source": "n1c-178-hold-hunger-1109", "boards": boards, "recorded": recorded,
            "skill": skill, "home": home}
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
