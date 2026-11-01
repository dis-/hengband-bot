"""Freeze the D60 stuck:wander boards of 2026-11-01 (#47, n1c-stuck-wander-1101).

Source: the automatic livelock-exhausted capture of the viewing Magic-Eater
n1-c, life-098 (Lv21, 鉄獄12階 = Angband 12F, runtime RANDOM quest 43, build
bot-461b75b92), copied read-only to
C:/hengband-backups/pdca/captures/n1c-stuck-wander-1101/incident-captures/
20261101-200240-livelock-exhausted/.

The fixture keeps the two ring boards around the last breakthrough step
before the stop (turn 1188007, recorded decision 9118
``breeder-breakthrough:seek-upstairs`` '1', and turn 1188021, where that step
arrived), the recorded decision rows 9057-9120 (the 60 stuck decisions between
two breakthrough steps), the policy's remembered terrain at the capture
(policy-state.json ``terrain``), the last skill_exp knowledge row of the ring
and the monster knowledge of the quest target.  Only this extraction tool reads
the capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-stuck-wander-1101/incident-captures/"
               "20261101-200240-livelock-exhausted")
SKILL_RING = "snapshots-20261101-195013-837808.jsonl.gz"
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-stuck-wander-1101.json.gz"
MONRACES = Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")
TURNS = (1188007, 1188021)
SEQUENCES = range(9057, 9121)
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def boards():
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    found = {}
    for row in rows:
        if row["type"] == "player_turn" and row["turn"] in TURNS:
            found.setdefault(row["turn"], row)
    assert sorted(found) == list(TURNS), sorted(found)
    return [found[turn] for turn in TURNS]


def skill():
    rows = ring_rows(CAPTURE / "snapshots" / SKILL_RING)
    return next(row for row in reversed(rows) if row["type"] == "knowledge"
                and row["knowledge"]["category"] == "skill_exp")


def decisions():
    rows = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a bounded tail starts in the middle of a record
        if row.get("decision_sequence") in SEQUENCES and "reason" in row:
            rows.append({field: row.get(field) for field in DECISION_FIELDS})
    assert [row["decision_sequence"] for row in rows] == list(SEQUENCES)
    return rows


def main():
    frozen = boards()
    state = json.loads((CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    races = load_monrace_knowledge(MONRACES)
    ids = {quest["r_idx"] for quest in frozen[0]["progress"]["quests"] if quest.get("r_idx", 0) > 0}
    ids |= {row["race_id"] for board in frozen
            for field in ("visible_monsters", "detected_monsters")
            for row in board.get(field, [])}
    fixture = dict(
        source=f"{CAPTURE.name} (n1-c life-098, copied from the viewing server)",
        boards=frozen,
        decisions=decisions(),
        terrain=state["terrain"],
        terrain_turn=state.get("created_at"),
        skill=skill(),
        monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
    )
    with gzip.open(FIXTURE, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(FIXTURE, FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
