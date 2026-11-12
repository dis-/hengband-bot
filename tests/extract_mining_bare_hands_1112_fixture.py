"""Freeze the 2026-11-12 n1-a life-518 bare-handed mining boards (D45, second scene).

Source: the viewing warrior n1-a life-518 (Lv8, Yeek cave 1F, mining for
funds), stopped by the loop guard at 18:04 and 18:05 and by the navigation
livelock at 18:06 (incident captures 20261112-180456-loop-detected,
20261112-180513-loop-detected, 20261112-180608-livelock-exhausted).  Read:

  <state.jsonl>        the life directory's state log (sha256 c2bac022...),
                       copied read-only from the viewing server's
                       ~/hengbot-soak/n1-a/life-518/state.jsonl
  <decision-tail>      20261112-180608-livelock-exhausted/decision-tail.jsonl
                       (decision rows of game turns 127068-156598)

'ta' (fundraise:wield-digging-tool) took off the Broad Sword at 139869; a
breeding white worm mass (race 31) came into view three cells away at
139876 and the flee rung answered (free damage 0 with the hand empty: T1),
two Teleportation scrolls followed, and the return walked bare-handed from
139938 on (fundraise:seek-upstairs-explore, no hostile in view).  From
156220 to the stop at 156613 the flee rung waited (flee:wait) seven cells
from a grey mold (race 20, NEVER_MOVE) that cannot reach the player.

Frozen: the boards of turns 139869 (sword worn, nothing in view), 139876
(hand empty, the worm mass three cells away), 139938 (hand empty, nothing in
view, the return walking) and 156598 (hand empty, the grey mold seven cells
away), the latest skill-proficiency knowledge row before 139869, the recorded
decision rows of those turns, and the race knowledge of races 31 and 20
(lib/edit/MonraceDefinitions.jsonc; run with PYTHONPATH=src from
C:/hengband).  Only this extraction tool reads the capture; the committed
test reads the frozen fixture alone.

    python tests/extract_mining_bare_hands_1112_fixture.py <state.jsonl> <decision-tail.jsonl>
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


OUTPUT = Path(__file__).with_name("fixtures") / "mining-bare-hands-20261112.json.gz"
BOARDS = {"worn": 139869, "sighted": 139876, "returning": 139938, "mold": 156598}
WORM_MASS, GREY_MOLD = 31, 20
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "rung", "player",
                   "floor", "position", "mining", "fundraising", "threat_prediction")


def main():
    state, tail = Path(sys.argv[1]), Path(sys.argv[2])
    boards, skill = {}, None
    with state.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if (row.get("type") == "knowledge" and row["knowledge"]["category"] == "skill_exp"
                    and row["turn"] <= BOARDS["worn"]):
                skill = row
            if row.get("type") == "player_turn" and row["turn"] in BOARDS.values():
                # The last board of a game turn is the one the live process decided on.
                boards[next(name for name, turn in BOARDS.items() if turn == row["turn"])] = row
    assert set(boards) == set(BOARDS) and skill is not None
    hands = ("main_hand", "sub_hand")
    assert [item["slot"] for item in boards["worn"]["equipment"]].count("main_hand") == 1
    assert not boards["worn"]["visible_monsters"] and not boards["returning"]["visible_monsters"]
    for name in ("sighted", "returning", "mold"):
        assert not any(item["slot"] in hands for item in boards[name]["equipment"])
    assert {m["race_id"] for m in boards["sighted"]["visible_monsters"]} == {WORM_MASS}
    assert {m["race_id"] for m in boards["mold"]["visible_monsters"]} == {GREY_MOLD}
    decisions = {}
    with tail.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # the tail's first line is cut by the capture's size cap
            if row.get("turn") in BOARDS.values():
                decisions.setdefault(str(row["turn"]), []).append(
                    {k: row.get(k) for k in DECISION_FIELDS})
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    case = dict(
        source="n1-a life-518 state.jsonl and the 18:06 livelock capture's decision tail",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (state, tail)},
        boards=boards,
        knowledge=skill,
        decisions=decisions,
        monraces={str(race): asdict(races[race]) for race in (WORM_MASS, GREY_MOLD)},
    )
    OUTPUT.parent.mkdir(exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
