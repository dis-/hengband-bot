"""designed_stop_lint: every stop the policy sends on purpose is listed and classified, and a
requirement stop carries its debt (MAINTAINABILITY.md rule 2, 2026-11-27)."""

import tests  # noqa: F401
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import designed_stop_lint as lint  # noqa: E402

SOURCES = {
    'mutant': '''
STOP_REASON = "quest:blocked:mutant-tool"


def stop(policy):
    policy.last_reason = STOP_REASON
    return ""


def park(policy, why):
    policy._town_blocked_reason = "mutant-short"
    return policy._town_blocked_key(None)


def compose(policy):
    return f"town:blocked:{policy._town_blocked_reason}"


def escape(policy):
    policy.last_reason = "livelock:exhausted"


def reader(policy):
    if policy.last_reason == "livelock:exhausted":
        return 1
    if policy.last_reason.startswith("town:blocked:"):
        return 2
    return {"quest:blocked:mutant-tool": "banner"}.get(policy.last_reason)


def not_a_stop(policy):
    policy.last_reason = "town:wait-recall"
''',
}


class DesignedStopLintTest(unittest.TestCase):
    def test_sent_stops_are_sites_and_reads_are_not(self):
        sites = lint.stop_sites(SOURCES)
        self.assertEqual(sorted(sites), [
            'mutant:escape: livelock:exhausted',
            'mutant:park: town:blocked:mutant-short',
            'mutant:stop: quest:blocked:mutant-tool',
        ])
        self.assertEqual(sites['mutant:escape: livelock:exhausted'][2], 'final')
        self.assertEqual(sites['mutant:park: town:blocked:mutant-short'][2], 'town-fuse')

    def test_unlisted_and_requirement_without_debt_fail(self):
        sites = lint.stop_sites(SOURCES)
        entries = {
            'mutant:escape: livelock:exhausted': {'kind': 'mechanism'},
            'mutant:park: town:blocked:mutant-short': {'kind': 'requirement'},
            'mutant:gone: town:blocked:old': {'kind': 'mechanism'},
        }
        failures, stale = lint.check(sites, entries)
        self.assertEqual(len(failures), 2)
        self.assertTrue(any('without "debt"' in failure for failure in failures))
        self.assertTrue(any('unlisted' in failure and 'mutant-tool' in failure for failure in failures))
        self.assertEqual(stale, ['mutant:gone: town:blocked:old'])

    def test_requirement_with_debt_and_bad_kind(self):
        sites = {'m:f: town:blocked:x': ('m', 1, 'town-fuse')}
        self.assertEqual(lint.check(sites, {'m:f: town:blocked:x': {'kind': 'requirement', 'debt': 'why'}}),
                         ([], []))
        failures, _ = lint.check(sites, {'m:f: town:blocked:x': {'kind': 'unclassified'}})
        self.assertEqual(len(failures), 1)

    def test_halting_vocabulary(self):
        self.assertEqual(lint.halts('town:blocked:departure-unsatisfiable'), 'final')
        self.assertEqual(lint.halts('town:blocked:stage-deadline:shop'), 'final')
        self.assertEqual(lint.halts('town:blocked:anything'), 'town-fuse')
        self.assertEqual(lint.halts('quest:blocked:hold'), 'blocked')
        self.assertIsNone(lint.halts('livelock:ascend'))
        self.assertIsNone(lint.halts('town:blocked'))

    def test_repository_sites_are_all_classified(self):
        sites = lint.stop_sites(lint.repository_sources())
        failures, _stale = lint.check(sites, lint.load_list())
        self.assertEqual(failures, [])


if __name__ == '__main__':
    unittest.main()
