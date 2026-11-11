"""Freeze the n1-c life-195 short-blind / reverse-choke loop of 2026-11-11 (tests/test_n1c_195_short_blind_1111_recorded.py).

Source: the viewing Magic-Eater n1-c life-195 (Lv 37 zombie), オークの洞窟23階 (floor (3, 23, 0)),
stopped with ``loop-detected`` at 17:26:09 among light hounds (ライト・ハウンド, BR_LITE).
Copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-195-short-blind-1111:

  incident/20261111-172609-loop-detected/snapshots/   the ring generations (the boards)
  incident/20261111-172609-loop-detected/policy-state.json   the remembered terrain, the absorption record
  bot-decisions.jsonl.gz                              the decision rows

The fixture keeps the player-turn boards of turns 4268823-4269495 (decisions 20340-20441), the
compact decision rows, the last skill-exp knowledge row before them, the absorption record,
the remembered terrain and the monster races on the boards.  Only this extraction tool reads
the copies; the committed test reads the fixture.
"""

from __future__ import annotations

from dataclasses import asdict
import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-195-short-blind-1111")
INCIDENT = ROOT / "incident" / "20261111-172609-loop-detected"
RINGS = ("snapshots-20261111-172603-5283d3.jsonl.gz", "snapshots-current.jsonl.gz")
FIRST, LAST = 4268823, 4269495
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-195-short-blind-1111.json.gz"


def main():
    rows = [row for ring in RINGS for row in ring_rows(INCIDENT / "snapshots" / ring)]
    boards, turns, skill = [], set(), None
    for row in rows:
        if row.get("type") == "knowledge" and row["knowledge"]["category"] == "skill_exp":
            if row["turn"] <= FIRST:
                skill = row
        if (row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST
                and row["turn"] not in turns):
            turns.add(row["turn"])
            boards.append(row)
    assert {FIRST, LAST} <= turns
    if skill is None:
        earlier = ring_rows(INCIDENT / "snapshots" / "snapshots-20261111-171910-f98bf4.jsonl.gz")
        skill = [row for row in earlier if row.get("type") == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp"][-1]
    decisions = []
    with gzip.open(ROOT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if FIRST <= row.get("turn", 0) <= LAST:
                decisions.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                                  "reason": row["reason"], "key": row["key"],
                                  "position": row.get("position")})
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for row in board.get(field, [])}
    fixture = {
        "source": f"{INCIDENT.name} (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
        "skill": skill,
        "absorbed": state["state"]["_me_staff_sequence"]["absorbed"],
        "terrain": state["terrain"],
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT.name, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main()
