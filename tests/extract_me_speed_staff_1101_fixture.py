"""Freeze the life-085 Black Market Speed-potion purchase (#47, owner 2026-11-01).

Source: the n1-c player-death capture of life-085 (Lv18 zombie Magic-Eater,
build c326f0fd6), copied read-only to
C:/hengband-backups/pdca/captures/viewing-incidents-20261101/n1-c/life-085/
incident-captures/20261101-092407-player-death.  At turn 1444679 (decision
9047, 09:23:55) the Q2 strategy force asked two Potions of Speed
(``fixedquest_readiness.strategy_force.speed_potions`` measured 0, required 2)
and the bot bought them in the Black Market: ``shop:in-store-buy`` ``pg2``.
The same life had absorbed the Staff of Speed (the 08:50 departure capture's
``_me_staff_sequence.absorbed`` holds ``staff:22``: 8).

The fixture keeps the ring rows of that turn (the player board before the
shelf and the three shelf boards), the last skill-proficiency and Home
knowledge rows before them, the death capture's ``_me_staff_sequence`` and
the recorded decision rows of the turn.  Only this tool reads the capture;
the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/viewing-incidents-20261101/n1-c/life-085/"
               "incident-captures/20261101-092407-player-death")
OUTPUT = Path(__file__).with_name("fixtures") / "me-speed-staff-life085-1101.json.gz"
TURN = 1444679
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "shop_selector",
                   "fixedquest_readiness", "quest_strategy")


def decision_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
        if row.get("turn") == TURN and "reason" in row:
            rows.append({field: row.get(field) for field in DECISION_FIELDS})
    return rows


def main():
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    start = next(index for index, row in enumerate(rows) if row.get("turn") == TURN)
    boards = [row for row in rows if row.get("turn") == TURN]
    assert [row["type"] for row in boards] == ["player_turn", "store", "store", "store"]
    state = json.loads((CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    fixture = dict(
        source=f"{CAPTURE.name} of n1-c life-085 (copied from the viewing server)",
        boards=boards,
        decisions=decision_rows(CAPTURE / "decision-tail.jsonl"),
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state["state"].get("_me_staff_sequence"),
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
