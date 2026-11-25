"""The quest plans' single readings and their lint (contradiction audit 2026-11-25, (a)-1..(a)-4).

Owner 2026-11-25 (verbatim) 「追加分にたいして矛盾が増えてきた気がする。保守性のチェック入れて」: the audit
(C:/hengband-backups/pdca/maintainability-review-contradictions-1125/REPORT.md) found the same idea
written several times over the quest modules.  Each idea now has one reading, and
scripts/cross_rule_lint.py fails on a quest module that writes its own again.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import tests  # noqa: F401 -- isolate runtime files before policy imports
from hengbot import quest_plan_base

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cross_rule_lint  # noqa: E402


def _policy(**flags_by_race):
    knowledge = {int(race[1:]): SimpleNamespace(flags=frozenset(flags)) for race, flags in flags_by_race.items()}
    return SimpleNamespace(_monrace_knowledge=knowledge)


class NeverMovesTest(unittest.TestCase):
    """(a)-1: one "never moves" predicate, ``in_water`` for the dry-ground readers."""

    def test_never_move_and_aquatic_by_argument(self):
        policy = _policy(r1={"NEVER_MOVE"}, r2={"AQUATIC"}, r3={"FRIENDS", "ANIMAL"})
        self.assertTrue(quest_plan_base.never_moves(policy, 1))
        self.assertTrue(quest_plan_base.never_moves(policy, 1, in_water=True))
        self.assertFalse(quest_plan_base.never_moves(policy, 2))
        self.assertTrue(quest_plan_base.never_moves(policy, 2, in_water=True))
        self.assertFalse(quest_plan_base.never_moves(policy, 3, in_water=True))
        self.assertFalse(quest_plan_base.never_moves(policy, 99, in_water=True))

    def test_the_lint_names_a_quest_module_reading_the_flags(self):
        tree = ast.parse('def stays(flags):\n    """NEVER_MOVE in a docstring is prose."""\n'
                         '    return "AQUATIC" in flags\n')
        problems = cross_rule_lint.move_flag_problems({"quest_example": tree})
        self.assertEqual(len(problems), 1)
        self.assertIn("quest_example.py:3 reads AQUATIC", problems[0])
        self.assertEqual(cross_rule_lint.move_flag_problems({"policy_example": tree}), [])

    def test_the_source_has_no_such_read(self):
        modules = cross_rule_lint._modules()
        self.assertEqual(cross_rule_lint.move_flag_problems(modules), [])


if __name__ == "__main__":
    unittest.main()
