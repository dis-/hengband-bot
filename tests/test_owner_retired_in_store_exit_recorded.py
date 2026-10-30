"""2026-10-30 D28: a forgiven owner retirement inside a store stopped the bot.

n1-c life-045 23:45:52 (and n1-c life-038, n1-b lives 249, 251, 256): on a
store page the town arbiter retired shop-buy (recurrence 2/2) on the very
decision that composed an in-store purchase.  The soak's log-only mode
forgives that retirement by leaving the store (cli._handle_owner_retirement),
but it replaced only the key: the decision still carried
``shop:in-store-buy``, observed_input refuses an in-store buy that is not
``p`` with its prompt gates, the in-store breaker tripped and the bot
stopped (stuck-prompt / exit:no-marker).  The breaker file then kept
in-store operations off for the rest of the life.

The case starts on the recorded General store page (turn 85917) with the
recorded shelves (tests/extract_owner_retired_in_store_exit.py).  The
decision goes through the public chooser, the driver's retirement entrance
and the production executor.
"""
import tests  # noqa: F401

import copy
import gzip
import io
import json
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from hengbot import cli
from hengbot.model import parse_snapshot
from hengbot.policy_constants import IN_STORE_OPERATION_REASONS, LEAVE_STORE_KEY
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "owner-retired-in-store-exit-20261030.json.gz"


class OwnerRetiredInStoreExitRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def boundary(self):
        case = self.case
        policy, raw = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=case["monraces"], snapshot=case["board"], knowledge=case["knowledge"],
            state={"modes_and_latches": {}}))
        # The viewing soak runs with --in-store-shop-ops; the executor's
        # ready screen shows this page (cli.observe_store_screen).
        policy._in_store_ops_enabled = True
        policy.observe_store_screen(True)
        return policy, raw

    def test_recorded_population_is_one_shape(self):
        population = self.case["population"]
        self.assertEqual(len(population), 5)
        for name, row in population.items():
            with self.subTest(capture=name):
                self.assertEqual((row["breaker"]["owner"], row["breaker"]["key"]),
                                 ("shop:in-store-buy", LEAVE_STORE_KEY))
                decision = row["decision"]
                self.assertEqual((decision["reason"], decision["key"]),
                                 ("shop:in-store-buy", LEAVE_STORE_KEY))
                self.assertTrue(decision["operation"]["key"].startswith("p"))
                self.assertEqual(decision["retired"], ["shop-buy"])
                self.assertEqual(decision["producer"], "cli.py:_handle_owner_retirement")
                self.assertEqual((decision["trigger"], decision["recurrence"]), ("recurrence", [2, 2]))

    def test_forgiven_retirement_leaves_the_store_with_the_in_store_exit(self):
        policy, raw = self.boundary()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        key = policy.choose_key(board)
        recorded = self.case["recorded"]["decision"]
        self.assertEqual((key, policy.last_reason),
                         (recorded["operation"]["key"], recorded["reason"]))
        # DECLARED RECONSTRUCTED: the arbiter's recurrence retirement of
        # shop-buy recorded on this decision (town_idle_d0: recurrence 2/2,
        # entry point policy.py:3086); the capture keeps the telemetry, not
        # the arbiter's progress vectors.
        policy._town_turn_arbiter.retire(
            "shop-buy", ("recorded-recurrence",), entry_point="policy.py:3086",
            recurrence_count=2, recurrence_limit=2, trigger_category="recurrence")
        with redirect_stderr(io.StringIO()):
            key = cli._handle_owner_retirement(
                SimpleNamespace(owner_retired_log_only=True, decision_log=None), board, key, policy)
        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertNotIn(policy.last_reason, IN_STORE_OPERATION_REASONS)
        # The executor posts the exit on the recorded page; the next board is
        # outside the store (DECLARED CONSTRUCTED reply).
        following = copy.deepcopy(raw)
        following["store"] = None
        following["turn"] += 1
        self.post(policy, raw, key, following)
        self.assertIsNone(policy._in_store_breaker)
        # The outside board continues the town errands instead of a stop.
        key = policy.choose_key(parse_snapshot(following, policy._monrace_knowledge))
        self.assertNotEqual(key, "")
        self.assertFalse(policy.last_reason.startswith(("town:blocked:", "store:in-store-breaker")),
                         policy.last_reason)


if __name__ == "__main__":
    import unittest
    unittest.main()
