import unittest
from unittest.mock import patch
import tests  # noqa: F401
from tests import test_item_reservation as fixture
from hengbot.item_reservation import (
    checked_item_command, item_command, reserved_item_command, reservation_verdict,
    reservation_decision, reservation_shadow,
)


class ItemSerializationTest(unittest.TestCase):
    scene = fixture.ItemReservationTest.scene

    def test_every_command_kind_has_an_item_bound_verdict(self):
        policy, board, item = self.scene()
        policy._equipment_transaction_session = None
        cases = {'deposit': 'dq', 'sell': 'dq', 'withdraw': 'pq', 'buy': 'pq',
                 'wield': 'wq', 'takeoff': 'tq', 'inscribe': '{q',
                 'inscribe-equipped': '{/a', 'uninscribe-equipped': '}/a',
                 'destroy': '01kq'}
        for kind, expected in cases.items():
            with self.subTest(kind=kind):
                verdict = reservation_verdict(policy, board, item, 'equipment-txn', kind.split('-')[0])
                selected = (item, 'a') if kind.endswith('-equipped') else item
                self.assertEqual(item_command(kind, selected, verdict), expected)

    def test_missing_verdict_and_wrong_item_or_sink_are_rejected(self):
        policy, board, item = self.scene()
        policy._equipment_transaction_session = None
        verdict = reservation_verdict(policy, board, item, 'home-visit', 'deposit')
        with self.assertRaises(TypeError):
            item_command('deposit', item)
        with self.assertRaises(TypeError):
            item_command('deposit', item, None)
        with self.assertRaises(ValueError):
            item_command('deposit', board.inventory[0], verdict)
        with self.assertRaises(ValueError):
            item_command('sell', item, verdict)

    def test_foreign_reservation_cannot_be_serialized_in_either_mode(self):
        for enforced in (False, True):
            policy, board, item = self.scene(enforced)
            verdict = reservation_verdict(policy, board, item, 'home-visit', 'deposit')
            with self.assertRaises(ValueError):
                item_command('deposit', item, verdict)
            self.assertIsNone(checked_item_command(policy, 'deposit', item, verdict))
            self.assertIsNone(reserved_item_command(policy, board, 'deposit', item, 'home-visit'))

    def test_off_serializer_exception_logs_shadow_and_preserves_historical_key(self):
        policy, board, item = self.scene()
        policy._equipment_transaction_session = None
        @reservation_decision
        def decide(policy, board):
            with patch('hengbot.item_reservation.item_command', side_effect=RuntimeError('pin')):
                self.assertEqual(reserved_item_command(policy, board, 'deposit', item, 'home-visit'), 'dq')
            self.assertEqual(reservation_shadow(policy)[0]['error'], 'RuntimeError')
            self.assertNotIn('would_stop', reservation_shadow(policy)[0])
        decide(policy, board)

    def test_on_serializer_exception_is_a_typed_stop(self):
        policy, board, item = self.scene(True)
        policy._equipment_transaction_session = None
        @reservation_decision
        def decide(policy, board):
            with patch('hengbot.item_reservation.item_command', side_effect=RuntimeError('pin')):
                self.assertIsNone(reserved_item_command(policy, board, 'deposit', item, 'home-visit'))
            self.assertEqual(policy.last_reason, 'ownership:item-reserved:deposit:serializer-error')
            self.assertEqual(reservation_shadow(policy)[0]['would_stop'], policy.last_reason)
        decide(policy, board)

    def test_invalid_verdict_error_does_not_escape_the_exception_seam(self):
        for enforced in (False, True):
            policy, board, item = self.scene(enforced)
            policy._equipment_transaction_session = None
            @reservation_decision
            def decide(policy, board):
                key = checked_item_command(policy, 'deposit', item, None)
                self.assertEqual(key, None if enforced else 'dq')
                self.assertEqual(reservation_shadow(policy)[0]['error'], 'TypeError')
            decide(policy, board)

    def test_retention_is_a_quantity_view_without_an_owner(self):
        policy, board, item = self.scene()
        policy._equipment_transaction_session = None
        with patch.object(policy, '_retention_surplus', return_value=0):
            verdict = reservation_verdict(policy, board, item, 'home-visit', 'deposit')
        self.assertIsNone(verdict.owner)
        self.assertEqual(verdict.quantity, 0)

    def test_merchant_purchase_does_not_claim_reserved_possessions(self):
        for enforced in (False, True):
            policy, board, item = self.scene(enforced)
            self.assertEqual(reserved_item_command(policy, board, 'buy', item, 'shop-buy'), 'pq')
            self.assertIsNone(reserved_item_command(policy, board, 'withdraw', item, 'home-visit'))
