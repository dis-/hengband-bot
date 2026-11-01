"""Freeze the n1-b life-285 upstairs walk past moving mice (#47 D55 follow-up).

Source: the automatic player-death capture of the viewing bot n1-b, copied
read-only to C:/hengband-backups/pdca/captures/fix-deaths-1101/
(n1-b/life-285/incident-captures/20261101-005823-player-death, build
f9c921d32, 2026-11-01 00:58, Lv8 zombie warrior, Yeek cave 1F).

The fixture keeps every player board of the floor visit, from the arrival
board (turn 85511) to the first melee after the walk (turn 220640), the last
skill-proficiency and Home knowledge rows before the arrival, and the
recorded decision rows of the walk (turns 220409-220640, decisions
1115-1137).  The snapshot ring copy is the tail of a multi-member gzip
(``ring_rows`` keeps whole members only).  Only this extraction tool reads
the capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import knowledge, ring_rows

CAPTURE = Path(
    "C:/hengband-backups/pdca/captures/fix-deaths-1101/n1-b/life-285/"
    "incident-captures/20261101-005823-player-death"
)
OUTPUT = Path(__file__).with_name("fixtures") / "route-moving-blocker-n1b-285-1101.json.gz"
ARRIVAL_TURN, LAST_TURN = 85511, 220640
WALK_FIRST_TURN = 220409
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "player", "position")


def decision_rows(path: Path, turns: set[int]) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
        if row.get("turn") in turns and "reason" in row:
            rows.append({field: row.get(field) for field in DECISION_FIELDS})
    return rows


def main():
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    start = next(index for index, row in enumerate(rows)
                 if row["type"] == "player_turn" and row["turn"] == ARRIVAL_TURN)
    boards, turns = [], set()
    for row in rows[start:]:
        if row["type"] != "player_turn" or row["turn"] in turns:
            continue
        if row["turn"] > LAST_TURN:
            break
        turns.add(row["turn"])
        boards.append(row)
    assert boards[-1]["turn"] == LAST_TURN
    assert all(row["type"] == "player_turn" for row in rows[start:start + len(boards)])
    walk = {turn for turn in turns if turn >= WALK_FIRST_TURN}
    fixture = dict(
        source=f"{CAPTURE.relative_to(CAPTURE.parents[3]).as_posix()} "
               "(copied from the viewing server)",
        boards=boards,
        decisions=decision_rows(CAPTURE / "decision-tail.jsonl", walk),
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(fixture["decisions"]))


if __name__ == "__main__":
    main()
