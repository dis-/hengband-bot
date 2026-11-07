"""Freeze the n1-c life-159 boards of Quest 25 (2026-11-07 15:31-15:32) for the mass and teleport tests.

Source: n1-c life-159 (build bot-16206b8d3) on hengband.net, ~/hengbot-soak/n1-c/life-159/jsonlog,
copied to C:/hengband-backups/pdca/captures/n1c-159-q25-mass-1107/ (snapshots-current.jsonl.gz, the
snapshot ring; bot-decisions.jsonl.gz, the decision log).  One board per recorded decision on the
quest floor, from the arrival (turn 2890499) through the first boards where a corpse mass stood
beside the player on [1,18] and the bot held (``LAST_SEQUENCE``): the ring's last row of that turn
with the decision row's messages.  On the way: the six Scrolls of Teleportation the Resistance
potion's no-chance leave read (the first beside the spectral tyrannosaurus on [10,1]).  The
recorded reason and key of each board are kept.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-159-q25-mass-1107")
OUTPUT = Path(__file__).with_name("fixtures") / "q25-mass-n1c-159-1107.json.gz"
QUEST = 25
LAST_SEQUENCE = 431


def gz_rows(path: Path) -> list[dict]:
    found = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        try:
            for line in stream:
                try:
                    found.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # The live ring may end in a partial line.
        except EOFError:
            pass
    return found


def main():
    rows = gz_rows(ROOT / "snapshots-current.jsonl.gz")
    decisions = [row for row in gz_rows(ROOT / "bot-decisions.jsonl.gz")
                 if row.get("floor", {}).get("quest_id") == QUEST]
    end = next(index for index, row in enumerate(decisions) if row["decision_sequence"] == LAST_SEQUENCE)
    decisions = decisions[:end + 1]
    last = {row["turn"]: row for row in rows
            if row["type"] == "player_turn" and row.get("floor", {}).get("quest_id") == QUEST}
    boards, recorded = [], []
    for row in decisions:
        boards.append(dict(last[row["turn"]], messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"], "rung": row.get("rung")})
    first = next(index for index, row in enumerate(rows)
                 if row["type"] == "player_turn" and row["turn"] == boards[0]["turn"])
    knowledge = {}
    for row in rows[:first]:
        if row["type"] == "knowledge":
            knowledge[row["knowledge"]["category"]] = row
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1c-159-q25-mass-1107", boards=boards, recorded=recorded,
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
