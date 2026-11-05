"""Quest 25 『幽霊屋敷』: a constructed playthrough through the public ``choose_key``.

Owner 2026-11-04: 「強敵複数と同時に対峙する想定は重すぎる。1対1で戦える想定で数値を出して。」;
「テレポートで立て直すだけ」; 手のドルジは「最後に回して戻って撃つ」; 「魔道具術師は有効な攻撃魔法道具も
考慮に入れて良い」; 「経験値復活の薬と腕力復活の薬を2本ずつ持参」.

DECLARED CONSTRUCTED: no character has played this quest.  The boards are the recorded n1-c
Q31 board of tests/fixtures/once-quest-recall-20261103.json.gz with its floor, grid map, quest
row, position, HP, monsters and carried potions and scrolls replaced: the grid map from the
real lib/edit/quests/025_HauntedHouse.jsonc (every cell known), the monsters with the races and
cells of that map.  Monster data is the real MonraceDefinitions.  The owner approved the
file on 2026-11-05, withdrew it the same day (「直るまで受けない」) and restored it (「Q25の承認を戻す」).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import policy_quest as policy_quest_module
from hengbot import consumable_policy, destruction_use, once_quest_recall, quest_optional_carry, quest_room_light, quest_room_sweep, quest_exposure, quest_force_rows, quest_ranged_force, trap_warning
from hengbot.cli import _cell_loop_guard_applies
from hengbot.model import (
    Position, STORE_ALCHEMIST, STORE_HOME, STORE_TEMPLE, StoreItem, StoreState,
    SV_POTION_CURE_CRITICAL, SV_POTION_ENLIGHTENMENT, SV_POTION_HEALING, SV_POTION_RESTORE_EXP, SV_POTION_RESTORE_STR, SV_POTION_SPEED,
    TVAL_POTION, TVAL_SCROLL, TVAL_WAND, parse_snapshot, _GRID_TERRAIN_NAMES,
)
from hengbot.monrace_knowledge import _strip_jsonc, find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_constants import (
    CHEST_DISARM_BUDGET, EXECUTABLE_QUEST_STRATEGY_IDS, REST_MACRO, SEARCH_KEY, SEARCH_LIMIT, WAIT_KEY,
)
from hengbot.quest_find_exit import HEAL_REASON, HOLD_REASON, MELEE_REASON, RECALL_REASON
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_room_sweep import (
    APPROACH_REASON, CLOSE_REASON, COVER_REASON, EXIT_REASON, EXIT_WALK_REASON, LIGHT_REASON, NOTHING_LEFT_REASON, OPEN_REASON, RESTORE_REASON,
    TELEPORT_REASON, WALK_REASON, _note_last_seen, _sought_cells,
)
from hengbot.quest_strategies import load_quest_strategies
from hengbot.trap_warning import SEARCH_REASON
from tests.test_q14_heal_ccw_recorded import town_maps

ROOT = Path(__file__).parents[1]
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


class Q25MapFactsTest(unittest.TestCase):
    TERRAIN = QUESTS[25].battlefield.terrain

    def test_the_roster_stands_where_the_plan_says(self):
        placed = {cell: race for cell, race in QUESTS[25].battlefield.monster_placements}
        self.assertEqual(
            {(9, 19): TYRANNOSAUR, (12, 24): DREADMASTER, (13, 15): VAMPIRE, (11, 18): DRUJ, (9, 8): TOME,
             (7, 4): HOUND, (7, 17): IPSISSIMUS, (8, 17): IPSISSIMUS, (9, 17): IPSISSIMUS, (13, 4): SPECTRE,
             (13, 8): SPECTRE, (2, 5): SKELETAL_T, (9, 9): QUYL, (9, 13): QUYL, (13, 29): STAIR, (1, 11): MASS,
             (1, 14): MASS, **{(y, x): SHADOW for y in (11, 12, 13) for x in (10, 11, 12)}}, placed)
        self.assertEqual(QUESTS[25].level, 48)
        self.assertEqual(QUESTS[25].battlefield.player_start, START)

    def test_wall_passers_have_only_doors_and_the_one_granite_and_the_hound_comes_by_it(self):
        self.assertNotIn("CAN_PASS", TERRAINS["PERMANENT"]["flags"])
        self.assertIn("CAN_PASS", TERRAINS["GRANITE"]["flags"])
        self.assertIn("CAN_PASS", TERRAINS["CLOSED_DOOR"]["flags"])
        self.assertEqual(QUEST["map"][9][3], "#")
        self.assertEqual(self.TERRAIN[(10, 2)], "floor")
        granite = [(y, x) for y, line in enumerate(QUEST["map"]) for x, glyph in enumerate(line) if glyph == "#"]
        self.assertEqual(granite, [(9, 3)])

    def test_the_draft_choke_is_gone(self):
        text = (ROOT / "strategy" / "quests" / "QUEST_25.jsonc").read_text(encoding="utf-8")
        self.assertNotIn("[8,1]", text)
        self.assertIsNone(STRATEGIES[25].engagement_plan["hold_position"])
        # Withdrawn 2026-11-05 「直るまで受けない」 until the summon rules reach this plan.
        self.assertTrue(FILE_STRATEGIES[25].approved)

    def test_every_stop_is_walkable_and_every_target_door_is_a_door(self):
        for stop in PLAN["stands"]:
            self.assertEqual(self.TERRAIN[tuple(stop["cell"])], "floor", stop)
        for stop in PLAN["last_targets"]:
            if "door" in stop:
                self.assertEqual(self.TERRAIN[tuple(stop["door"])], "door", stop)
            self.assertEqual(self.TERRAIN[tuple(stop["stand"])], "floor", stop)

    def test_the_hall_stands_reach_their_targets_within_a_radius_2_light(self):
        for stand, targets in (((7, 8), ((9, 8),)), ((8, 15), ((7, 17), (8, 17), (9, 17)))):
            self.assertIn({"cell": list(stand)}, PLAN["stands"])
            for target in targets:
                self.assertLessEqual(quest_exposure.game_distance(stand, target), 2)
                self.assertTrue(quest_exposure.projectable(self.TERRAIN, stand, target))

    def test_the_quyl_stand_is_dry_and_reaches_both_within_a_radius_2_light(self):
        stops = [stop for stop in PLAN["last_targets"] if stop["race"] == QUYL]
        self.assertEqual([tuple(stop["cell"]) for stop in stops], [(9, 9), (9, 13)])
        for stop in stops:
            stand, quyl = tuple(stop["stand"]), tuple(stop["cell"])
            self.assertEqual(self.TERRAIN[stand], "floor")
            self.assertLessEqual(quest_exposure.game_distance(stand, quyl), 2)
            self.assertTrue(quest_exposure.projectable(self.TERRAIN, stand, quyl))
            self.assertEqual(stand[0], quyl[0])  # on the ray: a shot with no target-failure limit

    def test_the_end_of_the_walk_is_the_stair_the_quyls_and_the_druj(self):
        self.assertEqual([stop["race"] for stop in PLAN["last_targets"]], [STAIR, QUYL, QUYL, DRUJ])
        self.assertEqual(tuple(STRATEGIES[25].priority_targets[-3:]), (STAIR, QUYL, DRUJ))

    def test_no_dry_cell_has_the_players_line_to_a_quyl_without_its_line_back(self):
        """So the quyls cannot be shot out of their line on this map."""
        for quyl in ((9, 9), (9, 13)):
            cells = [cell for cell, kind in self.TERRAIN.items() if kind == "floor"
                     and 0 < quest_exposure.game_distance(cell, quyl) <= quest_exposure.MAX_SPELL_RANGE]
            self.assertEqual([cell for cell in cells if quest_exposure.projectable(self.TERRAIN, cell, quyl)
                              and not quest_exposure.projectable(self.TERRAIN, quyl, cell)], [])


class Q25WalkTest(unittest.TestCase):
    def test_opening_steps_off_the_stair_and_meets_what_comes(self):
        key, reason, _ = decide(board())
        self.assertEqual((key, reason), (step_key(START, (13, 2)), WALK_REASON))
        key, reason, _ = decide(board((13, 2)))
        self.assertEqual((key, reason), (WAIT_KEY, HOLD_REASON))

    def test_a_quiet_floor_is_walked_stop_by_stop_with_doors_opened_and_the_last_two_last(self):
        raw = board()
        policy = new_policy(raw)
        position, visited, opened, lit = START, [], [], []
        for _ in range(500):
            raw["player"].update(y=position[0], x=position[1])
            key = choose(policy, raw)
            if policy.last_reason == HOLD_REASON:
                continue
            if policy.last_reason == LIGHT_REASON:
                self.assertEqual(position, (5, 3))
                lit.append(position)
                continue
            if key.startswith("o") or policy.last_reason == OPEN_REASON:
                delta = next(offset for offset, value in DIRECTION.items() if key.endswith(value))
                cell = (position[0] + delta[0], position[1] + delta[1])
                opened.append(cell)
                open_door(raw, cell)
                continue
            if policy.last_reason == NOTHING_LEFT_REASON or navigator_of(policy).sweep_round:
                break
            self.assertEqual(policy.last_reason, WALK_REASON, position)
            delta = next(offset for offset, value in DIRECTION.items() if value == key)
            position = (position[0] + delta[0], position[1] + delta[1])
            visited.append(position)
        self.assertEqual(navigator_of(policy).sweep_round, 1, opened)
        order = [visited.index(tuple(stop["cell"])) for stop in PLAN["stands"]]
        self.assertEqual(order, sorted(order))
        self.assertEqual(opened[-2:], [(13, 28), (11, 19)])
        tail = visited[visited.index((13, 27)):]
        self.assertLess(tail.index((9, 11)), tail.index((11, 20)))
        self.assertEqual(lit, [(5, 3)])
        self.assertNotIn((11, 19), visited)
        self.assertNotIn((13, 1), visited)  # never back on the stair

    def test_the_walk_avoids_deep_water(self):
        key, reason, _ = decide(board((6, 7)), stage=4)  # to [7,8]
        self.assertEqual(reason, WALK_REASON)
        self.assertEqual(key, step_key((6, 7), (7, 8)))
        key, reason, _ = decide(board((7, 8)), stage=6)  # to [9,6], round the water
        self.assertEqual(reason, WALK_REASON)
        self.assertEqual(key, step_key((7, 8), (7, 7)))

    def test_the_rounds_limit_is_the_owners_100(self):
        self.assertEqual(PLAN["max_rounds"], 100)
        raw = board((13, 2))
        policy = new_policy(raw)
        _set_stage(policy, raw, 0)
        navigator_of(policy).sweep_round = 99
        choose(policy, raw)
        self.assertNotEqual(policy.last_reason, NOTHING_LEFT_REASON)

    def test_rounds_end_by_name(self):
        raw = board((13, 2))
        policy = new_policy(raw)
        _set_stage(policy, raw, 0)
        navigator_of(policy).sweep_round = PLAN["max_rounds"]
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, NOTHING_LEFT_REASON))

    def test_a_completed_quest_is_no_longer_this_plans(self):
        _, reason, _ = decide(board((13, 2), status=2))
        self.assertNotIn(reason, {HOLD_REASON, WALK_REASON})

    def test_an_unapproved_file_does_not_run_the_plan(self):
        raw = board((13, 2))
        unapproved = {**FILE_STRATEGIES, 25: replace(FILE_STRATEGIES[25], approved=False)}
        policy = ConservativePolicy(monrace_knowledge=RACES, quest_knowledge=QUESTS, quest_strategies=unapproved)
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        choose(policy, raw)
        self.assertNotIn(policy.last_reason, {HOLD_REASON, WALK_REASON})


class Q25DrujLastTest(unittest.TestCase):
    STAND, DOOR, CELL = (11, 20), (11, 19), (11, 18)
    STAGE = DRUJ_STOP

    def test_the_stand_is_walked_to_and_the_door_opened_only_at_its_stage(self):
        key, reason, _ = decide(board(self.STAND), stage=self.STAGE)
        self.assertEqual((key, reason), ("o" + step_key(self.STAND, self.DOOR), OPEN_REASON))

    def test_control_before_its_stage_the_door_stays_shut(self):
        key, reason, _ = decide(board(self.STAND), stage=0)
        self.assertEqual(reason, WALK_REASON)
        self.assertFalse(key.startswith("o"))

    def test_with_the_door_open_it_is_shot(self):
        raw = board(self.STAND, speed=0, monsters=[monster(DRUJ, *self.CELL)])
        open_door(raw, self.DOOR)
        key, reason, _ = decide(raw, stage=self.STAGE)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith(step_key(self.STAND, self.DOOR)), key)

    def test_something_else_in_view_goes_first(self):
        raw = board(self.STAND, speed=0, monsters=[monster(DRUJ, *self.CELL), monster(SPECTRE, 11, 23)])
        open_door(raw, self.DOOR)
        key, reason, _ = decide(raw, stage=self.STAGE)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith("6"), key)  # east, at the spectre

    def test_teleported_away_it_walks_back_every_time_with_no_limit(self):
        raw = board((2, 25), speed=0)
        open_door(raw, self.DOOR)
        policy = new_policy(raw)
        _set_stage(policy, raw, self.STAGE)
        for attempt in range(60):  # far past any attempt count; a landing differs each time
            raw["player"].update(y=1 + attempt % 3, x=20 + attempt % 10)
            choose(policy, raw)
            self.assertEqual(policy.last_reason, WALK_REASON)
            self.assertEqual(navigator_of(policy).sweep_stage, self.STAGE)
            # thrown back to the stand and away again
            raw["player"].update(y=self.STAND[0], x=self.STAND[1])
            raw["visible_monsters"] = [monster(DRUJ, *self.CELL)]
            choose(policy, raw)
            self.assertTrue(policy.last_reason.startswith("ranged:"), policy.last_reason)
            raw["visible_monsters"] = []
        self.assertEqual(navigator_of(policy).sweep_stage, self.STAGE)

    def test_gone_from_its_cell_the_round_ends(self):
        raw = board(self.STAND)
        open_door(raw, self.DOOR)
        policy = new_policy(raw)
        _set_stage(policy, raw, self.STAGE)
        choose(policy, raw)
        self.assertEqual(navigator_of(policy).sweep_round, 1)
        self.assertEqual(navigator_of(policy).sweep_stage, 0)


class Q25TargetOrderTest(unittest.TestCase):
    def test_the_tome_is_shot_with_a_quyl_nearer_and_in_view(self):
        raw = board((7, 9), monsters=[monster(TOME, 9, 7), monster(QUYL, 9, 9)])
        key, reason, _ = decide(raw)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith("1"), key)  # at the tome on the diagonal; the quyl is south

    def test_control_with_no_quyl_the_tome_is_shot(self):
        raw = board((7, 9), monsters=[monster(TOME, 9, 7)])
        key, reason, _ = decide(raw)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith("1"), key)

    def test_the_summoner_is_shot_before_a_nearer_spectre(self):
        raw = board((8, 14), speed=0, monsters=[monster(IPSISSIMUS, 8, 17), monster(SPECTRE, 8, 12)])
        key, reason, _ = decide(raw)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith("6"), key)

    def test_the_tome_goes_before_a_nearer_spectre_too(self):
        raw = board((6, 8), speed=0, monsters=[monster(TOME, 9, 8), monster(SPECTRE, 6, 6)])
        key, reason, _ = decide(raw)
        self.assertTrue(key.endswith("2"), (key, reason))

    def test_a_coming_enemy_beside_the_player_is_struck(self):
        raw = board((8, 15), monsters=[monster(SPECTRE, 8, 14), monster(IPSISSIMUS, 8, 17)])
        key, reason, _ = decide(raw)
        self.assertEqual((key, reason), (step_key((8, 15), (8, 14)), MELEE_REASON))

    def test_an_immobile_target_with_no_shot_is_walked_up_to_through_the_water(self):
        raw = board((7, 9), monsters=[monster(TOME, 9, 8)])
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in {16, 17, 18}]
        key, reason, _ = decide(raw)
        self.assertEqual(reason, APPROACH_REASON)


class Q25QuylLastTest(unittest.TestCase):
    """Owner 2026-11-05: 「クイルスルグは放置しても問題ないし、簡単には倒せないので最後ドルジの前に処理する」."""

    HALL = (7, 11)
    STAND = (9, 11)
    QUYLS = ((9, 9), (9, 13))

    def seen(self, position=HALL, **kwargs):
        return board(position, speed=0, monsters=[monster(QUYL, *cell, index=480 + index)
                                                  for index, cell in enumerate(self.QUYLS)], **kwargs)

    def test_mid_sweep_a_seen_quyl_gets_no_shot_and_the_walk_goes_on(self):
        key, reason, policy = decide(self.seen(), stage=4)  # to [7,8]
        self.assertEqual((key, reason), ("7", WALK_REASON))
        self.assertEqual(navigator_of(policy).sweep_enemy_turns, 0)

    def test_control_at_the_quyls_stop_it_is_shot(self):
        key, reason, _ = decide(self.seen(self.STAND), stage=QUYL_STOP)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith(("4", "6")), key)

    def test_control_the_stair_stop_still_leaves_it_alone(self):
        _, reason, _ = decide(self.seen(), stage=QUYL_STOP - 1)
        self.assertEqual(reason, WALK_REASON)

    def test_with_no_shot_it_is_not_walked_up_to_before_its_stop(self):
        raw = self.seen()
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in {16, 17, 18}]
        _, reason, _ = decide(raw, stage=4)
        self.assertEqual(reason, WALK_REASON)
        _, reason, _ = decide(copy.deepcopy(raw), stage=QUYL_STOP)
        self.assertEqual(reason, APPROACH_REASON)

    def test_it_does_not_hold_a_stand_up_or_stop_the_rest(self):
        key, reason, _ = decide(self.seen((5, 4), hp=300), stage=4)  # in a line: out of it first
        self.assertEqual((key, reason), (step_key((5, 4), (5, 3)), WALK_REASON))
        key, reason, _ = decide(board((5, 3), hp=300, monsters=[monster(QUYL, 9, 9)]), stage=4)
        self.assertEqual((key, reason), (REST_MACRO, "rest"))

    def test_below_the_scroll_floor_it_alone_is_no_enemy_for_the_recall(self):
        _, reason, _ = decide(self.seen(teleports=4), stage=4)
        self.assertEqual(reason, WALK_REASON)

    def test_hit_by_the_unseen_with_only_a_quyl_in_view_it_is_not_shot(self):
        raw = self.seen()
        # DECLARED: no Light here.  What a dark room does is Q25DarkRoomTest's.
        raw["inventory"] = [item for item in raw["inventory"] if (item["tval"], item["sval"]) != (TVAL_SCROLL, SV_LIGHT)]
        policy = new_policy(raw)
        _set_stage(policy, raw, 4)
        choose(policy, raw)
        raw["messages"] = ["何かがアイス・ボールの呪文を唱えた。"]  # recorded in the first real play
        raw["player"]["hp"] -= 30
        raw["turn"] += 10
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        # The shared rung that shoots a never-moving monster: the plan must not reach it.
        with patch("hengbot.immobile_ranged_kill.key", return_value="SHOT"):
            key = policy.choose_key(snapshot)
        self.assertIsNotNone(policy._unseen_attack_evidence)
        self.assertEqual((key, policy.last_reason), ("7", WALK_REASON))

    def test_quiet_with_only_a_quyl_in_view_the_shared_rungs_are_not_reached(self):
        raw = self.seen()
        policy = new_policy(raw)
        _set_stage(policy, raw, 4)
        with patch("hengbot.immobile_ranged_kill.key", return_value="SHOT"):
            key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("7", WALK_REASON))

    def test_a_coming_enemy_is_answered_as_if_the_quyl_were_not_there(self):
        raw = self.seen()
        raw["visible_monsters"].append(monster(SPECTRE, 7, 13))
        key, reason, _ = decide(raw, stage=4)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith("6"), key)

    def test_teleported_away_at_its_stop_it_walks_back_with_no_limit(self):
        raw = board((2, 25), speed=0)
        policy = new_policy(raw)
        _set_stage(policy, raw, QUYL_STOP)
        for attempt in range(60):  # far past any attempt count
            raw["player"].update(y=1 + attempt % 3, x=20 + attempt % 10)
            raw["visible_monsters"] = []
            choose(policy, raw)
            self.assertEqual(policy.last_reason, WALK_REASON)
            raw["player"].update(y=self.STAND[0], x=self.STAND[1])
            raw["visible_monsters"] = [monster(QUYL, *self.QUYLS[0])]
            choose(policy, raw)
            self.assertTrue(policy.last_reason.startswith("ranged:"), policy.last_reason)
            self.assertEqual(navigator_of(policy).sweep_stage, QUYL_STOP)
        self.assertEqual(navigator_of(policy).sweep_round, 0)

    SEEN_AT = (5, 8)

    def moved_away(self, far):
        """DECLARED: seen in the hall from the stand's stage, then the player is elsewhere and
        the quyl out of sight (a TELE_AWAY's board, or its own BLINK's when ``far`` looks at it)."""
        raw = board((7, 11), speed=0, monsters=[monster(QUYL, *self.SEEN_AT, index=481)])
        policy = new_policy(raw)
        _set_stage(policy, raw, QUYL_STOP)
        choose(policy, raw)
        raw["player"].update(y=far[0], x=far[1])
        raw["visible_monsters"] = []
        return raw, policy

    def test_the_last_seen_cell_is_remembered_per_monster(self):
        _, policy = self.moved_away((7, 11))
        self.assertEqual(navigator_of(policy).sweep_last_seen, {481: (QUYL, self.SEEN_AT)})

    def test_the_player_moved_it_walks_to_the_last_seen_cell_not_the_stand(self):
        raw, policy = self.moved_away((7, 11))
        self.assertEqual(choose(policy, raw), "7")  # the stand [9,11] is due south
        self.assertEqual(policy.last_reason, WALK_REASON)
        self.assertEqual(navigator_of(policy).sweep_stage, QUYL_STOP)
        self.assertEqual(navigator_of(policy).sweep_last_seen, {481: (QUYL, self.SEEN_AT)})

    def test_seen_again_it_is_shot(self):
        raw, policy = self.moved_away((7, 11))
        raw["visible_monsters"] = [monster(QUYL, *self.SEEN_AT, index=481)]
        choose(policy, raw)
        self.assertTrue(policy.last_reason.startswith("ranged:"), policy.last_reason)

    def test_the_monster_moved_the_cell_is_forgotten_and_the_stops_go_on(self):
        raw, policy = self.moved_away((6, 9))
        key = choose(policy, raw)
        self.assertEqual(navigator_of(policy).sweep_last_seen, {})
        self.assertEqual(policy.last_reason, WALK_REASON)
        self.assertEqual(navigator_of(policy).sweep_stage, QUYL_STOP)
        self.assertEqual(key, "3")  # on to the stand

    def test_control_blind_a_cell_is_not_looked_at(self):
        raw, policy = self.moved_away((6, 9))
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        _note_last_seen(replace(snapshot, player=replace(snapshot.player, blind=True)), navigator_of(policy), PLAN)
        self.assertEqual(navigator_of(policy).sweep_last_seen, {481: (QUYL, self.SEEN_AT)})

    def test_control_mid_sweep_it_is_left_alone_however_it_was_seen(self):
        raw = self.seen()
        policy = new_policy(raw)
        _set_stage(policy, raw, 4)
        choose(policy, raw)
        self.assertEqual(set(navigator_of(policy).sweep_last_seen), {480, 481})
        raw["player"].update(y=2, x=2)
        raw["visible_monsters"] = []
        choose(policy, raw)
        self.assertEqual(navigator_of(policy).sweep_stage, 4)
        self.assertEqual(_sought_cells(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
                                       navigator_of(policy), PLAN), {})

    def test_in_sight_it_is_not_sought_and_a_new_floor_forgets(self):
        raw, policy = self.moved_away((7, 11))
        raw["visible_monsters"] = [monster(QUYL, *self.SEEN_AT, index=481)]
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(_sought_cells(snapshot, navigator_of(policy), PLAN), {})
        navigator_of(policy).reset_for_floor((9, 9, 25))
        self.assertEqual(navigator_of(policy).sweep_last_seen, {})

    def test_no_way_to_it_the_record_is_dropped(self):
        raw, policy = self.moved_away((7, 11))
        with patch("hengbot.quest_room_sweep._path", return_value=[]):
            choose(policy, raw)
        self.assertEqual(navigator_of(policy).sweep_last_seen, {})

    def test_dead_the_walk_goes_on_to_the_druj_and_no_round_is_spent(self):
        raw = board(self.STAND, speed=0)
        policy = new_policy(raw)
        _set_stage(policy, raw, QUYL_STOP)
        choose(policy, raw)
        self.assertEqual(policy.last_reason, WALK_REASON)
        self.assertEqual(navigator_of(policy).sweep_stage, DRUJ_STOP)
        self.assertEqual(navigator_of(policy).sweep_round, 0)
        self.assertEqual(PLAN["last_targets"][-1]["race"], DRUJ)

    def test_at_its_stop_something_else_in_view_goes_first(self):
        raw = self.seen(self.STAND)
        raw["visible_monsters"].append(monster(SPECTRE, 7, 11))
        key, reason, _ = decide(raw, stage=QUYL_STOP)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertTrue(key.endswith("8"), key)

    def test_a_blinked_quyl_on_the_way_is_walked_round_not_struck(self):
        raw = board(self.HALL, speed=0, monsters=[monster(QUYL, 6, 10)])
        key, reason, _ = decide(raw, stage=4)
        self.assertEqual(reason, WALK_REASON)
        self.assertEqual(key, "4")  # [7,10]; the free walk's own first step is [6,10]

    def test_missing_it_goes_on_shooting_from_the_stand(self):
        raw = board(self.STAND, speed=0, monsters=[monster(QUYL, *self.QUYLS[0])])
        policy = new_policy(raw)
        _set_stage(policy, raw, QUYL_STOP)
        for _ in range(10):
            self.assertTrue(choose(policy, raw).endswith("4"))
            self.assertTrue(policy.last_reason.startswith("ranged:"), policy.last_reason)

    def test_the_rounds_do_not_turn_while_they_are_left_alone(self):
        raw = self.seen()
        policy = new_policy(raw)
        _set_stage(policy, raw, 4)
        for _ in range(30):
            choose(policy, raw)
        self.assertEqual(navigator_of(policy).sweep_round, 0)
        self.assertEqual(navigator_of(policy).sweep_stage, 4)


class Q25EmergencyTest(unittest.TestCase):
    def test_below_the_line_teleport_and_no_recall(self):
        raw = board((8, 19), hp=300, monsters=[monster(TYRANNOSAUR, 8, 20)])
        key, reason, _ = decide(raw)
        self.assertEqual(reason, TELEPORT_REASON)
        self.assertTrue(key.startswith("r"))
        self.assertNotEqual(reason, RECALL_REASON)

    def test_an_enemy_still_on_the_player_after_the_teleport_gets_the_potion(self):
        raw = board((8, 19), hp=300, monsters=[monster(TYRANNOSAUR, 8, 20)])
        policy = new_policy(raw)
        choose(policy, raw)
        self.assertEqual(policy.last_reason, TELEPORT_REASON)
        raw["player"].update(y=2, x=25)
        raw["visible_monsters"] = [monster(SPECTRE, 2, 26)]
        choose(policy, raw)
        self.assertEqual(policy.last_reason, HEAL_REASON)

    def test_no_recall_at_any_hp_while_five_scrolls_remain(self):
        for hp in (10, 300, 500):
            raw = board((8, 19), hp=hp, teleports=5, monsters=[monster(TYRANNOSAUR, 8, 20)])
            _, reason, policy = decide(raw)
            self.assertNotEqual(reason, RECALL_REASON)
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            self.assertTrue(once_quest_recall.held(policy, snapshot))

    def test_below_five_scrolls_with_an_enemy_recall_at_any_hp(self):
        key, reason, _ = decide(board((8, 19), hp=FULL_HP, teleports=4, speed=0, monsters=[monster(TYRANNOSAUR, 8, 20)]))
        self.assertEqual(reason, RECALL_REASON)
        self.assertTrue(key.startswith("r"))

    def test_below_five_scrolls_with_no_enemy_no_recall(self):
        raw = board((8, 19), hp=FULL_HP, teleports=4)
        _, reason, policy = decide(raw)
        self.assertNotEqual(reason, RECALL_REASON)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertTrue(once_quest_recall.held(policy, snapshot))

    def test_recall_read_the_fight_goes_on_with_scrolls_and_potions(self):
        raw = board((8, 19), hp=300, teleports=4, recalling=True, monsters=[monster(TYRANNOSAUR, 8, 20)])
        _, reason, _ = decide(raw)
        self.assertEqual(reason, TELEPORT_REASON)

    def test_cure_critical_is_no_hp_recovery(self):
        raw = board((8, 19), hp=300, healing=0, speed=0, teleports=0, recall=0, ccw=9,
                    monsters=[monster(TYRANNOSAUR, 8, 20)])
        key, reason, _ = decide(raw)
        self.assertEqual((key, reason), (step_key((8, 19), (8, 20)), MELEE_REASON))

    def test_healing_above_the_line_below_the_plans_threshold(self):
        raw = board((8, 19), hp=500, speed=0, monsters=[monster(TYRANNOSAUR, 8, 20)])
        _, reason, _ = decide(raw)
        self.assertEqual(reason, HEAL_REASON)

    def test_the_stair_is_taken_life_threatened_with_the_healing_used_up(self):
        enemy = [monster(TYRANNOSAUR, 12, 2)]
        key, reason, _ = decide(board(START, hp=100, healing=0, speed=0, monsters=enemy))
        self.assertEqual((key, reason), ("<", EXIT_REASON))
        key, reason, _ = decide(board((10, 1), hp=100, healing=0, speed=0, monsters=[monster(SPECTRE, 9, 1)]))
        self.assertEqual((key, reason), (step_key((10, 1), (11, 1)), EXIT_WALK_REASON))

    def test_controls_the_stair_is_not_taken(self):
        enemy = [monster(TYRANNOSAUR, 12, 2)]
        for raw, expected in (
            (board(START, hp=100, speed=0, monsters=enemy), TELEPORT_REASON),  # Healing left
            (board(START, hp=300, healing=0, speed=0, monsters=enemy), TELEPORT_REASON),  # above the panic line
            (board(START, hp=FULL_HP, healing=0, speed=0, monsters=enemy), None),
            (board((5, 1), hp=100, healing=0, speed=0, monsters=[monster(SPECTRE, 4, 1)]), TELEPORT_REASON),  # 8 steps
        ):
            key, reason, _ = decide(raw)
            self.assertNotIn("<", key)
            self.assertNotEqual(reason, EXIT_WALK_REASON)
            if expected is not None:
                self.assertEqual(reason, expected)

    def test_quiet_the_stair_is_not_taken_at_any_hp(self):
        key, reason, _ = decide(board(START, hp=100, healing=0))
        self.assertEqual((key, reason), (REST_MACRO, "rest"))

    def test_a_heavy_fight_takes_the_speed_potion(self):
        _, reason, _ = decide(board((8, 19), monsters=[monster(TYRANNOSAUR, 8, 20)]))
        self.assertEqual(reason, "quest-strategy:quaff-speed")

    def test_quiet_rests_at_any_hp(self):
        key, reason, _ = decide(board((8, 19), hp=100))
        self.assertEqual((key, reason), (REST_MACRO, "rest"))

    def test_quiet_and_drained_the_carried_potions_are_drunk(self):
        raw = board((8, 19))
        raw["inventory"] += [_stack(TVAL_POTION, SV_POTION_RESTORE_EXP, 2), _stack(TVAL_POTION, SV_POTION_RESTORE_STR, 2)]
        raw["player"]["exp_drained"] = True
        _, reason, _ = decide(raw)
        self.assertEqual(reason, RESTORE_REASON)


class Q25LightTest(unittest.TestCase):
    MOUTH = (5, 3)
    STAGE = 3

    def test_the_mouth_is_out_of_both_quyls_lines_and_opens_on_the_hall(self):
        self.assertEqual(PLAN["stands"][self.STAGE], {"cell": list(self.MOUTH), "read_light": True})
        lines = quest_exposure.exposure_map(QUESTS[25].battlefield.terrain, [(9, 9), (9, 13)]).pull
        self.assertNotIn(self.MOUTH, lines)

    def test_it_is_read_once_there_then_the_walk_goes_on(self):
        raw = board(self.MOUTH)
        policy = new_policy(raw)
        _set_stage(policy, raw, self.STAGE)
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, LIGHT_REASON)
        self.assertTrue(key.startswith("r"), key)
        choose(policy, raw)
        self.assertEqual(policy.last_reason, WALK_REASON)

    def test_with_an_enemy_shooting_from_the_dark_it_is_still_read(self):
        raw = board(self.MOUTH, speed=0, monsters=[monster(SPECTRE, 7, 12)])
        _, reason, _ = decide(raw, stage=self.STAGE)
        self.assertEqual(reason, LIGHT_REASON)

    def test_control_not_on_the_mouth_or_with_none_it_is_not_read(self):
        _, reason, _ = decide(board((5, 2)), stage=self.STAGE)
        self.assertEqual(reason, WALK_REASON)
        _, reason, _ = decide(board(self.MOUTH, light=0), stage=self.STAGE)
        self.assertEqual(reason, WALK_REASON)

    def test_survival_comes_first(self):
        raw = board(self.MOUTH, hp=300, monsters=[monster(SPECTRE, 5, 4)])
        _, reason, _ = decide(raw, stage=self.STAGE)
        self.assertEqual(reason, TELEPORT_REASON)

    def test_a_lit_hall_is_shot_from_afar(self):
        raw = board((5, 4), speed=0, monsters=[monster(TOME, 9, 8, index=1)])
        key, reason, _ = decide(raw, stage=self.STAGE + 1)
        self.assertTrue(reason.startswith("ranged:"), reason)

    def test_the_absorbed_light_staff_casts_in_its_place(self):
        raw = board(self.MOUTH, light=0)
        with patch("hengbot.policy_quest.carry_cast_key", return_value="mAb"):
            key, reason, _ = decide(raw, stage=self.STAGE)
        self.assertEqual(key, "mAb")
        self.assertTrue(reason.startswith(LIGHT_REASON), reason)

    def test_the_carry_is_asked_at_acceptance_and_the_staff_waives_it(self):
        accept = Q25AcceptanceTest()
        ready, telemetry, _ = accept.verdict(accept.town(max_hp=850, light=11), 200)
        self.assertFalse(ready, telemetry)
        self.assertIn("required_scrolls.light", telemetry["strategy_force"]["failed"])
        ready, telemetry, _ = accept.verdict(accept.town(max_hp=850), 200)
        self.assertTrue(ready, telemetry)
        real = policy_quest_module.replaced_by_absorbed
        with patch("hengbot.policy_quest.replaced_by_absorbed", side_effect=lambda policy, snapshot, target, *rest: (
                getattr(target, "name", None) == "light" or real(policy, snapshot, target, *rest))):
            ready, telemetry, _ = accept.verdict(accept.town(max_hp=850, light=0), 200)
        self.assertTrue(ready, telemetry)


class Q25LineTest(unittest.TestCase):
    def test_a_quyls_line_is_a_cell_the_rule_knows_and_the_walk_takes_the_fewest(self):
        lines = quest_exposure.exposure_map(QUESTS[25].battlefield.terrain, [(9, 9), (9, 13)]).pull
        self.assertIn((7, 8), lines)
        self.assertIn((5, 4), lines)
        self.assertNotIn((5, 3), lines)  # the hall's mouth, out of both
        self.assertNotIn((12, 6), lines)  # a closed door shuts them out of the south rooms

    def test_no_wait_in_a_casters_line_it_walks_on(self):
        # A coming enemy in view with no shot: the ammunition is gone.
        raw = board((7, 8), speed=0, monsters=[monster(VAMPIRE, 7, 12)])
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in {16, 17, 18}]
        _, reason, _ = decide(raw, stage=4)
        self.assertEqual(reason, WALK_REASON)

    def test_control_out_of_every_line_it_waits_for_what_comes(self):
        raw = board((12, 6), speed=0, monsters=[monster(VAMPIRE, 12, 8)])
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in {16, 17, 18}]
        key, reason, _ = decide(raw, stage=7)
        self.assertEqual((key, reason), (WAIT_KEY, HOLD_REASON))

    def test_hurt_and_quiet_in_a_line_it_walks_out_before_resting(self):
        key, reason, _ = decide(board((5, 4), hp=300))
        self.assertEqual((key, reason), (step_key((5, 4), (5, 3)), WALK_REASON))
        key, reason, _ = decide(board((5, 3), hp=300))
        self.assertEqual((key, reason), (REST_MACRO, "rest"))


class Q25UnseenAttackerTest(unittest.TestCase):
    """Owner 2026-11-05: 「生存は最優先として、移動は一歩で遮蔽が取れるかで判断。一歩で遮蔽が取れないなら
    距離を詰めたほうが良い。」  DECLARED CONSTRUCTED: the walk is two boards of the module's map, the hit
    is the recorded message 「何かがアイス・ボールの呪文を唱えた。」 with the HP it cost.  Doors as drawn."""

    HIT = "何かがアイス・ボールの呪文を唱えた。"

    def hit_after_walking(self, start, end, *, hp=700, opened=(), light=0, **kwargs):
        raw = board(start, speed=0, light=light, **kwargs)
        for door in opened:
            open_door(raw, door)
        policy = new_policy(raw)
        _set_stage(policy, raw, 1)
        choose(policy, raw)
        raw["player"].update(y=end[0], x=end[1])
        choose(policy, raw)
        raw["player"]["hp"] = hp
        raw["messages"] = [self.HIT]
        return raw, policy

    def in_the_west_passage(self, **kwargs):
        """North up the first play's own walk: back on [8,1], out of every line ahead."""
        return self.hit_after_walking((8, 1), (7, 1), **kwargs)

    def test_a_step_out_of_every_line_ahead_is_taken(self):
        raw, policy = self.in_the_west_passage()
        self.assertEqual(choose(policy, raw), "2")
        self.assertEqual(policy.last_reason, COVER_REASON)
        self.assertEqual(navigator_of(policy).sweep_cover_taken, frozenset({(7, 1)}))

    def test_it_is_looked_for_ahead_of_the_last_step_and_a_new_floor_forgets(self):
        raw, policy = self.hit_after_walking((3, 23), (3, 24))
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        cells = quest_room_sweep._unseen_attacker_cells(policy, snapshot, navigator_of(policy))
        self.assertTrue(cells)
        self.assertTrue(all(cell[1] > 24 for cell in cells), cells)
        navigator_of(policy).sweep_cover_taken = frozenset({(1, 1)})
        navigator_of(policy).reset_for_floor((9, 9, 25))
        self.assertEqual(navigator_of(policy).sweep_cover_taken, frozenset())

    def test_at_the_corridor_door_of_the_first_play_it_closes(self):
        """Rows 67-72: west through the open door [1,18].  Every neighbour shows to the corridor."""
        raw, policy = self.hit_after_walking((1, 20), (1, 19), opened=[(1, 18)])
        self.assertEqual(choose(policy, raw), "4")
        self.assertEqual(policy.last_reason, CLOSE_REASON)

    def test_a_cell_left_once_for_cover_closes_the_next_time(self):
        raw, policy = self.in_the_west_passage()
        choose(policy, raw)
        raw["player"]["hp"] -= 10
        self.assertEqual(choose(policy, raw), "9")  # ahead, toward the hall
        self.assertEqual(policy.last_reason, CLOSE_REASON)

    def test_after_a_teleport_the_direction_is_unknown_and_the_plan_walks(self):
        raw = board((3, 24), speed=0, light=0)
        policy = new_policy(raw)
        _set_stage(policy, raw, 1)
        choose(policy, raw)
        raw["player"]["hp"] = 700
        raw["messages"] = [self.HIT]
        choose(policy, raw)
        self.assertEqual(policy.last_reason, WALK_REASON)

    def test_a_gaze_with_no_damage_is_no_hit_and_the_plan_walks(self):
        raw, policy = self.in_the_west_passage(hp=FULL_HP)
        raw["messages"] = ["何かがあなたの目をじっと見つめた！", "しかし効果がなかった！"]  # recorded
        choose(policy, raw)
        self.assertEqual(policy.last_reason, WALK_REASON)

    def test_control_below_the_line_survival_comes_first(self):
        raw, policy = self.in_the_west_passage(hp=200)
        choose(policy, raw)
        self.assertEqual(policy.last_reason, TELEPORT_REASON)

    def test_control_a_blow_is_struck_back(self):
        raw, policy = self.in_the_west_passage()
        raw["messages"] = ["何かに噛まれた。"]
        key = choose(policy, raw)
        self.assertTrue(key.startswith("+"), (key, policy.last_reason))

    def test_control_without_the_plan_field_it_is_the_shared_rung(self):
        raw, policy = self.in_the_west_passage()
        with patch.dict(PLAN, {"unseen_attacker": "none"}):
            choose(policy, raw)
        self.assertNotIn(policy.last_reason, {COVER_REASON, CLOSE_REASON})

    def test_the_plans_steps_are_not_rewritten_by_the_low_hp_gate(self):
        raw, policy = self.in_the_west_passage()
        choose(policy, raw)
        self.assertTrue(quest_room_sweep.planned_step(
            policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))


class Q25AmbushTest(unittest.TestCase):
    """Owner 2026-11-05 「遮蔽が近ければ遮蔽をとって待ち伏せ」.  DECLARED CONSTRUCTED as above: the hit in
    the west passage, the step to the cover [8,1], then the boards on it."""

    COVER = (8, 1)
    HURT_A_LITTLE = FULL_HP - 20

    def on_the_cover(self, *, hp=HURT_A_LITTLE, **kwargs):
        raw, policy = Q25UnseenAttackerTest().hit_after_walking((8, 1), (7, 1), hp=hp, **kwargs)
        self.assertEqual(choose(policy, raw), "2")
        self.assertEqual(policy.last_reason, COVER_REASON)
        raw["player"].update(y=self.COVER[0], x=self.COVER[1])
        raw["messages"] = []
        return raw, policy

    def test_on_the_cover_it_waits_and_does_not_walk_on(self):
        raw, policy = self.on_the_cover()
        for _ in range(3):
            self.assertEqual(choose(policy, raw), WAIT_KEY)
            self.assertEqual(policy.last_reason, HOLD_REASON)
        self.assertEqual(navigator_of(policy).sweep_ambush_turns, 3)

    def test_the_wait_ends_with_the_plans_budget(self):
        raw, policy = self.on_the_cover()
        navigator_of(policy).sweep_ambush_turns = PLAN["enemy_wait_turns"] - 1
        self.assertEqual(choose(policy, raw), WAIT_KEY)
        choose(policy, raw)
        self.assertEqual(policy.last_reason, WALK_REASON)
        self.assertIsNone(navigator_of(policy).sweep_ambush)

    def test_an_enemy_in_view_is_answered_by_the_fight_and_the_wait_is_over(self):
        raw, policy = self.on_the_cover()
        choose(policy, raw)
        raw["visible_monsters"] = [monster(SPECTRE, 6, 1)]
        key = choose(policy, raw)
        self.assertTrue(key.startswith("f"), (key, policy.last_reason))
        raw["visible_monsters"] = []
        choose(policy, raw)
        self.assertEqual(policy.last_reason, WALK_REASON)

    def test_hurt_it_rests_on_the_cover_before_it_waits(self):
        raw, policy = self.on_the_cover(hp=int(FULL_HP * 0.8))
        self.assertEqual(choose(policy, raw), REST_MACRO)
        self.assertEqual(navigator_of(policy).sweep_ambush, self.COVER)

    def test_survival_comes_first(self):
        raw, policy = self.on_the_cover()
        raw["player"]["hp"] = 200
        raw["messages"] = [Q25UnseenAttackerTest.HIT]
        choose(policy, raw)
        self.assertEqual(policy.last_reason, TELEPORT_REASON)

    def test_hit_on_the_cover_the_read_answers_again(self):
        raw, policy = self.on_the_cover()
        choose(policy, raw)
        raw["player"]["hp"] -= 20
        raw["messages"] = [Q25UnseenAttackerTest.HIT]
        choose(policy, raw)
        self.assertIn(policy.last_reason, {COVER_REASON, CLOSE_REASON, WALK_REASON})

    def test_moved_off_the_cover_the_wait_is_over(self):
        raw, policy = self.on_the_cover()
        choose(policy, raw)
        raw["player"].update(y=3, x=24)
        choose(policy, raw)
        self.assertEqual(policy.last_reason, WALK_REASON)
        self.assertIsNone(navigator_of(policy).sweep_ambush)

    def test_blind_it_leaves_the_board_to_the_shared_rungs_and_the_wait_stays(self):
        raw, policy = self.on_the_cover(ccw=1)
        raw["player"]["status"]["blind"] = True
        choose(policy, raw)
        self.assertNotEqual(policy.last_reason, HOLD_REASON)
        self.assertEqual(navigator_of(policy).sweep_ambush, self.COVER)

    def test_a_cell_in_a_casters_line_is_no_cover(self):
        raw, policy = Q25UnseenAttackerTest().in_the_west_passage()
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        lines = SimpleNamespace(pull=frozenset({(6, 1), (6, 2)}))  # the neighbours tried before the cover
        with patch.object(quest_room_sweep, "_lines", return_value=lines):
            step = quest_room_sweep._cover_step(
                snapshot, navigator_of(policy), PLAN, set(), SimpleNamespace(occupied=set()))
        self.assertEqual(step, Position(*self.COVER))

    def test_on_a_caster_line_it_does_not_wait(self):
        raw, policy = self.on_the_cover()
        with patch.object(quest_room_sweep, "_in_line", return_value=True):
            choose(policy, raw)
        self.assertNotEqual(policy.last_reason, HOLD_REASON)
        self.assertIsNone(navigator_of(policy).sweep_ambush)


class Q25WarningRefusedStepTest(unittest.TestCase):
    """RECORDED: n1-b life-310, the first real play (bot-e0a97bcb5, 2026-11-05).  Both boards
    of each pair are the game's own; the second carries the prompt of the first's step.  The
    walk offered the refused cell again, the gate made that no key, and the bot stopped
    (no-key-exhausted) at 1136/1137 HP with nothing on it.  Owner 2026-11-05: 「罠があるので対応する」.
    Both cells are traps by the map: [1,17] is `^`; [3,1] is `!` showing no object from beside it.
    The grid shows neither (the export's MIMIC terrain), and no monster is on either board.
    DECLARED: the later boards are the recorded prompt board without its messages, and a found
    trap is its grid with ``trap`` set; the monsters of the controls are declared."""

    with gzip.open(ROOT / "tests" / "fixtures" / "q25-warning-1105.json.gz", "rt", encoding="utf-8") as _stream:
        BOARDS = json.load(_stream)

    def after_the_prompt(self, name, *, stage=None, supplies=True, monsters=()):
        walk, prompt = copy.deepcopy(self.BOARDS[name]["walk"]), copy.deepcopy(self.BOARDS[name]["prompt"])
        # DECLARED: no Light on these boards.  What a dark room does is Q25DarkRoomTest's.
        for raw in (walk, prompt):
            raw["inventory"] = [item for item in raw["inventory"]
                                if (item["tval"], item["sval"]) != (TVAL_SCROLL, SV_LIGHT)]
        if not supplies:
            for raw in (walk, prompt):
                raw["inventory"] = [item for item in raw["inventory"] if item["tval"] != TVAL_SCROLL]
        prompt["visible_monsters"] = [dict(row) for row in monsters]
        policy = new_policy(walk)
        if stage is not None:
            _set_stage(policy, walk, stage)
        walked = policy.choose_key(parse_snapshot(walk, policy._monrace_knowledge))
        answered = policy.choose_key(parse_snapshot(prompt, policy._monrace_knowledge))
        return walked, answered, policy, prompt

    @staticmethod
    def next_board(policy, prompt, *, trap=None, monsters=()):
        raw = copy.deepcopy(prompt)
        raw["messages"], raw["visible_monsters"] = [], [dict(row) for row in monsters]
        raw["turn"] = prompt["turn"] = prompt["turn"] + 10
        snapshot = parse_snapshot(raw, policy._monrace_knowledge)
        if trap is not None:
            cell = Position(*trap)
            snapshot = replace(snapshot, grids={**snapshot.grids, cell: replace(snapshot.grids[cell], trap=True)})
        return snapshot

    @staticmethod
    def refused(policy):
        return {(cell.y, cell.x) for cell in policy._warning_refused_cells}

    def test_the_recorded_cells_show_no_trap_and_no_monster(self):
        for name, cell in (("choke", (3, 1)), ("corridor", (1, 17))):
            snapshot = parse_snapshot(copy.deepcopy(self.BOARDS[name]["prompt"]), None)
            self.assertFalse(snapshot.grids[Position(*cell)].trap)
            self.assertEqual((snapshot.visible_monsters, snapshot.detected_monsters), ([], []))

    def test_no_monster_to_blame_it_is_searched_from_beside_it(self):
        for name, stage, walk_key in (("corridor", None, "4"), ("choke", 1, "8")):
            with self.subTest(name):
                walked, answered, policy, _ = self.after_the_prompt(name, stage=stage)
                self.assertEqual(walked, walk_key)
                self.assertEqual(self.refused(policy), set())
                self.assertEqual((answered, policy.last_reason), (SEARCH_KEY, SEARCH_REASON))

    def test_a_stop_over_the_warned_cell_is_not_passed(self):
        """[3,1] is the only way from the hall to the north-west rooms."""
        _, _, policy, _ = self.after_the_prompt("choke", stage=1)
        self.assertEqual(navigator_of(policy).sweep_stage, 1)  # [2,2] still ahead

    def test_with_no_scroll_left_it_is_the_same_answer(self):
        _, answered, _, _ = self.after_the_prompt("choke", stage=1, supplies=False)
        self.assertEqual(answered, SEARCH_KEY)

    def test_never_found_the_searches_end_and_the_walk_answers_its_prompt(self):
        _, answered, policy, prompt = self.after_the_prompt("choke", stage=1)
        keys = [answered, *(policy.choose_key(self.next_board(policy, prompt)) for _ in range(SEARCH_LIMIT))]
        self.assertEqual(keys, [SEARCH_KEY] * SEARCH_LIMIT + ["8y"])
        self.assertEqual(policy.last_reason, WALK_REASON)

    def test_found_it_is_disarmed_within_the_budget_and_then_crossed(self):
        _, _, policy, prompt = self.after_the_prompt("choke", stage=1)
        keys = [policy.choose_key(self.next_board(policy, prompt, trap=(3, 1)))
                for _ in range(CHEST_DISARM_BUDGET + 1)]
        self.assertEqual(keys, ["D8"] * CHEST_DISARM_BUDGET + ["8y"])

    def test_with_an_enemy_awake_elsewhere_there_is_no_search(self):
        """In the hall: no line to the corridor cell, so not to blame, but no time to search."""
        far = monster(SPECTRE, 7, 5)
        _, _, policy, prompt = self.after_the_prompt("choke", stage=1, monsters=[far])
        self.assertEqual(self.refused(policy), set())
        self.assertEqual({(cell.y, cell.x) for cell in policy._trap_warning_cells}, {(3, 1)})
        snapshot = self.next_board(policy, prompt, monsters=[far])
        self.assertIsNone(trap_warning.search_key(policy, snapshot, Position(3, 1)))
        self.assertTrue(trap_warning.walk_across(policy, snapshot, Position(3, 1)))

    def test_control_an_awake_monster_in_line_keeps_the_latch(self):
        _, _, policy, prompt = self.after_the_prompt("choke", stage=1, monsters=[monster(SPECTRE, 1, 1)])
        self.assertEqual(self.refused(policy), {(3, 1)})
        self.assertEqual(policy._trap_warning_cells, {})
        key = policy.choose_key(self.next_board(policy, prompt))
        self.assertEqual(policy.last_reason, WALK_REASON)
        self.assertEqual(navigator_of(policy).sweep_stage, 3)  # [2,2] and [1,4] passed; [5,3] next
        self.assertEqual(key, "2")
        self.assertEqual(navigator_of(policy).sweep_round, 0)

    def test_control_an_asleep_monster_is_not_to_blame(self):
        _, _, policy, _ = self.after_the_prompt("choke", stage=1, monsters=[monster(SPECTRE, 1, 1, asleep=True)])
        self.assertEqual(self.refused(policy), set())

    def test_control_the_latched_cell_with_no_scroll_left_still_forced(self):
        _, _, policy, prompt = self.after_the_prompt(
            "choke", stage=1, supplies=False, monsters=[monster(SPECTRE, 1, 1)])
        self.assertEqual(policy.choose_key(self.next_board(policy, prompt)), "8y")
        self.assertEqual(policy.last_reason, WALK_REASON)

    def test_a_tail_that_answered_it_with_no_monster_latches_nothing(self):
        walk, prompt = copy.deepcopy(self.BOARDS["choke"]["walk"]), copy.deepcopy(self.BOARDS["choke"]["prompt"])
        prompt["player"].update(y=3, x=1)
        policy = new_policy(walk)
        _set_stage(policy, walk, 1)
        policy.choose_key(parse_snapshot(walk, policy._monrace_knowledge))
        policy.choose_key(parse_snapshot(prompt, policy._monrace_knowledge))
        self.assertEqual(self.refused(policy), set())

    def test_the_searches_of_a_corridor_of_traps_are_no_cell_loop(self):
        _, _, policy, prompt = self.after_the_prompt("choke", stage=1)
        snapshot = self.next_board(policy, prompt)
        self.assertFalse(_cell_loop_guard_applies(snapshot, SEARCH_REASON, snapshot.player.position))

    def test_a_restored_checkpoint_without_the_record_decides(self):
        policy = new_policy(copy.deepcopy(self.BOARDS["choke"]["walk"]))
        del policy.__dict__["_trap_warning_cells"]
        normalize_policy_state(policy)
        self.assertEqual(policy._trap_warning_cells, {})

    def test_the_record_ends_with_the_floor_and_in_a_destroyed_circle(self):
        _, _, policy, prompt = self.after_the_prompt("choke", stage=1)
        self.assertIn("_trap_warning_cells", destruction_use.POSITION_DICTS)
        other = self.next_board(policy, prompt)
        other = replace(other, floor_key=(other.floor_key[0], other.floor_key[1] + 1, 0))
        policy.choose_key(other)
        self.assertEqual(policy._trap_warning_cells, {})

    def test_control_the_same_prompt_off_the_plan_is_latched(self):
        """The plan makes this floor's answer; with no room sweep the walkers go round it."""
        walk, prompt = copy.deepcopy(self.BOARDS["choke"]["walk"]), copy.deepcopy(self.BOARDS["choke"]["prompt"])
        policy = new_policy(walk)
        _set_stage(policy, walk, 1)
        policy.choose_key(parse_snapshot(walk, policy._monrace_knowledge))
        with patch("hengbot.quest_room_sweep._plan", return_value=None):
            trap_warning.note_warned(policy, parse_snapshot(prompt, policy._monrace_knowledge), Position(3, 1))
        self.assertEqual(self.refused(policy), {(3, 1)})
        self.assertEqual(policy._trap_warning_cells, {Position(3, 1): 0})

    def test_crossed_the_cell_is_forgotten(self):
        _, _, policy, prompt = self.after_the_prompt("choke", stage=1)
        on_it = copy.deepcopy(prompt)
        on_it["player"].update(y=3, x=1)
        on_it["messages"] = []
        policy.choose_key(parse_snapshot(on_it, policy._monrace_knowledge))
        self.assertEqual(policy._trap_warning_cells, {})


class Q25LightCountTest(unittest.TestCase):
    """Owner 2026-11-05 「半端にせず必要数用意すること」: rooms of the real map + what fire burned."""

    BURNED_ON_THE_RECORD = 2  # 4 -> 2, n1-b life-312 turn 11652737 (test_plan_floor_summons_1105_recorded)

    def test_the_number_is_the_rooms_of_the_walk_and_what_fire_burned(self):
        terrain = QUESTS[25].battlefield.terrain
        cells = [tuple(stop["cell"]) for stop in PLAN["stands"]] + [tuple(stop["stand"]) for stop in PLAN["last_targets"]]
        rooms = {quest_room_light.room_of(terrain, cell) for cell in cells}
        self.assertEqual(len(rooms), 10)
        self.assertEqual(STRATEGIES[25].required_force["required_scrolls"]["light"], 10 + self.BURNED_ON_THE_RECORD)

    def test_the_real_file_carries_it_in_the_kit(self):
        policy, snapshot = Q25TownTest().policy_and_snapshot()
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=250.0):
            status = policy._quest_carry_status(snapshot, policy._carry_procurement_strategy(snapshot).required_force)
        self.assertEqual(status["required_scrolls.light"]["required"], 12)


class Q25LightShelfTest(unittest.TestCase):
    """An unbuyable requirement does not stop the town.  DECLARED CONSTRUCTED on Q25TownTest's recorded
    Outpost board; the Alchemist's shelf is built, Light being in its random table (articles-on-sale.cpp)."""

    @staticmethod
    def ware(count, price=20):
        return StoreItem(letter="a", name="Light", count=count, tval=TVAL_SCROLL, sval=SV_LIGHT, price=price, aware=True)

    def at_the_shelf(self, *wares):
        policy, snapshot = Q25TownTest().policy_and_snapshot()
        snapshot = replace(snapshot, player=replace(snapshot.player, gold=100000),
                           store=StoreState(STORE_ALCHEMIST, items=list(wares)))
        return policy, snapshot

    def bought(self, shelf):
        policy, snapshot = self.at_the_shelf(self.ware(shelf))
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=250.0):
            profile = policy._carry_procurement_strategy(snapshot)
            ware = policy._quest_carry_purchase(snapshot, profile)
            self.assertEqual(ware, snapshot.store.items[0])
            return policy._purchase_quantity(snapshot, ware)

    def test_a_full_shelf_buys_what_is_asked_and_a_short_one_what_it_has(self):
        self.assertEqual(self.bought(21), 12)
        self.assertEqual(self.bought(5), 5)

    def test_a_shelf_without_it_leaves_no_alchemist_need_and_no_departure_block(self):
        policy, snapshot = Q25TownTest().policy_and_snapshot()
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=250.0):
            self.assertIn(STORE_ALCHEMIST, {need.store_type for need in policy._enumerate_town_needs(snapshot)
                                            if need.category.startswith("quest-")})
            policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn
            needs = policy._enumerate_town_needs(snapshot)
            self.assertNotIn(STORE_ALCHEMIST, {need.store_type for need in needs if need.category == "quest-scrolls"})
            self.assertIn("required_scrolls.light", policy._abandoned_quest_carry_requirements)
            self.assertNotIn("quest-scrolls", {need.category for need in policy._departure_blocking_town_needs(snapshot)})

    def test_short_of_it_the_quest_is_not_accepted_and_the_town_goes_on(self):
        policy, snapshot = Q25TownTest().policy_and_snapshot()
        policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn
        key = str(policy.choose_key(snapshot))
        self.assertFalse(policy.last_reason.startswith("fixedquest:request"), (key, policy.last_reason))
        self.assertFalse(policy.last_reason.startswith("town:blocked"), (key, policy.last_reason))


class Q25TownTest(unittest.TestCase):
    """Giver and carries on the recorded Outpost board of tests/fixtures/q14-lv8-1102.json.gz.
    DECLARED CONSTRUCTED: its quest rows (every earlier quest finished) and the giver cell."""

    @staticmethod
    def town_board():
        with gzip.open(ROOT / "tests" / "fixtures" / "q14-lv8-1102.json.gz", "rt", encoding="utf-8") as stream:
            raw = json.load(stream)["board"]
        raw["progress"]["quests"] = [
            *[{"fixed": True, "id": quest_id, "level": QUESTS[quest_id].level, "name": "q", "status": 4,
               "type": QUESTS[quest_id].type} for quest_id in (1, 2, 14, 18, 22, 31, 34)],
            {"fixed": True, "id": 25, "level": 48, "name": "haunted house", "status": 0, "type": 6},
        ]
        for cell in raw["grid_map"]["cells"]:
            if cell.get("p") == 14:
                cell["p"] = 25
        return raw

    def policy_and_snapshot(self, **player):
        maps = town_maps()
        policy = ConservativePolicy(town_map=maps[0], town_maps=maps, monrace_knowledge=RACES,
                                    quest_knowledge=QUESTS, quest_strategies=STRATEGIES)
        raw = self.town_board()
        raw["player"].update(max_hp=900, hp=900, **player)
        bolts = next(item for item in BASE["inventory"] if item["tval"] == 18)
        raw["inventory"].append(dict(copy.deepcopy(bolts), count=5, name="bolts (68/shot 181/turn)"))
        bow = next(item for item in BASE["equipment"] if item["slot"] == "bow")
        raw["equipment"] = [item for item in raw["equipment"] if item["slot"] != "bow"] + [copy.deepcopy(bow)]
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(snapshot)
        return policy, snapshot

    def test_ready_is_requested_only_while_the_quest_is_listed_executable(self):
        policy, snapshot = self.policy_and_snapshot()
        self.assertEqual(policy._fixed_quest_head(snapshot).id, 25)
        with patch.object(ConservativePolicy, "_fixed_quest_ready", return_value=True), \
                patch.object(ConservativePolicy, "_fixed_quest_ready_for_travel", return_value=True), \
                patch("hengbot.policy_quest.EXECUTABLE_QUEST_STRATEGY_IDS", EXECUTABLE_QUEST_STRATEGY_IDS - {25}):
            self.assertIsNone(policy._fixed_quest_key(snapshot, []))
        policy, snapshot = self.policy_and_snapshot()
        policy.consume_home_knowledge(())  # read: no owed scan comes first (Q25OptionalCarryTest)
        with patch.object(ConservativePolicy, "_fixed_quest_ready", return_value=True), \
                patch.object(ConservativePolicy, "_fixed_quest_ready_for_travel", return_value=True):
            policy._fixed_quest_key(snapshot, [])
        self.assertTrue(policy.last_reason.startswith("fixedquest:request"), policy.last_reason)

    def test_the_kit_is_bought_from_the_stores_that_sell_it_and_stays_in_the_pack(self):
        policy, snapshot = self.policy_and_snapshot()
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=250.0):
            force = policy._carry_procurement_strategy(snapshot).required_force
            status = policy._quest_carry_status(snapshot, force)
            self.assertEqual((force["heal_potions"], force["speed_potions"]), (5, 3))
            self.assertEqual(status["required_potions.restore_str"]["required"], 2)
            self.assertEqual(status["required_scrolls.teleport"]["required"], 5)
            self.assertEqual(policy._quest_carry_suppliers("required_potions.restore_exp"), (STORE_TEMPLE,))
            self.assertEqual(policy._quest_carry_suppliers("required_potions.restore_str"), (STORE_ALCHEMIST,))
            potion = parse_snapshot(copy.deepcopy(board()), policy._monrace_knowledge).inventory[0]
            restore = replace(potion, tval=TVAL_POTION, sval=SV_POTION_RESTORE_STR)
            self.assertTrue(consumable_policy.carry_required(policy, snapshot, restore))

    def test_a_character_short_of_every_row_keeps_nothing_for_it(self):
        policy, snapshot = self.policy_and_snapshot()
        force = policy._strategy_force_for_snapshot(snapshot, STRATEGIES[25])
        self.assertEqual((force["heal_potions"], force["required_potions"]), (0, {}))


class Q25OptionalCarryTest(unittest.TestCase):
    """Owner 2026-11-05 「Q25の必須要件に啓蒙の薬は入れていないが、自宅にある場合は受注前に持ち出して」.
    DECLARED CONSTRUCTED on Q25TownTest's recorded Outpost board: readiness is pinned true, the catalogue
    is delivered as the knowledge response would be, the potion on the later boards as the withdrawal
    would leave it."""

    WITHDRAW = "home-errand:atomic-withdraw:quest-optional-carry"

    def setUp(self):
        for name in ("_fixed_quest_ready", "_fixed_quest_ready_for_travel"):
            patcher = patch.object(ConservativePolicy, name, return_value=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def potion(snapshot, *, slot="p", count=1):
        row = next(item for item in snapshot.inventory if item.tval == TVAL_POTION) if any(
            item.tval == TVAL_POTION for item in snapshot.inventory) else None
        base = parse_snapshot(copy.deepcopy(board()), RACES).inventory[0] if row is None else row
        return replace(base, slot=slot, count=count, tval=TVAL_POTION, sval=SV_POTION_ENLIGHTENMENT,
                       name="Enlightenment", aware=True, weight=4)

    def town(self):
        """A warrior: the recorded board's Magic-Eater reads its powers first."""
        policy, snapshot = Q25TownTest().policy_and_snapshot(class_id=0)
        policy.consume_skill_knowledge(dict(copy.deepcopy(_CASE["skill"]), turn=snapshot.turn, player=dict(
            _CASE["skill"]["player"], level=snapshot.player.level)))
        return policy, snapshot

    def scanned(self, *, stored=1):
        policy, snapshot = self.town()
        policy.consume_home_knowledge((self.potion(snapshot, slot="a", count=stored),) if stored else ())
        return policy, snapshot

    @staticmethod
    def on_the_entrance(snapshot):
        entrance = next(position for position, grid in snapshot.grids.items() if grid.store_number == STORE_HOME)
        return replace(snapshot, player=replace(snapshot.player, position=entrance))

    @staticmethod
    def decide_on(policy, snapshot):
        return str(policy.choose_key(snapshot)), policy.last_reason

    def with_the_potion(self, snapshot):
        return replace(snapshot, turn=snapshot.turn + 10,
                       inventory=[*snapshot.inventory, self.potion(snapshot)])

    def test_with_one_at_home_it_goes_home_before_the_quest(self):
        policy, snapshot = self.scanned()
        _key, reason = self.decide_on(policy, snapshot)
        self.assertFalse(reason.startswith("fixedquest:request"), reason)
        self.assertEqual(policy._town_claim_categories[0], quest_optional_carry.CATEGORY)
        self.assertEqual(policy._home_errand.request.purpose, quest_optional_carry.PURPOSE)

    def test_only_one_is_taken_of_a_stack(self):
        policy, snapshot = self.scanned(stored=3)
        self.decide_on(policy, snapshot)
        self.assertEqual(policy._home_errand.request.quantity, 1)

    def test_withdrawn_then_the_quest_is_requested(self):
        policy, snapshot = self.scanned()
        entrance = self.on_the_entrance(snapshot)
        key, _reason = self.decide_on(policy, entrance)  # into the Home once: its page size
        policy.confirm_key_posted(key)
        ware = StoreItem(letter="a", name="Enlightenment", count=1, tval=TVAL_POTION, sval=SV_POTION_ENLIGHTENMENT,
                         price=0)
        page = StoreState(STORE_HOME, items=[ware], stock_num=1, page_top=0, page_size=12, capacity=24)
        key, reason = self.decide_on(policy, replace(entrance, turn=entrance.turn + 10, store=page))
        self.assertEqual(reason, "home:leave-for-pending-withdraw")
        policy.confirm_key_posted(key)
        key, reason = self.decide_on(policy, replace(entrance, turn=entrance.turn + 20))
        self.assertEqual(reason, self.WITHDRAW, key)
        self.assertIn("pa", key)
        policy.confirm_key_posted(key)
        carried = self.with_the_potion(replace(entrance, turn=entrance.turn + 30))
        policy.consume_home_knowledge(())
        _key, reason = self.decide_on(policy, carried)
        self.assertTrue(reason.startswith("fixedquest:request"), reason)
        self.assertEqual(policy._home_errand.state.value, "done")

    def test_none_at_home_the_quest_is_requested(self):
        policy, snapshot = self.scanned(stored=0)
        _key, reason = self.decide_on(policy, snapshot)
        self.assertTrue(reason.startswith("fixedquest:request"), reason)

    def test_already_carried_it_is_not_taken_again(self):
        policy, snapshot = self.scanned()
        _key, reason = self.decide_on(policy, replace(snapshot, inventory=[*snapshot.inventory, self.potion(snapshot)]))
        self.assertTrue(reason.startswith("fixedquest:request"), reason)

    def test_the_catalogue_not_known_the_scan_goes_first_and_the_town_does_not_wait_on_it(self):
        policy, snapshot = self.town()
        _key, reason = self.decide_on(policy, snapshot)
        self.assertEqual(reason, "home:request-knowledge-scan")
        # A scan that cannot be had: nothing is known to be there, and the quest goes on.
        policy.confirm_key_posted(_key)
        with patch.object(ConservativePolicy, "_home_catalogue_scan_owed", return_value=False):
            _key, reason = self.decide_on(policy, replace(snapshot, turn=snapshot.turn + 10))
        self.assertTrue(reason.startswith("fixedquest:request"), reason)

    def test_the_catalogue_read_with_one_in_it_it_goes_home(self):
        policy, snapshot = self.town()
        key, _reason = self.decide_on(policy, snapshot)
        policy.confirm_key_posted(key)
        policy.consume_home_knowledge((self.potion(snapshot, slot="a"),))
        self.decide_on(policy, replace(snapshot, turn=snapshot.turn + 10))
        self.assertEqual(policy._home_errand.request.purpose, quest_optional_carry.PURPOSE)

    def test_no_home_in_reach_the_quest_is_requested(self):
        policy, snapshot = self.scanned()
        with patch.object(ConservativePolicy, "_home_available", return_value=False):
            _key, reason = self.decide_on(policy, snapshot)
        self.assertTrue(reason.startswith("fixedquest:request"), reason)

    def test_a_withdrawal_that_failed_is_not_filed_again_this_visit(self):
        policy, snapshot = self.scanned()
        self.decide_on(policy, snapshot)
        policy._home_errand.state = type(policy._home_errand.state).FAILED
        _key, reason = self.decide_on(policy, replace(snapshot, turn=snapshot.turn + 10))
        self.assertTrue(reason.startswith("fixedquest:request"), reason)

    def test_a_stopped_withdrawal_does_not_hold_the_town(self):
        policy, snapshot = self.scanned()
        self.decide_on(policy, snapshot)
        policy._home_errand.state = type(policy._home_errand.state).STOPPED
        policy._home_errand.stopped_fact = "constructed"
        _key, reason = self.decide_on(policy, replace(snapshot, turn=snapshot.turn + 10))
        self.assertTrue(reason.startswith("fixedquest:request"), reason)

    def test_carried_it_is_no_deposit_no_weight_relief_no_sale(self):
        policy, snapshot = self.scanned(stored=0)
        carried = self.with_the_potion(snapshot)
        item = carried.inventory[-1]
        self.assertEqual(policy._retention_reservation_detail(carried, item),
                         (1, quest_optional_carry.RETENTION_BRANCH))
        self.assertEqual(policy._retention_surplus(carried, item), 0)
        self.assertTrue(consumable_policy.carry_required(policy, carried, item))
        self.assertNotIn(item, policy._weight_deposit_candidates(carried))

    def test_at_home_with_it_carried_the_visit_does_not_put_it_back(self):
        policy, snapshot = self.scanned(stored=0)
        carried = self.with_the_potion(snapshot)
        at_home = replace(self.on_the_entrance(carried), store=StoreState(STORE_HOME, items=[], stock_num=0))
        self.assertFalse(policy._home_deposit_candidate(carried.inventory[-1], at_home))
        key, reason = self.decide_on(policy, at_home)
        self.assertNotIn(key[:2], {"dp", "gp"}, (key, reason))

    def test_a_second_carried_is_past_the_plans_count_but_stays_with_the_quest(self):
        policy, snapshot = self.scanned(stored=0)
        two = replace(snapshot, inventory=[*snapshot.inventory, self.potion(snapshot, count=2)])
        self.assertEqual(policy._retention_reservation(two, two.inventory[-1]), 1)

    def test_it_is_no_part_of_the_carry_or_the_kit(self):
        force = STRATEGIES[25].required_force
        self.assertNotIn("enlightenment", force.get("required_potions", {}))
        policy, snapshot = Q25TownTest().policy_and_snapshot()
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=250.0):
            status = policy._quest_carry_status(snapshot, policy._carry_procurement_strategy(snapshot).required_force)
        self.assertFalse(any("enlightenment" in name for name in status))

    def test_stored_it_is_no_home_disposal(self):
        policy, snapshot = self.scanned()
        stored = self.potion(snapshot, slot="a")
        ware = StoreItem(letter="a", name=stored.name, count=1, tval=TVAL_POTION, sval=SV_POTION_ENLIGHTENMENT, price=0)
        at_home = replace(self.on_the_entrance(snapshot), store=StoreState(STORE_HOME, items=[ware], stock_num=1))
        policy._home_disposal_pass = True
        policy._home_disposal_home_key(at_home)
        self.assertFalse(policy._home_disposal_candidates)

    def test_a_plan_without_the_field_files_nothing(self):
        policy, snapshot = self.scanned()
        plain = {**STRATEGIES, 25: replace(STRATEGIES[25], consumable_plan={
            key: value for key, value in STRATEGIES[25].consumable_plan.items() if key != "optional_carry"})}
        with patch.object(policy, "_quest_strategies", plain):
            _key, reason = self.decide_on(policy, snapshot)
        self.assertTrue(reason.startswith("fixedquest:request"), reason)


class _ReadyLight:
    one_shot_quest_entry_ready = True
    one_shot_quest_entry_reject_reason = "light"
    releases_one_shot_quest = False
    worn = None


class Q25AcceptanceTest(unittest.TestCase):
    """The owner's two conditions.  DECLARED CONSTRUCTED: the measured damage is pinned
    and the abilities are the recorded row with the ones this plan and level 48 ask set; the
    ammunition's display is written on the recorded stack's name."""

    ABILITIES = ("see_invisible", "free_action", "resist_conf", "resist_blind", "resist_neth", "resist_pois",
                 "resist_fire", "resist_cold", "resist_elec", "resist_acid", "resist_chaos")

    def town(self, *, max_hp, healing=5, speed=3, resists=True, unhasted_speed=110, shot=68, turn=181, ammo=40,
             teleports=5, restores=2, class_id=None, light=12):
        raw = board(max_hp=max_hp, hp=max_hp, healing=healing, speed=speed, teleports=teleports, light=light)
        raw["floor"].update(quest_id=0, level=0, in_town=True)
        raw["progress"]["quests"][0]["status"] = 0
        raw["player"]["speed"] = unhasted_speed
        if class_id is not None:
            raw["player"]["class_id"] = class_id
        sources = raw["player"]["ability_sources"]
        for name in self.ABILITIES:
            sources.setdefault(name, {})["equipment"] = resists
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] != 18]
        bolts = next(item for item in BASE["inventory"] if item["tval"] == 18)
        raw["inventory"].append(dict(copy.deepcopy(bolts), count=ammo, name=f"bolts ({shot}/shot {turn}/turn)"))
        if restores:
            raw["inventory"] += [_stack(TVAL_POTION, SV_POTION_RESTORE_EXP, restores),
                                 _stack(TVAL_POTION, SV_POTION_RESTORE_STR, restores)]
        return raw

    def verdict(self, raw, damage, *, lists=None):
        policy = new_policy()
        if lists is not None:
            policy._me_device_lists = lists
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=damage), \
                patch.object(ConservativePolicy, "_main_hand_dps", return_value=damage), \
                patch.object(ConservativePolicy, "_inventory_overweight", return_value=False), \
                patch.object(ConservativePolicy, "_temporary_status_clear", return_value=True), \
                patch.object(ConservativePolicy, "_combat_weapon_ready", return_value=True), \
                patch.object(ConservativePolicy, "_light_judgment", return_value=_ReadyLight()):
            ready = policy._evaluate_fixed_quest_readiness(snapshot, 25, require_target_town=False)
            force = policy._strategy_force_for_snapshot(snapshot, STRATEGIES[25])
        return ready, policy._fixed_quest_readiness, force

    def test_condition_1(self):
        ready, telemetry, force = self.verdict(self.town(max_hp=850), 200)
        self.assertTrue(ready, telemetry)
        self.assertEqual((force["min_hp"], force["speed_potions"], force["heal_potions"]), (850, 3, 5))
        self.assertFalse(force.get("always_hasted"))

    def test_condition_2_by_potions_and_by_gear(self):
        ready, telemetry, force = self.verdict(self.town(max_hp=500, speed=8, turn=120), 100)
        self.assertTrue(ready, telemetry)
        self.assertEqual((force["min_hp"], force["speed_potions"], force["heal_potions"]), (500, 8, 5))
        self.assertTrue(force["always_hasted"])
        ready, telemetry, force = self.verdict(self.town(max_hp=500, speed=0, unhasted_speed=120, turn=120), 100)
        self.assertTrue(ready, telemetry)
        self.assertEqual(force["speed_potions"], 0)

    def test_condition_2_by_absorbed_speed_needs_eight_charges(self):
        for charges, accepted in ((8, True), (7, False)):
            with patch("hengbot.me_capability.replaced_by_absorbed", return_value=True), \
                    patch("hengbot.me_capability.charges", return_value=charges), \
                    patch("hengbot.speed_dose.available", return_value=True):
                ready, telemetry, force = self.verdict(self.town(max_hp=500, speed=0, turn=120), 100)
            self.assertEqual(ready, accepted, telemetry)
            self.assertEqual(bool(force.get(quest_force_rows.ABSORBED_SHORT)), not accepted)

    def test_the_turn_figure_picks_the_row(self):
        """A /turn under condition 1's 180 leaves only condition 2, with its eight potions."""
        ready, telemetry, force = self.verdict(self.town(max_hp=900, speed=3, turn=121), 250)
        self.assertFalse(ready)
        self.assertEqual(force["speed_potions"], 8)
        self.assertIn("speed_potions", telemetry["strategy_force"]["failed"])

    def test_controls_refuse(self):
        for raw, damage, failed in (
            (self.town(max_hp=849), 200, "speed_potions"),  # row 2's HP holds, its eight potions do not
            (self.town(max_hp=850), 199, "speed_potions"),
            (self.town(max_hp=499, speed=8), 200, "hp"),
            (self.town(max_hp=850, speed=8), 99, "dps"),
            (self.town(max_hp=850, healing=4), 200, "heal_potions"),
            (self.town(max_hp=850, resists=False), 200, "resists"),
            (self.town(max_hp=850, shot=64), 200, "hp"),   # no qualifying stack: no row
            (self.town(max_hp=850, turn=119), 200, "hp"),
            (self.town(max_hp=850, ammo=39), 200, "throwing_items.launcher_ammo"),
            (self.town(max_hp=850, teleports=4), 200, "required_scrolls.teleport"),
            (self.town(max_hp=850, restores=1), 200, "required_potions.restore_exp"),
        ):
            ready, telemetry, _ = self.verdict(raw, damage)
            self.assertFalse(ready, failed)
            self.assertEqual(telemetry["reason"], "strategy-force", telemetry)

    def test_no_row_buys_nothing(self):
        _, _, force = self.verdict(self.town(max_hp=300, healing=0, speed=0), 40)
        self.assertEqual((force["heal_potions"], force["speed_potions"], force["throwing_items"],
                          force["required_potions"]), (0, 0, {}, {}))

    def test_depth_abilities_and_recall_are_asked(self):
        raw = self.town(max_hp=850)
        raw["player"]["ability_sources"]["resist_chaos"]["equipment"] = False
        ready, telemetry, _ = self.verdict(raw, 200)
        self.assertFalse(ready)
        self.assertEqual(telemetry["reason"], "depth-abilities")
        raw = self.town(max_hp=850)
        raw["inventory"] = [item for item in raw["inventory"]
                            if not (item["tval"] == TVAL_SCROLL and item["sval"] == SV_RECALL)]
        ready, telemetry, _ = self.verdict(raw, 200)
        self.assertFalse(ready)
        self.assertEqual(telemetry["reason"], "no-recall")


class Q25DeviceScoreTest(Q25AcceptanceTest):
    """Class 16 counts absorbed and carried attack devices; every other class does not."""

    @staticmethod
    def _power():
        from hengbot import me_device_attacks
        return next(power for power in me_device_attacks.POWERS.values()
                    if power.kind == "wand" and power.damage(45) >= 200 and not power.group_only)

    def lists(self, success=90, current=40):
        power = self._power()
        return {"wand": (0, [{"name": power.names[0], "current": current, "max": current, "success": success}])}

    def raw(self, class_id=16, **kwargs):
        raw = self.town(max_hp=850, shot=10, turn=10, ammo=0, class_id=class_id, **kwargs)
        raw["player"]["level"] = 45
        return raw

    def test_absorbed_power_meets_the_ranged_requirement(self):
        ready, telemetry, force = self.verdict(self.raw(), 200, lists=self.lists())
        self.assertTrue(ready, telemetry)
        self.assertEqual(force["throwing_items"]["launcher_ammo"], 0)
        self.assertEqual(telemetry["strategy_force"]["ranged"]["shots"]["device"], 40)

    def test_charges_short_of_forty_are_made_up_with_ammunition(self):
        raw = self.town(max_hp=850, shot=68, turn=10, ammo=25, class_id=16)
        raw["player"]["level"] = 45
        ready, telemetry, force = self.verdict(raw, 200, lists=self.lists(current=15))
        self.assertTrue(ready, telemetry)
        self.assertEqual(force["throwing_items"]["launcher_ammo"], 25)

    def test_control_too_few_charges_or_too_low_a_rate_refuses(self):
        ready, telemetry, _ = self.verdict(self.raw(), 200, lists=self.lists(current=39))
        self.assertFalse(ready, telemetry)
        ready, telemetry, _ = self.verdict(self.raw(), 200, lists=self.lists(success=5))
        self.assertFalse(ready, telemetry)

    def test_control_another_class_counts_no_device(self):
        ready, telemetry, _ = self.verdict(self.raw(class_id=0), 200, lists=self.lists())
        self.assertFalse(ready, telemetry)

    def test_a_carried_wand_counts_for_the_class_with_its_use_chance(self):
        from hengbot import me_device_attacks
        power = self._power()
        raw = self.raw()
        raw["inventory"].append(dict(
            copy.deepcopy(next(item for item in BASE["inventory"] if item["tval"] == TVAL_WAND)),
            sval=power.sval, charges=40, count=1, name="wand (40)"))
        policy = new_policy()
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        found = quest_ranged_force.score(policy, snapshot, STRATEGIES[25].required_force["ranged"])
        self.assertGreaterEqual(found.turn, 65)
        self.assertLess(found.turn, me_device_attacks.expected_damage(power, 45, RACES[IPSISSIMUS].flags) + 1)
        self.assertEqual(found.device_shots, 40)


if __name__ == "__main__":
    unittest.main()
