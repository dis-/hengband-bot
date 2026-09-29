"""Pins for producer outcomes that can be superseded before claim exit."""

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.claim_register import observe
from hengbot.home_errand import HomeErrandRequest
from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit
from test_policy import Snapshot, StoreState, STORE_HOME, grid, player


def home_entrance():
    here = Position(10, 10)
    return Snapshot(player(10, 10), {here: replace(grid(10, 10), store_number=STORE_HOME)},
                    [], floor_key=(0, 0, 0), town_flag=True)


def bind(policy, owner, key):
    claim = policy._claim_register.declare(
        owner, observe(("producer-result",), 8, "store-operation"))
    policy._record_execution_declaration(claim, key, policy.last_reason)
    return policy._claim_register.current.execution


class AtomicHomeWithdrawGapTest(unittest.TestCase):
    def test_probe_none_binds_only_if_final_owner_and_key_match(self):
        policy = HengbotPolicy()
        policy._shopping_approach_store_type = STORE_HOME
        key = policy._atomic_home_withdraw_key(home_entrance(), Position(10, 10))
        self.assertIsNone(key)
        declaration = bind(policy, "home-visit", key)
        self.assertEqual((declaration.state, declaration.cause),
                         ("releasing", "no-withdrawal-request"))


class AtomicHomeDepositGapTest(unittest.TestCase):
    def test_no_candidate_names_deposit_probe(self):
        policy = HengbotPolicy()
        policy._shopping_approach_store_type = STORE_HOME
        with patch.object(policy, "_find_home_deposit", return_value=None):
            key = policy._atomic_home_deposit_key(home_entrance(), Position(10, 10))
        declaration = bind(policy, "home-visit", key)
        self.assertEqual((key, declaration.state, declaration.cause),
                         (None, "releasing", "no-deposit-candidate"))


class OpenHomeDepositGapTest(unittest.TestCase):
    def test_open_page_without_candidate_releases(self):
        policy = HengbotPolicy()
        policy._store_visit = StoreVisit("home", "deposit", STORE_HOME)
        board = replace(home_entrance(), store=StoreState(STORE_HOME, []))
        with patch.object(policy, "_find_home_deposit", return_value=None):
            key = policy._open_home_deposit_key(board)
        declaration = bind(policy, "home-visit", key)
        self.assertEqual((key, declaration.cause),
                         (None, "open-page-deposit-not-authorized"))


class FiledHomeErrandGapTest(unittest.TestCase):
    def test_filed_request_names_next_executor_on_none(self):
        policy = HengbotPolicy()
        board = home_entrance()
        request = HomeErrandRequest(("scroll", 1, 2), 1, "home-catalog",
                                    "identification")
        with patch.object(policy, "_post_owner_expectation"):
            filed = policy._file_home_errand(board, request,
                                             knowledge_current=False)
        self.assertTrue(filed)
        declaration = bind(policy, "home-errand", None)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "home.knowledge.request"))


class DeferredHomeScanGapTest(unittest.TestCase):
    def test_deferred_scan_names_holder_on_none(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        holder = SimpleNamespace(owner=SimpleNamespace(value="home-visit"),
                                 claim_id=42)
        with (patch.object(policy, "_claim_errand_hold", return_value=holder),
              patch.object(policy, "_recorded_execution_token", return_value=None)):
            self.assertTrue(policy._defer_town_errand("home-scan", "outside-scan"))
        declaration = bind(policy, "home-scan", None)
        self.assertEqual((declaration.state, declaration.cause),
                         ("releasing", "deferred:outside-scan:holder:42"))


class AtomicShopGapTest(unittest.TestCase):
    def test_uncomposable_probe_does_not_bind_to_later_key(self):
        policy = HengbotPolicy()
        board = home_entrance()
        self.assertIsNone(policy._atomic_shop_transaction_key(board))
        declaration = bind(policy, "store-router", None)
        self.assertEqual((declaration.state, declaration.cause),
                         ("releasing", "page-not-composable"))
        policy = HengbotPolicy()
        self.assertIsNone(policy._atomic_shop_transaction_key(board))
        policy._offer_execution("6", producer="store-router", work_id="later",
                                next_step="route.resume")
        declaration = bind(policy, "store-router", "6")
        self.assertEqual((declaration.work_id, declaration.next_step),
                         ("later", "route.resume"))


class ShoppingApproachGapTest(unittest.TestCase):
    def test_unresolved_direction_releases_route(self):
        policy = HengbotPolicy()
        board = home_entrance()
        policy._shopping_approach_goal = Position(10, 11)
        policy._shopping_approach_store_type = STORE_HOME
        with patch.object(policy, "_step_toward", return_value=None):
            key = policy._stage_shopping_approach_key(
                board, None, claim_family="store-router")
        declaration = bind(policy, "store-router", key)
        self.assertEqual((declaration.state, declaration.cause),
                         ("releasing", "approach-step-unresolved"))


class TownTravelGapTest(unittest.TestCase):
    def test_undisclosed_goal_releases_native_route(self):
        policy = HengbotPolicy()
        board = home_entrance()
        key = policy._town_travel_key(board, Position(2, 2), "`n!." ,
                                       "town:travel-store")
        declaration = bind(policy, "store-router", key)
        self.assertEqual((declaration.state, declaration.cause),
                         ("releasing", "goal-undisclosed"))


if __name__ == "__main__":
    unittest.main()
