"""Freeze the n1-b life-413 Quest 25 waits of 2026-11-22 (tests/test_n1b_413_q25_wait_cells_1122_recorded.py).

Source: the viewing Magic-Eater n1-b life-413 (Lv37, Zombie) on Quest 25 『幽霊屋敷』 (floor (0, 48, 25)).
Copied read-only from the viewing server (~/hengbot-soak/n1-b/life-413/jsonlog) to
C:/hengband-backups/pdca/q25-wait-cells-1122/copied:

  windows.json.gz   the player_turn boards of turns 2507800-2508200 (snapshots-20261122-013654: the
                    ranged ambush holding [13,1] after its third kill) and 2563250-2563700
                    (snapshots-current: the dreadmaster phase walking to [1,17] and holding there),
                    with bot-decisions.jsonl(.1)'s Q25 rows of the same turns

and the battle record at the floor's last stop, C:/hengband-backups/pdca/n1b-413-q25-1122/q25-battle.json
(its kills with their turns: the test reconstructs each phase's record from them).

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/q25-wait-cells-1122/copied/windows.json.gz")
RECORD = Path("C:/hengband-backups/pdca/n1b-413-q25-1122/q25-battle.json")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-413-q25-wait-cells-1122.json.gz"
TURNS = (2507807, 2507812, 2507818, 2563370, 2563375, 2563380, 2563386)


def main():
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        source = json.load(stream)
    boards, seen = [], set()
    for board in source["boards"]:
        if board["turn"] in TURNS and board["turn"] not in seen:
            seen.add(board["turn"])
            boards.append(board)
    decisions, kept = [], set()
    for row in source["decisions"]:
        entry = (int(row["turn"]), row["reason"], row["key"])
        if entry[0] in TURNS and entry not in kept:
            kept.add(entry)
            decisions.append({"turn": entry[0], "reason": entry[1], "key": entry[2]})
    fixture = {
        "window": {"source": "n1-b life-413 snapshots turns 2507807-2507818 and 2563370-2563386 "
                             "(copied from the viewing server)",
                   "boards": boards, "decisions": decisions},
        "battle_record": json.loads(RECORD.read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
