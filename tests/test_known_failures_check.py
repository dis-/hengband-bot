"""known_failures_check: the comparison of a run's failures with tests/KNOWN_FAILURES.txt
(MAINTAINABILITY.md rule 6, 2026-11-27).  Fake results only: no suite runs here."""

import tests  # noqa: F401
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import known_failures_check as check  # noqa: E402

STDERR = '''\
======================================================================
ERROR: test_a (tests.test_x.Alpha.test_a)
----------------------------------------------------------------------
Traceback (most recent call last):
======================================================================
FAIL: test_b (tests.test_x.Alpha.test_b) (case=1)
----------------------------------------------------------------------
======================================================================
FAIL: test_b (tests.test_x.Alpha.test_b) (case=2)
----------------------------------------------------------------------
======================================================================
ERROR: setUpClass (tests.test_y.Beta)
----------------------------------------------------------------------
======================================================================
ERROR: test_z (unittest.loader._FailedTest.test_z)
----------------------------------------------------------------------
'''


class KnownFailuresCheckTest(unittest.TestCase):
    def test_headers_become_ids(self):
        self.assertEqual(check.parse_failures(STDERR), {
            'tests.test_x.Alpha.test_a': 'ERROR',
            'tests.test_x.Alpha.test_b': 'FAIL',
            'tests.test_y.Beta (setUpClass)': 'ERROR',
            'tests.test_z (import)': 'ERROR',
        })
        self.assertEqual(check.module_of('tests.test_y.Beta (setUpClass)'), 'tests.test_y')
        self.assertEqual(check.module_of('tests.test_z (import)'), 'tests.test_z')

    def test_only_unlisted_failures_are_new(self):
        failing = {'tests.test_x.Alpha.test_a', 'tests.test_x.Alpha.test_b', 'tests.test_y.Beta.test_c'}
        known = {'tests.test_x.Alpha.test_a', 'tests.test_x.Alpha.test_gone', 'tests.test_w.W.test_w'}
        flaky = {'tests.test_x.Alpha.test_b', 'tests.test_x.Alpha.test_flake'}
        new, passing = check.compare(failing, known, flaky, {'tests.test_x', 'tests.test_y'})
        self.assertEqual(new, ['tests.test_y.Beta.test_c'])
        # test_w's module did not run; a flaky id that passes is not offered for removal.
        self.assertEqual(passing, ['tests.test_x.Alpha.test_gone'])

    def test_flaky_ids_are_the_differences_within_the_rerun_modules(self):
        first = {'tests.test_x.A.t1', 'tests.test_x.A.t2', 'tests.test_y.B.t3'}
        second = {'tests.test_x.A.t1', 'tests.test_x.A.t4'}
        self.assertEqual(check.flaky_between(first, second, {'tests.test_x'}),
                         {'tests.test_x.A.t2', 'tests.test_x.A.t4'})

    def test_file_round_trip_keeps_the_flaky_section(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'KNOWN_FAILURES.txt'
            check.write_known({'tests.b.B.t', 'tests.a.A.t', 'tests.c.C.t'}, {'tests.c.C.t'}, path,
                              header='Tests failing on main.')
            lines = path.read_text(encoding='utf-8').splitlines()
            self.assertEqual(lines, ['# Tests failing on main.', 'tests.a.A.t', 'tests.b.B.t',
                                     '# flaky', 'tests.c.C.t'])
            self.assertEqual(check.load_known(path), ({'tests.a.A.t', 'tests.b.B.t'}, {'tests.c.C.t'}))
            self.assertEqual(check._header(path), 'Tests failing on main.')

    def test_lanes_cap_at_two_and_keep_the_serial_modules_together(self):
        modules = [f'tests.test_m{index:02d}' for index in range(7)] + sorted(check.SERIAL_MODULES)
        plan = check.lanes(modules, 2, 3, {})
        self.assertEqual(len(plan), 2)
        self.assertEqual(sorted(plan[0][0]), sorted(check.SERIAL_MODULES))
        batched = [module for lane in plan for batch in lane for module in batch]
        self.assertEqual(sorted(batched), sorted(modules))
        self.assertTrue(all(len(batch) <= 3 for lane in plan for batch in lane[1:]))


if __name__ == '__main__':
    unittest.main()
