"""DECLARED CONSTRUCTED posted-session seam on A's actual item board.

No restorable checkpoint exists. Rebuild the recorded pending deposit via
session.dispatch, then feed unchanged observations to its existing limit.
Replay stops at the first changed key; no historical command effects follow.
"""
import unittest
from dataclasses import replace
import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.equipment_transaction_session import observe_equipment_transactions
from hengbot.policy import HengbotPolicy, EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT
from s33_phase2_fixtures import board, session, town_map


class EquipmentReleaseTest(unittest.TestCase):
    def test_recorded_pending_deposit_releases_without_dead_continuation(self):
        snapshot = board(10498)
        policy = HengbotPolicy(town_map=town_map())
        policy.prime(snapshot)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        pending = session()
        action = pending.current_action
        observation = replace(observe_equipment_transactions(snapshot), in_home=True)
        self.assertTrue(pending.dispatch(action, observation))
        for _ in range(EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT):
            pending.observe(observation)
        policy._equipment_transaction_session = pending
        claim = policy._claim_register.declare('equipment-txn',
            observe(('recorded-pending-deposit',), 8, source='transaction'),
            floor=snapshot.floor_key)
        policy._claim_register.declare_execution(claim.claim_id,
            producer='equipment-txn', work_id='equipment:town:pending:017513216e865629',
            state='acting', next_step='equipment.action.observe', arguments=('dm',),
            expected_effect='equipment-action-confirmed', continuation='equipment.next-action')
        key = policy.choose_key(snapshot)
        self.assertEqual(key, '5')
        self.assertEqual(policy.last_reason, 'equipment-transaction:confirmation-stall-bound')
        self.assertIsNone(policy._equipment_transaction_session)
        declaration = policy._claim_register.current.execution
        self.assertEqual(declaration.next_step, 'equipment.confirmation-stall-stop')
        self.assertIsNone(declaration.continuation)
        self.assertIsNone(policy._s33_shadow_verdict(snapshot, key)['would_stop'])
        self.assertIsNone(policy.decision_claim['declaration_mismatch'])
        self.assertIsNone(policy.decision_claim['claim_verdict_conflict'])


if __name__ == '__main__':
    unittest.main()
