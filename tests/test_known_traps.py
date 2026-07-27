import unittest

from hengbot.model import Position, Snapshot
from hengbot.policy import CHEST_DISARM_BUDGET, HengbotPolicy

from tests.test_policy import grid, player


class KnownTrapNavigationTest(unittest.TestCase):
    def _policy_and_snapshot(self, grids, *, start):
        snapshot = Snapshot(player(start.y, start.x), grids, [])
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)
        return policy, snapshot

    def test_detours_instead_of_entering_known_trap(self):
        start = Position(2, 0)
        trap = Position(2, 1)
        goal = Position(2, 3)
        grids = {
            start: grid(2, 0),
            trap: grid(2, 1, trap=True),
            Position(2, 2): grid(2, 2),
            goal: grid(2, 3, objects=1),
            Position(1, 0): grid(1, 0),
            Position(0, 0): grid(0, 0),
            Position(0, 1): grid(0, 1),
            Position(0, 2): grid(0, 2),
            Position(0, 3): grid(0, 3),
            Position(1, 3): grid(1, 3),
        }
        policy, snapshot = self._policy_and_snapshot(grids, start=start)

        step = policy._nearest_goal_step(
            snapshot, lambda cell: cell.position == goal
        )

        self.assertIsNotNone(step)
        self.assertNotEqual(step, trap)

    def test_forced_crossing_disarms_then_steps_after_budget(self):
        start = Position(1, 1)
        trap = Position(1, 2)
        goal = Position(1, 3)
        grids = {
            start: grid(1, 1),
            trap: grid(1, 2, trap=True),
            goal: grid(1, 3),
        }
        policy, snapshot = self._policy_and_snapshot(grids, start=start)

        for _ in range(CHEST_DISARM_BUDGET):
            step = policy._nearest_goal_step(
                snapshot, lambda cell: cell.position == goal
            )
            self.assertEqual(step, trap)
            self.assertEqual(policy._step_toward(snapshot, step), "D6")

        step = policy._nearest_goal_step(
            snapshot, lambda cell: cell.position == goal
        )
        self.assertEqual(policy._step_toward(snapshot, step), "6")

    def test_goal_on_known_trap_is_reached_via_disarm(self):
        start = Position(1, 1)
        goal = Position(1, 2)
        grids = {
            start: grid(1, 1),
            goal: grid(1, 2, trap=True, objects=1),
        }
        policy, snapshot = self._policy_and_snapshot(grids, start=start)

        step = policy._nearest_goal_step(
            snapshot, lambda cell: cell.position == goal
        )

        self.assertEqual(step, goal)
        self.assertEqual(policy._step_toward(snapshot, step), "D6")

    def test_absent_trap_flag_preserves_direct_route(self):
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
        policy, snapshot = self._policy_and_snapshot(grids, start=start)

        step = policy._nearest_goal_step(
            snapshot, lambda cell: cell.position == goal
        )

        self.assertEqual(step, Position(0, 2))
        self.assertEqual(policy._step_toward(snapshot, step), "9")


if __name__ == "__main__":
    unittest.main()
