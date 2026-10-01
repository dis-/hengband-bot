"""Live30 recorded boards/quaff screen through the production sender.

The incident captured no inner staff/identify chooser. Those screens below
are explicitly derived from recorded inventory and production prompt literals.
Address variants stop at the first new target answer. A separate declared
protocol result is not claimed as recorded. The staff-failure command board
is unchanged recorded data.
"""
import tests  # noqa: F401
import copy
import json
import time
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_identification import SOURCE_PROMPT, IDENTIFY_ITEM_PROMPT
import tests.test_input_executor as harness

FIXTURES = Path(__file__).with_name('fixtures') / 'live30-identify-normal'


def load(name):
    return json.loads((FIXTURES / (name + '.json')).read_text(encoding='utf-8'))


def derived_chooser(board, source=True, japanese=True):
    literal = (SOURCE_PROMPT['u'] if source else IDENTIFY_ITEM_PROMPT)[0 if japanese else 1]
    screen = harness.prompt_screen("(持ち物:a-s,'(',')', ESC) " + literal.rstrip()
                                   if japanese else "(Inven:a-s,'(',')', ESC) " + literal.rstrip())
    items = [item for item in board['inventory'] if not source or item['tval'] == 55]
    for index, item in enumerate(items, 1):
        screen['lines'][index] = item['slot'] + ') ' + item['name']
    return screen


class StopAfterNewTarget(harness.FaithfulHookGame):
    def hook(self, request):
        if request['op'] == 'screen' and len(self.accepted) == 3:
            return {'id': request['id'], 'ok': False,
                    'error': 'no post-divergence capture'}, None
        return super().hook(request)


class Live30IdentifyNormalPin(harness.ProductionHarness):
    def send(self, screens, states, *, japanese=True, stop_target=False):
        game = StopAfterNewTarget() if stop_target else harness.FaithfulHookGame()
        game.state = load('before-identify')
        game.screens, game.states = copy.deepcopy(screens), copy.deepcopy(states)
        _, client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, 'ready')
        policy = ConservativePolicy()
        snapshot = parse_snapshot(executor.ready_board, {})
        key = policy._town_item_processing_key(snapshot)
        self.assertEqual((key, policy.last_reason), ('uoq', 'identify:normal'))
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
        _send_decision_key_with_prompt_chain(
            port, 'recorded-live30', key, None, set(), policy=policy,
            shadow_client=client, file=None, deadline=time.monotonic() + 1,
            poll_interval=0, prompt_japanese=japanese,
            decision=dict(sequence=4797, turn=snapshot.turn, reason=policy.last_reason,
                          key=key, prompt_owner_handoff=policy.prompt_owner_handoff),
            snapshot=snapshot, posting_contract=None, in_store=False)
        return game, port.last_result

    def test_recorded_purchase_did_not_shift_staff_or_target(self):
        before, after = load('before-purchase'), load('before-identify')
        self.assertEqual([(item['slot'], item['tval'], item['sval'], item['name']) for item in before['inventory']],
                         [(item['slot'], item['tval'], item['sval'], item['name']) for item in after['inventory']])
        inventory = {item['slot']: item for item in after['inventory']}
        self.assertEqual((inventory['g']['tval'], inventory['g']['sval'], inventory['g']['count']), (70, 11, 10))
        self.assertEqual((inventory['o']['tval'], inventory['o']['sval'], inventory['o']['charges']), (55, 5, 10))
        self.assertEqual((inventory['q']['tval'], inventory['q']['known']), (22, False))

    def test_composer_uses_current_inventory_addresses(self):
        board = load('before-identify')
        # Derived next board with staff and target addresses swapped, leaving
        # their complete recorded identities unchanged.
        board['inventory'][14]['slot'], board['inventory'][15]['slot'] = 'p', 'o'
        board['inventory'][16]['slot'], board['inventory'][17]['slot'] = 'r', 'q'
        policy = ConservativePolicy()
        key = policy._town_item_processing_key(parse_snapshot(board, {}))
        self.assertEqual(key, 'upr')
        chain = policy.peek_staged_prompt_chain()
        self.assertEqual(chain['key'], key)
        self.assertEqual(chain['gates'], ((1, SOURCE_PROMPT['u']), (2, IDENTIFY_ITEM_PROMPT)))

    def test_recorded_staff_failure_drops_q_before_quaff(self):
        before, failed = load('before-identify'), load('staff-failed')
        self.assertIn('杖をうまく使えなかった。', failed['messages'])
        game, result = self.send([derived_chooser(before), harness.command_screen(failed['turn'])], [before, failed])
        self.assertEqual(game.accepted, ['u', 'o'])
        self.assertEqual(result.outcome, 'completed')
        self.assertEqual(result.operation.dropped_continuations, ['q'])

    def test_recorded_quaff_is_divergence_before_target(self):
        before = load('before-identify')
        game, result = self.send([derived_chooser(before), load('recorded-quaff-screen')], [before, load('staff-failed')])
        self.assertEqual(game.accepted, ['u', 'o'])
        self.assertEqual(result.outcome, 'stuck-prompt')
        self.assertIn('phase=continuation', result.reason)

    def test_derived_normal_result_returns_without_blind_dismissal(self):
        before = load('before-identify')
        # Protocol variant only: a successful normal identify returns to the
        # command wait. Its result board is not claimed as a live30 capture.
        identified = copy.deepcopy(before)
        identified['inventory'][16]['known'] = True
        game, result = self.send([derived_chooser(before), derived_chooser(before, False),
                                  harness.command_screen(before['turn'])],
                                 [before, before, identified])
        self.assertEqual(game.accepted, ['u', 'o', 'q'])
        self.assertEqual(result.outcome, 'completed')
        self.assertTrue(result.board['inventory'][16]['known'])
        self.assertEqual(result.operation.continuations, [])

    def test_answers_rebind_at_each_chooser(self):
        before = load('before-identify')
        source = copy.deepcopy(before)
        # Derived address shift: swap the two staff stacks; then swap target
        # with the shovel at the target prompt (e.g. after device unstacking).
        source['inventory'][14]['slot'], source['inventory'][15]['slot'] = 'p', 'o'
        target = copy.deepcopy(source)
        target['inventory'][16]['slot'], target['inventory'][17]['slot'] = 'r', 'q'
        for japanese in (False, True):
            with self.subTest(japanese=japanese):
                game, result = self.send([derived_chooser(source, japanese=japanese),
                                          derived_chooser(target, False, japanese)],
                                         [source, target], japanese=japanese, stop_target=True)
                self.assertEqual(game.accepted, ['u', 'p', 'r'])
                self.assertEqual(result.outcome, 'stuck-prompt')
                self.assertIn('phase=screen', result.reason)
                self.assertEqual(result.operation.continuations, [])

    def test_source_identity_and_visible_address_are_required(self):
        before = load('before-identify')
        for variant in ('wrong-staff', 'missing-row', 'duplicate-identity'):
            with self.subTest(variant=variant):
                board = copy.deepcopy(before)
                if variant == 'wrong-staff':
                    board['inventory'][14]['sval'] = 1
                    board['inventory'][14]['name'] = 'Staff of Darkness'
                if variant == 'duplicate-identity':
                    duplicate = copy.deepcopy(board['inventory'][14])
                    duplicate['slot'] = 't'
                    board['inventory'].append(duplicate)
                screen = derived_chooser(board)
                if variant == 'missing-row':
                    screen['lines'][1] = ''
                game, result = self.send([screen], [board])
                self.assertEqual(game.accepted, ['u'])
                self.assertEqual(result.outcome, 'stuck-prompt')

    def test_target_identity_collection_and_visible_address_are_required(self):
        before = load('before-identify')
        for variant in ('replaced-target', 'missing-row', 'equipment-page', 'wrong-prompt'):
            with self.subTest(variant=variant):
                board = copy.deepcopy(before)
                if variant == 'replaced-target':
                    board['inventory'][16]['name'] = 'A different halberd'
                screen = derived_chooser(board, False)
                if variant == 'missing-row':
                    screen['lines'][17] = ''
                if variant == 'equipment-page':
                    screen['lines'][0] = '(Equip:a-s, ESC) Identify which item?'
                if variant == 'wrong-prompt':
                    screen['lines'][0] = '(Inven:a-s, ESC) *Identify* which item?'
                game, result = self.send([derived_chooser(before), screen], [before, board])
                self.assertEqual(game.accepted, ['u', 'o'])
                self.assertEqual(result.outcome, 'stuck-prompt')

    def test_missing_target_without_failure_evidence_stops(self):
        before = load('before-identify')
        game, result = self.send([derived_chooser(before), harness.command_screen(before['turn'])], [before, before])
        self.assertEqual(game.accepted, ['u', 'o'])
        self.assertEqual(result.outcome, 'stuck-prompt')
        self.assertIn('expected prompt absent', result.reason)
