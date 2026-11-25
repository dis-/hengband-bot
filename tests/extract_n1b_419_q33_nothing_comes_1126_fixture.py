"""Freeze n1-b life-419's Quest 33 stop: the sweep stopped by name with a Bokrug asleep in the west room.

Source: n1-b life-419 (Zombie Magic-Eater Lv41) on hengband.net, the process started at 2026-11-26 08:00:01
(bot main 9688945f9), entered the Quest 33 floor at 08:07:18 and stopped by name at 08:09:23 (turn
3867119, [15,39], ``quest:blocked:sweep-nothing-comes``; incident capture
20261126-080923-quest-blocked-sweep-nothing-comes).  Copied to
C:/hengband-backups/pdca/n1b-419-q33-nothing-comes-1126 (SOURCE.txt):

 * ``town-arrival-policy.pkl``: the same process's town-arrival checkpoint (08:06:26, turn 3860443);
 * ``quest-plan.pkl``, ``sweep-kills.json``, ``map-memory.pkl``: the plan state, the tracked races' kills
   and the remembered maps the process left at the stop (quest_plan_record, quest_sweep_record,
   map_memory_record), which a restart restores;
 * ``full-current.jsonl.gz``: the process's boards; the fixture keeps the stop board (turn 3867119),
   the board of the detection that showed the third Bokrug (turn 3866785) and the last ~f skill list;
 * ``decision-tail.jsonl``: the decisions of 08:06:54-08:09:23.

    python tests/extract_n1b_419_q33_nothing_comes_1126_fixture.py [source-dir]
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1b-419-q33-nothing-comes-1126")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-419-q33-nothing-comes-1126"
QUEST = 33
STOP_TURN = 3867119
DETECTION_TURN = 3866785
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(lines):
    for line in lines:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def main():
    boards, knowledge = {}, None
    with gzip.open(ROOT / "full-current.jsonl.gz", "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for raw in _rows(stream):
            if raw.get("type") == "knowledge" and raw["turn"] <= STOP_TURN:
                knowledge = raw
            elif (raw.get("type") == "player_turn" and raw["floor"].get("quest_id") == QUEST
                  and raw["turn"] in (STOP_TURN, DETECTION_TURN)):
                boards[raw["turn"]] = raw   # the last board of the turn: the one decided last
    with open(ROOT / "decision-tail.jsonl", "rb") as stream:
        recorded = [{"sequence": row["decision_sequence"], "turn": row["turn"], "reason": row["reason"],
                     "key": row["key"], "position": [row["position"]["y"], row["position"]["x"]]}
                    for row in _rows(stream) if "decision_sequence" in row
                    and row["floor"]["quest_id"] == QUEST and row["turn"] >= DETECTION_TURN]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, source in (("policy.pkl.xz", "town-arrival-policy.pkl"), ("quest-plan.pkl.xz", "quest-plan.pkl"),
                         ("map-memory.pkl.xz", "map-memory.pkl")):
        (OUTPUT / name).write_bytes(lzma.compress((ROOT / source).read_bytes(), preset=PRESET))
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1b-419-q33-nothing-comes-1126", "stop_board": boards[STOP_TURN],
         "detection_board": boards[DETECTION_TURN], "knowledge": knowledge, "recorded": recorded,
         "sweep_kills": json.loads((ROOT / "sweep-kills.json").read_text(encoding="utf-8"))},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8", "surrogateescape"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(recorded)} decisions\n")


if __name__ == "__main__":
    main()
