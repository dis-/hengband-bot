"""Freeze n1-c life-217's last Quest 25 boards (2026-11-19 05:24) for the blocked-execute test.

Source: n1-c life-217 (Magic-Eater Lv38, build bot-c9bb90888) on hengband.net, the loop-detected
stop captures/20261119-052415-loop-detected and incident-captures/20261119-052411-loop-detected
(its town-arrival checkpoint, ``incident/``) (every decision its state ring holds on the quest
floor, to the stop) and jsonlog/q25-battle.json as the process left it at 05:24:15 (turn
3582917, the tome's phase, ``phase`` 5), copied read-only to
C:/hengband-backups/pdca/n1c-217-q25-blocked-1119/ (``capture/`` and ``q25-battle.json``).

One board per recorded decision (the decisions of one turn take that turn's last rows in order)
with its decision row's messages and the recorded reason and key.  Only this extraction tool
reads the capture; the committed test reads the fixture alone.

    PYTHONPATH="src;tests;." python tests/extract_n1c_217_q25_tome_blocked_1119_fixture.py
"""

from __future__ import annotations

import gzip
import json
import pathlib
import pickle
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1b_378_q25_blocked_1113_fixture import QUEST, _decisions  # noqa: F401
import tests.extract_n1b_378_q25_blocked_1113_fixture as base

SOURCE = Path("C:/hengband-backups/pdca/n1c-217-q25-blocked-1119")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-q25-tome-blocked-1119.json.gz"


def main():
    base.ROOT = SOURCE
    boards, recorded, knowledge = base.process("capture", restarted=False)
    # The magic-eater lists the process held at its town arrival (05:10:33): the ring's boards do
    # not carry them.  The checkpoint was pickled on Linux; its runtime paths are PosixPath.
    pathlib.PosixPath = pathlib.WindowsPath if sys.platform == "win32" else pathlib.PosixPath
    with (SOURCE / "incident" / "town-arrival" / "policy.pkl").open("rb") as stream:
        state = pickle.load(stream)
    lists = {kind: [turn, list(rows)] for kind, (turn, rows) in state["_me_device_lists"].items()}
    # Its ~f skill reading (two-weapon, shield exp): the ring holds no knowledge row.
    two_weapon, shield = state["_skill_exp_cache"][:2]
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1c-217-q25-tome-blocked-1119",
                boards=boards, recorded=recorded, lists=lists, skill_exp=[two_weapon, shield],
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((SOURCE / "q25-battle.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
