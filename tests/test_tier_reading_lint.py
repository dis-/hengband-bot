"""tier_reading_lint: a threat tier compared directly outside the threat modules fails unless the
lint's BASELINE lists it (maintainability review 2026-11-18 S6 / 6(a)-9)."""

import tests  # noqa: F401
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import tier_reading_lint


BASE = ("from hengbot import threat_tiers\n"
        "def leave(policy, snapshot, hostiles):\n"
        "    return threat_tiers.tier_of(policy, snapshot, hostiles) == threat_tiers.T1\n")
BASELINE = {"base.py:leave: threat_tiers.tier_of(policy, snapshot, hostiles) == threat_tiers.T1":
            (1, "why")}


def _findings(modules: dict, baseline=BASELINE):
    with TemporaryDirectory() as raw:
        root = Path(raw)
        for name, source in modules.items():
            (root / f"{name}.py").write_text(source, encoding="utf-8")
        return tier_reading_lint.findings(root, baseline)


class TierReadingLintTest(unittest.TestCase):
    def test_the_source_matches_the_baseline(self):
        self.assertEqual(tier_reading_lint.findings(), ([], []))

    def test_the_baselined_comparison_and_a_named_reader_pass(self):
        named = ("from hengbot import threat_tiers\n"
                 "def flee(policy, snapshot, monster):\n"
                 "    return threat_tiers.alone_t1(policy, snapshot, monster)\n")
        self.assertEqual(_findings({"base": BASE, "named": named}), ([], []))

    def test_each_shape_of_a_direct_comparison_fails(self):
        source = ("from hengbot import threat_tiers\n"
                  "from hengbot.threat_projection import T2\n"
                  "def a(reading):\n    return reading.tier == threat_tiers.T1\n"
                  "def b(reading):\n    return reading.tier != T2\n"
                  "def c(reading):\n    return reading.tier in ('T1', 'T2')\n"
                  "def d(reading):\n    return reading.tier not in threat_tiers.STRONG_ON_THE_WAY\n"
                  "class K:\n    def e(self, tier):\n        return 'T3' == tier\n")
        new, stale = _findings({"base": BASE, "other": source})
        self.assertEqual(stale, [])
        self.assertEqual([line.split(" compares")[0] for line in new],
                         ["other.py:4", "other.py:6", "other.py:8", "other.py:10", "other.py:13"])
        self.assertIn("other.py:K.e: 'T3' == tier", new[-1])

    def test_a_second_identical_comparison_in_a_baselined_function_fails(self):
        doubled = ("from hengbot import threat_tiers\n"
                   "def leave(policy, snapshot, hostiles):\n"
                   "    if threat_tiers.tier_of(policy, snapshot, hostiles) == threat_tiers.T1:\n"
                   "        return True\n"
                   "    return threat_tiers.tier_of(policy, snapshot, hostiles) == threat_tiers.T1\n")
        new, stale = _findings({"base": doubled})
        self.assertEqual((len(new), stale), (1, []))

    def test_the_threat_modules_are_not_read_and_a_gone_entry_is_stale(self):
        owner = ("def tiered(reading):\n    return reading.tier == T1\n")
        new, stale = _findings({"threat_tiers": owner, "threat_tier_memory": owner})
        self.assertEqual(new, [])
        self.assertEqual(len(stale), 1)


if __name__ == "__main__":
    unittest.main()
