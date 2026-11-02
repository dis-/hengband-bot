"""80 frozen incident seams, not a continuous replay or a captured checkpoint.

Rows 78-80 have exact boards: recompute public decisions independently.
For the other 77 rows, pin the affected verdict on the recorded inputs.
Every extra board, item, pre-declaration or pending ledger is CONSTRUCTED;
in particular, no historical response is delivered after a changed command.
"""
import ast
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import pickle
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tests  # noqa: F401 -- isolate all runtime writes
from hengbot.claim_register import ClaimState, ExecutionDeclaration, Goal, observe
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.item_reservation import (
    ReservationVerdict, checked_item_command, item_command, reservation_decision,
    reservation_shadow, reservation_verdict,
)
from hengbot.model import Position, StoreState, STORE_HOME, parse_snapshot, _parse_items
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from test_policy import Snapshot, grid, player

FIXTURE = Path(__file__).parent / 'fixtures/s33-shadow-zero-20261005.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    '2dd71ebcaecb6e3a3baffb2add351c9ddb0d8f3bccb2133a2a6d11d838af685c')
DATA = json.loads(gzip.decompress(FIXTURE.read_bytes()))
HOME_SURPLUS_REFUSAL = 'shop:unsellable-home-full-surplus-sale-refused'


def tuples(value):
    return tuple(map(tuples, value)) if isinstance(value, list) else value


def attach_claim(policy, recorded):
    """Reconstruct plain claim data; no policy checkpoint was captured."""
    goal = Goal(**{k: tuples(v) for k, v in recorded['goal'].items()})
    claim = policy._claim_register.declare(recorded['owner'], goal,
                                         non_discardable=recorded.get('non_discardable', False))
    execution = recorded.get('execution')
    declaration = (ExecutionDeclaration(**{k: tuples(v) for k, v in execution.items()})
                   if execution else None)
    policy._claim_register._claim = replace(claim, claim_id=recorded['claim_id'],
        execution=declaration, state=ClaimState(recorded.get('state', 'active')))
    policy._claim_register._next_id = recorded['claim_id'] + 1
    return policy._claim_register.current


def attach_visit(policy, row):
    if row.get('store_visit'):
        policy._store_visit = StoreVisit(**{**row['store_visit'],
            'phase': StoreVisitPhase(row['store_visit']['phase'])})


def constructed_board(row):
    """CONSTRUCTED board: only captured town position/store/turn are inputs."""
    pos = row['position']
    return Snapshot(player(pos['y'], pos['x']),
        {Position(pos['y'], pos['x']): grid(pos['y'], pos['x'])}, [],
        floor_key=(0, 0, 0), town_flag=True, turn=row['turn'],
        store=StoreState(row['store_type'], []) if row['store_type'] is not None else None)


def attach_session(policy, row):
    """Captured plan, CONSTRUCTED cursor at the recorded current/pending action."""
    plan_text = next(text for text in row['claim']['goal']['expectation']
                     if 'EquipmentTransaction(' in text)
    actions = []
    for text in ast.literal_eval(plan_text):
        node = ast.parse(text, mode='eval').body
        actions.append(EquipmentTransaction(**{
            kw.arg: ast.literal_eval(kw.value) for kw in node.keywords}))
    session = EquipmentTransactionSession(
        EquipmentTransactionPlan(tuple(actions), (), 0), physical_context='home')
    telemetry = row['equipment_optimization']
    current = telemetry.get('transaction_pending') or telemetry.get('transaction_next')
    if current:
        session.index = next(i for i, action in enumerate(actions)
                             if action.item_id == current['item_id'] and action.kind == current['kind'])
    policy._equipment_transaction_session = session
    return session


class ShadowZeroTest(unittest.TestCase):
    def test_selection_counts_inscribe_wield_and_weight_skips_in_both_modes(self):
        from test_item_reservation import ItemReservationTest
        for enforced in (False, True):
            policy, board, target = ItemReservationTest().scene(enforced)
            policy.last_reason = 'periodic:game-save'
            @reservation_decision
            def decide(policy, board):
                for sink in ('inscribe', 'wield', 'weight-deposit'):
                    for _ in range(2):
                        verdict = reservation_verdict(policy, board, target, 'foreign', sink)
                        self.assertEqual(verdict.owner, 'equipment-txn')
                rows = reservation_shadow(policy)
                self.assertEqual(len(rows), 3)
                self.assertEqual([r['count'] for r in rows], [2, 2, 2])
                self.assertFalse(any(r.get('would_stop') for r in rows))
                self.assertEqual(policy.last_reason, 'periodic:game-save')
                self.assertEqual(policy._enforce_town_claim_result(board, '\x13'), '\x13')
            decide(policy, board)

    def test_suppressed_foreign_emission_remains_visible_in_off_shadow(self):
        from test_item_reservation import ItemReservationTest
        policy, board, target = ItemReservationTest().scene(False)
        @reservation_decision
        def decide(policy, board):
            verdict = reservation_verdict(policy, board, target, 'foreign', 'deposit')
            key = checked_item_command(policy, 'deposit', target, verdict)
            self.assertIsNone(key)
            self.assertEqual(policy._s33_shadow_verdict(board, key)['would_stop'],
                             'ownership:item-reserved:deposit:equipment-txn')
        decide(policy, board)

    def test_refused_wait_envelope_requires_exact_holder_family_key_and_target(self):
        row = DATA['rows'][76]
        policy = HengbotPolicy()
        board = constructed_board(row)
        prior = DATA['prior']['77']['row']
        holder = attach_claim(policy, prior['claim'])
        policy._decision_errand_deferred = row['claim']['errand_deferred']
        declaration = row['claim']['execution']
        key, reason = row['key'], row['reason']
        self.assertFalse(policy._town_refused_output_entry(board, key, reason, 'idle', holder))
        policy._offer_execution(key, producer='idle', work_id=declaration['work_id'],
            next_step=declaration['next_step'], arguments=tuples(declaration['arguments']),
            expected_effect=declaration['expected_effect'])
        before = pickle.dumps(policy)
        self.assertTrue(policy._town_refused_output_entry(board, key, reason, 'idle', holder))
        self.assertFalse(policy._town_refused_output_entry(None, key, reason, 'idle', holder))
        self.assertEqual(pickle.dumps(policy), before)
        self.assertFalse(policy._town_refused_output_entry(board, key, reason, 'departure', holder))
        self.assertFalse(policy._town_refused_output_entry(board, '9', reason, 'idle', holder))
        displaced = replace(holder, claim_id=holder.claim_id + 1)
        self.assertFalse(policy._town_refused_output_entry(board, key, reason, 'idle', displaced))
        moved = replace(board, player=replace(board.player, position=Position(1, 1)))
        self.assertFalse(policy._town_refused_output_entry(moved, key, reason, 'idle', holder))

    def test_posted_entry_route_wait_rejects_changed_binding(self):
        row = DATA['rows'][0]
        policy = HengbotPolicy()
        policy._decision_sequence = row['store_visit']['posted_sequence']
        policy.last_reason = row['reason']
        attach_visit(policy, row)
        holder = attach_claim(policy, row['claim'])
        policy._store_entry_wait_key = holder.execution.operation_ref.split(':', 2)[2]
        policy._store_entry_wait_owner = policy._store_entry_posted_owner = row['store_visit']['store_type']
        self.assertTrue(policy._town_posted_route_entry_wait(holder))
        before = pickle.dumps(policy)
        self.assertFalse(policy._town_posted_route_entry_wait(replace(holder,
            execution=replace(holder.execution, operation_ref='decision:562:7'))))
        self.assertFalse(policy._town_posted_route_entry_wait(replace(holder,
            goal=replace(holder.goal, cell=(1, 1)))))
        self.assertEqual(pickle.dumps(policy), before)
        policy._store_visit.phase = StoreVisitPhase.APPROACHING
        self.assertFalse(policy._town_posted_route_entry_wait(holder))

    def test_home_exit_transition_preserves_goal_identity_and_pending_effect(self):
        row = DATA['rows'][13]
        policy = HengbotPolicy()
        board = constructed_board(row)
        session = attach_session(policy, row)
        holder = attach_claim(policy, row['claim'])
        holder = replace(holder, execution=replace(holder.execution,
            work_id='equipment:town:approach-home', next_step='equipment.town.approach-home',
            arguments=(), expected_effect='home-reached'))
        policy.last_reason = row['reason']
        declaration = row['claim']['execution']
        policy._offer_execution(row['key'], producer='equipment-txn',
            work_id=declaration['work_id'], next_step=declaration['next_step'],
            arguments=tuples(declaration['arguments']), expected_effect=declaration['expected_effect'],
            continuation=declaration['continuation'])
        self.assertIsNone(policy._town_final_declaration_stop(board, row['key'], holder))
        changed_goal = replace(holder, goal=replace(holder.goal, expectation=('other session',)))
        self.assertEqual(policy._town_final_declaration_stop(board, row['key'], changed_goal),
                         'ownership:declaration-stale:equipment-txn')
        session._dispatched = session.current_action  # CONSTRUCTED pending operation.
        self.assertEqual(policy._town_final_declaration_stop(board, row['key'], holder),
                         'ownership:declaration-stale:equipment-txn')

    def test_direct_descent_is_gated_before_departure_mutations(self):
        # CONSTRUCTED stair board at the captured row-25 position.
        board = constructed_board(DATA['rows'][24])
        pos = board.player.position
        board = replace(board, grids={pos: grid(pos.y, pos.x, downstairs=True)})
        for enforced in (False,):
            policy = HengbotPolicy()
            policy.prime(board)
            policy._equipment_catalog.home_scan_complete = True
            holder = policy._claim_register.declare('home-visit',
                observe(('deposit',), 8, 'store-operation'))
            policy._claim_register.declare_execution(holder.claim_id, producer='home-visit',
                work_id='home:operation', state='awaiting', operation_ref='decision:1:da',
                expected_effect='home-inventory-effect', continuation='home.operation.observe')
            with patch.object(policy, '_dungeon_entry_allowed', return_value=True), \
                    patch.object(policy, '_descent_is_blocked', return_value=False):
                key = policy._decide(board)
            self.assertEqual(key, None if enforced else '>')
            self.assertTrue(any(r['deferred_reason'] == 'entry:direct-descent'
                                for r in policy._decision_errand_deferred))
            if not enforced:
                self.assertIsNone(policy._s33_shadow_verdict(board, key)['would_stop'])
            self.assertEqual(policy._claim_register.current.claim_id, holder.claim_id)

    def test_sale_refusal_declares_its_registered_exit_owner(self):
        from test_item_reservation import ItemReservationTest
        from hengbot.claim_goal_typing import goal_typing
        from hengbot.model import STORE_WEAPON
        policy, board, target = ItemReservationTest().scene(True)
        board = replace(board, store=StoreState(STORE_WEAPON, []))
        self.assertEqual(DATA['rows'][75]['reason'], 'shop:home-full-surplus-sale-refused')
        reason = HOME_SURPLUS_REFUSAL
        key = policy._store_sell_key(board, target, 'shop:sell-home-full-surplus', rejected_reason=reason)
        self.assertEqual((key, policy.last_reason), ('\x1b', reason))
        self.assertEqual(policy._claim_family_of(reason), 'shop-sell')
        self.assertIsNotNone(goal_typing('shop-sell', reason))
        holder = policy._claim_register.declare('shop-sell', observe(('sale',), 8, 'store-operation'))
        policy._record_execution_declaration(holder, key, reason)
        execution = policy._claim_register.current.execution
        self.assertEqual((execution.producer, execution.next_step, execution.expected_effect),
                         ('shop-sell', 'store.leave.send', 'outside-store'))


if __name__ == '__main__':
    unittest.main()
