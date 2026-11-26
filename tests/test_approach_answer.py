"""The store approach's answer in three kinds (approach_answer, review 2026-11-18 S2 (a)-3).

``ShopMixin._shopping_approach_answer`` tells a key, a yield to the town's holder and no route
apart; ``_shopping_approach_key`` still returns the same key (None or "" for both empty kinds).
A stop named after an empty answer records who held the town, in the decision log only.

Owner 2026-11-18 (review Q2, 「先の用事を待って続ける」): a stop site that read a yield waits for
the holder (answers nothing this board) and, after ``WAIT_LIMIT`` yielded boards for one holder,
stops under ``town:blocked:approach-yielded:<stop>:waiting-for:<holder>``; no route stops as
before.

The recorded case is n1-a life-530 2026-11-18 (c7e2f1a4c1, the fixture of
tests/test_n1a_530_equip_restore_1118_recorded.py): with that fix taken back (the town hold no
longer opens the Home route for the equipment transaction), row 12 stopped under
``equipment-transaction:restore-blocked-terminal`` (the journalled reason).  It now waits for
the Home errand: the step off the entrance it journalled, under the transaction's deferred
wait instead of the terminal, and no restore terminal.  At the bound it stops named after the
Home errand.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot import approach_answer
from hengbot.approach_answer import ApproachKind, WAIT, WAIT_LIMIT
from hengbot.cli import _policy_final_stop_banner, _policy_final_stop_required
from support.town_arrival_fixture import load
from test_n1a_530_equip_restore_1118_recorded import FIXTURE, STOP_ROW, post


class ApproachAnswerKindsTest(unittest.TestCase):
    def test_three_kinds_keep_the_returned_value(self):
        self.assertEqual(approach_answer.answered("4").kind, ApproachKind.KEY)
        for empty in (None, ""):
            answer = approach_answer.answered(empty)
            self.assertEqual(answer.kind, ApproachKind.NO_ROUTE)
            self.assertIs(answer.key, empty)
            answer = approach_answer.yielded(empty, "town-hold:home-errand", 7)
            self.assertEqual(answer.kind, ApproachKind.YIELDED)
            self.assertIs(answer.key, empty)
            self.assertEqual((answer.yielded_to, answer.holder_claim_id),
                             ("town-hold:home-errand", 7))
        # A path that stood aside but still made a key answers that key.
        answer = approach_answer.yielded("5", "equipment-txn:owns-relocation")
        self.assertEqual((answer.kind, answer.key, answer.yielded_to),
                         (ApproachKind.KEY, "5", None))

    def test_a_stop_records_only_a_yield_of_this_decision(self):
        policy = SimpleNamespace(_decision_sequence=3, _shopping_approach_store_type=8)
        approach_answer.remember(policy, approach_answer.answered(None), "shop:travel")
        approach_answer.note_stop(policy, "shop-operation-unavailable")
        self.assertIsNone(approach_answer.report(policy))

        approach_answer.remember(
            policy, approach_answer.yielded(None, "town-hold:home-errand", 11), "shop:travel")
        approach_answer.note_stop(policy, "shop-operation-unavailable")
        self.assertEqual(approach_answer.report(policy), [{
            "stop": "shop-operation-unavailable", "yielded_to": "town-hold:home-errand",
            "holder_claim_id": 11, "travel_reason": "shop:travel", "store_type": 8}])

        # The next decision reads neither the old answer nor the old record.
        policy._decision_sequence = 4
        self.assertIsNone(approach_answer.latest(policy))
        self.assertIsNone(approach_answer.report(policy))
        approach_answer.note_stop(policy, "shop-operation-unavailable")
        self.assertIsNone(approach_answer.report(policy))


class AfterEmptyTest(unittest.TestCase):
    SITE = "shop-operation-unavailable"

    def policy(self):
        return SimpleNamespace(_decision_sequence=1, _shopping_approach_store_type=8)

    def decide(self, policy, answer):
        policy._decision_sequence += 1
        approach_answer.remember(policy, answer, "shop:travel")
        return approach_answer.after_empty(policy, self.SITE, approach_answer.latest(policy))

    def test_no_route_and_no_answer_keep_the_stop(self):
        policy = self.policy()
        self.assertIsNone(self.decide(policy, approach_answer.answered(None)))
        self.assertIsNone(approach_answer.after_empty(policy, self.SITE, None))
        self.assertIsNone(approach_answer.report(policy))

    def test_a_yield_waits_then_stops_named_after_the_holder(self):
        policy = self.policy()
        held = approach_answer.yielded(None, "town-hold:home-errand", 11)
        for board in range(1, WAIT_LIMIT):
            self.assertEqual(self.decide(policy, held), WAIT, board)
        [row] = approach_answer.report(policy)
        self.assertEqual((row["waited"], row["verdict"]), (WAIT_LIMIT - 1, WAIT))
        stop = ("town:blocked:approach-yielded:shop-operation-unavailable"
                ":waiting-for:home-errand")
        self.assertEqual(self.decide(policy, held), stop)
        self.assertEqual(approach_answer.report(policy)[0]["waited"], WAIT_LIMIT)
        self.assertTrue(stop.startswith(approach_answer.WAIT_STOP_PREFIX))

    def test_one_decision_counts_once(self):
        policy = self.policy()
        held = approach_answer.yielded(None, "town-hold:home-errand", 11)
        self.decide(policy, held)
        approach_answer.after_empty(policy, self.SITE, held)
        self.assertEqual(policy._approach_yield_waits[(self.SITE, "home-errand", 11)][0], 1)

    def test_another_holder_or_claim_or_visit_starts_again(self):
        policy = self.policy()
        for _ in range(5):
            self.decide(policy, approach_answer.yielded(None, "town-hold:home-errand", 11))
        self.decide(policy, approach_answer.yielded(None, "town-hold:home-errand", 12))
        self.assertEqual(policy._approach_yield_waits, {(self.SITE, "home-errand", 12): (1, 7)})
        self.decide(policy, approach_answer.yielded(None, "terminal:t3"))
        self.assertEqual(list(policy._approach_yield_waits), [(self.SITE, "terminal:t3", None)])
        approach_answer.forget_visit(policy)
        self.assertEqual(policy._approach_yield_waits, {})

    def test_a_key_between_yields_keeps_the_count(self):
        # The c7e2f1a4c1 lap: a step off the entrance and a walk back (a key) each lap.
        policy = self.policy()
        held = approach_answer.yielded(None, "town-hold:home-errand", 11)
        self.decide(policy, held)
        policy._decision_sequence += 1
        approach_answer.remember(policy, approach_answer.answered("1"), "shop:travel")
        self.decide(policy, held)
        self.assertEqual(policy._approach_yield_waits[(self.SITE, "home-errand", 11)][0], 2)


class Q34ReadinessSiteTest(unittest.TestCase):
    """The Q34 readiness rejection's livelock:exhausted site (quest_opening_readiness)."""

    def policy(self, answer):
        policy = SimpleNamespace(_decision_sequence=1, _shopping_approach_store_type=8,
                                 last_reason=None)

        def approach(_snapshot, _step, reason):
            approach_answer.remember(policy, answer, reason)
            return answer.key

        policy._physical_adjacent_hostiles = lambda _snapshot: []
        policy._shopping_approach_step = lambda _snapshot, router_plan_stop: "step"
        policy._shopping_approach_key = approach
        policy._start_fundraising = lambda _snapshot, _cause=None: False
        return policy

    def decide(self, policy):
        from hengbot.quest_opening_readiness import q34_readiness_rejection_key
        policy._decision_sequence += 1
        return q34_readiness_rejection_key(
            policy, SimpleNamespace(player=SimpleNamespace(food_state="normal")), [],
            {"verdict": False, "reason": "light"})

    def test_no_route_releases_the_opening(self):
        # n1-a life-541 (supervisor 2026-11-26): an opening requirement no route of the
        # opening can meet hands the town on (quest_opening_readiness.RELEASED) instead of the
        # former livelock:exhausted stop; the rungs below answer this board.
        policy = self.policy(approach_answer.answered(None))
        self.assertEqual((self.decide(policy), policy.last_reason),
                         (None, "opening-q34:released"))
        self.assertEqual(policy._q34_opening_released, "unaffordable:light")

    def test_a_yield_waits_then_stops_named_after_the_holder(self):
        policy = self.policy(approach_answer.yielded(None, "town-hold:home-errand", 4))
        for _ in range(WAIT_LIMIT - 1):
            self.assertIsNone(self.decide(policy))
        self.assertEqual(self.decide(policy), "5")
        self.assertEqual(policy.last_reason,
                         "town:blocked:approach-yielded:livelock:exhausted:waiting-for:home-errand")


HOME_ERRAND_CLAIM = 9093   # the Home errand's hold on row 12 (the town hold's claim)


class RestoreBlockedYieldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()

    def fresh_policy(self):
        """The arrival policy replayed to the stop row, for one test alone."""
        policy, self.journal, steps = load(FIXTURE, Path(self.scratch.name) / self.id())
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == STOP_ROW:
                self.board = board
                return policy
            before = copy.copy(policy._store_visit)
            policy.choose_key(board)
            post(policy, board, recorded["key"], before)
        raise AssertionError("no stop row")

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def decide_before_c7e2f1a4c1(self, policy):
        import hengbot.policy as policy_module

        opened = policy_module.town_home_route_opened_for

        def before_c7e2f1a4c1(policy, family):
            return family != "equipment-txn" and opened(policy, family)

        with mock.patch.object(policy_module, "town_home_route_opened_for",
                               before_c7e2f1a4c1):
            return policy.choose_key(self.board)

    def test_the_old_stop_now_waits_for_the_home_errand(self):
        policy = self.fresh_policy()
        key = self.decide_before_c7e2f1a4c1(policy)
        # The journalled stop was this step off the entrance under the restore terminal; the
        # transaction now waits for the errand (its deferred wait), and no terminal is set.
        recorded = self.journal[STOP_ROW]
        self.assertEqual(recorded["reason"],
                         "town:entrance-step-off:equipment-transaction:restore-blocked-terminal")
        self.assertEqual((key, policy.last_reason),
                         (recorded["key"],
                          "town:entrance-step-off:equipment-transaction:deferred-wait"))
        self.assertIsNone(policy._equipment_transaction_restore_terminal)
        self.assertFalse(_policy_final_stop_required(policy))
        answer = approach_answer.latest(policy)
        self.assertEqual(answer.kind, ApproachKind.YIELDED)
        self.assertIsNone(answer.key)
        [note] = [row for row in approach_answer.report(policy)
                  if row["stop"] == "equipment-transaction:restore-blocked-terminal"]
        self.assertEqual(note["yielded_to"], "town-hold:home-errand")
        self.assertEqual(note["travel_reason"], "equipment-transaction:travel-home")
        self.assertEqual(note["holder_claim_id"], HOME_ERRAND_CLAIM)
        self.assertEqual((note["waited"], note["verdict"]), (1, WAIT))

    def test_the_wait_stops_named_after_the_home_errand_at_the_bound(self):
        policy = self.fresh_policy()
        site = "equipment-transaction:restore-blocked-terminal"
        # The wait's earlier boards: the count for the errand's claim (9093, the hold's claim
        # on this board) stands one short of the bound.
        policy._approach_yield_waits = {(site, "home-errand", HOME_ERRAND_CLAIM): (WAIT_LIMIT - 1, None)}
        key = self.decide_before_c7e2f1a4c1(policy)
        stop = ("town:blocked:approach-yielded:equipment-transaction:restore-blocked-terminal"
                ":waiting-for:home-errand")
        self.assertEqual(policy.last_reason, stop)
        self.assertEqual(policy._equipment_transaction_restore_terminal, stop)
        self.assertTrue(_policy_final_stop_required(policy))
        self.assertIn("yielded to the town's holder", _policy_final_stop_banner(stop))
        self.assertTrue(key)
        # The stop holds on the next board, as the restore terminal did.
        self.decide_before_c7e2f1a4c1(policy)
        self.assertEqual(policy.last_reason, stop)


if __name__ == "__main__":
    unittest.main()
