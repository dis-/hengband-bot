"""Freeze the n1-c life-211 Quest 25 hold boards with cursed gear of 2026-11-15 (tests/test_n1c_211_rest_curse_1115_recorded.py).

Source: the viewing Magic-Eater n1-c life-211 (Lv33) on Quest 25 『幽霊屋敷』 (floor (0, 48, 25)), battle
phase 0 (the ambush) ready, holding '5' with seven cursed pieces worn (the druj's CAUSE_3 curses), the
summoning and drain-HP curses announcing themselves.  Copied read-only from the viewing server
(~/hengbot-soak/n1-c/life-211: state.jsonl, jsonlog/bot-decisions.jsonl(.1), jsonlog/q25-battle.json)
to C:/hengband-backups/pdca/curse-1115/n1c-211:

  state-rows.jsonl.gz   the player_turn boards of turns 4123560-4123700 (「★鉄鋲底の靴『炎の鉄ゲタ』が
                        動物を引き寄せた！」 at 4123620) and 4135900-4136145 (「高速度のヘヴィ・クロスボウは
                        あなたの体力を吸収した！」 at 4135981, the life's last boards)
  decisions.jsonl.gz    their decision rows (turn, reason, key, time); the game was restarted from its
                        save twice and the turns of 4123xxx were decided at 06:29 and again at 06:51:
                        the last decision of a turn is kept, the boards are the 06:51 process's
  q25-battle.json       the battle record the life left (06:53)

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/curse-1115/n1c-211")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-211-rest-curse-1115.json.gz"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def main():
    boards = sorted(_rows(ROOT / "state-rows.jsonl.gz"), key=lambda board: board["turn"])
    decisions = {}
    for row in sorted(_rows(ROOT / "decisions.jsonl.gz"), key=lambda row: (row["time"] or "", row["turn"])):
        decisions[row["turn"]] = {"turn": row["turn"], "reason": row["reason"], "key": row["key"]}
    fixture = {
        "boards": boards,
        "decisions": [decisions[turn] for turn in sorted(decisions)],
        "battle_record": json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(fixture["decisions"]))


if __name__ == "__main__":
    main()
