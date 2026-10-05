"""Slice-0 coverage controls. All sends use a fake executor/transport."""
import tests  # noqa: F401 -- isolate runtime files
import ast
import json
import gzip
import hashlib
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot.cli import _ExecutorInputPort
from hengbot.input_executor import Operation, OperationExecutor, Transport
from hengbot.policy import HengbotPolicy
from hengbot.town_work import (UNMAPPED, current_record, driver_record, manifest,
                              receipts, town_work_decision, validate_emit, work_record,
                              bind_driver_override)
from test_policy import Snapshot, grid, player
from hengbot.model import Position

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import town_work_manifest as generator
from ownership_on_corpus import MANIFEST, read_json, run_window


def board():
    return Snapshot(player(1, 1), {Position(1, 1): grid(1, 1)}, [],
                    floor_key=(0, 0, 0), town_flag=True)


class TownWorkContractTest(unittest.TestCase):
    def test_single_validator_denies_absent_wrong_key_and_unknown_work(self):
        source = 'policy_town.py:TownMixin._town_destroy_key'
        record = work_record(source, 'k', sequence=1)
        for context in (board(), {'floor': {'in_town': True}}, {'store': {}}):
            for missing in (None, dict(record, producer='unknown'), dict(record, key='x')):
                receipt = validate_emit(context, 'k', missing, seam='control')
                self.assertFalse(receipt['valid'])
                self.assertEqual(receipt['reason'], UNMAPPED)
            self.assertTrue(validate_emit(context, 'k', record, seam='control')['valid'])
        for key in (None, ''):
            self.assertTrue(validate_emit(board(), key, None, seam='poll')['valid'])
        self.assertTrue(validate_emit({'floor': {'in_town': False}}, 'k', None, seam='dungeon')['valid'])

    def test_unknown_returning_child_cannot_borrow_decision_wrapper(self):
        # Construct a new policy producer with a real repo filename/namespace.
        namespace = {'__name__': 'hengbot.policy'}
        exec(compile('def new_town_work(self, snapshot):\n return "5"\n',
                     str(Path(HengbotPolicy.choose_key.__code__.co_filename).with_name('policy.py')),
                     'exec'), namespace)
        policy = HengbotPolicy()
        with patch.object(policy, '_choose_key', namespace['new_town_work'].__get__(policy)):
            key = policy.choose_key(board())
        # Shadow failure is recorded; no command or reason is changed by it.
        self.assertEqual(key, '5')
        final = receipts(policy)[-1]
        self.assertEqual(final['reason'], UNMAPPED)
        self.assertIn('new_town_work', final['producer'])
        self.assertIsNone(current_record(policy, key))

    def test_scope_restores_profiler_on_exception_and_dungeon_is_unprofiled(self):
        def broken(policy, snapshot):
            raise RuntimeError('control')
        previous = sys.getprofile()
        policy = HengbotPolicy()
        with self.assertRaises(RuntimeError):
            town_work_decision(broken)(policy, board())
        self.assertIs(sys.getprofile(), previous)
        self.assertEqual(receipts(policy), [])

    def test_driver_unknown_key_records_failure_and_preserves_submission(self):
        seen = []
        observed = []
        executor = SimpleNamespace(active=object(), ready_board={'floor': {'in_town': True}},
                                   client=None, submit=lambda op, **kw:
                                   (seen.append(op) or SimpleNamespace(outcome='completed')))
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=1,
                                  work_receipt=observed.append)
        port('\x1b', decision={'sequence': 3, 'reason': 'constructed-override'})
        self.assertEqual(seen[0].keys, '\x1b')
        self.assertIsNone(seen[0].work_record)
        self.assertEqual(observed[-1]['reason'], UNMAPPED)
        # Concrete live caller mapping covers the LEAVE override and prompt clear.
        for key in ('\x1b', '\x1b\x1b', ' '):
            record = driver_record(None, key, site='cli.py:main', sequence=3)
            receipt = validate_emit(executor.ready_board, key, record, seam='driver-control')
            self.assertTrue(receipt['valid'])

    def test_normal_driver_cannot_forge_parent_but_override_and_prefix_inherit(self):
        captured = []
        observed = []
        executor = SimpleNamespace(active=object(), ready_board={'floor': {'in_town': True}},
                                   client=None, submit=lambda op, **kw:
                                   (captured.append(op) or SimpleNamespace(outcome='completed')))
        policy = HengbotPolicy()
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=1,
                                  policy=policy, work_receipt=observed.append)
        namespace = {'__name__': 'hengbot.cli'}
        exec(compile('def _send_new_decision_key(send, key, original):\n'
                     ' return send(key, decision={"key": original})\n',
                     str(Path(__file__).resolve().parents[1] / 'src/hengbot/cli.py'), 'exec'), namespace)
        emit = namespace['_send_new_decision_key']
        emit(port, 'p', 'pa')
        self.assertEqual(observed[-1]['reason'], UNMAPPED)
        bind_driver_override(policy, 'pa', site='cli.py:main')
        emit(port, 'p', 'pa')
        self.assertTrue(observed[-1]['valid'])
        self.assertEqual(captured[-1].work_record['key'], 'p')
        bind_driver_override(policy, '\x1b', site='cli.py:main')
        emit(port, '\x1b', '\x1b')
        self.assertTrue(observed[-1]['valid'])
        self.assertEqual(captured[-1].keys, '\x1b')

    def test_executor_tail_and_prompt_clear_share_validator_for_tcp_and_wm(self):
        for transport in (Transport.TCP, Transport.WM):
            for parent in (None, driver_record(None, 'pa', site='cli.py:main', sequence=2)):
                from hengbot.control_client import KeyPostStatus
                executor = OperationExecutor(SimpleNamespace(post_keys=lambda *a, **k:
                    SimpleNamespace(status=KeyPostStatus.ACCEPTED, reason=None)))
                executor.active = Operation(2, 'constructed-purchase', 'pa',
                                            {'floor': {'in_town': True}}, transport=transport,
                                            work_record=parent)
                executor.active.timing = executor._new_timing()
                # Only the transport is stubbed, preserving the actual logical
                # post seam used by _after_post's prompt/tail continuations.
                with patch.object(executor, '_post_wm', return_value='posted'), \
                     patch.object(executor, '_after_post', return_value='posted'):
                    # Mapped continuation caller; exact live source site is pinned.
                    namespace = {'__name__': 'hengbot.input_executor'}
                    code = ('class OperationExecutor:\n'
                            ' def _after_post(self, key):\n'
                            '  return self._post_and_barrier(key, 1, role="answer")\n')
                    exec(compile(code, str(Path(__file__).resolve().parents[1] /
                                          'src/hengbot/input_executor.py'), 'exec'), namespace)
                    namespace['OperationExecutor']._after_post(executor, 'a')
                receipt = executor.work_receipts[-1]
                self.assertEqual(receipt['valid'], parent is not None)
                self.assertEqual(receipt['reason'], None if parent else UNMAPPED)
                if parent:
                    self.assertEqual(receipt['work']['work_id'], parent['work_id'])

    def test_manifest_has_zero_unmapped_and_unknown_additions_fail(self):
        self.assertEqual(generator.check_repository(), [])
        reviewed = json.loads(generator.REVIEW.read_text(encoding='utf8'))
        source = generator.sources()
        mutant = dict(source)
        # A new reachable producer must require its own review entry.
        tree = ast.parse(mutant['policy.py'])
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'HengbotPolicy')
        choose = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_choose_key')
        choose.body.insert(0, ast.parse('return self.new_town_work(snapshot)').body[0])
        cls.body.append(ast.parse('def new_town_work(self, snapshot):\n return "5"').body[0])
        mutant['policy.py'] = ast.unparse(ast.fix_missing_locations(tree))
        with self.assertRaisesRegex(ValueError, 'unmapped.*new_town_work'):
            generator.generate(mutant, reviewed)
        original = generator.generate(source, reviewed)
        mutant = dict(source)
        mutant['cli.py'] = mutant['cli.py'].replace('key = LEAVE_STORE_KEY', 'key = "x"', 1)
        self.assertNotEqual(generator.generate(mutant, reviewed), original)

    def test_recorded_versioned_corpus_has_zero_unmapped_receipts(self):
        results = []
        original = HengbotPolicy.choose_key
        def choose(policy, snapshot):
            key = original(policy, snapshot)
            rows = receipts(policy)
            results.extend(rows)
            self.assertFalse([r for r in rows if r['reason']], rows)
            return key
        corpus = read_json(MANIFEST)
        windows = []
        with patch.object(HengbotPolicy, 'choose_key', choose):
            for window in corpus['windows']:
                with self.subTest(window=window['name']), TemporaryDirectory(prefix='slice0-corpus-') as raw:
                    result = run_window(window, Path(raw))
                    windows.append(dict(name=result.window, rows=result.rows_replayed,
                                        matched=result.matched_rows, first_divergence=result.first_divergence))
        self.assertGreater(sum(r['required'] for r in results), 0)
        destination = os.environ.get('TOWN_WORK_CORPUS_RESULTS')
        if destination:
            Path(destination).write_text(json.dumps(dict(schema=1, windows=windows,
                receipts=len(results), required=sum(r['required'] for r in results),
                unmapped=sum(bool(r['reason']) for r in results)), indent=2) + '\n', encoding='utf8')

    def test_both_captures_all_complete_boards_and_recorded_producers(self):
        from ownership_on_corpus import new_policy, monraces
        from hengbot.model import parse_snapshot
        fixture = Path(__file__).parent / 'fixtures/town-work-slice0-captures-20261006.json.gz'
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),
                         '8baa913dd11de1a3ff11b6372cfcb191e8ee51fa2f8620cbe76aed4c94c735f6')
        data = json.loads(gzip.decompress(fixture.read_bytes()))
        results = []
        for capture in data['captures']:
            self.assertEqual(capture['skipped_partial_rows'], [1])
            mapped = []
            recorded_receipts = []
            for recorded in capture['decisions']:
                rung = recorded['rung'] or ''
                execution = recorded['execution'] or {}
                method = execution.get('producer_entry') or rung.split('#')[0]
                candidates = [s for s, e in manifest().items()
                              if s.endswith('.' + method) and e['classification'] != 'data']
                if rung.startswith(('town-errand:', 'fallback:')):
                    candidates = ['policy.py:HengbotPolicy._choose_key']
                self.assertTrue(candidates, (capture['name'], recorded))
                source = candidates[0]
                work = work_record(source, recorded['key'], sequence=recorded['sequence'],
                                   work_id=execution.get('work_id') or
                                   f'reconstructed:{capture["name"]}:{recorded["physical_row"]}')
                if work:
                    work['reconstructed'] = True
                context = {'floor': {'in_town': True}}
                receipt = validate_emit(context, recorded['key'], work,
                                        seam='recorded-producer-reconstruction', producer=source)
                self.assertTrue(receipt['valid'], receipt)
                recorded_receipts.append(receipt)
                if recorded['key']:
                    self.assertEqual(validate_emit(context, recorded['key'], None,
                                                   seam='recorded-no-work-control')['reason'], UNMAPPED)
                mapped.append(dict(physical_row=recorded['physical_row'], rung=rung,
                                   mapped_candidates=candidates, reconstructed=True))
            count = required = 0
            unmapped = []
            first = None
            reasons = {}
            for captured in capture['boards']:
                # Independent reconstructed baseline; never credit an earlier
                # control or treat this board as its historical response.
                with TemporaryDirectory(prefix='slice0-capture-') as raw:
                    policy = new_policy(Path(raw))
                    snapshot = parse_snapshot(captured['board'], monraces())
                    if captured['skill_baseline'] is not None:
                        # Only previously recorded skill evidence within the
                        # same uninterrupted town/level span. Prime a baseline;
                        # do not fake a command or deliver any future response.
                        policy.prime(snapshot)
                        skill = capture['skill_knowledge'][captured['skill_baseline']]
                        self.assertLess(skill['physical_row'], captured['physical_row'])
                        policy.consume_skill_knowledge(skill['data'])
                    key = policy.choose_key(snapshot)
                    reasons[policy.last_reason] = reasons.get(policy.last_reason, 0) + 1
                    observed = receipts(policy)
                    count += len(observed)
                    required += sum(r['required'] for r in observed)
                    unmapped.extend(dict(physical_row=captured['physical_row'], **r)
                                    for r in observed if r['reason'])
                    if first is None:
                        first = dict(physical_row=captured['physical_row'], key=key, reason=policy.last_reason)
            self.assertFalse(unmapped, json.dumps(unmapped[:8], ensure_ascii=False))
            results.append(dict(name=capture['name'], sources=capture['sources'],
                                recorded_decisions=len(mapped), board_controls=len(capture['boards']),
                                receipts=count, required=required, unmapped=unmapped,
                                reconstructed_recorded_receipts=len(recorded_receipts),
                                reconstructed_recorded_unmapped=sum(bool(r['reason']) for r in recorded_receipts),
                                reasons=reasons,
                                first_control=first, boundary=capture['checkpoint'],
                                mapped_producers=mapped))
        destination = os.environ.get('TOWN_WORK_CAPTURE_RESULTS')
        if destination:
            Path(destination).write_text(json.dumps(dict(schema=1, captures=results), indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    unittest.main()
