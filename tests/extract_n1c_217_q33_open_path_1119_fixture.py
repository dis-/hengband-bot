"""Extract tests/fixtures/n1c-217-q33-open-path-1119.json.gz (q33-gachapin-wait-1119).

Source: C:/hengband-backups/pdca/captures/n1c-217-q33-lure3-1119 (from ~/hengbot-soak/n1-c/life-217,
Quest 33 段2 resumed with the walk-following reader, 2026-11-19 23:52, halted
quest:blocked:sweep-nothing-comes): ``*/state.jsonl.gz`` the boards of the process -- the first
(``board``: the player on [20,48], the Gachapins sensed at [21,59] [24,57] [23,56]) and the last
(``last``: the player on [26,41] after one Gachapin's kill line, another seen at [27,53]) --
and ``*/bot-decisions.jsonl.gz`` its Quest 33 decisions as runs of (time, cell, reason, decisions)
with each run's messages (``runs``).

Run: python tests/extract_n1c_217_q33_open_path_1119_fixture.py [ROOT]
"""
import gzip
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "C:/hengband-backups/pdca/captures/n1c-217-q33-lure3-1119")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-q33-open-path-1119.json.gz"


def main():
    halt = next(path for path in ROOT.iterdir() if path.is_dir())
    with gzip.open(halt / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream if line.strip()]
    board, last = boards[0], boards[-1]
    with gzip.open(halt / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    rows = [row for row in rows if (row.get("floor") or {}).get("quest_id") == 33]
    runs = []
    for (cell, reason), group in itertools.groupby(
            rows, key=lambda row: ((row["position"]["y"], row["position"]["x"]), row["reason"])):
        group = list(group)
        runs.append(dict(time=group[0]["time"], cell=list(cell), reason=reason, decisions=len(group),
                         messages=[message for row in group for message in row.get("messages") or ()]))
    runs = [run for run in runs if run["time"] >= "2026-11-19T23:52"]
    case = dict(source="n1c-217-q33-open-path-1119", board=board, last=last, runs=runs)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(OUTPUT, len(runs))


if __name__ == "__main__":
    main()
