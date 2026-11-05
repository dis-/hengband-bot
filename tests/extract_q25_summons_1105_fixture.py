"""Freeze the n1-b life-312 boards of Quest 25 (2026-11-05 12:02, death) for the summon tests.

Source: the player-death copy C:/hengband-backups/pdca/captures/n1b-312-q25-death-1105/
(cap.tgz: jsonlog/snapshots/snapshots-current.jsonl.gz; tail-decisions.jsonl.gz).  One board
per recorded decision on the quest floor, from the arrival (turn 11651335) to the death: the
ring's last row of that turn with the decision row's messages, which are the ones the bot was
given (control_client merges a skipped board's messages into the next).  Two sessions: the
08:13 retirement and the 12:02 resume.  The recorded reason and key of each board are kept.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import io
import json
import sys
import tarfile
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures/n1b-312-q25-death-1105")
RING = "jsonlog/snapshots/snapshots-current.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "q25-summons-n1b-312-1105.json.gz"
QUEST = 25


def ring_rows() -> list[dict]:
    with tarfile.open(ROOT / "cap.tgz") as archive:
        member = next(name for name in archive.getnames() if name.endswith(RING))
        data = archive.extractfile(member).read()
    rows = []
    with gzip.open(io.BytesIO(data), "rt", encoding="utf-8") as stream:
        rows.extend(json.loads(line) for line in stream if line.strip())
    return rows


def main():
    rows = ring_rows()
    with gzip.open(ROOT / "tail-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        decisions = [json.loads(line) for line in stream]
    decisions = [row for row in decisions if row.get("floor", {}).get("quest_id") == QUEST]
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
    case = dict(source="n1b-312-q25-death-1105", boards=boards, recorded=recorded,
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
