"""13:42 recorded boards with explicitly constructed Home ownership walls.

No checkpoint or complete Home catalogue was recorded. Boards and decisions
are verbatim; the fresh charged-device catalogue and held executor requests
are constructed, never described as captured stock or continuous replay.
"""
import tests  # noqa: F401 -- isolate all runtime writes
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from hengbot.home_visit import HomeVisitExecutor, HomeVisitKind, HomeVisitRequest, HomeVisitState
from hengbot.home_errand import HomeErrandRequest, HomeErrandState
from hengbot.claim_register import reach
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import parse_snapshot, TVAL_WAND, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO, WAIT_KEY
from policy_fixtures import item

FIXTURE = Path(__file__).parent / 'fixtures/mana-home-20261005.json.gz'


class ManaHomeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
            'cf5dd406e406370d03fdeeb9cff631ad7a73e57e9ecc6ea8c0fbe6322e220ca3')
        cls.data = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def wall(self, row=1804, *, catalogue=True, owner='home-deposit'):
        board = parse_snapshot(next(x['raw'] for x in self.data['boards']
                                    if x['source'] == 'state.jsonl.gz' and x['row'] == row))
        policy = HengbotPolicy()
        policy._observe(board)
        policy.consume_skill_knowledge(next(x['raw'] for x in self.data['knowledge']
                                            if x['source'] == 'state.jsonl.gz' and x['row'] == 1796))
        # CONSTRUCTED supplier premise. Captured pages do not prove either
        # presence or absence of a charged device on the unobserved shelves.
        device = item('h', TVAL_WAND, 1, charges=12, name='CONSTRUCTED Home wand')
        if catalogue:
            policy.consume_home_knowledge((device,))
            policy._home_page_size = 52
        old = HomeVisitRequest(HomeVisitKind.DEPOSIT, owner,
                               ('CONSTRUCTED suspended deposit', 55, 5))
        policy._home_visit.file(old)
        policy._home_visit.begin_approach(0)
        policy._home_visit.observe_outside_ready(('CONSTRUCTED old page',), 0)
        return policy, board, device, old

    def test_recorded_before_both_captures_blocked(self):
        for number, turn in ((8935, 11699160), (8942, 11699170)):
            raw = next(x['raw'] for x in self.data['decisions'] if x['row'] == number)
            self.assertEqual(raw['turn'], turn)
            self.assertEqual(raw['reason'], 'town:blocked:survival-mana-no-charges')
            self.assertEqual(raw['player']['gold'], 6315)
            self.assertEqual(raw['player']['food_state'], 'hungry')
            self.assertEqual(raw['home_route_refusal']['executor_state'], 'EXIT_PENDING')
            self.assertFalse(raw['equipment_optimization']['home_procurement']['home_visit_filed'])

    def test_recorded_after_public_decision_withdraws_under_survival(self):
        for row in (1792, 1804):
            for enforced in (False, True):
                with self.subTest(row=row, enforced=enforced):
                    policy, board, device, old = self.wall(row)
                    policy._town_claim_bar_enforced = enforced
                    # CONSTRUCTED registered deposit route with its original
                    # rank. It must be suspended with its id and goal intact.
                    held = policy._claim_register.declare('home-visit', reach((45, 125)))
                    policy._claim_register._claim = replace(
                        held, rank=64, rung='_home_disposal_processing_key')
                    self.assertEqual(policy._count_mana_food_uses(board), 0)
                    self.assertEqual(policy.choose_key(board), '5pa\x1b')
                    self.assertEqual(policy.last_reason, 'survival:mana-home-withdraw')
                    self.assertEqual(policy._home_visit.request.requester, 'survival')
                    self.assertEqual(policy._home_visit.operation, ('take', policy._item_signature(device)))
                    self.assertEqual(policy._claim_register.current.owner.value, 'survival')
                    self.assertEqual(policy._claim_register.current.execution.producer, 'survival')
                    self.assertEqual(policy._home_visit.queued, [old])
                    self.assertEqual(policy._claim_register.suspended[-1].claim_id, held.claim_id)
                    self.assertEqual(policy._claim_register.suspended[-1].goal, held.goal)

    def test_restored_policy_refiles_missing_executor_for_survival(self):
        policy, board, _device, _old = self.wall(catalogue=False)
        policy._home_visit = None
        self.assertEqual(policy._mana_food_survival_override_key(board), HOME_KNOWLEDGE_MACRO)
        self.assertEqual(policy._home_visit.request.requester, 'survival')

    def test_recorded_stale_catalogue_scans_before_deposit_or_purchase(self):
        policy, board, device, old = self.wall(catalogue=False)
        self.assertEqual(policy._mana_food_survival_override_key(board), HOME_KNOWLEDGE_MACRO)
        self.assertEqual(policy.last_reason, 'survival:mana-home-scan')
        self.assertEqual(policy._home_visit.request.kind, HomeVisitKind.SCAN)
        self.assertEqual(policy._home_visit.request.requester, 'survival')
        self.assertEqual(policy._home_visit.queued, [old])
        self.assertIsNone(policy._home_procurement_fallthrough)
        policy._home_knowledge_scan_inflight = True
        self.assertEqual(policy._mana_food_survival_override_key(board), WAIT_KEY)
        policy._home_knowledge_scan_inflight = False
        policy.consume_home_knowledge((device,))
        policy._home_page_size = 52
        self.assertEqual(policy._mana_food_survival_override_key(board), '5pa\x1b')
        self.assertEqual(policy.last_reason, 'survival:mana-home-withdraw')
        self.assertEqual(policy._home_visit.queued, [old])

    def test_recorded_open_page_yields_to_survival(self):
        policy, _board, _device, _old = self.wall(catalogue=False)
        board = parse_snapshot(next(x['raw'] for x in self.data['knowledge']
                                    if x['source'].startswith('autorecover') and x['row'] == 47))
        self.assertEqual(board.store.stock_num, 239)
        self.assertEqual(policy.choose_key(board), '\x1b')
        self.assertEqual(policy.last_reason, 'survival:mana-leave-wrong-store')
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertFalse(policy._home_knowledge_current)

    def test_suspended_errand_item_and_quantity_survive_absorption(self):
        policy, board, device, old = self.wall(owner='home-errand:recall')
        pending = ('CONSTRUCTED recall stock', TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        policy._home_pending_item = pending
        policy._home_pending_quantity = 4
        policy._home_pending_quantities[pending] = 4
        policy._home_errand.file(HomeErrandRequest(pending, 4, 'test', 'recall'), knowledge_current=True)
        self.assertEqual(policy._mana_food_survival_override_key(board), '5pa\x1b')
        self.assertEqual(policy._home_pending_item, pending)
        self.assertEqual(policy._home_pending_quantity, 4)
        self.assertEqual(policy._home_pending_quantities[pending], 4)
        acquired = replace(board, turn=board.turn + 1,
                           inventory=[*board.inventory, replace(device, slot='z')])
        # CONSTRUCTED successful effect, not a historical response to new input.
        policy._observe_home_atomic_withdrawal_outside(acquired)
        self.assertEqual(policy._mana_food_survival_override_key(acquired), 'Ez')
        self.assertEqual(policy.last_reason, 'survival:mana-absorb')
        report = policy._home_visit.consume_report()
        self.assertEqual((report.request.requester, report.outcome), ('survival', 'completed'))
        self.assertEqual(policy._home_visit.request, old)
        self.assertEqual(policy._home_pending_item, pending)
        self.assertEqual(policy._home_pending_quantity, 4)
        self.assertTrue(policy._home_errand.active)
        fed = replace(acquired, player=replace(acquired.player, food_state='normal'))
        self.assertIsNone(policy._mana_food_survival_override_key(fed))
        self.assertTrue(policy._ensure_home_visit_request(fed))
        self.assertEqual(policy._home_visit.request.requester, 'home-errand:recall')

    def test_survival_does_not_post_or_complete_same_device_errand(self):
        policy, board, device, _old = self.wall()
        signature = policy._item_signature(device)
        policy._home_pending_item = signature
        policy._home_pending_quantity = 4
        policy._home_pending_quantities[signature] = 4
        policy._home_errand.file(HomeErrandRequest(signature, 4, 'test', 'device'), knowledge_current=True)
        self.assertEqual(policy._mana_food_survival_override_key(board), '5pa\x1b')
        self.assertEqual(policy._home_errand.state, HomeErrandState.COMPOSABLE)
        acquired = replace(board, turn=board.turn + 1,
                           inventory=[*board.inventory, replace(device, slot='z')])
        policy._observe_home_atomic_withdrawal_outside(acquired)
        self.assertEqual(policy._home_errand.state, HomeErrandState.COMPOSABLE)
        self.assertEqual(policy._home_pending_item, signature)
        self.assertEqual(policy._home_pending_quantity, 4)
        self.assertEqual(policy._home_pending_quantities[signature], 4)
        self.assertIsNone(policy._home_pending_take_confirmed)
        self.assertEqual(policy._mana_food_survival_override_key(acquired), 'Ez')

    def test_equipment_withdrawal_stays_pending_while_survival_takes_device(self):
        policy, board, _device, _old = self.wall()
        action = EquipmentTransaction('home_prepare', 'withdraw', 'CONSTRUCTED weapon',
                                      item_identity='CONSTRUCTED equipment identity')
        session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 21))
        policy._equipment_transaction_session = session
        self.assertEqual(policy._mana_food_survival_override_key(board), '5pa\x1b')
        self.assertIs(policy._equipment_transaction_session, session)
        self.assertIs(session.current_action, action)
        self.assertIsNone(session.pending_action)
        self.assertEqual(policy.last_reason, 'survival:mana-home-withdraw')

    def test_posted_deposit_waits_for_bounded_observation_then_scans(self):
        policy, board, _device, _old = self.wall(catalogue=False)
        visit = policy._home_visit
        visit.record_operation('put', visit.request.item_identity, 0)
        visit.post_exit()
        # CONSTRUCTED full-Home refusal, matching the captured unresolved exit.
        policy._home_atomic_deposit_pending = (
            ((policy._item_signature(board.inventory[0]), board.inventory[0].count, 1),), None, board.turn - 1, 0)
        policy._home_full_refused = True
        self.assertEqual(policy._mana_food_survival_override_key(board), WAIT_KEY)
        self.assertEqual(policy.last_reason, 'survival:mana-home-await-operation')
        for _ in range(10):
            policy._observe_home_atomic_deposit_outside(board)
            if policy._home_atomic_deposit_pending is None:
                break
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertIsNotNone(policy._home_full_relief)
        self.assertEqual(policy._mana_food_survival_override_key(board), HOME_KNOWLEDGE_MACRO)
        self.assertEqual(policy._home_visit.request.requester, 'survival')
        self.assertIsNotNone(policy._home_full_relief)

    def test_posted_registered_observer_keeps_owner_until_effect(self):
        from test_s33_shadow_zero import attach_claim, attach_visit
        policy, board, _device, _old = self.wall(catalogue=False)
        raw = next(x['raw'] for x in self.data['decisions'] if x['row'] == 8934)
        held = attach_claim(policy, raw['claim'])
        attach_visit(policy, raw)
        policy._town_claim_bar_enforced = True
        policy._decision_sequence = 2534
        # CONSTRUCTED current emitter declaration for already-sent input.
        policy._claim_register._claim = replace(held, execution=replace(
            held.execution, state='awaiting', operation_ref='decision:2534', next_step=None))
        visit = policy._home_visit
        visit.record_operation('put', visit.request.item_identity, 0)
        visit.post_exit()
        carried = board.inventory[0]
        policy._home_atomic_deposit_pending = (
            ((policy._item_signature(carried), carried.count, 1),), None, board.turn, 0)
        policy._home_entry_operation_posted = True
        self.assertIsNotNone(policy.choose_key(board))
        self.assertEqual(policy._claim_register.current.owner.value, 'home-visit')
        self.assertEqual(policy._claim_register.current.claim_id, held.claim_id)
        self.assertEqual(policy._home_visit.request.requester, 'home-deposit')
        self.assertIsNotNone(policy._home_atomic_deposit_pending)

    def test_shortened_address_prefix_earns_scan(self):
        policy, board, _device, _old = self.wall()
        policy._home_knowledge_valid_before = 0
        self.assertEqual(policy._mana_food_survival_override_key(board), HOME_KNOWLEDGE_MACRO)
        self.assertFalse(policy._home_knowledge_current)
        self.assertIsNone(policy._home_atomic_withdraw_pending)


class SurvivalHomeExecutorTest(unittest.TestCase):
    def test_handover_resumes_each_unposted_owner_without_budget_reset(self):
        for owner in ('home-deposit', 'home-full-relief', 'home-errand:recall', 'equipment-transaction'):
            for state in (HomeVisitState.FILED, HomeVisitState.APPROACHING, HomeVisitState.OBSERVING):
                with self.subTest(owner=owner, state=state):
                    executor = HomeVisitExecutor(8)
                    old = HomeVisitRequest(HomeVisitKind.DEPOSIT, owner, ('old', 1))
                    new = HomeVisitRequest(HomeVisitKind.WITHDRAW, 'survival', ('device', 2))
                    executor.file(old)
                    if state != HomeVisitState.FILED:
                        executor.begin_approach(1)
                    if state == HomeVisitState.OBSERVING:
                        executor.observe_outside_ready(('old page',), 2)
                    before = executor.attempts_used
                    self.assertEqual(executor.file_survival(new), 'active')
                    self.assertEqual(executor.queued, [old])
                    self.assertIsNone(executor.fresh_evidence)
                    self.assertTrue(executor.begin_approach(3))
                    self.assertEqual(executor.attempts_used, before + (state == HomeVisitState.FILED))
                    executor.observe_outside_ready(('fresh device address',), 4)
                    self.assertTrue(executor.record_operation('take', new.item_identity, 4))
                    executor.post_exit()
                    executor.observe_outside(effect_observed=True)
                    self.assertEqual(executor.consume_report().request, new)
                    self.assertEqual(executor.request, old)
                    self.assertTrue(executor.begin_approach(5))
                    executor.observe_outside_ready(('fresh deposit address',), 6)
                    self.assertTrue(executor.record_operation('put', old.item_identity, 6))
                    executor.post_exit()
                    executor.observe_outside(effect_observed=True)
                    self.assertEqual(executor.consume_report().request, old)

    def test_posted_input_cannot_be_handed_over(self):
        for state in (HomeVisitState.ENTRY_PENDING, HomeVisitState.OPERATING, HomeVisitState.EXIT_PENDING):
            executor = HomeVisitExecutor(8)
            old = HomeVisitRequest(HomeVisitKind.DEPOSIT, 'home-deposit', ('old', 1))
            executor.file(old)
            executor.state = state
            self.assertEqual(executor.file_survival(
                HomeVisitRequest(HomeVisitKind.SCAN, 'survival')), 'pending')
            self.assertEqual(executor.request, old)
            self.assertEqual(executor.state, state)
            self.assertEqual(executor.queued, [])


if __name__ == '__main__':
    unittest.main()
