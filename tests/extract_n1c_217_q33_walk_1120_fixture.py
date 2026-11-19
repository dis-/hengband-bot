"""Extract tests/fixtures/n1c-217-q33-walk-1120.json.gz (q33-walk-1120).

Source: C:/hengband-backups/pdca/captures/n1c-217-q33-walk-1120 (from ~/hengbot-soak/n1-c/life-217,
Quest 33 段3, 2026-11-20 00:45-01:22, halted stall:floor-dwell:quest-strategy:sweep-walk):

 * ``*/state.jsonl.gz``: the halt's last board (``board``) and how many of its boards showed a hostile
   (``boards``, ``boards_with_hostiles``);
 * ``decisions.jsonl.gz``: every decision of the run as (reason, cell) and the cells where the walk
   turned back (``turns``).

Run: python tests/extract_n1c_217_q33_walk_1120_fixture.py [ROOT]
"""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/captures/n1c-217-q33-walk-1120")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-q33-walk-1120.json.gz"


def main():
    halt = next(path for path in ROOT.iterdir() if path.is_dir())
    with gzip.open(halt / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream if line.strip()]
    with gzip.open(ROOT / "decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    rows = [row for row in rows if (row.get("floor") or {}).get("quest_id") == 33]
    cells = [(row["position"]["y"], row["position"]["x"]) for row in rows]
    turns = [list(cells[index]) for index in range(1, len(cells) - 1)
             if (cells[index][1] - cells[index - 1][1]) * (cells[index + 1][1] - cells[index][1]) < 0]
    case = dict(source="n1c-217-q33-walk-1120", board=boards[-1], boards=len(boards),
                boards_with_hostiles=sum(1 for row in boards if row["detected_monsters"] or row["visible_monsters"]),
                reasons=dict(Counter(row["reason"] for row in rows)), turns=turns)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(OUTPUT, len(rows), len(turns))


if __name__ == "__main__":
    main()
