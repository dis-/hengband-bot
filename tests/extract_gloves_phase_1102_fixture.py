"""Freeze the n1-a life-464 07:12 Home boards (Dragon Gloves {r呪} destroyed).

Source: C:/hengband-backups/pdca/captures/hourly-0800-1102/
20261102-071240-town-blocked-survival-cure-critical-ready (bot-e8f860713).
The full-Home relief chose ドラゴン・グローブ [4,+8] {r呪} (31,3) as
plain gear on the Home page (decision 2292, home:junk-sweep-withdraw), took it
(2293, home-errand:atomic-withdraw:full-home-discard) and destroyed it (2294,
home:junk-sweep:plain-gear).  Frozen: state rows 63-79 (the town walk, the
first Home page, its ~9 answer, the second Home page and the 2293 outside
board) and the recorded facts of decisions 2287-2294.  Only this tool reads
the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-0800-1102/"
               "20261102-071240-town-blocked-survival-cure-critical-ready")
OUTPUT = Path(__file__).with_name("fixtures") / "gloves-phase-1102.json.gz"
ROWS = range(63, 80)
DECISIONS = range(2287, 2295)
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key")


def main() -> None:
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("decision_sequence") in DECISIONS:
                decisions.append({key: row[key] for key in DECISION_FACTS})
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in ("state.jsonl.gz", "bot-decisions.jsonl.gz")},
        rows=[lines[index] for index in ROWS], decisions=decisions,
    )
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [d["reason"] for d in decisions])


if __name__ == "__main__":
    main()
