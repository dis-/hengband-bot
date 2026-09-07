"""Revert-proof tests for the AST-driven split mover."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

import split_move


SOURCE_PATH = Path(__file__).parents[1] / "src" / "hengbot" / "policy.py"
SOURCE = '''from .policy_constants import STORE_STUCK_LIMIT

class HengbotPolicy:
    # This comment belongs to the method.
    @staticmethod
    def decorated(value):
        return value + STORE_STUCK_LIMIT

    def retained(self):
        return 1
'''


class SplitMoveTest(unittest.TestCase):
    def test_decorator_and_leading_comment_move_with_method(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        changed, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)
        self.assertIn("# This comment belongs", target)
        self.assertIn("@staticmethod\n    def decorated", target)
        self.assertNotIn("@staticmethod", changed)
        self.assertEqual(plan.decorated_methods, ("decorated",))
        self.assertEqual(plan.decorator_sentinels, ("retained",))

    def test_module_constant_import_is_computed(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        self.assertEqual(plan.import_lines, ("from .policy_constants import STORE_STUCK_LIMIT",))

    def test_unmatched_selector_is_refused(self) -> None:
        with self.assertRaisesRegex(split_move.SplitMoveError, "matched nothing"):
            split_move.build_plan(SOURCE, "HengbotPolicy", ["typo*"])

    def test_identity_guard_catches_deliberately_corrupted_move(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        changed, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)
        corrupted = target.replace("value + STORE_STUCK_LIMIT", "value - STORE_STUCK_LIMIT")
        with self.assertRaisesRegex(split_move.SplitMoveError, "AST identity failed"):
            split_move.verify_move(plan, changed, corrupted, "HengbotPolicy", "HomeMixin", SOURCE_PATH, "policy_home")

    def test_decorator_guard_bites_when_decorator_is_stranded(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        changed, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)
        corrupted = target.replace("    @staticmethod\n", "")
        with self.assertRaisesRegex(split_move.SplitMoveError, "AST identity failed|decorator was stranded"):
            split_move.verify_move(plan, changed, corrupted, "HengbotPolicy", "HomeMixin", SOURCE_PATH, "policy_home")

    def test_mixin_is_first_for_every_supported_class_header_shape(self) -> None:
        headers = (
            ("class HengbotPolicy(One, Two):", "class HengbotPolicy(HomeMixin, One, Two):"),
            ("class HengbotPolicy(One):", "class HengbotPolicy(HomeMixin, One):"),
            ("class HengbotPolicy(One, metaclass=Meta):", "class HengbotPolicy(HomeMixin, One, metaclass=Meta):"),
            ("class HengbotPolicy(Generic[T]):", "class HengbotPolicy(HomeMixin, Generic[T]):"),
            ("class HengbotPolicy():", "class HengbotPolicy(HomeMixin):"),
            ("class HengbotPolicy:", "class HengbotPolicy(HomeMixin):"),
        )
        for header, expected in headers:
            with self.subTest(header=header):
                source = SOURCE.replace("class HengbotPolicy:", header)
                plan = split_move.build_plan(source, "HengbotPolicy", ["decorated"])
                changed, _ = split_move.render(source, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)
                self.assertIn(expected, changed)

    def test_source_module_back_reference_is_refused_with_symbols(self) -> None:
        source = SOURCE.replace("class HengbotPolicy:", "class LocalGate: pass\n\nclass HengbotPolicy:").replace(
            "return value + STORE_STUCK_LIMIT", "return LocalGate"
        )
        plan = split_move.build_plan(source, "HengbotPolicy", ["decorated"])
        with self.assertRaisesRegex(split_move.SplitMoveError, "LocalGate.*lift"):
            split_move.render(source, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)

    def test_import_smoke_test_rejects_missing_dependency(self) -> None:
        source = SOURCE.replace("from .policy_constants import STORE_STUCK_LIMIT", "from .missing_split_dependency import STORE_STUCK_LIMIT")
        plan = split_move.build_plan(source, "HengbotPolicy", ["decorated"])
        with self.assertRaisesRegex(split_move.SplitMoveError, "import smoke test"):
            split_move.render(source, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)

    def test_import_smoke_test_rejects_a_real_circular_import(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        changed, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)
        circular = target.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\nfrom .policy import HengbotPolicy\n",
        )
        with self.assertRaisesRegex(split_move.SplitMoveError, "import smoke test"):
            split_move.verify_move(plan, changed, circular, "HengbotPolicy", "HomeMixin", SOURCE_PATH, "policy_home")

    def test_generated_module_uses_future_annotations(self) -> None:
        plan = split_move.build_plan(SOURCE, "HengbotPolicy", ["decorated"])
        _, target = split_move.render(SOURCE, plan, "HengbotPolicy", "policy_home", "HomeMixin", SOURCE_PATH)
        self.assertTrue(target.startswith("from __future__ import annotations\n"))


if __name__ == "__main__":
    unittest.main()
