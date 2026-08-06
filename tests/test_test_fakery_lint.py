import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from test_fakery_lint import analyze_source, scan_tests  # noqa: E402


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
    policy._d = fake
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


class TestTreeFakeryLint(unittest.TestCase):
    EXPECTED_UNDECLARED = {
        ("literal-success-predicate", "test_alchemist_interleaved_unconfirmed_purchase_keeps_bounded_window"),
        ("invariant-input-overwritten", "test_incomplete_optimizer_blocks_normal_direct_entrance"),
        ("pipeline-result-injected", "test_unactionable_suppression_keeps_confirmed_loadout"),
        ("private-state-injected", "_catalogued_withdrawal_policy"),
        ("frozen-drive-state", "test_live_home_door_block_replay_never_posts_stay_publicly"),
        ("pipeline-result-injected", "test_departure_is_immediate_for_already_optimal_loadout"),
        ("pipeline-result-injected", "test_timeout_keeps_confirmed_loadout_but_requires_its_premise"),
        ("pipeline-result-injected", "test_confirmed_loadout_survives_restart_and_is_input_key_bound"),
    }
    DECLARED_FINDING_RATCHET = 97

    def test_tree_has_only_catalogued_undeclared_shapes(self):
        findings = scan_tests()
        undeclared = {(f.rule, f.test) for f in findings if not f.allowed_reason}
        self.assertEqual(undeclared, self.EXPECTED_UNDECLARED)

    def test_inline_exception_count_is_ratcheted(self):
        findings = scan_tests()
        declared = [finding for finding in findings if finding.allowed_reason]
        self.assertEqual(len(declared), self.DECLARED_FINDING_RATCHET)

    def test_two_invalid_declarations_were_fixed_not_moved(self):
        findings = scan_tests()
        affected = {
            "test_equipment_transaction_keeps_home_page_wait_until_observation",
            "test_cross_town_identify_capture_starts_travel_instead_of_visible_stop",
        }
        self.assertFalse([finding for finding in findings if finding.test in affected])


if __name__ == "__main__":
    unittest.main()
