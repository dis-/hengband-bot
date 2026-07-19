import unittest

from hengbot.model import Position
from hengbot.projection_path import projection_path


class ProjectionPathTest(unittest.TestCase):
    def test_horizontal_vertical_and_diagonal_steps_match_cpp_range_cost(self):
        origin = Position(5, 5)
        clear = lambda _pos: False

        self.assertEqual(
            projection_path(origin, Position(5, 9), 4, clear),
            [Position(5, 6), Position(5, 7), Position(5, 8), Position(5, 9)],
        )
        self.assertEqual(
            projection_path(origin, Position(9, 5), 4, clear),
            [Position(6, 5), Position(7, 5), Position(8, 5), Position(9, 5)],
        )
        self.assertEqual(
            projection_path(origin, Position(9, 9), 4, clear, through=True),
            [Position(6, 6), Position(7, 7), Position(8, 8)],
        )

    def test_offset_line_rounds_around_wall_corner_and_reaches_victim(self):
        origin = Position(10, 10)
        victim = Position(7, 2)
        wall = Position(7, 3)

        direct = projection_path(origin, victim, 10, lambda pos: pos == wall, through=True)
        offset = projection_path(
            origin, Position(7, 1), 10, lambda pos: pos == wall, through=True
        )

        self.assertNotIn(victim, direct)
        self.assertIn(victim, offset)


if __name__ == "__main__":
    unittest.main()
