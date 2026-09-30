"""Recorded live22 attachments stop at the first key divergence."""
import gzip
import json
import pickle
from pathlib import Path
import unittest
from dataclasses import replace
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.claim_register import reach
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).parent / "fixtures" / "live22-bounty"


def boards():
    with gzip.open(FIXTURE / "state.jsonl.gz", "rt", encoding="utf8") as source:
        return [parse_snapshot(row, {}) for row in map(json.loads, source)]


def attached_policy():
    recorded = boards()
    policy = HengbotPolicy()
    policy.prime(recorded[0])
    # Reconstruct the observed supplier context, not a fake shelf or UI.
    policy._shopping_approach_goal = recorded[3].player.position
    policy._shopping_approach_store_type = recorded[3].store.store_type
    policy._town_supplier_stock[4] = recorded[3].store
    return policy, recorded


def bounty_result(policy, board):
    policy._map_predicate_snapshot = board
    policy._build_grid_index(board)
    key = policy._town_order_step4_key(board)
    key = policy._town_procurement_decision(board, key)
    policy._record_decision_claim(board, key)
    return key, policy.last_reason


class Live22BountyTest(unittest.TestCase):
    def test_recorded_cycle_and_bounty_destination(self):
        with gzip.open(FIXTURE / "decisions.jsonl.gz", "rt", encoding="utf8") as source:
            rows = list(map(json.loads, source))
        self.assertEqual([row["key"] for row in rows], ["7", "3", "\x1b", "7"])
        self.assertEqual(rows[2]["store_type"], 4)
        self.assertEqual(rows[2]["claim"]["s33_shadow"]["would_stop"],
                         "ownership:gate-missing:quest-request")
        self.assertEqual(rows[0]["claim"]["goal"]["cell"], [25, 71])
        bounty = next(item for item in boards()[0].inventory if item.is_bounty)
        self.assertEqual(bounty.slot, "r")

    def test_recorded_production_path_first_divergence_is_office_walk(self):
        for restored in (False, True):
            policy, recorded = attached_policy()
            self.assertEqual(bounty_result(policy, recorded[0]), ("7", "bounty:approach"))
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            # Live sends 3 here. Never feed the resulting store page as the
            # consequence of this new 7: this is the last replayed decision.
            self.assertEqual(bounty_result(policy, recorded[1]), ("7", "bounty:approach"))
            self.assertEqual(policy._decision_goal[0], "quest-request")
            self.assertEqual(policy._decision_goal[1].cell, (25, 71))
            self.assertEqual(policy._shopping_approach_goal, Position(37, 91))

    def test_recorded_supplier_entry_has_typed_nothing_to_do_release(self):
        policy, recorded = attached_policy()
        board = recorded[3]  # independent attachment, never post-divergence
        policy._map_predicate_snapshot = board
        self.assertEqual(policy._town_order_step4_key(board), "\x1b")
        offer = policy._execution_offers_for()[-1]
        self.assertEqual(offer[1:3], ("quest-request", "normal-step4-bounty"))
        self.assertEqual(offer[8], "releasing")
        self.assertEqual(offer[10], "nothing-to-do-here:supplier:4")
        # This independently attached ESC matches live decision 5125, so its
        # recorded outside board is an action-consistent continuation.
        self.assertEqual(bounty_result(policy, recorded[4]), ("7", "bounty:approach"))
        self.assertEqual(policy._decision_goal[1].cell, (25, 71))

    def test_recorded_supplier_asks_family_gate_off_and_on_after_restore(self):
        for enforced in (False, True):
            for restored in (False, True):
                policy, recorded = attached_policy()
                policy._town_claim_bar_enforced = enforced
                board = recorded[3]
                policy._map_predicate_snapshot = board
                policy._claim_register.declare("store-router", reach((25, 71)))
                if restored:
                    policy = pickle.loads(pickle.dumps(policy))
                key = policy._town_order_step4_key(board)
                self.assertEqual(key, None if enforced else "\x1b")
                deferred = policy._decision_errand_deferred[-1]
                self.assertEqual(deferred["deferred_family"], "quest-request")
                self.assertEqual(deferred["holder_family"], "store-router")
                if not enforced:
                    shadow = policy._s33_shadow_verdict(board, key)
                    self.assertEqual(shadow["would_stop"], "ownership:gate-missing:quest-request")

    def test_recorded_route_has_bound_continuation_after_restore(self):
        for awaiting in (False, True):
            policy, recorded = attached_policy()
            policy._town_claim_bar_enforced = True
            board = recorded[0]
            policy._map_predicate_snapshot = board
            key = policy._town_order_step4_key(board)
            policy._record_decision_claim(board, key)
            claim = policy._claim_register.current
            if awaiting:
                policy._claim_register.declare_execution(
                    claim.claim_id, producer="quest-request", work_id="normal-step4-bounty",
                    state="awaiting", next_step="bounty.resume", continuation="bounty.resume",
                    operation_ref="decision:5123:7", expected_effect="bounty-removed")
            policy = pickle.loads(pickle.dumps(policy))
            holder = policy._claim_register.current
            self.assertEqual(policy._claim_errand_hold("shop-buy"), holder)
            self.assertEqual(policy._claim_errand_hold("quest-request"), None)
            self.assertEqual(policy._town_producer_entry(
                "_atomic_shop_transaction_key", lambda: self.fail("supplier displaced bounty"),
                family="shop-buy"), None)
            self.assertEqual(policy._town_holder_structural_stop(holder, board), None)
            self.assertEqual(policy._town_holder_declared_key(holder, board), "7")
            self.assertEqual(policy.last_reason, "bounty:approach")
            self.assertEqual(policy._s33_shadow_verdict(board, "7")["would_stop"], None)
            self.assertEqual(policy._s33_shadow_verdict(board, "7")["holder_family"], "quest-request")
            self.assertEqual(policy._s33_shadow_verdict(board, None)["would_stop"], None)

    def test_repeated_ineffective_declared_route_stops_instead_of_other_errand(self):
        # Recorded board, independent unit attachment with a deliberately
        # ineffective declared destination. No fabricated follow-up board.
        for restored in (False, True):
            policy, recorded = attached_policy()
            board = recorded[1]
            policy._town_begin_progress_decision(board)
            policy.last_reason = "bounty:approach"
            policy._declare_reach(Position(37, 91))
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            self.assertEqual(policy._town_procurement_decision(board, "7"), "5")
            self.assertEqual(policy.last_reason, "town:blocked:route-nonprogress:quest-request")
            self.assertEqual(policy._town_blocked_reason, "route-nonprogress:quest-request")

    def test_obsolete_bounty_reports_done_to_its_holder_after_restore(self):
        policy, recorded = attached_policy()
        board = recorded[0]
        policy._map_predicate_snapshot = board
        policy._town_order_step4_key(board)
        policy = pickle.loads(pickle.dumps(policy))
        # Supplemental unit case, not a claim that the divergent replay cashed out.
        cleared = replace(board, inventory=[item for item in board.inventory if not item.is_bounty])
        self.assertEqual(policy._town_order_step4_key(cleared), None)
        self.assertEqual(policy._decision_offer_buffer().no_steps[-1][:3],
                         ("quest-request", "normal-step4-bounty", "bounty-removed"))
        self.assertEqual(policy._decision_offer_buffer().no_steps[-1][4], "done")
        self.assertEqual(policy._town_order_operation, None)

    def test_other_routes_keep_their_supplier_progress_after_restore(self):
        for restored in (False, True):
            policy, recorded = attached_policy()
            board = recorded[1]
            policy.last_reason = "shop:approach"
            policy._shopping_approach_goal = Position(25, 71)
            policy._declare_reach(Position(37, 91))
            policy._town_begin_progress_decision(board)
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            self.assertTrue(policy._town_result_makes_progress(board, "7"))
            self.assertEqual(policy._town_procurement_decision(board, "7"), "7")
            self.assertEqual(policy.last_reason, "shop:approach")

    def test_other_ineffective_routes_keep_the_existing_resolution(self):
        for restored in (False, True):
            policy, recorded = attached_policy()
            board = recorded[1]
            policy.last_reason = "shop:approach"
            policy._declare_reach(Position(37, 91))
            policy._town_begin_progress_decision(board)
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            with patch.object(policy, "_town_result_makes_progress", return_value=False):
                self.assertEqual(policy._town_procurement_decision(board, "7"), "7")
            self.assertEqual(policy.last_reason, "shop:approach")
            self.assertIsNone(policy._town_blocked_reason)

    def test_missing_office_route_skips_without_latching_after_restore(self):
        policy = HengbotPolicy()
        board = replace(boards()[0], grids={})  # supplemental route-failure unit
        policy._map_predicate_snapshot = board
        self.assertIsNone(policy._town_order_step4_key(board))
        self.assertIsNone(policy._town_blocked_reason)
        restored = pickle.loads(pickle.dumps(policy))
        self.assertIsNone(restored._town_blocked_reason)
        self.assertIsNone(restored._town_order_step4_key(board))

    def test_missing_office_releases_existing_bounty_holder_after_restore(self):
        policy, recorded = attached_policy()
        board = recorded[0]
        policy._town_claim_bar_enforced = True
        policy._map_predicate_snapshot = board
        key = policy._town_order_step4_key(board)
        policy._record_decision_claim(board, key)
        policy = pickle.loads(pickle.dumps(policy))
        missing = replace(board, grids={})
        policy._map_predicate_snapshot = missing
        self.assertIsNone(policy._town_holder_declared_key(
            policy._claim_register.current, missing))
        self.assertEqual(policy.last_reason, "ownership:holder-released:quest-request")
        self.assertEqual(policy._claim_register.current.closed, "release")
        self.assertEqual(policy._claim_register.current.closed_reason,
                         "no-step:bounty-office-route-unavailable")
        self.assertIsNone(policy._town_blocked_reason)

    def test_unavailable_office_step_off_skips_without_a_block_after_restore(self):
        board = boards()[0]
        office = Position(25, 71)
        # Supplemental closed-in office board, no invented replay continuation.
        board = replace(board, player=replace(board.player, position=office),
                        grids={office: board.grids[office]})
        policy = HengbotPolicy()
        policy.prime(board)
        policy = pickle.loads(pickle.dumps(policy))
        self.assertIsNone(policy._bounty_cashout_key(board))
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(policy._decision_offer_buffer().no_steps[-1][:3],
                         ("quest-request", "normal-step4-bounty",
                          "bounty-office-step-off-unavailable"))


if __name__ == "__main__":
    unittest.main()
