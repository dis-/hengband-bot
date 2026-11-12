"""Freeze the n1-b life-377 approach / seek-loot loop of 2026-11-12 11:24.

Source (copied read-only from the viewing server's ~/hengbot-soak/n1-b/life-377/ to
C:/hengband-backups/pdca/captures/n1b-377-approach-loot-1112):

  20261112-112425-loop-detected/state.jsonl.gz          the boards before the stop
  20261112-112425-loop-detected/bot-decisions.jsonl.gz  their decision rows

Kept: the player-turn boards from the arrival on Angband 80F (turn 9031291) to the stop and
the compact decision rows (turn, key, reason, position) of the same span.

    python tests/extract_n1b_377_approach_loot_1112_fixture.py
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-377-approach-loot-1112"
               "/20261112-112425-loop-detected")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-377-approach-loot-1112.json.gz"
ARRIVAL = 9031291


def main():
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream)
                  if row.get("type") == "player_turn" and row["turn"] >= ARRIVAL]
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "decision_sequence" in row and row.get("turn", 0) >= ARRIVAL:
                decisions.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                                  "key": row["key"], "reason": row["reason"],
                                  "position": row.get("position")})
    fixture = {"source": f"{CAPTURE.name} (copied from the viewing server)",
               "boards": boards, "decisions": decisions}
    OUTPUT.write_bytes(gzip.compress(json.dumps(fixture, ensure_ascii=False, sort_keys=True)
                                     .encode("utf-8"), mtime=0))
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
