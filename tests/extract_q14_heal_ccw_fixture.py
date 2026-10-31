"""Freeze the 2026-10-31 n1-c life-072 town board that refused Q14 (Warg problem).

Source: read-only copies from the viewing zombie Magic-Eater n1-c (Lv18) in
C:/hengband-backups/pdca/captures/q14-heal-1031/n1-c/life-072/ (README.txt
there names the server files):

  town-1375149-raw.json   the snapshot-ring boards of turn 1375149 (the Outpost
                          after the town visit), the last skill_exp and Home
                          knowledge rows of that visit, and decisions
                          10351-10376 of bot-decisions.jsonl.
  policy-state-20261031-2323.json
                          the diagnostic checkpoint whose ``_me_staff_sequence``
                          is the staff-sequence record (stage 3, nothing left).

Decision 10375 chose ``town:recall-to-alt-dungeon`` with fixedquest_readiness
quest 14 ``strategy-force`` failed ["heal_potions"] measured 1 required 2:
the board carries ten Potions of Cure Critical Wounds and one Potion of
Healing, and only Healing counted.

Only this extraction tool reads the copies; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


LIFE = Path("C:/hengband-backups/pdca/captures/q14-heal-1031/n1-c/life-072")
RAW = LIFE / "town-1375149-raw.json"
STATE = LIFE / "policy-state-20261031-2323.json"
OUTPUT = Path(__file__).with_name("fixtures") / "q14-heal-ccw-20261031.json.gz"
BOARD_TURN = 1375149
DECISION = 10375
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "objective",
                   "fixedquest_readiness")


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    board = raw["boards"][-1]
    assert (board["turn"], board["type"]) == (BOARD_TURN, "player_turn")
    decision = next(row for row in raw["decisions"]
                    if row["decision_sequence"] == DECISION)
    assert decision["reason"] == "town:recall-to-alt-dungeon", decision["reason"]
    sequence = json.loads(STATE.read_text(encoding="utf-8"))["state"]["_me_staff_sequence"]
    assert sequence["stage"] == 3 and sequence["remaining"] == [], sequence
    case = dict(
        source="n1-c life-072 (2026-10-31 23:13, town after the visit of decisions 10351-10375)",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RAW, STATE)},
        board=board,
        skill=raw["knowledge"]["skill_exp"],
        home=raw["knowledge"]["home"],
        decision={key: decision[key] for key in DECISION_FIELDS},
        staff_sequence={key: sequence[key] for key in ("absorbed", "stage", "powers_read")},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, board["turn"], OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
