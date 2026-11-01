"""Freeze the 2026-11-01 20:08 n1-c life-098 Q2 reward board (#47 D62).

Source (copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/q2-reward-lamp-1101/): the snapshot ring
jsonlog/snapshots/snapshots-20261101-202425-3705dc.jsonl.gz (20:04-20:24)
and the decision log that starts at 20:07:04 (bot-decisions.jsonl.3 at copy
time, saved as bot-decisions-2007.jsonl).

Decision 2520 (turn 1283380, at (22,40) beside the Telmora castle) posted
``fixedquest:claim`` ``9q<ESC>``.  castle_quest set REWARDED and asked for the
town to be rebuilt; wilderness_gen placed object 582 (Feanorian lamp) on the
'!' cell (22,42) and set FINISHED, so the next board (turn 1283392) shows
Q2 status 4 and the lamp at distance 1.  Decisions 2521-2566 walked away
under me-staff:return-outpost and took the inn at (28,56) (``3ma``);
decision 2567 is in the Outpost.

Frozen: the skill_exp and Home knowledge rows the bot read before the claim,
the claim board (the last player_turn row at turn 1283380 before the claim
was posted), the first board after the report, and the compact facts of the
recorded decisions.  Only this tool reads the capture; the test reads the
fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/q2-reward-lamp-1101")
RING = CAPTURE / "snapshots-20261101-202425-3705dc.jsonl.gz"
DECISIONS = CAPTURE / "bot-decisions-2007.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "q2-reward-lamp-20261101.json.gz"
CLAIM_TURN, REPORTED_TURN = 1283380, 1283392
SEQUENCES = (2520, 2521, 2539, 2553, 2554, 2566, 2567)


def _rows():
    with gzip.open(RING, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn", 0) > REPORTED_TURN:
                return
            yield row


def _decision_facts():
    facts = {}
    with DECISIONS.open(encoding="utf-8") as stream:
        for line in stream:
            if '"decision_sequence": 25' not in line[:120]:
                continue
            row = json.loads(line)
            if row["decision_sequence"] in SEQUENCES and row["turn"] < 1290000:
                claim = row["claim"] or {}
                facts[row["decision_sequence"]] = dict(
                    turn=row["turn"], reason=row["reason"], key=row["key"],
                    rung=claim.get("rung"), owner=claim.get("owner"),
                    position=row["position"], loot=row["loot"],
                    inventory=row["inventory"])
    assert sorted(facts) == list(SEQUENCES), sorted(facts)
    return [facts[sequence] | dict(sequence=sequence) for sequence in SEQUENCES]


def main():
    knowledge, claim_board, reported = [], None, None
    for row in _rows():
        if row.get("type") == "knowledge" and row["turn"] >= 1282772:
            knowledge.append(row)
        if row.get("type") == "player_turn" and row["turn"] == CLAIM_TURN and claim_board is None:
            claim_board = row
        if row.get("type") == "player_turn" and row["turn"] == REPORTED_TURN:
            reported = row
    assert [row["knowledge"]["category"] for row in knowledge] == ["skill_exp", "home"]
    assert (claim_board["player"]["y"], claim_board["player"]["x"]) == (22, 40)
    assert reported["grid_map"]["found_items"] == [[22, 42, 1, 39]]
    case = dict(
        source="n1-c life-098 snapshots-20261101-202425-3705dc + decision log from 20:07:04",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RING, DECISIONS)},
        knowledge=knowledge, claim_board=claim_board, reported_board=reported,
        decisions=_decision_facts())
    OUTPUT.write_bytes(gzip.compress(json.dumps(case, ensure_ascii=False).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
