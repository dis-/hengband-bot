import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import unittest
from pathlib import Path

from hengbot.model import Position
from hengbot.town_maps import find_outpost_map, find_town_map, parse_town_map


EDIT = Path(r"C:\hengband\lib\edit")


class RealTownMapTest(unittest.TestCase):
    def _town(self, town_index):
        if not EDIT.is_dir():
            self.skipTest("real Hengband lib/edit data is unavailable")
        path = find_town_map(town_index, EDIT)
        self.assertIsNotNone(path, f"TownDefinitionList.jsonc has no town {town_index}")
        return parse_town_map(path)

    def test_outpost_dims_and_general_store(self):
        tm = self._town(1)
        self.assertEqual((tm.width, tm.height), (198, 66))
        self.assertEqual(tm.store_position(0), Position(31, 119))
        self.assertEqual(len(tm.stores), 8)
        self.assertIsNotNone(tm.building_position(13))
        self.assertEqual(tm.quest_building_positions(1), frozenset({Position(26, 98)}))
        self.assertIn(Position(35, 177), tm.quest_entrance_positions(1))
        self.assertIn(Position(27, 98), tm.reward_positions)

    def test_a_floor_route_exists_from_the_dungeon_entrance_to_a_store(self):
        from collections import deque

        tm = self._town(1)
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

    def test_telmora_locations_come_from_indexed_jsonc_map(self):
        town = self._town(2)
        self.assertEqual(town.quest_entrance_positions(2), frozenset({Position(25, 47)}))
        self.assertIn(Position(22, 42), town.reward_positions)
        self.assertIsNotNone(town.building_position(4))

    def test_finder_uses_town_definition_index_and_normal_outpost_variant(self):
        if not EDIT.is_dir():
            self.skipTest("real Hengband lib/edit data is unavailable")
        self.assertEqual(find_outpost_map(EDIT), EDIT / "towns" / "01_Outpost_Full.jsonc")
        self.assertEqual(find_town_map(1, EDIT), find_outpost_map(EDIT))

    def test_town_parser_rejects_legacy_text_paths(self):
        with self.assertRaises(ValueError):
            parse_town_map(EDIT / "towns" / "01_Outpost_Full.txt")


if __name__ == "__main__":
    unittest.main()
