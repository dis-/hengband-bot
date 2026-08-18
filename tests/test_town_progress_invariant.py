from dataclasses import replace
from pathlib import Path
from random import Random
from types import SimpleNamespace
import unittest

from hengbot.model import STORE_MAGIC, TVAL_WAND, StoreItem, StoreState
from hengbot.policy import (
    FOOD_TYPE_MANA,
    HengbotPolicy,
    ProcurementHomeGate,
    StoreVisit,
    WAIT_KEY,
)
from trajectory_harness import checkpoint_row, restore_incident_checkpoint


class TownProgressInvariantTest(unittest.TestCase):
    FIXTURE = (
        Path(__file__).parent
        / "fixtures"
        / "device-purchase-preempted-checkpoint.jsonl.gz"
    )

    def _case(self, price=1083, *, on_door=True, food_type=None):
        _row, policy_blob, snapshot_blob = checkpoint_row(self.FIXTURE, 253)
        policy, snapshot = restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )
        wand = StoreItem(
            "e", "Sleep Monster wand (31 charges)", 3, TVAL_WAND, 0,
            price, charges=31,
        )
        store = StoreState(STORE_MAGIC, [wand], page_top=0)
        position = snapshot.player.position
        player = snapshot.player
        if food_type is not None:
            player = replace(player, food_type=food_type, food_state="normal")
        snapshot = replace(
            snapshot, player=player,
            grids={
                **snapshot.grids,
                position: replace(snapshot.grids[position], store_number=(
                    STORE_MAGIC if on_door else -1
                )),
            },
        )
        if not on_door:
            entrance = min(
                (
                    grid for grid in snapshot.grids.values()
                    if grid.position.distance_to(position) >= 3
                    and grid.passable
                ),
                key=lambda grid: grid.position.distance_to(position),
            )
            snapshot = replace(snapshot, grids={
                **snapshot.grids,
                entrance.position: replace(
                    entrance, store_number=STORE_MAGIC
                ),
            })
        policy._purchase_has_fresh_home_absence = (
            lambda _snapshot, _item: ProcurementHomeGate.ALLOW_PURCHASE
        )
        policy._shopping_approach_store_type = STORE_MAGIC
        policy._shop_observation = (store, policy._decision_sequence)
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", STORE_MAGIC
        )
        policy._town_store_attempted.pop(STORE_MAGIC, None)
        policy._town_blocked_reason = "repetition"
        policy._town_cycle_pending = True
        return policy, snapshot, store

    def test_whole_approach_enter_compose_sequence_uses_one_seam(self):
        policy, snapshot, store = self._case()
        step = snapshot.player.position
        policy._shop_observation = None
        policy._town_supplier_stock = {STORE_MAGIC: store}
        policy._next_required_store_type = lambda _snapshot: STORE_MAGIC
        policy._shopping_approach_step = (
            lambda _snapshot, _store_type=None: step
        )
        policy._shopping_approach_key = (
            lambda _snapshot, _step, _reason: "6"
        )

        policy.last_reason = "town:blocked:repetition"
        self.assertEqual(
            policy._town_procurement_decision(snapshot, WAIT_KEY), "6"
        )
        self.assertIn("town-progress-invariant:defect", policy.last_reason)

        inside = replace(snapshot, store=store)
        policy._shop_observation = (store, policy._decision_sequence)
        policy.last_reason = "shop:observe-and-leave"
        self.assertEqual(policy._town_procurement_decision(inside, "\x1b"), "\x1b")
        self.assertEqual(
            policy.last_reason,
            "town-progress-invariant:continue-observed-shop",
        )

        policy._shopping_approach_step = HengbotPolicy._shopping_approach_step.__get__(
            policy, HengbotPolicy
        )
        policy._shopping_approach_key = HengbotPolicy._shopping_approach_key.__get__(
            policy, HengbotPolicy
        )
        policy.last_reason = "town:blocked:repetition"
        self.assertEqual(
            policy._town_procurement_decision(snapshot, WAIT_KEY), WAIT_KEY
        )
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertIn("=>shop:one-shot-buy", policy.last_reason)

    def test_closed_allow_set_members_are_individually_pinned(self):
        policy, snapshot, _store = self._case()
        cases = (
            ("emergency:heal", snapshot, "emergency-lethal-danger"),
            (
                "survival:mana-absorb",
                replace(
                    snapshot,
                    player=replace(snapshot.player, food_state="weak"),
                ),
                "weak-fainting-survival-absorb",
            ),
            (
                "town:repetition-depart:recall",
                snapshot,
                "recall-entry-invariant",
            ),
            (
                "town:blocked:repetition",
                replace(
                    snapshot,
                    visible_monsters=[SimpleNamespace(distance=2)],
                ),
                "nearby-threat-defer",
            ),
        )
        for reason, candidate_snapshot, member in cases:
            with self.subTest(member=member):
                policy.last_reason = reason
                self.assertIn(
                    member,
                    policy._town_progress_allow_members(candidate_snapshot),
                )
        policy.last_reason = "town:blocked:repetition"
        policy._fundraising_kit_reserve = lambda _snapshot: snapshot.player.gold
        self.assertIn(
            "reserve-already-satisfied",
            policy._town_progress_allow_members(snapshot),
        )
        self.assertEqual(
            policy.TOWN_PROGRESS_ALLOW_SET,
            {
                "emergency-lethal-danger",
                "weak-fainting-survival-absorb",
                "recall-entry-invariant",
                "nearby-threat-defer",
                "reserve-already-satisfied",
            },
        )

    def test_derived_randomized_result_invariant_generalized_sweep(self):
        rng = Random(5488)
        reasons = (
            "town:blocked:injected-owner", "town:idle-wait",
            "procurement:defer", "town:hold", "await-restock",
        )
        for index in range(40):
            price = rng.randint(1, 20000)
            far_away = bool(index % 2)
            food_type = FOOD_TYPE_MANA if index % 3 == 0 else 0
            policy, snapshot, store = self._case(
                price, on_door=not far_away, food_type=food_type,
            )
            policy._town_supplier_stock = {STORE_MAGIC: store}
            if far_away:
                policy._shop_observation = None
            reserve = policy._fundraising_kit_reserve(snapshot)
            affordable = price <= snapshot.player.gold - reserve
            wanted = policy._next_purchase_unreserved(
                replace(snapshot, store=store)
            )
            composable = affordable and wanted is not None
            reason = reasons[index % len(reasons)]
            def injected_terminal(_snapshot):
                policy.last_reason = reason
                return WAIT_KEY
            policy._choose_key_with_latch_capture = injected_terminal
            key = policy.choose_key(snapshot)
            if composable:
                self.assertTrue(
                    policy._store_visit.operation_posted
                    or policy._town_result_makes_progress(snapshot, key),
                    (index, reason, far_away, food_type, key,
                     policy.last_reason, policy._town_progress_invariant_defect),
                )
                self.assertEqual(
                    policy._town_progress_invariant_defect["marker"],
                    "TOWN_PROGRESS_INVARIANT_DEFECT",
                )
            else:
                self.assertFalse(policy._store_visit.operation_posted)
                self.assertEqual(policy.last_reason, reason)

    def test_emit_only_phase_is_silent_for_legitimate_results(self):
        policy, snapshot, store = self._case(
            price=999999, on_door=False
        )
        policy._town_supplier_stock = {STORE_MAGIC: store}
        for reason, key in (
            ("town:idle-wait", WAIT_KEY),
            ("procurement:defer", WAIT_KEY),
            ("ordinary-action", "6"),
        ):
            with self.subTest(reason=reason):
                policy._town_progress_invariant_defect = {}
                policy.last_reason = reason
                self.assertEqual(
                    policy._town_procurement_decision(
                        snapshot, key, enforce=False
                    ),
                    key,
                )
                self.assertEqual(policy._town_progress_invariant_defect, {})

    def test_emit_only_phase_reports_without_overriding(self):
        policy, snapshot, store = self._case(on_door=False)
        policy._town_supplier_stock = {STORE_MAGIC: store}
        policy._shop_observation = None
        policy.last_reason = "town:idle-wait"
        self.assertEqual(
            policy._town_procurement_decision(
                snapshot, WAIT_KEY, enforce=False
            ),
            WAIT_KEY,
        )
        self.assertEqual(
            policy._town_progress_invariant_defect["marker"],
            "TOWN_PROGRESS_INVARIANT_DEFECT",
        )


if __name__ == "__main__":
    unittest.main()
