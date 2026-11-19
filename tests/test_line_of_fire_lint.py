"""line_of_fire_lint: a projection_path given a stop of its own outside line_of_fire fails unless
line_of_fire.READERS lists it (maintainability review 2026-11-18 S7-3 / 6(a)-8, the glass class of
ea26e01d4a: a path stopped on LOS instead of PROJECTION)."""

import tests  # noqa: F401
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import line_of_fire_lint


LINE_OF_FIRE = (
    "READERS = {\n"
    "    ('listed', 'reach', 'own_stop'): 'why',\n"
    "    ('named', 'aim', 'player_path'): 'why',\n"
    "}\n"
    "def player_path(policy, snapshot, source, target, max_range):\n"
    "    return projection_path(source, target, max_range, lambda p: False)\n"
)


def _findings(modules: dict) -> list[str]:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "line_of_fire.py").write_text(LINE_OF_FIRE, encoding="utf-8")
        for name, source in modules.items():
            (root / f"{name}.py").write_text(source, encoding="utf-8")
        return line_of_fire_lint.findings(root, root / "no-tests")


LISTED = ("from hengbot.projection_path import projection_path\n"
          "def reach(snapshot, cell, target):\n"
          "    return projection_path(cell, target, 10, lambda p: False)\n")
NAMED = ("from hengbot import line_of_fire\n"
         "def aim(policy, snapshot, cell, target):\n"
         "    return line_of_fire.player_path(policy, snapshot, cell, target, 10)\n")


class LineOfFireLintTest(unittest.TestCase):
    def test_the_source_has_no_finding(self):
        self.assertEqual(line_of_fire_lint.findings(), [])

    def test_the_listed_stop_and_the_named_reading_pass(self):
        self.assertEqual(_findings({"listed": LISTED, "named": NAMED}), [])

    def test_a_sight_stop_of_its_own_fails(self):
        # The glass class: the stop reads LOS, glass has LOS and no PROJECTION.
        glass = ("from hengbot.projection_path import projection_path\n"
                 "def shot(snapshot, cell, target):\n"
                 "    def blocks(pos):\n"
                 "        grid = snapshot.grids.get(pos)\n"
                 "        return grid is not None and grid.known and not grid.allows_los\n"
                 "    return projection_path(cell, target, 10, blocks)\n")
        lines = _findings({"listed": LISTED, "named": NAMED, "glass": glass})
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("glass.py:6 shot passes a stop of its own"), lines)

    def test_a_lambda_stop_and_a_keyword_stop_fail(self):
        source = ("from hengbot import projection_path as pp\n"
                  "def one(snapshot, a, b):\n"
                  "    return pp.projection_path(a, b, 10, lambda p: not snapshot.grids[p].allows_los)\n"
                  "def two(snapshot, a, b, stop):\n"
                  "    return projection_path(a, b, 10, blocks=stop)\n")
        lines = _findings({"listed": LISTED, "named": NAMED, "other": source})
        self.assertEqual([line.split(" passes")[0] for line in lines],
                         ["other.py:3 one", "other.py:5 two"])

    def test_the_listed_stop_moved_to_another_function_fails_and_its_row_is_stale(self):
        moved = LISTED.replace("def reach(", "def reach_all(")
        lines = _findings({"listed": moved, "named": NAMED})
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(any("listed.py:3 reach_all passes a stop of its own" in line for line in lines))
        self.assertTrue(any("('listed', 'reach', 'own_stop') has no call" in line for line in lines))

    def test_the_projection_blockers_are_not_a_stop_of_its_own(self):
        source = ("from hengbot.projection_path import projection_path\n"
                  "def beam(policy, snapshot, a, b):\n"
                  "    return projection_path(a, b, 10,\n"
                  "        lambda p: policy._stops_player_projection(snapshot, p), through=True)\n")
        self.assertEqual(_findings({"listed": LISTED, "named": NAMED, "beam": source}), [])


if __name__ == "__main__":
    unittest.main()
