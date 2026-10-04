"""Batch 3 isolated seams; reconstructed ledgers, never a full checkpoint.

The 15:45 board is absent: loot uses the recorded 2026-09-26 board instead.
The existing final-deposit completion control constructs its effect on the
17:29 Home board; it is not a replay of the board-missing 15:59 incident.
Other boards are exact, with the explicit attach substitutions below.
"""
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.claim_register import observe, reach
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_optimizer import equipment_move_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession, observe_equipment_transactions
from hengbot.model import parse_snapshot, Position, _parse_items
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
import test_town_loot_store_20260926_recorded as recorded_loot

FIXTURE = Path(__file__).parent / 'fixtures/shadow3-20261004.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    '5fe9de76d4f92bdece3cceac8f2bab379fc9b2a83f62eede925d101d034bc02d')
DATA = json.loads(gzip.decompress(FIXTURE.read_bytes()))


def board(line):
    raw = DATA['boards'][next(k for k in DATA['boards']
        if k.endswith(f':state-upto-1740.jsonl.gz:{line}'))]
    # Missing attach skill cache and town resident race catalogue: irrelevant
    # to isolated equipment/store ownership seams, explicitly constructed.
    return replace(parse_snapshot({**raw, 'visible_monsters': [],
        'detected_monsters': []}), protocol_version=2)


def row(line, early=False):
    return DATA['rows'][f"decisions-{'1-at' if early else '1714'}-1740.jsonl.gz:{line}"]


def attached(snapshot, enforced):
    policy = HengbotPolicy()
    policy.prime(snapshot)
    policy._town_claim_bar_enforced = enforced
    policy._crossarea_fundraising_enforced = True
    policy._in_store_ops_enabled = True
    return policy


def declare_row(policy, line, *, awaiting=True):
    c = row(line)['claim']
    g = c['goal']
    claim = policy._claim_register.declare(c['owner'], observe(
        g['expectation'], g['within'], g['source']))
    e = c['execution']
    args = tuple(tuple(v) if isinstance(v, list) else v for v in e['arguments'])
    policy._claim_register.declare_execution(claim.claim_id,
        producer=e['producer'], work_id=e['work_id'],
        state='awaiting' if awaiting else 'acting',
        next_step=None if awaiting else e['next_step'], arguments=args,
        operation_ref=f"decision:{row(line)['decision_sequence']}:{row(line)['key']}" if awaiting else None,
        expected_effect=e['expected_effect'], continuation=e['continuation'])
    return claim


class Shadow3Test(unittest.TestCase):
    def clean(self, policy, snapshot, key):
        self.assertIsNone(policy._s33_shadow_verdict(snapshot, key)['would_stop'])
        self.assertFalse((policy.last_reason or '').startswith('ownership:declaration-'))

    def test_loot_downstream_respects_registered_route(self):
        recorded_loot.TownLootStoreRecordedTest.setUpClass()
        snapshot = recorded_loot.TownLootStoreRecordedTest().board(33899)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(snapshot, enforced)
                policy._begin_map_predicate_cache(snapshot)
                policy._known_loot.add(recorded_loot.GOLD)
                policy._loot_target = recorded_loot.GOLD
                policy._shopping_approach_store_type = 4
                claim = policy._claim_register.declare('store-router', reach((32, 90)))
                policy._claim_register.declare_execution(claim.claim_id,
                    producer='store-router', work_id='route:store:32,90', state='acting',
                    next_step='route.resume', arguments=('store', (32, 90)),
                    expected_effect='arrive:32,90', continuation='route.resume')
                policy.last_reason = 'shop:approach'
                key = policy._town_procurement_decision(snapshot, '7')
                if enforced:
                    self.assertNotEqual(policy.last_reason, 'seek-loot')
                else:
                    self.assertTrue(any(r.get('producer_key') == key and
                        r['deferred_family'] == 'floor-loot'
                        for r in getattr(policy, '_decision_errand_deferred', ()) or ()))
                self.clean(policy, snapshot, key)

    def test_suppression_effect_closes_its_own_work(self):
        snapshot = board(800)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(snapshot, enforced)
                knowledge = DATA['knowledge']['8826362:state-upto-1740.jsonl.gz:794']['knowledge']
                policy.consume_home_knowledge(tuple(_parse_items(knowledge['items'], protocol=3)))
                declare_row(policy, 2444)
                key = policy.choose_key(snapshot)
                self.clean(policy, snapshot, key)
                self.assertIsNotNone(policy.decision_claim['closed_claim'])
                self.assertEqual(policy.decision_claim['closed_claim']['closed'], 'complete')
                self.assertEqual(policy.decision_claim['closed_claim']['closed_reason'],
                    'random-teleport-suppressed')
                self.assertFalse(any(c and c.is_open and c.execution and
                    c.execution.work_id == 'suppress-random-teleport'
                    for c in (policy._claim_register.current, *policy._claim_register.suspended)))

    def test_full_home_direct_sale_is_bound_and_observed_on_store_page(self):
        before, after = board(2243), board(2244)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(before, enforced)
                target = next(i for i in before.inventory if i.inscription == '@0')
                policy._home_full_relief = {'town': policy._effective_town_id(before),
                    'sale': (policy._item_signature(target), 5, 0), 'withdrawn': True,
                    'remaining': 1, 'deposits': ()}
                policy._store_visit = StoreVisit('town-errand', 'shopping', 5,
                    StoreVisitPhase.OPERATING, opened_sequence=1326)
                key = policy.choose_key(before)
                self.assertEqual(key, row(3772)['key'])
                self.assertIsNotNone(policy._claim_register.current.execution)
                self.assertEqual(policy._claim_register.current.execution.producer, 'shop-sell')
                self.assertTrue(policy._store_visit.operation_posted)
                policy.confirm_key_posted(key)
                key = policy.choose_key(after)
                self.assertNotEqual(key, '')
                self.assertIsNone(policy._batch_sell_pending)
                self.clean(policy, after, key)

    def test_direct_sale_unchanged_store_page_exits_without_retry(self):
        before = board(2243)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(before, enforced)
                target = next(i for i in before.inventory if i.inscription == '@0')
                policy._home_full_relief = {'town': policy._effective_town_id(before),
                    'sale': (policy._item_signature(target), 5, 0), 'withdrawn': True,
                    'remaining': 1, 'deposits': ()}
                policy._store_visit = StoreVisit('town-errand', 'shopping', 5,
                    StoreVisitPhase.OPERATING, opened_sequence=1326)
                key = policy.choose_key(before)
                policy.confirm_key_posted(key)
                # DECLARED CONSTRUCTED alternate response: the operation
                # returned to STORE with unchanged pack/gold, rather than the
                # recorded successful sale. The existing in-store no-effect
                # boundary must leave, with no second sale or empty-key wait.
                key = policy.choose_key(before)
                self.assertEqual(key, '\x1b')
                self.assertEqual(policy.decision_claim['owner'], 'shop-sell')
                self.assertEqual(policy._claim_register.current.execution.producer, 'shop-sell')
                self.clean(policy, before, key)

    def test_scan_gate_sees_suspended_restoration(self):
        snapshot = board(2255)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(snapshot, enforced)
                declare_row(policy, 3778)
                policy._claim_register.suspend('constructed-recovery', turn=snapshot.turn)
                policy._claim_register.declare('survival', reach((38, 106)))
                policy._begin_map_predicate_cache(snapshot)
                policy._decision_errand_deferred = []
                refused = policy._defer_town_errand('home-scan', 'outside-scan')
                self.assertTrue(policy._decision_errand_deferred)
                self.assertEqual(refused, enforced)

    def test_existing_last_deposit_completion_remains_observed(self):
        # DECLARED CONSTRUCTED control on the 17:29 recorded pack item;
        # the removal below is a constructed success, not historical evidence.
        before = board(788)
        target = next(i for i in before.inventory if i.count == 1 and i.is_equipment)
        after = replace(before, inventory=tuple(i for i in before.inventory if i != target),
            store=None, turn=before.turn + 1)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(before, enforced)
                action = EquipmentTransaction('home_prepare', 'deposit', 'pack:recorded:0',
                    item_identity=equipment_identity(target), move_identity=equipment_move_identity(target))
                session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0),
                    physical_context='home')
                session.opened_sequence = 1
                self.assertTrue(session.dispatch(action, observe_equipment_transactions(before)))
                policy._equipment_transaction_session = session
                claim = policy._claim_register.declare('equipment-txn',
                    observe((repr(session.plan.actions), '1'), 8, 'transaction'))
                policy._claim_register.declare_execution(claim.claim_id,
                    producer='equipment-txn', work_id=f'equipment:{session.target_loadout_id}:0',
                    state='awaiting', operation_ref='decision:1:d'+target.slot,
                    expected_effect='equipment-action-confirmed', continuation='equipment.next-action')
                # This control already passes on main: completed sessions
                # must close before the next Home requester can take over.
                policy._home_knowledge_invalidated = True
                key = policy.choose_key(after)
                self.assertTrue(session.complete)
                self.clean(policy, after, key)
                closed = policy.decision_claim['closed_claim']
                self.assertEqual(closed['closed_reason'], 'equipment-transaction-complete')

    def test_unobserved_suppression_is_a_visible_stop(self):
        snapshot = board(798)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(snapshot, enforced)
                declare_row(policy, 2444)
                claim = policy._claim_register.current
                e = claim.execution
                policy._claim_register.declare_execution(claim.claim_id,
                    producer=e.producer, work_id=e.work_id, state='awaiting',
                    arguments=e.arguments, operation_ref=e.operation_ref,
                    expected_effect=e.expected_effect, continuation='equipment.suppression.observe')
                self.assertEqual(policy._town_holder_structural_stop(
                    policy._claim_register.current, snapshot), 'ownership:declaration-stale:equipment-txn')

    def test_suspended_restoration_public_scan_board(self):
        snapshot = board(2255)
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = attached(snapshot, enforced)
                declare_row(policy, 3778)
                policy._claim_register.suspend('constructed-recovery', turn=snapshot.turn)
                policy._claim_register.declare('survival', reach((38, 106)))
                key = policy.choose_key(snapshot)
                self.clean(policy, snapshot, key)
                if enforced:
                    self.assertEqual(policy.last_reason, 'town:restore-combat-weapon')
                    self.assertEqual(key, row(3782)['key'])
                    self.assertEqual(policy.decision_claim['owner'], 'equipment-txn')


if __name__ == '__main__':
    unittest.main()
