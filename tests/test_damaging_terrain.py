import tempfile
import unittest
from pathlib import Path

from hengbot.model import Position, Snapshot
from hengbot.policy import HengbotPolicy
from hengbot.terrain_knowledge import load_damaging_terrain_ids

from tests.test_policy import grid, player


LAVA = 85


class DamagingTerrainNavigationTest(unittest.TestCase):
    def _step(
        self, grids, goal, *, start=Position(1, 1), damaging=frozenset({LAVA})
    ):
        snapshot = Snapshot(player(start.y, start.x), grids, [])
        policy = HengbotPolicy(damaging_terrain_ids=damaging)
        policy._build_grid_index(snapshot)
        return policy._nearest_goal_step(snapshot, lambda cell: cell.position == goal)

    def test_detours_instead_of_entering_lava(self):
        start = Position(2, 0)
        lava = Position(2, 1)
        goal = Position(2, 3)
        grids = {
            start: grid(2, 0),
            lava: grid(2, 1, terrain_id=LAVA),
            Position(2, 2): grid(2, 2),
            goal: grid(2, 3, objects=1),
            Position(1, 0): grid(1, 0),
            Position(0, 0): grid(0, 0),
            Position(0, 1): grid(0, 1),
            Position(0, 2): grid(0, 2),
            Position(0, 3): grid(0, 3),
            Position(1, 3): grid(1, 3),
        }
        step = self._step(grids, goal, start=start)
        self.assertIsNotNone(step)
        self.assertNotEqual(step, lava)

    def test_falls_back_when_lava_is_only_corridor(self):
        start = Position(1, 1)
        lava = Position(1, 2)
        goal = Position(1, 3)
        grids = {
            start: grid(1, 1),
            lava: grid(1, 2, terrain_id=LAVA),
            goal: grid(1, 3),
        }
        self.assertEqual(self._step(grids, goal), lava)

    def test_damaging_goal_is_exempt(self):
        start = Position(1, 1)
        goal = Position(1, 2)
        grids = {
            start: grid(1, 1),
            goal: grid(1, 2, terrain_id=LAVA, downstairs=True),
        }
        self.assertEqual(self._step(grids, goal), goal)

    def test_absent_terrain_id_preserves_old_behavior(self):
        start = Position(1, 1)
        direct = Position(1, 2)
        goal = Position(1, 3)
        grids = {
            start: grid(1, 1),
            direct: grid(1, 2),
            goal: grid(1, 3),
            Position(0, 1): grid(0, 1),
            Position(0, 2): grid(0, 2),
            Position(0, 3): grid(0, 3),
        }
        self.assertEqual(
            self._step(grids, goal),
            self._step(grids, goal, damaging=frozenset()),
        )


class DamagingTerrainKnowledgeTest(unittest.TestCase):
    def test_loads_individual_and_combined_cpp_damage_flags(self):
        source = """{"terrains":[
          {"id":1,"flags":["LAVA"]},
          {"id":2,"flags":["COLD_PUDDLE"]},
          {"id":3,"flags":["ELEC_PUDDLE"]},
          {"id":4,"flags":["ACID_PUDDLE"]},
          {"id":5,"flags":["POISON_PUDDLE"]},
          {"id":6,"flags":["WATER","DEEP"]},
          {"id":7,"flags":["WATER","SHALLOW"]}
        ]}"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TerrainDefinitions.jsonc"
            path.write_text(source, encoding="utf-8")
            self.assertEqual(
                load_damaging_terrain_ids(path), frozenset({1, 2, 3, 4, 5, 6})
            )


if __name__ == "__main__":
    unittest.main()
