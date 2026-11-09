"""Freeze the boards of the three n1-b deaths of 2026-11-08/09 (owner decisions A-E of 11-09).

Sources, copied read-only from the viewing server (n1-b's life directories) and from the analysis
folder C:/hengband-backups/pdca/captures/deaths-1109 (REPORT.txt):

  <life>/state.jsonl                       the player_turn boards of the window below
  <life>/incident-captures/*-player-death/decision-tail-80.jsonl.gz
                                           the live decision rows of the same window
  <life>/incident-captures/*-player-death/town-arrival/policy.pkl
                                           the absorbed device lists the game last displayed
                                           (``_me_device_lists``: kind -> (turn, rows)), read
                                           on the viewing server with the bot's own venv into
                                           <me-lists.json> ({life: {kind: [turn, rows]}})

  life-355  Angband 80F, Chiron locusts' brain smash      turns 4229810-4230087 (town wait, 80F)
  life-350  Labyrinth 15F, Umber hulk's confusing gaze   turns 969800-970284
  life-346  Angband 19F, Chthonian paralysis              turns 1623690-1623973

One board per decision row: the last board of the row's game turn (a second board of the same
turn is the one the live process decided on), its messages replaced by the row's messages (the
live process merges the messages of a board it did not decide on into the next decision:
life-350's 970243 into 970252).  The rows keep sequence, turn, reason, key and the recorded
threat_tiers' tier / instant_death.  Only this tool reads the copies; the tests read the fixture.

    python tests/extract_deaths_1109_fixture.py <boards-dir> <captures-dir> <me-lists.json>

<boards-dir> holds life-355-boards.jsonl.gz etc. (the window's player_turn rows of state.jsonl,
one JSON line each, after one header line).
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "deaths-1109.json.xz"
LIVES = {
    "life-355": "20261109-042934-player-death",
    "life-350": "20261108-204544-player-death",
    "life-346": "20261108-120646-player-death",
}


def main() -> None:
    boards_dir, captures = Path(sys.argv[1]), Path(sys.argv[2])
    lists = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    payload = {}
    for life, incident in LIVES.items():
        with gzip.open(boards_dir / f"{life}-boards.jsonl.gz", "rt", encoding="utf-8") as stream:
            boards = [json.loads(line) for line in stream][1:]
        rows_path = captures / life / "incident-captures" / incident / "decision-tail-80.jsonl.gz"
        with gzip.open(rows_path, "rt", encoding="utf-8") as stream:
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
        payload[life] = {"boards": decided, "decisions": decisions, "lists": lists[life]}
    FIXTURE.write_bytes(lzma.compress(
        json.dumps(payload, ensure_ascii=False).encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
