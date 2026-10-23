"""ROOT-FIX S2-c: the cross-town shopping hold lives only in the verdict.

``_fixed_quest_key`` no longer asks the hold itself; the fixed-quest rung's
terminal does (``cross-town-shopping-in-progress``).  So every board where
the body would act past its former hold must name a quest-work terminal:
a taken kill quest's descent, and travel toward the travel quest when no
target quest is chosen.  The opening Q34 owner calls the body without an
entry and asks the same verdict.

Boards: the CONSTRUCTED goldburn seam (row 3512, Telmora, the admitted
identification trip; see test_goldburn_shopping_constructed) and the
measured Q34 opening of test_policy_quest.  Quest choices are DECLARED
CONSTRUCTED patches of the quest selectors.
"""

import tests  # noqa: F401

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.model import QuestState
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    QUEST_STATUS_TAKEN, STORE_RESTOCK_WAIT_TURNS,
)
from hengbot.model import STORE_GENERAL
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_types import CrossTownShoppingExpedition
from hengbot.quest_knowledge import QUEST_TYPE_KILL_LEVEL
from hengbot.town_terminal import TerminalRef, fixed_quest_intended_terminal
from test_goldburn_shopping_constructed import board, shopping_policy
import test_policy_quest


def _entry(policy, snap):
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    policy._observe_cross_town_shopping_arrival(snap)
    calls = []
    key = policy._town_producer_entry(
        "_fixed_quest_key#2", lambda: calls.append("ran") or "7")
    return key, calls, policy._decision_terminal_admissions


class KillQuestDescentTest(unittest.TestCase):
    def run_entry(self, policy):
        policy._quest_knowledge = {2: SimpleNamespace(type=QUEST_TYPE_KILL_LEVEL)}
        with patch.object(HengbotPolicy, "_fixed_quest_target", return_value=2), \
                patch.object(HengbotPolicy, "_known_fixed_quests",
                             return_value={2: QuestState(2, status=QUEST_STATUS_TAKEN)}):
            self.assertEqual(fixed_quest_intended_terminal(policy, board()),
                             TerminalRef("quest-descent", (2,)))
            return _entry(policy, board())

    def test_taken_kill_quest_descent_is_held_by_the_trip(self):
        key, calls, rows = self.run_entry(shopping_policy())
        self.assertEqual((key, calls), (None, []))
        self.assertEqual([(row["terminal"], row["codes"]) for row in rows],
                         [(["quest-descent", [2]], ["cross-town-shopping-in-progress"])])

    def test_control_without_a_trip_the_descent_runs(self):
        key, calls, rows = self.run_entry(HengbotPolicy())
        self.assertEqual((key, calls, rows), ("7", ["ran"], []))


class TravelWithoutTargetTest(unittest.TestCase):
    def test_travel_quest_in_another_town_is_held_by_the_trip(self):
        head = QuestState(22, status=QUEST_STATUS_TAKEN)
        policy = shopping_policy()
        with patch.object(HengbotPolicy, "_fixed_quest_target", return_value=None), \
                patch.object(HengbotPolicy, "_fixed_quest_head", return_value=head), \
                patch.object(HengbotPolicy, "approved_quest_strategy", return_value=object()):
            self.assertEqual(fixed_quest_intended_terminal(policy, board()),
                             TerminalRef("quest-travel", (3,)))
            key, calls, rows = _entry(policy, board())
        self.assertEqual((key, calls), (None, []))
        self.assertEqual([row["codes"] for row in rows],
                         [["cross-town-shopping-in-progress"]])

    def test_control_unapproved_head_has_no_terminal(self):
        # Outpost board (row 3691): no prepare-return from town 0.
        head = QuestState(22, status=QUEST_STATUS_TAKEN)
        with patch.object(HengbotPolicy, "_fixed_quest_target", return_value=None), \
                patch.object(HengbotPolicy, "_fixed_quest_head", return_value=head), \
                patch.object(HengbotPolicy, "approved_quest_strategy", return_value=None):
            self.assertIsNone(fixed_quest_intended_terminal(shopping_policy(), board(1)))


class OpeningQ34AsksTheVerdictTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_policy_quest.ApprovedQuestStrategyExecutionTest.setUpClass()

    def key(self, *, trip):
        helper = test_policy_quest.ApprovedQuestStrategyExecutionTest()
        policy = helper._policy()
        opening = helper._measured_q34_opening()
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        policy._home_knowledge_scan_requested = True
        policy._town_restock_waiting_for = (STORE_GENERAL,)
        policy._town_restock_wait_until = opening.turn + STORE_RESTOCK_WAIT_TURNS
        if trip:
            policy._cross_town_shopping = CrossTownShoppingExpedition(
                trigger_town_id=0, blocking_categories=("recall",),
                shortage_costs={}, reserve=0, required_gold=0,
                candidate_order=(1,), target_town_id=1)
        # The quest body is a spy: whether the opening owner calls it.
        with patch.object(policy, "_town_claims_active", return_value=False),                 patch.object(policy, "_town_terminal_transitions"),                 patch.object(policy, "_fixed_quest_key", return_value="7") as body:
            return policy._opening_q34_town_key(opening, []), body.call_count

    def test_trip_holds_the_quest_body(self):
        self.assertEqual(self.key(trip=True), (WAIT_KEY, 0))

    def test_control_without_a_trip_the_quest_body_runs(self):
        self.assertEqual(self.key(trip=False), ("7", 1))


if __name__ == "__main__":
    unittest.main()
