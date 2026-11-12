"""Quest 18 『湖の洞窟』: a constructed playthrough through the public ``choose_key``.

Owner 2026-11-04: 「Q18から直しを入れて実際に受けられるところまでブラッシュアップしよう。」;
「テレポート禁止エリアが設定されているため、テレポートすると必ず中央に飛ばされる。…絶対に回避する
べきである。」; 「隘路で各個撃破することを目標とする。」; 「薬で戦い線より下で帰還」.

DECLARED CONSTRUCTED: no character has played this quest.  The boards are the recorded
n1-c Q31 board of tests/fixtures/once-quest-recall-20261103.json.gz with its floor, grid
map, quest row, position, HP, monsters and carried potions replaced: the grid map from the
real lib/edit/quests/018_WaterCave.jsonc (every cell known), the monsters with the races
and cells of that map.  Its monster data is the real MonraceDefinitions.  A live floor
shows only what the light and memory show; the navigator's route reads the quest map, as
on every approved quest.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

from hengbot import cli, once_quest_recall, quest_exposure, quest_find_exit, quest_force_rows, quest_no_teleport
from hengbot.model import Position, SV_POTION_HEALING, SV_POTION_SPEED, TVAL_POTION, TVAL_SCROLL, parse_snapshot
from hengbot.model import _GRID_TERRAIN_NAMES
from hengbot.monrace_knowledge import _strip_jsonc, find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import REST_MACRO, WAIT_KEY
from hengbot.quest_find_exit import (
    DIG_REASON, HEAL_REASON, HOLD_REASON, CLEAR_REASON, PULL_REFUSED_REASON, PULL_WALK_REASON, PULLED_BACK_REASON, MELEE_REASON, RECALL_REASON, SPEED_REASON, STEP_ON_EXIT_REASON,
    TO_CHOKE_REASON, WALK_REASON,
)
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests.test_q14_heal_ccw_recorded import town_maps

ROOT = Path(__file__).parents[1]
GAME = Path("C:/hengband/lib/edit")
with gzip.open(ROOT / "tests" / "fixtures" / "once-quest-recall-20261103.json.gz", "rt",
               encoding="utf-8") as _stream:
    _CASE = json.load(_stream)
BASE = _CASE["boards"][0]
QUEST = json.loads(_strip_jsonc((GAME / "quests" / "018_WaterCave.jsonc").read_text(encoding="utf-8")))
TERRAINS = {row["key"]: row for row in json.loads(_strip_jsonc(
    (GAME / "TerrainDefinitions.jsonc").read_text(encoding="utf-8")))["terrains"]}
RACES = load_monrace_knowledge(find_monrace_definitions(ROOT, None) or GAME / "MonraceDefinitions.jsonc")
QUESTS = load_quest_knowledge(find_quest_definitions(ROOT) or GAME / "quests")
STRATEGIES = load_quest_strategies(ROOT / "strategy" / "quests")
with gzip.open(ROOT / "tests" / "fixtures" / "q18-live-20261104.json.gz", "rt", encoding="utf-8",
               errors="surrogateescape") as _stream:
    LIVE = {row["turn"]: row for row in json.load(_stream)["boards"]}
ENTRANCE, EXIT, LAST_CELL = (1, 2), (1, 22), (1, 23)
SQUID, SEAHORSE, SIREN, KRAKEN, SHARK = 482, 443, 1272, 775, 386
SV_PHASE, SV_TELEPORT, SV_RECALL = 8, 9, 11
FULL_HP = 800
AMMO_TVALS = {16, 17, 18}


def _cell_terrain(glyph: str) -> str:
    return "PERMANENT" if glyph == "X" else QUEST["legend"][glyph]["terrain"]


def _palette_row(terrain_key: str) -> list[int]:
    row = TERRAINS[terrain_key]
    flags = {flag.lower() for flag in row["flags"]}
    bits = sum(1 << index for index, name in enumerate(_GRID_TERRAIN_NAMES) if name in flags)
    return [row["id"], 2, bits, 1]


def _grid_map() -> dict:
    keys = sorted({_cell_terrain(glyph) for line in QUEST["map"] for glyph in line})
    return {
        "cells": [], "found_item_ids": [], "found_item_names": [], "found_items": [],
        "h": len(QUEST["map"]), "w": len(QUEST["map"][0]),
        "palette": [_palette_row(key) for key in keys],
        "runs": [[y, x, 1, keys.index(_cell_terrain(glyph))]
                 for y, line in enumerate(QUEST["map"]) for x, glyph in enumerate(line)],
        "unsafe_rows": [],
    }


def monster(race, y, x, *, index=None, asleep=False):
    return {"asleep": asleep, "confused": False, "fast": False, "fearful": False,
            "friendly": False, "health": "unhurt", "index": index or race, "invulnerable": False,
            "level": RACES[race].level, "name": f"race{race}", "pet": False, "race_id": race,
            "slow": False, "stunned": False, "x": x, "y": y}


def open_cell(raw, cell):
    """The vein as the game leaves it: DESTROYED is DEEP_WATER."""
    grid_map = raw["grid_map"]
    if _palette_row("DEEP_WATER") not in grid_map["palette"]:
        grid_map["palette"].append(_palette_row("DEEP_WATER"))
    index = grid_map["palette"].index(_palette_row("DEEP_WATER"))
    for run in grid_map["runs"]:
        if (run[0], run[1]) == cell:
            run[3] = index


def potion(sval, count):
    row = next(item for item in BASE["inventory"] if item["tval"] == TVAL_POTION)
    return dict(copy.deepcopy(row), sval=sval, count=count, name=f"potion{sval}")


def board(position=ENTRANCE, *, hp=FULL_HP, monsters=(), healing=2, speed=1, teleports=True,
          recalling=False, max_hp=FULL_HP, ammo=True):
    """DECLARED CONSTRUCTED, see the module note."""
    raw = copy.deepcopy(BASE)
    raw["floor"].update(quest_id=18, level=1, height=len(QUEST["map"]), width=len(QUEST["map"][0]))
    raw["grid_map"] = _grid_map()
    raw["progress"]["quests"] = [
        {"fixed": True, "id": 18, "level": 35, "name": "water cave", "status": 1, "type": 4},
        *[row for row in raw["progress"]["quests"] if row["id"] != 18 and row["id"] != 31],
    ]
    raw["player"].update(y=position[0], x=position[1], hp=hp, max_hp=max_hp, recalling=recalling)
    kept = [item for item in raw["inventory"]
            if not (item["tval"] == TVAL_POTION and item["sval"] in {SV_POTION_HEALING, SV_POTION_SPEED})
            and (teleports or not (item["tval"] == TVAL_SCROLL and item["sval"] in {SV_PHASE, SV_TELEPORT}))]
    raw["inventory"] = kept + [
        potion(sval, count) for sval, count in ((SV_POTION_HEALING, healing), (SV_POTION_SPEED, speed))
        if count]
    if not ammo:
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in AMMO_TVALS]
    raw["visible_monsters"] = [dict(row) for row in monsters]
    raw["detected_monsters"] = []
    raw["messages"] = []
    return raw


def new_policy(primed=None):
    policy = ConservativePolicy(monrace_knowledge=RACES, quest_knowledge=QUESTS,
                                quest_strategies=STRATEGIES)
    first = copy.deepcopy(primed or BASE)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(_CASE["skill"]), turn=first["turn"],
        player=dict(_CASE["skill"]["player"], level=first["player"]["level"])))
    return policy


def decide(raw, *, primed=None):
    policy = new_policy(primed or raw)
    key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
    return key, policy.last_reason, policy


DIRECTION = {(-1, -1): "7", (-1, 0): "8", (-1, 1): "9", (0, -1): "4", (0, 1): "6",
             (1, -1): "1", (1, 0): "2", (1, 1): "3"}


def step_key(start, goal):
    return DIRECTION[(goal[0] - start[0], goal[1] - start[1])]


class Q18MapFactsTest(unittest.TestCase):
    def test_map_facts_the_plan_rests_on(self):
        battlefield = QUESTS[18].battlefield
        self.assertEqual(battlefield.player_start, ENTRANCE)
        self.assertEqual(battlefield.exit, EXIT)
        self.assertEqual(battlefield.terrain[(19, 16)], "wall")  # the magma beside the kraken

    def test_each_choke_cell_is_the_corridor_the_plan_says(self):
        terrain = QUESTS[18].battlefield.terrain
        passable = {"deep_water", "shallow_water", "exit"}

        def neighbours(cell):
            return {(cell[0] + dy, cell[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if (dy, dx) != (0, 0) and terrain.get((cell[0] + dy, cell[1] + dx)) in passable}

        plan = STRATEGIES[18].engagement_plan["find_exit"]
        self.assertEqual(plan["choke_cells"],
                         [[1, 3], [1, 5], [1, 9], [1, 12], [1, 15], [1, 19], [3, 22], [2, 26], [1, 24]])
        self.assertEqual(neighbours((1, 3)), {(1, 2), (1, 4)})
        self.assertEqual(neighbours((1, 5)), {(1, 4), (2, 6)})
        self.assertEqual(neighbours((1, 9)), {(1, 8), (1, 10)})
        self.assertEqual(neighbours((1, 12)), {(2, 11), (2, 13)})
        self.assertEqual(neighbours((1, 15)), {(1, 14), (1, 16)})
        self.assertEqual(neighbours((1, 19)), {(2, 18), (2, 20)})
        self.assertEqual(neighbours((3, 22)), {(4, 21), (4, 22)})
        self.assertEqual(neighbours((2, 26)), {(3, 25), (1, 25)})
        self.assertEqual(neighbours((1, 24)), {(1, 23), (1, 25)})
        self.assertEqual(neighbours(LAST_CELL), {EXIT, (1, 24)})
        self.assertEqual(neighbours(EXIT), {LAST_CELL})


LEAST_EXPOSED_ROUTE = [
    (1, 2), (1, 3), (1, 4), (1, 5), (2, 6), (2, 7), (1, 8), (1, 9), (1, 10), (2, 11), (1, 12), (2, 13),
    (1, 14), (1, 15), (1, 16), (1, 17), (2, 18), (1, 19), (2, 20), (3, 20), (4, 21), (4, 22), (5, 23),
    (5, 24), (6, 25), (5, 26), (4, 26), (3, 25), (2, 26), (1, 25), (1, 24), (1, 23), (1, 22)]
EXPOSED_ON_ROUTE = [(2, 6), (2, 7), (1, 16), (1, 17), (2, 18), (5, 24), (6, 25), (5, 26), (4, 26)]
DUG_ROUTE = [
    (1, 2), (1, 3), (1, 4), (1, 5), (2, 6), (1, 7), (1, 8), (1, 9), (1, 10), (2, 11), (1, 12), (2, 13),
    (1, 14), (1, 15), (1, 16), (1, 17), (2, 18), (1, 19), (2, 20), (3, 20), (4, 21), (4, 22), (5, 23),
    (5, 24), (5, 25), (4, 26), (3, 25), (2, 26), (1, 25), (1, 24), (1, 23), (1, 22)]
EXPOSED_ON_DUG_ROUTE = [(2, 6), (1, 16), (1, 17), (2, 18), (5, 24), (5, 25), (4, 26)]
# Every cell a shriek was recorded on, 2026-11-04 18:40-18:45 (n1-a 47, n1-b 76).
RECORDED_SHRIEK_CELLS = {(4, 13): 47, (9, 21): 31, (15, 9): 17, (10, 21): 12, (14, 7): 11,
                         (4, 18): 2, (15, 8): 2, (11, 22): 1}


class Q18ExposureTest(unittest.TestCase):
    def setUp(self):
        battlefield = QUESTS[18].battlefield
        self.terrain = battlefield.terrain
        self.sirens = [cell for cell, race in battlefield.monster_placements if race == SIREN]
        self.exposure = quest_exposure.exposure_map(self.terrain, self.sirens)

    def test_every_recorded_shriek_cell_comes_out_exposed(self):
        for cell in RECORDED_SHRIEK_CELLS:
            self.assertTrue(self.exposure.exposed(cell), cell)

    def test_the_cell_no_siren_sees_is_reached_through_its_neighbour(self):
        self.assertNotIn((4, 13), self.exposure.pull)
        self.assertFalse(quest_exposure.projectable(self.terrain, (6, 14), (4, 13)))
        self.assertTrue(quest_exposure.projectable(self.terrain, (6, 14), (5, 12)))
        self.assertIn((6, 14), self.exposure.shout[(4, 13)])

    def test_the_recorded_pulls_had_the_direct_line_and_landed_in_the_centre(self):
        # n1-b seq 3617 stepped from (4,18) to (4,19); the next board stands at (15,8).
        self.assertIn((16, 8), self.exposure.pull[(4, 19)])
        self.assertEqual(quest_exposure.game_distance((16, 8), (4, 19)), 17)
        self.assertNotIn((9, 22), self.exposure.pull.get((15, 9), ()))  # the second took two pulls
        self.assertIn((16, 8), self.exposure.pull[(15, 9)])
        self.assertIn((9, 22), self.exposure.pull[(15, 8)])

    def test_no_route_takes_fewer_exposed_cells_and_the_recorded_ones_took_more(self):
        route = quest_exposure.least_exposed_path(self.terrain, self.exposure, ENTRANCE, {EXIT})
        self.assertEqual(route, LEAST_EXPOSED_ROUTE)
        self.assertEqual([cell for cell in route if self.exposure.exposed(cell)], EXPOSED_ON_ROUTE)
        self.assertEqual([cell for cell in route if cell in self.exposure.pull], [(6, 25), (5, 26)])

    def test_every_choke_is_out_of_reach(self):
        for cell in STRATEGIES[18].engagement_plan["find_exit"]["choke_cells"]:
            self.assertFalse(self.exposure.exposed(tuple(cell)), cell)


class Q18ExposedCellTest(unittest.TestCase):
    """DECLARED CONSTRUCTED boards, cells from the real map."""

    def test_no_rest_on_an_exposed_cell_it_walks_on(self):
        key, reason, _ = decide(board((1, 16), hp=400))
        self.assertEqual((key, reason), (step_key((1, 16), (1, 17)), WALK_REASON))

    def test_no_hold_on_an_exposed_cell_with_an_enemy_coming(self):
        key, reason, _ = decide(board((2, 7), monsters=[monster(SHARK, 5, 9)], ammo=False))
        self.assertEqual((key, reason), (step_key((2, 7), (1, 8)), WALK_REASON))

    def test_no_chosen_fight_on_an_exposed_cell(self):
        key, reason, _ = decide(board((2, 7), monsters=[monster(SHARK, 3, 8)], speed=0))
        self.assertEqual((key, reason), (step_key((2, 7), (1, 8)), WALK_REASON))

    def test_a_monster_is_struck_when_the_only_other_step_is_a_pull_cell(self):
        # (2,17) goes on too, but a caster's direct line reaches it.
        squid = monster(SQUID, 1, 17)
        key, reason, _ = decide(board((1, 16), monsters=[squid], speed=0))
        self.assertEqual((key, reason), (step_key((1, 16), (1, 17)), MELEE_REASON))

    def test_survival_still_comes_first_on_an_exposed_cell(self):
        shark = monster(SHARK, 3, 8)
        self.assertEqual(decide(board((2, 7), hp=300, monsters=[shark], speed=0))[1], RECALL_REASON)
        self.assertEqual(decide(board((2, 7), hp=500, monsters=[shark], speed=0))[1], HEAL_REASON)

    def test_after_the_recorded_pulls_it_walks_on_by_the_least_exposed_way(self):
        # n1-b seq 3618 at (15,8) (melee then hold beside the siren) and seq 3636 at (9,21)
        # (melee beside the siren), monsters as logged.
        first = [monster(292, 13, 6), monster(SIREN, 16, 8), monster(SEAHORSE, 17, 7, index=2)]
        _, reason, _ = decide(board((15, 8), monsters=first, hp=FULL_HP))
        self.assertEqual(reason, PULLED_BACK_REASON)
        second = [monster(SHARK, 9, 20), monster(SIREN, 9, 22), monster(SEAHORSE, 10, 20),
                  monster(406, 10, 18), monster(SQUID, 11, 22)]
        _, reason, _ = decide(board((9, 21), monsters=second, hp=FULL_HP))
        self.assertIn(reason, {PULLED_BACK_REASON, MELEE_REASON})
        exposure = quest_exposure.exposure_map(
            QUESTS[18].battlefield.terrain,
            [cell for cell, race in QUESTS[18].battlefield.monster_placements if race == SIREN])
        path = quest_exposure.least_exposed_path(QUESTS[18].battlefield.terrain, exposure, (9, 21), {EXIT})
        self.assertEqual(path[-1], EXIT)
        self.assertLess(sum(exposure.exposed(cell) for cell in path), len(path))


class Q18RecordedBoardsTest(unittest.TestCase):
    """The recorded n1-a boards (tests/fixtures/q18-live-20261104.json.gz,
    tests/extract_q18_live_fixture.py) with this plan; the recorded keys are in the rows."""

    @staticmethod
    def replay(turn):
        raw = LIVE[turn]
        return raw["player"]["y"], raw["player"]["x"], decide(raw)[:2]

    def test_the_walk_turns_north_off_the_recorded_lake_crossing(self):
        # Recorded: '3' to (3,8), past the sleeper.  (1,8), the only way north, holds it.
        y, x, (key, reason) = self.replay(2723388)
        self.assertEqual((y, x), (2, 7))
        self.assertEqual((key, reason), (step_key((2, 7), (1, 8)), MELEE_REASON))

    def test_no_hold_on_4_13_with_the_seahorse_coming(self):
        # (4,13) is exposed: the waiting happens on the next free choke, not here.
        y, x, (_, reason) = self.replay(2723443)  # recorded: a shot, holding here
        self.assertEqual((y, x), (4, 13))
        self.assertEqual(reason, WALK_REASON)

    def test_the_recorded_seahorse_board_on_the_free_choke_waits(self):
        """DECLARED CONSTRUCTED: the recorded board, player moved to the choke (1,12),
        the recorded seahorse on (3,11) two cells off."""
        raw = copy.deepcopy(LIVE[2723443])
        raw["player"].update(y=1, x=12)
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in AMMO_TVALS]
        raw["equipment"] = [item for item in raw["equipment"] if item["slot"] != "bow"]
        self.assertEqual(decide(raw)[:2], (WAIT_KEY, HOLD_REASON))

    def test_below_the_line_recall_is_still_read(self):
        y, x, (key, reason) = self.replay(2723779)  # recorded: the same read
        self.assertEqual((y, x), (4, 13))
        self.assertEqual(reason, RECALL_REASON)
        self.assertTrue(key.startswith("r"))


class Q18DigTest(unittest.TestCase):
    """Owner 2026-11-04 「簡単に掘れるので道具がなくても必ず掘る。」.  DECLARED CONSTRUCTED boards."""

    def test_both_digs_with_no_tool(self):
        raw = board((2, 6))
        self.assertFalse(any(item.get("tval") == 20 for item in raw["equipment"]))
        self.assertEqual(decide(raw)[:2], ("T" + step_key((2, 6), (1, 7)), DIG_REASON))
        self.assertEqual(decide(board((5, 24)))[:2], ("T" + step_key((5, 24), (5, 25)), DIG_REASON))

    def test_a_dug_cell_is_walked(self):
        for start, cell in (((2, 6), (1, 7)), ((5, 24), (5, 25))):
            raw = board(start)
            open_cell(raw, cell)
            self.assertEqual(decide(raw)[:2], (step_key(start, cell), WALK_REASON))

    def test_the_exposure_is_of_the_floor_as_dug(self):
        terrain = QUESTS[18].battlefield.terrain
        sirens = [cell for cell, race in QUESTS[18].battlefield.monster_placements if race == SIREN]
        dug = {**terrain, (1, 7): "deep_water", (5, 25): "deep_water"}
        exposure = quest_exposure.exposure_map(dug, sirens)
        route = quest_exposure.least_exposed_path(dug, exposure, ENTRANCE, {EXIT})
        self.assertEqual(route, DUG_ROUTE)
        self.assertEqual([cell for cell in route if exposure.exposed(cell)], EXPOSED_ON_DUG_ROUTE)
        for cell in STRATEGIES[18].engagement_plan["find_exit"]["choke_cells"]:
            self.assertFalse(exposure.exposed(tuple(cell)), cell)

    def test_a_coming_enemy_is_answered_at_the_choke_first(self):
        coming = board((2, 6), monsters=[monster(SHARK, 6, 6)], speed=0, ammo=False)
        self.assertEqual(decide(coming)[:2], (step_key((2, 6), (1, 5)), TO_CHOKE_REASON))

    def test_the_bound_falls_back_to_the_undug_route(self):
        raw = board((2, 6))
        policy = new_policy(raw)
        limit = STRATEGIES[18].engagement_plan["find_exit"]["dig_attempt_limit"]
        rows = []
        for _ in range(limit + 1):
            raw["turn"] += 10
            key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
            rows.append((key, policy.last_reason))
        self.assertEqual(rows[:limit], [("T" + step_key((2, 6), (1, 7)), DIG_REASON)] * limit)
        self.assertEqual(rows[limit], (step_key((2, 6), (2, 7)), WALK_REASON))


class Q18VeinWillNotOpenTest(unittest.TestCase):
    """Owner 2026-11-04 「可能な限り多くのモンスターを事前に倒してから引き寄せのマスを進む」.
    DECLARED CONSTRUCTED: the digging rating, and a floor already emptied of monsters."""

    @staticmethod
    def no_digger(position=(5, 24), **kwargs):
        raw = board(position, **kwargs)
        raw["player"]["skill_ratings"]["digging"]["value"] = 10
        return raw

    def walk(self, policy, raw, limit):
        position = (raw["player"]["y"], raw["player"]["x"])
        reasons = []
        for _ in range(limit):
            raw["player"].update(y=position[0], x=position[1])
            raw["turn"] += 10
            key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
            reasons.append(policy.last_reason)
            delta = next((offset for offset, value in DIRECTION.items() if value == key), None)
            self.assertIsNotNone(delta, (position, key, policy.last_reason))
            position = (position[0] + delta[0], position[1] + delta[1])
            yield position, policy.last_reason

    def test_it_clears_first_then_steps_on_the_pull_cell(self):
        raw = self.no_digger()
        policy = new_policy(raw)
        pull = quest_exposure.exposure_map(
            QUESTS[18].battlefield.terrain,
            [cell for cell, race in QUESTS[18].battlefield.monster_placements if race == SIREN]).pull
        seen = []
        for position, reason in self.walk(policy, raw, 900):
            seen.append(reason)
            if position in pull:
                break
        self.assertEqual(position, (6, 25))
        self.assertEqual(reason, PULL_WALK_REASON)
        self.assertIn(CLEAR_REASON, seen)
        navigator = policy._quest_navigators[18]
        self.assertTrue(navigator.exit_clearing_done)
        self.assertGreater(len(navigator.exit_cleared_placements), 10)

    def test_control_an_awake_enemy_that_comes_keeps_it_off_the_pull_cells(self):
        raw = self.no_digger(monsters=[monster(SHARK, 4, 21)], speed=0, ammo=False)
        key, reason, _ = decide(raw)
        self.assertNotEqual(key, step_key((5, 24), (6, 25)))
        self.assertNotIn(reason, {PULL_WALK_REASON, PULL_REFUSED_REASON})

    def test_the_clearing_cannot_freeze(self):
        raw = self.no_digger(monsters=[monster(SHARK, 4, 21)], speed=0, ammo=False)
        policy = new_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.choose_key(snapshot)
        navigator = policy._quest_navigators[18]
        navigator.exit_clear_turns = STRATEGIES[18].engagement_plan["find_exit"]["clear_turn_limit"]
        raw["turn"] += 10
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (step_key((5, 24), (6, 25)), PULL_WALK_REASON))

    def test_below_the_line_with_an_enemy_recall_still_comes_first(self):
        raw = self.no_digger(hp=300, monsters=[monster(SHARK, 5, 23)], speed=0)
        self.assertEqual(decide(raw)[1], RECALL_REASON)


class Q18PullCellTest(unittest.TestCase):
    """Owner 2026-11-04 「テレポートバックは確実に避けるべきなので条件を把握すること。」"""

    def setUp(self):
        self.terrain = QUESTS[18].battlefield.terrain
        self.sirens = [cell for cell, race in QUESTS[18].battlefield.monster_placements if race == SIREN]

    def test_the_undug_route_has_two_pull_cells_and_the_dug_route_none(self):
        undug = quest_exposure.exposure_map(self.terrain, self.sirens)
        self.assertEqual([cell for cell in LEAST_EXPOSED_ROUTE if cell in undug.pull], [(6, 25), (5, 26)])
        dug = quest_exposure.exposure_map({**self.terrain, (1, 7): "deep_water", (5, 25): "deep_water"}, self.sirens)
        self.assertEqual([cell for cell in DUG_ROUTE if cell in dug.pull], [])

    def test_a_pull_needs_the_direct_line_a_shout_only_a_neighbour(self):
        exposure = quest_exposure.exposure_map(self.terrain, self.sirens)
        self.assertIn((4, 26), exposure.shout)
        self.assertNotIn((4, 26), exposure.pull)
        self.assertTrue(quest_exposure.projectable(self.terrain, (9, 22), (5, 26)))
        self.assertFalse(quest_exposure.projectable(self.terrain, (9, 22), (4, 26)))

    def test_no_rung_steps_onto_a_pull_cell_around_the_east_door(self):
        pull = quest_exposure.exposure_map(self.terrain, self.sirens).pull
        cells = ((5, 24), (4, 26), (5, 23), (3, 25))
        for position in cells:
            neighbours = [(position[0] + dy, position[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                          if (dy, dx) != (0, 0)
                          and self.terrain.get((position[0] + dy, position[1] + dx)) in {"deep_water", "shallow_water"}]
            sets = [(), *[[monster(SHARK, *cell)] for cell in neighbours],
                    [monster(SQUID, *cell) for cell in neighbours],
                    [monster(SHARK, position[0] + 3, position[1] - 3)]]
            for monsters in sets:
                for hp in (FULL_HP, 500, 300, 100):
                    for healing in (2, 0):
                        raw = board(position, hp=hp, monsters=monsters, healing=healing, speed=0, ammo=False)
                        key, reason, _ = decide(raw)
                        delta = next((offset for offset, value in DIRECTION.items() if value == key), None)
                        if delta is None:
                            continue
                        target = (position[0] + delta[0], position[1] + delta[1])
                        occupied = {(row["y"], row["x"]) for row in monsters}
                        self.assertFalse(target in pull and target not in occupied, (position, monsters, hp, reason))

    def test_the_net_refuses_every_other_walker(self):
        policy = new_policy(board((5, 24)))
        snapshot = parse_snapshot(board((5, 24)), policy._monrace_knowledge)
        policy.last_reason = "flee"
        self.assertEqual(policy._step_toward(snapshot, Position(6, 25)), WAIT_KEY)
        self.assertEqual(policy.last_reason, PULL_REFUSED_REASON)

    def test_a_player_on_a_pull_cell_takes_the_way_back_by_name(self):
        key, reason, _ = decide(board((6, 25)))
        self.assertEqual(reason, PULLED_BACK_REASON)
        self.assertIn(key, {step_key((6, 25), (5, 24))})
        _, reason, _ = decide(board((15, 8)))
        self.assertEqual(reason, PULLED_BACK_REASON)


class Q18ClearBeforeAdvancingTest(unittest.TestCase):
    """Owner 2026-11-04 「隘路で敵を十分倒してから先に進むことを明記する」."""

    CHOKE, NEXT = (1, 12), (2, 13)

    def run_boards(self, boards):
        policy = new_policy(boards[0])
        rows = []
        for turn, raw in enumerate(boards):
            raw = copy.deepcopy(raw)
            raw["turn"] = BASE["turn"] + 10 * (turn + 1)
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            rows.append((key, policy.last_reason))
        return rows

    def test_it_waits_kills_then_advances_after_the_quiet_bound(self):
        """DECLARED CONSTRUCTED: the recorded n1-a seahorse (seq 1489, 443 two cells off) on
        this plan's choke, then adjacent, then dead."""
        coming = board(self.CHOKE, monsters=[monster(SEAHORSE, 2, 11 - 1)], speed=0, ammo=False)
        adjacent = board(self.CHOKE, monsters=[monster(SEAHORSE, 2, 11)], speed=0, ammo=False)
        clear = board(self.CHOKE, speed=0, ammo=False)
        bound = STRATEGIES[18].engagement_plan["find_exit"]["choke_hold_turns"]
        rows = self.run_boards([coming, adjacent, adjacent, *[clear] * (bound + 1)])
        self.assertEqual(rows[0], (WAIT_KEY, HOLD_REASON))
        self.assertEqual(rows[1], (step_key(self.CHOKE, (2, 11)), MELEE_REASON))
        self.assertEqual(rows[2], (step_key(self.CHOKE, (2, 11)), MELEE_REASON))
        self.assertEqual(rows[3:3 + bound], [(WAIT_KEY, HOLD_REASON)] * bound)
        self.assertEqual(rows[3 + bound], (step_key(self.CHOKE, self.NEXT), WALK_REASON))

    def test_control_nothing_fought_advances_at_once(self):
        self.assertEqual(self.run_boards([board(self.CHOKE)]),
                         [(step_key(self.CHOKE, self.NEXT), WALK_REASON)])

    def test_hurt_with_no_enemy_rests_before_the_wait_and_the_walk(self):
        self.assertEqual(self.run_boards([board(self.CHOKE, hp=FULL_HP // 2)]), [(REST_MACRO, "rest")])

    def test_an_enemy_known_beside_the_next_leg_holds_and_a_far_one_does_not_for_long(self):
        near = board(self.CHOKE)
        near["detected_monsters"] = [dict(monster(SHARK, 1, 15), perception="detected")]
        self.assertEqual(self.run_boards([near]), [(WAIT_KEY, HOLD_REASON)])

    def test_an_aquatic_enemy_in_a_sealed_pocket_does_not_freeze_it(self):
        sealed = board(self.CHOKE, monsters=[monster(SHARK, 18, 15)], ammo=False)
        self.assertEqual(self.run_boards([sealed]), [(step_key(self.CHOKE, self.NEXT), WALK_REASON)])

    def test_a_siren_in_view_does_not_freeze_it(self):
        seen = board(self.CHOKE, monsters=[monster(SIREN, 6, 14)], ammo=False)
        self.assertEqual(self.run_boards([seen]), [(step_key(self.CHOKE, self.NEXT), WALK_REASON)])

    def test_a_sleeper_in_the_only_way_is_shot_from_the_choke_or_struck_beside_it(self):
        sleeper = monster(SQUID, 2, 11, asleep=True)
        self.assertTrue(self.run_boards([board((1, 9), monsters=[sleeper])])[0][1].startswith("ranged:"))
        self.assertEqual(self.run_boards([board((1, 9), monsters=[sleeper], ammo=False)]),
                         [(step_key((1, 9), (1, 10)), WALK_REASON)])
        beside = monster(SQUID, *self.NEXT, asleep=True)
        self.assertEqual(self.run_boards([board(self.CHOKE, monsters=[beside], ammo=False)]),
                         [(step_key(self.CHOKE, self.NEXT), MELEE_REASON)])

    def test_a_sleeper_beside_the_next_choke_is_shot_and_one_off_the_route_is_left(self):
        beside = monster(SQUID, 1, 16, asleep=True)  # beside the next choke (1,15)
        self.assertTrue(self.run_boards([board(self.CHOKE, monsters=[beside])])[0][1].startswith("ranged:"))
        off_route = monster(SQUID, 3, 3, asleep=True)
        self.assertEqual(self.run_boards([board(self.CHOKE, monsters=[off_route])]),
                         [(step_key(self.CHOKE, self.NEXT), WALK_REASON)])

    def test_an_exposed_cell_still_walks_on(self):
        self.assertEqual(self.run_boards([board((2, 7), monsters=[monster(SHARK, 3, 8)], speed=0)]),
                         [(step_key((2, 7), (1, 8)), WALK_REASON)])


def detected(race, y, x, *, index):
    return dict(monster(race, y, x, index=index), perception="detected")


class Q18FarEnemyThatDoesNotComeTest(unittest.TestCase):
    """Owner 2026-11-06 「n1-a が35階の水の洞窟で、隘路へ向かう歩きと出口へ向かう歩きを1マスごと
    に交互に選んで止まった。来ない遠くの敵を理由に隘路へ戻らないようにし…」.

    DECLARED CONSTRUCTED from the n1-a incidents (lives 490 and 491, floor (0,35,18)): the
    player's cells, the spent chokes, the ESP-detected movers' races and cells as the decision
    logs and the investigator recorded them; the rest is this module's board.
    """

    SPENT = frozenset({Position(1, 9), Position(1, 12), Position(1, 15)})

    def walk(self, start, boards_monsters, *, spent=frozenset(), dug=(), visible=()):
        """One decision per entry of ``boards_monsters`` (the detected monsters of that
        board); the player moves by each step key, as the game would."""
        raw = board(start, monsters=list(visible), speed=0, ammo=False)
        for cell in dug:
            open_cell(raw, cell)
        policy = new_policy(raw)
        position, rows = start, []
        for detected_now in boards_monsters:
            raw["player"].update(y=position[0], x=position[1])
            raw["detected_monsters"] = [dict(row) for row in detected_now]
            raw["turn"] += 10
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            if spent and not rows:  # the live floor had spent them before this stretch
                quest_find_exit._navigator(policy, snapshot, 18).exit_spent_chokes = spent
            key = str(policy.choose_key(snapshot))
            rows.append((position, key, policy.last_reason))
            delta = next((offset for offset, value in DIRECTION.items() if value == key), None)
            if delta is not None:
                position = (position[0] + delta[0], position[1] + delta[1])
        return rows

    def test_life_490_a_seahorse_stepping_in_place_far_off_does_not_send_it_back(self):
        """n1-a life 490: on (1,8), chokes (1,9) (1,12) (1,15) spent, HP full, the seahorse
        443 two rows of water away stepping (9,6) <-> (10,6) the whole time.  It stepped to
        the choke (1,5) through the shouted (2,7), and from there back to the exit, 20 times."""
        jitter = [[detected(SEAHORSE, 9 + turn % 2, 6, index=77)] for turn in range(8)]
        rows = self.walk((1, 8), jitter, spent=self.SPENT)
        self.assertNotIn(TO_CHOKE_REASON, [reason for _, _, reason in rows], rows)
        cells = [cell for cell, _, _ in rows]
        self.assertEqual(len(cells), len(set(cells)), rows)  # never back on a cell
        self.assertEqual(rows[0][1:], (step_key((1, 8), (1, 9)), WALK_REASON))
        self.assertGreater(cells[-1][1], 12, rows)

    def test_control_a_far_seahorse_that_closes_in_still_sends_it_to_the_choke(self):
        """The same board with the seahorse closing one cell a turn: after two cells it comes,
        and the walk goes to the choke and keeps going on the shouted (2,7)."""
        closing = [[detected(SEAHORSE, y, 6, index=77)] for y in (7, 6, 5, 4)]
        rows = self.walk((1, 8), closing, spent=self.SPENT)
        self.assertEqual([reason for _, _, reason in rows[:2]], [WALK_REASON, WALK_REASON], rows)
        self.assertEqual(rows[2][2], TO_CHOKE_REASON, rows)
        cell = rows[2][0]
        self.assertEqual(rows[3][2], TO_CHOKE_REASON, rows)
        self.assertNotEqual(rows[3][0], cell)

    def test_the_walk_to_a_choke_goes_on_over_a_shouted_cell(self):
        """n1-a life 490: (1,8) chose the choke (1,5) through the shouted (2,7), and (2,7) chose
        the exit back through (1,8).  With a seahorse that comes (here in view), (2,7) goes on
        to the choke."""
        rows = self.walk((1, 8), [[]] * 3, spent=self.SPENT, visible=[monster(SEAHORSE, 7, 6)])
        self.assertEqual(rows[0], ((1, 8), step_key((1, 8), (2, 7)), TO_CHOKE_REASON), rows)
        self.assertEqual(rows[1][0], (2, 7), rows)
        self.assertEqual(rows[1][2], TO_CHOKE_REASON, rows)
        self.assertNotEqual(rows[1][1], step_key((2, 7), (1, 8)), rows)
        cells = [cell for cell, _, _ in rows]
        self.assertEqual(len(cells), len(set(cells)), rows)

    def test_life_491_far_squids_that_do_not_come_do_not_stop_the_dig(self):
        """n1-a life 491: on (5,24) beside the vein (5,25), the squids 482 ESP-detected at
        (17,24) and (19,19) and not coming; the dig turned into a step to a choke, and (5,23)
        stepped back east, 20 times."""
        squids = [detected(SQUID, 17, 24, index=91), detected(SQUID, 19, 19, index=92)]
        rows = self.walk((5, 24), [squids] * 4, dug=[(1, 7)])
        self.assertEqual([(key, reason) for _, key, reason in rows],
                         [("T" + step_key((5, 24), (5, 25)), DIG_REASON)] * 4, rows)

    def test_control_a_coming_squid_is_answered_at_the_choke_before_the_dig(self):
        """Owner 2026-11-04 「来る敵がいれば先に隘路で倒してから掘り直す」: a squid closing in
        on (5,24) still sends the walk to a choke, and it keeps going there."""
        squid = [[detected(SQUID, y, 24, index=91)] for y in (12, 11, 10, 9, 8)]
        rows = self.walk((5, 24), squid, dug=[(1, 7)])
        self.assertEqual(rows[0][2], DIG_REASON, rows)
        moved = [row for row in rows if row[2] == TO_CHOKE_REASON]
        self.assertTrue(moved, rows)
        start = rows.index(moved[0])
        self.assertNotIn(DIG_REASON, [row[2] for row in rows[start:]], rows)
        self.assertNotIn(WALK_REASON, [row[2] for row in rows[start:]], rows)


with gzip.open(ROOT / "tests" / "fixtures" / "q18-life495-20261108.json.gz", "rt", encoding="utf-8",
               errors="surrogateescape") as _stream:
    LIFE_495 = {(row["player"]["y"], row["player"]["x"]): row for row in json.load(_stream)["boards"]}
SWORDFISH = 88


class Q18InViewThatDoesNotComeTest(unittest.TestCase):
    """Owner 2026-11-08 「見えていても移動経路があるとは限らない。50行動で来なければ経路がないと
    判断する。」.

    n1-a life 495 (2026-11-08 00:15, floor (0,35,18)): from (3,20) the swordfish 88 on (10,13)
    (and the shrieker 40, which never moves) was in view, from (2,20) and (1,19) nothing.  The
    swordfish never moved.  (3,20) stepped to the choke (1,19), (2,20) stepped back to the exit,
    until the loop guard stopped the bot; after each restart it did the same at once.

    The boards are the recorded ones (tests/fixtures/q18-life495-20261108.json.gz,
    tests/extract_q18_life495_fixture.py: turns 1413514 on (3,20), 1413519 on (2,20), 1413558
    on (1,19)).  DECLARED CONSTRUCTED: HP full and fed (the recorded 534/627 and hungry
    answer with the rest and the meal first, which the live bot did not take there); a cell the
    recording has no board for is the (2,20) board with the player moved and nothing in view.
    """

    def raw_at(self, position, turn):
        raw = copy.deepcopy(LIFE_495.get(position) or LIFE_495[(2, 20)])
        if position not in LIFE_495:
            raw["player"].update(y=position[0], x=position[1])
            raw["visible_monsters"], raw["detected_monsters"] = [], []
        raw["player"].update(hp=raw["player"]["max_hp"], food_state="normal")
        raw["turn"] = turn
        return raw

    def walk(self, decisions):
        """The player moves by each step key, as the game would; the cell loop guard of the
        CLI is run beside it.  Returns the rows and the decision the guard tripped on."""
        start = LIFE_495[(3, 20)]
        policy = new_policy(self.raw_at((3, 20), start["turn"]))
        position, turn, rows, tripped = (3, 20), start["turn"], [], None
        recent = deque(maxlen=cli.MULTIPLIER_COMBAT_LOOP_WINDOW)
        last_position = last_player = None
        for decision in range(decisions):
            turn += 10
            snapshot = parse_snapshot(self.raw_at(position, turn), policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            rows.append((position, key, policy.last_reason))
            previous_position, last_position = last_position, snapshot.player.position
            previous_player, last_player = last_player, snapshot.player
            if cli._cell_loop_guard_applies(snapshot, policy.last_reason, previous_position,
                                            previous_player):
                recent.append((snapshot.floor_key, position[0], position[1]))
                if tripped is None and cli._is_looping(recent):
                    tripped = decision
            else:
                recent.clear()
            delta = next((offset for offset, value in DIRECTION.items() if value == key), None)
            if delta is not None:
                position = (position[0] + delta[0], position[1] + delta[1])
        return rows, tripped

    def test_life_495_the_swordfish_that_does_not_come_does_not_rock_the_walk(self):
        rows, tripped = self.walk(80)
        self.assertIsNone(tripped, rows)
        cells = [cell for cell, _, _ in rows]
        rocks = [index for index in range(2, len(cells))
                 if cells[index] == cells[index - 2] != cells[index - 1]]
        self.assertEqual(rocks, [], rows)
        # It waits for it on the choke it went to, then goes on to the exit side.
        self.assertEqual(rows[0], ((3, 20), step_key((3, 20), (2, 20)), TO_CHOKE_REASON), rows)
        self.assertEqual(rows[2][:1] + rows[2][2:], ((1, 19), HOLD_REASON), rows)
        self.assertGreater(max(x for _, x in cells), 22, rows)

    def stay(self, swordfish_cells):
        """The player kept on (3,20) (DECLARED CONSTRUCTED), one decision per entry with the
        swordfish on that cell."""
        policy = new_policy(self.raw_at((3, 20), LIFE_495[(3, 20)]["turn"]))
        rows = []
        for decision, cell in enumerate(swordfish_cells):
            raw = self.raw_at((3, 20), LIFE_495[(3, 20)]["turn"] + 10 * (decision + 1))
            for row in raw["visible_monsters"]:
                if row["race_id"] == SWORDFISH:
                    row.update(y=cell[0], x=cell[1])
            policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
            rows.append(policy.last_reason)
        return rows

    def test_in_view_fifty_actions_without_coming_it_has_no_route(self):
        wait = quest_find_exit.IN_VIEW_WAIT_ACTIONS
        rows = self.stay([(10, 13)] * (wait + 1))
        self.assertEqual(rows[:wait], [TO_CHOKE_REASON] * wait, rows)
        self.assertEqual(rows[wait], WALK_REASON, rows)

    def test_control_one_that_comes_nearer_counts_again(self):
        wait = quest_find_exit.IN_VIEW_WAIT_ACTIONS
        cells = [(10, 13)] * (wait - 5) + [(9, 16)] * 10
        rows = self.stay(cells)
        self.assertEqual(rows, [TO_CHOKE_REASON] * len(cells), rows)


class Q18RestLoopGuardTest(unittest.TestCase):
    """Owner 2026-11-06 「休憩中の止まり判定の誤りも直す」.  n1-a life 490 (floor (0,35,18)):
    on the choke (1,12) the rest was cut after one turn each time (the sealed Greater kraken
    775 stepping (18,14) <-> (18,15) in the ESP range), HP 550 -> 604 of 716 over 40 rests,
    and the cell guard stopped the bot.  DECLARED CONSTRUCTED from that decision log."""

    def run_rests(self, hp_of):
        policy = new_policy(board((1, 12), hp=550, max_hp=716))
        recent = deque(maxlen=cli.MULTIPLIER_COMBAT_LOOP_WINDOW)
        last_position = last_player = None
        for tick in range(cli.LOOP_WINDOW + 5):
            raw = board((1, 12), hp=hp_of(tick), max_hp=716)
            raw["detected_monsters"] = [detected(KRAKEN, 18, 14 + tick % 2, index=55)]
            raw["turn"] += 10 * (tick + 1)
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            self.assertEqual((key, policy.last_reason), (REST_MACRO, "rest"), tick)
            previous_position, last_position = last_position, snapshot.player.position
            previous_player, last_player = last_player, snapshot.player
            if not cli._cell_loop_guard_applies(snapshot, policy.last_reason, previous_position,
                                                previous_player):
                recent.clear()
                continue
            recent.append((snapshot.floor_key, snapshot.player.position.y, snapshot.player.position.x))
            if cli._is_looping(recent):
                return tick
        return None

    def test_a_rest_that_recovers_is_no_cell_loop(self):
        self.assertIsNone(self.run_rests(lambda tick: 550 + tick))

    def test_control_a_rest_that_recovers_nothing_still_trips_the_guard(self):
        self.assertIsNotNone(self.run_rests(lambda tick: 550))


class Q18PlaythroughTest(unittest.TestCase):
    def test_opening_walks_east_toward_the_exit(self):
        key, reason, _ = decide(board())
        self.assertEqual((key, reason), (step_key(ENTRANCE, (1, 3)), WALK_REASON))

    def test_a_quiet_floor_is_walked_and_dug_from_the_entrance_to_the_exit(self):
        raw = board()
        policy = new_policy(raw)
        position, route, digs = ENTRANCE, [ENTRANCE], []
        for _ in range(45):
            raw["player"].update(y=position[0], x=position[1])
            raw["turn"] += 10
            key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
            if key.startswith("T"):
                self.assertEqual(policy.last_reason, DIG_REASON)
                delta = next(offset for offset, value in DIRECTION.items() if value == key[1:])
                cell = (position[0] + delta[0], position[1] + delta[1])
                digs.append((position, cell))
                open_cell(raw, cell)
                continue
            self.assertIn(policy.last_reason, {WALK_REASON, STEP_ON_EXIT_REASON}, route)
            delta = next(offset for offset, value in DIRECTION.items() if value == key)
            position = (position[0] + delta[0], position[1] + delta[1])
            route.append(position)
            if position == EXIT:
                break
        self.assertEqual(digs, [((2, 6), (1, 7)), ((5, 24), (5, 25))])
        self.assertEqual(route, DUG_ROUTE)
        self.assertEqual(len(route) - 1, 31)

    def test_sealed_kraken_is_nothing_to_this_floor(self):
        key, reason, _ = decide(board(monsters=[monster(KRAKEN, 19, 15)]))
        self.assertEqual((key, reason), (step_key(ENTRANCE, (1, 3)), WALK_REASON))

    def test_a_sleeper_in_the_only_corridor_is_struck(self):
        key, reason, _ = decide(board((1, 3), monsters=[monster(SQUID, 1, 4, asleep=True)]))
        self.assertEqual((key, reason), (step_key((1, 3), (1, 4)), MELEE_REASON))

    def test_an_awake_enemy_is_met_at_the_nearest_choke(self):
        far = monster(SHARK, 6, 10)
        key, reason, _ = decide(board((2, 11), monsters=[far], ammo=False))
        self.assertEqual((key, reason), (step_key((2, 11), (1, 12)), TO_CHOKE_REASON))

    def test_the_choke_holds_for_what_comes_and_shoots_first(self):
        key, reason, _ = decide(board((1, 5), monsters=[monster(SHARK, 4, 7)], speed=0, ammo=False))
        self.assertEqual((key, reason), (WAIT_KEY, HOLD_REASON))
        key, reason, _ = decide(board((1, 5), monsters=[monster(SHARK, 4, 7)], speed=0))
        self.assertEqual(reason, "ranged:fire-target")

    def test_the_choke_hold_stays_under_fire(self):
        shark = monster(SHARK, 4, 7)
        key, reason, _ = decide(board((1, 5), hp=FULL_HP - 50, monsters=[shark], speed=0, ammo=False),
                                primed=board((1, 5), monsters=[shark], speed=0, ammo=False))
        self.assertEqual((key, reason), (WAIT_KEY, HOLD_REASON))

    def test_the_quiet_bound_does_not_push_past_an_enemy_in_view(self):
        """Owner 2026-11-08 「50行動で来なければ経路がないと判断する」: the shark that stays in
        view on its cell is waited for IN_VIEW_WAIT_ACTIONS actions, then the quiet wait of the
        choke it was waited on (choke_hold_turns) runs, then the walk goes on."""
        shark = monster(SHARK, 4, 7)
        raw = board((1, 5), monsters=[shark], speed=0, ammo=False)
        policy = new_policy(raw)
        plan = STRATEGIES[18].engagement_plan["find_exit"]
        wait = quest_find_exit.IN_VIEW_WAIT_ACTIONS
        held = wait + plan["choke_hold_turns"]
        reasons = []
        for _ in range(held + 2):
            raw["turn"] += 10
            policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            reasons.append(policy.last_reason)
        self.assertGreater(plan["choke_enemy_wait_turns"], wait)
        self.assertEqual(reasons[:held], [HOLD_REASON] * held)
        self.assertEqual(reasons[held], WALK_REASON)

    def test_a_choke_fight_strikes_the_adjacent_enemy(self):
        raw = board((1, 3), monsters=[monster(SQUID, 1, 4)], speed=0)
        key, reason, _ = decide(raw)
        self.assertEqual((key, reason), (step_key((1, 3), (1, 4)), MELEE_REASON))

    def test_a_heavy_fight_takes_the_speed_potion_once(self):
        raw = board((1, 3), monsters=[monster(SQUID, 1, 4), monster(SEAHORSE, 1, 2)],
                    hp=400)
        key, reason, policy = decide(raw)
        self.assertEqual(reason, HEAL_REASON)  # 400/800 is below the 0.70 heal line
        raw = board((1, 3), monsters=[monster(SQUID, 1, 4), monster(SEAHORSE, 1, 2)], hp=600)
        key, reason, policy = decide(raw)
        self.assertEqual(reason, SPEED_REASON)

    def test_below_the_line_with_an_enemy_recall_then_potions_then_blows(self):
        enemy = monster(SQUID, 1, 4)
        raw = board((1, 3), hp=300, monsters=[enemy], speed=0)
        key, reason, _ = decide(raw)
        self.assertEqual(reason, RECALL_REASON)
        self.assertTrue(key.startswith("r"))

        recalling = board((1, 3), hp=300, monsters=[enemy], speed=0, recalling=True)
        key, reason, _ = decide(recalling)
        self.assertEqual(reason, HEAL_REASON)

        out = board((1, 3), hp=300, monsters=[enemy], speed=0, healing=0, recalling=True)
        key, reason, _ = decide(out)
        self.assertEqual((key, reason), (step_key((1, 3), (1, 4)), MELEE_REASON))

    def test_above_the_line_with_an_enemy_no_recall(self):
        raw = board((1, 3), hp=340, monsters=[monster(SQUID, 1, 4)], speed=0)
        key, reason, _ = decide(raw)
        self.assertEqual(reason, HEAL_REASON)
        raw = board((1, 3), hp=340, monsters=[monster(SQUID, 1, 4)], speed=0, healing=0)
        key, reason, _ = decide(raw)
        self.assertEqual((key, reason), (step_key((1, 3), (1, 4)), MELEE_REASON))

    def test_no_enemy_rests_at_any_hp(self):
        for hp in (100, 500):
            key, reason, _ = decide(board((1, 3), hp=hp))
            self.assertEqual((key, reason), (REST_MACRO, "rest"), hp)

    def test_last_cell_occupied_is_fought_then_the_exit_is_stepped_on(self):
        guard = monster(SEAHORSE, *LAST_CELL)
        key, reason, _ = decide(board((1, 24), monsters=[guard], speed=0))
        self.assertEqual((key, reason), (step_key((1, 24), LAST_CELL), MELEE_REASON))

        key, reason, _ = decide(board((1, 24)))
        self.assertEqual((key, reason), (step_key((1, 24), LAST_CELL), WALK_REASON))

    def test_the_exit_beside_the_player_is_taken_even_below_the_line(self):
        chaser = monster(SHARK, 1, 24)
        key, reason, _ = decide(board(LAST_CELL, hp=100, monsters=[chaser]))
        self.assertEqual((key, reason), (step_key(LAST_CELL, EXIT), STEP_ON_EXIT_REASON))
        key, reason, _ = decide(board(LAST_CELL))
        self.assertEqual((key, reason), (step_key(LAST_CELL, EXIT), STEP_ON_EXIT_REASON))

    def test_stepping_on_the_exit_is_no_quest_failure(self):
        policy = new_policy()
        snapshot = parse_snapshot(board(LAST_CELL), policy._monrace_knowledge)
        self.assertFalse(policy._quest_exit_would_fail(snapshot))

    def test_a_siren_beside_the_player_is_walked_away_from(self):
        siren = monster(SIREN, 9, 22)
        key, reason, _ = decide(board((8, 23), monsters=[siren]))
        self.assertEqual(reason, PULLED_BACK_REASON)  # its own direct line
        self.assertNotEqual(key, step_key((8, 23), (9, 22)))


class Q18NoTeleportTest(unittest.TestCase):
    """No relocation scroll is read here, whichever rung would have read it."""

    def assert_no_relocation(self, raw, **kwargs):
        key, reason, policy = decide(raw, **kwargs)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        relocation = [item for item in snapshot.inventory
                      if item.tval == TVAL_SCROLL and item.sval in {SV_PHASE, SV_TELEPORT}]
        for item in relocation:
            self.assertNotEqual(key, f"r{item.slot}", reason)
        self.assertNotIn("teleport", reason)
        self.assertNotIn("phase", reason)
        return key, reason

    def test_the_shared_place_answers_none_here_and_finds_them_elsewhere(self):
        raw = board((1, 3))
        policy = new_policy()
        here = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertTrue(any(item.tval == TVAL_SCROLL and item.sval == SV_TELEPORT for item in here.inventory))
        self.assertTrue(quest_no_teleport.forbids(policy, here))
        self.assertIsNone(policy._find_teleport_scroll(here))
        self.assertIsNone(policy._find_phase_scroll(here))
        self.assertIsNone(policy._escape_scroll(here))
        self.assertIsNone(policy._escape_scroll(here, teleport_only=True))

        elsewhere = copy.deepcopy(BASE)
        policy = new_policy()
        there = parse_snapshot(elsewhere, policy._monrace_knowledge)
        self.assertFalse(quest_no_teleport.forbids(policy, there))
        self.assertIsNotNone(policy._find_teleport_scroll(there))

    def test_every_hp_and_enemy_board_of_the_floor_reads_no_relocation(self):
        for position in ((1, 3), (4, 13), (6, 14), (8, 23), LAST_CELL):
            for hp in (FULL_HP, 500, 330, 300, 100, 20):
                for monsters in (
                    (),
                    [monster(SQUID, position[0], position[1] + 1)],
                    [monster(SHARK, position[0] + 3, position[1])],
                    [monster(SQUID, position[0], position[1] + 1),
                     monster(SEAHORSE, position[0], position[1] - 1)],
                ):
                    for healing in (2, 0):
                        self.assert_no_relocation(board(position, hp=hp, monsters=monsters, healing=healing))

    def test_hit_by_something_unseen_reads_no_relocation(self):
        # DECLARED CONSTRUCTED: the observation's evidence of an unseen hit.
        with patch("hengbot.once_quest_recall._hit_by_unseen", return_value=True):
            key, reason = self.assert_no_relocation(board((4, 13), hp=250))
        self.assertEqual(reason, RECALL_REASON)

    def test_the_shared_ladders_alone_read_none_here(self):
        """The emergency, flee and no-wait rungs, with the plan's own rung out of the way."""
        raw = board((4, 13), hp=200, monsters=[monster(SQUID, 4, 14), monster(SEAHORSE, 4, 12)], healing=0)
        with patch("hengbot.quest_find_exit.key", return_value=None):
            key, reason = self.assert_no_relocation(raw)
        self.assertNotEqual(key, "")

    def test_once_quest_hold_counts_no_scroll_here(self):
        enemy = monster(SQUID, 1, 4)
        policy = new_policy()
        above = parse_snapshot(board((1, 3), hp=340, monsters=[enemy]), policy._monrace_knowledge)
        below = parse_snapshot(board((1, 3), hp=300, monsters=[enemy]), policy._monrace_knowledge)
        self.assertTrue(once_quest_recall.held(policy, above))
        self.assertFalse(once_quest_recall.held(policy, below))


class Q18AcceptanceTest(unittest.TestCase):
    """The owner's two conditions.  DECLARED CONSTRUCTED: the measured damage is pinned
    (a worn weapon of that output is not in the recorded pack) and the resists are the
    recorded row with the six the strategy names set."""

    def town(self, *, max_hp, healing=2, speed=1, resists=True, unhasted_speed=110):
        raw = board(max_hp=max_hp, hp=max_hp, healing=healing, speed=speed, teleports=False)
        raw["floor"].update(quest_id=0, level=0, in_town=True)
        raw["progress"]["quests"][0]["status"] = 0
        raw["player"]["speed"] = unhasted_speed
        sources = raw["player"]["ability_sources"]
        for name in ("free_action", "resist_conf", "resist_pois", "resist_acid", "resist_elec", "resist_cold",
                     "resist_chaos"):
            sources[name]["equipment"] = resists
        return raw

    def verdict(self, raw, damage):
        policy = new_policy()
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=damage), \
                patch.object(ConservativePolicy, "_main_hand_dps", return_value=damage), \
                patch.object(ConservativePolicy, "_inventory_overweight", return_value=False), \
                patch.object(ConservativePolicy, "_temporary_status_clear", return_value=True), \
                patch.object(ConservativePolicy, "_combat_weapon_ready", return_value=True), \
                patch.object(ConservativePolicy, "_light_judgment", return_value=_ReadyLight()):
            ready = policy._evaluate_fixed_quest_readiness(snapshot, 18, require_target_town=False)
            force = policy._strategy_force_for_snapshot(snapshot, STRATEGIES[18])
        return ready, policy._fixed_quest_readiness, force

    def test_condition_one(self):
        ready, telemetry, force = self.verdict(self.town(max_hp=700), 150)
        self.assertTrue(ready, telemetry)
        self.assertEqual((force["min_hp"], force["speed_potions"], force["heal_potions"]), (700, 1, 2))
        self.assertFalse(force.get("always_hasted"))

    def test_condition_two_with_six_potions(self):
        ready, telemetry, force = self.verdict(self.town(max_hp=500, speed=6), 75)
        self.assertTrue(ready, telemetry)
        self.assertEqual((force["min_hp"], force["speed_potions"]), (500, 6))
        self.assertTrue(force["always_hasted"])

    def test_condition_two_with_speed_from_gear(self):
        ready, telemetry, force = self.verdict(self.town(max_hp=500, speed=0, unhasted_speed=120), 75)
        self.assertTrue(ready, telemetry)
        self.assertEqual(force["speed_potions"], 0)

    def test_condition_two_with_absorbed_speed_needs_six_charges(self):
        for charges, accepted in ((6, True), (5, False)):
            with patch("hengbot.me_capability.replaced_by_absorbed", return_value=True), \
                    patch("hengbot.me_capability.charges", return_value=charges), \
                    patch("hengbot.speed_dose.available", return_value=True):
                ready, telemetry, force = self.verdict(self.town(max_hp=500, speed=0), 75)
            self.assertEqual(ready, accepted, telemetry)
            self.assertEqual(bool(force.get(quest_force_rows.ABSORBED_SHORT)), not accepted)

    def test_controls_refuse(self):
        for raw, damage, failed in (
            (self.town(max_hp=699), 150, "dps"),  # row 2's HP holds, its six potions do not
            (self.town(max_hp=700), 149, "speed_potions"),
            (self.town(max_hp=499, speed=6), 200, "hp"),
            (self.town(max_hp=800, speed=6), 74, "dps"),
            (self.town(max_hp=800, healing=1), 200, "heal_potions"),
            (self.town(max_hp=800, resists=False), 200, "resists"),
        ):
            ready, telemetry, _ = self.verdict(raw, damage)
            self.assertFalse(ready)
            self.assertEqual(telemetry["reason"], "strategy-force", telemetry)
            self.assertTrue(telemetry["strategy_force"]["failed"], telemetry)

    def test_the_quest_levels_depth_abilities_are_asked_at_acceptance(self):
        raw = self.town(max_hp=800)
        raw["player"]["ability_sources"]["resist_chaos"]["equipment"] = True
        self.assertTrue(self.verdict(raw, 200)[0])
        raw["player"]["ability_sources"]["resist_chaos"].update(equipment=False, permanent=False)
        ready, telemetry, _ = self.verdict(raw, 200)
        self.assertFalse(ready)
        self.assertEqual(telemetry["reason"], "depth-abilities")

    def test_no_recall_scroll_no_acceptance(self):
        raw = self.town(max_hp=800)
        raw["inventory"] = [item for item in raw["inventory"]
                            if not (item["tval"] == TVAL_SCROLL and item["sval"] == SV_RECALL)]
        ready, telemetry, _ = self.verdict(raw, 200)
        self.assertFalse(ready)
        self.assertEqual(telemetry["reason"], "no-recall")

    def test_short_of_every_row_asks_for_no_potion(self):
        _, _, force = self.verdict(self.town(max_hp=300, healing=0, speed=0), 40)
        self.assertEqual((force["heal_potions"], force["speed_potions"]), (0, 0))
        self.assertEqual((force["min_hp"], force["min_expected_dps"]), (700, 150))


class Q18TownTest(unittest.TestCase):
    """Giver, carries and report on the recorded Outpost board of
    tests/fixtures/q14-lv8-1102.json.gz.  DECLARED CONSTRUCTED: its quest rows (every
    earlier quest finished), the giver cell's special 14 -> 18, and the readiness verdict."""

    @staticmethod
    def town_board(status):
        with gzip.open(ROOT / "tests" / "fixtures" / "q14-lv8-1102.json.gz", "rt", encoding="utf-8") as stream:
            raw = json.load(stream)["board"]
        raw["progress"]["quests"] = [
            *[{"fixed": True, "id": quest_id, "level": QUESTS[quest_id].level, "name": "q", "status": 4,
               "type": QUESTS[quest_id].type} for quest_id in (1, 2, 14, 22, 31, 34)],
            {"fixed": True, "id": 18, "level": 35, "name": "water cave", "status": status, "type": 4},
        ]
        for cell in raw["grid_map"]["cells"]:
            if cell.get("p") == 14:
                cell["p"] = 18
        return raw

    def policy(self):
        maps = town_maps()
        return ConservativePolicy(town_map=maps[0], town_maps=maps, monrace_knowledge=RACES,
                                  quest_knowledge=QUESTS, quest_strategies=STRATEGIES)

    def snapshot(self, policy, raw):
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(snapshot)
        return snapshot

    def test_ready_walks_to_the_giver_and_unready_leaves_the_town_alone(self):
        policy = self.policy()
        snapshot = self.snapshot(policy, self.town_board(0))
        self.assertEqual(policy._fixed_quest_head(snapshot).id, 18)
        self.assertIsNone(policy._fixed_quest_key(snapshot, []))  # far from the floors: no stop
        policy = self.policy()
        snapshot = self.snapshot(policy, self.town_board(0))
        with patch.object(ConservativePolicy, "_fixed_quest_ready", return_value=True), \
                patch.object(ConservativePolicy, "_fixed_quest_ready_for_travel", return_value=True):
            policy._fixed_quest_key(snapshot, [])
        self.assertTrue(policy.last_reason.startswith("fixedquest:request"), policy.last_reason)

    def test_a_character_short_of_every_row_buys_nothing_for_it(self):
        policy = self.policy()
        snapshot = self.snapshot(policy, self.town_board(0))
        force = policy._carry_procurement_strategy(snapshot).required_force
        self.assertEqual((force["heal_potions"], force["speed_potions"]), (0, 0))

    def test_a_capable_character_buys_the_rows_potions_healing_from_temple_then_black_market(self):
        policy = self.policy()
        raw = self.town_board(0)
        raw["player"].update(max_hp=800, hp=800)
        snapshot = self.snapshot(policy, raw)
        with patch.object(ConservativePolicy, "_strategy_measured_dps", return_value=200.0):
            force = policy._carry_procurement_strategy(snapshot).required_force
        self.assertEqual((force["heal_potions"], force["speed_potions"]), (2, 1))

    def test_a_completed_quest_is_reported_and_its_reward_cell_is_the_towns(self):
        policy = self.policy()
        snapshot = self.snapshot(policy, self.town_board(2))
        self.assertEqual(policy._fixed_quest_head(snapshot).id, 18)
        policy._fixed_quest_key(snapshot, [])
        self.assertTrue(policy.last_reason.startswith("fixedquest:claim"), policy.last_reason)
        self.assertIn(Position(27, 98), town_maps()[0].reward_positions)


class _ReadyLight:
    one_shot_quest_entry_ready = True
    one_shot_quest_entry_reject_reason = "light"
    releases_one_shot_quest = False
    worn = None


with gzip.open(ROOT / "tests" / "fixtures" / "q18-life515-20261112.json.gz", "rt", encoding="utf-8",
               errors="surrogateescape") as _stream:
    LIFE_515 = {row["turn"]: row for row in json.load(_stream)["boards"]}
LIFE_515_ENTRY = 1803953


class Q18Life515Test(unittest.TestCase):
    """n1-a life 515 (2026-11-12 15:14, warrior Lv33, floor (0,35,18)) died on (3,20).

    Accepted on the first force row (max HP 716 of 700); the seahorses' LOSE_CON bites drained
    the max HP to 641 before the last fight (485 at death).  Decision 48623 left the spent choke
    (1,19) for (3,22) by (2,20) and (3,20); on (3,20) it meleed two seahorses 443 beside it, and
    from 48631 a giant squid 482 too: three at once against the strategy's
    ``max_simultaneous_melee`` 2, until the emergency rungs and death at 48634.

    The boards are the recorded ones (tests/fixtures/q18-life515-20261112.json.gz,
    tests/extract_q18_life515_fixture.py: the floor's first board 1803953 and the boards of
    decisions 48623-48633).  The recorded keys are in the comments.
    """

    @staticmethod
    def raw(turn):
        return copy.deepcopy(LIFE_515[turn])

    @staticmethod
    def decide_off_the_line(raw, *, spent=()):
        """The board with the force line out of it: DECLARED CONSTRUCTED, the floor entered on
        the second row (min_hp 500), so the drained max HP crosses nothing; ``spent``: the
        chokes whose waits were spent, as at decision 48623."""
        policy = new_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        navigator = quest_find_exit._navigator(policy, snapshot, 18)
        navigator.entry_force_min_hp = 500
        navigator.exit_spent_chokes = frozenset(Position(*cell) for cell in spent)
        key = str(policy.choose_key(snapshot))
        return key, policy.last_reason

    def test_recorded_three_beside_it_walks_back_to_the_choke(self):
        for turn in (1806402, 1806410):  # recorded: melee '3' (the squid), melee '3'
            raw = self.raw(turn)
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (3, 20))
            beside = sorted((row["race_id"], row["y"], row["x"]) for row in raw["visible_monsters"]
                            if abs(row["y"] - 3) <= 1 and abs(row["x"] - 20) <= 1)
            self.assertEqual(beside, [(SEAHORSE, 4, 19), (SEAHORSE, 4, 20), (SQUID, 4, 21)])
            key, reason = self.decide_off_the_line(raw)
            # (2,20), the way to the choke (1,19), has nobody beside it.
            self.assertEqual((key, reason), (step_key((3, 20), (2, 20)), quest_find_exit.MELEE_CAP_REASON),
                             turn)

    def test_control_two_beside_it_is_still_fought(self):
        raw = self.raw(1806375)  # recorded: melee '2', the seahorses on (4,20) and (4,19)
        key, reason = self.decide_off_the_line(raw)
        self.assertEqual((key, reason), (step_key((3, 20), (4, 20)), MELEE_REASON))

    def test_no_step_onto_a_cell_with_three_beside_it(self):
        """DECLARED CONSTRUCTED: the recorded (3,20) board of decision 48631, its three
        seahorses and squid moved a row down to (5,20), (5,21) and (5,22), none beside the
        player; the chokes behind spent up to (1,19), as they were at 48623, so the walk to
        (3,22) goes by (4,21), where all three would stand beside it."""
        raw = self.raw(1806402)
        moved = {(4, 19): (5, 20), (4, 20): (5, 21), (4, 21): (5, 22)}
        for row in raw["visible_monsters"]:
            if (row["y"], row["x"]) in moved:
                row["y"], row["x"] = moved[(row["y"], row["x"])]
        key, reason = self.decide_off_the_line(
            raw, spent=[(1, 3), (1, 5), (1, 9), (1, 12), (1, 15), (1, 19)])
        self.assertNotEqual(key, step_key((3, 20), (4, 21)), reason)
        self.assertEqual((key, reason), (step_key((3, 20), (2, 20)), quest_find_exit.MELEE_CAP_REASON))

    def walk_from_entry(self, turn):
        """The policy given the floor's first board, then the board of ``turn``."""
        entry = self.raw(LIFE_515_ENTRY)
        policy = new_policy(entry)
        policy.choose_key(parse_snapshot(entry, policy._monrace_knowledge))
        navigator = policy._quest_navigators[18]
        self.assertEqual(navigator.entry_force_min_hp, 700)  # the first row, as accepted
        return policy

    def test_drained_below_the_entry_row_reads_recall_with_the_seahorse_in_view(self):
        raw = self.raw(1806351)  # recorded: exit-to-choke '2' onto (3,20)
        self.assertEqual((raw["player"]["hp"], raw["player"]["max_hp"]), (641, 641))
        policy = self.walk_from_entry(1806351)
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, RECALL_REASON)
        self.assertTrue(key.startswith("r"), key)

    def test_control_undrained_reads_no_recall(self):
        """DECLARED CONSTRUCTED: the same board with the max HP of the entry, 716."""
        raw = self.raw(1806351)
        raw["player"]["max_hp"] = raw["player"]["hp"] = 716
        policy = self.walk_from_entry(1806351)
        policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
        self.assertNotEqual(policy.last_reason, RECALL_REASON)

    def test_drained_with_no_enemy_reads_no_recall(self):
        raw = self.raw(1806342)  # recorded: exit-to-choke '3', nothing in view on (1,19)
        self.assertEqual(raw["visible_monsters"] + raw["detected_monsters"], [])
        policy = self.walk_from_entry(1806342)
        policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
        self.assertNotEqual(policy.last_reason, RECALL_REASON)


if __name__ == "__main__":
    unittest.main()
