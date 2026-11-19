"""Extract tests/fixtures/n1c-217-q33-gachapin-wait-1119.json.gz (q33-gachapin-wait-1119).

Source: C:/hengband-backups/pdca/captures/n1c-217-q33-lure2-1119 (from ~/hengbot-soak/n1-c/life-217,
Quest 33 段2 after the restart record was seeded, 2026-11-19 23:13-23:14): ``*/state.jsonl.gz`` the boards
of the process, the first one with the player on the lure's start [20,48] (the Gachapins sensed at
[21,59] [23,57] [24,57]); ``*/bot-decisions.jsonl.gz`` its decisions as runs of (time, cell, reason,
decisions), and every board's Gachapin cells while the player held [20,48] (``held``).

Run: python tests/extract_n1c_217_q33_gachapin_wait_1119_fixture.py [ROOT]
"""
import gzip
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "C:/hengband-backups/pdca/captures/n1c-217-q33-lure2-1119")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-q33-gachapin-wait-1119.json.gz"
GACHAPIN = 441


def main():
    halt = next(path for path in ROOT.iterdir() if path.is_dir())
    with gzip.open(halt / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream if line.strip()]
    held = [row for row in boards if (row["player"]["y"], row["player"]["x"]) == (20, 48)]
    board = held[0]
    cells = [[row["turn"], sorted([m["y"], m["x"]] for m in row["detected_monsters"] + row["visible_monsters"]
                                  if m["race_id"] == GACHAPIN)] for row in held]
    with gzip.open(halt / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    rows = [row for row in rows if (row.get("floor") or {}).get("quest_id") == 33]
    runs = []
    for (cell, reason), group in itertools.groupby(
            rows, key=lambda row: ((row["position"]["y"], row["position"]["x"]), row["reason"])):
        group = list(group)
        runs.append(dict(time=group[0]["time"], cell=list(cell), reason=reason, decisions=len(group)))
    case = dict(source="n1c-217-q33-gachapin-wait-1119", board=board, runs=runs, held=cells)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(OUTPUT, len(runs), len(cells))


if __name__ == "__main__":
    main()
