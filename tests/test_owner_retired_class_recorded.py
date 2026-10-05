"""Recorded boards with explicitly reconstructed owners, not a policy replay.

The backups contain no policy checkpoint. Historical decisions pin the before
stop; reconstruction exercises the actual effect, route and final policy seams.
"""
import gzip
import hashlib
import json
from pathlib import Path
from dataclasses import replace
import unittest
from unittest.mock import patch

import tests  # isolate runtime files
from hengbot.model import parse_snapshot, Position, STORE_HOME, TVAL_WAND
from hengbot.policy import HengbotPolicy
from hengbot.home_errand import HomeErrandRequest
from hengbot.policy_types import StoreVisit
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.town_arbiter import town_owner_progress, _new_town_turn_arbiter


FIXTURE = Path(__file__).parent / "fixtures/owner-retired-class-20261005.json.gz"


class OwnerRetiredClassRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
            "2ba6724d02a6c87a7a6a40caa114b8b84479cbf7bf24a8f918c71c93c8ed1ce9")
        cls.pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))["pins"]

    def state(self, stamp, line):
        row = next(entry["row"] for entry in self.pins[stamp]["state-fixed"]
                   if entry["line"] == line)
        # Static reconstructed lore is only needed to parse captured monsters;
        # positions, inventory and store observations remain the recorded rows.
        lore = {monster["race_id"]: MonraceKnowledge(10, 110, False, False)
                for monster in row.get("visible_monsters", []) + row.get("detected_monsters", [])}
        return parse_snapshot(row, lore)

    def old_stop(self, stamp):
        row = self.pins[stamp]["decisions"][-1]["row"]
        self.assertEqual(row["reason"], "town:blocked:owner-retired")
        return row

    def test_1549_observed_relief_releases_stale_home_route_verdict(self):
        self.assertTrue(self.old_stop("154937")["arbiter"]["retired"])
        p = HengbotPolicy()
        taken = self.state("154937", 78)
        sold = self.state("154937", 84)
        p.prime(taken)
        target = next(item for item in taken.inventory if item.tval == 80 and item.sval == 19)
        self.assertFalse(any(item.tval == 80 and item.sval == 19 for item in sold.inventory))
        p._home_full_relief = {
            "town": p._effective_town_id(sold), "remaining": 1,
            "deposits": (), "sale": (p._item_signature(target), 0, 0),
            "withdrawn": True,
        }
        p._town_blocked_reason = "home-full-deposit-retry-unreachable"
        p._home_full_relief_key(sold)
        self.assertIsNone(p._town_blocked_reason)
        self.assertIsNone(p._home_full_relief)
        final = self.state("154937", 91)
        step = p._shopping_approach_step(final, STORE_HOME, requester="home-visit")
        self.assertIsNotNone(step)
        key = p._shopping_approach_key(final, step, "shop:travel")
        self.assertTrue(key)
        self.assertNotEqual(p.last_reason, "town:blocked:owner-retired")

    def test_1553_pooled_wand_take_is_observed_and_relief_continues(self):
        self.assertTrue(self.old_stop("155328")["arbiter"]["retired"])
        p = HengbotPolicy()
        before, after = self.state("155328", 84), self.state("155328", 86)
        target = next(item for item in before.store.items if item.tval == TVAL_WAND and item.sval == 6)
        signature = p._item_signature(target)
        # Historical exact-name matching misses the pooled, renamed stack.
        self.assertEqual(p._inventory_signature_count(after, signature), 0)
        self.assertEqual(p._home_transfer_count(before, target), 1)
        self.assertEqual(p._home_transfer_count(after, target), 2)
        # The current producer avoids creating this legacy pooled disposal
        # request in the first place, keeping the existing device supply.
        self.assertIsNone(p._home_full_sale_candidate(before, target))
        p.prime(before)
        p._town_turn_arbiter = _new_town_turn_arbiter()
        p._home_errand.file(HomeErrandRequest(signature, 1, "home-catalog", "full-home-sale"),
                            knowledge_current=True)
        p._home_errand.post(1)
        p._home_atomic_withdraw_pending = (signature, 1, target, 1)
        p._home_atomic_withdraw_posted_turn = before.turn
        p._town_blocked_reason = "home-full-surplus-withdraw-failed"
        p._observe_home_atomic_withdrawal_outside(after)
        self.assertEqual(p._home_errand.state.value, "done")
        self.assertIsNone(p._town_blocked_reason)
        self.assertIsNone(p._home_atomic_withdraw_pending)
        # A later route remains eligible after the real stock/pack effect.
        self.assertTrue(p._town_turn_arbiter.preview_may_select(
            "shop:travel", p._town_arbiter_progress_vector(after, "shop:travel")))

    def test_1605_save_suspends_progressing_route_at_public_boundary(self):
        historical = self.old_stop("160548")
        self.assertEqual(historical["arbiter"]["budget_remaining_estimate"], 2)
        self.assertFalse(historical["arbiter"]["retired"])
        p = HengbotPolicy()
        before, after = self.state("160548", 99), self.state("160548", 100)
        p.prime(before)
        p._town_turn_arbiter = _new_town_turn_arbiter()
        p._store_visit = StoreVisit(owner="town-errand", purpose="shopping",
                                   store_type=6, goal=Position(45, 84))
        arbiter = p._town_turn_arbiter
        vector = p._town_arbiter_progress_vector(before, "shop:approach")
        arbiter.observe(in_town=True, reason="shop:approach", progress_vector=vector)
        budgets = dict(arbiter._no_progress_by_owner)
        vectors = dict(arbiter._vector_by_owner)
        recurrences = dict(arbiter._recurrences)
        def save(_snapshot):
            p.last_reason = "periodic:game-save"
            return "\x1b\x13"
        with patch.object(p, "_skill_exp_request_key", return_value=None), patch.object(
                p, "_choose_key_with_latch_capture", side_effect=save):
            key = p.choose_key(after)
        self.assertEqual(key, "\x1b\x13")
        self.assertEqual(p.last_reason, "periodic:game-save")
        self.assertEqual(arbiter._no_progress_by_owner, budgets)
        self.assertEqual(arbiter._vector_by_owner, vectors)
        self.assertEqual(dict(arbiter._recurrences), recurrences)
        resumed = p._town_arbiter_progress_vector(after, "shop:approach")
        self.assertTrue(town_owner_progress(vector, resumed))
        self.assertTrue(arbiter.preview_may_select("shop:approach", resumed))

    def test_interruptions_do_not_spend_or_refill_route_budget(self):
        p = HengbotPolicy()
        board = self.state("160548", 99)
        p._store_visit = StoreVisit(owner="town-errand", purpose="shopping",
                                   store_type=6, goal=Position(45, 84))
        a = p._town_turn_arbiter
        vector = p._town_arbiter_progress_vector(board, "shop:approach")
        a.observe(in_town=True, reason="shop:approach", progress_vector=vector)
        a.observe(in_town=True, reason="shop:approach", progress_vector=vector)
        remaining = a._no_progress_by_owner["store-router"]
        recurrence = dict(a._recurrences)
        for reason in ("town:kill-mob-approach", "melee", "seek-loot", "periodic:game-save"):
            a.observe(in_town=True, reason=reason,
                      progress_vector=p._town_arbiter_progress_vector(board, reason))
        self.assertEqual(a._no_progress_by_owner["store-router"], remaining)
        self.assertEqual(a._recurrences[("store-router", next(
            key[1] for key in recurrence if key[0] == "store-router"))], 1)
        a.observe(in_town=True, reason="shop:approach", progress_vector=vector)
        self.assertEqual(a._no_progress_by_owner["store-router"], remaining + 1)

    def test_true_stall_still_retires_visibly_at_public_boundary(self):
        p = HengbotPolicy()
        board = self.state("160548", 100)
        p.prime(board)
        def blocked(_snapshot):
            p.last_reason = "town:blocked:constructed-no-effect"
            return "5"
        with patch.object(p, "_skill_exp_request_key", return_value=None), patch.object(
                p, "_choose_key_with_latch_capture", side_effect=blocked):
            for _ in range(p._town_turn_arbiter.registry["town-plan"].budget + 2):
                key = p.choose_key(board)
        self.assertEqual(key, "5")
        self.assertEqual(p.last_reason, "town:blocked:owner-retired")
        self.assertTrue(p._town_turn_arbiter.telemetry["retired"])

    def test_gold_and_internal_flags_do_not_prove_progress(self):
        p = HengbotPolicy()
        board = self.state("160548", 100)
        vector = p._town_arbiter_progress_vector(board, "town-plan:waiting")
        p._town_blocked_reason = "changed-bookkeeping"
        richer = replace(board, player=replace(board.player, gold=board.player.gold + 1000))
        self.assertFalse(town_owner_progress(vector, p._town_arbiter_progress_vector(
            richer, "town-plan:waiting")))

    def test_distance_requires_the_same_declared_target_and_a_decrease(self):
        p = HengbotPolicy()
        board = replace(self.state("160548", 99), grids={})
        p._store_visit = StoreVisit(owner="town-errand", purpose="shopping",
                                   store_type=6, goal=Position(45, 84))
        vector = p._town_arbiter_progress_vector(board, "shop:approach")
        for position in (Position(42, 93), Position(44, 92)):
            moved = replace(board, player=replace(board.player, position=position))
            self.assertFalse(town_owner_progress(vector, p._town_arbiter_progress_vector(
                moved, "shop:approach")))
        p._shopping_approach_goal = board.player.position
        self.assertFalse(town_owner_progress(vector, p._town_arbiter_progress_vector(
            board, "shop:approach")))

    def test_observed_home_stock_change_counts_with_unchanged_pack(self):
        p = HengbotPolicy()
        board = self.state("155328", 84)
        p._home_knowledge_items = list(board.store.items)
        vector = p._town_arbiter_progress_vector(board, "home:request-knowledge-scan")
        p._home_knowledge_items = p._home_knowledge_items[1:]
        self.assertTrue(town_owner_progress(vector, p._town_arbiter_progress_vector(
            board, "home:request-knowledge-scan")))


class OwnerRetiredClass2RecordedTest(unittest.TestCase):
    """October 5 17:21/17:22 pins; no checkpoint or post-divergence replay."""

    @classmethod
    def setUpClass(cls):
        fixture = FIXTURE.with_name("owner-retired-class2-20261005.json.gz")
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == (
            "91f878d9f0e43a4b248333c196ed1bf56bf60668aee3a169b37e0be55cc545f4")
        cls.pins = json.loads(gzip.decompress(fixture.read_bytes()))["pins"]

    def state(self, stamp, line):
        row = next(entry["row"] for entry in self.pins[stamp]["state-fixed"]
                   if entry["line"] == line)
        lore = {monster["race_id"]: MonraceKnowledge(10, 110, False, False)
                for monster in row.get("visible_monsters", []) + row.get("detected_monsters", [])}
        return parse_snapshot(row, lore)

    def decision(self, stamp, line):
        return next(entry["row"] for entry in self.pins[stamp]["decisions"]
                    if entry["line"] == line)

    def test_purchase_effect_survives_same_store_reentry_at_public_boundary(self):
        self.assertTrue(self.decision("172143", 220)["arbiter"]["retired"])
        self.assertEqual(self.decision("172143", 223)["reason"],
                         "town:blocked:owner-retired")
        p = HengbotPolicy()
        before, bought, reentry = (self.state("172143", line) for line in (69, 70, 71))
        self.assertEqual((before.inventory[2].count, bought.inventory[2].count), (8, 9))
        p.prime(before)
        p._shopping_approach_goal = reentry.player.position
        p._store_visit = StoreVisit(owner="town-errand", purpose="shopping", store_type=6,
                                   goal=reentry.player.position)
        a = p._town_turn_arbiter
        vector = p._town_arbiter_progress_vector(before, "shop:travel:await-entry")
        a.observe(in_town=True, reason="shop:travel:await-entry", progress_vector=vector)
        # Reconstruct the captured route recurrence at its last permitted count.
        from hengbot.town_arbiter import town_recurrence_key
        a._recurrences[("store-router", town_recurrence_key(vector))] = (
            a.registry["detectors"].budget - 1)
        a._last_pair = None
        def resume(_snapshot):
            p.last_reason = "shop:travel:await-entry"
            p._intentional_entrance_activation = True
            return "5"
        with patch.object(p, "_skill_exp_request_key", return_value=None), patch.object(
                p, "_choose_key_with_latch_capture", side_effect=resume):
            self.assertEqual(p.choose_key(reentry), "5")
        self.assertEqual(p.last_reason, "shop:travel:await-entry")
        self.assertTrue(a.telemetry["progress"])
        self.assertEqual(a.telemetry["budget_remaining_estimate"], a.registry["store-router"].budget)
        self.assertNotIn("store-router", a._retired)
        # Gold alone cannot give the same route this credit.
        richer = replace(before, player=replace(before.player, gold=before.player.gold + 1000))
        self.assertFalse(town_owner_progress(vector, p._town_arbiter_progress_vector(
            richer, "shop:travel:await-entry")))
        # A sale has the same observed-effect contract, with gold excluded.
        sold = replace(reentry, inventory=before.inventory)
        self.assertTrue(town_owner_progress(p._town_arbiter_progress_vector(
            reentry, "shop:travel"), p._town_arbiter_progress_vector(sold, "shop:travel")))

    def test_fresh_routed_home_requests_complete_catalogue_instead_of_reentry(self):
        self.assertEqual(self.decision("172225", 218)["reason"], "home:scan-incomplete-open-page")
        self.assertTrue(self.decision("172225", 221)["arbiter"]["retired"])
        self.assertEqual(self.decision("172225", 224)["reason"], "town:blocked:owner-retired")
        for line in (70, 74):
            with self.subTest(line=line):
                p = HengbotPolicy()
                outside, page = self.state("172225", 69), self.state("172225", line)
                p.prime(outside)
                p._store_visit = StoreVisit(owner="town-errand", purpose="shopping", store_type=STORE_HOME)
                self.assertEqual((page.store.capacity, page.store.stock_num, len(page.store.items)), (240, 239, 52))
                self.assertFalse(p._home_knowledge_invalidated)
                self.assertFalse(p._open_home_page_is_complete(page))
                with patch.object(p, "_skill_exp_request_key", return_value=None):
                    key = p.choose_key(page)
                from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
                self.assertEqual((key, p.last_reason), (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
                self.assertFalse(p._equipment_catalog.home_scan_complete)
                # No historical board after the changed key proves its effect.
                # Reconstruct a complete response of the captured catalogue size.
                items = tuple(replace(p._inventory_item_from_store_item(page.store.items[i % 52]),
                                      slot=i, name=f"reconstructed-home-{i}") for i in range(239))
                self.assertTrue(p.consume_home_knowledge(items))
                self.assertTrue(p._equipment_catalog.home_scan_complete)
                self.assertTrue(p._home_knowledge_current)
                self.assertEqual(p._home_scan_item_count, 239)
                self.assertEqual(len(p._home_knowledge_items), 239)
                self.assertIsNone(p._home_knowledge_scan_epoch)

    def test_recorded_unchanged_home_reentry_still_exhausts_route_budget(self):
        p = HengbotPolicy()
        board = self.state("172225", 71)
        p.prime(board)
        p._shopping_approach_goal = board.player.position
        def stalled(_snapshot):
            p.last_reason = "shop:travel:await-entry"
            return "5"
        with patch.object(p, "_skill_exp_request_key", return_value=None), patch.object(
                p, "_choose_key_with_latch_capture", side_effect=stalled):
            for _ in range(p._town_turn_arbiter.registry["store-router"].budget + 2):
                p.choose_key(board)
                if p.last_reason == "town:blocked:owner-retired":
                    break
        self.assertEqual(p.last_reason, "town:blocked:owner-retired")


if __name__ == "__main__":
    unittest.main()
