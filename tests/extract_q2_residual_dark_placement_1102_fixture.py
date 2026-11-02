"""Freeze the n1-b life-295 Q2 residual-sweep stall boards of 2026-11-02.

Source: the viewing warrior n1-b life-295 (Lv22, 430 max HP, build
bot-9afd9203e), 鉄獄15階 fixed quest 2, stopped at 18:10:28 with
``stall:floor-dwell:quest-strategy:q#-residual-#-sweep``.  Copied read-only to
C:/hengband-backups/pdca/captures/hourly-1800-1102/<stamp>/:

  state.jsonl.gz      the last 15 boards before the stop (turns 782791-782947),
                      the player walking (1,5)-(3,7)-(1,1)-(1,5)-(2,6)-(3,7)
  bot-decisions.jsonl.gz  the decision rows of the same boards
  skill-exp-knowledge-638621.json  the life's last level-22 ~f row (from the
                      server's ring generation snapshots-20261102-175909)

The fixture keeps the boards, that skill row and the compact decision rows
(turn, reason, key).  Only this extraction tool reads the captures; the
committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


CAPTURE = Path(
    "C:/hengband-backups/pdca/captures/hourly-1800-1102/"
    "20261102-181028-stall-floor-dwell-quest-strategy-q-residual-sweep"
)
OUTPUT = Path(__file__).with_name("fixtures") / "q2-residual-dark-placement-20261102.json.gz"


def main():
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream]
    turns = {board["turn"] for board in boards}
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["turn"] in turns:
                decisions.append(
                    {"turn": row["turn"], "reason": row["reason"], "key": row["key"]}
                )
    # The last board is the one the stall detector stopped on (no decision).
    assert {row["turn"] for row in decisions} == turns - {boards[-1]["turn"]}
    fixture = {
        "source": f"{CAPTURE} (copied from the viewing server)",
        "boards": boards,
        "skill": json.loads(
            (CAPTURE / "skill-exp-knowledge-638621.json").read_text(encoding="utf-8")
        ),
        "decisions": decisions,
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
