"""Run the requested guards with the invoking system Python and UTF-8 logs."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
GUARDS = Path('C:/hengband-backups/guard-tools')
BASE = '069d2e7ce'


def run(label, arguments):
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(
        str(ROOT / part) for part in ('.', 'src', 'tests', 'scripts')),
        PYTHONIOENCODING='utf-8')
    with (OUT / (label + '.log')).open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, '-X', 'utf8', *map(str, arguments)],
                                cwd=ROOT, env=environment, stdout=log,
                                stderr=subprocess.STDOUT)
    print(label, 'exit', result.returncode, flush=True)
    return result.returncode


mode = sys.argv[1]
if mode in ('preflight', 'mutation_check', 'fast_tier'):
    arguments = [GUARDS / (mode + '.py'), ROOT, BASE]
    if mode == 'mutation_check':
        arguments.extend(['--tests', 'tests.test_rod_overflow_recorded', '--record'])
    if mode == 'fast_tier':
        arguments.extend(['--shards', '4'])
    raise SystemExit(run(mode, arguments))
elif mode == 'derive':
    raise SystemExit(run(mode, [ROOT / 'scripts/verify_scope.py', '--target', 'HEAD',
                               '--base', BASE, '--derive-only', '--output',
                               OUT / 'scope.json']))
elif mode == 'modules':
    sys.path.insert(0, str(GUARDS))
    from gate_lock import wait_for_gate
    wait_for_gate('rod-overflow-modules')
    # Mutation checking temporarily reverts production hunks in this worktree.
    # Module verification must see only the restored committed source.
    while True:
        mutation = (OUT / 'mutation_check.log').read_text(encoding='utf-8')
        fast = (OUT / 'fast_tier.log').read_text(encoding='utf-8')
        if ('recorded for' in mutation or 'MUTATION FAIL' in mutation
                or 'STOP:' in mutation) and 'Total:' in fast:
            break
        print('modules: waiting for local guards to finish', flush=True)
        time.sleep(30)
    scope = json.loads((OUT / 'scope.json').read_text(encoding='utf-8'))
    (OUT / 'modules').mkdir(exist_ok=True)
    def module_check(module):
        label = 'modules/' + module
        code = run(label, [OUT / 'module_runner.py', module,
                           OUT / (label + '.json')])
        return module, code
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(module_check, module)
                   for module in scope['derived']['modules']]
        for future in as_completed(futures):
            module, code = future.result()
            results[module] = code
            (OUT / 'module-exits.json').write_text(
                json.dumps(results, indent=2, sort_keys=True), encoding='utf-8')
    raise SystemExit(any(results.values()))
else:
    raise SystemExit('unknown mode')
