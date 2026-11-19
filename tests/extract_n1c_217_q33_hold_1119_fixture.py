"""Extract tests/fixtures/n1c-217-q33-hold-1119.json.gz (q33-post-disengage-hold-1119).

Source (C:/hengband-backups/pdca/captures/n1c-217-q33-hold-1119, from ~/hengbot-soak/n1-c/life-217,
build a39d54ce5, the first live Quest 33 run, 2026-11-19):

 * ``snapshots-20261119-185058-6186dd.jsonl.gz``: its first board (turn 4865466, 18:50), the player
   on [2,56] where he landed at 18:32:23 (decision 1056, quest-strategy:summoned-disengage-teleport
   :absorbed-power); the board is the one every hold read from 18:32:43 to the halt but its turn,
   clock and the monsters' cells.
 * ``n1c-q33-decisions.jsonl.gz``: decisions 1056-1120 (the teleport, the two ファゾルト shot, the
   holds), as (sequence, key, reason, position).

Run: python tests/extract_n1c_217_q33_hold_1119_fixture.py [ROOT]
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "C:/hengband-backups/pdca/captures/n1c-217-q33-hold-1119")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-q33-hold-1119.json.gz"


def main():
    with gzip.open(ROOT / "snapshots-20261119-185058-6186dd.jsonl.gz", "rt", encoding="utf-8") as stream:
        board = json.loads(stream.readline())
    decisions = []
    with gzip.open(ROOT / "n1c-q33-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if 1056 <= row["decision_sequence"] <= 1120:
                decisions.append(dict(sequence=row["decision_sequence"], key=row["key"],
                                      reason=row["reason"], position=row["position"]))
    case = dict(source="n1c-217-q33-hold-1119", board=board, decisions=decisions)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(OUTPUT, len(decisions))


if __name__ == "__main__":
    main()
