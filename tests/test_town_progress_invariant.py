from dataclasses import replace
from pathlib import Path
from random import Random
from types import SimpleNamespace
import unittest

from hengbot.model import (
    STORE_ALCHEMIST,
    STORE_MAGIC,
    TVAL_WAND,
    StoreItem,
    StoreState,
)
from hengbot.policy import (
    FOOD_TYPE_MANA,
    DIRECTION_KEYS,
    HengbotPolicy,
    LEAVE_STORE_KEY,
    ProcurementHomeGate,
    RESTOCK_WAIT_MACRO,
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
        # The searched live A28 geometry no longer survives in the capture
        # generations.  Restore the real decision-253 checkpoint and seed only
        # its measured incident preconditions: open-town position, remembered
        # Magic shelf, and the selected supplier.  The captured board already
        # contains the real Magic entrance at (38, 106).
        incident_position = replace(snapshot.player.position, y=36, x=104)
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=incident_position),
        )
        policy._shop_observation = None
        policy._town_supplier_stock = {STORE_MAGIC: store}
        policy._shopping_approach_store_type = STORE_MAGIC

        policy.last_reason = "town:blocked:repetition"
        approach_key = policy._town_procurement_decision(snapshot, WAIT_KEY)
        self.assertTrue(policy._town_result_makes_progress(snapshot, approach_key))
        self.assertIn("town-progress-invariant:defect", policy.last_reason)

        # Consume ordinary one-tile approach results until the real captured
        # Magic entrance is reached; no approach producer is replaced.
        while snapshot.player.position != policy._shopping_approach_goal:
            delta = next(
                delta for delta, key in DIRECTION_KEYS.items()
                if key == approach_key
            )
            position = snapshot.player.position
            snapshot = replace(snapshot, player=replace(
                snapshot.player,
                position=replace(
                    position,
                    y=position.y + delta[0],
                    x=position.x + delta[1],
                ),
            ))
            policy.last_reason = "town:blocked:repetition"
            approach_key = policy._town_procurement_decision(snapshot, WAIT_KEY)

        inside = replace(snapshot, store=store)
        policy._shop_observation = (store, policy._decision_sequence)
        policy.last_reason = "shop:observe-and-leave"
        self.assertEqual(policy._town_procurement_decision(inside, "\x1b"), "\x1b")
        self.assertEqual(
            policy.last_reason,
            "town-progress-invariant:continue-observed-shop",
        )

        policy.last_reason = "town:blocked:repetition"
        posted_key = policy._town_procurement_decision(snapshot, WAIT_KEY)
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertEqual(posted_key, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "pe3\r\r\x1b")
        self.assertIn("=>shop:one-shot-buy", policy.last_reason)

    def test_live_shaped_magic_observe_then_compose_ignores_advanced_plan(self):
        policy, snapshot, store = self._case()
        # The live 08:04:52 page was Magic at the real captured entrance
        # (38, 106).  Seed only that measured position/page onto the restored
        # decision-253 checkpoint and preserve the observation naturally.
        entrance = replace(snapshot.player.position, y=38, x=106)
        outside = replace(
            snapshot,
            player=replace(snapshot.player, position=entrance),
            grids={
                **snapshot.grids,
                entrance: replace(
                    snapshot.grids[entrance], store_number=STORE_MAGIC
                ),
            },
            store=None,
        )
        inside = replace(outside, store=store)
        policy._shop_observation = None
        policy._shopping_approach_store_type = STORE_MAGIC
        policy._town_blocked_reason = None
        policy._town_cycle_pending = False

        # Drive the real store handler: observe first, then leave.  The town
        # plan advancing to another store must not invalidate this Magic page.
        observed_key = policy.choose_key(inside)
        self.assertEqual(observed_key, "\x1b")
        self.assertEqual(
            policy.last_reason,
            "town-progress-invariant:continue-observed-shop",
        )
        self.assertEqual(policy._shop_observation[0].store_type, STORE_MAGIC)
        policy._store_visit = replace(
            policy._store_visit, store_type=STORE_ALCHEMIST
        )
        self.assertNotEqual(
            policy._shopping_approach_store_type,
            policy._shop_observation[0].store_type,
        )
        posted_key = policy._atomic_shop_transaction_key(outside)
        self.assertEqual(posted_key, WAIT_KEY)
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertEqual(policy._store_visit.operation_key, "pe3\r\r\x1b")

    def test_target_leave_is_defect_but_nonstocking_leave_can_advance(self):
        policy, snapshot, store = self._case()
        target = replace(snapshot, store=store)
        policy._shop_observation = (store, policy._decision_sequence)
        policy._store_visit = replace(
            policy._store_visit, store_type=STORE_ALCHEMIST
        )
        self.assertNotEqual(
            policy._shopping_approach_store_type,
            policy._shop_observation[0].store_type,
        )
        self.assertEqual(
            policy._atomic_shop_transaction_key(snapshot), WAIT_KEY
        )
        policy.last_reason = "shop:observe-and-leave"
        self.assertEqual(
            policy._town_procurement_decision(target, "\x1b"), "\x1b"
        )
        self.assertEqual(
            policy._town_progress_invariant_defect["winning_rung"],
            "shop:observe-and-leave",
        )

        empty = replace(store, items=[])
        nonstocking = replace(snapshot, store=empty)
        policy._town_progress_invariant_defect = {}
        policy.last_reason = "shop:observe-and-leave"
        self.assertEqual(
            policy._town_procurement_decision(nonstocking, "\x1b"), "\x1b"
        )
        self.assertEqual(policy.last_reason, "shop:observe-and-leave")
        self.assertEqual(policy._town_progress_invariant_defect, {})

    def test_saved_page_composes_after_town_plan_advances(self):
        policy, snapshot, store = self._case()
        policy._shop_observation = (store, policy._decision_sequence)
        policy._store_visit = replace(
            policy._store_visit, store_type=STORE_ALCHEMIST
        )
        self.assertNotEqual(
            policy._shopping_approach_store_type,
            policy._shop_observation[0].store_type,
        )
        key = policy._atomic_shop_transaction_key(snapshot)
        self.assertEqual(key, WAIT_KEY)
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertEqual(policy._store_visit.operation_key, "pe3\r\r\x1b")

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
        terminal_keys = (WAIT_KEY, RESTOCK_WAIT_MACRO, "l", "s", "\x1b\x1b")
        store_types = (STORE_MAGIC, STORE_ALCHEMIST)
        for index in range(40):
            price = rng.randint(1, 20000)
            far_away = bool(index % 2)
            food_type = FOOD_TYPE_MANA if index % 3 == 0 else 0
            policy, snapshot, store = self._case(
                price, on_door=not far_away, food_type=food_type,
            )
            store_type = store_types[index % len(store_types)]
            store = replace(store, store_type=store_type)
            policy._town_supplier_stock = {store_type: store}
            policy._shopping_approach_store_type = store_type
            if far_away:
                policy._shop_observation = None
            reserve = policy._fundraising_kit_reserve(snapshot)
            affordable = price <= snapshot.player.gold - reserve
            wanted = policy._next_purchase_unreserved(
                replace(snapshot, store=store)
            )
            composable = affordable and wanted is not None
            reason = reasons[index % len(reasons)]
            terminal_key = terminal_keys[index % len(terminal_keys)]
            def injected_terminal(_snapshot):
                policy.last_reason = reason
                return terminal_key
            policy._choose_key_with_latch_capture = injected_terminal
            key = policy.choose_key(snapshot)
            if composable:
                self.assertTrue(
                    policy._store_visit.operation_posted
                    or policy._town_result_makes_progress(snapshot, key),
                    (index, reason, terminal_key, store_type, far_away, food_type, key,
                     policy.last_reason, policy._town_progress_invariant_defect),
                )
                self.assertEqual(
                    policy._town_progress_invariant_defect["marker"],
                    "TOWN_PROGRESS_INVARIANT_DEFECT",
                )
            else:
                self.assertFalse(policy._store_visit.operation_posted)
                self.assertEqual(policy.last_reason, reason)

    def test_closed_key_axis_rejects_known_and_novel_noop_macros(self):
        for terminal_key in (RESTOCK_WAIT_MACRO, "l", "s", "\x1b\x1b"):
            with self.subTest(key=repr(terminal_key)):
                policy, snapshot, store = self._case(on_door=False)
                policy._town_supplier_stock = {STORE_MAGIC: store}
                policy._shop_observation = None
                def injected_terminal(_snapshot):
                    policy.last_reason = "town:wait-restock:magic"
                    return terminal_key
                policy._choose_key_with_latch_capture = injected_terminal
                key = policy.choose_key(snapshot)
                self.assertNotEqual(key, terminal_key)
                self.assertTrue(policy._town_result_makes_progress(snapshot, key))
                self.assertEqual(
                    policy._town_progress_invariant_defect["marker"],
                    "TOWN_PROGRESS_INVARIANT_DEFECT",
                )

    def test_move_reason_cannot_bless_wait_or_leave_axis(self):
        for terminal_key in (WAIT_KEY, LEAVE_STORE_KEY):
            with self.subTest(key=repr(terminal_key)):
                policy, snapshot, store = self._case(on_door=False)
                policy._town_supplier_stock = {STORE_MAGIC: store}
                policy._shop_observation = None

                def injected_terminal(_snapshot):
                    policy.last_reason = "seek-loot"
                    return terminal_key

                policy._choose_key_with_latch_capture = injected_terminal
                key = policy.choose_key(snapshot)
                self.assertNotEqual(key, terminal_key)
                self.assertIn(
                    "town-progress-invariant:defect:seek-loot",
                    policy.last_reason,
                )
                self.assertEqual(
                    policy._town_progress_invariant_defect["marker"],
                    "TOWN_PROGRESS_INVARIANT_DEFECT",
                )

    def test_seek_loot_progress_is_not_preempted_by_composable_purchase(self):
        policy, snapshot, store = self._case(on_door=False)
        policy._town_supplier_stock = {STORE_MAGIC: store}
        policy._shop_observation = None
        policy._shopping_approach_goal = None
        seek_key = next(iter(DIRECTION_KEYS.values()))

        def injected_seek_loot(_snapshot):
            policy.last_reason = "seek-loot"
            return seek_key

        policy._choose_key_with_latch_capture = injected_seek_loot
        key = policy.choose_key(snapshot)
        self.assertEqual(key, seek_key)
        self.assertEqual(policy.last_reason, "seek-loot")
        self.assertEqual(policy._town_progress_invariant_defect, {})

    def test_net_zero_goal_walk_is_still_preempted(self):
        policy, snapshot, store = self._case(on_door=False)
        policy._town_supplier_stock = {STORE_MAGIC: store}
        policy._shop_observation = None
        policy._shopping_approach_goal = None
        policy._town_progress_history().append(
            policy._town_progress_fingerprint(snapshot)
        )
        seek_key = next(iter(DIRECTION_KEYS.values()))

        def injected_cyclic_walk(_snapshot):
            policy.last_reason = "seek-loot"
            return seek_key

        policy._choose_key_with_latch_capture = injected_cyclic_walk
        key = policy.choose_key(snapshot)
        self.assertNotEqual(key, seek_key)
        self.assertIn("town-progress-invariant:defect:seek-loot", policy.last_reason)
        self.assertEqual(
            policy._town_progress_invariant_defect["marker"],
            "TOWN_PROGRESS_INVARIANT_DEFECT",
        )

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
