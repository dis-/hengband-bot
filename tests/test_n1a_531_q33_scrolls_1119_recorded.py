"""n1-a life-531 2026-11-19 16:05:49, town:blocked:survival:inventory_weight_ready.

The Lv50 warrior (no absorbed Teleportation) came home with 32 Scrolls of Teleportation and 7 of
Light it held for Quest 33, untaken: Q33 asks ``teleport_scrolls_without_absorbed`` 40
(owner 2026-11-19 「ない場合はテレポートの巻物を40巻用意すること」) and 10 Light scrolls, but also ten
resistances, and the character lacks blindness.  The visit bought 8 more Teleportation and 3 Light
scrolls (rows 69-77), the weight relief deposited 25 in Telmora (row 143: there Q33 is not offered,
the fallback strategy kept the profile's 10), and back in the Outpost the head's 40 withdrew them
(row 175, ``5pw25``): the overweight pack stopped the departure (row 177).

Owner 2026-11-19 (home-full root proposal, question 5) 「条件がそろってから買い自宅に置く」: the
supplies of a quest not yet taken are bought only once its other conditions are met, held in the
Home until it is taken, and never carried before (quest_supply_gate).

Recorded: the stop's town-arrival checkpoint and all 178 journal rows
(tests/extract_n1a_531_q33_scrolls_1119_fixture.py).  Every row is decided through the public
choose_key and acknowledged as recorded; rows 0-38 replay as recorded (row 39 differs on the
unchanged code too: the bot has moved on since the capture).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from dataclasses import replace
from tempfile import TemporaryDirectory

from hengbot import quest_supply_gate
from hengbot.model import SV_SCROLL_TELEPORT, TVAL_SCROLL
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-q33-scrolls-1119"
MATCHING_ROWS = 39
ARRIVAL, ALCHEMIST_TRIP, WITHDRAW_ROW, STEP_OFF_ROW, STOP_ROW = 0, 69, 175, 176, 177
QUEST_CARRIES = {"Quest Teleport scrolls", "Quest Light scrolls"}


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def teleport_stack(board):
    return next(item for item in board.inventory
                if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_TELEPORT)


class Quest33ScrollsWaitForConditionsRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed, cls.seen = [], {}
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row in (ARRIVAL, ALCHEMIST_TRIP, WITHDRAW_ROW, STEP_OFF_ROW, STOP_ROW):
                cls.seen[row] = dict(
                    board=board,
                    strategy=policy._carry_procurement_strategy(board),
                    fallback=policy._quest_strategy_for_errand_or_floor(board),
                    requirements={entry["item"] for entry in policy.procurement_requirements(board)},
                    teleport_kept=policy._retention_reservation(board, teleport_stack(board)),
                )
            key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            if row in cls.seen:
                cls.seen[row].update(decided=(key, policy.last_reason),
                                     blocked=policy._town_blocked_reason)
            post(policy, recorded["key"])
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_rows_before_the_change_replay_as_recorded(self):
        for row, (decided, recorded) in enumerate(self.replayed[:MATCHING_ROWS]):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[WITHDRAW_ROW]["key"], "5pw25\r\x1b")
        self.assertEqual(self.journal[STOP_ROW]["reason"], "town:blocked:survival:inventory_weight_ready")

    def test_q33_short_of_a_resistance_is_not_admitted(self):
        board = self.seen[ARRIVAL]["board"]
        profile = self.policy.approved_quest_strategy(33)
        self.assertEqual(self.policy._fixed_quest_head(board).id, 33)
        self.assertNotIn("resist_blind", board.player.abilities)
        self.assertFalse(quest_supply_gate.other_conditions_met(self.policy, board, profile))
        # Its resolved force asks the 40 scrolls (no absorbed Teleportation) ...
        force = self.policy._strategy_force_for_snapshot(board, profile)
        self.assertEqual(force["required_scrolls"]["teleport"], 40)

    def test_no_quest_carry_is_procured_before_the_conditions(self):
        # ... which nobody asks for: not bought, not kept, not a departure item.
        for row in (ARRIVAL, ALCHEMIST_TRIP, WITHDRAW_ROW, STEP_OFF_ROW, STOP_ROW):
            seen = self.seen[row]
            self.assertIsNone(seen["strategy"] and seen["strategy"].quest_id, row)
            self.assertIsNone(seen["fallback"] and seen["fallback"].quest_id, row)
            self.assertFalse(seen["requirements"] & QUEST_CARRIES, row)
        # Recorded row 69 went to the Alchemist for the 8 Teleportation scrolls.
        self.assertNotEqual(self.seen[ALCHEMIST_TRIP]["decided"], ("\x1b`n%.", "shop:travel"))

    def test_carried_scrolls_beyond_the_ordinary_carry_go_home(self):
        # The 32 carried at the arrival and the 40 at the stop keep only the ordinary carry.
        for row in (ARRIVAL, STOP_ROW):
            seen = self.seen[row]
            self.assertLess(seen["teleport_kept"], 32, row)
        self.assertLessEqual(self.seen[STOP_ROW]["teleport_kept"], 15)

    def test_the_home_scrolls_are_not_withdrawn_and_the_visit_departs(self):
        withdraw = self.seen[WITHDRAW_ROW]
        self.assertNotEqual(withdraw["decided"][1], "home:atomic-withdraw")
        # Row 176 (the 40 scrolls on the pack at the Home entrance; recorded: the step off to
        # the stop) enters the Home to deposit the overload, and neither board is blocked.
        step_off = self.seen[STEP_OFF_ROW]
        self.assertEqual(step_off["decided"], ("5", "home:weight-overload-deposit"))
        self.assertIsNone(step_off["blocked"])
        self.assertIsNone(self.seen[STOP_ROW]["blocked"])
        self.assertNotEqual(self.seen[STOP_ROW]["decided"][1],
                            "town:blocked:survival:inventory_weight_ready")


class Quest33ConditionsMetKeepsItsScrollsTest(unittest.TestCase):
    """CONSTRUCTED from the arrival board: the same character with the missing resistance
    (blindness) meets every other Q33 condition, so its 40 scrolls are bought and carried; a
    taken Q33 keeps them as before; while Q33 waits, its Home stock is kept, not sold."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.policy, cls.board = policy, steps[ARRIVAL][1]()
        player = cls.board.player
        cls.ready = replace(cls.board, player=replace(
            player, abilities=player.abilities | {"resist_blind"}))

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        setattr(self.policy, quest_supply_gate.ADMITTED, None)

    def test_conditions_met_buys_and_carries_the_forty(self):
        policy, board = self.policy, self.ready
        profile = policy.approved_quest_strategy(33)
        self.assertTrue(quest_supply_gate.other_conditions_met(policy, board, profile))
        strategy = policy._carry_procurement_strategy(board)
        self.assertEqual(strategy.quest_id, 33)
        self.assertEqual(strategy.required_force["required_scrolls"]["teleport"], 40)
        requirements = {entry["item"]: entry for entry in policy.procurement_requirements(board)}
        self.assertEqual((requirements["Quest Teleport scrolls"]["current"],
                          requirements["Quest Teleport scrolls"]["target"]), (32, 40))
        self.assertIn("Quest Light scrolls", requirements)
        self.assertEqual(policy._retention_reservation(board, teleport_stack(board)), 32)

    def test_met_once_this_visit_stays_admitted(self):
        policy = self.policy
        self.assertIsNone(policy._carry_procurement_strategy(self.board))
        policy._carry_procurement_strategy(self.ready)
        # The ring taken off for a swap does not send the scrolls Home and back.
        self.assertEqual(policy._carry_procurement_strategy(self.board).quest_id, 33)
        setattr(policy, quest_supply_gate.ADMITTED, (object(), frozenset({33})))
        self.assertIsNone(policy._carry_procurement_strategy(self.board))

    def test_a_taken_q33_keeps_its_supplies(self):
        policy, board = self.policy, self.board
        # Q33 is not exported untaken (the static knowledge adds it); taken, the game lists it.
        self.assertNotIn(33, board.quests)
        untaken = policy._known_fixed_quests(board)[33]
        taken = replace(board, quests={**board.quests, 33: replace(untaken, status=QUEST_STATUS_TAKEN)})
        self.assertEqual(policy._carry_procurement_strategy(taken).quest_id, 33)
        self.assertEqual(policy._retention_reservation(taken, teleport_stack(taken)), 32)

    def test_the_waiting_quest_home_stock_is_kept(self):
        policy, board = self.policy, self.board
        stock = replace(teleport_stack(board), slot="home-surplus")
        self.assertTrue(quest_supply_gate.home_keeps(policy, board, stock))
        self.assertFalse(quest_supply_gate.home_keeps(policy, board, teleport_stack(board)))
        policy._carry_procurement_strategy(self.ready)   # admitted: the carry rules it
        self.assertFalse(quest_supply_gate.home_keeps(policy, board, stock))


if __name__ == "__main__":
    unittest.main()
