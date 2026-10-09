"""Narrow recorded substrates, not historical continuations.

Capture c decision row 10751 and matching board row 897; capture a decision
row 2521 (its truncated state tail has no matching board). The fixture carries
source paths, physical rows and SHA256 of original row bytes. No checkpoint
exists here. Driver tests reconstruct only arbiter retirement state; the c
route test reconstructs the disclosed Home relocation hold, with an isolated
movement adapter. It stops at the first changed key, consuming no later board.
"""
import tests  # runtime isolation
import ast
import base64
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot import cli
from hengbot.model import parse_snapshot, Position
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from hengbot.town_arbiter import _new_town_turn_arbiter

FIXTURE = Path(__file__).parent / 'fixtures/owner-retirement-slice1-20261006.json.gz'


class Policy:
    def __init__(self):
        self._town_turn_arbiter = _new_town_turn_arbiter()
        self._decision_sequence = 1
        self.last_reason = 'shop:approach'
        self.rank = 10
        self._shopping_approach_goal = Position(4, 5)

    def _town_map_goal_route(self, snapshot, goal):
        return SimpleNamespace(target=goal, remaining_edges=self.rank)


def board(town=1, in_town=True):
    return SimpleNamespace(town_id=town, floor_key=(0, 0, 0), in_town=in_town,
                           store=None, turn=100)


def args(path=None, enabled=True):
    return SimpleNamespace(owner_retired_log_only=enabled, decision_log=path)


def retire(policy, owner='store-router'):
    policy._town_turn_arbiter.retire(owner, ('unchanged',))


class RecordedRetirementTest(unittest.TestCase):
    def pins(self):
        pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        for pin in pins:
            raw = base64.b64decode(pin['decision_row_bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), pin['row_sha256'])
            self.assertEqual(json.loads(raw), pin['decision'])
            if 'board' in pin:
                raw = base64.b64decode(pin['board_row_bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), pin['board_row_sha256'])
                self.assertEqual(json.loads(raw), pin['board'])
        return pins

    def test_hidden_c_and_a_are_logged_and_forgiven_with_original_reason(self):
        for pin in self.pins():
            with self.subTest(capture=pin['capture']), TemporaryDirectory() as root:
                decision = pin['decision']
                self.assertTrue(decision['arbiter']['would_retire'])
                self.assertNotEqual(decision['reason'], 'town:blocked:owner-retired')
                self.assertEqual(pin['physical_row'], 10751 if pin['capture'] == 'c' else 2521)
                self.assertEqual(len(pin['row_sha256']), 64)
                policy = Policy()
                policy.last_reason = decision['reason']
                arbiter = policy._town_turn_arbiter
                arbiter.telemetry = copy.deepcopy(decision['arbiter'])
                # Explicit checkpoint reconstruction of the state the row proves.
                arbiter._retired = {owner: ('unchanged',)
                                    for owner in decision['arbiter']['retirement_set']}
                log = Path(root) / 'decisions.jsonl'
                with patch('sys.stderr', io.StringIO()):
                    key = cli._handle_owner_retirement(args(log), board(), decision['key'], policy)
                self.assertEqual(key, decision['key'])
                self.assertFalse(arbiter.retirement_pending)
                receipt = json.loads(log.with_name('owner-retired-log-only.jsonl').read_text())
                self.assertEqual(receipt['reason'], decision['reason'])
                self.assertEqual(receipt['retirement_reason'], 'town:blocked:owner-retired')
                self.assertTrue(receipt['forgiven'])
                self.assertEqual(receipt['arbiter'], decision['arbiter'])
                self.assertEqual(policy._owner_retired_no_progress_count, 1)
                # Probe telemetry remains for the decision log, but is consumed.
                policy._decision_sequence += 1
                with patch('sys.stderr', io.StringIO()):
                    cli._handle_owner_retirement(args(log), board(), decision['key'], policy)
                self.assertEqual(policy._owner_retired_no_progress_count, 1)

    def test_c_survival_route_interrupts_the_disclosed_home_relocation_hold(self):
        pin = self.pins()[0]
        # The isolated adapter does not inspect monsters. Supply a declared
        # parsing-only lookup, without importing data from another worktree.
        lookup = {monster['race_id']: MonraceKnowledge(1, 110, False, False)
                  for monster in pin['board'].get('detected_monsters', [])
                  if 'race_id' in monster}
        snapshot = parse_snapshot(pin['board'], lookup)
        self.assertTrue(snapshot.player.hungry)
        self.assertEqual(pin['decision']['key'], '5')
        self.assertEqual(pin['decision']['equipment_optimization']['equipment_transaction']['context'], 'home')
        policy = HengbotPolicy()
        policy._shopping_approach_store_type = 5
        policy.last_reason = pin['decision']['reason']
        # No real checkpoint: reconstruct the recorded blocking predicate only.
        # Isolate the movement adapter, rather than inventing later game effects.
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: no checkpoint exists for the live hold; the recorded blocking predicate is reconstructed and only the movement adapter is the subject
        with patch.object(policy, '_equipment_transaction_owns_town_relocation', return_value=True), \
             patch.object(policy, '_atomic_shop_transaction_key', return_value=None), \
             patch.object(policy, '_atomic_home_withdraw_key', return_value=None), \
             patch.object(policy, '_atomic_home_deposit_key', return_value=None), \
             patch.object(policy, '_has_light_equipped', return_value=False), \
             patch.object(policy, '_step_toward', return_value='6'), \
             patch.object(policy, '_stage_shopping_approach_key', return_value='6') as movement:
            key = policy._shopping_approach_key(snapshot, Position(22, 67), 'survival:mana-shop-travel')
        self.assertEqual(key, '6')
        movement.assert_called_once()

    def test_driver_entrance_precedes_empty_result_branch(self):
        tree = ast.parse(Path(cli.__file__).read_text(encoding='utf8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == '_handle_owner_retirement']
        self.assertEqual(len(calls), 1)
        source = Path(cli.__file__).read_text(encoding='utf8').splitlines()
        self.assertIn('if key is None or key == "":', '\n'.join(source[calls[0].lineno:calls[0].lineno + 20]))


class BurstTest(unittest.TestCase):
    def handle(self, policy, snapshot=None, key='5', visit=None):
        with patch('sys.stderr', io.StringIO()):
            result = cli._handle_owner_retirement(args(), snapshot or board(), key, policy, visit)
        policy._decision_sequence += 1
        return result

    def test_two_continue_third_stops_even_with_reason_rewrites_and_forgiveness(self):
        policy = Policy()
        for owner in ['home-visit', 'shop-buy']:
            retire(policy, owner)
            self.assertEqual(self.handle(policy), '5')
            self.assertFalse(policy._town_turn_arbiter.retirement_pending)
        retire(policy, 'town-plan')
        self.handle(policy)
        self.assertEqual(policy.last_reason, 'town:blocked:owner-retired-burst')
        self.assertTrue(cli._policy_final_stop_required(policy))
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
        self.assertTrue(policy._town_turn_arbiter.retirement_pending)
        self.assertIn('three retirements', cli._policy_final_stop_banner(policy.last_reason))

    def test_bookkeeping_retirements_never_count_toward_the_burst(self):
        """Live 2026-10-09 01:01-01:02 (owner-retired-log-only.jsonl, capture
        autorecover-20261009-010300): store-router retired once, then two
        periodic:character-dump retirements of owner misc ended the visit as
        owner-retired-burst during a productive walk."""
        policy = Policy()
        retire(policy, 'store-router')
        self.handle(policy)
        self.assertEqual(policy._owner_retired_no_progress_count, 1)
        policy.last_reason = 'periodic:character-dump'
        for _ in range(3):
            retire(policy, 'misc')
            self.handle(policy)
            self.assertNotEqual(policy.last_reason, 'town:blocked:owner-retired-burst')
            policy.last_reason = 'periodic:character-dump'
        self.assertEqual(policy._owner_retired_no_progress_count, 1)
        # Errand owners still count: two more retirements reach the burst.
        policy.last_reason = 'shop:approach'
        retire(policy, 'store-router'); self.handle(policy)
        retire(policy, 'shop-buy'); self.handle(policy)
        self.assertEqual(policy.last_reason, 'town:blocked:owner-retired-burst')

    def test_labelled_and_empty_hidden_retirements_share_the_same_counter(self):
        policy = Policy()
        policy.last_reason = 'town:blocked:owner-retired'
        self.handle(policy)
        # The harness advances sequence after each driver decision. Check the
        # actual final-stop predicate in the forgiven decision's identity.
        policy._decision_sequence -= 1
        self.assertFalse(cli._policy_final_stop_required(policy))
        policy._decision_sequence += 1
        policy.last_reason = 'shop:one-shot-in-flight'
        retire(policy)
        self.assertEqual(self.handle(policy, key=''), '')
        retire(policy)
        self.assertEqual(self.handle(policy, key=''), '5')
        self.assertEqual(policy.last_reason, 'town:blocked:owner-retired-burst')

    def test_log_only_does_not_forgive_an_independent_final_failure(self):
        policy = Policy()
        retire(policy)
        policy.last_reason = 'town:blocked:survival-mana-no-charges'
        self.handle(policy)
        self.assertEqual(policy.last_reason, 'town:blocked:survival-mana-no-charges')
        self.assertTrue(policy._town_turn_arbiter.retirement_pending)

    def test_hidden_retirement_does_not_swallow_a_typed_contract_stop(self):
        policy = Policy()
        retire(policy)
        policy.last_reason = 'ownership:declaration-missing:survival'
        self.handle(policy)
        self.assertTrue(cli._policy_final_stop_required(policy))
        self.assertTrue(policy._town_turn_arbiter.retirement_pending)

    def test_off_hidden_retirement_has_a_visible_stop(self):
        policy = Policy()
        retire(policy)
        result = cli._handle_owner_retirement(args(enabled=False), board(), '', policy)
        self.assertEqual(result, '5')
        self.assertEqual(policy.last_reason, 'town:blocked:owner-retired')

    def test_observed_store_effect_resets_but_admission_and_ui_changes_do_not(self):
        policy = Policy()
        retire(policy); self.handle(policy)
        retire(policy); self.handle(policy)
        visit = SimpleNamespace(operation_effect_observed=False, posted_sequence=2, store_type=5)
        self.handle(policy, visit=visit)
        self.assertEqual(policy._owner_retired_no_progress_count, 2)
        visit.operation_effect_observed = True
        self.handle(policy, visit=visit)
        self.assertEqual(policy._owner_retired_no_progress_count, 0)
        retire(policy); self.handle(policy, visit=visit)
        self.assertEqual(policy._owner_retired_no_progress_count, 1)
        # Re-reading the same effect never grants another reset.
        self.handle(policy, visit=visit)
        self.assertEqual(policy._owner_retired_no_progress_count, 1)

    def test_admitted_route_new_minimum_resets_but_bounce_and_new_target_do_not(self):
        policy = Policy()
        with patch('hengbot.town_work.current_record', return_value={'work_id': 'route'}):
            self.handle(policy)  # rank 10 baseline earns no credit
            retire(policy); self.handle(policy)
            retire(policy); self.handle(policy)
            policy.rank = 9
            self.handle(policy)
            self.assertEqual(policy._owner_retired_no_progress_count, 0)
            retire(policy); self.handle(policy)
            policy.rank = 10
            self.handle(policy)
            policy.rank = 9
            self.handle(policy)
            self.assertEqual(policy._owner_retired_no_progress_count, 1)
        policy.rank = 8
        self.handle(policy)  # no admitted work receipt
        self.assertEqual(policy._owner_retired_no_progress_count, 1)

    def test_visit_exit_and_town_change_reset_but_store_entry_does_not(self):
        policy = Policy()
        retire(policy); self.handle(policy)
        shop_board = board()
        shop_board.store = SimpleNamespace(store_type=5)
        self.handle(policy, shop_board)
        self.assertEqual(policy._owner_retired_no_progress_count, 1)
        self.handle(policy, board(in_town=False))
        self.handle(policy)
        self.assertEqual(policy._owner_retired_no_progress_count, 0)
        retire(policy); self.handle(policy)
        self.handle(policy, board(town=2))
        self.assertEqual(policy._owner_retired_no_progress_count, 0)


class SurvivalTest(unittest.TestCase):
    def test_safety_cannot_be_retired_by_budget_recurrence_or_transfer(self):
        for reason in ['survival:mana-shop-approach', 'eat', 'no-wait:escape-scroll', 'no-wait:flee']:
            with self.subTest(reason=reason):
                arbiter = _new_town_turn_arbiter()
                arbiter._transfer_exhausted = True
                arbiter._retired['survival'] = ('same',)  # old checkpoint
                arbiter._recurrences[('survival', ('same',))] = 100
                for _ in range(20):
                    self.assertTrue(arbiter.may_select(reason, ('same',)))
                    telemetry = arbiter.observe(in_town=True, reason=reason, progress_vector=('same',))
                    self.assertFalse(telemetry['would_retire'])
                self.assertEqual(arbiter._recurrences[('survival', ('same',))], 100)

    def test_survival_interrupt_freezes_errand_budget_and_returns(self):
        arbiter = _new_town_turn_arbiter()
        arbiter.observe(in_town=True, reason='shop:approach', progress_vector=('same',))
        arbiter.observe(in_town=True, reason='shop:approach', progress_vector=('same',))
        before = copy.deepcopy(arbiter.__dict__)
        arbiter.observe(in_town=True, reason='survival:mana-absorb', progress_vector=('changed',))
        for field in ['_no_progress_by_owner', '_vector_by_owner', '_recurrences', '_last_pair', '_owner', '_tenure']:
            self.assertEqual(arbiter.__dict__[field], before[field])
        arbiter.observe(in_town=True, reason='shop:approach', progress_vector=('same',))
        self.assertEqual(arbiter._no_progress_by_owner['store-router'], 2)

    def test_mutating_selection_refusal_publishes_a_receipt(self):
        arbiter = _new_town_turn_arbiter()
        arbiter._recurrences[('store-router', ('same',))] = 100
        self.assertFalse(arbiter.preview_may_select('shop:approach', ('same',)))
        self.assertFalse(arbiter.retirement_pending)
        self.assertFalse(arbiter.may_select('shop:approach', ('same',)))
        self.assertTrue(arbiter.retirement_pending)
        arbiter.forgive_retirement()
        self.assertFalse(arbiter.retirement_pending)


if __name__ == '__main__':
    unittest.main()
