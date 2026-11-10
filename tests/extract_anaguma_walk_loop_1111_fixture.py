"""Freeze the n1-b life-367 Anaguma walk loop of 2026-11-11 (tests/test_anaguma_walk_loop_1111_recorded.py).

Source: the viewing Magic-Eater n1-b life-367 (Lv 42), オークの洞窟23階 (floor (3, 23, 0)),
stopped with ``loop-detected`` at 00:03:38/00:03:40 and again at 00:03:47 and was retired:
``anaguma:walk`` from (34,124) toward the plan's start (33,123) alternated with ``seek-loot`` /
``explore`` / ``breakout:seek-frontier`` back from (33,123), among forest trolls (FRIENDS).
Copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-367-anaguma-loop-1111:

  CAPTURE/state.jsonl.gz          the 44 player-turn boards before the stop (turns 5800295-5800471)
  CAPTURE/bot-decisions.jsonl.gz  their decision rows
  INCIDENT/policy-state.json      the stop's policy summary (the absorption record, the plan)

The fixture keeps every board, the compact decision rows, the absorption record and the plan
the process held at the stop.  Only this extraction tool reads the copies; the committed test
reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/n1b-367-anaguma-loop-1111")
CAPTURE = ROOT / "captures" / "20261111-000340-loop-detected"
INCIDENT = ROOT / "incident-captures" / "20261111-000338-loop-detected"
OUTPUT = Path(__file__).with_name("fixtures") / "anaguma-walk-loop-20261111.json.gz"


def main():
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream) if row.get("type") == "player_turn"]
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn", 0) >= boards[0]["turn"]:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                                  "position": row.get("position")})
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))["state"]
    fixture = {
        "source": f"{CAPTURE.name} (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
        "absorbed": state["_me_staff_sequence"]["absorbed"],
        "stop_plan": state["_anaguma_plan"],
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
