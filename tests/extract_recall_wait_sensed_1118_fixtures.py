"""Freeze the recall-wait boards of the owner decision of 2026-11-18 (tests/test_recall_wait_sensed_1118_recorded.py).

Source: the viewing server's snapshot logs of n1-c life-216 (``jsonlog/snapshots/*.jsonl.gz``, one
player-turn board a line), cut read-only by C:/hengband-backups/pdca/captures/recall-wait-sensed-1118/cut.py
and copied to that folder:

  n1c-216-80F-6224305.jsonl  Angband 80F: Word of Recall read after the board of turn 6224305; the whole
                             countdown (turns 6224308-6224345) stood still with no hostile in view, one
                             hostile known only by telepathy, full HP and found items 4 cells away
  n1c-216-60F-6108483.jsonl  60F: Word of Recall read after the board of turn 6108483; the countdown
                             (6108486-) with three hostiles in view and items 4 cells away

The fixtures keep the tail each test replays.  Only this extraction tool reads the copies.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/recall-wait-sensed-1118")
FIXTURES = Path(__file__).with_name("fixtures")
CUTS = {
    "n1c-216-80F-6224305.jsonl": ("recall-wait-sensed-1118-detected.jsonl.gz", 6224266, 6224345),
    "n1c-216-60F-6108483.jsonl": ("recall-wait-sensed-1118-visible.jsonl.gz", 6108441, 6108500),
}


def main():
    for source, (target, first, last) in CUTS.items():
        rows = [line for line in (ROOT / source).read_text(encoding="utf-8").splitlines()
                if line.strip() and first <= json.loads(line)["turn"] <= last]
        with gzip.open(FIXTURES / target, "wt", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(rows) + "\n")
        print(target, len(rows))


if __name__ == "__main__":
    main()
