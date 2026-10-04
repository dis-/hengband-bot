"""Verify each original producer independently breaks the regression pins.

Read base methods with git show and patch them only inside test subprocesses.
Production files are never reverted on disk. All runs use the requested serial
module runner; logs stay in this worktree. Expected failures are evidence.
"""
import ast
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'validation' / 'chokeloop'
BASE = '7e5156ccd4be0e10381d1645df62c269d2f1a066'


def method(path, name):
    source = subprocess.check_output(
        ['git', 'show', f'{BASE}:{path}'], cwd=ROOT, encoding='utf-8')
    node = next(n for n in ast.walk(ast.parse(source))
                if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.unparse(node)


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    variants = (
        ('intercept', ('_unseen_retreat_intercept_key',)),
        ('wait', ('_unseen_retreat_key',)),
        ('both', ('_unseen_retreat_intercept_key', '_unseen_retreat_key')),
    )
    for label, names in variants:
        module_name = f'_chokeloop_revert_{os.getpid()}_{label}'
        hook = ROOT / 'tests' / (module_name + '.py')
        if hook.exists():
            raise SystemExit(f'refusing to overwrite {hook}')
        try:
            setup = '''import hengbot.policy_supply as supply
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import BREEDER_CONTAINMENT_WINDOW
scope = dict(vars(supply), BREEDER_CONTAINMENT_WINDOW=BREEDER_CONTAINMENT_WINDOW)
'''
            for name in names:
                setup += f'exec({method("src/hengbot/policy_supply.py", name)!r}, scope)\n'
                setup += f'HengbotPolicy.{name} = scope[{name!r}]\n'
            setup += 'from tests.test_choke_hold_loop_recorded import ChokeHoldLoopRecordedTest\n'
            if label == 'both':
                setup += '''import unittest
from unittest.mock import patch
from tests.test_choke_hold_loop_recorded import arm, parse_snapshot
class RecordedBaselineEqualityTest(unittest.TestCase):
    def test_original_producers_match_all_80_recorded_keys_and_reasons(self):
        ChokeHoldLoopRecordedTest.setUpClass()
        for record in ChokeHoldLoopRecordedTest.records[1:]:
            with self.subTest(line=record['line_number']):
                board = parse_snapshot(record['board'], ChokeHoldLoopRecordedTest.knowledge)
                policy = HengbotPolicy(monrace_knowledge=ChokeHoldLoopRecordedTest.knowledge)
                policy.prime(board)
                arm(policy, board, 10457786)
                with patch.object(policy, '_skill_exp_request_key', return_value=None):
                    key = policy.choose_key(board)
                expected = record['decision']
                self.assertEqual((key, policy.last_reason), (expected['key'], expected['reason']))
'''
            hook.write_text(setup, encoding='utf-8')
            env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
            prefix = str(EVIDENCE / f'test-chokeloop-revert-{label}')
            command = [sys.executable, 'scripts/test_parallel_runner.py',
                       '--workers', '1', '--modules', 'tests.' + module_name,
                       '--output', prefix + '.json', '--summary-output', prefix + '-summary.json',
                       '--streams-dir', prefix + '-streams', '--purity', 'never']
            with (ROOT / (prefix + '-console.txt')).open('w', encoding='utf-8') as output:
                result = subprocess.run(command, cwd=ROOT, env=env,
                                        stdout=output, stderr=subprocess.STDOUT)
            console = (ROOT / (prefix + '-console.txt')).read_text(encoding='utf-8')
            print(label, 'exit', result.returncode)
            for line in console.splitlines():
                if line.startswith(('FAILED', 'Failures:', 'Errors:', 'Total:')):
                    print(line)
            if result.returncode != 1 or 'Errors: none' not in console or 'Failures: []' in console:
                raise SystemExit(f'{label}: expected assertion failures without errors')
            if 'FAIL: test_original_producers_match' in console:
                raise SystemExit('both: original producers failed recorded equality')
        finally:
            hook.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
