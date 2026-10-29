"""#47 high-level retirement pins through choose_key and the follow executor.

ATTACH BOUNDARY: these captures have diagnostic JSON, not Python checkpoints.
The immutable Home board/catalogue and skill reply are recorded. A one-action
session reconstructs exactly the recorded transaction_next takeoff; earlier
transaction actions, calibration and driver retirement counters are not replayed.
Executor replies after the first divergent action are explicitly constructed.
"""
import tests  # noqa: F401 -- runtime isolation

import copy
import gzip
import io
import json
from pathlib import Path
import time

from hengbot.cli import _ExecutorInputPort, _send_decision_key_with_prompt_chain, PostingContract
from hengbot.equipment_capacity import release_unaffordable_session
from hengbot.equipment_optimizer import Loadout, OwnedEquipment, equipment_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import _parse_items, InventoryItem, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_equipment import plan_equipment_transactions
import tests.test_input_executor as executor_harness
from tests.test_resume_inside_store import _fit

FIXTURE = Path(__file__).parent / 'fixtures/retired-burst-high-20261029.json.gz'


class RetiredBurstHighTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def attach(self, case):
        policy = HengbotPolicy()
        for row in case['knowledge'].values():
            if row['knowledge']['category'] == 'home':
                policy.consume_home_knowledge(tuple(_parse_items(
                    row['knowledge']['items'], protocol=row.get('protocol_version', 3))))
            elif row['knowledge']['category'] == 'skill_exp':
                policy.consume_skill_knowledge(row)
        raw = copy.deepcopy(case['inputs'][0]['board'])
        board = parse_snapshot(raw)
        policy.prime(board)
        # DECLARED CONSTRUCTED: the startup skill probe is already settled.
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        facts = case['inputs'][0]['decision']['equipment_optimization']
        action = facts['transaction_next']
        worn = next(item for item in board.equipment if item.slot == action['target_slot'])
        self.assertEqual(action['item_id'].split(':')[1], equipment_identity(worn))
        takeoff = EquipmentTransaction(
            action['phase'], action['kind'], action['item_id'],
            action['target_slot'], equipment_identity(worn))
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((takeoff,), (), len(board.inventory) + 1),
            physical_context='home')
        return policy, board, raw

    def post_exit(self, policy, board, raw, key):
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_harness.store_screen()
        game.screen['turn'] = raw['turn']
        # DECLARED CONSTRUCTED: render this recorded Home page using the
        # game's slot/name columns and an expanded terminal for all 52 slots.
        game.screen.update(height=80, lines=[''] * 80)
        game.screen['lines'][60] = 'You may: g) Get an item. d) Drop an item.'
        game.screen['lines'][61] = ' ESC) Exit from Building.'
        game.screen['cursor'] = {'visible': True, 'y': 60, 'x': 0}
        for index, item in enumerate(raw['store']['items']):
            game.screen['lines'][6 + index] = item['letter'] + ') ' + _fit(item['name'], 64)
        game.jsonl = [copy.deepcopy(raw)]
        # DECLARED CONSTRUCTED: successful Escape returns this same inventory
        # and equipment on the outside command boundary, with no capacity credit.
        after = copy.deepcopy(raw)
        after.pop('store')
        after['type'] = 'player_turn'
        after['turn'] += 1
        game.states = [after]
        game.screens = [executor_harness.command_screen(after['turn'])]
        _, _, executor = self.make(game)
        boundary = executor.observe_boundary(deadline=time.monotonic() + 10)
        self.assertEqual(boundary.outcome, 'ready', boundary)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, 'retired-burst-high', key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False, snapshot=board, in_store=True,
            decision={'sequence': policy._decision_sequence, 'reason': policy.last_reason},
            posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result)
        self.assertEqual(port.last_result.outcome, 'completed')
        self.assertEqual(game.accepted, ['\x1b'])
        self.assertFalse(game.term_fifo)
        return after

    def test_each_equipment_capture_releases_the_refused_work_before_follow_exit(self):
        fixed = [case for case in self.cases if case['fixed_group']]
        self.assertEqual(len(fixed), 3)
        for case in fixed:
            with self.subTest(source=case['source']):
                policy, board, raw = self.attach(case)
                self.assertGreaterEqual(len(board.inventory), 19)
                key = policy.choose_key(board)
                self.assertEqual(key, '\x1b')
                self.assertIsNone(policy._equipment_transaction_session)
                self.assertFalse(policy._equipment_transaction_home_work())
                self.assertFalse(policy._equipment_transaction_failed_items)
                self.assertFalse(policy.last_reason.startswith('town:blocked:'))
                after = self.post_exit(policy, board, raw, key)
                next_key = policy.choose_key(parse_snapshot(after))
                self.assertIsNotNone(next_key)
                self.assertFalse(policy.last_reason.startswith(('town:blocked:', 'equipment-transaction:approach')))
                self.assertIsNone(policy._equipment_transaction_session)

    def test_replanning_keeps_posted_work_and_restoration_debt_with_the_owner(self):
        case = next(case for case in self.cases if case['fixed_group'])
        for posted in (False, True):
            with self.subTest(posted=posted):
                policy, board, _ = self.attach(case)
                session = policy._equipment_transaction_session
                if posted:
                    # DECLARED CONSTRUCTED: a previously posted action awaits
                    # its causal barrier; this is not a new unposted refusal.
                    session._dispatched = session.current_action
                else:
                    policy._equipment_transaction_owned_items = [('restore-me', 'body')]
                release_unaffordable_session(policy, board)
                self.assertIs(policy._equipment_transaction_session, session)

    def test_town_planner_uses_the_mutation_budget_without_blocking_empty_plans(self):
        # DECLARED CONSTRUCTED: one worn armour, one Home replacement.
        def gear(name, origin):
            return OwnedEquipment(name, InventoryItem(
                slot=name, name=name, count=1, tval=36, sval=1,
                known=True, aware=True, fully_known=True, is_equipment=True), origin)
        old, new = gear('old', 'equipped'), gear('new', 'home')
        current = Loadout((('body', old),), 'empty')
        target = Loadout((('body', new),), 'empty')
        args = (old, new), current, target
        plan = plan_equipment_transactions(*args, current_pack_items=19, home_scan_complete=True)
        self.assertFalse(plan.executable)
        self.assertTrue(any(b.startswith('pack-space-required:') for b in plan.blockers))
        roomy = plan_equipment_transactions(*args, current_pack_items=17, home_scan_complete=True)
        self.assertTrue(roomy.executable)
        self.assertLessEqual(roomy.peak_pack_items, 19)
        empty = plan_equipment_transactions((old,), current, current,
                                           current_pack_items=22, home_scan_complete=True)
        self.assertTrue(empty.executable)
        self.assertEqual(empty.actions, ())
