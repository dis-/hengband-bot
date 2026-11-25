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
        """Since Q6 (2026-11-15) no memory is left: the flash records what forgot."""
        policy = _Policy()
        policy._retreat_veto_life = object()
        cross_rules.begin(policy)
        cross_rules.destruction_flash(policy, ("monster_memory.DESTRUCTION_FORGETS",))
        cross_rules.end(policy, _board(level=0, in_town=True), "")
        self.assertEqual(cross_rules.report(policy), [
            "cross-rule:destruction-forget:consulted:monster_memory.DESTRUCTION_FORGETS"])

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

    def test_every_memory_is_forgotten_by_the_registry(self):
        from hengbot import monster_memory

        self.assertEqual(cross_rules.UNFORGOTTEN_MONSTER_MEMORIES, ())
        attributes = {row.attribute for row in monster_memory.DESTRUCTION_FORGETS}
        for attribute in ("_breeder_quest_seen", "_oneshot_breath_visit", "_retreat_veto_life",
                          "_summon_response_memory", "_threat_tier_memory",
                          "_sensed_approach_memory", "_sent_away_t1", "_deep_teleport_landing",
                          "_blind_strike_monsters"):
            self.assertIn(attribute, attributes)

    def test_the_source_has_no_new_gap(self):
        import contextlib
        import io

        lint = self._lint()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = lint.main([])
        self.assertEqual(status, 0, out.getvalue())


class WalkVetoNamesTest(unittest.TestCase):
    """Stage 3: each named combination reads its parts in the table's order."""

    PARTS = {"_engagement_avoid_cells": "retreat", "refused": "left",
             "_engagement_route_veto": "route", "_unseen_attack_area_veto": "unseen-area",
             "_unseen_attack_area_cells": "unseen-cells", "_warning_refused_cells": "warning",
             "_town_entrance_cells": "town-entrance"}

    def test_each_function_is_its_row(self):
        import ast
        import inspect

        from hengbot import walk_vetoes

        tree = ast.parse(inspect.getsource(walk_vetoes))
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for name, parts in walk_vetoes.COMBINATIONS.items():
            node = functions[name.replace("-", "_")]
            # ast.walk is breadth-first: order the reads by their place in the source.
            read = [self.PARTS[sub.attr] for sub in sorted(
                (sub for sub in ast.walk(node)
                 if isinstance(sub, ast.Attribute) and sub.attr in self.PARTS),
                key=lambda sub: (sub.lineno, sub.col_offset))]
            self.assertEqual(tuple(read), parts, name)

    def test_the_walk_veto_is_the_walk_row(self):
        from hengbot import walk_vetoes

        calls = []
        policy = SimpleNamespace(
            _engagement_avoid_cells={1},
            _engagement_owned_avoid_cells=frozenset(),
            _engagement_route_veto=lambda snapshot: calls.append("route") or frozenset({2}),
            _unseen_attack_area_veto=lambda snapshot: calls.append("unseen") or frozenset({3}))
        cells = walk_vetoes.walk(policy, SimpleNamespace(floor_key=(1, 1, 0)))
        self.assertEqual(cells, frozenset({1, 2, 3}))
        self.assertIsInstance(cells, frozenset)
        self.assertEqual(calls, ["route", "unseen"])


if __name__ == "__main__":
    unittest.main()
