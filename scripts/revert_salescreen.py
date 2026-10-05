"""Run the sale-screen pins with only policy_shop reverted in memory.

No worktree or runtime file is changed. Exit success only when the two incident
regressions fail against the intended base (82fcaeb9).
"""
from pathlib import Path
import importlib.abc
import importlib.util
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASE = '82fcaeb9'
SOURCE = subprocess.check_output(
    ['git', 'show', f'{BASE}:src/hengbot/policy_shop.py'], cwd=ROOT,
).decode('utf-8')


class BaselineShop(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'hengbot.policy_shop':
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = str(ROOT / 'src/hengbot/policy_shop.py')
        exec(compile(SOURCE, module.__file__, 'exec'), module.__dict__)


if __name__ == '__main__':
    sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]
    sys.meta_path.insert(0, BaselineShop())
    names = [
        'test_home_surplus_sale_screen_recorded.HomeSurplusSaleScreenRecordedTest.' + name
        for name in (
            'test_A_recorded_failure_and_reconstructed_owned_refusal',
            'test_B_recorded_singleton_and_posted_tail_now_leave',
        )
    ]
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    # Four subtest failures: A/B, claims enforced off/on. Both base commands
    # must be the historically observed d0y, rather than the fixed owned ESC.
    reproduced = (not result.errors and len(result.failures) == 4
                  and all("'d0y'" in detail for _, detail in result.failures))
    print(f'Baseline {BASE}: A/B historical d0y reproduced={reproduced}; '
          f'failures={len(result.failures)}; errors={len(result.errors)}')
    raise SystemExit(0 if reproduced else 1)
