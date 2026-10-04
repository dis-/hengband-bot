"""Run incident pins against isolated base source; never mutate the worktree.

Both copies are inside this worktree. Each test subprocess finishes before
the next starts. This is a base-revert proof, not a long trajectory replay.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.shadow3-validation'
FILES = ('policy.py', 'policy_town.py', 'policy_home.py', 'policy_instore.py')


def main():
    OUT.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='base-revert-', dir=OUT) as directory:
        base = Path(directory).resolve()
        assert base.is_relative_to(ROOT.resolve())
        package = base/'hengbot'
        shutil.copytree(ROOT/'src/hengbot', package,
            ignore=shutil.ignore_patterns('__pycache__'))
        for name in FILES:
            original = subprocess.check_output(['git', 'show',
                '504a7c5e:src/hengbot/'+name], cwd=ROOT)
            (package/name).write_bytes(original)
        env = {**os.environ, 'PYTHONPATH': os.pathsep.join(map(str,
            (base, ROOT/'tests', ROOT/'scripts')))}
        with (OUT/'base-revert-pins.txt').open('w', encoding='utf8') as log:
            result = subprocess.run([sys.executable, '-m', 'unittest',
                'test_shadow3_recorded', '-v'], cwd=ROOT, env=env,
                stdout=log, stderr=subprocess.STDOUT)
        print(json.dumps({'base': '504a7c5e', 'exit': result.returncode,
            'log': str(OUT/'base-revert-pins.txt')}))
        if result.returncode == 0:
            raise RuntimeError('The regression pins did not detect the reverted fixes')
        evidence = (OUT/'base-revert-pins.txt').read_text(encoding='utf8')
        if 'FAILED (failures=' not in evidence or 'ERROR' in evidence:
            raise RuntimeError('Revert proof must fail assertions, not imports or setup')
        for name in ('test_full_home_direct_sale', 'test_loot_downstream',
                     'test_scan_gate', 'test_suppression_effect'):
            if f'FAIL: {name}' not in evidence:
                raise RuntimeError('Missing expected reverted incident failure: '+name)


if __name__ == '__main__':
    main()
