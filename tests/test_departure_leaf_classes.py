"""Every departure gate leaf has exactly one class (departure_leaf_classes, MAINTAINABILITY.md 2-3).

The leaves are read from the gates' source by scripts/departure_rescue_lint.py (``gate_leaves``), so
a leaf added to a gate without a class fails here and in the lint.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import importlib.util
import unittest
from pathlib import Path

from hengbot import departure_leaf_classes

LINT = Path(__file__).resolve().parents[1] / "scripts" / "departure_rescue_lint.py"


def lint_module():
    spec = importlib.util.spec_from_file_location("departure_rescue_lint", LINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DepartureLeafClassesTest(unittest.TestCase):
    def test_every_gate_leaf_is_in_exactly_one_class(self):
        lint = lint_module()
        leaves = set().union(*lint.gate_leaves().values())
        self.assertGreaterEqual(len(leaves), 37)
        self.assertEqual(lint.class_problems(leaves), [])
        for leaf in leaves:
            self.assertIsNotNone(departure_leaf_classes.class_of(leaf), leaf)

    def test_an_unclassified_leaf_is_reported(self):
        lint = lint_module()
        leaves = set().union(*lint.gate_leaves().values()) | {"new_leaf_ready"}
        self.assertEqual(lint.class_problems(leaves),
                         ["departure_leaf_classes: leaf 'new_leaf_ready' is in no class"])

    def test_the_minimum_is_never_waived(self):
        # free_pack_slots_ready is OPTIONAL for the ordinary gate (four or five slots) but the
        # forced departure's minimum (one slot) holds it.
        self.assertFalse(departure_leaf_classes.only_waivable(
            None, None, ("free_pack_slots_ready",), survival=("free_pack_slots_ready",)))
        self.assertTrue(departure_leaf_classes.only_waivable(
            None, None, ("free_pack_slots_ready", "home_candidate_resolved")))
        self.assertFalse(departure_leaf_classes.only_waivable(
            None, None, ("home_candidate_resolved", "food_ready")))


if __name__ == "__main__":
    unittest.main()
