"""The per-board memos of the walk, the grid index and the town route start again with each decision.

Maintainability review 2026-11-23 (a)-6 (「肥大化しているファイルやルーティーンの無駄もチェック」):
one decision asked ``_walkable_neighbors`` ~1,600 times (each asking ``floor_step_fits`` and
``_on_town_border`` of the same cells again), built the grid index of one board twice and ran
the same town BFS up to four times.  The memos that replace the repeats
(``policy._walk_step_memo``, ``policy_navigation._grid_index_pass_memo``,
``policy_town._town_route_memo``) must answer exactly what the computation answers, so each
is dropped when what it was computed from changes: a new decision, another board, a grid
index rebuilt from changed memory.

CONSTRUCTED: a 10x10 town board of plain floor; a pile on (5,6) that the terminal pack
reserve refuses (20 of 23 slots carried, one non-gold object).
"""
import tests  # noqa: F401 -- isolate runtime files

import unittest

from hengbot import policy as policy_module
from hengbot import policy_navigation, policy_town
from hengbot.item_reservation import decision_caches_disabled
from hengbot.model import Position, Snapshot, TVAL_POTION
from hengbot.policy import HengbotPolicy
from policy_fixtures import grid, item, player

HERE = Position(5, 5)
PILE = Position(5, 6)
FAR = Position(5, 8)


def board(*, pile: bool) -> Snapshot:
    grids = {}
    for y in range(10):
        for x in range(10):
            edge = y in (0, 9) or x in (0, 9)
            heap = pile and (y, x) == (PILE.y, PILE.x)
            grids[Position(y, x)] = grid(
                y, x, passable=not edge, objects=1 if heap else 0,
                object_tvals=(TVAL_POTION,) if heap else ())
    return Snapshot(
        player=player(HERE.y, HERE.x), grids=grids, visible_monsters=[],
        width=10, height=10, town_flag=True, town_id=1,
        inventory=[item(slot, TVAL_POTION, slot, name=f"potion {slot}")
                   for slot in range(20)],
    )


def decide(policy: HengbotPolicy, snapshot: Snapshot) -> None:
    """The board-dependent start of a decision the memos hang on."""
    policy._begin_map_predicate_cache(snapshot)
    policy._build_grid_index(snapshot)


class WalkStepMemoTest(unittest.TestCase):
    def test_a_new_decision_answers_its_own_board(self):
        policy = HengbotPolicy()
        heaped, cleared = board(pile=True), board(pile=False)
        decide(policy, heaped)
        self.assertNotIn(PILE, policy._walkable_neighbors(heaped, HERE))
        decide(policy, cleared)
        self.assertIn(PILE, policy._walkable_neighbors(cleared, HERE))
        table = policy_module._walk_step_memo[policy]
        self.assertIs(table[0], cleared)
        self.assertNotIn(id(heaped), table[1])

    def test_the_memo_answers_what_the_computation_answers(self):
        policy = HengbotPolicy()
        heaped = board(pile=True)
        decide(policy, heaped)
        cached = [policy._walkable_neighbors(heaped, HERE) for _ in range(2)]
        with decision_caches_disabled():
            plain = policy._walkable_neighbors(heaped, HERE)
        self.assertEqual(cached, [plain, plain])


class GridIndexPassMemoTest(unittest.TestCase):
    def test_memory_forgotten_on_the_same_board_is_learned_again(self):
        # *Destruction* (destruction_use.forget_circle) and the floor reset remove cells from
        # the remembered sets; a rebuild on the same board must show them again.
        policy = HengbotPolicy()
        snapshot = board(pile=False)
        decide(policy, snapshot)
        self.assertIn((PILE.y, PILE.x), policy._floor_t)
        policy._remembered_floor_t.discard((PILE.y, PILE.x))
        policy._build_grid_index(snapshot)
        self.assertIn((PILE.y, PILE.x), policy._floor_t)
        policy._remembered_floor_t.clear()
        policy._remembered_known_t.clear()
        policy._build_grid_index(snapshot)
        self.assertIn((PILE.y, PILE.x), policy._floor_t)

    def test_another_board_is_passed_again(self):
        policy = HengbotPolicy()
        first, second = board(pile=False), board(pile=False)
        decide(policy, first)
        decide(policy, second)
        self.assertIs(policy_navigation._grid_index_pass_memo[policy][0], second)


class TownRouteMemoTest(unittest.TestCase):
    def test_a_rebuilt_grid_index_routes_again(self):
        policy = HengbotPolicy()
        snapshot = board(pile=False)
        decide(policy, snapshot)
        self.assertIsNotNone(policy._town_map_goal_route(snapshot, FAR))
        # The column between the player and the target is no longer walkable.
        policy._floor_t = {cell for cell in policy._floor_t if cell[1] != 7}
        self.assertIsNone(policy._town_map_goal_route(snapshot, FAR))

    def test_a_new_decision_starts_an_empty_table(self):
        policy = HengbotPolicy()
        first, second = board(pile=False), board(pile=False)
        decide(policy, first)
        policy._town_map_goal_route(first, FAR)
        decide(policy, second)
        route = policy._town_map_goal_route(second, FAR)
        table = policy_town._town_route_memo[policy]
        self.assertIs(table[0], second)
        self.assertEqual([question[0] for question in table[1]], [id(second)])
        with decision_caches_disabled():
            self.assertEqual(policy._town_map_goal_route(second, FAR), route)


if __name__ == "__main__":
    unittest.main()
