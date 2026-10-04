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
)


class ItemReservationTest(unittest.TestCase):
    def baseline(self, name):
        """Exact selector source extracted from the task's base 5cd05e8e."""
        import hengbot.policy_home as module
        namespace = dict(vars(module))
        source = (Path(__file__).parent / ('fixtures/s33slice-before-' + name + '.py.txt')).read_text(encoding='utf8')
        exec(compile(source, '<5cd05e8e:' + name + '>', 'exec'), namespace)
        return namespace[name]

    def scene(self, enforced=False):
        raw = json.loads(gzip.decompress((Path(__file__).parent /
            'fixtures/s33slice-weight-board.json.gz').read_bytes()))
        board = parse_snapshot(raw)
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = enforced
        target = next(item for item in board.inventory if item.slot == 'q')
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
            with patch.object(policy, '_retention_reservation', return_value=0), \
                    patch.object(policy, '_disposal_protected_by_identification', return_value=False), \
                    patch.object(policy, '_home_full_relief_key', return_value='retry') as retry, \
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

    def test_owned_transaction_and_unreserved_item_are_allowed(self):
        policy, board, target = self.scene()
        self.assertTrue(item_available(policy, board, target, 'equipment-txn', 'deposit'))
        self.assertTrue(item_available(policy, board, board.inventory[0], 'home-visit', 'deposit'))

    def test_all_named_sinks_consult_same_predicate(self):
        for sink in ('sell', 'deposit', 'withdraw', 'destroy', 'wield', 'weight-deposit', 'home-full-sale'):
            policy, board, target = self.scene()
            self.assertFalse(item_available(policy, board, target, 'foreign', sink))

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

    def test_ambiguous_identical_reserved_stacks_are_typed(self):
        policy, board, target = self.scene()
        board = replace(board, inventory=(*board.inventory, replace(target, slot='z')))
        verdict = item_reserved_by_other(policy, board, target, ('foreign', 'sell'))
        self.assertTrue(verdict.ambiguous)
