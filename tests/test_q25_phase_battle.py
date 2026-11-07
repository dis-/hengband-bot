"""Quest 25 『幽霊屋敷』 phase battle (quest25_battle) through the public ``choose_key``.

Owner 2026-11-06 「作り直すまで外す」: the plan is the draft
``engagement_plan.revised_plan_draft`` of strategy/quests/QUEST_25.jsonc, each owner
decision quoted there.  The owner restored approval on 2026-11-07 (「承認を戻す」); the tests still run it with
``approved`` forced on (``APPROVED``), and one test pins that the shipped file runs it.

DECLARED CONSTRUCTED, as tests/test_q25_haunted_house.py (whose board builder this reuses):
the recorded n1-c Q31 board (a Lv25 Magic-Eater with a crossbow and bolts, a Stone to Mud
wand) with the real Q25 map, its monsters on the map's cells, the real MonraceDefinitions.
Where a test gives the character an absorbed power list, a carried device or a trap shown on
a cell, it says so.  A phase is entered by setting the plan's memory (``at_phase``): its
earlier phases are what the other tests drive.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from unittest.mock import patch
from dataclasses import replace

from hengbot import attack_expectation, quest25_battle as battle, quest25_geometry as geo, threat_tiers
from hengbot import quest25_druj_gear as druj_gear, quest_exposure, quest_optional_carry, quest_room_sweep, spare_gear
from hengbot.me_device_attacks import DEVICE_REASON
from hengbot.me_powers_refresh import REFRESH_REASON
from hengbot.model import TVAL_ROD, TVAL_WAND, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import REST_MACRO, SEARCH_KEY, WAIT_KEY
from hengbot.quest_find_exit import HOLD_REASON
from hengbot.quest_strategies import has_ability_or_alternative
from tests import test_q25_haunted_house as q25
from tests.test_q25_haunted_house import (
    BASE, FILE_STRATEGIES, QUESTS, RACES, _CASE, _palette_row, board, monster, open_door,
)

APPROVED = {**FILE_STRATEGIES, 25: replace(FILE_STRATEGIES[25], approved=True)}
BATTLEFIELD = QUESTS[25].battlefield
TERRAIN = BATTLEFIELD.terrain
DIRECTION = q25.DIRECTION
DRAFT = FILE_STRATEGIES[25].engagement_plan["revised_plan_draft"]


def new_policy(raw, strategies=APPROVED):
    policy = ConservativePolicy(monrace_knowledge=RACES, quest_knowledge=QUESTS, quest_strategies=strategies)
    first = copy.deepcopy(raw)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(_CASE["skill"]), turn=first["turn"],
        player=dict(_CASE["skill"]["player"], level=first["player"]["level"])))
    return policy


def choose(policy, raw):
    raw["turn"] += 10
    return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))


def memory(policy, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    return battle._memory(quest_room_sweep._navigator(policy, snapshot, 25))


def at_phase(policy, raw, name, *, ready=True, **fields):
    record = memory(policy, raw)
    record.__dict__.update(battle.Battle(phase=battle.PHASE_NAMES.index(name), ready=ready,
                                         **fields).__dict__)
    return record


def phase_of(policy, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    return battle.describe(policy, snapshot)["phase"]


def step(start, goal):
    return DIRECTION[(goal[0] - start[0], goal[1] - start[1])]


def without_melee(raw):
    raw["equipment"] = [item for item in raw["equipment"] if item["slot"] != "main_hand"]
    return raw


def without_ranged(raw):
    raw["equipment"] = [item for item in raw["equipment"] if item["slot"] != "bow"]
    raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in {16, 17, 18}]
    return raw


def with_wand_list(raw, *rows):
    """CONSTRUCTED: the absorbed wand list on the board (``_magic_eater_power_list``)."""
    raw["_magic_eater_power_list"] = {"kind": "wand", "rows": [dict(row) for row in rows]}
    return raw


FIRE_BALL = {"name": "ファイア・ボール", "fail": 10, "success": 90, "max": 5, "current": 5}
FIRE_BALL_LETTER = "w"   # sval 22


def with_trap_shown(raw, cell):
    """CONSTRUCTED: the trap on ``cell`` found (the grid's TRAP bit, view/display-map.cpp)."""
    row = _palette_row("FLOOR")
    row = [row[0], row[1], row[2] | 1 << 14, row[3]]   # _GRID_TERRAIN_NAMES "trap"
    palette = raw["grid_map"]["palette"]
    if row not in palette:
        palette.append(row)
    for run in raw["grid_map"]["runs"]:
        if (run[0], run[1]) == tuple(cell):
            run[3] = palette.index(row)
    return raw


def carried(raw, tval, sval, name, **fields):
    """CONSTRUCTED: a known carried device."""
    row = copy.deepcopy(next(item for item in BASE["inventory"] if item["tval"] == TVAL_WAND))
    row.update(tval=tval, sval=sval, name=name, slot="l", count=1, charges=fields.pop("charges", 5), **fields)
    if tval == TVAL_ROD:
        row["charging_count"] = 0
    raw["inventory"].append(row)
    return raw


class Q25GeometryTest(unittest.TestCase):
    """The draft's cells, derived from the map (quest25_geometry), against the draft's list."""

    def test_summon_cells_are_the_drafts(self):
        counts = geo.summon_counts(TERRAIN)
        by = {}
        for cell, count in counts.items():
            by.setdefault(count, set()).add(cell)
        self.assertEqual(by[1], {(4, 1), (5, 1), (6, 1)})
        self.assertEqual(by[2], {(6, 2)})
        hound_den = {(7, 4), (8, 3), (8, 4)}   # walled off inside rows 4-9: 739's den, not the hall
        hall = {(y, x) for y in range(4, 10) for x in range(3, 18)
                if TERRAIN[(y, x)] in geo.STANDABLE} - hound_den
        self.assertEqual(by[3], hall | {(5, 2), (10, 6), (10, 11), (10, 15)})
        for cell in ((7, 1), (13, 1), (10, 1), (1, 6)):
            self.assertNotIn(cell, counts)

    def test_from_5_1_only_7_17_is_reached_and_it_has_no_line_back(self):
        self.assertTrue(quest_exposure.projectable(TERRAIN, (5, 1), (7, 17)))
        self.assertFalse(quest_exposure.projectable(TERRAIN, (5, 1), (8, 17)))
        self.assertFalse(quest_exposure.projectable(TERRAIN, (5, 1), (9, 17)))
        self.assertFalse(quest_exposure.projectable(TERRAIN, (7, 17), (5, 1)))

    def test_ball_centres_are_the_drafts(self):
        self.assertEqual(geo.ball_centre(TERRAIN, (5, 2), (9, 13), 2), (2, (7, 14)))
        self.assertEqual(geo.ball_centre(TERRAIN, (5, 2), (9, 9), 3), (3, (6, 8)))
        self.assertEqual(geo.ball_centre(TERRAIN, (5, 1), (9, 9), 3), (3, (6, 9)))
        self.assertEqual(geo.ball_centre(TERRAIN, (5, 1), (9, 13), 3), (3, (6, 12)))
        self.assertEqual(geo.ball_centre(TERRAIN, (5, 1), (9, 8), 3), (3, (6, 9)))
        self.assertEqual(geo.ball_centre(TERRAIN, (5, 2), (9, 8), 3), (3, (6, 8)))
        for stand in geo.QUYL_STANDS:   # a radius-2 ball reaches neither [9,9] nor the tome
            self.assertIsNone(geo.ball_centre(TERRAIN, stand, (9, 9), 2))
            self.assertIsNone(geo.ball_centre(TERRAIN, stand, (9, 8), 2))
        self.assertIsNone(geo.ball_centre(TERRAIN, (5, 1), (9, 13), 2))

    def test_the_dreadmasters_vision(self):
        dreadmaster = (12, 24)
        edge = geo.vision_cells(TERRAIN, dreadmaster, 20, edge=True)
        self.assertEqual(edge, {(1, 9), (2, 9), (4, 8), (5, 7), (6, 7), (7, 6), (8, 6),
                                (11, 4), (12, 4), (13, 4)})
        outside = {cell for cell, kind in TERRAIN.items() if kind in geo.STANDABLE} - \
            geo.vision_cells(TERRAIN, dreadmaster, 20)
        self.assertEqual(len(outside), 44)
        for cell in (*geo.PHASE2_WALK, (5, 2), (4, 1), (6, 2), geo.START):
            self.assertIn(cell, outside)

    def test_traps_of_the_map(self):
        self.assertEqual(set(BATTLEFIELD.trap_cells) & set(geo.NORTH_CORRIDOR), set(geo.NORTH_CORRIDOR))
        self.assertIn((3, 1), BATTLEFIELD.maybe_trap_cells)
        self.assertIn((1, 4), BATTLEFIELD.maybe_trap_cells)
        self.assertNotIn((1, 6), (*BATTLEFIELD.trap_cells, *BATTLEFIELD.maybe_trap_cells))
        for cell in ((13, 20), (13, 27), (12, 27), (11, 20), (12, 20)):
            self.assertIn(cell, BATTLEFIELD.trap_cells)

    def test_the_druj_route(self):
        open_ = geo.opened(TERRAIN, [geo.DRUJ_DOOR])
        lines = geo.line_cells(open_, (11, 18))
        trapless = {cell for cell in lines if TERRAIN.get(cell) == "floor"
                    and cell not in BATTLEFIELD.trap_cells and cell not in BATTLEFIELD.maybe_trap_cells}
        self.assertEqual(trapless, {(12, y) for y in range(21, 27)})
        self.assertTrue(quest_exposure.projectable(TERRAIN, (13, 20), (11, 19)))
        self.assertFalse(quest_exposure.projectable(open_, (11, 18), (13, 20)))


class Q25WiringTest(unittest.TestCase):
    def test_the_shipped_file_is_approved_and_runs_the_plan(self):
        # Owner 2026-11-07 「承認を戻す」: the shipped file runs the phase battle.
        self.assertTrue(FILE_STRATEGIES[25].approved)
        raw = board()
        policy = new_policy(raw, FILE_STRATEGIES)
        choose(policy, raw)
        self.assertTrue((policy.last_reason or "").startswith(battle.REASON), policy.last_reason)

    def test_approved_the_phase_battle_runs_and_the_room_sweep_steps_aside(self):
        raw = board()
        policy = new_policy(raw)
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "ambush")
        self.assertNotIn(policy.last_reason, {q25.WALK_REASON, q25.LIGHT_REASON})
        snapshot = parse_snapshot(copy.deepcopy(raw), RACES)
        self.assertIsNone(quest_room_sweep._plan(policy, snapshot))
        self.assertTrue(quest_room_sweep.walks_over_traps(policy, snapshot))

    def test_the_phase_table_follows_the_draft(self):
        self.assertEqual(battle.PHASE_NAMES, (
            "ambush", "wall-passers", "ipsissimus", "stragglers", "quylthulgs", "tome",
            "corpse-masses", "dreadmaster", "sweep", "stairway", "druj"))
        for phase in battle.PHASES:
            self.assertIn(phase.spec_key, DRAFT)
        self.assertEqual({phase.name for phase in battle.PHASES if phase.full_hp},
                         {"wall-passers", "ipsissimus", "tome", "stairway"})


class Q25AmbushTest(unittest.TestCase):
    """phase1: 「DPSで比較」 then the stand; 「どちらにせよ加速を使用する」."""

    def test_the_comparison_counts_slays_and_hit_chance(self):
        raw = board()
        policy = new_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), RACES)
        melee = attack_expectation.melee_against(policy, snapshot, geo.SPECTRAL_T)
        plain = attack_expectation.melee(policy, snapshot, replace(
            parse_snapshot(copy.deepcopy(board(monsters=[monster(geo.SPECTRAL_T, 12, 1)])),
                           RACES).visible_monsters[0], hp=10 ** 6))
        self.assertGreater(melee, plain)   # the spear's slays (evil, undead, animal) count
        shot = attack_expectation.launcher_against(policy, snapshot, geo.SPECTRAL_T, 9)
        self.assertGreater(shot, 0)
        self.assertLess(shot, 54 * 3)      # (54/shot ...) times a slay at most, times a hit chance
        self.assertTrue(battle.melee_is_fewer(policy, snapshot, geo.SPECTRAL_T))
        unarmed = without_melee(board())
        self.assertFalse(battle.melee_is_fewer(
            policy, parse_snapshot(unarmed, RACES), geo.SPECTRAL_T))

    def test_ranged_opens_the_west_door_and_waits_on_the_start(self):
        raw = without_melee(board())
        policy = new_policy(raw)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (step((13, 1), (12, 1)), battle.WALK_REASON))
        raw["player"].update(y=10, x=1)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("o8", battle.OPEN_REASON))
        open_door(raw, geo.WEST_DOOR)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (step((10, 1), (11, 1)), battle.WALK_REASON))
        raw["player"].update(y=13, x=1)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, HOLD_REASON))
        self.assertEqual(memory(policy, raw).style, "ranged")

    def test_ranged_shoots_what_comes_down_the_corridor_after_the_haste(self):
        # The hound, light enough that the shared heavy-fight speed rung stays quiet.
        raw = without_melee(board(monsters=[monster(geo.HOUND, 5, 1)]))
        open_door(raw, geo.WEST_DOOR)
        open_door(raw, (4, 1))
        policy = new_policy(raw)
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.HASTE_REASON)
        self.assertTrue(key.startswith("q"), key)
        policy._player_hasted = lambda snapshot: True   # DECLARED: the haste shown on the board
        key = choose(policy, raw)
        self.assertTrue((policy.last_reason or "").startswith("ranged:"), (key, policy.last_reason))

    def test_melee_closes_the_door_waits_and_closes_in_the_turn_it_opens(self):
        raw = without_ranged(board((10, 1)))
        open_door(raw, geo.WEST_DOOR)
        policy = new_policy(raw)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("c", battle.CLOSE_REASON))
        raw = without_ranged(board((10, 1)))
        policy = new_policy(raw)
        self.assertEqual((choose(policy, raw), policy.last_reason), (WAIT_KEY, HOLD_REASON))
        raw = without_ranged(board((10, 1), monsters=[monster(geo.SPECTRAL_T, 8, 1)]))
        open_door(raw, geo.WEST_DOOR)
        policy = new_policy(raw)
        policy._player_hasted = lambda snapshot: True   # DECLARED: hasted already
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("8", battle.ENGAGE_REASON))

    def test_the_four_killed_end_the_phase(self):
        raw = board()
        policy = new_policy(raw)
        names = {race: RACES[race].names[0] for race in (geo.HOUND, geo.SKELETAL_T, geo.VAMPIRE)}
        raw["messages"] = [names[geo.HOUND] + "を倒した。", names[geo.SKELETAL_T] + "を倒した。",
                           names[geo.VAMPIRE] + "を倒した。"]
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "ambush")
        raw["messages"] = [RACES[geo.SPECTRAL_T].names[0] + "を倒した。"]
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "wall-passers")


class Q25BetweenPhasesTest(unittest.TestCase):
    """between_phases: 「各段階の間に…攻撃に使うものを全快させる」 (R& does not wait for them)."""

    def test_read_rest_read_then_go_on(self):
        short = dict(FIRE_BALL, current=2)
        raw = with_wand_list(board((13, 1)), short)
        policy = new_policy(raw)
        at_phase(policy, raw, "wall-passers", ready=False)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("bB", REFRESH_REASON))
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (battle.RECHARGE_REST_KEY, battle.RECHARGE_REASON))
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("bB", REFRESH_REASON))   # the rest is read again
        with_wand_list(raw, FIRE_BALL)
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.WALK_REASON)   # full: on to [7,1]
        self.assertNotEqual(key, REST_MACRO)

    def test_the_first_phase_does_not_wait_for_charges(self):
        raw = with_wand_list(board(), dict(FIRE_BALL, current=2))
        policy = new_policy(raw)
        choose(policy, raw)
        self.assertNotIn(policy.last_reason, {REFRESH_REASON, battle.RECHARGE_REASON})

    def test_full_hp_before_the_wall_passers(self):
        raw = board((13, 1), hp=500)
        policy = new_policy(raw)
        at_phase(policy, raw, "wall-passers", ready=False)
        self.assertEqual((choose(policy, raw), policy.last_reason), (REST_MACRO, battle.FULL_HP_REASON))


class Q25WallPassersTest(unittest.TestCase):
    def test_fifty_actions_without_an_arrival_end_the_wait(self):
        raw = board((7, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "wall-passers")
        for _ in range(battle.QUIET_ACTIONS - 1):
            self.assertEqual((choose(policy, raw), policy.last_reason), (WAIT_KEY, HOLD_REASON))
        self.assertEqual(phase_of(policy, raw), "wall-passers")
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "ipsissimus")

    def test_a_new_arrival_restarts_the_count(self):
        raw = board((7, 1))
        policy = new_policy(raw)
        record = at_phase(policy, raw, "wall-passers", quiet=40)
        raw["visible_monsters"] = [monster(geo.SPECTRE, 7, 3, index=901)]
        choose(policy, raw)
        self.assertLess(record.quiet, 5)


class Q25IpsissimusTest(unittest.TestCase):
    """phase2: 「全快して(7,1)に移動、事前に加速して(6,1)(5,1)と移動。一番ダメージの出る攻撃をイプシシマスに放つ」."""

    def test_haste_on_7_1_then_the_walk_to_5_1(self):
        raw = board((7, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.HASTE_REASON)
        self.assertTrue(key.startswith("q"), key)
        policy._player_hasted = lambda snapshot: True   # DECLARED: the haste shown
        self.assertEqual(choose(policy, raw), step((7, 1), (6, 1)))
        raw["player"].update(y=6, x=1)
        self.assertEqual(choose(policy, raw), step((6, 1), (5, 1)))

    def test_on_5_1_the_unseen_pen_is_shot_by_its_grid(self):
        raw = board((5, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.SHOT_REASON)
        self.assertTrue(key.endswith("*p" + "33" + "6" * 14 + "t5\x1b"), key)   # to [7,17]
        self.assertTrue(key.startswith("f"), key)

    def test_the_strongest_attack_an_absorbed_ball_bursts_on_the_pen(self):
        raw = with_wand_list(board((5, 1)), FIRE_BALL)
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("mB" + FIRE_BALL_LETTER + "@7,17", DEVICE_REASON))

    def summoned(self, raw, race=geo.SPECTRE, cell=(5, 2)):
        raw["visible_monsters"] = [monster(race, *cell, index=902)]
        return raw

    def test_summons_with_a_piercing_attack_and_a_low_threat_keep_the_fire_on_the_pen(self):
        raw = self.summoned(with_wand_list(board((5, 1)), FIRE_BALL), cell=(4, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        policy._player_hasted = lambda snapshot: True
        snapshot = parse_snapshot(copy.deepcopy(raw), RACES)
        self.assertFalse(policy._is_material_threat(snapshot, policy._physical_hostiles(snapshot)))
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("mB" + FIRE_BALL_LETTER + "@7,17", DEVICE_REASON))

    def test_summons_with_no_piercing_attack_teleport(self):
        raw = self.summoned(board((5, 1)), cell=(4, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.TELEPORT_REASON)
        self.assertTrue(key.startswith("r"), key)
        self.assertTrue(memory(policy, raw).rallying)

    def test_summons_with_a_high_threat_teleport_even_with_a_ball(self):
        # No Healing or Speed carried: the survival rungs ahead of the summons stay quiet.
        raw = self.summoned(with_wand_list(board((5, 1), hp=480, healing=0, speed=0), FIRE_BALL),
                            race=geo.SPECTRAL_T, cell=(4, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        policy._player_hasted = lambda snapshot: True
        snapshot = parse_snapshot(copy.deepcopy(raw), RACES)
        self.assertTrue(policy._is_material_threat(snapshot, policy._physical_hostiles(snapshot)))
        # The plan's order beneath its 1-turn 即死 rung (owner 2026-11-07 「作戦が先・即死だけ例外」):
        # the spectral tyrannosaur's next action reaches HP 480, so the rung now answers first.
        with patch.object(threat_tiers, "instant_death_key", lambda policy, snapshot: None):
            key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.TELEPORT_REASON, key)
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, "emergency:teleport", key)

    def test_after_the_teleport_a_choke_is_taken_before_contact(self):
        # A landing in the east room, nothing in view: the nearest choke out of the summons is
        # the door [10,24] (south-west), while the walk back to [7,1] would go west.
        raw = board((8, 25))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus", rallying=True)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (step((8, 25), (9, 24)), battle.WALK_REASON))

    def test_three_kills_end_it_unseen_kills_count_for_the_aimed_pen(self):
        raw = board((5, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus", aimed_race=geo.IPSISSIMUS,
                 kills={geo.IPSISSIMUS: 2})
        raw["messages"] = ["何かを倒した。"]
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "stragglers")

    def test_one_seen_out_of_the_pen_counts_as_escaped(self):
        raw = board((5, 1), monsters=[monster(geo.IPSISSIMUS, 2, 25, index=903)])
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus", kills={geo.IPSISSIMUS: 2})
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "stragglers")


class Q25StragglersTest(unittest.TestCase):
    def test_waits_on_5_1_and_fifty_quiet_actions_end_it(self):
        raw = board((5, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "stragglers")
        for _ in range(battle.QUIET_ACTIONS):
            choose(policy, raw)
        self.assertNotEqual(phase_of(policy, raw), "stragglers")

    def test_an_escaped_ipsissimus_in_view_is_shot(self):
        raw = board((5, 1), monsters=[monster(geo.IPSISSIMUS, 5, 4, index=903)])
        policy = new_policy(raw)
        at_phase(policy, raw, "stragglers")
        choose(policy, raw)
        self.assertTrue((policy.last_reason or "").startswith(("ranged:", "magic-eater", "me-")),
                        policy.last_reason)


class Q25QuylthulgTest(unittest.TestCase):
    """phase3 1): 「範囲攻撃があればネクサス・クイルスルグを倒すまたはショートテレポートさせるまで撃つ」."""

    def test_a_radius_2_ball_catches_9_13_from_5_2(self):
        raw = with_wand_list(board((5, 2)), FIRE_BALL)
        policy = new_policy(raw)
        at_phase(policy, raw, "quylthulgs")
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("mB" + FIRE_BALL_LETTER + "@7,14", DEVICE_REASON))

    def test_walked_to_5_2_first(self):
        raw = with_wand_list(board((5, 1)), FIRE_BALL)
        policy = new_policy(raw)
        at_phase(policy, raw, "quylthulgs")
        self.assertEqual((choose(policy, raw), policy.last_reason), ("6", battle.WALK_REASON))

    def test_without_a_ball_the_step_is_skipped_for_the_tome(self):
        raw = board((5, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "quylthulgs")
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "tome")


class Q25TomeTest(unittest.TestCase):
    def test_no_ball_reaches_it_out_of_its_lines_so_it_is_shot_from_5_5_after_the_haste(self):
        raw = board((5, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "tome")
        self.assertEqual((choose(policy, raw), policy.last_reason), ("6", battle.WALK_REASON))
        raw["player"].update(y=5, x=5)
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.HASTE_REASON, key)
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.SHOT_REASON)
        self.assertTrue(key.endswith("*p3332t5\x1b"), key)   # to the tome's own cell [9,8]


class Q25TrapTest(unittest.TestCase):
    """phase4 「10回で打ち切る」 on a cell that may hold a trap; phase5 「見つかるまで探す」."""

    def test_the_way_to_1_6_crosses_3_1_after_ten_searches_and_never_the_corridor(self):
        raw = board((4, 1))
        open_door(raw, (4, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "corpse-masses")
        for _ in range(battle.MAYBE_TRAP_SEARCHES):
            self.assertEqual((choose(policy, raw), policy.last_reason), (SEARCH_KEY, battle.SEARCH_REASON))
        self.assertEqual((choose(policy, raw), policy.last_reason), ("8", battle.WALK_REASON))
        ctx = battle._ctx(policy, parse_snapshot(copy.deepcopy(raw), RACES))
        path = battle._path(ctx, {geo.MASS_STAND})
        self.assertNotIn((1, 4), path)
        self.assertFalse(set(path) & set(geo.NORTH_CORRIDOR))

    def test_an_always_trapped_cell_is_searched_past_ten(self):
        raw = board((1, 7))
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", style="ranged", searches={(1, 8): 25})
        self.assertEqual((choose(policy, raw), policy.last_reason), (SEARCH_KEY, battle.SEARCH_REASON))

    def test_a_found_trap_is_disarmed_then_crossed(self):
        raw = with_trap_shown(board((1, 7)), (1, 8))
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", style="ranged")
        self.assertEqual(choose(policy, raw), "D6")
        raw = board((1, 7))
        open_door(raw, (1, 7))
        choose(policy, raw)   # shown before, not now: disarmed
        self.assertIn((1, 8), memory(policy, raw).cleared)

    def test_a_disarming_device_is_aimed_first(self):
        raw = carried(board((1, 7)), TVAL_WAND, 4, "解除の魔法棒 (5回分)")
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", style="ranged")
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("al6", battle.DISARM_REASON))


class Q25CorpseMassTest(unittest.TestCase):
    def test_on_1_6_the_door_is_opened_then_the_masses_shot(self):
        raw = board((1, 6))
        policy = new_policy(raw)
        at_phase(policy, raw, "corpse-masses")
        self.assertEqual((choose(policy, raw), policy.last_reason), ("o6", battle.OPEN_REASON))
        raw = board((1, 6), monsters=[monster(geo.MASS, 1, 11, index=950)])
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "corpse-masses", lit=True)
        choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.SHOT_REASON)

    def test_none_left_in_view_from_1_6_ends_it(self):
        raw = board((1, 6))
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "corpse-masses", lit=True)
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "dreadmaster")


class Q25DreadmasterTest(unittest.TestCase):
    def test_ranged_waits_on_the_edge_of_its_vision(self):
        raw = without_melee(board((1, 9)))
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", cleared=frozenset({(1, 8), (1, 9)}))
        self.assertEqual((choose(policy, raw), policy.last_reason), (WAIT_KEY, HOLD_REASON))
        self.assertEqual(memory(policy, raw).style, "ranged")

    def test_melee_walks_to_1_17(self):
        raw = without_ranged(board((1, 9)))
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", cleared=frozenset(geo.NORTH_CORRIDOR))
        self.assertEqual((choose(policy, raw), policy.last_reason), ("6", battle.WALK_REASON))
        self.assertEqual(memory(policy, raw).style, "melee")

    def test_in_view_it_is_fought_hasted(self):
        raw = without_melee(board((1, 9), monsters=[monster(geo.DREADMASTER, 1, 14)]))
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", cleared=frozenset({(1, 8), (1, 9)}))
        choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.HASTE_REASON)


class Q25SweepTest(unittest.TestCase):
    ALL_BUT_LAST = {race: count for race, count in geo.ROSTER.items()
                    if race not in {geo.DRUJ, geo.STAIRWAY, geo.MASS}}

    def test_a_full_count_goes_on_to_the_stairway(self):
        raw = board((12, 24))
        policy = new_policy(raw)
        at_phase(policy, raw, "sweep", kills=dict(self.ALL_BUT_LAST))
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "stairway")

    def test_a_short_count_patrols_the_stands(self):
        raw = board((13, 1))
        kills = dict(self.ALL_BUT_LAST, **{str(geo.SHADOW): 0})
        kills = {int(race): count for race, count in kills.items()}
        policy = new_policy(raw)
        at_phase(policy, raw, "sweep", kills=kills)
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (step((13, 1), (13, 2)), battle.WALK_REASON))

    def test_detection_is_used_first_when_carried(self):
        raw = carried(board((12, 24)), TVAL_ROD, 6, "全感知のロッド", charges=0)
        policy = new_policy(raw)
        at_phase(policy, raw, "sweep", kills=dict(self.ALL_BUT_LAST))
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("zl", battle.DETECT_REASON))
        raw["detected_monsters"] = []
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "stairway")


class Q25StairwayTest(unittest.TestCase):
    def test_hasted_then_the_door_opened_then_shot_from_13_27(self):
        raw = board((13, 27))
        policy = new_policy(raw)
        at_phase(policy, raw, "stairway", style="ranged", cleared=frozenset({(13, 27)}))
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.HASTE_REASON, key)
        policy._player_hasted = lambda snapshot: True
        self.assertEqual((choose(policy, raw), policy.last_reason), ("o6", battle.OPEN_REASON))
        open_door(raw, geo.STAIRWAY_DOOR)
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.SHOT_REASON)
        self.assertTrue(key.endswith("*p66t5\x1b"), key)

    def test_a_summons_that_is_not_lethal_does_not_stop_it(self):
        # The spectre named casting a summons: the shared rule 1 would shoot it first.
        raw = board((13, 27), monsters=[monster(geo.SPECTRE, 12, 24, index=960)])
        raw["messages"] = [raw["visible_monsters"][0]["name"] + "が魔法でアンデッドを召喚した。"]
        open_door(raw, geo.STAIRWAY_DOOR)
        policy = new_policy(raw)
        at_phase(policy, raw, "stairway", style="ranged", cleared=frozenset({(13, 27)}))
        policy._player_hasted = lambda snapshot: True
        snapshot = parse_snapshot(copy.deepcopy(raw), RACES)
        self.assertIsNone(battle._summons(policy, snapshot))
        choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.SHOT_REASON)


class Q25DrujTest(unittest.TestCase):
    """phase7: 「ドアを開けずに13,20に移動して、11,19を岩石溶解して11,19に範囲攻撃を撃つ」."""

    def test_with_a_ball_and_stone_to_mud_the_door_is_melted_from_13_20(self):
        raw = with_wand_list(board((13, 20)), FIRE_BALL)
        policy = new_policy(raw)
        at_phase(policy, raw, "druj", cleared=frozenset({(13, 20)}))
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertTrue(key.startswith("af*p"), key)    # the carried Stone to Mud wand, slot f
        self.assertTrue(key.endswith("t5\x1b"), key)

    def test_the_melted_door_takes_the_ball(self):
        raw = with_wand_list(board((13, 20)), FIRE_BALL)
        for run in raw["grid_map"]["runs"]:
            if (run[0], run[1]) == geo.DRUJ_DOOR:
                run[3] = raw["grid_map"]["palette"].index(_palette_row("FLOOR"))
        policy = new_policy(raw)
        at_phase(policy, raw, "druj", cleared=frozenset({(13, 20)}))
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("mB" + FIRE_BALL_LETTER + "@11,19", DEVICE_REASON))

    def test_without_a_ball_the_door_is_opened_and_it_is_shot_from_a_trapless_line_cell(self):
        raw = board((12, 21))
        open_door(raw, geo.DRUJ_DOOR)
        policy = new_policy(raw)
        at_phase(policy, raw, "druj")
        policy._player_hasted = lambda snapshot: True
        choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.SHOT_REASON)

    def test_the_magic_eater_hastes_out_of_its_line_only(self):
        raw = board((12, 21))
        open_door(raw, geo.DRUJ_DOOR)
        policy = new_policy(raw)
        at_phase(policy, raw, "druj")
        choose(policy, raw)
        self.assertNotEqual(policy.last_reason, battle.HASTE_REASON)   # in its line
        raw = board((12, 24))
        policy = new_policy(raw)
        at_phase(policy, raw, "druj")
        choose(policy, raw)   # the door shut: no line
        self.assertEqual(policy.last_reason, battle.HASTE_REASON)


class Q25AcceptanceTest(unittest.TestCase):
    """phase5: 「透明なものが見えない時はクエストを受けない」, 「どれか1つでよい」."""
    FORCE = FILE_STRATEGIES[25].required_force

    def sight(self, abilities, flags=frozenset()):
        item = replace(parse_snapshot(copy.deepcopy(BASE), RACES).equipment[0], known_flags=frozenset(flags))
        return has_ability_or_alternative(self.FORCE, "see_invisible", frozenset(abilities), [item])

    def test_each_one_of_the_four_is_enough(self):
        self.assertTrue(self.sight({"see_invisible"}))
        self.assertTrue(self.sight({"telepathy"}))
        self.assertTrue(self.sight(set(), {105}))   # TR_ESP_UNDEAD
        self.assertTrue(self.sight(set(), {112}))   # TR_ESP_EVIL
        self.assertFalse(self.sight(set(), {113}))
        self.assertFalse(self.sight(set()))

    def ready(self, raw):
        policy = new_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), RACES)
        policy._approved_strategy_force_ready(snapshot, APPROVED[25])
        return "resists" in policy._fixed_quest_readiness["strategy_force"].get("failed", [])

    @staticmethod
    def resisting():
        """CONSTRUCTED: the other required resistances worn, so the sight alone decides."""
        raw = board()
        for name in ("resist_conf", "resist_blind", "resist_neth", "resist_pois", "free_action"):
            raw["player"]["ability_sources"][name] = {"equipment": True, "permanent": False,
                                                      "temporary": False}
        return raw

    def blind_to_the_invisible(self):
        raw = self.resisting()
        raw["player"]["ability_sources"]["see_invisible"] = {
            "equipment": False, "permanent": False, "temporary": False}
        raw["player"]["ability_sources"].pop("telepathy", None)
        for item in raw["equipment"]:
            item["known_flags"] = [flag for flag in item.get("known_flags", []) if flag not in {78, 79}]
        return raw

    def test_without_any_of_them_the_quest_is_refused(self):
        self.assertFalse(self.ready(self.resisting()))
        self.assertTrue(self.ready(self.blind_to_the_invisible()))

    def test_evil_esp_alone_lets_it_be_taken(self):
        raw = self.blind_to_the_invisible()
        raw["equipment"][0]["known_flags"] = [*raw["equipment"][0]["known_flags"], 112]
        self.assertFalse(self.ready(raw))


# -- the owner's answers of 2026-11-06 (phase2, phase3, wait_limits, phase7_druj) --------------

IPSISSIMUS_NAME = RACES[geo.IPSISSIMUS].names[0]


class Q25EscapeTest(unittest.TestCase):
    """phase2 「テレポートしたメッセージで判断」 and 「当たらない撃ちで補う」."""

    def pen(self, raw=None):
        raw = raw or board((5, 1))
        policy = new_policy(raw)
        at_phase(policy, raw, "ipsissimus")
        policy._player_hasted = lambda snapshot: True
        return policy, raw

    def test_the_teleport_line_counts_an_escape(self):
        policy, raw = self.pen()
        at_phase(policy, raw, "ipsissimus", kills={geo.IPSISSIMUS: 2})
        raw["messages"] = [IPSISSIMUS_NAME + "がテレポートした。"]
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "stragglers")

    def test_ten_unanswered_pen_shots_count_the_rest_escaped(self):
        policy, raw = self.pen()
        for _ in range(battle.PEN_MISSES_TO_ESCAPED):
            choose(policy, raw)
            self.assertEqual(policy.last_reason, battle.SHOT_REASON)
            self.assertEqual(phase_of(policy, raw), "ipsissimus")
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "stragglers")

    def test_a_hit_line_restarts_the_count(self):
        policy, raw = self.pen()
        for turn in range(battle.PEN_MISSES_TO_ESCAPED + 3):
            raw["messages"] = ["クロスボウの矢が何かに命中した。"] if turn == 5 else []
            choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "ipsissimus")

    def test_pain_lines_of_the_unseen_target_count_as_hits_for_a_ball_too(self):
        # The game's forms (monster-pain-describer.cpp, the common table of a 'p'), under the unseen
        # name: deal_effect_damage_from_player prints them within MAX_PLAYER_SIGHT, seen or not.
        for lines in (["何かは痛みで絶叫した。"], ["It shrugs off the attack."]):
            with self.subTest(lines=lines):
                policy, raw = self.pen(with_wand_list(board((5, 1)), FIRE_BALL))
                for _ in range(battle.PEN_MISSES_TO_ESCAPED + 3):
                    key = choose(policy, raw)
                    self.assertEqual((key, policy.last_reason), ("mBw@7,17", DEVICE_REASON))
                    raw["messages"] = list(lines)
                self.assertEqual(phase_of(policy, raw), "ipsissimus")

    def test_the_unseen_kill_line_counts_a_kill(self):
        policy, raw = self.pen()
        at_phase(policy, raw, "ipsissimus", kills={geo.IPSISSIMUS: 2}, aimed_race=geo.IPSISSIMUS)
        raw["messages"] = ["何かを殺した。"]   # monster-damage.cpp show_kill_message, !monster.ml
        choose(policy, raw)
        self.assertEqual(memory(policy, raw).kills[geo.IPSISSIMUS], 3)
        self.assertEqual(phase_of(policy, raw), "stragglers")

    def test_with_evil_esp_the_misses_do_not_count(self):
        raw = board((5, 1))
        raw["equipment"][0]["known_flags"] = [*raw["equipment"][0]["known_flags"], 112]
        policy, raw = self.pen(raw)
        for _ in range(battle.PEN_MISSES_TO_ESCAPED + 2):
            choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "ipsissimus")


class Q25DirectQuylTest(unittest.TestCase):
    """phase3 「加速して直接撃つ」 and 「…相対する可能性がある。その場合は加速して討伐を試みる。」."""

    def direct(self, position, **fields):
        raw = with_wand_list(board(position), FIRE_BALL)
        policy = new_policy(raw)
        at_phase(policy, raw, "quylthulgs", quyls_done=frozenset({(9, 13)}), **fields)
        return policy, raw

    def test_with_radius_2_balls_the_9_9_quyl_is_walked_to_a_line_cell(self):
        policy, raw = self.direct((5, 2))
        choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.WALK_REASON)
        self.assertEqual(phase_of(policy, raw), "quylthulgs")

    def test_on_a_line_cell_haste_then_the_shot(self):
        policy, raw = self.direct((7, 9))
        choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.HASTE_REASON)
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertIn(policy.last_reason, {battle.SHOT_REASON, DEVICE_REASON}, key)

    def test_its_kill_marks_the_aimed_one_only(self):
        policy, raw = self.direct((7, 9), aimed_race=geo.QUYL)
        record = memory(policy, raw)
        record.quyls_done = frozenset()
        record.aimed_quyl = (9, 13)
        raw["messages"] = ["何かを倒した。"]
        choose(policy, raw)
        self.assertIn((9, 13), memory(policy, raw).quyls_done)
        self.assertNotIn((9, 9), memory(policy, raw).quyls_done)

    def test_faced_with_the_dreadmaster_after_a_teleport_away_it_hastes_and_fights(self):
        policy, raw = self.direct((12, 22))
        raw["visible_monsters"] = [monster(geo.DREADMASTER, 12, 25, index=970)]
        choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.HASTE_REASON)
        policy._player_hasted = lambda snapshot: True
        choose(policy, raw)
        self.assertNotEqual(policy.last_reason, battle.WALK_REASON)


class Q25WaitLimitTest(unittest.TestCase):
    """wait_limits 「仮に5000にする」."""

    def test_the_ambush_ends_after_5000_quiet_actions(self):
        raw = without_melee(board((13, 1)))
        open_door(raw, geo.WEST_DOOR)
        policy = new_policy(raw)
        at_phase(policy, raw, "ambush", quiet=battle.LONG_WAIT_ACTIONS - 2)
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "ambush")
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "wall-passers")

    def test_the_dreadmasters_wait_ends_after_5000(self):
        raw = without_melee(board((1, 9)))
        open_door(raw, (1, 7))
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", quiet=battle.LONG_WAIT_ACTIONS - 1,
                 cleared=frozenset({(1, 8), (1, 9)}))
        choose(policy, raw)
        self.assertEqual(phase_of(policy, raw), "sweep")


ANTI_TELEPORT = 68


def with_piece(raw, *, tval=45, sval=0, flags=(ANTI_TELEPORT,), **fields):
    """CONSTRUCTED: an identified ring (or other piece) of anti-teleportation in the pack."""
    row = copy.deepcopy(next(item for item in BASE["equipment"] if item["slot"] == "main_ring"))
    row.update(tval=tval, sval=sval, slot="m", name="反テレポートの指輪", known_flags=list(flags), **fields)
    raw["inventory"].append(row)
    return raw


class Q25DrujGearTest(unittest.TestCase):
    """phase7_druj 「反テレポート付きで他のデメリットがない装備がもしあれば、持ち込んでこの戦闘でのみ使用する。」."""

    def snapshot(self, raw):
        return parse_snapshot(copy.deepcopy(raw), RACES)

    def test_only_a_clean_piece_qualifies(self):
        piece = lambda **fields: self.snapshot(with_piece(board(), **fields)).inventory[-1]
        self.assertTrue(druj_gear.qualifies(piece()))
        self.assertFalse(druj_gear.qualifies(piece(flags=(ANTI_TELEPORT, 91))))   # aggravation
        self.assertFalse(druj_gear.qualifies(piece(pval=-2)))
        self.assertFalse(druj_gear.qualifies(piece(flags=(91,))))
        self.assertFalse(druj_gear.qualifies(piece(tval=22)))                      # a weapon

    def test_the_slot_loses_no_required_ability(self):
        raw = with_piece(board())
        # CONSTRUCTED: see invisible only from the left ring.
        for item in raw["equipment"]:
            item["known_flags"] = [flag for flag in item["known_flags"] if flag != 78]
            if item["slot"] == "main_ring":
                item["known_flags"].append(78)
        raw["player"]["ability_sources"]["see_invisible"] = {   # not the race's own sight
            "equipment": True, "permanent": False, "temporary": False}
        policy = new_policy(raw)
        snapshot = self.snapshot(raw)
        force = policy._strategy_force_for_snapshot(snapshot, APPROVED[25])
        self.assertEqual(druj_gear.slot_for(policy, snapshot, force, snapshot.inventory[-1]), "sub_ring")

    def test_worn_for_the_druj_and_put_back_after(self):
        raw = with_piece(board((12, 24)))
        policy = new_policy(raw)
        at_phase(policy, raw, "druj")
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, f"quest25:{druj_gear.WEAR_GOAL}", key)
        self.assertTrue(key.startswith("w"), key)
        self.assertEqual(memory(policy, raw).displaced[0], "main_ring")
        # Worn; then the druj killed: the displaced ring goes back on.
        ring = next(item for item in raw["equipment"] if item["slot"] == "main_ring")
        piece = raw["inventory"].pop()
        raw["inventory"].append(dict(ring, slot="m"))
        raw["equipment"] = [dict(piece, slot="main_ring") if item["slot"] == "main_ring" else item
                            for item in raw["equipment"]]
        raw["messages"] = [RACES[geo.DRUJ].names[0] + "を倒した。"]
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, f"quest25:{druj_gear.RESTORE_GOAL}", key)
        self.assertTrue(key.startswith("w"), key)

    @staticmethod
    def wearing(position, *, hp, monsters=()):
        """CONSTRUCTED: the anti-teleport ring worn (left ring), the druj's door open."""
        raw = board(position, hp=hp, monsters=monsters)
        for item in raw["equipment"]:
            if item["slot"] == "main_ring":
                item["known_flags"] = [*item["known_flags"], ANTI_TELEPORT]
        open_door(raw, geo.DRUJ_DOOR)
        return raw

    def druj_policy(self, raw):
        policy = new_policy(raw)
        at_phase(policy, raw, "druj")
        policy._player_hasted = lambda snapshot: True
        return policy

    def test_below_the_line_with_it_worn_the_walk_leaves_the_druj_line(self):
        # Owner 2026-11-07 「歩いてドルジの射線から外れる。」: no Teleportation, no potion in the line.
        # The stand was reached from the dreadmaster's room door [10,24] over [11,23] (searched and cleared).
        raw = self.wearing((12, 22), hp=300, monsters=[monster(geo.DRUJ, 11, 18)])
        policy = self.druj_policy(raw)
        at_phase(policy, raw, "druj", cleared=frozenset({(11, 23)}))
        key = choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (step((12, 22), (11, 23)), battle.RETREAT_REASON))
        self.assertTrue(memory(policy, raw).retreating)
        raw["player"].update(y=11, x=23)
        self.assertEqual((choose(policy, raw), policy.last_reason), ("o9", battle.RETREAT_REASON))  # its door
        self.assertNotIn((10, 24), geo.line_cells(geo.opened(TERRAIN, [geo.DRUJ_DOOR]), (11, 18)))

    def test_out_of_the_line_it_rests_and_drinks_only_when_the_rest_did_not_heal(self):
        raw = self.wearing((13, 21), hp=300)
        policy = self.druj_policy(raw)
        at_phase(policy, raw, "druj", retreating=True, cleared=frozenset({(13, 21)}))
        self.assertEqual((choose(policy, raw), policy.last_reason), (REST_MACRO, battle.RETREAT_REST_REASON))
        key = choose(policy, raw)    # the rest gave nothing (HP unchanged): 「必要なら…薬を飲む」
        self.assertEqual(policy.last_reason, battle.RETREAT_HEAL_REASON, key)
        self.assertTrue(key.startswith("q"), key)

    def test_full_again_the_fight_goes_on(self):
        raw = self.wearing((13, 21), hp=q25.FULL_HP)
        policy = self.druj_policy(raw)
        at_phase(policy, raw, "druj", retreating=True, cleared=frozenset({(13, 21)}))
        choose(policy, raw)
        self.assertNotIn(policy.last_reason, {battle.RETREAT_REASON, battle.RETREAT_REST_REASON})
        self.assertFalse(memory(policy, raw).retreating)

    def test_control_without_the_piece_the_old_line_reads_teleportation(self):
        raw = board((12, 22), hp=300, monsters=[monster(geo.DRUJ, 11, 18)])
        open_door(raw, geo.DRUJ_DOOR)
        policy = self.druj_policy(raw)
        at_phase(policy, raw, "druj", cleared=frozenset({(11, 23)}))
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, q25.TELEPORT_REASON, key)

    def test_kept_in_the_pack_and_wanted_from_home(self):
        raw = with_piece(board((12, 24)))
        policy = new_policy(raw)
        snapshot = self.snapshot(raw)
        self.assertTrue(druj_gear.kept(policy, snapshot, snapshot.inventory[-1]))
        policy._target_loadout_known = lambda: True   # DECLARED: a target loadout, so spare gear is released
        plain = self.snapshot(with_piece(board((12, 24)), flags=(50,)))   # control: a plain spare ring
        self.assertTrue(spare_gear.released(policy, plain, plain.inventory[-1]))
        self.assertFalse(spare_gear.released(policy, snapshot, snapshot.inventory[-1]))
        # DECLARED: a current Home catalogue holding the piece.
        bare = self.snapshot(board((12, 24)))
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [snapshot.inventory[-1]]
        policy._home_knowledge_valid_before = 1
        self.assertIs(druj_gear.home_piece(policy, bare, APPROVED[25]), snapshot.inventory[-1])
        self.assertIsNone(druj_gear.home_piece(policy, snapshot, APPROVED[25]))   # carried already
        self.assertTrue(quest_optional_carry._missing(policy, bare, APPROVED[25]))


if __name__ == "__main__":
    unittest.main()
