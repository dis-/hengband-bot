"""Recorded full chooser through the production sender; stop at first new key.

The command wait and source chooser are explicitly protocol controls. The
target is verbatim live evidence; no later board is claimed as its effect.
"""
import tests  # noqa: F401
import copy
import hashlib
import json
from pathlib import Path

import tests.test_classA_observed_input as class_a
import tests.test_input_executor as harness

FIXTURE = Path(__file__).with_name('fixtures') / 'classA3'


class StopAtTarget(harness.FaithfulHookGame):
    def hook(self, request):
        if request['op'] == 'screen' and self.accepted == ['r', 'i', 's']:
            return {'id': request['id'], 'ok': False,
                    'error': 'no post-divergence capture'}, None
        return super().hook(request)


class FullIdentifyPins(harness.ProductionHarness):
    drive = class_a.ClassAObservedInputPins.drive

    def test_recorded_carried_full_target_posts_only_target(self):
        data = (FIXTURE / 'full-target.json').read_bytes()
        self.assertEqual(hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest(),
                         'a1273db71ce717c083fac3f65c20cedcee0358ea31d2f794639ef3acf95a480a')
        screen = json.loads(data)
        board = json.loads((FIXTURE / 'before.json').read_text(encoding='utf-8'))
        # Source selection was already accepted live (r,i). Use a captured
        # scroll source UI; this is a protocol control, not a replayed effect.
        source = class_a.recorded('live15-read-scroll-prompt.json')
        game = StopAtTarget()
        game.state = copy.deepcopy(board)
        game.screen = harness.command_screen(board['turn'])
        game.screens = [source, screen]
        game.states = [copy.deepcopy(board), copy.deepcopy(board)]
        import time
        from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
        from hengbot.model import parse_snapshot
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic()+1).outcome, 'ready')
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
        _send_new_decision_key(port, 'recorded-classA3', 'ris\x1b\x1b', None, set(),
                               decision={'sequence':1126, 'reason':'identify:full'},
                               snapshot=parse_snapshot(board, {}), posting_contract=None, in_store=False)
        self.assertEqual(game.accepted, ['r', 'i', 's'])
        self.assertEqual(port.last_result.operation.continuations, [])
        self.assertEqual(port.last_result.outcome, 'stuck-prompt')

    def test_normal_owner_rejects_recorded_full_target(self):
        screen = json.loads((FIXTURE / 'full-target.json').read_text(encoding='utf-8'))
        game, result = self.drive('rjs', 'identify:device', [
            class_a.recorded('live15-read-scroll-prompt.json'), screen])
        self.assertEqual(game.accepted, ['r', 'j'])
        self.assertEqual(result.outcome, 'stuck-prompt')

    def test_full_owner_rejects_recorded_normal_target(self):
        game, result = self.drive('rjs', 'identify:full', [
            class_a.recorded('live15-read-scroll-prompt.json'),
            class_a.recorded('20-sweep-identify-item-target.json')])
        self.assertEqual(game.accepted, ['r', 'j'])
        self.assertEqual(result.outcome, 'stuck-prompt')
