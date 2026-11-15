"""The cross-layer rules' observer (hengbot.cross_rules): it records, it decides nothing.

Maintainability review of the dungeon decisions 2026-11-15, stage 1."""
import tests  # noqa: F401  -- runtime-file isolation before policy imports

import unittest
from types import SimpleNamespace

from hengbot import cross_rules


class _Policy:
    last_reason = ""


def _board(*, level=10, in_town=False):
    return SimpleNamespace(in_town=in_town, store=None, dungeon_level=level)


class CrossRuleObserverTest(unittest.TestCase):
    def test_step_after_the_registry_read_is_consulted(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.consult(policy, cross_rules.LEFT_CELLS, "explore")
        cross_rules.produce(policy, cross_rules.LEFT_CELLS, "walker")
        cross_rules.end(policy, _board(), "4")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:left-cells:consulted:walker"])

    def test_step_before_any_registry_read_is_not_consulted(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.produce(policy, cross_rules.LEFT_CELLS, "walker")
        cross_rules.consult(policy, cross_rules.LEFT_CELLS, "later")
        cross_rules.end(policy, _board(), "4")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:left-cells:not-consulted:walker"])

    def test_dungeon_rest_and_wait_read_the_uncurse_point(self):
        policy = _Policy()
        policy.last_reason = "rest:hp"
        cross_rules.begin(policy)
        cross_rules.end(policy, _board(), "R&\r")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:uncurse-before-rest:not-consulted:rest:hp"])
        cross_rules.begin(policy)
        cross_rules.consult(policy, cross_rules.UNCURSE_BEFORE_REST, "key")
        cross_rules.end(policy, _board(), "5")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:uncurse-before-rest:consulted:rest:hp"])

    def test_town_rest_is_not_a_dungeon_rule(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.end(policy, _board(level=0, in_town=True), "R&\r")
        self.assertIsNone(cross_rules.report(policy))

    def test_escape_noted_by_its_producer(self):
        from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS

        reason = sorted(EMERGENCY_ESCAPE_REASONS)[0]
        policy = _Policy()
        policy.last_reason = reason
        cross_rules.begin(policy)
        cross_rules.end(policy, _board(), "r")
        state = cross_rules.report(policy)[0].split(":")[2]
        self.assertIn(state, (cross_rules.NOT_CONSULTED, cross_rules.CONSULTED))
        cross_rules.begin(policy)
        cross_rules.consult(policy, cross_rules.ESCAPE_LINE_OF_FIRE, "x")
        cross_rules.end(policy, _board(), "r")
        self.assertEqual(cross_rules.report(policy),
                         [f"cross-rule:escape-line-of-fire:consulted:{reason}"])

    def test_destruction_flash_lists_the_memories_left(self):
        policy = _Policy()
        policy._retreat_veto_life = object()
        cross_rules.begin(policy)
        cross_rules.destruction_flash(policy, ("monster_memory.KINDS",))
        cross_rules.end(policy, _board(level=0, in_town=True), "")
        self.assertEqual(cross_rules.report(policy), [
            "cross-rule:destruction-forget:consulted:monster_memory.KINDS",
            "cross-rule:destruction-forget:not-consulted:_retreat_veto_life"])

    def test_nothing_is_stored_on_the_policy(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.produce(policy, cross_rules.LEFT_CELLS, "walker")
        cross_rules.end(policy, _board(), "4")
        self.assertEqual(vars(policy), {})

    def test_real_hooks_name_the_caller(self):
        from hengbot import left_cells

        policy = SimpleNamespace(_engagement_owned_avoid_cells=frozenset())

        def some_walker():
            return left_cells.refused(policy, SimpleNamespace(floor_key=(1, 1, 0)))

        cross_rules.begin(policy)
        some_walker()
        sites = [site for _clock, site in cross_rules._ledger(policy).consults[cross_rules.LEFT_CELLS]]
        self.assertEqual(sites, ["some_walker"])


class CrossRuleLintTest(unittest.TestCase):
    """Stage 2: the registry and its lint (scripts/cross_rule_lint.py)."""

    @staticmethod
    def _lint():
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "cross_rule_lint.py"
        spec = importlib.util.spec_from_file_location("cross_rule_lint", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_walker_without_the_registry_is_a_gap(self):
        import ast

        lint = self._lint()
        sources = {
            "left_cells": """
def refused(policy, snapshot):
    return frozenset()
""",
            "good_walk": """
from hengbot import left_cells
def walk(policy, snapshot):
    left_cells.refused(policy, snapshot)
    return policy._step_toward(snapshot, None)
""",
            "bad_walk": """
def walk(policy, snapshot):
    return policy._step_toward(snapshot, None)
""",
            "helper_walk": """
from hengbot import left_cells
def _veto(policy, snapshot):
    return left_cells.refused(policy, snapshot)
def walk(policy, snapshot):
    _veto(policy, snapshot)
    return policy._step_toward(snapshot, None)
""",
        }
        index = lint.Index({name: ast.parse(text) for name, text in sources.items()})
        self.assertEqual(lint.gaps(index)[cross_rules.LEFT_CELLS], ["bad_walk:walk"])

    def test_the_census_names_the_unforgotten_memories(self):
        self.assertEqual(
            {row.attribute for row in cross_rules.MONSTER_MEMORIES if row.forgotten_by is None},
            set(cross_rules.UNFORGOTTEN_MONSTER_MEMORIES))

    def test_the_source_has_no_new_gap(self):
        import contextlib
        import io

        lint = self._lint()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = lint.main([])
        self.assertEqual(status, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
