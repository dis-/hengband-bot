"""Revert-proof tests for the AST-driven split mover."""

from __future__ import annotations

import ast
import unittest

import split_move


SOURCE = '''from .policy_constants import LIMIT

class HengbotPolicy:
    # This comment belongs to the method.
    @staticmethod
    def decorated(value):
        return value + LIMIT

    def retained(self):
        return 1
'''


class SplitMoveTest(unittest.TestCase):
    def test_decorator_and_leading_comment_move_with_method(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        changed, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin")
        self.assertIn("# This comment belongs", target)
        self.assertIn("@staticmethod\n    def decorated", target)
        self.assertNotIn("@staticmethod", changed)
        self.assertEqual(plan.decorated_methods, ("decorated",))
        self.assertEqual(plan.decorator_sentinels, ("retained",))

    def test_module_constant_import_is_computed(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        self.assertEqual(plan.import_lines, ("from .policy_constants import LIMIT",))

    def test_unmatched_selector_is_refused(self) -> None:
        with self.assertRaisesRegex(split_move.SplitMoveError, "matched nothing"):
            split_move.build_plan(SOURCE, "HengbotPolicy", ["typo*"])

    def test_identity_guard_catches_deliberately_corrupted_move(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        changed, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin")
        corrupted = target.replace("value + LIMIT", "value - LIMIT")
        with self.assertRaisesRegex(split_move.SplitMoveError, "AST identity failed"):
            split_move.verify_move(plan, changed, corrupted, "HengbotPolicy", "HomeMixin")

    def test_decorator_guard_bites_when_decorator_is_stranded(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        changed, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin")
        corrupted = target.replace("    @staticmethod\n", "")
        with self.assertRaisesRegex(split_move.SplitMoveError, "AST identity failed|decorator was stranded"):
            split_move.verify_move(plan, changed, corrupted, "HengbotPolicy", "HomeMixin")


if __name__ == "__main__":
    unittest.main()
