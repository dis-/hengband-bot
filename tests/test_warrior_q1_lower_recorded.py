"""D20: the recorded Lv7 zombie warrior takes quest 1 on the torch premise.

The boundary is the 2026-10-30 08:12:45 viewing-character stop after Q34
(Lv7, max HP 177, Broad Sword 2d5 with 3 blows, 14 lit torches, no potions).
Only replies to newly posted keys are constructed; the recorded stats,
inventory and shelves are not.
"""
import tests  # noqa: F401
import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.quest_strategies import acceptance_dps_floor, acceptance_hp_floor, load_quest_strategies
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "warrior-q1-lower-20261030.json.gz"
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"


class WarriorQ1LowerRecordedTest(executor_harness.ProductionHarness):
    post = lv7.Lv7TownStopRecordedTest.post
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    equip_reply = staticmethod(lv7.Lv7TownStopRecordedTest.equip_reply)

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def boundary(self, **kwargs):
        return lv7.Lv7TownStopRecordedTest().boundary(self.case, **kwargs)

    def board(self, policy, raw):
        return parse_snapshot(raw, policy._monrace_knowledge)

    def test_recorded_stop_is_the_warrior_force_gate(self):
        readiness = self.case["recorded_readiness"]
        self.assertEqual((self.case["recorded_key"], self.case["recorded_reason"]),
                         ("", "quest:blocked:opening-route"))
        self.assertEqual(readiness["opening_route_failure"], "stop:stock:quest-healing")
        force = readiness["strategy_force"]
        self.assertEqual(force["dps"], {"measured": 24.9, "required": 28.0})
        self.assertEqual(force["failed"], ["dps", "speed_potions", "heal_potions"])
        self.assertEqual(force["lit_torch"], {"measured": 14, "required": 5})
        player = self.case["snapshot"]["player"]
        self.assertEqual((player["class_id"], player["race_id"], player["level"], player["max_hp"]),
                         (0, 25, 7, 177))

    def test_census_board_equips_light_and_requests_q1(self):
        # DECLARED CONSTRUCTED: the optional mining-kit survey of shelves this
        # capture never observed is marked done, so the drive reaches Q1.
        policy, raw = self.boundary(kit_bought=True)
        board = self.board(policy, raw)
        # Unfixed, this board was refused for the default dps floor 28 and
        # then for the two Healing and one Speed potions (recorded above).
        self.assertTrue(policy._fixed_quest_ready(board, 1), policy.fixed_quest_readiness_state())
        force = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertEqual(force["failed"], [])
        self.assertEqual(force["dps"], {"measured": 24.9, "required": 14.89})
        self.assertEqual([row[1] for row in policy._opening_q1_requirements(board)], [5, 0, 0])
        key = str(policy.choose_key(board))
        self.assertEqual((key[0], policy.last_reason), ("w", "opening-q1:equip-light"))
        following = self.equip_reply(raw, key)
        self.post(policy, raw, key, following)
        raw = following
        key = str(policy.choose_key(self.board(policy, raw)))
        self.assertEqual(policy.last_reason, "fixedquest:request:approach", key)
        following = copy.deepcopy(raw)
        following["turn"] += 1
        self.post(policy, raw, key, following)

    def test_census_board_without_kit_survey_continues_the_bounded_route(self):
        # Without the survey mark the route goes on to that existing bounded
        # survey (general store) instead of blocking on potions.
        policy, raw = self.boundary()
        board = self.board(policy, raw)
        key = str(policy.choose_key(board))
        self.assertEqual((key, policy.last_reason), ("\x1b`n!.", "shop:travel"))
        stage, store = policy._opening_q1_plan(board)[:2]
        self.assertTrue(stage.startswith("observe:fundraising-"), stage)
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))
        following = copy.deepcopy(raw)
        following["turn"] += 1
        self.post(policy, raw, key, following)


class WarriorQ1FloorsTest(unittest.TestCase):
    """The class-0 floors derived in QUEST_1.jsonc from the game formulas."""

    def test_derived_floors(self):
        force = load_quest_strategies(STRATEGIES)[1].required_force
        tier = force["no_healing_tier"]
        # skill_tht 0 + 55 + 30*5//10 + 0 = 70, minus distance 2.
        chance = 0 + 55 + 30 * 5 // 10 + 0 - 2
        hit = {ac: 0.05 + 0.90 * (1 - (ac * 3 // 4) / chance) for ac in (24, 12)}
        torch = {ac: 8.75 * rate for ac, rate in hit.items()}
        self.assertAlmostEqual((36 - torch[24]) / 2, 14.886, places=3)
        self.assertLessEqual((20 - torch[12]) / 14.89, 1)
        self.assertEqual(acceptance_dps_floor(force, 0), 14.89)
        self.assertEqual(acceptance_dps_floor(tier, 0), 14.89)
        self.assertEqual(acceptance_hp_floor(tier, 0), (2 * 2 * 12 + 2 * 1 * 10) * 2)
        self.assertEqual(acceptance_hp_floor(force, 0), 56)
        self.assertEqual(force["throwing_items"], {"lit_torch": 5})
        # Class 16 and the default floors are unchanged.
        self.assertEqual((acceptance_dps_floor(force, 16), acceptance_hp_floor(tier, 16)), (4.58, 98))
        self.assertEqual((acceptance_dps_floor(force, 3), acceptance_hp_floor(tier, 3)), (28.0, 88))


class WarriorQ1ThrowPremiseTest(unittest.TestCase):
    """The premise: a lit torch at a thief two cells away, melee once adjacent."""

    def decide(self, distance):
        from hengbot.model import Snapshot, TVAL_LITE, SV_LITE_TORCH
        from hengbot.policy import HengbotPolicy
        from policy_fixtures import grid, hostile, item, player

        profile = load_quest_strategies(STRATEGIES)[1]
        policy = HengbotPolicy(quest_strategies={1: profile})
        # DECLARED CONSTRUCTED: a bandit approaching the approved [8,3] hold.
        bandit = replace(hostile(1, 8, 3 + distance, hp=36, max_hp=36, distance=distance),
                         race_id=150)
        torches = [item("a", TVAL_LITE, SV_LITE_TORCH, count=5, fuel=2500,
                        known=True, name="Wooden Torch")]
        snapshot = Snapshot(
            player(8, 3, hp=177, max_hp=177, level=7, class_id=0, main_hand_blows=3),
            {Position(8, x): grid(8, x, monster=x == 3 + distance) for x in range(1, 7)},
            [bandit], floor_key=(0, 5, 1), inventory=torches,
        )
        adjacent = [bandit] if distance == 1 else []
        key = policy._approved_quest_strategy_key(snapshot, [bandit], adjacent)
        return str(key), policy.last_reason

    def test_torch_at_distance_two_then_melee(self):
        key, reason = self.decide(2)
        self.assertEqual(reason, "quest-strategy:throw-torch")
        self.assertTrue(key.startswith("v") and key.endswith("6"), key)
        self.assertEqual(self.decide(1), ("6", "quest-strategy:melee"))


if __name__ == "__main__":
    unittest.main()
