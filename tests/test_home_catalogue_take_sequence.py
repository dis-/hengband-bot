"""DECLARED CONSTRUCTED R1/R2 boards; historical evidence has decisions only."""
import tests  # noqa: F401

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot.cli import _dispatch_response_lines
from hengbot.home_errand import HomeErrandRequest
from hengbot.model import Position, StoreState, STORE_HOME, TVAL_POTION, SV_POTION_CURE_CRITICAL
from policy_fixtures import item
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO, WAIT_KEY
from tests.test_home_withdraw_moved_address import (
    board, wares, carried, ENTRANCE, BESIDE, LATER,
)


class HomeCatalogueTakeSequenceTest(unittest.TestCase):
    def policy(self):
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy.prime(board(turn=100, at=BESIDE))
        policy._shopping_approach_store_type = STORE_HOME
        return policy

    def response(self, policy, shelf=None):
        shelf = wares() if shelf is None else shelf
        response = {
            "type": "knowledge", "knowledge": {
                "category": "home", "menu_key": "9", "items": [
                    {"slot": i, "name": it.name, "tval": it.tval,
                     "sval": it.sval, "count": it.count,
                     "is_equipment": it.is_equipment, "known": True}
                    for i, it in enumerate(shelf)
                ],
            },
        }
        with TemporaryDirectory() as directory:
            _dispatch_response_lines(
                [json.dumps(response)], policy, lambda _key: True,
                knowledge_ledger_path=Path(directory) / "response.jsonl",
            )
            ledger = json.loads((Path(directory) / "response.jsonl").read_text())
        self.assertTrue(ledger["accepted"])
        self.assertTrue(ledger["settled"])
        self.assertTrue(policy._home_knowledge_current)

    def test_r1_first_entry_and_incomplete_exit_then_catalogue_continuation(self):
        policy = self.policy()
        # There is physical work to observe here; retain its first entry.
        self.assertEqual(policy._shopping_approach_key(
            board(turn=101), ENTRANCE, "shop:travel"), WAIT_KEY)
        self.assertEqual(policy.last_reason, "shop:travel:await-entry")
        partial = replace(board(turn=102), store=StoreState(
            STORE_HOME, [], stock_num=20, page_size=12, page_top=0))
        key = policy.choose_key(partial)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "home:scan-incomplete-open-page"))
        policy.confirm_key_posted(key)
        key = policy.choose_key(board(turn=103))
        # Before D4 public continuation walked '4'/shop:approach; the router
        # alone re-entered '5'/shop:travel:await-entry at historical seq4.
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertEqual(policy._claim_register.current.owner.value, "home-scan")
        policy.confirm_key_posted(key)
        self.assertEqual(policy.choose_key(board(turn=104)), "")
        self.assertEqual(policy.last_reason, "home:scan-await-observation")
        self.response(policy)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertNotEqual(policy.choose_key(board(turn=105)), HOME_KNOWLEDGE_MACRO)

    def test_r2_stale_named_take_requests_awaits_then_takes_fresh_address(self):
        policy = self.policy()
        policy._home_pending_item = policy._item_signature(wares()[LATER])
        policy._home_page_size = 12
        key = policy._shopping_approach_key(
            board(turn=101), Position(44, 124), "shop:travel")
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        # Use the public decision seam to attach and post the prerequisite.
        key = policy.choose_key(board(turn=102))
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertEqual(policy._claim_register.current.owner.value, "home-scan")
        policy.confirm_key_posted(key)
        for turn in (103, 104):
            self.assertEqual(policy.choose_key(board(turn=turn)), "")
            self.assertEqual(policy.last_reason, "home:scan-await-observation")
        self.response(policy)
        key = policy.choose_key(board(turn=105))
        self.assertEqual((key, policy.last_reason),
                         ("5 pd1\r\x1b", "home:atomic-withdraw"))
        telemetry = policy._home_atomic_withdraw_telemetry
        self.assertEqual((telemetry["resolved_index"], telemetry["resolved_page"],
                          telemetry["resolved_letter"]), (15, 1, "d"))
        policy.confirm_key_posted(key)
        observed = board([carried(wares()[LATER], 1)], turn=110)
        policy.choose_key(observed)
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._digger_home_withdraw_failures, 0)

    def test_posted_scan_survives_home_entry_without_repost(self):
        policy = self.policy()
        policy._home_pending_item = policy._item_signature(wares()[LATER])
        key = policy.choose_key(board(turn=101))
        self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
        policy.confirm_key_posted(key)
        page = replace(board(turn=102), store=StoreState(
            STORE_HOME, list(wares()[:12]), stock_num=20, page_size=12, page_top=0))
        policy.choose_key(page)
        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertTrue(policy._home_knowledge_scan_requested)
        self.assertNotEqual(policy.last_reason, "home:request-knowledge-scan")
        self.response(policy)

    def test_recovery_interrupts_the_scan_without_charging_or_reposting(self):
        policy = self.policy()
        policy._home_pending_item = policy._item_signature(wares()[LATER])
        policy.confirm_key_posted(policy.choose_key(board(turn=101)))
        hurt = board([item("a", TVAL_POTION, SV_POTION_CURE_CRITICAL)], turn=102)
        hurt = replace(hurt, player=replace(hurt.player, hp=4, poisoned=True))
        key = policy.choose_key(hurt)
        self.assertEqual((key, policy.last_reason), ("R&\r", "town:recover"))
        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertEqual(policy._home_knowledge_scan_wait_decisions, 0)
        self.assertEqual(policy.choose_key(board(turn=103)), "")
        self.assertEqual(policy.last_reason, "home:scan-await-observation")
        self.assertEqual(policy._home_knowledge_scan_wait_decisions, 1)

    def test_declared_inflight_scan_is_not_counterfactual_travel(self):
        policy = self.policy()
        # DECLARED CONSTRUCTED optimizer input: Home contents are its blocker.
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("home-scan-incomplete",), result=None)
        outside = board(turn=101)
        key = policy._home_full_knowledge_key(outside)
        policy.confirm_key_posted(key)
        key = policy._home_full_knowledge_key(outside)
        self.assertEqual(key, "")
        self.assertEqual(policy._town_procurement_decision(outside, key), "")
        self.assertEqual(policy.last_reason, "home:scan-await-observation")

    def test_contrary_shelf_does_not_repost_an_unsettled_request(self):
        policy = self.policy()
        target = policy._item_signature(wares()[LATER])
        policy._home_pending_item = target
        policy.confirm_key_posted(policy.choose_key(board(turn=101)))
        token = policy._home_knowledge_scan_epoch
        # A complete independent observation supersedes the posted request;
        # later contrary shelf facts invalidate its addresses and content.
        policy._adopt_home_catalogue(wares())
        page = replace(board(turn=102), store=StoreState(
            STORE_HOME, [], stock_num=21, page_size=12, page_top=0))
        policy.choose_key(page)
        self.assertFalse(policy._home_knowledge_current)
        self.assertEqual(policy._home_knowledge_scan_epoch, token)
        key = policy._atomic_home_withdraw_key(board(turn=103), ENTRANCE)
        # Finish the observed exit before composing the prerequisite outside.
        policy.choose_key(board(turn=104))
        policy._shopping_approach_store_type = STORE_HOME
        self.assertEqual(policy._shopping_approach_key(board(turn=105), ENTRANCE, "shop:travel"), "")
        self.assertEqual(policy.last_reason, "home:scan-await-observation")
        self.assertNotEqual(key, HOME_KNOWLEDGE_MACRO)
        policy.settle_home_knowledge_request()
        self.assertEqual(policy._shopping_approach_key(board(turn=106), ENTRANCE, "shop:travel"),
                         HOME_KNOWLEDGE_MACRO)

    def test_named_take_lost_request_is_bounded_without_reposting(self):
        policy = self.policy()
        target = policy._item_signature(wares()[LATER])
        policy._home_pending_item = target
        key = policy.choose_key(board(turn=101))
        self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
        policy.confirm_key_posted(key)
        decisions = []
        for turn in range(102, 110):
            key = policy.choose_key(board(turn=turn))
            decisions.append((key, policy.last_reason))
            if policy.last_reason.startswith("town:blocked"):
                break
        self.assertNotIn(HOME_KNOWLEDGE_MACRO, [k for k, _ in decisions])
        self.assertLessEqual(len(decisions), 8)
        self.assertEqual(decisions[-1], ("4", "town:blocked:owner-retired"))
        self.assertEqual(policy._home_pending_item, target)
        self.assertIn("home-scan", policy._town_turn_arbiter.pending_retirement_owners)
        self.assertEqual(policy.consume_pending_home_visit_report(),
                         "home-visit:home-scan:knowledge-unobserved")
        self.assertIsNone(policy.consume_pending_home_visit_report())
        policy._home_knowledge_await_key(board(turn=110), producer="home-scan")
        self.assertIsNone(policy.consume_pending_home_visit_report())
        # A new town visit can request again; its first own await starts at 1.
        policy.choose_key(replace(board(turn=120), town_flag=False, floor_key=(1, 1, 0)))
        key = policy.choose_key(board(turn=121))
        self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
        policy.confirm_key_posted(key)
        self.assertEqual(policy.choose_key(board(turn=122)), "")
        self.assertEqual(policy.last_reason, "home:scan-await-observation")

    def test_errand_keeps_its_request_and_await_holder(self):
        policy = self.policy()
        target = policy._item_signature(wares()[LATER])
        policy._file_home_errand(board(turn=101), HomeErrandRequest(
            target, 1, "home-catalog", "identification-catalog"), knowledge_current=False)
        key = policy.choose_key(board(turn=102))
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, policy._home_errand.reason("request-knowledge")))
        self.assertEqual(policy._claim_register.current.owner.value, "home-errand")
        policy.confirm_key_posted(key)
        key = policy.choose_key(board(turn=103))
        self.assertEqual((key, policy.last_reason),
                         ("", policy._home_errand.reason("await-fresh-knowledge")))
        self.assertEqual(policy._claim_register.current.owner.value, "home-errand")

    def test_errand_lost_request_records_its_optional_outcome_once(self):
        policy = self.policy()
        target = policy._item_signature(wares()[LATER])
        policy._file_home_errand(board(turn=101), HomeErrandRequest(
            target, 1, "home-catalog", "identification-catalog"), knowledge_current=False)
        key = policy.choose_key(board(turn=102))
        policy.confirm_key_posted(key)
        for turn in range(103, 111):
            policy.choose_key(board(turn=turn))
        self.assertEqual(policy._home_errand.stopped_fact, "knowledge-unobserved")
        self.assertFalse(policy._home_errand.active)
        self.assertIn(target, policy._deferred_home_items)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy.consume_pending_home_visit_report(),
                         "home-visit:home-errand:knowledge-unobserved")
        self.assertIsNone(policy.consume_pending_home_visit_report())

    def test_cleanup_preserves_proved_content_and_fresh_take(self):
        policy = self.policy()
        policy.consume_home_knowledge(wares())
        policy._home_page_size = 12
        target = policy._item_signature(wares()[LATER])
        policy._home_pending_item = target
        page = replace(board(turn=102), store=StoreState(
            STORE_HOME, list(wares()[:12]), stock_num=20, page_size=12, page_top=0))
        key = policy.choose_key(page)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "home:leave-for-pending-withdraw"))
        policy.confirm_key_posted(key)
        key = policy.choose_key(board(turn=103))
        self.assertEqual((key, policy.last_reason),
                         ("5 pd1\r\x1b", "home:atomic-withdraw"))
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_atomic_withdraw_telemetry["resolved_letter"], "d")


if __name__ == "__main__":
    unittest.main()
