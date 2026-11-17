"""Freeze the boards of the 50F+ efficiency decisions of 2026-11-17 (tests/test_deep_efficiency_1117_recorded.py).

Source: the viewing server's snapshot logs (``jsonlog/snapshots/*.jsonl.gz``, one player-turn board a
line), cut read-only by C:/hengband-backups/pdca/deep-efficiency-1117/impl_extract*.py and copied to
C:/hengband-backups/pdca/captures/deep-efficiency-1117:

  deadend-up.jsonl       n1-c life-216, Angband 80F (1, 80, 0): the last 40 boards of the visit that
                         ended by the up stairs (turns 5555571-5555864), explore walks
  dl-5162719.jsonl       n1-b life-411, Castle 64F (12, 64, 0): the sensed-T1 approach and the use of
                         *Destruction* at turn 5162719 (turns 5162560-5162727)
  recall-wait.jsonl      n1-c life-216, Glass castle 55F: a Word of Recall read at turn 5663857 and
                         its countdown (turns 5663846-...)
  floor-identify.jsonl   n1-c life-216, Glass castle 49F, 15:43:34: seek-loot, pickup 'g',
                         identify:dungeon-equipment 'mAfo' and the auto-destroy of the 戦闘用つるはし
                         (turns 5629041-5629130)

The fixtures keep the tail each test replays.  Only this extraction tool reads the copies.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/deep-efficiency-1117")
FIXTURES = Path(__file__).with_name("fixtures")
CUTS = {
    "deadend-up.jsonl": ("deep-efficiency-1117-explored-floor.jsonl.gz", 5555750, 5555864),
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
