"""The full-Home relief is read only through ``home_full_relief.relief_of`` (review 2026-11-23 (a)-9).

scripts/home_relief_read_lint.py rejects an attribute read of ``_home_full_relief``, its name as a
string outside the files that name it as data, and the relief read as the dict it was.
"""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from home_relief_read_lint import POLICY_ROOT, analyze_source  # noqa: E402

from hengbot.home_full_relief import HomeFullRelief, relief_of  # noqa: E402


class HomeReliefReadLintTest(unittest.TestCase):
    def test_the_bot_reads_the_relief_only_through_relief_of(self):
        findings = [
            (path.name, finding)
            for path in sorted(POLICY_ROOT.rglob("*.py"))
            for finding in analyze_source(path.read_text(encoding="utf-8"), path.name)
        ]
        self.assertEqual(findings, [])

    def test_other_reads_are_rejected(self):
        mutant = """
def f(self, policy):
    a = self._home_full_relief
    b = getattr(policy, "_home_full_relief", None)
    relief = relief_of(policy)
    c = relief["mode"], relief.get("sale"), "taken" in relief
    return a, b, c
"""
        findings = analyze_source(mutant)
        self.assertEqual(len(findings), 5, findings)

    def test_writes_and_field_reads_pass(self):
        allowed = """
def f(self, policy):
    self._home_full_relief = None
    policy._home_full_relief = HomeFullRelief()
    relief = relief_of(policy)
    return relief.sale, relief.skipped.get("x")
"""
        self.assertEqual(analyze_source(allowed), [])

    def test_relief_of_reads_the_attribute_or_none(self):
        relief = HomeFullRelief(remaining=1)
        self.assertIs(relief_of(SimpleNamespace(_home_full_relief=relief)), relief)
        self.assertIsNone(relief_of(SimpleNamespace()))


if __name__ == "__main__":
    unittest.main()
