"""Quest 25 『幽霊屋敷』 CONSTRUCTED boards and policy helpers.

Moved verbatim out of tests/test_q25_haunted_house.py (maintainability review
1109, 段3), which re-exports every name.  See that module's note for what is
recorded and what is DECLARED CONSTRUCTED: the boards are the recorded n1-c
Q31 board of tests/fixtures/once-quest-recall-20261103.json.gz with its floor,
grid map, quest row, position, HP, monsters and carried potions and scrolls
replaced (the grid map from lib/edit/quests/025_HauntedHouse.jsonc, every cell
known; the real MonraceDefinitions).

Other recorded/constructed Q25 tests import this module rather than the test
module, so they do not depend on its test classes.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import (
    SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, SV_POTION_SPEED,
    TVAL_POTION, TVAL_SCROLL, parse_snapshot, _GRID_TERRAIN_NAMES,
)
from hengbot.monrace_knowledge import _strip_jsonc, find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_room_sweep import LIGHT_REASON, TELEPORT_REASON, WALK_REASON  # noqa: F401 -- for importers
from hengbot.quest_strategies import load_quest_strategies

ROOT = Path(__file__).parents[2]
GAME = Path("C:/hengband/lib/edit")
with gzip.open(ROOT / "tests" / "fixtures" / "once-quest-recall-20261103.json.gz", "rt",
               encoding="utf-8") as _stream:
    _CASE = json.load(_stream)
BASE = _CASE["boards"][0]
QUEST = json.loads(_strip_jsonc((GAME / "quests" / "025_HauntedHouse.jsonc").read_text(encoding="utf-8")))
BASE_LEGEND = json.loads(_strip_jsonc((GAME / "QuestPreferences.jsonc").read_text(encoding="utf-8")))["legend"]
TERRAINS = {row["key"]: row for row in json.loads(_strip_jsonc(
    (GAME / "TerrainDefinitions.jsonc").read_text(encoding="utf-8")))["terrains"]}
RACES = load_monrace_knowledge(find_monrace_definitions(ROOT, None) or GAME / "MonraceDefinitions.jsonc")
QUESTS = load_quest_knowledge(find_quest_definitions(ROOT) or GAME / "quests")
FILE_STRATEGIES = load_quest_strategies(ROOT / "strategy" / "quests")
STRATEGIES = FILE_STRATEGIES
PLAN = STRATEGIES[25].engagement_plan["room_sweep"]
START = (13, 1)
TYRANNOSAUR, DREADMASTER, VAMPIRE, DRUJ, TOME, HOUND, IPSISSIMUS, SHADOW, SPECTRE, SKELETAL_T, QUYL, STAIR, MASS = (
    705, 690, 623, 748, 557, 739, 571, 665, 508, 466, 480, 439, 202)
SV_PHASE, SV_TELEPORT, SV_RECALL, SV_LIGHT = 8, 9, 11, 24
FULL_HP = 800
DIRECTION = {(-1, -1): "7", (-1, 0): "8", (-1, 1): "9", (0, -1): "4", (0, 1): "6",
             (1, -1): "1", (1, 0): "2", (1, 1): "3"}
LAST_STOP = len(PLAN["stands"])
QUYL_STOP = LAST_STOP + 1
DRUJ_STOP = LAST_STOP + 3


def _terrain_key(glyph: str) -> str:
    entry = QUEST["legend"].get(glyph) or BASE_LEGEND[glyph]
    return entry["terrain"]


def _palette_row(terrain_key: str) -> list[int]:
    row = TERRAINS[terrain_key]
    flags = {flag.lower() for flag in row["flags"]}
    if "DOOR" in terrain_key:  # the emitter's own bit: a terrain tag, not a flag
        flags.add("door")
    bits = sum(1 << index for index, name in enumerate(_GRID_TERRAIN_NAMES) if name in flags)
    return [row["id"], 2, bits, 1]


def _grid_map() -> dict:
    keys = sorted({_terrain_key(glyph) for line in QUEST["map"] for glyph in line} | {"OPEN_DOOR"})
    return {
        "cells": [], "found_item_ids": [], "found_item_names": [], "found_items": [],
        "h": len(QUEST["map"]), "w": len(QUEST["map"][0]),
        "palette": [_palette_row(key) for key in keys],
        "runs": [[y, x, 1, keys.index(_terrain_key(glyph))]
                 for y, line in enumerate(QUEST["map"]) for x, glyph in enumerate(line)],
        "unsafe_rows": [],
    }


def open_door(raw, cell):
    index = raw["grid_map"]["palette"].index(_palette_row("OPEN_DOOR"))
    for run in raw["grid_map"]["runs"]:
        if (run[0], run[1]) == cell:
            run[3] = index


def monster(race, y, x, *, index=None, asleep=False):
    return {"asleep": asleep, "confused": False, "fast": False, "fearful": False,
            "friendly": False, "health": "unhurt", "index": index or race, "invulnerable": False,
            "level": RACES[race].level, "name": f"race{race}", "pet": False, "race_id": race,
            "slow": False, "stunned": False, "x": x, "y": y}


def _stack(tval, sval, count):
    row = next(item for item in BASE["inventory"] if item["tval"] == tval)
    return dict(copy.deepcopy(row), sval=sval, count=count, name=f"item{tval}-{sval}")


def board(position=START, *, hp=FULL_HP, monsters=(), healing=5, speed=3, teleports=15, recall=3, ccw=0, light=2,
          recalling=False, max_hp=FULL_HP, status=1):
    """DECLARED CONSTRUCTED, see the module note."""
    raw = copy.deepcopy(BASE)
    raw["floor"].update(quest_id=25, level=1, height=len(QUEST["map"]), width=len(QUEST["map"][0]))
    raw["grid_map"] = _grid_map()
    raw["progress"]["quests"] = [
        {"fixed": True, "id": 25, "level": 48, "name": "haunted house", "status": status, "type": 6},
        *[row for row in raw["progress"]["quests"] if row["id"] not in {25, 31}],
    ]
    raw["player"].update(y=position[0], x=position[1], hp=hp, max_hp=max_hp, recalling=recalling)
    kept = [item for item in raw["inventory"] if item["tval"] not in {TVAL_POTION, TVAL_SCROLL}]
    raw["inventory"] = kept + [
        _stack(tval, sval, count) for tval, sval, count in (
            (TVAL_POTION, SV_POTION_HEALING, healing), (TVAL_POTION, SV_POTION_SPEED, speed),
            (TVAL_POTION, SV_POTION_CURE_CRITICAL, ccw),
            (TVAL_SCROLL, SV_TELEPORT, teleports), (TVAL_SCROLL, SV_RECALL, recall),
            (TVAL_SCROLL, SV_LIGHT, light)) if count]
    raw["visible_monsters"] = [dict(row) for row in monsters]
    raw["detected_monsters"] = []
    raw["messages"] = []
    return raw


def new_policy(primed=None):
    policy = ConservativePolicy(monrace_knowledge=RACES, quest_knowledge=QUESTS, quest_strategies=STRATEGIES)
    first = copy.deepcopy(primed or BASE)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(_CASE["skill"]), turn=first["turn"],
        player=dict(_CASE["skill"]["player"], level=first["player"]["level"])))
    return policy


def choose(policy, raw):
    raw["turn"] += 10
    return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))


def decide(raw, *, stage=None):
    policy = new_policy(raw)
    if stage is not None:
        _set_stage(policy, raw, stage)
    return choose(policy, raw), policy.last_reason, policy


def _set_stage(policy, raw, stage):
    from hengbot.quest_room_sweep import _navigator
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    _navigator(policy, snapshot, 25).sweep_stage = stage


def step_key(start, goal):
    return DIRECTION[(goal[0] - start[0], goal[1] - start[1])]


def navigator_of(policy):
    return policy._quest_navigators[25]

