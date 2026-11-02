"""Freeze the n1-c life-103 07:02:47 loop-detected boards (summoner hold).

Source: C:/hengband-backups/pdca/captures/hourly-0700-1102/
n1-c-life-103-20261102-070247-loop-detected (bot-c116f37e1).  On 18F the
bot reached (2,30), saw a Crypt Creep (race 124) twenty cells west down the
corridor, chose the summoner choke hold, and the survival gate rewrote the
wait into ``no-wait:flee`` '6'; explore walked back '4' from (2,31) and the
pair alternated (decisions 6096-6131) until the loop detector stopped it.
Frozen: the ring boards of turns 1971629 (decision 6095, (2,31)), 1971637
(6096, (2,30)) and 1971646 (6097, (2,31)), their decision facts and the
last skill row before them.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-0700-1102/"
               "n1-c-life-103-20261102-070247-loop-detected")
RING = CAPTURE / "incident-captures" / "snapshots" / "snapshots-current.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "summoner-hold-los-1102.json.gz"
TURNS = (1971629, 1971637, 1971646)
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key", "position")


def main() -> None:
    rows = ring_rows(RING.read_bytes())
    boards = [next(row for row in rows if row["type"] == "player_turn" and row["turn"] == turn)
              for turn in TURNS]
    skill = [row for row in rows if row["type"] == "knowledge"
             and row["knowledge"]["category"] == "skill_exp" and row["turn"] <= TURNS[0]]
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("turn") in TURNS and row.get("reason") != "loop-detected":
                decisions.append({key: row[key] for key in DECISION_FACTS})
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in ("bot-decisions.jsonl.gz",
                              "incident-captures/snapshots/snapshots-current.jsonl.gz")},
        boards=boards, skill=skill[-1] if skill else None, decisions=decisions,
    )
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [d["reason"] for d in decisions])


if __name__ == "__main__":
    main()
