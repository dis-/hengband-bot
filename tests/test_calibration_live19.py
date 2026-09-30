"""Recorded live19 calibration restoration through the production executors.

The initial debt is registered by the real deposit producer against the original
carried items. Subsequent inventory/knowledge facts are byte-faithful recorded
boards; after a changed command they prove only observation/recovery, not that
the historical next board is the result of the changed command.
"""

import gzip
import hashlib
import json
import pickle
import re
import unittest
from dataclasses import replace
from pathlib import Path

import tests  # noqa: F401 -- isolate runtime writes
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import STORE_HOME, _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures/live19-calibration-restore-20261001.jsonl.gz"


def rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as source:
        return list(map(json.loads, source))


def outside(raw, turn):
    return parse_snapshot(next(r for r in raw if r["turn"] == turn
                               and not r.get("store")
                               and r.get("type") == "player_turn"), {})


def catalogue(policy, raw, turn):
    page = next(r for r in raw if r["turn"] == turn and r.get("knowledge"))
    policy.consume_home_knowledge(tuple(_parse_items(page["knowledge"]["items"])))
    # Page size is protocol evidence from an observed Home page in this capture.
    home = next(r for r in raw if r.get("store", {}).get("store_type") == STORE_HOME)
    policy._home_page_size = home["store"]["page_size"]


def deposited_policy(raw):
    policy = HengbotPolicy()
    policy.observe_town_visit_epoch(True, 549266)
    policy.consume_skill_knowledge(next(r for r in raw
        if r.get("knowledge", {}).get("category") == "skill_exp"))
    policy._crossarea_fundraising_enforced = True
    policy._calibration_redress_loaded = True
    policy._calibration_phase = "deposit"
    initial = outside(raw, 549266)
    for carried in initial.inventory:
        policy._home_deposit_key(initial, carried, forced_count=carried.count)
    policy._calibration_phase = "restore-supplies"
    policy._shopping_approach_store_type = STORE_HOME
    return policy


class Live19CalibrationTest(unittest.TestCase):
    def test_fixture_and_missing_target_are_recorded_facts(self):
        with gzip.open(FIXTURE, "rb") as source:
            frozen = source.read()
        self.assertEqual(hashlib.sha256(frozen).hexdigest(),
                         "f2b061635c3c867f73b972d06a04a6d2c2e2ac78b4216610a98b8e1b7431131d")
        raw = rows()
        self.assertEqual(len(raw), 84)
        initial = outside(raw, 549266)
        final = outside(raw, 549419)
        gloves = next(i for i in initial.inventory if i.tval == 31)
        self.assertTrue(any(equipment_identity(i) == equipment_identity(gloves)
                            for i in final.equipment))
        policy = deposited_policy(raw)
        catalogue(policy, raw, 549419)
        self.assertFalse(any(policy._calibration_restore_item_matches(
            policy._item_signature(gloves), i) for i in policy._home_knowledge_items))

    def test_recorded_restore_observation_resolves_to_terminal_not_step_off(self):
        raw = rows()
        for restored in (False, True):
            with self.subTest(checkpoint=restored):
                policy = deposited_policy(raw)
                catalogue(policy, raw, 549401)
                board = outside(raw, 549401)
                with gzip.open(FIXTURE.with_name(
                        "live19-calibration-decisions-20261001.jsonl.gz"),
                        "rt", encoding="utf-8") as source:
                    posted = next(r for r in map(json.loads, source)
                                  if r["decision_sequence"] == 3034)
                # Reconstruct the actual posted macro's pending observation
                # from recorded shelf letters/counts, not a counterfactual key.
                entries = []
                for letter, amount in re.findall(r"p([a-zA-Z])(\d*\r)?", posted["key"]):
                    index = ord(letter) - (ord("a") if letter.islower()
                                           else ord("A") - 26)
                    item = policy._home_knowledge_items[index]
                    signature = policy._item_signature(item)
                    entries.append((signature, policy._inventory_signature_count(
                        board, signature), item, int(amount) if amount else 1, index))
                pending = (*entries[-1][:4], tuple(entries))
                self.assertEqual(len(entries), 17)
                if restored:
                    policy = pickle.loads(pickle.dumps(policy))
                # Historical macro response: 57 torches, then the recorded
                # overweight deposit and fresh ~9.
                after = outside(raw, 549413)
                policy._observe_calibration_restore_batch(after, pending)
                catalogue(policy, raw, 549419)
                final = outside(raw, 549419)
                key = policy._atomic_home_withdraw_key(final, final.player.position)
                decision = policy._enforce_town_claim_result(final, key)
                print("live19 recorded recovery:", repr(decision), policy.last_reason)
                self.assertIsNone(decision)
                self.assertEqual(policy.last_reason,
                                 "town:blocked:calibration-restore-target-absent")
                self.assertTrue(policy._calibration_restore_signatures)
                self.assertIsNone(policy._home_atomic_deposit_pending)

    def test_batch_uses_deposit_quantities_and_cumulative_weight(self):
        raw = rows()
        policy = deposited_policy(raw)
        catalogue(policy, raw, 549401)
        board = outside(raw, 549401)
        owed = policy._home_pending_quantities.copy()
        key = policy._atomic_home_withdraw_key(board, board.player.position)
        self.assertIsNotNone(key)
        entries = policy._home_atomic_withdraw_pending[4]
        for signature, _before, withdrawn, quantity, _index in entries:
            self.assertEqual(quantity, owed[signature])
            self.assertLessEqual(quantity, withdrawn.count)
        self.assertLessEqual(policy._inventory_weight(board) + sum(
            withdrawn.weight * quantity for _, _, withdrawn, quantity, _ in entries
        ), policy._inventory_weight_limit(board))
        torch = next(e for e in entries if e[2].is_torch)
        self.assertEqual(torch[2].count, 57)
        self.assertEqual(torch[3], 5)
        self.assertIn("py5\r", key)
        # Capacity changes select a smaller whole-debt batch or stop visibly.
        heavy = replace(board, inventory=[replace(
            outside(raw, 549266).inventory[0], count=1,
            weight=policy._inventory_weight_limit(board)
                   - policy._inventory_weight(board) - 100)])
        constrained = deposited_policy(raw)
        catalogue(constrained, raw, 549401)
        key = constrained._atomic_home_withdraw_key(heavy, heavy.player.position)
        self.assertIsNotNone(key)
        pending = constrained._home_atomic_withdraw_pending
        if pending is not None:
            entries = pending[4] if len(pending) == 5 else (pending[:4] + (0,),)
            self.assertLessEqual(constrained._inventory_weight(heavy) + sum(
                item.weight * quantity for _, _, item, quantity, _ in entries
            ), constrained._inventory_weight_limit(heavy))
        else:
            self.assertEqual(constrained.last_reason,
                             "town:blocked:calibration-restore-weight-limit")

    def test_restore_excludes_foreign_producers_off_and_on_after_checkpoint(self):
        raw = rows()
        for enforced in (False, True):
            for restored in (False, True):
                with self.subTest(s33=enforced, checkpoint=restored):
                    policy = deposited_policy(raw)
                    policy._town_claim_bar_enforced = enforced
                    policy._map_predicate_snapshot = outside(raw, 549376)
                    if restored:
                        policy = pickle.loads(pickle.dumps(policy))
                    for family in ("equipment-txn", "equipment-opt", "home-errand",
                                   "shop-buy", "shop-sell", "departure", "fundraising",
                                   "store-router", "home-visit"):
                        self.assertIsNone(policy._town_producer_entry(
                            "_equipment_transaction_town_key", lambda: self.fail(
                                "foreign town producer entered restore"), family=family))
                    self.assertIsNone(policy._prepare_equipment_optimization(
                        outside(raw, 549376)))
                    self.assertIsNone(policy._equipment_transaction_session)
                    board = outside(raw, 549413)
                    self.assertIsNone(policy._atomic_home_deposit_key(
                        board, board.player.position))
                    self.assertIsNone(policy._home_atomic_deposit_pending)

    def test_public_capture_uses_calibration_session_then_restore_or_typed_stop(self):
        raw = rows()
        policy = deposited_policy(raw)
        initial = outside(raw, 549266)
        policy._calibration_worn_before = tuple(
            (i.slot, equipment_identity(i)) for i in initial.equipment)
        policy._calibration_stripped_unrestored = True
        policy._calibration_phase = "capture"
        policy._calibration_naked_dump_requested = True
        policy._calibration_naked_flags = frozenset()
        policy._equipment_catalog.home_scan_complete = True
        boards = [outside(raw, turn) for turn in (
            549327, 549337, 549346, 549359, 549367, 549371, 549376)]
        decisions = []
        for board in boards:
            key = policy.choose_key(board)
            decisions.append((key, policy.last_reason,
                              (policy.decision_claim or {}).get("owner")))
            if key is None:
                break
            policy.confirm_key_posted(key)
        print("live19 capture continuation:", decisions)
        self.assertTrue(decisions)
        self.assertFalse(any(owner == "equipment-txn" for _, _, owner in decisions))
        self.assertFalse(any("travel-home" in reason for _, reason, _ in decisions))
        self.assertTrue(decisions[-1][0] is None or
                        decisions[-1][1] == "calibration:request-restore-knowledge")

    def test_absent_restore_and_overweight_are_typed_with_all_switches_off(self):
        raw = rows()
        for restored in (False, True):
            policy = deposited_policy(raw)
            policy._crossarea_fundraising_enforced = False
            # Observe the already-posted historical batch to recover its sole
            # missing signature, without marking that signature complete.
            final = outside(raw, 549419)
            glove = next(i for i in outside(raw, 549266).inventory if i.tval == 31)
            debt = policy._item_signature(glove)
            policy._calibration_restore_signatures = [debt]
            catalogue(policy, raw, 549419)
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            key = policy._atomic_home_withdraw_key(final, final.player.position)
            self.assertIsNone(policy._enforce_town_claim_result(final, key))
            self.assertEqual(policy.last_reason,
                             "town:blocked:calibration-restore-target-absent")
            self.assertEqual(policy._calibration_restore_signatures, [debt])
            heavy = outside(raw, 549413)
            self.assertTrue(policy._inventory_overweight(heavy))
            key = policy._calibration_town_key(heavy)
            self.assertIsNone(policy._enforce_town_claim_result(heavy, key))
            self.assertEqual(policy.last_reason,
                             "town:blocked:calibration-restore-weight-limit")
            self.assertEqual(policy._calibration_restore_signatures, [debt])


if __name__ == "__main__":
    unittest.main()
