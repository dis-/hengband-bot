"""state_registry_lint: every policy state name is declared, the town visit's forwarded names are
read from its tables, and the "reset by" column of the counter-like entries lists exactly the
source's reset sites (maintainability review 2026-11-18 S4)."""

import tests  # noqa: F401
import ast
import unittest
from unittest import mock

from hengbot import state_registry
import state_registry_lint

MIXIN = '''
class MutantMixin:
    def step(self):
        self._mutant_new_state = 1

    def forwarded(self):
        self._store_sell_attempt = None

    def forget(self):
        self._nav_stall_count = 0


class Helper:
    def own(self):
        self._helper_own_state = 1


class HengbotPolicy(MutantMixin):
    pass


def module_resets(policy):
    setattr(policy, "_rest_count", None)
    policy.__dict__.pop("_dig_attempts", None)
'''


class StateRegistryLintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = state_registry_lint._modules()

    def _with_mutant(self):
        return {**self.modules, "mutant_mixin": ast.parse(MIXIN)}

    def test_the_source_has_no_finding(self):
        self.assertEqual(state_registry_lint.findings(self.modules), [])

    def test_an_undeclared_assignment_in_a_mixin_fails(self):
        lines = state_registry_lint.findings(self._with_mutant())
        self.assertIn("mutant_mixin.py:4 _mutant_new_state (assigned) is not declared in "
                      "hengbot/state_registry.py", lines)
        # Another class's own attribute and a forwarded town-visit name are no finding.
        self.assertFalse([line for line in lines if "_helper_own_state" in line])
        self.assertFalse([line for line in lines if "_store_sell_attempt" in line])

    def test_an_unlisted_reset_of_a_counter_fails(self):
        lines = state_registry_lint.findings(self._with_mutant())
        for name, site in (("_nav_stall_count", "mutant_mixin.forget"),
                           ("_rest_count", "mutant_mixin.module_resets"),
                           ("_dig_attempts", "mutant_mixin.module_resets")):
            self.assertIn(f"reset-by: {name} is reset in {site}, which its RESET_BY row does "
                          "not list", lines)

    def test_a_stale_or_missing_reset_row_fails(self):
        table = dict(state_registry.RESET_BY)
        del table["_nav_stall_count"]
        table["_anaguma_retry"] = state_registry.Reset(
            ("floor_visit_memory.forget", "policy._choose_key", "policy._no_such_function"))
        table["_rest_count"] = state_registry.Reset()
        with mock.patch.object(state_registry, "RESET_BY", table):
            lines = state_registry_lint.reset_findings(self.modules)
        self.assertTrue(any(line.startswith("reset-by: _nav_stall_count is a counter-like entry "
                                            "with no RESET_BY row") for line in lines))
        self.assertIn("reset-by: _anaguma_retry lists policy._choose_key, which resets nothing "
                      "of it", lines)
        self.assertIn("reset-by: _anaguma_retry lists policy._no_such_function, which its "
                      "module does not define", lines)
        self.assertIn("reset-by: _rest_count lists no site and has no note", lines)

    def test_a_forwarded_name_declared_twice_fails(self):
        row = state_registry.State("_store_sell_attempt", "policy_home", state_registry.LIFE,
                                   "a copy of the town visit's row")
        with mock.patch.object(state_registry, "REGISTRY", state_registry.REGISTRY + (row,)):
            lines = state_registry_lint.findings(self.modules)
        self.assertIn("town-visit: _store_sell_attempt is forwarded to "
                      "_town_visit.store_sell_attempt (town_visit) and is also a REGISTRY row; "
                      "keep the one declaration", lines)

    def test_the_counter_like_rows_and_the_column_match(self):
        counters = {row.name for row in state_registry.REGISTRY
                    if state_registry.COUNTER_NAME.search(row.name)}
        self.assertEqual(set(state_registry.RESET_BY), counters)


if __name__ == "__main__":
    unittest.main()
