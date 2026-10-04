"""Recorded board, reconstructed session: backup names contain replacement bytes.

18:33:03 sent dqdmdi4\rdh2\r ESC. Reconstruct a planned deposit of
the recorded q item to exercise the stolen-item selector seam. The later
missing-item ID 5a23aaab8fc64246 is absent from this supplied board; this
is not a reconstruction of that absent checkpoint or a full replay.
"""
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from dataclasses import replace
import tests  # noqa: F401
from hengbot.model import parse_snapshot, StoreState, STORE_WEAPON
from hengbot.policy import HengbotPolicy
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.item_reservation import (
    item_reserved_by_other, item_available, reservation_decision, reservation_shadow,
    reserved_item_command,
)


class ItemReservationTest(unittest.TestCase):
    def baseline(self, name):
        """Exact selector source extracted from the task's base 5cd05e8e."""
        import hengbot.policy_home as module
        namespace = dict(vars(module))
        source = (Path(__file__).parent / ('fixtures/s33slice-before-' + name + '.py.txt')).read_text(encoding='utf8')
        exec(compile(source, '<5cd05e8e:' + name + '>', 'exec'), namespace)
        return namespace[name]

    def scene(self, enforced=False, slot='q'):
        raw = json.loads(gzip.decompress((Path(__file__).parent /
            'fixtures/s33slice-weight-board.json.gz').read_bytes()))
        board = parse_snapshot(raw)
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = enforced
        target = next(item for item in board.inventory if item.slot == slot)
        action = EquipmentTransaction('home_prepare', 'deposit',
            'pack:' + equipment_identity(target) + ':0', None,
            equipment_identity(target), equipment_move_identity(target))
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0), physical_context='home')
        return policy, board, target

    def test_recorded_weight_selector_skips_planned_deposit_off_and_on(self):
        for enforced in (False, True):
            policy, board, target = self.scene(enforced)
            # Historical candidate eligibility is pinned on this board.
            self.assertIn(target, self.baseline('_weight_deposit_candidates')(policy, board))
            self.assertNotIn(target, policy._weight_deposit_candidates(board))
            self.assertEqual(policy._equipment_transaction_session.index, 0)

    def test_home_relief_sale_cannot_take_session_planned_deposit(self):
        for enforced in (False, True):
            policy, board, target = self.scene(enforced)
            board = replace(board, store=StoreState(STORE_WEAPON, []))
            signature = policy._item_signature(target)
            policy._home_full_relief = {
                "deposits": (), "remaining": 1, "sale": (signature, STORE_WEAPON, 0),
                "withdrawn": True, "town": policy._effective_town_id(board),
            }
            from hengbot.policy_home import HomeMixin
            with patch.object(policy, '_home_full_relief_key', return_value='retry') as retry, \
                    patch.object(policy, '_store_sell_key', return_value='sale') as sale:
                self.assertEqual(self.baseline('_home_full_relief_key')(policy, board), 'sale')
                sale.assert_called_once()
                sale.reset_mock()
                key = HomeMixin._home_full_relief_key(policy, board)
                sale.assert_not_called()
                if enforced:
                    self.assertIsNone(key)
                    self.assertEqual(policy.last_reason,
                        'ownership:item-reserved:home-full-sale:equipment-txn')
                else:
                    self.assertEqual(key, 'retry')
                    self.assertIsNone(policy._home_full_relief['sale'])
                    retry.assert_called_once_with(board)
            self.assertFalse(item_available(policy, board, target, 'home-visit', 'home-full-sale'))
            self.assertEqual(item_reserved_by_other(policy, board, target,
                ('home-visit', 'home-full-sale')).owner, 'equipment-txn')

    def test_recorded_staff_session_ownership_protects_non_equipment(self):
        for enforced in (False, True):
            policy, board, target = self.scene(enforced, 'm')
            self.assertFalse(target.is_equipment)
            self.assertFalse(self.baseline('_equipment_transaction_deposit_owns_item')(policy, target))
            self.assertTrue(policy._equipment_transaction_deposit_owns_item(target))
            self.assertFalse(item_available(policy, board, target, 'home-visit', 'deposit'))
            self.assertEqual(item_reserved_by_other(policy, board, target,
                ('home-visit', 'weight-deposit')).owner, 'equipment-txn')

    def test_owned_transaction_and_unreserved_item_are_allowed(self):
        policy, board, target = self.scene()
        self.assertTrue(item_available(policy, board, target, 'equipment-txn', 'deposit'))
        self.assertTrue(item_available(policy, board, board.inventory[0], 'home-visit', 'deposit'))

    def test_all_named_sinks_consult_same_predicate(self):
        for sink in ('sell', 'deposit', 'withdraw', 'destroy', 'wield', 'weight-deposit', 'home-full-sale',
                     'read', 'quaff', 'eat', 'staff', 'wand', 'rod', 'fire', 'throw', 'refill'):
            policy, board, target = self.scene()
            self.assertFalse(item_available(policy, board, target, 'foreign', sink))

    def test_consumption_serializer_preserves_actual_key_constants_and_tails(self):
        from hengbot import policy_constants as keys
        from hengbot.item_reservation import item_command, reservation_verdict
        policy, board, target = self.scene()
        policy._equipment_transaction_session = None
        for kind, constant in (('read', keys.READ_KEY), ('quaff', keys.QUAFF_KEY),
                               ('eat', keys.EAT_KEY), ('staff', keys.USE_STAFF_KEY),
                               ('wand', keys.AIM_WAND_KEY), ('rod', keys.ZAP_ROD_KEY),
                               ('fire', keys.FIRE_KEY), ('throw', keys.THROW_KEY),
                               ('refill', keys.REFILL_KEY)):
            with self.subTest(kind=kind):
                verdict = reservation_verdict(policy, board, target, 'survival', kind)
                self.assertEqual(item_command(kind, target, verdict), constant + target.slot)
                self.assertEqual(reserved_item_command(policy, board, kind, target, suffix= '*t5\x1b'),
                                 constant + target.slot + '*t5\x1b')

    def test_town_consumption_cannot_steal_planned_deposit(self):
        for kind in ('read', 'quaff', 'eat', 'staff', 'wand', 'rod', 'fire', 'throw', 'refill'):
            for enforced in (False, True):
                policy, board, target = self.scene(enforced)
                policy.last_reason = 'survival:hunger'
                self.assertIsNone(reserved_item_command(policy, board, kind, target))

    def test_dungeon_consumption_preserves_keys_for_unreserved_item(self):
        policy, board, target = self.scene(True)
        policy._equipment_transaction_session = None
        board = replace(board, store=None, floor_key=(1, 5, 0), town_flag=False)
        self.assertFalse(board.in_town)
        policy.last_reason = 'combat:heal'
        self.assertEqual(reserved_item_command(policy, board, 'quaff', target), 'q' + target.slot)

    def test_consumption_cannot_borrow_a_stale_transaction_owner_reason(self):
        policy, board, staff = self.scene(True, 'm')
        policy.last_reason = 'equipment-transaction:home-prepare'
        self.assertIsNone(reserved_item_command(policy, board, 'staff', staff))

    def test_public_decision_is_terminal_on_and_shadow_skip_off(self):
        for enforced in (False, True):
            policy, board, target = self.scene(enforced)
            def producer(snapshot):
                item_available(policy, snapshot, target, 'home-visit', 'weight-deposit')
                policy.last_reason = 'home:weight-overload-deposit'
                return '5'
            with patch.object(policy, '_skill_exp_request_key', return_value=None), \
                    patch.object(policy, '_choose_key_with_latch_capture', side_effect=producer):
                key = policy.choose_key(board)
            if enforced:
                self.assertIsNone(key)
                self.assertEqual(policy.last_reason,
                    'ownership:item-reserved:weight-deposit:equipment-txn')
            else:
                self.assertIsNotNone(key)
                self.assertFalse(policy.last_reason.startswith('ownership:item-reserved:'))
            self.assertEqual(policy.decision_claim['item_reservation_shadow'][0]['would_stop'],
                'ownership:item-reserved:weight-deposit:equipment-txn')

    def test_off_predicate_exception_is_shadow_and_historical_fallback(self):
        policy, board, target = self.scene()
        @reservation_decision
        def decide(policy, board):
            with patch('hengbot.item_reservation.item_reserved_by_other', side_effect=RuntimeError('pin')):
                self.assertTrue(item_available(policy, board, target, 'home-visit', 'deposit'))
            self.assertEqual(reservation_shadow(policy)[0]['error'], 'RuntimeError')
        decide(policy, board)

    def test_on_predicate_exception_stops(self):
        policy, board, target = self.scene(True)
        with patch('hengbot.item_reservation.item_reserved_by_other', side_effect=RuntimeError('pin')):
            self.assertFalse(item_available(policy, board, target, 'home-visit', 'deposit'))
        self.assertEqual(policy.last_reason, 'ownership:item-reserved:deposit:predicate-error')

    def test_view_built_once_and_does_not_add_policy_attributes(self):
        policy, board, target = self.scene()
        attributes = set(vars(policy))
        @reservation_decision
        def decide(policy, board):
            import hengbot.item_reservation as module
            with patch.object(module, '_view', wraps=module._view) as view:
                item_available(policy, board, target, 'foreign', 'sell')
                item_available(policy, board, target, 'foreign', 'deposit')
                self.assertFalse(item_available(policy, board, replace(target, slot='z'),
                                                'foreign', 'sell'))
                self.assertEqual(view.call_count, 1)
        decide(policy, board)
        self.assertEqual(set(vars(policy)), attributes)

    def test_retry_and_atomic_reservations_derive_from_existing_state(self):
        policy, board, target = self.scene()
        policy._equipment_transaction_session = None
        signature = policy._item_signature(target)
        policy._home_full_retry_deposits = ((signature, 1, 1),)
        self.assertFalse(item_available(policy, board, target, 'shop-sell', 'sell'))
        self.assertTrue(item_available(policy, board, target, 'home-visit', 'deposit'))
        policy._home_full_retry_deposits = None
        policy._home_atomic_deposit_pending = (((signature, 1, 1),), None, board.turn, 0)
        self.assertFalse(item_available(policy, board, target, 'shop-sell', 'sell'))

    def test_unreferenced_home_catalogue_rows_are_not_evaluated(self):
        policy, board, target = self.scene()
        policy._home_knowledge_items = (replace(board.inventory[0], slot='z'),)
        @reservation_decision
        def decide(policy, board):
            import hengbot.item_reservation as module
            with patch.object(module, '_reservation_row', wraps=module._reservation_row) as row:
                item_available(policy, board, target, 'foreign', 'sell')
                item_available(policy, board, target, 'foreign', 'deposit')
                item_available(policy, board, board.inventory[0], 'home-visit', 'deposit')
                self.assertEqual(row.call_count, 2)
        decide(policy, board)

    def test_ambiguous_identical_reserved_stacks_are_typed(self):
        for enforced in (False, True):
            policy, board, target = self.scene(enforced)
            board = replace(board, inventory=(*board.inventory, replace(target, slot='z')))
            verdict = item_reserved_by_other(policy, board, target, ('foreign', 'sell'))
            self.assertTrue(verdict.ambiguous)
            @reservation_decision
            def decide(policy, board):
                self.assertFalse(item_available(policy, board, target, 'foreign', 'sell'))
                row = reservation_shadow(policy)[0]
                self.assertTrue(row['ambiguous'])
                self.assertEqual(row['would_stop'], 'ownership:item-reserved:sell:equipment-txn')
                if enforced:
                    self.assertEqual(policy.last_reason, row['would_stop'])
            decide(policy, board)

    def test_need_query_skips_foreign_items_without_poisoning_owner_handoff(self):
        from hengbot.item_reservation import reservation_query
        for enforced in (False, True):
            policy, board, target = self.scene(enforced)
            policy.last_reason = 'equipment-transaction:travel-home'
            @reservation_query
            def query():
                return item_available(policy, board, target, 'home-visit', 'weight-deposit')
            @reservation_decision
            def decide(policy, board):
                self.assertFalse(query())
                self.assertEqual(policy.last_reason, 'equipment-transaction:travel-home')
                self.assertEqual(reservation_shadow(policy)[0]['query_skip'],
                    'ownership:item-reserved:weight-deposit:equipment-txn')
                self.assertNotIn('would_stop', reservation_shadow(policy)[0])
                self.assertFalse(item_available(policy, board, target, 'home-visit', 'weight-deposit'))
                self.assertEqual(reservation_shadow(policy)[1]['would_stop'],
                    'ownership:item-reserved:weight-deposit:equipment-txn')
            decide(policy, board)
