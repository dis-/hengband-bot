"""Finish this authorized verification job and commit its factual Japanese report."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
GUARDS = Path('C:/hengband-backups/guard-tools')
PRIVACY = Path('C:/Users/user/.codex/skills/hengband-pr-submit/scripts/check_report_privacy.py')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


expected = {name: git('rev-parse', '01f208c44:' + name)
            for name in ('src/hengbot', 'tests')}
branch = git('symbolic-ref', '--short', 'HEAD')


def unchanged():
    return (git('symbolic-ref', '--short', 'HEAD') == branch
            and all(git('rev-parse', 'HEAD:' + name) == tree
                    for name, tree in expected.items())
            and not git('status', '--porcelain', '--', 'src', 'tests'))


def execute(label, args):
    with (OUT / (label + '.log')).open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, '-X', 'utf8', *map(str, args)],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print(label, 'exit', result.returncode, flush=True)
    return result.returncode


scope = json.loads((OUT / 'scope.json').read_text(encoding='utf-8'))
while True:
    path = OUT / 'module-exits.json'
    try:
        exits = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        exits = {}
    if set(exits) == set(scope['derived']['modules']):
        break
    time.sleep(30)

if not unchanged():
    raise SystemExit('Source/tests or branch changed: refusing to attribute or commit stale results')
# The first fast tier may overlap the hunk-reversion check. Repeat on restored
# committed source, after every module has finished, for unambiguous evidence.
codes = {'fast_tier_final': execute('fast_tier_final', [
    GUARDS / 'fast_tier.py', ROOT, '069d2e7ce', '--shards', '4'])}
if not unchanged():
    raise SystemExit('Source/tests changed during final fast tier')
codes['preflight'] = execute('preflight', [GUARDS / 'preflight.py', ROOT, '069d2e7ce'])
if not unchanged():
    raise SystemExit('Source/tests changed during final preflight')
codes['module_failures'] = sum(code != 0 for code in exits.values())
(OUT / 'final-exits.json').write_text(json.dumps(codes, indent=2), encoding='utf-8')
subprocess.run([sys.executable, '-X', 'utf8', str(OUT / 'write_report.py')], cwd=ROOT, check=True)
subprocess.run([sys.executable, '-X', 'utf8', str(PRIVACY),
                str(ROOT / 'LUNA-REPORT-rod-overflow.txt')], cwd=ROOT, check=True)
paths = ['LUNA-REPORT-rod-overflow.txt',
         'validation/rod-overflow-1027/final-exits.json',
         'validation/rod-overflow-1027/preflight.log',
         'validation/rod-overflow-1027/mutation_check.log',
         'validation/rod-overflow-1027/fast_tier.log',
         'validation/rod-overflow-1027/fast_tier_final.log',
         'validation/rod-overflow-1027/module-exits.json',
         ':(glob)validation/rod-overflow-1027/modules/*.json']
subprocess.run(['git', 'add', '--', *paths], cwd=ROOT, check=True)
subprocess.run(['git', 'commit', '--only', '-m',
                'docs: record completed overflow verification results (#47)',
                '--', *paths], cwd=ROOT, check=True)
print('FINAL_REPORT_COMMIT', git('rev-parse', 'HEAD'), flush=True)
