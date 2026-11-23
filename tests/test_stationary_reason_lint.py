"""scripts/stationary_reason_lint.py: a wait or rest names a stationary row or a bound.

Whole-bot maintainability review 2026-11-23, K3 / (a)-1.  The repository passes against the
recorded baseline, a new wait under a reason no row knows fails (revert-proof), and a wait under
a stationary row or a ``reasons.BOUNDED_WAITS`` row passes."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import stationary_reason_lint as lint  # noqa: E402
from reason_registry_lint import repository_sources  # noqa: E402
from hengbot import reasons  # noqa: E402

NL = "\n"
HOST = "amberite_curse"     # imports WAIT_KEY and REST_MACRO is reachable through policy_constants

# The 2026-11-23 review's (K3) waits outside every stationary row that the source sends with the
# wait key or a rest command itself.  summoner:hold-reposition and quest-strategy:retake-hold are
# not here: both return policy._step_toward (a step; its own refusals wait under their own reasons).
REVIEW_K3 = ("opening-q34:wait",)
# The (b)-1 waits (owner 2026-11-23 「上限を付けて見張りから外す」): bounded by stationary_bounds and
# rows of the table now, so registered and no longer findings.
BOUNDED_B1 = (
    "amberite:hold", "angband-finale:hold", "blind:wait-sight", "fundraise:wait-sight",
    "return:wait-sight", "threat:wait", "combat:disengage-hold",
    "combat:avoid-unprofitable-unique-wait", "combat:avoid-unprofitable-unique-hold",
    "quest25:hold-out-of-fire", "quest-strategy:hold-unreachable", "quest:blocked:hold", "wait",
    "policy:none-wait",
)


def injected(body: str) -> dict:
    sources = dict(repository_sources())
    sources[HOST] = sources[HOST] + NL + NL + body + NL
    return sources


WAIT_SITE = (
    "def _lint_probe(policy):" + NL
    + "    policy.last_reason = {reason!r}" + NL
    + "    return WAIT_KEY"
)


class RepositoryTest(unittest.TestCase):
    def test_no_new_finding_and_the_bounds_exist(self):
        self.assertEqual(lint.new_findings(), [])
        self.assertEqual(lint.bounded_findings(), [])

    def test_the_review_waits_are_found_and_baselined(self):
        found = lint.findings()
        for reason in REVIEW_K3:
            self.assertTrue(any(f"unregistered wait {reason!r}" in finding
                                or f"unregistered rest {reason!r}" in finding for finding in found),
                            reason)
        sent = {shape for _, _, _, _, shapes in lint.sites() for shape in shapes}
        for reason in BOUNDED_B1:
            self.assertIn(reason, sent)
            self.assertTrue(lint.registered(reason), reason)
            self.assertFalse(any(f"{reason!r}" in finding for finding in found), reason)
        self.assertNotIn("summoner:hold-reposition", sent)
        self.assertNotIn("quest-strategy:retake-hold", sent)

    def test_registered_waits_are_sites_and_pass(self):
        verdicts = {shape: lint.registered(shape)
                    for _, _, _, _, shapes in lint.sites() for shape in shapes}
        for reason in ("anaguma:hold", "status-threat:wait", "quest25:rest-recharge",
                       "quest-search:wait-redetect", "combat:disengage-wait"):
            self.assertIs(verdicts.get(reason), True, reason)


class RevertProofTest(unittest.TestCase):
    def test_a_new_unregistered_wait_fails(self):
        new = lint.new_findings(injected(WAIT_SITE.format(reason="quest99:wait")))
        self.assertTrue(any("'quest99:wait'" in finding for finding in new), new)

    def test_a_new_unregistered_rest_fails(self):
        body = ("def _lint_probe(policy, turns):" + NL
                + "    policy.last_reason = 'quest99:rest'" + NL
                + "    return f'R{turns}\\r'")
        new = lint.new_findings(injected(body))
        self.assertTrue(any("unregistered rest 'quest99:rest'" in finding for finding in new), new)

    def test_a_reason_set_in_a_returning_branch_does_not_name_the_wait(self):
        body = ("def _lint_probe(policy, x):" + NL
                + "    policy.last_reason = 'quest99:wait'" + NL
                + "    if x:" + NL
                + "        policy.last_reason = 'confused:wait'" + NL
                + "        return 'x'" + NL
                + "    return WAIT_KEY")
        new = lint.new_findings(injected(body))
        self.assertTrue(any("'quest99:wait'" in finding for finding in new), new)

    def test_a_stationary_row_passes(self):
        self.assertEqual(lint.new_findings(injected(WAIT_SITE.format(reason="confused:wait"))), [])

    def test_a_bounded_declaration_passes_and_must_name_a_constant(self):
        sources = injected(WAIT_SITE.format(reason="quest99:wait"))
        row = reasons.BoundedWait("quest99:wait", "quest_navigator.DEFAULT_HOLD_BUDGET", "a test")
        with mock.patch.object(reasons, "BOUNDED_WAITS", [row]):
            self.assertEqual(lint.new_findings(sources), [])
            self.assertEqual(lint.bounded_findings(), [])
        bad = reasons.BoundedWait("quest99:wait", "quest_navigator.NO_SUCH_LIMIT", "a test")
        with mock.patch.object(reasons, "BOUNDED_WAITS", [bad]):
            self.assertTrue(lint.bounded_findings())
            self.assertEqual(lint.main([]), 1)


if __name__ == "__main__":
    unittest.main()
