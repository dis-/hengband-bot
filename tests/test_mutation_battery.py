import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "mutation_battery", ROOT / "scripts" / "mutation_battery.py"
)
mutation_battery = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = mutation_battery
SPEC.loader.exec_module(mutation_battery)


class MutationBatteryFailureParserTest(unittest.TestCase):
    def test_failure_headers_include_plain_and_subtest_identities(self):
        output = """\
FAIL: test_plain (test_policy.RetentionAuthorityTest.test_plain)
----------------------------------------------------------------------
AssertionError: plain
FAIL: test_takeoff_projection_uses_real_two_torch_pack_order (test_policy.RetentionAuthorityTest.test_takeoff_projection_uses_real_two_torch_pack_order) (case='fuel-5000-torch-displaced-last')
----------------------------------------------------------------------
AssertionError: False != True
FAIL: test_bracket_variant (test_policy.RetentionAuthorityTest.test_bracket_variant) [worn_fuel=5000]
----------------------------------------------------------------------
AssertionError: bracket
"""

        self.assertEqual(
            [match.group(1) for match in mutation_battery.FAILURE_RE.finditer(output)],
            [
                "test_policy.RetentionAuthorityTest.test_plain",
                "test_policy.RetentionAuthorityTest.test_takeoff_projection_uses_real_two_torch_pack_order",
                "test_policy.RetentionAuthorityTest.test_bracket_variant",
            ],
        )


if __name__ == "__main__":
    unittest.main()
