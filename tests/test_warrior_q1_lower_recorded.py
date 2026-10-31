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
import math
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.quest_strategies import (
    acceptance_dps_floor, acceptance_hp_floor, class_throwing_items, load_quest_strategies,
)
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

    def test_census_board_keeps_the_lantern_and_requests_q1(self):
        # DECLARED CONSTRUCTED: the optional mining-kit survey of shelves this
        # capture never observed is marked done, so the drive reaches Q1.
        policy, raw = self.boundary(kit_bought=True)
        board = self.board(policy, raw)
        # Unfixed, this board was refused for the default dps floor 28 and
        # then for the two Healing and one Speed potions (recorded above).
        self.assertTrue(policy._fixed_quest_ready(board, 1), policy.fixed_quest_readiness_state())
        force = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertEqual(force["failed"], [])
        self.assertEqual(force["dps"], {"measured": 24.9, "required": 13.23})
        # Bad-luck HP floor 88 (2026-10-30 「運が悪い時の余裕を大きく取りたい」) still admits HP 177.
        self.assertEqual(force["hp"], {"measured": 177, "required": 88})
        self.assertEqual([row[1] for row in policy._opening_q1_requirements(board)], [5, 0, 0])
        key = str(policy.choose_key(board))
        # D48: the worn Brass Lantern is kept, not swapped for a torch.
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


# A lit torch hit: Dice(1,6), fire brand x2.5 truncated, TR_THROW x(3+1),
# then the lowest to_d_m (-2, STR 3); the critical bonus is left out.
TORCH_HIT = sum(roll * 25 // 10 * 4 - 2 for roll in range(1, 7)) / 6


# The largest damage of one thief action: r_idx 150 HIT 2d6, r_idx 44 HIT 1d5 x2.
MAX_BLOW = {150: 12, 44: 10}


def hit_chance(chance, ac):
    return 0.05 + 0.90 * (1 - (ac * 3 // 4) / chance)


class TorchQuestFloorsTest(unittest.TestCase):
    """The torch floors derived in QUEST_1/QUEST_34.jsonc from the game formulas."""

    def test_torch_hit_average(self):
        self.assertEqual(TORCH_HIT, 32.0)
        self.assertEqual(sum(roll * 4 - 2 for roll in range(1, 7)) / 6, 12.0)  # IM_FIRE

    def test_warrior_q1_floors(self):
        force = load_quest_strategies(STRATEGIES)[1].required_force
        tier = force["no_healing_tier"]
        # skill_tht 0 + 55 + 30*5//10 + 0 = 70, minus distance 2.
        torch = TORCH_HIT * hit_chance(0 + 55 + 30 * 5 // 10 + 0 - 2, 24)
        self.assertAlmostEqual(36 - torch, 13.2235, places=4)
        for gate in (force, tier):
            self.assertEqual(acceptance_dps_floor(gate, 0), 13.23)
            self.assertGreaterEqual(acceptance_dps_floor(gate, 0) + torch, 36)
        # 2026-10-30 「運が悪い時の余裕を大きく取りたい」: both tiers take the
        # bad-luck side (thief blows hit 100% at max dice, 2d6=12 / 2*1d5=10,
        # one exposed action each) in the 50% budget instead of the expected 36.
        bad_luck = (2 * 1 * MAX_BLOW[150] + 2 * 1 * MAX_BLOW[44]) / 0.50
        self.assertEqual(bad_luck, 88)
        # Every torch missing (melee alone: 3 and 2 actions) would exclude the
        # recorded HP 177 board, so the largest met floor 88 (> expected x2 72) is kept.
        all_miss = (2 * math.ceil(36 / 13.23) * MAX_BLOW[150]
                    + 2 * math.ceil(20 / 13.23) * MAX_BLOW[44]) / 0.50
        self.assertEqual(all_miss, 224)
        self.assertGreater(all_miss, 177)
        self.assertEqual((acceptance_hp_floor(force, 0), acceptance_hp_floor(tier, 0)),
                         (max(bad_luck, 36 * 2), 88))
        # The warrior keeps the 2026-10-26 opening carry of 5 (one per thief plus one).
        self.assertEqual(class_throwing_items(force, 0), {"lit_torch": 5})
        self.assertEqual(force["throwing_items"], {"lit_torch": 5})
        self.assertEqual((acceptance_dps_floor(force, 3), acceptance_hp_floor(tier, 3)), (28.0, 88))

    def test_magic_eater_q1_floors(self):
        force = load_quest_strategies(STRATEGIES)[1].required_force
        chance = 0 + 35 + 11 * 5 // 10 + 0 - 2
        throws = {hp: hp / (TORCH_HIT * hit_chance(chance, ac)) for hp, ac in ((36, 24), (20, 12))}
        need = 2 * math.ceil(throws[36]) + 2 * math.ceil(throws[20]) + 1
        self.assertEqual(need, 9)
        # The owner's fixed carry 20 also covers every first throw missing (8+4).
        self.assertLessEqual(need - 1 + 4, 20)
        self.assertEqual(class_throwing_items(force, 16), {"lit_torch": 20})
        steal_out = 1 - 0.7328
        damage = 2 * 5.0 * (1 - (1 - steal_out) ** max(0, throws[36] - 1)) / steal_out
        self.assertEqual(throws[20] < 1, True)
        expected = math.ceil(damage / 0.50)
        self.assertEqual(expected, 23)
        # Bad luck: 100% hit, max dice, exposure ceil(expected throws) - 1 = 2 / 0.
        exposure = {hp: math.ceil(n) - 1 for hp, n in throws.items()}
        self.assertEqual(exposure, {36: 2, 20: 0})
        bad_luck = (2 * exposure[36] * MAX_BLOW[150] + 2 * exposure[20] * MAX_BLOW[44]) / 0.50
        self.assertEqual(bad_luck, 96)
        # Stricter candidates exclude the recorded HP 107 board: a contact action
        # at r_idx 44 (136) or every first throw missing (3/1 actions, 184).
        contact = (2 * 2 * MAX_BLOW[150] + 2 * 1 * MAX_BLOW[44]) / 0.50
        first_miss = (2 * 3 * MAX_BLOW[150] + 2 * 1 * MAX_BLOW[44]) / 0.50
        self.assertEqual((contact, first_miss), (136, 184))
        self.assertGreater(min(contact, first_miss), 107)
        floor = max(bad_luck, expected * 2)
        self.assertEqual(acceptance_hp_floor(force, 16), floor)
        self.assertEqual(acceptance_hp_floor(force["no_healing_tier"], 16), floor)
        self.assertEqual(acceptance_dps_floor(force, 16), 3.6)

    def test_q34_torch_count(self):
        force = load_quest_strategies(STRATEGIES)[34].required_force
        rate = hit_chance(68, 40)
        throws = 2 * math.ceil(36 / (12.0 * rate)) + math.ceil(49 / (TORCH_HIT * rate))
        self.assertEqual(throws, 15)
        expected_need = math.ceil(throws * rate * 0.50 + rate * 0.50) + 6
        # Bad luck: every hit torch breaks (2*3 + 2 hits, plus the bee's throw).
        bad_luck_need = 2 * math.ceil(36 / 12.0) + math.ceil(49 / TORCH_HIT) + 1 + 6
        self.assertEqual((expected_need, bad_luck_need), (11, 15))
        # The owner's fixed carry 20 holds both derived needs.
        self.assertEqual(force["throwing_items"], {"lit_torch": 20})


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
