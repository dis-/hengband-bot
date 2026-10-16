"""Positions sort by row then column (Linux soak 2026-10-16 14:06 crash in quest route keys)."""
import tests  # noqa: F401
import unittest

from hengbot.model import Position


class PositionOrderTest(unittest.TestCase):
    def test_several_positions_sort_by_row_then_column(self):
        positions = {Position(5, 9), Position(3, 12), Position(5, 2)}
        self.assertEqual(tuple(sorted(positions)),
                         (Position(3, 12), Position(5, 2), Position(5, 9)))


if __name__ == "__main__":
    unittest.main()
