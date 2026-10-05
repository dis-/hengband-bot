"""Pin the 2026-10-05 Home exit loop at its first changed command.

Boards and declarations are captured. No checkpoint exists: the retry ledger,
session and visit are reconstructed from the posted command/declaration.
No later historical response is replayed as an effect of the changed command.
"""
import ast
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.item_reservation import item_reserved_by_other
from hengbot.model import parse_snapshot, _parse_items, STORE_HOME
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase

FIXTURE = Path(__file__).parent / 'fixtures/homeexit-20261005.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    '382ecb3be6469fedd7e6e720b93a8a32c606f0405fa8ac59f90bc16dc7170bd7')
DATA = json.loads(gzip.decompress(FIXTURE.read_bytes()))


def board(line):
    raw = DATA['states'][str(line)]
    # Constructed static combat defaults; preserve captured town perception.
    lore = {m['race_id']: MonraceKnowledge(10, 110, False, False)
            for m in raw.get('visible_monsters', []) + raw.get('detected_monsters', [])}
    return parse_snapshot(raw, lore)


def scene(enforced, line=75):
    snapshot = board(line)
    policy = HengbotPolicy()
    policy.prime(snapshot)
    policy.consume_skill_knowledge(DATA['states']['42'])
    policy._town_claim_bar_enforced = enforced
    policy._crossarea_fundraising_enforced = True
    policy._in_store_ops_enabled = True
    policy.consume_home_knowledge(tuple(_parse_items(
        DATA['states']['70']['knowledge']['items'], protocol=3)))
    text = DATA['decisions']['226']['claim']['goal']['expectation'][0]
    actions = []
    for value in ast.literal_eval(text):
        node = ast.parse(value, mode='eval').body
        actions.append(EquipmentTransaction(**{
            kw.arg: ast.literal_eval(kw.value) for kw in node.keywords}))
    session = EquipmentTransactionSession(
        EquipmentTransactionPlan(tuple(actions), (), 0), physical_context='home')
    session.opened_sequence = 19
    policy._equipment_transaction_session = session
    # 209 posted di9\r ESC; 45/46 capture refusal. 225 records space ready.
    target = next(i for i in board(45).inventory if i.slot == 'i')
    policy._home_full_retry_deposits = ((policy._item_signature(target), target.count, 9),)
    policy._store_visit = StoreVisit('equipment-transaction', 'equipment-work',
        STORE_HOME, StoreVisitPhase.OPERATING, opened_sequence=19)
    claim = policy._claim_register.declare('equipment-txn',
        observe((19, tuple(map(repr, session.plan.actions))), 8, source='transaction'))
    policy._claim_register.declare_execution(claim.claim_id,
        producer='equipment-txn', work_id='equipment:town:approach-home',
        state='acting', next_step='equipment.town.approach-home',
        expected_effect='home-reached', continuation='equipment.next-action')
    return policy, snapshot, session


class HomeExitRecordedTest(unittest.TestCase):
    def test_capture_proves_idle_exit_intercepted_available_withdrawal(self):
        self.assertEqual(DATA['decisions']['225']['reason'], 'home:full-space-ready')
        for row in (227, 230):
            captured = DATA['decisions'][str(row)]
            self.assertEqual(captured['reason'], 'policy:none-store-exit')
            self.assertEqual(captured['key'], '\x1b')
            self.assertEqual(captured['claim']['owner'], 'idle')
            self.assertTrue(any(e['deferred_reason'] == 'entry:_home_full_relief_key'
                                for e in captured['claim']['errand_deferred']))
        self.assertEqual(DATA['decisions']['234']['reason'], 'town:blocked:owner-retired')

    def test_retry_tail_admits_equipment_withdrawal_on_captured_home_pages(self):
        for line in (75, 79):
            for enforced in (False, True):
                with self.subTest(line=line, enforced=enforced):
                    policy, snapshot, session = scene(enforced, line)
                    target = next(i for i in policy._home_knowledge_items
                                  if equipment_identity(i) == session.current_action.item_identity)
                    self.assertIsNone(item_reserved_by_other(
                        policy, snapshot, target, ('equipment-txn', 'withdraw')))
                    retry = policy._home_full_retry_deposits
                    key = policy.choose_key(snapshot)
                    self.assertEqual(key, ' ')
                    self.assertEqual(policy.last_reason, 'equipment-transaction:seek-home-page')
                    self.assertEqual(policy.decision_claim['owner'], 'equipment-txn')
                    self.assertIsNone(policy.decision_claim['violation'])
                    self.assertIsNone(policy.decision_claim['declaration_mismatch'])
                    self.assertIsNone(policy._s33_shadow_verdict(snapshot, key)['would_stop'])
                    self.assertEqual(policy._home_full_retry_deposits, retry)
                    self.assertIsNone(session.pending_action)
                    policy.confirm_key_posted(key)
                    # DECLARED CONSTRUCTED target page: capture 70 supplies the
                    # full catalogue; no page 156 response exists in the log.
                    # This is an address projection, not a historical replay.
                    target_page = replace(snapshot, store=replace(snapshot.store,
                        page_top=156, items=list(policy._home_knowledge_items[156:208])))
                    key = policy.choose_key(target_page)
                    self.assertEqual(key, 'pz')
                    self.assertEqual(policy.last_reason, 'equipment-transaction:withdraw')
                    self.assertEqual(policy.decision_claim['owner'], 'equipment-txn')
                    self.assertIsNone(policy.decision_claim['violation'])
                    self.assertIsNone(policy._s33_shadow_verdict(target_page, key)['would_stop'])
                    policy.confirm_key_posted(key)
                    self.assertEqual(session.pending_action.kind, 'withdraw')

    def test_conflicting_home_withdrawal_exits_with_equipment_owner_and_cause(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, snapshot, session = scene(enforced)
                target = policy._home_knowledge_items[181]
                snapshot = replace(snapshot, store=replace(snapshot.store,
                    page_top=156, items=list(policy._home_knowledge_items[156:208])))
                pending = (policy._item_signature(target), 0, False, 1)
                policy._home_atomic_withdraw_pending = pending
                self.assertEqual(item_reserved_by_other(policy, snapshot, target,
                    ('equipment-txn', 'withdraw')).owner, 'home-errand')
                key = policy._equipment_transaction_home_key(snapshot)
                self.assertEqual(key, '\x1b')
                self.assertEqual(policy.last_reason,
                                 'equipment-transaction:withdraw-reservation-refused')
                self.assertIn('withdraw-reservation-refused', session.blockers)
                self.assertIsNone(session.pending_action)
                self.assertEqual(policy._home_atomic_withdraw_pending, pending)

    def test_conflicting_home_deposit_exits_with_equipment_owner_and_cause(self):
        from test_equipment_deposit_owner_recorded import DepositOwnerRecordedTest
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, snapshot, session, target = DepositOwnerRecordedTest().retry_scene(enforced)
                pending = (((policy._item_signature(target), target.count, target.count),),
                           None, snapshot.turn, 0)
                policy._home_atomic_deposit_pending = pending
                self.assertEqual(item_reserved_by_other(policy, snapshot, target,
                    ('equipment-txn', 'deposit')).owner, 'home-visit')
                key = policy._equipment_transaction_home_key(snapshot)
                self.assertEqual(key, '\x1b')
                self.assertEqual(policy.last_reason,
                                 'equipment-transaction:deposit-reservation-refused')
                self.assertIn('deposit-reservation-refused', session.blockers)
                self.assertIsNone(session.pending_action)
                self.assertEqual(policy._home_atomic_deposit_pending, pending)

    def test_equipment_retry_deposit_has_one_owner_after_explicit_handoff(self):
        from test_equipment_deposit_owner_recorded import DepositOwnerRecordedTest
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, snapshot, session, target = DepositOwnerRecordedTest().retry_scene(enforced)
                key = policy.choose_key(snapshot)
                self.assertEqual(key, 'dp')
                self.assertEqual(policy.last_reason, 'equipment-transaction:deposit')
                self.assertIsNone(policy._home_full_retry_deposits)
                self.assertIsNone(policy._home_atomic_deposit_pending)
                self.assertEqual(policy.decision_claim['owner'], 'equipment-txn')
                self.assertIsNone(policy.decision_claim['violation'])
                self.assertEqual(item_reserved_by_other(policy, snapshot, target,
                    ('home-visit', 'deposit')).owner, 'equipment-txn')
                policy.confirm_key_posted(key)
                self.assertEqual(session.pending_action.kind, 'deposit')


if __name__ == '__main__':
    unittest.main()
