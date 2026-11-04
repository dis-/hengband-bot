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
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import once_quest_recall, quest_exposure, quest_force_rows, quest_no_teleport
from hengbot.model import Position, SV_POTION_HEALING, SV_POTION_SPEED, TVAL_POTION, TVAL_SCROLL, parse_snapshot
from hengbot.model import _GRID_TERRAIN_NAMES
from hengbot.monrace_knowledge import _strip_jsonc, find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import EXECUTABLE_QUEST_STRATEGY_IDS, REST_MACRO, WAIT_KEY
from hengbot.quest_find_exit import (
    DIG_REASON, HEAL_REASON, HOLD_REASON, NO_SAFE_ROUTE_REASON, PULL_REFUSED_REASON, PULLED_BACK_REASON, MELEE_REASON, RECALL_REASON, SPEED_REASON, STEP_ON_EXIT_REASON,
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
# DECLARED: approval is switched on here.  The owner withdrew it on main until this fix is
# checked (「直しが入るまで止めておいて」); these tests exercise the plan, not the flag.
STRATEGIES = load_quest_strategies(ROOT / "strategy" / "quests")
STRATEGIES[18] = replace(STRATEGIES[18], approved=True)
EXECUTABLE_WITH_18 = frozenset({*EXECUTABLE_QUEST_STRATEGY_IDS, 18})
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

    def test_the_vein_before_the_pull_cells_that_will_not_open_stops_by_name(self):
        raw = board((5, 24))
        policy = new_policy(raw)
        limit = STRATEGIES[18].engagement_plan["find_exit"]["dig_attempt_limit"]
        for _ in range(limit + 1):
            raw["turn"] += 10
            key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, NO_SAFE_ROUTE_REASON))


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
        shark = monster(SHARK, 4, 7)
        raw = board((1, 5), monsters=[shark], speed=0, ammo=False)
        policy = new_policy(raw)
        plan = STRATEGIES[18].engagement_plan["find_exit"]
        reasons = []
        for _ in range(plan["choke_enemy_wait_turns"] + 2):
            raw["turn"] += 10
            policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            reasons.append(policy.last_reason)
        self.assertGreater(plan["choke_enemy_wait_turns"], plan["choke_hold_turns"])
        self.assertEqual(reasons[:plan["choke_enemy_wait_turns"]],
                         [HOLD_REASON] * plan["choke_enemy_wait_turns"])
        self.assertNotEqual(reasons[plan["choke_enemy_wait_turns"]], HOLD_REASON)

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
                patch.object(ConservativePolicy, "_fixed_quest_ready_for_travel", return_value=True), \
                patch("hengbot.policy_quest.EXECUTABLE_QUEST_STRATEGY_IDS", EXECUTABLE_WITH_18):
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


if __name__ == "__main__":
    unittest.main()
