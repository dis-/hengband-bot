"""hengbot/goal_route.py: a goal walk keeps its route while the route is valid.

Board (only walkable cells exist; A = start, G = upstairs):

    row 1:  .  A  c  c  c  G        corridor (1,1)-(1,5)
    row 2:  d  #  #  #  #  d        detour (2,0) ... (2,5)
    row 3:  #  d  d  d  d  #

With a monster on (1,3) the walk from A detours (first step (2,0), 7 edges).
On the next board the monster has stepped away: from (2,0) the corridor back
through A is 5 edges and the detour 6, so a fresh search walks straight back
onto A -- the n1-b life-285 reversal (tests/test_route_moving_blocker_recorded).
"""
import tests  # noqa: F401 -- isolate live runtime files

import pickle
import unittest

from hengbot.model import Position, Snapshot
from hengbot.policy import HengbotPolicy

from policy_fixtures import grid, player

LAVA = 85
A, DETOUR_FIRST, GOAL = Position(1, 1), Position(2, 0), Position(1, 5)
CORRIDOR = [Position(1, x) for x in range(2, 5)]
DETOUR = [DETOUR_FIRST, Position(3, 1), Position(3, 2), Position(3, 3),
          Position(3, 4), Position(2, 5)]


def upstairs(cell):
    return cell.has_up_stairs


class GoalRouteCommitmentTest(unittest.TestCase):
    def setUp(self):
        self.policy = HengbotPolicy(damaging_terrain_ids=frozenset({LAVA}))

    def board(self, at, turn, *, monsters=(), lava=(), stairs=(GOAL,)):
        cells = {}
        for cell in [A, *CORRIDOR, GOAL, *DETOUR]:
            cells[cell] = grid(cell.y, cell.x, monster=cell in monsters,
                               upstairs=cell in stairs,
                               terrain_id=LAVA if cell in lava else -1)
        snapshot = Snapshot(player(at.y, at.x), cells, [], turn=turn)
        self.policy._build_grid_index(snapshot)
        return snapshot

    def route(self, snapshot, predicate=upstairs):
        return self.policy._nearest_goal_route(snapshot, predicate)

    def test_detour_is_kept_when_the_blocker_steps_away(self):
        first = self.route(self.board(A, 10, monsters={CORRIDOR[1]}))
        self.assertEqual((first.first_step, first.remaining_edges), (DETOUR_FIRST, 7))
        second = self.route(self.board(DETOUR_FIRST, 20))
        self.assertEqual((second.target, second.first_step, second.remaining_edges),
                         (GOAL, DETOUR[1], 6))

    def test_a_monster_on_the_committed_route_replans(self):
        self.route(self.board(A, 10, monsters={CORRIDOR[1]}))
        route = self.route(self.board(DETOUR_FIRST, 20, monsters={DETOUR[2]}))
        self.assertEqual((route.first_step, route.remaining_edges), (A, 5))

    def test_a_safer_fresh_route_wins_over_a_committed_hazard_route(self):
        # The only route on the first board crosses lava (second pass).
        first = self.route(self.board(A, 10, monsters={CORRIDOR[1]}, lava={DETOUR[2]}))
        self.assertEqual(first.first_step, DETOUR_FIRST)
        route = self.route(self.board(DETOUR_FIRST, 20, lava={DETOUR[2]}))
        self.assertEqual(route.first_step, A)

    def test_a_player_off_the_committed_step_replans(self):
        self.route(self.board(A, 10, monsters={CORRIDOR[1]}))
        route = self.route(self.board(CORRIDOR[0], 20))
        self.assertEqual((route.first_step, route.remaining_edges), (CORRIDOR[1], 3))

    def test_a_goal_reached_earlier_on_the_route_ends_it_there(self):
        self.route(self.board(A, 10, monsters={CORRIDOR[1]}))
        route = self.route(self.board(DETOUR_FIRST, 20, stairs={GOAL, DETOUR[3]}))
        self.assertEqual((route.target, route.first_step, route.remaining_edges),
                         (DETOUR[3], DETOUR[1], 3))

    def test_other_goal_kinds_keep_their_own_commitment(self):
        snapshot = self.board(A, 10, monsters={CORRIDOR[1]})
        self.route(snapshot)
        self.assertEqual(self.route(snapshot, lambda cell: cell.position == CORRIDOR[0])
                         .first_step, CORRIDOR[0])
        route = self.route(self.board(DETOUR_FIRST, 20))
        self.assertEqual(route.first_step, DETOUR[1])

    def test_restored_checkpoint_without_the_table(self):
        self.route(self.board(A, 10, monsters={CORRIDOR[1]}))
        table = pickle.loads(pickle.dumps(self.policy._goal_route_commitments))
        self.assertEqual(table, self.policy._goal_route_commitments)
        del self.policy.__dict__["_goal_route_commitments"]
        route = self.route(self.board(DETOUR_FIRST, 20))
        self.assertEqual(route.first_step, A)


if __name__ == "__main__":
    unittest.main()
