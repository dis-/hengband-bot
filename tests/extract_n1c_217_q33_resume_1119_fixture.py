"""Extract tests/fixtures/n1c-217-q33-resume-1119.json.gz (q33-resume-1119).

Source: C:/hengband-backups/pdca/captures (from ~/hengbot-soak/n1-c/life-217, Quest 33):

 * ``n1c-217-q33-lure-1119/20261119-224613-loop-detected/state.jsonl.gz``: the first board of the
   process restarted at 22:46 (turn 5087002, the player on [15,38], two ボーシン sensed), and
   ``bot-decisions.jsonl.gz``: its decisions until the loop detector's halt (runs of cell and reason).
 * The tracked races' kill lines the earlier processes read, from their decision logs
   (``n1c-217-q33-hold-1119/n1c-q33-decisions.jsonl.gz``: the three Its, 18:30;
   ``n1c-217-q33-loop2-1119/decisions.jsonl.gz``: the three Dagons and the three Bokrugs, 20:25-20:26),
   each board once: (kill line, game turn), every kill line (q2_kill_credit ``_killed``).

Run: PYTHONPATH=src python tests/extract_n1c_217_q33_resume_1119_fixture.py [CAPTURES]
"""
import gzip
import itertools
import json
import sys
from pathlib import Path

from hengbot.q2_kill_credit import _killed

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/captures")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-q33-resume-1119.json.gz"
HALT = ROOT / "n1c-217-q33-lure-1119" / "20261119-224613-loop-detected"
LOGS = (ROOT / "n1c-217-q33-hold-1119" / "n1c-q33-decisions.jsonl.gz",
        ROOT / "n1c-217-q33-loop2-1119" / "decisions.jsonl.gz")


def main():
    with gzip.open(HALT / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        board = next(json.loads(line) for line in stream if line.strip())
    with gzip.open(HALT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    rows = [row for row in rows if row.get("turn", 0) >= board["turn"]]
    runs = []
    for (cell, reason), group in itertools.groupby(
            rows, key=lambda row: ((row["position"]["y"], row["position"]["x"]), row["reason"])):
        group = list(group)
        runs.append(dict(time=group[0]["time"], cell=list(cell), reason=reason, decisions=len(group)))
    lines = []
    for log in LOGS:
        seen = set()
        with gzip.open(log, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                read = (row["turn"], tuple(row.get("messages") or ()))
                if read in seen or (row.get("floor") or {}).get("quest_id") != 33:
                    continue
                seen.add(read)
                lines.extend([message, row["turn"]] for message in row.get("messages") or ()
                             if _killed(message) is not None)
    case = dict(source="n1c-217-q33-resume-1119", board=board, runs=runs, earlier_lines=lines)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(OUTPUT, len(runs), len(lines))


if __name__ == "__main__":
    main()
