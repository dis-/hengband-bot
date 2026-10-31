"""D17: the recorded Lv7 Magic-Eater takes quest 1 with its carried torches.

The boundaries are the 2026-10-29 verification-machine stops after Q34
(cleared at Lv7, 184 gold, 21 torches, no potions).  Only replies to newly
posted keys are constructed; the recorded stats, inventory and shelves are not.
"""
import tests  # noqa: F401
import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.magic_eater import MISSILE_REASON
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "me-q1-torch-20261029.json.gz"


class MagicEaterQ1TorchRecordedTest(executor_harness.ProductionHarness):
    post = lv7.Lv7TownStopRecordedTest.post
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def boundary(self, **kwargs):
        return lv7.Lv7TownStopRecordedTest().boundary(self.case, **kwargs)

    def board(self, policy, raw):
        return parse_snapshot(raw, policy._monrace_knowledge)

    def test_recorded_stops_are_the_force_gate_and_the_reward_latch(self):
        readiness = self.case["recorded_readiness"]
        self.assertEqual((self.case["recorded_key"], self.case["recorded_reason"]),
                         ("", "quest:blocked:opening-route"))
        self.assertEqual(readiness["opening_route_failure"], "stop:stock:quest-healing")
        self.assertEqual(readiness["strategy_force"]["dps"], {"measured": 4.62, "required": 18.0})
        self.assertEqual(self.case["recorded_reward_failure"], "reward-unavailable")
        player = self.case["snapshot"]["player"]
        self.assertEqual((player["class_id"], player["level"], player["max_hp"], player["gold"]),
                         (16, 7, 107, 184))

    def test_census_board_requests_q1_with_its_carried_torches(self):
        # 2026-10-30 「松明20本はキープして。」: the class-16 Q1 carry is the
        # fixed 20 torches (the derived need 9 is a floor inside it), so the
        # recorded 21 still suffice and nothing is bought.
        # Unfixed, this board travelled to the black market for the two
        # Healing and one Speed potions of the class-16 force gate, then
        # stopped on their stock (recorded above).
        for kit_bought in (False, True):
            with self.subTest(kit_bought=kit_bought):
                self.census_drive(kit_bought)

    def census_drive(self, kit_bought):
        # DECLARED CONSTRUCTED (kit_bought=True): the optional mining-kit
        # survey of shelves this capture never observed is marked done, so
        # the drive reaches the Q1 request.  Without it the route continues
        # to that bounded survey, not a block.
        policy, raw = self.boundary(kit_bought=kit_bought)
        board = self.board(policy, raw)
        self.assertTrue(policy._fixed_quest_ready(board, 1), policy.fixed_quest_readiness_state())
        details = policy.fixed_quest_readiness_state()
        self.assertEqual(details["strategy_force"]["failed"], [])
        self.assertEqual(details["strategy_force"]["lit_torch"], {"measured": 21, "required": 20})
        self.assertEqual([row[1:3] for row in policy._opening_q1_requirements(board)],
                         [(20, 21), (0, 0), (0, 0)])
        key = str(policy.choose_key(board))
        if not kit_bought:
            self.assertEqual((key, policy.last_reason), ("\x1b`n!.", "shop:travel"))
            stage, store = policy._opening_q1_plan(board)[:2]
            self.assertTrue(stage.startswith("observe:fundraising-"), stage)
            following = copy.deepcopy(raw)
            following["turn"] += 1
            self.post(policy, raw, key, following)
            return
        # D48: the worn Brass Lantern {average} is kept, not swapped for a torch.
        self.assertEqual(policy.last_reason, "fixedquest:request:approach", key)
        following = copy.deepcopy(raw)
        following["turn"] += 1
        self.post(policy, raw, key, following)

    def test_completed_reward_pickup_continues_to_the_torch_purchase(self):
        policy, _ = self.boundary()
        raw = copy.deepcopy(self.case["reward_snapshot"])
        # DECLARED RECONSTRUCTED: the live in-memory reward latch of the
        # pickup decision that preceded this board (cleared on completion).
        policy._fixed_quest_reward_pending = 34
        key = str(policy.choose_key(self.board(policy, raw)))
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None), policy.last_reason)
        self.assertNotEqual(key, "")
        following = copy.deepcopy(raw)
        following["turn"] += 1
        self.post(policy, raw, key, following)


class MagicEaterQ1ThrowPlanTest(unittest.TestCase):
    """In Q1 the Magic-Eater throws torches, then the missile aid, then melee."""

    def decide(self, *, class_id=16, torches=5, charges=None):
        from hengbot.model import Snapshot, TVAL_LITE, SV_LITE_TORCH
        from hengbot.policy import HengbotPolicy
        from hengbot.quest_strategies import load_quest_strategies
        from policy_fixtures import grid, hostile, item, player

        profile = load_quest_strategies(Path(__file__).parents[1] / "strategy" / "quests")[1]
        policy = HengbotPolicy(quest_strategies={1: profile})
        # DECLARED CONSTRUCTED: a bandit adjacent to the approved [8,3] hold.
        bandit = replace(hostile(1, 8, 4, hp=36, max_hp=36, distance=1), race_id=150)
        inventory = [item("a", TVAL_LITE, SV_LITE_TORCH, count=torches, fuel=2500,
                          known=True, name="Wooden Torch")] if torches else []
        snapshot = Snapshot(
            player(8, 3, hp=107, max_hp=107, level=7, class_id=class_id,
                   main_hand_blows=1),
            {Position(8, x): grid(8, x, monster=x == 4) for x in range(1, 7)},
            [bandit], floor_key=(0, 5, 1), inventory=inventory,
        )
        snapshot = replace(snapshot, magic_eater_wand_charges=charges)
        key = policy._approved_quest_strategy_key(snapshot, [bandit], [bandit])
        return str(key), policy.last_reason

    def test_adjacent_thief_gets_a_thrown_torch(self):
        key, reason = self.decide()
        self.assertEqual(reason, "quest-strategy:throw-torch")
        self.assertTrue(key.startswith("v") and key.endswith("6"), key)

    def test_missile_is_the_aid_once_torches_are_out(self):
        self.assertEqual(self.decide(torches=0), ("mBp6", MISSILE_REASON))
        # An observed empty power list falls back to melee on that board.
        self.assertEqual(self.decide(torches=0, charges=0), ("6", "quest-strategy:melee"))

    def test_warrior_keeps_melee_against_the_adjacent_thief(self):
        self.assertEqual(self.decide(class_id=0), ("6", "quest-strategy:melee"))


if __name__ == "__main__":
    unittest.main()
