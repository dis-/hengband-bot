import unittest
from unittest.mock import patch
from tests import test_item_reservation as fixture
from hengbot.item_reservation import reserved_item_command


class DecisionReturnBoundaryTest(unittest.TestCase):
    scene = fixture.ItemReservationTest.scene

    def assert_boundary(self, policy, board, expected):
        events = []
        enforce = policy._enforce_town_claim_result
        record = policy._record_decision_claim
        def final(snapshot, key):
            events.append(('enforce', key))
            return enforce(snapshot, key)
        def write(snapshot, key):
            events.append(('record', key))
            return record(snapshot, key)
        with patch.object(policy, '_enforce_town_claim_result', side_effect=final), \
                patch.object(policy, '_record_decision_claim', side_effect=write):
            key = policy.choose_key(board)
        self.assertEqual(key, expected)
        self.assertEqual([event for event in events if event[0] == 'record'], [('record', key)])
        self.assertEqual(events[-1], ('record', key))
        self.assertEqual(events[-2][0], 'enforce')

    def test_skill_probe_reaches_final_enforcement_and_record_once(self):
        for enforced in (False, True):
            policy, board, _ = self.scene(enforced)
            policy._equipment_transaction_session = None
            policy.last_reason = 'periodic:skill-exp-knowledge'
            with patch.object(policy, '_skill_exp_request_key', return_value='~f'):
                self.assert_boundary(policy, board, '~f')

    def test_posting_refusal_probe_reaches_same_boundary(self):
        for enforced in (False, True):
            policy, board, _ = self.scene(enforced)
            policy._equipment_transaction_session = None
            policy.last_reason = 'periodic:look-probe'
            policy._posting_refusal_probe = ('bookkeeping', policy._owner_progress_core(board))
            with patch.object(policy, '_skill_exp_request_key', return_value=None), \
                    patch.object(policy, '_look_probe_key', return_value='l'):
                self.assert_boundary(policy, board, 'l')

    def test_reservation_terminal_records_once_after_final_enforcement(self):
        for fallback in (None, '5'):
            with self.subTest(fallback=fallback):
                policy, board, item = self.scene(True)
                def producer(snapshot):
                    # Selection alone is a silent skip. Attempt serialization
                    # to exercise a terminal at the actual emission seam.
                    self.assertIsNone(reserved_item_command(
                        policy, snapshot, 'deposit', item, 'home-visit'))
                    return fallback
                with patch.object(policy, '_skill_exp_request_key', return_value=None), \
                        patch.object(policy, '_choose_key_with_latch_capture',
                                     side_effect=producer) as choose:
                    self.assert_boundary(policy, board, None)
                choose.assert_called_once_with(board)
                reason = 'ownership:item-reserved:deposit:equipment-txn'
                self.assertEqual(policy.last_reason, reason)
                self.assertEqual([row['would_stop'] for row in
                                  policy.decision_claim['item_reservation_shadow']
                                  if 'would_stop' in row], [reason])
