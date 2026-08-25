from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot.cli import STATIONARY_REASONS
from hengbot.model import STORE_ALCHEMIST, STORE_TEMPLE, StoreState
from hengbot.policy import (
    HengbotPolicy,
    RESTOCK_WAIT_MACRO,
    STORE_RESTOCK_WAIT_TURNS,
    STORE_STUCK_LIMIT,
    TOWN_CYCLE_IGNORED_REASONS,
)
from hengbot.policy_types import StoreVisit, StoreVisitPhase, TownErrandPlan
from test_policy import (
    SV_SCROLL_WORD_OF_RECALL,
    TVAL_SCROLL,
    store_item,
)
from trajectory_harness import (
    checkpoint_row,
    replay_checkpoint_trajectory,
    restore_incident_checkpoint,
)


class TownRestockStallTrajectoryTest(unittest.TestCase):
    FIXTURE = (
        Path(__file__).parent
        / "fixtures"
        / "town-restock-stall-hungry-checkpoints.jsonl.gz"
    )
    INCIDENT_WINDOW = (
        Path(__file__).parent
        / "fixtures"
        / "incident-restock-rest-burn-window-20260825.jsonl.gz"
    )

    def test_incident_window_binds_entry_overwrite_and_rest_burn(self):
        with gzip.open(self.INCIDENT_WINDOW, "rt", encoding="utf-8") as rows:
            captured = [json.loads(line) for line in rows]
        by_sequence = {
            row["decision_sequence"]: row for row in captured
            if row["decision_sequence"] in {618, 640}
        }

        self.assertEqual(by_sequence[618]["reason"], "periodic:game-save")
        self.assertEqual(by_sequence[618]["key"], "\x13")
        self.assertEqual(
            by_sequence[618]["store_visit"]["opened_sequence"], 618
        )
        self.assertEqual(
            by_sequence[640]["reason"],
            "town:blocked:restocked-recall-store-unreachable",
        )
        wait_rows = [
            row for row in captured
            if row["key"] == RESTOCK_WAIT_MACRO
        ]
        self.assertGreaterEqual(len(wait_rows), 2)
        self.assertGreater(
            wait_rows[-1]["turn"] - wait_rows[0]["turn"],
            STORE_RESTOCK_WAIT_TURNS * 4,
        )

    @staticmethod
    def _seed_recall_variant(policy):
        policy._food_ready = lambda _snapshot: True
        policy._town_restock_wait_until = 0
        policy._town_restock_waiting_for = (3, 4)
        policy._town_restock_rechecked = set()
        policy._town_blocked_reason_value = (
            "restocked-recall-store-unreachable"
        )

    def test_hungry_character_escapes_recall_restock_owner_alternation(self):
        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            self.FIXTURE,
            (2331, 2333),
            forbidden_reasons={
                "town:blocked:restocked-recall-store-unreachable",
                "town:wait-restock:temple",
            },
            required_reason_prefix="town:blocked:survival-mana-no-charges",
        )
        self.assertEqual(len(transcript), 2)
        self.assertTrue(all(key == "5" for _reason, key in transcript))

    def test_mana_device_reserve_releases_stale_home_route(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "food-store-unreachable-checkpoints.jsonl.gz"
        )
        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            fixture,
            (220, 221, 223, 242),
            forbidden_reasons={
                "town:blocked:restocked-food-store-unreachable",
            },
            required_reason_prefix="shop:",
        )
        self.assertEqual(len(transcript), 4)
        self.assertTrue(all(
            reason == "shop:travel" and key == "\x1b`n&."
            for reason, key in transcript
        ))

    def test_recall_supplier_releases_stale_home_route(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "recall-store-unreachable-checkpoints.jsonl.gz"
        )
        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            fixture,
            (220,),
            forbidden_reasons={
                "town:blocked:restocked-recall-store-unreachable",
            },
            required_reason_prefix="shop:",
            # This reviewer variant CAN occur through the released-restock
            # path, but was not naturally captured.  Preserve the real
            # pre-decision policy and seed only food readiness and the released
            # recall-restock terminal state; the inert Home visit is part of
            # the real checkpoint.
            seed_policy=self._seed_recall_variant,
        )
        self.assertEqual(transcript, (("shop:travel", "\x1b`n%."),))

    def test_fresh_recall_requirement_routes_before_waiting(self):
        """R1 revert proof: removing the attempted-suppliers gate returns wait-restock."""
        def seed(policy):
            self._seed_recall_variant(policy)
            policy._town_restock_wait_until = None
            policy._town_restock_rechecked.clear()
            policy._town_store_attempted.pop(STORE_TEMPLE, None)
            policy._town_store_attempted.pop(STORE_ALCHEMIST, None)

        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz",
            (220,),
            forbidden_reasons={"town:wait-restock:temple"},
            required_reason_prefix="shop:",
            seed_policy=seed,
        )
        self.assertEqual(transcript, (("shop:travel", "\x1b`n%."),))

    def test_affordable_remembered_recall_stock_routes_to_supplier(self):
        """R2 revert proof: removing recall.obtainable restores the blocked terminal."""
        def seed(policy):
            self._seed_recall_variant(policy)
            policy._town_restock_wait_until = None
            policy._town_restock_rechecked.update(
                {STORE_TEMPLE, STORE_ALCHEMIST}
            )
            policy._town_store_attempted.update({STORE_TEMPLE: 1, STORE_ALCHEMIST: 1})
            recall = store_item(
                "i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                count=6, price=247, name="Word of Recall",
            )
            policy._town_supplier_stock = {
                **getattr(policy, "_town_supplier_stock", {}),
                STORE_TEMPLE: StoreState(
                    STORE_TEMPLE, [recall]
                ),
            }

        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz",
            (220,),
            forbidden_reasons={"town:blocked:restocked-recall-unavailable"},
            required_reason_prefix="shop:",
            seed_policy=seed,
        )
        self.assertEqual(transcript, (("shop:travel", "\x1b`n%."),))
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        seed(policy)
        key = policy._recall_restock_key(snapshot)
        self.assertTrue(policy.last_reason.startswith("shop:"))
        self.assertNotEqual(key, "5")
        recalled_shelf = policy._town_supplier_stock[STORE_TEMPLE]
        in_store = replace(snapshot, store=recalled_shelf)
        purchase = policy._next_purchase(in_store)
        self.assertIsNotNone(purchase)
        self.assertEqual(
            (purchase.tval, purchase.sval),
            (TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
        )
        # The incident checkpoint predates this unrelated per-visit diagnostic.
        policy._town_visit_sale_signatures = set()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = ()
        self.assertTrue(policy._shop(in_store).startswith("p"))
        self.assertEqual(policy.last_reason, "shop:buy-recall")

    def test_stall_15_affordable_alchemist_stock_never_arms_wait(self):
        """P-A1a: remembered affordable recall stock routes to the Alchemist."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        snapshot = replace(snapshot, player=replace(snapshot.player, gold=10_040))
        policy._food_ready = lambda _snapshot: True
        policy._town_restock_wait_until = None
        policy._town_restock_rechecked.clear()
        policy._town_store_attempted.update({STORE_TEMPLE: 1, STORE_ALCHEMIST: 1})
        policy._town_supplier_stock = {
            STORE_ALCHEMIST: StoreState(
                STORE_ALCHEMIST,
                [store_item(
                    "i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                    count=26, price=243, name="Word of Recall",
                )],
            )
        }

        key = policy._recall_restock_key(snapshot)

        self.assertNotEqual(key, RESTOCK_WAIT_MACRO)
        self.assertIsNone(policy._town_restock_wait_until)
        self.assertEqual(policy._shopping_approach_store_type, STORE_ALCHEMIST)

    def test_genuinely_empty_supplier_pages_still_arm_wait(self):
        """P-A1b: remembered pages without the needed item retain waiting."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_restock_wait_until = None
        policy._town_supplier_stock = {
            STORE_TEMPLE: StoreState(STORE_TEMPLE, []),
            STORE_ALCHEMIST: StoreState(STORE_ALCHEMIST, []),
        }

        self.assertIsNone(policy._retry_after_store_restock(
            snapshot, (STORE_TEMPLE, STORE_ALCHEMIST)
        ))
        self.assertEqual(
            policy._town_restock_wait_until,
            snapshot.turn + STORE_RESTOCK_WAIT_TURNS,
        )

    def test_affordable_but_unreachable_suppliers_block_without_wait(self):
        """P-A1c: route failure is detector-visible and cannot become waiting."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        snapshot = replace(snapshot, player=replace(snapshot.player, gold=10_040))
        policy._food_ready = lambda _snapshot: True
        policy._town_restock_wait_until = None
        policy._town_supplier_stock = {
            STORE_ALCHEMIST: StoreState(
                STORE_ALCHEMIST,
                [store_item(
                    "i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                    count=26, price=243, name="Word of Recall",
                )],
            )
        }
        with patch.object(policy, "_shopping_approach_step", return_value=None):
            key = policy._recall_restock_key(snapshot)

        reason = "town:blocked:restock-store-unreachable"
        self.assertNotEqual(key, RESTOCK_WAIT_MACRO)
        self.assertEqual(policy.last_reason, reason)
        self.assertIsNone(policy._town_restock_wait_until)
        self.assertNotIn(reason, TOWN_CYCLE_IGNORED_REASONS)
        self.assertNotIn(reason, STATIONARY_REASONS)

    def test_restock_timer_requires_observed_empty_supplier_page(self):
        """R3 revert proof: timer expiry alone must not add _town_restock_rechecked."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_store_attempted.update({STORE_TEMPLE: 1, STORE_ALCHEMIST: 1})
        policy._town_restock_rechecked.clear()
        policy._retry_after_store_restock(snapshot, (STORE_TEMPLE, STORE_ALCHEMIST))
        expiry = replace(snapshot, turn=policy._town_restock_wait_until)

        self.assertEqual(
            policy._retry_after_store_restock(
                expiry, (STORE_TEMPLE, STORE_ALCHEMIST)
            ),
            STORE_TEMPLE,
        )
        self.assertEqual(policy._town_restock_rechecked, set())
        self.assertIsNone(
            policy._retry_after_store_restock(
                expiry, (STORE_TEMPLE, STORE_ALCHEMIST)
            )
        )
        self.assertGreater(policy._town_restock_wait_until, expiry.turn)
        self.assertEqual(policy._town_restock_rechecked, set())

        empty_temple = replace(
            expiry, store=StoreState(STORE_TEMPLE, [])
        )
        policy._observe_restock_supplier_page(empty_temple)
        self.assertEqual(policy._town_restock_rechecked, {STORE_TEMPLE})

    def test_single_alchemist_wait_marks_stocked_nonmatching_page(self):
        """F3 revert proof: unrelated stock cannot satisfy the waiting need."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_restock_waiting_for = (STORE_ALCHEMIST,)
        policy._town_restock_rechecked.clear()

        unrelated = StoreState(
            STORE_ALCHEMIST,
            [store_item("a", TVAL_SCROLL, 1, price=1)],
        )
        policy._observe_restock_supplier_page(replace(snapshot, store=unrelated))

        self.assertEqual(policy._town_restock_rechecked, {STORE_ALCHEMIST})

    def test_single_alchemist_wait_with_matching_stock_routes_to_buy(self):
        """F3 revert proof: composable matching stock prevents recheck credit."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_restock_waiting_for = (STORE_ALCHEMIST,)
        policy._town_restock_rechecked.clear()
        policy._identification_need = "normal"
        identify_stock = StoreState(
            STORE_ALCHEMIST,
            [store_item("a", TVAL_SCROLL, 12, price=1)],
        )
        in_store = replace(snapshot, store=identify_stock)

        policy._observe_restock_supplier_page(in_store)

        self.assertEqual(policy._town_restock_rechecked, set())
        self.assertIsNotNone(policy._next_purchase(in_store))

    def test_unarmed_supplier_observation_cannot_reuse_stale_wait_tuple(self):
        """F4 revert proof: floor reset prevents stale observation credit."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        _restored, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy = HengbotPolicy()
        policy._town_restock_waiting_for = (STORE_TEMPLE, STORE_ALCHEMIST)
        policy._town_restock_rechecked.clear()
        policy._floor_key = (1, 1, 1)
        policy._observe(snapshot)

        policy._observe_restock_supplier_page(
            replace(
                snapshot,
                player=replace(snapshot.player, gold=100),
                store=StoreState(STORE_TEMPLE, []),
            )
        )

        self.assertEqual(policy._town_restock_waiting_for, ())
        self.assertEqual(policy._town_restock_rechecked, set())

    def test_mismatched_entering_visit_releases_for_temple_route(self):
        """R4 revert proof: without required-stop-changed the approach returns None."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_blocked_reason = None
        policy._town_errand_plan = TownErrandPlan(
            [STORE_TEMPLE],
            need_categories={STORE_TEMPLE: ("recall",)},
            blocked_this_visit=[0],
        )
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", 0,
            phase=StoreVisitPhase.ENTERING,
        )
        policy._release_invalid_store_visit(snapshot)
        step = policy._shopping_approach_step(snapshot, STORE_TEMPLE)

        self.assertIsNotNone(step)
        self.assertEqual(policy._shopping_approach_store_type, STORE_TEMPLE)
        self.assertEqual(policy._store_visit.store_type, STORE_TEMPLE)
        self.assertEqual(
            policy._store_visit_last_closed.outcome, "required-stop-changed"
        )

    def test_posted_visit_survives_required_stop_change(self):
        """A posted operation is authoritative: the release must not close it."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_blocked_reason = None
        policy._town_errand_plan = TownErrandPlan(
            [STORE_TEMPLE],
            need_categories={STORE_TEMPLE: ("recall",)},
            blocked_this_visit=[0],
        )
        posted = StoreVisit(
            "town-errand", "shopping", 0,
            phase=StoreVisitPhase.ENTERING,
        )
        posted.operation_posted = True
        policy._store_visit = posted
        policy._release_invalid_store_visit(snapshot)
        self.assertIs(policy._store_visit, posted)

        foreign = StoreVisit(
            "home-errand", "deposit", 0,
            phase=StoreVisitPhase.ENTERING,
        )
        policy._store_visit = foreign
        policy._release_invalid_store_visit(snapshot)
        self.assertIs(policy._store_visit, foreign)

    def test_periodic_save_preserves_staged_home_entry_post(self):
        """D1 pin: a periodic save cannot replace the composed Home entry."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy.last_reason = "calibration:atomic-restore-withdraw"
        policy._periodic_save_requested = True
        policy._store_entry_wait_owner = 7
        policy._store_entry_posted_owner = None
        posted = StoreVisit(
            "equipment-transaction", "equipment-work", 7,
            opened_sequence=617,
        )
        posted.operation_posted = True
        posted.operation_released = False
        posted.posted_sequence = 618
        policy._store_visit = posted

        key = policy._periodic_game_save_key(snapshot, "5")

        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason, "calibration:atomic-restore-withdraw")
        self.assertTrue(policy._periodic_save_requested)

    def test_unobserved_posted_visit_releases_within_decision_bound(self):
        """D2 pin: an entry post with no observed page cannot retain the router."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_blocked_reason = None
        posted = StoreVisit(
            "town-errand", "shopping", 7,
            opened_sequence=618,
            posted_sequence=618,
        )
        posted.operation_posted = True
        policy._store_visit = posted
        policy._decision_sequence = 618

        for _ in range(STORE_STUCK_LIMIT):
            policy._decision_sequence += 1
            policy._release_invalid_store_visit(snapshot)
            if policy._store_visit is None:
                break

        self.assertIsNone(policy._store_visit)
        self.assertEqual(
            policy._store_visit_last_closed.outcome,
            "posted-entry-unobserved",
        )
        self.assertIsNotNone(
            policy._shopping_approach_step(snapshot, STORE_ALCHEMIST)
        )

    def test_restock_wait_has_cumulative_visible_terminal(self):
        """D3 pin: repeated re-arms consume a finite game-turn allowance."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._food_ready = lambda _snapshot: True
        policy._town_restock_wait_until = snapshot.turn + STORE_RESTOCK_WAIT_TURNS
        policy._town_restock_waiting_for = (STORE_TEMPLE, STORE_ALCHEMIST)
        policy._town_restock_rechecked.clear()
        policy._town_restock_waited_turns = 0
        policy._town_restock_last_wait_turn = None
        cap = STORE_RESTOCK_WAIT_TURNS * 4
        turn = snapshot.turn
        rests = 0

        while policy._town_blocked_reason != "restock-wait-exhausted":
            current = replace(snapshot, turn=turn)
            key = policy._recall_restock_key(current)
            if key == RESTOCK_WAIT_MACRO:
                rests += 1
                turn += STORE_RESTOCK_WAIT_TURNS
            else:
                policy._town_restock_wait_until = None
            self.assertLessEqual(rests, 4)

        self.assertLessEqual(policy._town_restock_waited_turns, cap)
        self.assertEqual(policy.last_reason, "town:blocked:restock-wait-exhausted")
        self.assertNotIn("town:wait-restock", TOWN_CYCLE_IGNORED_REASONS)
        policy._release_stale_town_block(snapshot)
        self.assertEqual(policy._town_blocked_reason, "restock-wait-exhausted")

    def test_productive_gap_charges_only_one_restock_rest(self):
        """A3a: unrelated elapsed turns cannot consume the cumulative cap."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        policy._town_restock_waited_turns = 0
        policy._town_restock_last_wait_turn = snapshot.turn
        policy._town_restock_wait_until = None
        policy._town_supplier_stock = {}
        much_later = replace(snapshot, turn=snapshot.turn + STORE_RESTOCK_WAIT_TURNS * 20)

        policy._retry_after_store_restock(
            much_later, (STORE_TEMPLE, STORE_ALCHEMIST)
        )

        self.assertEqual(policy._town_restock_waited_turns, STORE_RESTOCK_WAIT_TURNS)
        self.assertNotEqual(policy._town_blocked_reason, "restock-wait-exhausted")

    def test_fresh_policy_persists_restock_wait_exhausted(self):
        """A3b: constructor persistence protects the cumulative terminal."""
        policy = HengbotPolicy()
        self.assertIn(
            "restock-wait-exhausted",
            policy._cross_decision_latches[
                "_town_blocked_reason"
            ].permanent_values,
        )

    def test_recall_entry_invariant_stays_below_required_return(self):
        """Pin vacuity: the incident checkpoint has zero recall and cannot depart."""
        path = self.FIXTURE.parent / "recall-store-unreachable-checkpoints.jsonl.gz"
        _row, policy_blob, snapshot_blob = checkpoint_row(path, 220)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        recall_count = policy._count_recall_scrolls(snapshot)
        required_return = policy._recall_required_target(snapshot)

        self.assertLess(recall_count, required_return)
        self.assertFalse(
            policy._dungeon_entry_allowed(
                snapshot, via_recall=False, destination_depth=1
            )
        )


if __name__ == "__main__":
    unittest.main()
