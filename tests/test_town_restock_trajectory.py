from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import STORE_ALCHEMIST, STORE_TEMPLE, StoreState
from hengbot.policy import HengbotPolicy
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
        policy._town_store_attempted.pop(STORE_TEMPLE, None)
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
