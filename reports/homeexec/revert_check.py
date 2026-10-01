import os
from pathlib import Path
import subprocess
import sys

path = Path('src/hengbot/observed_input.py')
fixed = path.read_bytes()
baseline = subprocess.check_output(['git', 'show', 'bb722bf3:src/hengbot/observed_input.py'])
try:
    path.write_bytes(baseline)
    result = subprocess.run([
        sys.executable, '-m', 'unittest',
        'tests.test_classA_observed_input.ClassAObservedInputPins.test_existing_english_store_plans_preserve_all_composed_transactions',
    ], env=dict(os.environ, PYTHONPATH='src;tests;scripts'), capture_output=True, text=True)
    Path('reports/homeexec/revert.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
    print(result.stdout + result.stderr)
    if result.returncode == 0:
        raise SystemExit('Revert check unexpectedly passed')
finally:
    path.write_bytes(fixed)
