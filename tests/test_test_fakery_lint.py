import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from test_fakery_lint import LIMITATIONS, analyze_source, scan_tests  # noqa: E402


HISTORICAL_CASES = (
    ("optimizer precompletion", "594053f", "tests/test_policy.py", "test_mining_walk_in_is_the_only_zero_recall_entry", "subject-precompleted"),
    ("fundraising premise overwrite", "0de8159", "tests/test_policy.py", "test_incomplete_optimizer_blocks_normal_direct_entrance", "invariant-input-overwritten"),
    ("best/loadout fabrication", "43726bb", "tests/test_policy.py", "test_unactionable_suppression_keeps_confirmed_loadout", "pipeline-result-injected"),
    ("literal success predicate", "b57957f", "tests/test_policy.py", "test_alchemist_interleaved_unconfirmed_purchase_keeps_bounded_window", "literal-success-predicate"),
    ("frozen 105-decision drive", "HEAD", "tests/test_policy.py", "test_live_home_door_block_replay_never_posts_stay_publicly", "frozen-drive-state"),
    ("helper state injection", "5f49d7a", "tests/test_policy.py", "_catalogued_withdrawal_policy", "private-state-injected"),
    ("all collaborators mocked", "534b4be^", "tests/test_policy.py", "test_live_block_replay_continues_alchemist_plan_publicly", "collaborator-wall"),
)


def historical_source(revision, path):
    return subprocess.check_output(
        ["git", "show", f"{revision}:{path}"], cwd=ROOT,
        text=True, encoding="utf-8",
    )


class TestHistoricalFakerySites(unittest.TestCase):
    def test_real_historical_sites_fire_undeclared(self):
        print("\nHistorical acceptance table (real git blobs):")
        print("shape | revision | real site | fires | declared")
        for shape, revision, path, function, rule in HISTORICAL_CASES:
            with self.subTest(shape=shape):
                findings = analyze_source(
                    historical_source(revision, path), Path(path)
                )
                matches = [
                    finding for finding in findings
                    if finding.test == function and finding.rule == rule
                ]
                fires = bool(matches)
                declared = any(finding.allowed_reason for finding in matches)
                print(
                    f"{shape} | {revision} | {path}:{function} | "
                    f"{'YES' if fires else 'NO'} | {'YES' if declared else 'NO'}"
                )
                self.assertTrue(matches)
                self.assertFalse(declared)


class TestEvasionRewrites(unittest.TestCase):
    def assert_rule(self, rule, source):
        self.assertIn(rule, {finding.rule for finding in analyze_source(source)})

    def test_seven_rewrites_remain_caught(self):
        cases = (
            ("setattr replacement", "public-path-replaced", '''
def test_wrapper():
    setattr(policy, "_decide", fake)
    helper_assert(policy.choose_key(snapshot))
'''),
            ("string patch target", "public-path-replaced", '''
def test_wrapper():
    with patch("hengbot.policy.HengbotPolicy._decide"):
        helper_assert(policy.choose_key(snapshot))
'''),
            ("injection moved to helper", "private-state-injected", '''
def build_policy():
    policy._home_address_pages = pages
    return policy
def test_order():
    helper_assert(build_policy())
'''),
            ("assert delegated to helper", "public-path-replaced", '''
def test_wrapper():
    policy._decide = fake
    helper_assert(policy.choose_key(snapshot))
'''),
            ("wall split patch plus assignment", "collaborator-wall", '''
def test_branch():
    policy._d = Mock()
    with patch.object(policy, "_a"), patch.object(policy, "_b"), patch.object(policy, "_c"):
        helper_assert(policy.choose_key(snapshot))
'''),
            ("success literal hoisted", "literal-success-predicate", '''
def test_any_name():
    expected = "pm1\\r\\r"
    key = policy.choose_key(snapshot)
    helper_assert(key == expected)
'''),
            ("historical test renamed", "subject-precompleted", '''
def test_renamed_invariant():
    set_completed_equipment_optimization(policy)
    helper_assert(policy._dungeon_entry_allowed(snapshot))
'''),
        )
        print("\nSeven-rewrite evasion matrix:")
        for rewrite, rule, source in cases:
            with self.subTest(rewrite=rewrite):
                self.assert_rule(rule, source)
                print(f"{rewrite} | CAUGHT | {rule}")

    def test_repository_idiom_evasions_are_caught(self):
        cases = (
            ("Mock assignment", "public-path-replaced", '''
def test_wrapper():
    policy._decide = Mock(return_value="6ma")
    helper_assert(policy.choose_key(snapshot))
'''),
            ("mock.patch.object", "public-path-replaced", '''
def test_wrapper():
    with mock.patch.object(policy, "_decide", return_value="6ma"):
        helper_assert(policy.choose_key(snapshot))
'''),
            ("module constant patch target", "public-path-replaced", '''
TARGET = "hengbot.policy.HengbotPolicy._decide"
def test_wrapper():
    with patch(TARGET):
        helper_assert(policy.choose_key(snapshot))
'''),
            ("counted drive with aliased literal", "literal-success-predicate", '''
def test_drive():
    expected = "pm1\\r\\r"
    keys = [policy.choose_key(snapshot) for _ in range(40)]
    self.assertEqual(keys.count(expected), 3)
'''),
            ("renamed invariant", "invariant-input-overwritten", '''
def test_partial_optimizer_permits_direct_entrance():
    policy._fundraising_mode = None
    self.assertTrue(policy._dungeon_entry_allowed(snapshot))
'''),
            ("Mock collaborator wall", "collaborator-wall", '''
def test_branch():
    policy._a = Mock()
    policy._b = Mock()
    policy._c = Mock()
    policy._d = Mock()
    helper_assert(policy.choose_key(snapshot))
'''),
        )
        print("\nRepository-idiom evasion matrix:")
        for rewrite, rule, source in cases:
            with self.subTest(rewrite=rewrite):
                self.assert_rule(rule, source)
                print(f"{rewrite} | CAUGHT | {rule}")

    def test_policy_subclass_path_override_is_caught(self):
        self.assert_rule("public-path-replaced", '''
class ScriptedPolicy(HengbotPolicy):
    def _decide(self, snapshot):
        return "6"
''')

    def test_source_text_only_assertions_are_caught(self):
        self.assert_rule("source-text-only-assertions", '''
def test_behaviour_hidden_by_source_grep():
    source = inspect.getsource(HengbotPolicy)
    self.assertNotIn("deleted:first-mechanism", source)
    self.assertNotIn("deleted_second_mechanism", source)
''')

    def test_source_text_check_does_not_taint_behavioural_assertions(self):
        findings = analyze_source('''
def test_source_and_behaviour():
    source = inspect.getsource(HengbotPolicy)
    self.assertNotIn("obsolete", source)
    self.assertEqual(policy.choose_key(snapshot), "6")
''')
        self.assertNotIn(
            "source-text-only-assertions", {finding.rule for finding in findings}
        )

    def test_assert_equal_scope_is_withdrawn_honestly(self):
        single_findings = analyze_source('''
def test_one_decision():
    key = policy.choose_key(snapshot)
    self.assertEqual(key, "pm1")
''')
        repeated_findings = analyze_source('''
def test_repeated_drive():
    keys = [policy.choose_key(snapshot) for _ in range(LIVELOCK_LIMIT + 1)]
    self.assertEqual(keys[-1], "8")
''')
        self.assertNotIn(
            "literal-success-predicate", {finding.rule for finding in single_findings}
        )
        self.assertNotIn(
            "literal-success-predicate", {finding.rule for finding in repeated_findings}
        )
        self.assertTrue(
            any(
                "assertEqual/assertIn against a literal are not inspected" in item
                and "single-decision or repeated drives alike" in item
                and "92 live assertion sites in 54 functions" in item
                and "list/set-comprehension-built" in item
                for item in LIMITATIONS
            )
        )


class TestTreeFakeryLint(unittest.TestCase):
    EXPECTED_UNDECLARED = {
        ("invariant-input-overwritten", "test_incomplete_optimizer_blocks_normal_direct_entrance"),
        ("pipeline-result-injected", "test_unactionable_suppression_keeps_confirmed_loadout"),
        ("frozen-drive-state", "test_live_home_door_block_replay_never_posts_stay_publicly"),
        ("pipeline-result-injected", "test_departure_is_immediate_for_already_optimal_loadout"),
        ("pipeline-result-injected", "test_timeout_keeps_confirmed_loadout_but_requires_its_premise"),
        ("pipeline-result-injected", "test_confirmed_loadout_survives_restart_and_is_input_key_bound"),
    }
    EXPECTED_UNDECLARED_INSTANCES = 7
    # Six scan-only exception sites were deleted with their mechanism.
    DECLARED_FINDING_RATCHET = 111

    def test_tree_has_only_catalogued_undeclared_shapes(self):
        findings = scan_tests()
        undeclared = {(f.rule, f.test) for f in findings if not f.allowed_reason}
        self.assertEqual(undeclared, self.EXPECTED_UNDECLARED)
        self.assertEqual(
            len([finding for finding in findings if not finding.allowed_reason]),
            self.EXPECTED_UNDECLARED_INSTANCES,
        )

    def test_inline_exception_count_is_ratcheted(self):
        findings = scan_tests()
        declared = [finding for finding in findings if finding.allowed_reason]
        self.assertEqual(len(declared), self.DECLARED_FINDING_RATCHET)

    def test_two_invalid_declarations_were_fixed_not_moved(self):
        findings = scan_tests()
        affected = {
            "test_cross_town_identify_capture_starts_travel_instead_of_visible_stop",
        }
        self.assertFalse([finding for finding in findings if finding.test in affected])


if __name__ == "__main__":
    unittest.main()
