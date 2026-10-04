"""2026-10-04 ownership pins, with explicitly reconstructed checkpoints.

No policy checkpoint was captured. Plans/declarations come from decision rows;
second-incident boards are exact. The first incident's boards are absent from
the supplied state copies: its item board at 8403902 and constructed command
effects are used only for isolated seams, never a historical tour replay.
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
from hengbot.equipment_transaction_session import EquipmentTransactionSession, observe_equipment_transactions
from hengbot.model import parse_snapshot, STORE_HOME, StoreState, _parse_items
from hengbot.policy import HengbotPolicy, EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT
from hengbot.policy_types import StoreVisit, StoreVisitPhase

FIXTURE = Path(__file__).parent / 'fixtures/equipment-deposit-owner-20261004.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    '4b52ed1f601bc6cd04ee07968518cd4b1b83baeba085126f615ac0c7de2e092b')
DATA = json.loads(gzip.decompress(FIXTURE.read_bytes()))


def captured_board(raw):
    # DECLARED CONSTRUCTED: neutral town residents are irrelevant to these
    # equipment seams and their monster catalogue is absent from this copy.
    return replace(parse_snapshot({**raw, 'visible_monsters': [],
        'detected_monsters': []}), protocol_version=2)


def session(line):
    row = DATA['rows'][str(line)]
    text = next(s for s in row['claim']['goal']['expectation']
                if 'EquipmentTransaction(' in s)
    actions = []
    for s in ast.literal_eval(text):
        node = ast.parse(s, mode='eval').body
        actions.append(EquipmentTransaction(**{
            kw.arg: ast.literal_eval(kw.value) for kw in node.keywords}))
    return EquipmentTransactionSession(EquipmentTransactionPlan(tuple(actions), (), 0),
        physical_context=('home' if row['equipment_optimization']['transaction_context'] == 'home'
                          else 'legacy'))


def declared(policy, pending, *, awaiting=False):
    claim = policy._claim_register.declare('equipment-txn',
        observe((repr(pending.plan.actions),), 8, source='transaction'),
        non_discardable=True)
    action = pending.pending_action or pending.current_action
    policy._claim_register.declare_execution(claim.claim_id,
        producer='equipment-txn', work_id=f'equipment:{pending.target_loadout_id}:{pending.index}',
        state='awaiting' if awaiting else 'acting',
        next_step=None if awaiting else 'equipment.next-action',
        arguments=(action.kind, action.target_slot, action.item_identity),
        operation_ref='decision:12:dl' if awaiting else None,
        expected_effect='equipment-action-confirmed', continuation='equipment.next-action')
    return policy._claim_register.current


class DepositOwnerRecordedTest(unittest.TestCase):
    def test_initial_deposits_are_different_from_later_stolen_goals(self):
        self.assertNotEqual(session(13212).current_action.item_identity,
                            'c981fe7d3be0b0ad')
        self.assertNotEqual(session(2587).current_action.item_identity,
                            '10a5a853ae65a169')
        before = parse_snapshot(DATA['boards']['8440873:store'])
        after = parse_snapshot(DATA['boards']['8440873:store:after'])
        self.assertEqual(len(before.inventory) - len(after.inventory), 1)
        self.assertEqual(after.store.stock_num - before.store.stock_num, 1)

    def retry_scene(self, enforced, first=False):
        raw = DATA['boards']['8403902:player_turn' if first else '8441267:store']
        board = captured_board(raw)
        pending = session(13212) if first else None
        if first:
            pending.index = 1  # Recorded first deposit succeeded; next is queued.
        else:
            # The errand row names only the errand goal. The recorded optimizer
            # explicitly names this one-action deposit session and its identity.
            identity = '10a5a853ae65a169'
            target = next(i for i in board.inventory if equipment_identity(i) == identity)
            from hengbot.equipment_optimizer import equipment_move_identity
            pending = EquipmentTransactionSession(EquipmentTransactionPlan((
                EquipmentTransaction('home_prepare', 'deposit', 'pack:'+identity+':0',
                    None, identity, equipment_move_identity(target)),), (), 0), physical_context='home')
        target = next(i for i in board.inventory
                      if equipment_identity(i) == pending.current_action.item_identity)
        policy = HengbotPolicy()
        policy.prime(board)
        policy._in_store_ops_enabled = True
        policy._town_claim_bar_enforced = enforced
        policy._equipment_transaction_session = pending
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        if not first:
            policy.consume_home_knowledge(tuple(_parse_items(
                DATA['knowledge']['8441081']['items'], protocol=2)))
        policy._home_full_retry_deposits = ((policy._item_signature(target), target.count, target.count),)
        policy._store_visit = StoreVisit('equipment-transaction', 'equipment-work',
            STORE_HOME, StoreVisitPhase.OPERATING, opened_sequence=154)
        return policy, board, pending, target

    def test_retry_selection_never_takes_the_equipment_owners_item(self):
        for first in (False, True):
            for enforced in (False, True):
                with self.subTest(first=first, enforced=enforced):
                    policy, board, pending, target = self.retry_scene(enforced, first)
                    self.assertIsNone(policy._find_home_deposit(board))
                    if board.store is None:
                        policy._home_full_relief_key(board)
                    else:
                        # Selection did not mutate or dispatch either ledger.
                        self.assertIsNone(policy._home_atomic_deposit_pending)
                        continue
                    self.assertIsNone(policy._home_full_retry_deposits)
                    self.assertIs(policy._equipment_transaction_session, pending)
                    self.assertEqual(pending.index, 1 if first else 0)

    def test_open_page_retry_is_posted_and_observed_by_equipment_owner(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, board, pending, target = self.retry_scene(enforced)
                key = policy.choose_key(board)
                self.assertEqual(key, 'dp')
                self.assertEqual(policy.last_reason, 'equipment-transaction:deposit')
                self.assertEqual(policy.decision_claim['owner'], 'equipment-txn')
                self.assertIsNone(policy.decision_claim['violation'])
                if not enforced:
                    self.assertIsNone(policy.decision_claim['s33_shadow']['would_stop'])
                policy.confirm_key_posted(key)
                self.assertIsNotNone(pending.pending_action)
                # This recorded effect follows the identical dp command. Stop at
                # the observation seam; no later historical decisions are replayed.
                after = parse_snapshot(DATA['boards']['8441267:store:after'])
                policy.choose_key(replace(after, protocol_version=2))
                self.assertTrue(pending.complete)
                self.assertIsNone(policy._equipment_transaction_session)

    def test_confirmed_action_refreshes_its_own_declaration(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, board, pending, target = self.retry_scene(enforced, first=True)
                pending.index = 0
                action = pending.current_action
                self.assertTrue(pending.dispatch(action, replace(
                    observe_equipment_transactions(board), in_home=True)))
                declared(policy, pending, awaiting=True)
                # DECLARED CONSTRUCTED first deposit effect, since its store board
                # is missing. This preserves the captured second queued item.
                after = replace(board, inventory=tuple(i for i in board.inventory
                    if equipment_identity(i) != action.item_identity),
                    store=StoreState(STORE_HOME, [], 239, 0, 12, 240))
                policy._home_scan_item_count = 239  # Constructed catalogue count.
                policy.choose_key(after)
                self.assertEqual(pending.index, 1)
                holder = policy._claim_register.current
                self.assertIsNone(policy._town_holder_structural_stop(holder, after))

    def test_refused_deposit_exit_preserves_the_owner_continuation(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                board = captured_board(DATA['boards']['8406500:store'])
                after = captured_board(DATA['boards']['8406500:store:after'])
                outside = captured_board(DATA['boards']['8406506:player_turn'])
                policy = HengbotPolicy()
                policy.prime(board)
                policy._in_store_ops_enabled = True
                policy._town_claim_bar_enforced = enforced
                policy._home_knowledge_current = True
                pending = session(13273)
                pending.dispatch(pending.current_action, observe_equipment_transactions(board))
                policy._equipment_transaction_session = pending
                policy._store_visit = StoreVisit('equipment-transaction', 'equipment-work',
                    STORE_HOME, StoreVisitPhase.OPERATING, opened_sequence=73,
                    operation_released=True)
                policy._home_entry_operation_posted = True
                declared(policy, pending, awaiting=True)
                key = policy.choose_key(after)
                self.assertEqual(key, '\x1b')
                self.assertEqual(policy._claim_register.current.execution.continuation,
                                 'equipment.next-action')
                policy.confirm_key_posted(key)
                self.assertIsNone(policy._town_holder_structural_stop(
                    policy._claim_register.current, outside))
                self.assertIsNotNone(pending.pending_action)

    def test_successful_deposit_exit_keeps_the_next_item_goal_registered(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, board, pending, target = self.retry_scene(enforced, first=True)
                policy._home_full_retry_deposits = None
                pending.index = 0
                action = pending.current_action
                pending.dispatch(action, replace(observe_equipment_transactions(board), in_home=True))
                declared(policy, pending, awaiting=True)
                policy._store_visit = StoreVisit('equipment-transaction', 'equipment-work',
                    STORE_HOME, StoreVisitPhase.OPERATING, opened_sequence=12,
                    operation_posted=True, operation_released=True)
                # DECLARED CONSTRUCTED 13213/13214 effect boundary: row 13213
                # records advancement, but its board is missing from the copy.
                after = replace(board, store=StoreState(STORE_HOME, [], 240, 0, 12, 240),
                    inventory=tuple(i for i in board.inventory
                        if equipment_identity(i) != action.item_identity))
                policy._home_scan_item_count = 240
                policy._town_store_attempted[STORE_HOME] = board.turn
                key = policy.choose_key(after)
                self.assertEqual(key, 'dm' if enforced else '\x1b')
                self.assertEqual(pending.index, 1)
                self.assertEqual(policy._claim_register.current.execution.continuation,
                                 'equipment.next-action')
                policy.confirm_key_posted(key)
                outside = replace(after, store=None, turn=after.turn + 5)
                self.assertIsNone(policy._town_holder_structural_stop(
                    policy._claim_register.current, outside))
                self.assertIsNone(policy._s33_shadow_verdict(outside, None)['would_stop'])

    def test_stall_termination_releases_old_goal_before_final_validation(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                board = captured_board(DATA['boards']['8403902:player_turn'])
                policy = HengbotPolicy()
                policy.prime(board)
                policy._town_claim_bar_enforced = enforced
                pending = session(13237)
                pending.index = 2
                action = pending.current_action
                observation = replace(observe_equipment_transactions(board), in_home=True)
                self.assertTrue(pending.dispatch(action, observation))
                for _ in range(EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT):
                    pending.observe(observation)
                policy._equipment_transaction_session = pending
                declared(policy, pending)
                key = policy.choose_key(board)
                self.assertTrue(policy.last_reason.endswith('equipment-transaction:confirmation-stall-bound'))
                if not enforced:
                    self.assertIsNone(policy.decision_claim['s33_shadow']['would_stop'])
                self.assertIsNone(policy._s33_shadow_verdict(board, key)['would_stop'])
                self.assertIsNone(policy.decision_claim['violation'])
                self.assertIsNone(policy._equipment_transaction_session)
                self.assertIsNone(policy._claim_register.current.execution.continuation)
