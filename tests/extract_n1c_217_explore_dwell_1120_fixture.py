"""Extract tests/fixtures/n1c-217-explore-dwell-1120.jsonl.xz (tests/test_n1c_217_explore_dwell_1120_recorded.py).

Source: n1-c life-217 (Magic-Eater Lv50, Angband 95F, build bot-80276283e), stopped by the
server's floor-dwell watcher at 2026-11-20 19:34:04 with ``stall:floor-dwell:explore``.
Copied read-only to C:/hengband-backups/pdca/captures/n1c-217-20261120-193401-stall-floor-dwell-explore/:

  captures/20261120-193401-stall-floor-dwell-explore/state.jsonl.gz
      the last 44 boards before the stop (turns 6579210-6579327, one power_list row among them)
  captures/20261120-193401-stall-floor-dwell-explore/bot-decisions.jsonl.gz
      the last 224 decision rows (turns 6578700-6579324)

Rows: ``{"role": "board", "board": <recorded board>}`` for each player_turn board, and
``{"role": "decision", ...}`` for each decision row, compact (turn, reason, key, position, the
known map's size ``known``, the loot owner's ``loot`` record).  Only this tool reads the capture;
the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-217-20261120-193401-stall-floor-dwell-explore/"
               "captures/20261120-193401-stall-floor-dwell-explore")
TARGET = Path(__file__).with_name("fixtures") / "n1c-217-explore-dwell-1120.jsonl.xz"


def main() -> None:
    rows = []
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                board = json.loads(line)
                if board.get("type") == "player_turn":
                    rows.append({"role": "board", "board": board})
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append({"role": "decision", "turn": row["turn"], "reason": row["reason"],
                         "key": row["key"], "position": row["position"],
                         "known": row["map_memory"]["known_cells"]["known"],
                         "loot": row["loot"]})
    with lzma.open(TARGET, "wt", encoding="utf-8", preset=9 | lzma.PRESET_EXTREME) as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
