import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from test_fakery_lint import analyze_source, scan_tests  # noqa: E402


class TestFakeryLintRuleTest(unittest.TestCase):
    def _rules(self, source):
        return {finding.rule: finding.render() for finding in analyze_source(source)}

    def test_catches_public_decide_patch_out(self):
        rules = self._rules('''
def test_public_path(self):
    policy._decide = Mock(return_value="6")
    self.assertEqual(policy.choose_key(snapshot), "6")
''')
        self.assertIn("public-path-replaced", rules)

    def test_catches_hand_injected_home_address_pages(self):
        rules = self._rules('''
def test_home_order(self):
    policy._home_address_pages = [(second,), (first,)]
    self.assertEqual(policy.choose_key(snapshot), "pa\\r")
''')
        self.assertIn("private-state-injected", rules)

    def test_catches_all_collaborators_mocked(self):
        rules = self._rules('''
def test_branch(self):
    with (patch.object(policy, "_a"), patch.object(policy, "_b"),
          patch.object(policy, "_c"), patch.object(policy, "_d")):
        self.assertEqual(policy._decide(snapshot), "6")
''')
        self.assertIn("collaborator-wall", rules)

    def test_catches_literal_drive_success_predicate(self):
        rules = self._rules('''
def test_interleaved_drive(self):
    for snapshot in snapshots:
        key = policy.choose_key(snapshot)
        if key == "pm1\\r\\r":
            completed += 1
    self.assertEqual(completed, 1)
''')
        self.assertIn("literal-success-predicate", rules)

    def test_catches_precompleted_subject_and_invariant_mode(self):
        rules = self._rules('''
def test_mining_walk_in_is_the_only_zero_recall_entry(self):
    policy._fundraising_mode = "mine"
    set_completed_equipment_optimization(policy)
    self.assertEqual(policy.choose_key(snapshot), ">")
''')
        self.assertIn("subject-precompleted", rules)

        mode_rules = self._rules('''
def test_incomplete_optimizer_blocks_normal_direct_entrance(self):
    policy._fundraising_mode = None
    self.assertNotEqual(policy.choose_key(snapshot), ">")
''')
        self.assertIn("invariant-input-overwritten", mode_rules)

    def test_catches_fabricated_pipeline_result(self):
        rules = self._rules('''
def test_suppression(self):
    preparation.best.loadout = current
    self.assertTrue(policy._departure_ready(snapshot))
''')
        self.assertIn("pipeline-result-injected", rules)

    def test_catches_frozen_decision_drive(self):
        rules = self._rules('''
def test_decisions_histogram(self):
    for _ in range(105):
        key = policy.choose_key(snapshot)
        reasons[key] += 1
    self.assertEqual(sum(reasons.values()), 105)
''')
        self.assertIn("frozen-drive-state", rules)

    def test_snapshot_fixture_is_not_private_mechanism_replacement(self):
        rules = self._rules('''
def test_fixture(self):
    snapshot = Snapshot(player=player, grids=grids)
    self.assertEqual(policy.choose_key(snapshot), "6")
''')
        self.assertEqual(rules, {})

    def test_reasoned_marker_declares_but_does_not_hide_finding(self):
        findings = analyze_source('''
def test_wrapper_contract(self):
    # TEST_FAKERY_LINT_ALLOW: wrapper fallback is the mechanism under test
    policy._decide = Mock(return_value=None)
    self.assertEqual(policy.choose_key(snapshot), ESC)
''')
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].allowed_reason,
            "wrapper fallback is the mechanism under test",
        )


class TestTreeFakeryLintTest(unittest.TestCase):
    def test_tests_have_no_undeclared_fakery(self):
        findings = scan_tests()
        undeclared = [finding.render() for finding in findings if not finding.allowed_reason]
        self.assertEqual(undeclared, [], "\n" + "\n".join(undeclared))


if __name__ == "__main__":
    unittest.main()
