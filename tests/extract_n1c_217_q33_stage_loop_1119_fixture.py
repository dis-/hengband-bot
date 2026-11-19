"""Extract tests/fixtures/n1c-217-q33-stage-loop-1119.json.gz (q33-stage-loop-1119).

Source (C:/hengband-backups/pdca/captures/n1c-217-q33-loop-1119, from ~/hengbot-soak/n1-c/life-217,
build 33e3dadf0, Quest 33 resumed 2026-11-19 19:25, halted 20:00 stall:floor-dwell:quest-strategy:hold):

 * ``snapshots-current.jsonl.gz``: the first Q33 board with the player on [15,38] (the 段1 stand) and
   a monster sensed: the three 父なる『ダゴン』 at [25,45] [23,44] [25,44], two ボーシン.
 * ``decisions-after-resume.jsonl.gz``: the stands walked and held, as runs of (time, cell, reason,
   decisions) -- the round [13,39] [11,39] [2,46] [2,30] [5,10] [14,10] [15,38] and again, never
   [14,47] (refused: the Queens and the Dagons both act there) nor below.

Run: python tests/extract_n1c_217_q33_stage_loop_1119_fixture.py [ROOT]
"""
import gzip
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "C:/hengband-backups/pdca/captures/n1c-217-q33-loop-1119")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-q33-stage-loop-1119.json.gz"


def main():
    board = None
    with gzip.open(ROOT / "snapshots-current.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if (row["floor"].get("quest_id") == 33 and (row["player"]["y"], row["player"]["x"]) == (15, 38)
                    and row["detected_monsters"]):
                board = row
                break
    rows = []
    with gzip.open(ROOT / "decisions-after-resume.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if (row.get("floor") or {}).get("quest_id") == 33:
                rows.append(row)
    runs = []
    for (cell, reason), group in itertools.groupby(
            rows, key=lambda row: ((row["position"]["y"], row["position"]["x"]), row["reason"])):
        group = list(group)
        runs.append(dict(time=group[0]["time"], cell=list(cell), reason=reason, decisions=len(group)))
    case = dict(source="n1c-217-q33-stage-loop-1119", board=board, runs=runs)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(OUTPUT, len(runs))


if __name__ == "__main__":
    main()
