"""DECLARED CONSTRUCTED R10 shapes; decisions do not supply historical boards.

Use the installed Outpost map as prior navigation knowledge, never a copy.
"""
import tests  # noqa: F401

from dataclasses import replace
from pathlib import Path
import unittest

from hengbot import cli
from hengbot.model import (
    Snapshot, StoreState, Position, STORE_MAGIC, STORE_ALCHEMIST,
    TVAL_STAFF, SV_STAFF_IDENTIFY, PLAYER_CLASS_WARRIOR,
    TVAL_LITE, SV_LITE_LANTERN,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownErrandPlan, StoreVisit, StoreVisitPhase
from hengbot.town_maps import parse_town_map
from hengbot.town_arbiter import _new_town_turn_arbiter
from policy_fixtures import grid, player, store_item, item


class MagicContinuationTest(unittest.TestCase):
    def scene(self, *, verified=False, price=888, stock=True):
        town_map = parse_town_map(Path('C:/hengband/lib/edit/towns/01_Outpost_Full.txt'))
        magic = town_map.store_position(STORE_MAGIC)
        self.assertEqual(magic, Position(38, 106))
        self.assertEqual(town_map.store_position(STORE_ALCHEMIST), Position(37, 91))
        ware = store_item('m', TVAL_STAFF, SV_STAFF_IDENTIFY, count=3,
                          charges=19, price=price, name='Staff of Identify')
        snapshot = Snapshot(
            player(magic.y, magic.x, level=45, gold=9869,
                   class_id=PLAYER_CLASS_WARRIOR),
            {pos: replace(grid(pos.y, pos.x), store_number=store)
             for store, pos in town_map.stores.items()}, [],
            width=town_map.width, height=town_map.height, turn=16594608,
            floor_key=(0, 0, 0), town_flag=True, town_id=1,
            equipment=[item('light', TVAL_LITE, SV_LITE_LANTERN,
                            is_equipment=True, fuel=12000)],
            store=StoreState(STORE_MAGIC, [ware] if stock else [], page_top=0),
        )
        policy = HengbotPolicy(town_map=town_map)
        policy._floor_key = snapshot.floor_key
        policy._deepest_level = 45
        policy.consume_home_knowledge(())
        policy._town_errand_plan = TownErrandPlan(
            [STORE_MAGIC, STORE_ALCHEMIST],
            need_categories={STORE_MAGIC: ('identify-staff',),
                             STORE_ALCHEMIST: ('identification-full',)},
        )
        policy._store_visit = StoreVisit(
            'town-errand', 'shopping', STORE_MAGIC,
            phase=StoreVisitPhase.ENTERING, opened_sequence=18497,
            goal=magic,
        )
        policy._in_store_ops_enabled = True
        policy.observe_store_screen(verified)
        return policy, snapshot

    def test_constructed_3358_verified_page_buys_without_supplier_diversion(self):
        policy, snapshot = self.scene(verified=True)
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ('pm1\r\r', 'shop:in-store-buy'))

    def test_constructed_3358_cleanup_composes_from_its_saved_page(self):
        policy, snapshot = self.scene()
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason),
                         ('\x1b', 'town-progress-invariant:continue-observed-shop'))
        self.assertIsNotNone(policy._shop_observation)
        outside = replace(snapshot, store=None, turn=snapshot.turn + 1)
        key = policy.choose_key(outside)
        self.assertEqual((key, policy.last_reason), ('5', 'shop:one-shot-buy'))
        self.assertEqual(policy._store_visit.operation_key, 'pm1\r\r\x1b')

    def test_constructed_3361_displaced_shelf_resumes_same_magic_visit(self):
        policy, snapshot = self.scene()
        self.assertEqual(policy.choose_key(snapshot), '\x1b')
        visit = policy._store_visit
        observation = policy._shop_observation
        alchemist = Position(37, 91)
        outside = replace(snapshot, store=None, turn=snapshot.turn + 1,
                          player=replace(snapshot.player, position=alchemist))
        key = policy.choose_key(outside)
        self.assertEqual((key, policy.last_reason), ('\x1b`n&.', 'shop:travel'))
        self.assertIs(policy._store_visit, visit)
        self.assertIs(policy._shop_observation, observation)
        self.assertEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        self.assertFalse(policy._town_turn_arbiter.retirement_pending)
        arrived = replace(outside, player=snapshot.player, turn=outside.turn + 1)
        self.assertEqual((policy.choose_key(arrived), policy.last_reason),
                         ('5', 'shop:one-shot-buy'))
        self.assertIs(policy._store_visit, visit)
        self.assertEqual(visit.operation_key, 'pm1\r\r\x1b')

    def test_detector_cannot_offer_competing_supplier_while_magic_is_composable(self):
        policy, snapshot = self.scene()
        policy.choose_key(snapshot)
        outside = replace(snapshot, store=None, turn=snapshot.turn + 1)
        visit = policy._store_visit
        observation = policy._shop_observation
        self.assertIsNone(policy._shopping_approach_step(
            outside, STORE_ALCHEMIST, router_plan_stop=True))
        self.assertIs(policy._store_visit, visit)
        self.assertIs(policy._shop_observation, observation)
        self.assertEqual((policy.choose_key(outside), policy.last_reason),
                         ('5', 'shop:one-shot-buy'))

    def test_absent_and_unaffordable_shelves_do_not_bind_or_buy(self):
        for kwargs in ({'stock': False}, {'price': 100000}):
            with self.subTest(kwargs=kwargs):
                policy, snapshot = self.scene(verified=True, **kwargs)
                self.assertFalse(policy.choose_key(snapshot).startswith('p'))
                outside = replace(snapshot, store=None, turn=snapshot.turn + 1)
                self.assertFalse(policy._can_resume_magic_shelf(outside))
                self.assertIsNone(policy._store_buy_inflight)

    def test_matching_acquisition_credits_once_and_unrelated_gold_pack_never_credit(self):
        for matched in (False, True):
            with self.subTest(matched=matched):
                policy, snapshot = self.scene(verified=True)
                self.assertEqual(policy.choose_key(snapshot), 'pm1\r\r')
                visit = policy._store_visit
                cli._observe_owner_retired_progress(policy, snapshot, 'pm1\r\r')
                policy._owner_retired_no_progress_count = 2
                acquired = item('a', TVAL_STAFF, SV_STAFF_IDENTIFY,
                                charges=19 if matched else 2,
                                name='Staff of Identify (19 charges)')
                reply = replace(snapshot, turn=snapshot.turn + 1,
                                inventory=[acquired],
                                player=replace(snapshot.player, gold=8981))
                key = policy.choose_key(reply)
                self.assertEqual(bool(policy._town_visit_purchases), matched)
                self.assertEqual(sum(policy._town_visit_purchase_quantities.values()),
                                 1 if matched else 0)
                self.assertEqual(getattr(policy, '_magic_staff_buy_receipt', None)
                                 is not None, matched)
                cli._observe_owner_retired_progress(policy, reply, key, visit)
                self.assertEqual(policy._owner_retired_no_progress_count,
                                 0 if matched else 2)
                policy._owner_retired_no_progress_count = 1
                policy._decision_sequence += 1
                cli._observe_owner_retired_progress(policy, reply, key, visit)
                self.assertEqual(policy._owner_retired_no_progress_count, 1)

    def test_retained_route_still_retires_after_eight_unsuccessful_decisions(self):
        policy, snapshot = self.scene()
        policy.choose_key(snapshot)
        outside = replace(snapshot, store=None,
                          player=replace(snapshot.player, position=Position(37, 91)))
        visit = policy._store_visit
        self.assertEqual(policy.choose_key(replace(outside, turn=snapshot.turn + 1)),
                         '\x1b`n&.')
        arbiter = policy._town_turn_arbiter
        vector = arbiter._vector_by_owner['store-router']
        # Isolate the existing accounting bound after a real route selection.
        # These eight observations deliberately prove no further route progress;
        # they are not a sequential replay of unapplied movement commands.
        for attempt in range(1, 9):
            arbiter.observe(in_town=True, reason='shop:travel', progress_vector=vector)
            self.assertIs(policy._store_visit, visit)
            telemetry = arbiter.telemetry
            self.assertEqual(telemetry['budget_remaining_estimate'], 8 - attempt)
            self.assertEqual(telemetry['would_retire'], attempt == 8)

    def test_buy_confirmation_expires_at_eight_without_target_receipt(self):
        policy, snapshot = self.scene()
        policy.choose_key(snapshot)
        self.assertEqual(policy.choose_key(replace(snapshot, store=None,
                                                  turn=snapshot.turn + 1)), '5')
        self.assertEqual(policy.choose_key(replace(snapshot, turn=snapshot.turn + 2)),
                         'pm1\r\r\x1b')
        for attempt in range(1, 9):
            policy.choose_key(replace(snapshot, store=None,
                                      turn=snapshot.turn + attempt + 2))
            watch = policy._store_buy_inflight
            if attempt < 8:
                self.assertIsNotNone(watch)
                self.assertEqual(watch[4], attempt)
            else:
                self.assertIsNone(watch)
        self.assertIsNone(getattr(policy, '_magic_staff_buy_receipt', None))
        self.assertFalse(policy._town_visit_purchases)

    def test_unresolved_detector_routing_still_retires_at_two(self):
        arbiter = _new_town_turn_arbiter()
        arbiter.observe(reason='town-progress-invariant:approach', progress_vector=('unresolved',), in_town=True)
        arbiter.observe(reason='shop:travel', progress_vector=('other',), in_town=True)
        arbiter.observe(reason='town-progress-invariant:approach', progress_vector=('unresolved',), in_town=True)
        self.assertTrue(arbiter.telemetry['would_retire'])
        diagnostic = arbiter._retirement_diagnostic
        self.assertEqual(diagnostic['recurrence_count'], 2)
        self.assertEqual(diagnostic['recurrence_limit'], 2)
        self.assertEqual(diagnostic['trigger_category'], 'recurrence')

    def test_fresh_process_has_no_magic_shelf_or_receipt(self):
        policy, snapshot = self.scene()
        policy.choose_key(snapshot)
        fresh = HengbotPolicy()
        self.assertIsNone(fresh._shop_observation)
        self.assertIsNone(getattr(fresh, '_magic_staff_buy_watch', None))
        self.assertIsNone(getattr(fresh, '_magic_staff_buy_receipt', None))

    def test_enforced_ownership_keeps_magic_ahead_of_projected_next_stop(self):
        policy, snapshot = self.scene()
        policy._town_claim_bar_enforced = True
        self.assertEqual((policy.choose_key(snapshot), policy.last_reason),
                         ('\x1b', 'town-progress-invariant:continue-observed-shop'))
        visit = policy._store_visit
        outside = replace(snapshot, store=None, turn=snapshot.turn + 1,
                          player=replace(snapshot.player, position=Position(37, 91)))
        self.assertEqual((policy.choose_key(outside), policy.last_reason),
                         ('\x1b`n&.', 'shop:travel'))
        self.assertIs(policy._store_visit, visit)
        self.assertIsNone(policy.decision_claim['violation'])

    def test_genuine_posted_operation_context_violation_still_stops(self):
        policy, snapshot = self.scene(verified=True)
        policy._town_claim_bar_enforced = True
        self.assertEqual(policy.choose_key(snapshot), 'pm1\r\r')
        outside = replace(snapshot, store=None, turn=snapshot.turn + 1,
                          player=replace(snapshot.player, position=Position(37, 91)))
        self.assertIsNone(policy.choose_key(outside))
        self.assertEqual(policy.last_reason, 'ownership:declaration-stale:shop-buy')
        self.assertTrue(cli._policy_final_stop_required(policy))

    def test_prompt_owner_recovery_keeps_matching_staff_confirmation(self):
        policy, snapshot = self.scene(verified=True)
        self.assertEqual(policy.choose_key(snapshot), 'pm1\r\r')
        policy._decision_sequence += 1
        policy.refuse_key_posting('shop:leave', '\x1b')
        reply = replace(snapshot, turn=snapshot.turn + 1,
                        inventory=[item('a', TVAL_STAFF, SV_STAFF_IDENTIFY,
                                        charges=19, name='Staff of Identify (19 charges)')])
        policy.choose_key(reply)
        self.assertIsNotNone(policy._magic_staff_buy_receipt)

    def test_uncomposable_home_first_magic_shelf_keeps_its_concrete_refusal(self):
        policy, snapshot = self.scene()
        policy._home_knowledge_current = False
        policy.choose_key(snapshot)
        outside = replace(snapshot, store=None, turn=snapshot.turn + 1)
        self.assertFalse(policy._can_resume_magic_shelf(outside))
        self.assertIsNone(policy._atomic_shop_transaction_key(outside))
        self.assertEqual(policy._shop_selector_diagnostics['composition_refusal'],
                         'shop:home-first-yields-to-current-visit')
        self.assertIsNone(policy._shop_observation)

    def test_gold_only_and_unchanged_matching_staff_do_not_confirm(self):
        policy, snapshot = self.scene(verified=True)
        carried = item('a', TVAL_STAFF, SV_STAFF_IDENTIFY, charges=19,
                       name='Staff of Identify (19 charges)')
        snapshot = replace(snapshot, inventory=[carried])
        self.assertEqual(policy.choose_key(snapshot), 'pm1\r\r')
        reply = replace(snapshot, turn=snapshot.turn + 1,
                        player=replace(snapshot.player, gold=8981))
        policy.choose_key(reply)
        self.assertFalse(policy._town_visit_purchases)
        self.assertIsNone(getattr(policy, '_magic_staff_buy_receipt', None))


if __name__ == '__main__':
    unittest.main()
