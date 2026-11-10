"""The Stone to Mud wands' Tower recharge when gold allows (owner 2026-11-10).

Owner, verbatim (the Anaguma stock answer): 「資金に余裕があるとき魔法棒を塔でチャージする」.

Recorded boards of the Q2 Tower test (tests/fixtures/quest-stops-20261030.json.gz, n1-a
life-422, a warrior with one Stone to Mud wand of one charge, Morivant listed): the last
Outpost board, and the Morivant board beside the Tower of Sorcery that test builds
(``tower_board``).  DECLARED CONSTRUCTED: Q2 is marked finished on every board (so the Q2
trip, q2_tower_recharge, does not apply), the wand holds 3 charges, and the replies to the
posted keys are the Q2 test's (``recharge_reply``, ``moved``).  DECLARED RECONSTRUCTED as in
that test: no Home page and no skill reply.

Composition: the errand starts at the recall read (policy_town ``_town_special_key`` calls
``wand_tower_recharge.town_key``); no recorded board reaches that read with this character, so
the start is that call on the Outpost board (the producer).  From there every decision is the
public ``choose_key`` of the same policy instance (the consumer: ``trip_key`` in the town
owner chain, policy_quest), and the recharge is posted through the production executor port.
"""

import tests  # noqa: F401 -- isolate runtime files

import copy

from hengbot import morivant_tower, wand_tower_recharge as trip
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import parse_snapshot
from hengbot.policy_constants import MORIVANT_TOWN_ID, OUTPOST_TOWN_ID, TOWN_TELEPORT_COST
from tests import test_q2_tower_recharge_recorded as q2
from tests.support import recorded as executor_pins
from tests.test_me_tower_recharge_recorded import recharge_all_screens

Q2_DONE = {"complev": 20, "comptime": 500, "fixed": True, "id": 2, "level": 10, "name": "q2",
           "status": 4, "type": 1}


class WandTowerRechargeRecordedTest(executor_pins.ProductionHarness):
    # The Q2 Tower test's recorded boards, policy construction and replies (as the armour
    # smith's test borrows them; its tests are not run again here).
    policy = q2.Q2TowerRechargeRecordedTest.policy
    decide = q2.Q2TowerRechargeRecordedTest.decide
    post = q2.Q2TowerRechargeRecordedTest.post
    wand = staticmethod(q2.Q2TowerRechargeRecordedTest.wand)
    moved = staticmethod(q2.Q2TowerRechargeRecordedTest.moved)
    tower_board = q2.Q2TowerRechargeRecordedTest.tower_board
    recharge_reply = q2.Q2TowerRechargeRecordedTest.recharge_reply
    destination = q2.Q2TowerRechargeRecordedTest.destination

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        q2.Q2TowerRechargeRecordedTest.setUpClass.__func__(cls)

    def adjusted(self, raw, charges=3):
        raw = copy.deepcopy(raw)
        raw["progress"]["quests"].append(dict(Q2_DONE))
        wand = self.wand(raw)
        wand["name"] = wand["name"].replace(f"({wand['charges']}回分)", f"({charges}回分)")
        wand["charges"] = wand["pval"] = charges
        return raw

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.monraces)

    def test_spare_gold_starts_the_trip_to_morivant(self):
        raw = self.adjusted(self.q2["outpost_board"])
        policy = self.policy(raw)
        board = self.board(raw)
        self.assertTrue(trip.applies(policy, board))
        self.assertTrue(trip.spare(policy, board, 2))
        key = trip.town_key(policy, board)
        self.assertIsNotNone(key)
        self.assertEqual(policy.last_reason.removesuffix("-step-off"), trip.TRAVEL_REASON)
        self.assertEqual(trip.state(policy).origin, OUTPOST_TOWN_ID)

    def test_no_trip_without_spare_gold_or_for_a_magic_eater(self):
        raw = self.adjusted(self.q2["outpost_board"])
        policy = self.policy(raw)
        board = self.board(raw)
        reserve = policy._full_departure_resupply_reserve(board)
        cost = morivant_tower.recharge_cost(board) + 2 * TOWN_TELEPORT_COST
        with self.subTest("one gold short"):
            # DECLARED CONSTRUCTED: the gold one below the reserve after the trip.
            short = copy.deepcopy(raw)
            short["player"]["gold"] = reserve + cost - 1
            policy = self.policy(short)
            self.assertIsNone(trip.town_key(policy, self.board(short)))
        with self.subTest("Magic-Eater"):
            eater = copy.deepcopy(raw)
            eater["player"]["class_id"] = PLAYER_CLASS_MAGIC_EATER
            policy = self.policy(eater)
            self.assertIsNone(trip.town_key(policy, self.board(eater)))
        with self.subTest("full wand"):
            full = self.adjusted(self.q2["outpost_board"], charges=12)
            policy = self.policy(full)
            self.assertIsNone(trip.town_key(policy, self.board(full)))

    def test_the_tower_fills_the_wand_and_the_inn_takes_the_player_back(self):
        start = self.adjusted(self.q2["outpost_board"])
        policy = self.policy(start)
        self.assertIsNotNone(trip.town_key(policy, self.board(start)))
        tower = self.adjusted(self.tower_board())
        key = self.decide(policy, tower)
        self.assertEqual((key, policy.last_reason), ("1ay\x1b", trip.RECHARGE_REASON))
        following, paid = self.recharge_reply(tower)
        game = self.post(policy, tower, key, following, recharge_all_screens(paid))
        self.assertEqual(game.accepted, ["1", "a", "y", " ", "\x1b"])
        self.assertEqual(self.wand(following)["charges"], 12)
        key, destinations = self.destination(policy, following)
        self.assertEqual(policy.last_reason.removesuffix("-step-off"), trip.RETURN_REASON)
        self.assertEqual(destinations, [OUTPOST_TOWN_ID])
        self.assertNotEqual(self.board(following).town_id, OUTPOST_TOWN_ID)
        self.assertEqual(policy._effective_town_id(self.board(following)), MORIVANT_TOWN_ID)
