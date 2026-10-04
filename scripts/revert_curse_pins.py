"""Run the new pins against HEAD sources without changing the worktree."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
baseline = root / 'validation/curse-baseline/src'
shutil.copytree(root / 'src/hengbot', baseline / 'hengbot', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__'))
for name in ('policy.py', 'policy_supply.py', 'policy_town.py', 'policy_home.py',
             'policy_shop.py', 'policy_fundraising.py', 'policy_helpers.py', 'input_executor.py'):
    raw = subprocess.check_output(['git', 'show', 'HEAD:src/hengbot/' + name], cwd=root)
    (baseline / 'hengbot' / name).write_bytes(raw)
env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(baseline), str(root / 'tests'), str(root / 'scripts'))),
           PYTHONIOENCODING='utf-8')
if Path('C:/hengband/lib/edit/MonraceDefinitions.jsonc').is_file():
    env.setdefault('HENGBOT_TEST_GAME_EDIT_DIR', 'C:/hengband/lib/edit')
run = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_curse_priority_recorded'],
                     cwd=root, env=env, capture_output=True, text=True, encoding='utf-8')
(root / 'validation/curse-revert-pins.txt').write_text(run.stdout + run.stderr, encoding='utf-8')
print(run.stdout + run.stderr)
print('Baseline exit:', run.returncode)
if run.returncode == 0:
    raise SystemExit('Pins unexpectedly pass against HEAD')
output = run.stdout + run.stderr
for test in ('test_recorded_home_has_normal_scroll_and_owns_cure_before_shopping',
             'test_recorded_mining_cursed_weapon_returns_and_keeps_ownership',
             'test_recorded_stuck_recall_owner_answers_depth_prompt_n'):
    if not re.search(r'^FAIL: ' + test + r' \(', output, re.M):
        raise SystemExit('Missing behavioral fail-before pin: ' + test)
