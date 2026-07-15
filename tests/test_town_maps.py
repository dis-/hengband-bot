import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import Position
from hengbot.town_maps import find_outpost_map, parse_town_map


class TownMapParseTest(unittest.TestCase):
    def _write(self, text: str) -> Path:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "town.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_parses_dims_stores_and_walkability(self):
        text = "\n".join(
            [
                "# a tiny town",
                "F:!:FLOOR:3",  # '!' is an explicit floor char
                "F:h:BUILDING_13:3",
                "D:#######",
                "D:#.1.!.#",
                "D:#.hTT.#",  # T = tree, blocked
                "D:#######",
            ]
        )
        tm = parse_town_map(self._write(text))
        self.assertEqual((tm.width, tm.height), (7, 4))
        # digit '1' -> store_type 0 (General), at (row 1, col 2)
        self.assertEqual(tm.stores, {0: Position(1, 2)})
        self.assertEqual(tm.store_position(0), Position(1, 2))
        self.assertEqual(tm.building_position(13), Position(2, 2))
        self.assertTrue(tm.is_walkable(Position(1, 1)))  # '.'
        self.assertTrue(tm.is_walkable(Position(1, 2)))  # store entrance
        self.assertTrue(tm.is_walkable(Position(1, 4)))  # '!' -> FLOOR flag
        self.assertTrue(tm.is_walkable(Position(2, 2)))  # building entrance
        self.assertFalse(tm.is_walkable(Position(2, 3)))  # tree
        self.assertFalse(tm.is_walkable(Position(0, 0)))  # wall

    def test_all_eight_store_digits_map_to_store_types(self):
        text = "D:12345678\n"
        tm = parse_town_map(self._write(text))
        self.assertEqual(
            {st: (p.y, p.x) for st, p in tm.stores.items()},
            {i: (0, i) for i in range(8)},  # digit d -> store_type d-1 at column d-1
        )

    def test_rejects_a_file_with_no_map(self):
        with self.assertRaises(ValueError):
            parse_town_map(self._write("# only comments\nF:!:FLOOR:3\n"))


class RealOutpostMapTest(unittest.TestCase):
    def _outpost(self):
        path = find_outpost_map(Path(__file__).resolve().parent.parent)
        if path is None:
            self.skipTest("lib/edit/towns/01_Outpost_Full.txt not found")
        return parse_town_map(path)

    def test_outpost_dims_and_general_store(self):
        tm = self._outpost()
        self.assertEqual((tm.width, tm.height), (198, 66))
        # The General Store (store_type 0) sits at (31, 119) in the fixed Outpost.
        self.assertEqual(tm.store_position(0), Position(31, 119))
        self.assertEqual(len(tm.stores), 8)
        self.assertIsNotNone(tm.building_position(13))

    def test_a_floor_route_exists_from_the_dungeon_entrance_to_a_store(self):
        # The Yeek-Cave up-stairs land at (31, 150); a walkable route to the
        # General Store at (31, 119) must exist over the parsed floor.
        from collections import deque

        tm = self._outpost()
        start, goal = Position(31, 150), tm.store_position(0)
        seen, queue = {start}, deque([start])
        while queue:
            cur = queue.popleft()
            if cur == goal:
                break
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    nxt = Position(cur.y + dy, cur.x + dx)
                    if tm.is_walkable(nxt) and nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
        self.assertIn(goal, seen, "no floor route from the entrance to the store")


if __name__ == "__main__":
    unittest.main()
