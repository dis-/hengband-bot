import unittest
from dataclasses import replace

from hengbot.model import GridState, Position, Snapshot
from hengbot.policy import HengbotPolicy

from tests.test_policy import grid, player


FLOOR = (2, 8, 0)


def snapshot(x, grids, *, floor=FLOOR, turn=1):
    return Snapshot(
        player(10, x),
        {cell.position: cell for cell in grids},
        [],
        turn=turn,
        floor_key=floor,
        width=30,
        height=20,
    )


class PerFloorGridMemoryTest(unittest.TestCase):
    def test_vanished_corridor_remains_walkable(self):
        policy = HengbotPolicy()
        corridor = [grid(10, x) for x in range(5, 10)]
        policy.prime(snapshot(5, corridor))

        current = policy._with_grid_memory(snapshot(9, [grid(10, 9)], turn=2))
        policy._build_grid_index(current)

        vanished = Position(10, 7)
        self.assertTrue(current.grids[vanished].passable)
        self.assertIn((vanished.y, vanished.x), policy._floor_t)
        self.assertTrue(policy._is_step_open(current, Position(10, 8), vanished))

    def test_monster_occupancy_is_never_remembered(self):
        policy = HengbotPolicy()
        occupied = grid(10, 7, monster=True)
        occupied = replace(occupied, monster_index=41)
        first = policy._with_grid_memory(snapshot(6, [grid(10, 6), occupied]))
        self.assertTrue(first.grids[occupied.position].has_monster)

        absent = policy._with_grid_memory(snapshot(6, [grid(10, 6)], turn=2))
        remembered = absent.grids[occupied.position]
        self.assertFalse(remembered.has_monster)
        self.assertEqual(remembered.monster_index, 0)

        visible_empty = policy._with_grid_memory(
            snapshot(6, [grid(10, 6), grid(10, 7)], turn=3)
        )
        self.assertFalse(visible_empty.grids[occupied.position].has_monster)

    def test_newest_terrain_observation_wins(self):
        policy = HengbotPolicy()
        door = Position(10, 7)
        closed = policy._with_grid_memory(
            snapshot(6, [grid(10, 6), grid(10, 7, passable=False, closed_door=True)])
        )
        self.assertTrue(closed.grids[door].is_closed_door)

        opened = policy._with_grid_memory(
            snapshot(6, [grid(10, 6), grid(10, 7, open_door=True)], turn=2)
        )
        self.assertTrue(opened.grids[door].passable)
        self.assertTrue(opened.grids[door].is_door)
        self.assertFalse(opened.grids[door].is_closed_door)

    def test_floor_change_clears_grid_memory_including_zero_floor_keys(self):
        policy = HengbotPolicy()
        old = Position(10, 7)
        policy._with_grid_memory(snapshot(6, [grid(10, 6), grid(10, 7)]))

        town = policy._with_grid_memory(
            snapshot(3, [grid(10, 3)], floor=(0, 0, 0), turn=2)
        )
        self.assertNotIn(old, town.grids)
        self.assertEqual(set(town.grids), {Position(10, 3)})

    def test_dark_cavern_exploration_keeps_route_through_vanished_trail(self):
        policy = HengbotPolicy()
        corridor = [grid(10, x) for x in range(5, 11)]
        first = policy._with_grid_memory(snapshot(5, corridor))
        policy._build_grid_index(first)
        for x in range(5, 10):
            policy._visit_counts[Position(10, x)] = 1

        # Only the player's end of the dark corridor remains emitted. The sole
        # unvisited exploration target is back through tiles now absent on wire.
        dark = policy._with_grid_memory(snapshot(5, [grid(10, 5)], turn=2))
        policy._build_grid_index(dark)
        step = policy._explore_step(dark)

        self.assertEqual(step, Position(10, 6))
        self.assertIn(step, dark.grids)
        self.assertTrue(policy._is_step_open(dark, dark.player.position, step))


if __name__ == "__main__":
    unittest.main()
