import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import Position
from hengbot.town_maps import find_outpost_map, find_town_map, parse_town_map


EDIT = Path(r"C:\hengband\lib\edit")

_STORE_LEGEND = {
    "1": "GENERAL_STORE", "2": "ARMOURY", "3": "WEAPON_SMITHS", "4": "TEMPLE",
    "5": "ALCHEMY_SHOP", "6": "MAGIC_SHOP", "7": "BLACK_MARKET", "8": "HOME",
}


class TownMapParseTest(unittest.TestCase):
    def _write(self, feature_rules: list, rows: list[str] | None) -> Path:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        edit = Path(directory.name) / "lib" / "edit"
        (edit / "towns").mkdir(parents=True)
        legend = {"#": {"terrain": "PERMANENT"}, ".": {"terrain": "FLOOR"}}
        legend.update({digit: {"terrain": terrain} for digit, terrain in _STORE_LEGEND.items()})
        (edit / "TownPreferences.jsonc").write_text(json.dumps({"legend": legend}), encoding="utf-8")
        variants = [] if rows is None else [{"rows": rows}]
        path = edit / "towns" / "99_Test.jsonc"
        path.write_text(
            json.dumps({"version": 2, "featureRules": feature_rules, "mapVariants": variants}),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _rule(symbol, terrain, **fields):
        return {"symbol": symbol, "definition": {"terrain": terrain, **fields}}

    def test_parses_dims_stores_and_walkability(self):
        path = self._write(
            [
                self._rule("!", "FLOOR"),  # '!' is an explicit floor char
                self._rule("h", "BUILDING_13"),
                self._rule("q", "QUEST_ENTER", special=1),
                self._rule("r", "FLOOR", object="42"),
                self._rule("s", "FLOOR", monster="99", object="0"),  # unrelated nonzero field
                self._rule("H", "BUILDING_1", special=1),
            ],
            ["#######", "#s1.!.#", "#.hqrH#", "#######"],
        )
        tm = parse_town_map(path)
        self.assertEqual((tm.width, tm.height), (7, 4))
        # '1' -> store_type 0 (General), at (row 1, col 2)
        self.assertEqual(tm.stores, {0: Position(1, 2)})
        self.assertEqual(tm.store_position(0), Position(1, 2))
        self.assertEqual(tm.building_position(13), Position(2, 2))
        self.assertTrue(tm.is_walkable(Position(1, 1)))  # '.'
        self.assertTrue(tm.is_walkable(Position(1, 2)))  # store entrance
        self.assertTrue(tm.is_walkable(Position(1, 4)))  # '!' -> FLOOR rule
        self.assertTrue(tm.is_walkable(Position(2, 2)))  # building entrance
        self.assertTrue(tm.is_walkable(Position(2, 3)))  # quest entrance
        self.assertEqual(tm.quest_entrance_positions(1), frozenset({Position(2, 3)}))
        self.assertEqual(tm.quest_building_positions(1), frozenset({Position(2, 5)}))
        self.assertEqual(tm.reward_positions, frozenset({Position(2, 4)}))
        self.assertNotIn(Position(1, 1), tm.reward_positions)
        self.assertFalse(tm.is_walkable(Position(2, 6)))  # wall
        self.assertFalse(tm.is_walkable(Position(0, 0)))  # wall
        self.assertIsNone(tm.entrance)  # no '>' in this town

    def test_all_eight_store_digits_map_to_store_types(self):
        tm = parse_town_map(self._write([], ["12345678"]))
        self.assertEqual(
            {st: (p.y, p.x) for st, p in tm.stores.items()},
            {i: (0, i) for i in range(8)},  # digit d -> store_type d-1 at column d-1
        )

    def test_rejects_a_file_with_no_map(self):
        with self.assertRaises(ValueError):
            parse_town_map(self._write([self._rule("!", "FLOOR")], None))


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
