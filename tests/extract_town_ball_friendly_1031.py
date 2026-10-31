"""Freeze the town ball / friendly-bystander board (owner 2026-10-31).

Board: the D49 n1-c life-067 town fight (2026-10-31 19:26, Outpost, Lv8
Magic-Eater beside わめくキチガイ), ring row board turn 157197 from the frozen
tests/fixtures/town-combat-survival-20261031.json.gz (see
tests/extract_town_combat_survival_1031.py for its capture).  Added: the race
lore of the two friendly town races the test places on that board's real
map -- すずめ (race 3, 1 hp) and 農夫『マゴット』 (race 8, FORCE_MAXHP 350) --
from lib/edit/MonraceDefinitions.jsonc, as the bot loads it.  Only this
extraction tool reads the sources; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


SOURCE = Path(__file__).with_name("fixtures") / "town-combat-survival-20261031.json.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "town-ball-friendly-20261031.json.gz"
BOARD_TURN = 157197
FRIENDLY_RACES = (3, 8)


def main():
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        source = json.load(stream)
    board = next(row for row in source["boards"] if row["turn"] == BOARD_TURN)
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    monraces = dict(source["monraces"])
    monraces.update({str(race): asdict(races[race]) for race in FRIENDLY_RACES})
    fixture = dict(
        source=source["source"] + f", board turn {BOARD_TURN}",
        board=board, skill=source["skill"], home=source["home"],
        sequence=source["sequence"], monraces=monraces,
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
