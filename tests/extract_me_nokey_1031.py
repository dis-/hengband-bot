"""Freeze the 2026-10-31 n1-c no-key-exhausted stops of the Magic-Eater (#47).

Source: the viewing zombie Magic-Eater n1-c, copied to
C:/hengband-backups/pdca/captures/latest-12h-1031/n1-c/ (the diagnosis
LUNA-DIAG-nokey.txt names the cases):

  staff     life-054 20261031-061452-no-key-exhausted (build b6d47db93): the
            state ring rows 104-114 (outside the Magic shop, its page, the
            boards after leaving it, the Home visit and its knowledge row) and
            the last skill-proficiency row (83).  The bot stopped at 114 with
            quest:blocked:me-staff (fundraise-target-drift:staff-stockout)
            carrying four of stage 2's five staffs; Detect Evil was not on the
            Magic shop's shelf.
  equipment life-054 20261031-072115-no-key-exhausted (same build): the first
            ring board (turn 2418523) and its decision row, whose
            equipment_optimization names the in-flight Home session the staff
            sequence would not yield to (82 x shop:approach '5').
  opening   life-058 20261031-084721-no-key-exhausted (build ba0d425a9): ring
            rows 207-222, the skill-proficiency (181) and Home (192) rows, and
            the decision row of the stop (222, quest:blocked:opening-route
            stop:unaffordable-quest-reserve).

The staff sequence record is not in these captures; RECORDED_SEQUENCE is the
``_me_staff_sequence`` of the server incident capture 20261031-061450 (life
054, policy-state.json, read by the diagnosis), with only the fields the
tests use.  Only this extraction tool reads the captures; the committed test
reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/latest-12h-1031/n1-c")
STAFF = ROOT / "life-054/captures/20261031-061452-no-key-exhausted"
EQUIPMENT = ROOT / "life-054/captures/20261031-072115-no-key-exhausted"
OPENING = ROOT / "life-058/captures/20261031-084721-no-key-exhausted"
OUTPUT = Path(__file__).with_name("fixtures") / "me-nokey-20261031.json.gz"
RECORDED_SEQUENCE = {
    "absorbed": {"5": 21, "10": 19},
    "bought": [5, 8, 9, 10, 12, 13],
    "completed_stages": {"1": 1279501},
    "fundraise_runs": 6,
    "reached_runs": 6,
    "fundraise_why": "staff-stockout",
    "shelf_after_turn": 1571983,
    "stage": 2,
    "failure": "fundraise-target-drift:staff-stockout:2530",
}
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position", "player",
                   "equipment_optimization", "fixedquest_readiness")


def rows(path: Path, name: str) -> list[dict]:
    with gzip.open(path / name, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def decision(path: Path, turn: int, reason: str | None = None) -> dict:
    found = [row for row in rows(path, "bot-decisions.jsonl.gz") if row.get("turn") == turn
             and (reason is None or row.get("reason") == reason)]
    return {key: found[-1].get(key) for key in DECISION_FIELDS}


def main():
    staff = rows(STAFF, "state.jsonl.gz")
    equipment = rows(EQUIPMENT, "state.jsonl.gz")
    opening = rows(OPENING, "state.jsonl.gz")
    assert staff[83]["knowledge"]["category"] == "skill_exp"
    assert [row.get("store", {}).get("store_type") if row["type"] == "store" else None
            for row in staff[104:109]] == [None, 5, 5, 5, None]
    assert opening[181]["knowledge"]["category"] == "skill_exp"
    assert opening[192]["knowledge"]["category"] == "home"
    assert equipment[0]["turn"] == 2418523
    case = dict(
        source="n1-c life-054 (build b6d47db93) and life-058 (build ba0d425a9) captures",
        sources={f"{path.parent.parent.name}/{path.name}/{name}": hashlib.sha256(
            (path / name).read_bytes()).hexdigest()
            for path in (STAFF, EQUIPMENT, OPENING)
            for name in ("state.jsonl.gz", "bot-decisions.jsonl.gz")},
        recorded_sequence=RECORDED_SEQUENCE,
        staff=dict(skill=staff[83], boards=staff[104:115],
                   stop=decision(STAFF, staff[114]["turn"], "quest:blocked:me-staff")),
        equipment=dict(board=equipment[0], decision=decision(EQUIPMENT, equipment[0]["turn"]),
                       stop=decision(EQUIPMENT, equipment[-1]["turn"], "quest:blocked:me-staff")),
        opening=dict(skill=opening[181], home=opening[192],
                     boards=[row for row in opening[207:223] if row["type"] != "knowledge"],
                     stop=decision(OPENING, opening[222]["turn"], "quest:blocked:opening-route")),
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
