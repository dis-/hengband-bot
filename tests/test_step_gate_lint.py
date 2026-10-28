"""Fast structural ratchet for the single movement-step gate (#47)."""

import tests  # noqa: F401

import ast
from collections import defaultdict
from copy import deepcopy
from itertools import product
from pathlib import Path
from types import MethodType, SimpleNamespace
import unittest

import hengbot.policy as policy_module
import hengbot.policy_navigation as navigation
import step_gate_lint as lint


class StepGateLintTest(unittest.TestCase):
    def test_repository_census(self):
        steps, reads, findings = lint.analyze_repository()
        self.assertEqual(findings, [])
        self.assertEqual(steps, 7)  # gate + six existing raw-key composing sites
        self.assertEqual(reads, 11)  # four owner reads + seven documented exceptions

    def test_new_return_and_offer_bypasses_are_detected(self):
        bodies = [
            "return self._direction_key(here, cell)",
            "key = self._direction_key(here, cell)\n    return key + tail",
            "key = self._direction_key(here, cell)\n    alias = key\n    self._offer_execution(alias)",
            "self._offer_execution(key=self._direction_key(here, cell))",
            "return self._town_producer_entry('walk', lambda: self._direction_key(here, cell))",
            "self._step_toward(snapshot, other)\n    return self._direction_key(here, cell)",
        ]
        for body in bodies:
            with self.subTest(body=body):
                sites, _ = lint.scan_source("def producer(self):\n    " + body + "\n")
                self.assertEqual(len(sites), 1)
                self.assertTrue(lint.census_findings(sites, {}))

    def test_additional_bypass_in_allowlisted_function_fails(self):
        source = (
            "def _town_holder_declared_key(self):\n"
            "    if condition:\n"
            "        return self._direction_key(here, first)\n"
            "    return self._direction_key(here, second)\n"
        )
        sites, _ = lint.scan_source(source, "policy.py")
        self.assertTrue(lint.census_findings(sites, {("policy.py", "_town_holder_declared_key"): 1}))
        self.assertTrue(lint.census_findings([], {("policy.py", "_town_holder_declared_key"): 1}))

    def test_melee_suffix_commands_and_comparisons_are_excluded(self):
        bodies = [
            "return self._direction_key(here, monster.position)",
            "return ALTER_KEY + self._direction_key(here, cell)",
            "return command(suffix=self._direction_key(here, cell))",
            "return OPEN_KEY + self._direction_key(here, cell)",
            "direction = self._direction_key(here, cell)\n    return CHEST_DISARM_KEY + direction",
            "return self._direction_key(here, cell) == avoid_key",
            "return self._step_toward(snapshot, cell)",
        ]
        for body in bodies:
            with self.subTest(body=body):
                sites, _ = lint.scan_source("def producer(self):\n    " + body + "\n")
                self.assertEqual(sites, [])

    def test_only_initialization_is_not_a_warning_read(self):
        source = (
            "def producer(self):\n"
            "    self._warning_refused_cells = set()\n"
            "    avoided = self._warning_refused_cells\n"
            "    return cell in avoided\n"
        )
        _, reads = lint.scan_source(source)
        self.assertEqual(reads, [("<source>", "producer", 3)])
        self.assertTrue(lint.census_findings(reads, {}))

    def test_new_warning_read_in_existing_owner_fails(self):
        source = (
            "def _warning_step_refused(self):\n"
            "    copied = self._warning_refused_cells\n"
            "    return cell in self._warning_refused_cells\n"
        )
        _, reads = lint.scan_source(source, "policy_navigation.py")
        self.assertTrue(lint.census_findings(reads, lint.WARNING_OWNERS))


class WarningGateEquivalenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path(navigation.__file__).read_text(encoding="utf-8"))
        cls.step = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                        and node.name == "_step_toward")
        cls.predicate = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                             and node.name == "_warning_step_refused")

    def test_gate_consults_the_single_warning_predicate(self):
        calls = [node for node in ast.walk(self.step) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)]
        self.assertEqual(sum(node.func.attr == "_warning_step_refused" for node in calls), 1)
        self.assertFalse(any(node.func.attr == "_warning_supplies_exhausted" for node in calls))

    def test_legacy_and_shared_predicate_gate_return_identical_bytes_and_effects(self):
        # Freeze the old nested condition rather than reading a moving git base.
        legacy = deepcopy(self.step)
        refusal = next(node for node in legacy.body if isinstance(node, ast.If)
                       and isinstance(node.test, ast.Call)
                       and isinstance(node.test.func, ast.Attribute)
                       and node.test.func.attr == "_warning_step_refused")
        refusal.test = ast.parse(
            "step in self._warning_refused_cells and ("
            "not self._warning_supplies_exhausted(snapshot) or "
            "step in self._engagement_owned_avoid_cells)", mode="eval").body
        # A and (B or C) has the same short-circuit order as the old nested ifs.
        module = ast.Module(body=[deepcopy(self.step), deepcopy(self.predicate)], type_ignores=[])
        old_module = ast.Module(body=[legacy], type_ignores=[])
        context = dict(vars(navigation))
        exec(compile(ast.fix_missing_locations(module), "<current-step>", "exec"), context)
        old_context = dict(vars(navigation))
        exec(compile(ast.fix_missing_locations(old_module), "<legacy-step>", "exec"), old_context)
        for latched, exhausted, owned, tail in product((False, True), (False, True), (False, True), ("", "y", "n", "\x1b>")):
            with self.subTest(latched=latched, exhausted=exhausted, owned=owned, tail=tail):
                snapshot = SimpleNamespace(player=SimpleNamespace(position=(1, 1)), grids={}, floor_key=(1, 20), store=None)
                supply_calls = []

                def actor():
                    obj = SimpleNamespace(
                        last_reason="approach-descent", _decision_sequence=42,
                        _warning_refused_cells={(1, 2)} if latched else set(),
                        _engagement_owned_avoid_cells={(1, 2)} if owned else set(),
                        _paralyzer_avoid_cells=set(), _floor_trap_disarm_attempts=defaultdict(int),
                        _step_raises_unintended_confirm=lambda *args: False,
                        _direction_key=lambda *args: "6",
                        _warning_supplies_exhausted=lambda *args: supply_calls.append(True) or exhausted,
                    )
                    obj._warning_step_refused = MethodType(context["_warning_step_refused"], obj)
                    return obj

                current, old = actor(), actor()
                new_key = context["_step_toward"](current, snapshot, (1, 2), tail=tail)
                new_calls = len(supply_calls)
                supply_calls.clear()
                old_key = old_context["_step_toward"](old, snapshot, (1, 2), tail=tail)
                self.assertEqual(new_key.encode("utf-8"), old_key.encode("utf-8"))
                self.assertEqual(new_calls, len(supply_calls))
                self.assertEqual(current.last_reason, old.last_reason)
                self.assertEqual(getattr(current, "_warning_step_pending", None), getattr(old, "_warning_step_pending", None))


if __name__ == "__main__":
    unittest.main()
