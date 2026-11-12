"""Freeze the boards of n1-c life-201's death (2026-11-12 16:56, floor (1, 30, 0)).

Source, read-only, the analysis folder C:/hengband-backups/pdca/captures/n1c-201-death-1112:

  20261112-165651-exit-no-marker/state.jsonl.gz          the player_turn boards of the last visit
                                                         (turns 1936499-1936907)
  20261112-165651-exit-no-marker/bot-decisions.jsonl.gz  the live decision rows of the same turns
                                                         (decisions 24233-24286)

One board per decision row: the last board of the row's game turn, its messages replaced by the
row's messages (the live process merges the messages of a board it did not decide on into the
next decision).  The rows keep sequence, turn, reason, key and the recorded threat_tiers' tier /
instant_death.  Only this tool reads the copies; the tests read the fixture.

    python tests/extract_teleport_follower_pack_1112_fixture.py <capture directory>
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "teleport-follower-pack-n1c-201-1112.json.xz"
STOP = "20261112-165651-exit-no-marker"


def main() -> None:
    capture = Path(sys.argv[1]) / STOP
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream) if row.get("type") == "player_turn"]
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    first = boards[0]["turn"]
    decided, decisions = [], []
    for row in rows:
        if row["turn"] < first:
            continue
        board = [raw for raw in boards if raw["turn"] == row["turn"]][-1]
        decided.append(dict(board, messages=row["messages"]))
        tiers = row.get("threat_tiers") or {}
        decisions.append({
            "sequence": row["decision_sequence"], "turn": row["turn"], "reason": row["reason"],
            "key": row["key"], "tier": tiers.get("tier"),
            "instant_death": tiers.get("instant_death"),
        })
    FIXTURE.write_bytes(lzma.compress(
        json.dumps({"boards": decided, "decisions": decisions}, ensure_ascii=False).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
