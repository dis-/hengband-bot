"""The store approach's answer in three kinds (approach_answer, review 2026-11-18 S2 (a)-3).

``ShopMixin._shopping_approach_answer`` tells a key, a yield to the town's holder and no route
apart; ``_shopping_approach_key`` still returns the same key (None or "" for both empty kinds).
A stop named after an empty answer records who held the town, in the decision log only.

The recorded case is n1-a life-530 2026-11-18 (c7e2f1a4c1, the fixture of
tests/test_n1a_530_equip_restore_1118_recorded.py): with that fix taken back (the town hold no
longer opens the Home route for the equipment transaction), row 12 stops again under
``equipment-transaction:restore-blocked-terminal`` (the journalled key and reason) and the record says the approach yielded to
the Home errand's hold, which the transaction had read as no route.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot import approach_answer
from hengbot.approach_answer import ApproachKind
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


class RestoreBlockedYieldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == STOP_ROW:
                cls.board = board
                break
            before = copy.copy(policy._store_visit)
            policy.choose_key(board)
            post(policy, board, recorded["key"], before)
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_old_stop_records_the_yield_to_the_home_errand(self):
        import hengbot.policy as policy_module

        opened = policy_module.town_home_route_opened_for

        def before_c7e2f1a4c1(policy, family):
            return family != "equipment-txn" and opened(policy, family)

        with mock.patch.object(policy_module, "town_home_route_opened_for",
                               before_c7e2f1a4c1):
            key = self.policy.choose_key(self.board)
        # The recorded stop, decided again (key and reason as journalled).
        recorded = self.journal[STOP_ROW]
        self.assertEqual((key, self.policy.last_reason), (recorded["key"], recorded["reason"]))
        self.assertEqual(recorded["reason"],
                         "town:entrance-step-off:equipment-transaction:restore-blocked-terminal")
        answer = approach_answer.latest(self.policy)
        self.assertEqual(answer.kind, ApproachKind.YIELDED)
        self.assertIsNone(answer.key)
        [note] = [row for row in approach_answer.report(self.policy)
                  if row["stop"] == "equipment-transaction:restore-blocked-terminal"]
        self.assertEqual(note["yielded_to"], "town-hold:home-errand")
        self.assertEqual(note["travel_reason"], "equipment-transaction:travel-home")


if __name__ == "__main__":
    unittest.main()
