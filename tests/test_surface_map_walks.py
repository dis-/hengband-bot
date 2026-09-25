"""Class tests: surface-map terrain scope and the Morivant expedition's walks.

Found in the 2026-09-25 20:41 stop (recorded pin:
tests/test_morivant_return_walks_away_recorded.py):

1. Every surface map (each town, the wilderness) shares floor_key (0, 0, 0).
   The routing terrain the policy remembers was reset only on a floor-key
   change, so after an Inn teleport the Outpost's walls and '>' stayed in
   Morivant's routing graph and the walk to Morivant's Inn went round walls
   that are not there.  A change of known town id now forgets the terrain of
   the town left behind; boards of the same town keep it, including boards
   whose shape metadata flickers.
2. The expedition's walks to a declared cell must give the arbiter their
   distance.  Only the outbound walk (``travel-``) did; the return to the
   origin town and the Library walk registered none, so every step after the
   first scored no progress and the owner retired nine cells into a longer
   walk.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, Snapshot, StoreState, STORE_GENERAL
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    DIRECTION_KEYS,
    MORIVANT_FULL_IDENTIFY_COST,
    MORIVANT_LIBRARY_BUILDING_TYPE,
    MORIVANT_TOWN_ID,
    OUTPOST_TOWN_ID,
    TOWN_TRAVEL_STALL_LIMIT,
)
from hengbot.policy_types import MorivantFullIdentifyExpedition
from hengbot.town_maps import find_town_map, parse_town_map

from policy_fixtures import grid, item, player


GAME_ROOT = Path("C:/hengband")
OUTPOST_INN = Position(37, 119)
MORIVANT_INN = Position(43, 92)
OUTPOST_WALL = Position(40, 114)  # open street in Morivant
OUTPOST_ENTRANCE = Position(31, 150)  # the Outpost's '>'; Morivant has none
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}


def _town_maps():
    maps = {}
    for town_index in range(1, 6):
        path = find_town_map(town_index, GAME_ROOT)
        if path is not None:
            maps[town_index - 1] = parse_town_map(path)
    return maps


def _policy() -> HengbotPolicy:
    maps = _town_maps()
    return HengbotPolicy(town_map=maps.get(OUTPOST_TOWN_ID), town_maps=maps)


def _board(town_id, at, grids=(), *, gold=20000, inventory=(), in_town=True, turn=1000):
    cells = {Position(*at): grid(*at)}
    cells.update({cell.position: cell for cell in grids})
    return Snapshot(
        player(*at, hp=500, max_hp=500, gold=gold),
        cells,
        [],
        turn=turn,
        floor_key=(0, 0, 0),
        width=198,
        height=66,
        town_flag=in_town,
        town_id=town_id,
        inventory=list(inventory),
        visited_town_ids=(OUTPOST_TOWN_ID, MORIVANT_TOWN_ID),
    )


def _outpost_board():
    """An Outpost board that shows the wall and the '>' of the leak."""
    return _board(
        OUTPOST_TOWN_ID, (36, 118),
        (
            grid(OUTPOST_WALL.y, OUTPOST_WALL.x, passable=False),
            grid(OUTPOST_ENTRANCE.y, OUTPOST_ENTRANCE.x, entrance=True,
                 downstairs=True, entrance_dungeon_id=1),
        ),
    )


class SurfaceMapTerrainScopeTest(unittest.TestCase):
    def test_terrain_learned_in_one_town_is_not_routed_in_another(self):
        policy = _policy()
        policy.prime(_outpost_board())
        self.assertIn((OUTPOST_WALL.y, OUTPOST_WALL.x), policy._remembered_wall_t)
        self.assertIn(OUTPOST_ENTRANCE, policy._remembered_downstairs)

        morivant = _board(MORIVANT_TOWN_ID, (33, 115))
        policy.prime(morivant)
        self.assertNotIn((OUTPOST_WALL.y, OUTPOST_WALL.x), policy._remembered_wall_t)
        self.assertIn((OUTPOST_WALL.y, OUTPOST_WALL.x), policy._floor_t)
        self.assertNotIn(OUTPOST_ENTRANCE, policy._remembered_downstairs)
        self.assertNotIn(OUTPOST_ENTRANCE, policy._remembered_entrances)
        self.assertNotIn(OUTPOST_ENTRANCE, policy._town_entrance_cells(morivant))

        # Routing in Morivant is what a policy that never saw the Outpost
        # routes: Morivant's own layout.
        fresh = _policy()
        fresh.prime(morivant)
        self.assertEqual(
            policy._town_teleport_route(morivant, OUTPOST_TOWN_ID),
            fresh._town_teleport_route(morivant, OUTPOST_TOWN_ID),
        )
        self.assertEqual(
            policy._town_teleport_route(morivant, OUTPOST_TOWN_ID).route.target,
            MORIVANT_INN,
        )

    def _assert_outpost_forgotten(self, policy, morivant):
        self.assertNotIn((OUTPOST_WALL.y, OUTPOST_WALL.x), policy._remembered_wall_t)
        self.assertIn((OUTPOST_WALL.y, OUTPOST_WALL.x), policy._floor_t)
        self.assertNotIn(OUTPOST_ENTRANCE, policy._remembered_downstairs)
        self.assertNotIn(OUTPOST_ENTRANCE, policy._town_entrance_cells(morivant))
        fresh = _policy()
        fresh.prime(morivant)
        self.assertEqual(
            policy._town_teleport_route(morivant, OUTPOST_TOWN_ID),
            fresh._town_teleport_route(morivant, OUTPOST_TOWN_ID),
        )

    def _assert_outpost_kept(self, policy):
        self.assertIn((OUTPOST_WALL.y, OUTPOST_WALL.x), policy._remembered_wall_t)
        self.assertIn(OUTPOST_ENTRANCE, policy._remembered_downstairs)

    def test_arriving_over_the_wilderness_forgets_the_town_left(self):
        """Outpost -> wilderness -> Morivant (gpt-6-sol P1 on 3a9d2ad4)."""
        policy = _policy()
        policy.prime(_outpost_board())
        policy.prime(replace(
            _board(OUTPOST_TOWN_ID, (36, 118), in_town=False, turn=1010),
            town_id=-1,
        ))
        morivant = _board(MORIVANT_TOWN_ID, (33, 115), turn=1020)
        policy.prime(morivant)
        self._assert_outpost_forgotten(policy, morivant)

    def test_arriving_past_an_unknown_town_id_forgets_the_town_left(self):
        """Outpost -> a board with town id -1 -> Morivant (P1 on 3a9d2ad4)."""
        policy = _policy()
        policy.prime(_outpost_board())
        policy.prime(replace(
            _board(OUTPOST_TOWN_ID, (36, 118), turn=1010), town_id=-1,
        ))
        morivant = _board(MORIVANT_TOWN_ID, (33, 115), turn=1020)
        policy.prime(morivant)
        self._assert_outpost_forgotten(policy, morivant)

    def test_re_entering_the_same_town_keeps_its_terrain(self):
        for between in (
            replace(_board(OUTPOST_TOWN_ID, (36, 118), in_town=False, turn=1010),
                    town_id=-1),
            replace(_board(OUTPOST_TOWN_ID, (36, 118), turn=1010), town_id=-1),
        ):
            with self.subTest(in_town=between.in_town):
                policy = _policy()
                policy.prime(_outpost_board())
                policy.prime(between)
                self._assert_outpost_kept(policy)
                policy.prime(_board(OUTPOST_TOWN_ID, (36, 117), turn=1020))
                self._assert_outpost_kept(policy)

    def test_restored_checkpoint_without_the_town_key(self):
        """A checkpoint from before the key learns it on its next town board."""
        policy = _policy()
        policy.prime(_outpost_board())
        del policy.__dict__["_terrain_town_id"]
        policy.prime(_board(OUTPOST_TOWN_ID, (36, 117), turn=1010))
        self._assert_outpost_kept(policy)
        self.assertEqual(policy._terrain_town_id, OUTPOST_TOWN_ID)
        morivant = _board(MORIVANT_TOWN_ID, (33, 115), turn=1020)
        policy.prime(morivant)
        self._assert_outpost_forgotten(policy, morivant)

    def test_boards_of_the_same_town_keep_its_terrain(self):
        policy = _policy()
        policy.prime(_outpost_board())
        entrance = Position(36, 116)
        policy._town_visit_entrances.add(entrance)
        boards = [
            # A later Outpost board that no longer shows those cells,
            _board(OUTPOST_TOWN_ID, (36, 117), turn=1010),
            # a store page without grids,
            replace(
                _board(OUTPOST_TOWN_ID, (36, 117), turn=1020),
                grids={}, store=StoreState(STORE_GENERAL, []),
            ),
            # and flickering shape metadata (an unknown town id, no size)
            # are not another town.
            replace(_board(OUTPOST_TOWN_ID, (36, 117), turn=1030), town_id=-1),
            replace(_board(OUTPOST_TOWN_ID, (36, 117), turn=1040), width=0, height=0),
            _board(OUTPOST_TOWN_ID, (36, 117), turn=1050),
        ]
        for board in boards:
            policy.prime(board)
            self.assertIn((OUTPOST_WALL.y, OUTPOST_WALL.x), policy._remembered_wall_t)
            self.assertIn(OUTPOST_ENTRANCE, policy._remembered_downstairs)
            self.assertIn(entrance, policy._town_visit_entrances)


def _targets():
    return [
        item(chr(ord("p") + index), 45, index + 1, name=f"ego ring {index}",
             known=True, is_equipment=True, is_ego=True)
        for index in range(2)
    ]


class MorivantWalkLocomotionTest(unittest.TestCase):
    """Each expedition walk closes its registered distance until it arrives."""

    def _walk(self, policy, board, expedition, arrived):
        policy._morivant_full_identify = expedition
        arbiter = policy._town_turn_arbiter
        walk = []
        for move in range(8 * TOWN_TRAVEL_STALL_LIMIT):
            policy.prime(board)
            policy._decision_goal = None
            key = policy._morivant_full_identify_key(board)
            reason = policy.last_reason
            slot = policy._decision_goal
            arbiter.observe(
                in_town=True,
                reason=reason,
                progress_vector=policy._town_arbiter_progress_vector(board, reason),
            )
            telemetry = arbiter.telemetry
            walk.append((key, reason, slot[1].cell if slot else None,
                         telemetry["progress"], telemetry["retired"]))
            if arrived(key) or telemetry["retired"] or key is None:
                break
            dy, dx = STEPS[key[0]]
            position = board.player.position
            board = replace(
                board,
                player=replace(
                    board.player, position=Position(position.y + dy, position.x + dx)
                ),
                grids={Position(position.y + dy, position.x + dx):
                       grid(position.y + dy, position.x + dx)},
                turn=board.turn + 10,
            )
        return walk

    def _assert_walked(self, walk, reason, goal, arrived):
        self.assertTrue(arrived(walk[-1][0]), walk[-1])
        self.assertGreater(len(walk), TOWN_TRAVEL_STALL_LIMIT + 1)
        self.assertEqual(
            {(entry[1], entry[2]) for entry in walk}, {(reason, (goal.y, goal.x))}
        )
        self.assertEqual(
            [(entry[3], entry[4]) for entry in walk], [(True, False)] * len(walk)
        )

    def test_outbound_walk_to_the_origin_inn(self):
        policy = _policy()
        board = _board(OUTPOST_TOWN_ID, (46, 83), inventory=_targets())
        expedition = MorivantFullIdentifyExpedition(OUTPOST_TOWN_ID, ())
        arrived = lambda key: key is not None and key.endswith("mc")  # noqa: E731
        walk = self._walk(policy, board, expedition, arrived)
        self._assert_walked(
            walk, f"town:morivant-full-identify:travel-{MORIVANT_TOWN_ID}",
            OUTPOST_INN, arrived,
        )

    def test_return_walk_to_morivants_inn(self):
        policy = _policy()
        board = _board(MORIVANT_TOWN_ID, (33, 115))
        expedition = MorivantFullIdentifyExpedition(
            OUTPOST_TOWN_ID, (), returning=True
        )
        arrived = lambda key: key is not None and key.endswith("ma")  # noqa: E731
        walk = self._walk(policy, board, expedition, arrived)
        self._assert_walked(
            walk, "town:morivant-full-identify:return", MORIVANT_INN, arrived
        )

    def test_library_walk_from_morivants_inn(self):
        policy = _policy()
        library = policy._town_maps[MORIVANT_TOWN_ID].building_position(
            MORIVANT_LIBRARY_BUILDING_TYPE
        )
        board = _board(
            MORIVANT_TOWN_ID, (MORIVANT_INN.y, MORIVANT_INN.x),
            gold=4 * MORIVANT_FULL_IDENTIFY_COST, inventory=_targets(),
        )
        expedition = MorivantFullIdentifyExpedition(OUTPOST_TOWN_ID, ())
        arrived = lambda key: key is not None and len(key) > 1  # noqa: E731
        walk = self._walk(policy, board, expedition, arrived)
        self._assert_walked(
            walk, "town:morivant-full-identify:library", library, arrived
        )


if __name__ == "__main__":
    unittest.main()
