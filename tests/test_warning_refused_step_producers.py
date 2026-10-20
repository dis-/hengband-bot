"""Declared boards: every remaining step producer skips a grid the weapon warning refused (#93 round 2).

Owner direction 2026-10-19 (one question, one predicate): "may the bot step
onto cell C now?" answers False for a warning-refused grid for every step
producer.  Round 1 (tests/test_warning_refused_step_recorded.py) applied
``_warning_step_refused`` to the probe, the breeder breakthrough and the
choke route; these pins cover the producers its report listed as not
consulting it: the descent route (ledger path and BFS), the summoner retreat
route, the positional oscillation breaker, the three low-HP no-kit choices,
the flee fallback and ``_breakout_step``.

Every board is DECLARED (constructed, not recorded).  On each the refused
grid is the producer's old choice: before the fix the producer returns it
(or ``_step_toward`` turns it into the gate's WAIT); after the fix another
legal grid.  Controls: the same board without the refusal keeps the old
choice, and with no movement supply left (物資が全て尽きている場合のみ
徒歩強行を許す) the predicate is False, the producer still picks the grid and
``_step_toward`` posts the forced walk ``<dir>y``.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation

import unittest
from dataclasses import replace

from hengbot.model import (
    SV_SCROLL_TELEPORT,
    TVAL_SCROLL,
    Position,
    Snapshot,
)
from hengbot.policy import WAIT_KEY, HengbotPolicy

from policy_fixtures import grid, hostile, item, player

FLOOR_KEY = (1, 30, 0)
DIRECTION = {(-1, -1): "7", (-1, 0): "8", (-1, 1): "9", (0, -1): "4",
             (0, 1): "6", (1, -1): "1", (1, 0): "2", (1, 1): "3"}


def _key_to(origin: Position, cell: Position) -> str:
    return DIRECTION[(cell.y - origin.y, cell.x - origin.x)]


def _board(origin, floors, *, supplies=True, messages=(), monsters=(), marks=None):
    """A walled box around ``floors`` (``marks`` maps a cell to grid kwargs)."""
    marks = marks or {}
    cells = {origin, *floors, *marks}
    ys = [cell.y for cell in cells]
    xs = [cell.x for cell in cells]
    grids = {
        Position(y, x): grid(y, x, passable=False)
        for y in range(min(ys) - 1, max(ys) + 2)
        for x in range(min(xs) - 1, max(xs) + 2)
    }
    for cell in cells:
        grids[cell] = grid(cell.y, cell.x)
    for cell, kwargs in marks.items():
        grids[cell] = grid(cell.y, cell.x, **kwargs)
    for monster in monsters:
        grids[monster.position] = grid(
            monster.position.y, monster.position.x, monster=True
        )
    inventory = [item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)] if supplies else []
    return Snapshot(
        player(origin.y, origin.x, hp=100, max_hp=400),
        grids,
        list(monsters),
        messages=list(messages),
        inventory=inventory,
        floor_key=FLOOR_KEY,
        width=80,
        height=40,
    )


def _policy(snapshot):
    policy = HengbotPolicy()
    policy._floor_key = snapshot.floor_key
    policy._build_grid_index(snapshot)
    return policy


def _row(y, x0, x1):
    return [Position(y, x) for x in range(x0, x1 + 1)]


class DescentRouteTest(unittest.TestCase):
    """_descent_step: the BFS and the committed ledger path."""

    ORIGIN = Position(10, 10)
    REFUSED = Position(10, 11)
    DETOUR = Position(11, 10)

    def _snapshot(self, *, supplies=True):
        floors = [
            Position(10, 12),
            self.DETOUR,
            Position(12, 11),
            Position(12, 12),
            Position(11, 13),
            self.REFUSED,
        ]
        return _board(
            self.ORIGIN,
            floors,
            supplies=supplies,
            marks={Position(10, 13): {"downstairs": True}},
        )

    def test_bfs_skips_a_refused_grid(self):
        snapshot = self._snapshot()
        policy = _policy(snapshot)
        policy._latch_warning_refusal(self.REFUSED)
        self.assertEqual(policy._descent_step(snapshot), self.DETOUR)

    def test_committed_path_onto_a_refused_grid_is_replanned(self):
        snapshot = self._snapshot()
        policy = _policy(snapshot)
        self.assertEqual(policy._descent_step(snapshot), self.REFUSED)
        self.assertEqual(policy._nav_ledger.descent_path[0], self.REFUSED)
        policy._latch_warning_refusal(self.REFUSED)
        self.assertEqual(policy._descent_step(snapshot), self.DETOUR)

    def test_control_without_refusal_keeps_the_direct_step(self):
        snapshot = self._snapshot()
        self.assertEqual(_policy(snapshot)._descent_step(snapshot), self.REFUSED)

    def test_control_forced_walk_still_walks_with_y(self):
        snapshot = self._snapshot(supplies=False)
        policy = _policy(snapshot)
        policy._latch_warning_refusal(self.REFUSED)
        step = policy._descent_step(snapshot)
        self.assertEqual(step, self.REFUSED)
        self.assertEqual(policy._step_toward(snapshot, step), "6y")


class SummonerRetreatRouteTest(unittest.TestCase):
    """_summoner_retreat_route: the covered-cell BFS."""

    ORIGIN = Position(10, 10)
    REFUSED = Position(9, 11)
    EAST = Position(10, 11)

    def _snapshot(self, *, supplies=True):
        summoner = hostile(1, 10, 5, distance=5, can_summon=True)
        floors = [
            *_row(10, 6, 9),
            self.EAST, Position(10, 12), Position(10, 13), Position(10, 14),
            self.REFUSED, Position(8, 12), Position(7, 13),
        ]
        snapshot = _board(
            self.ORIGIN, floors, supplies=supplies, monsters=[summoner]
        )
        return snapshot, summoner

    def _first_step(self, refused, *, supplies=True):
        snapshot, summoner = self._snapshot(supplies=supplies)
        policy = _policy(snapshot)
        if refused:
            policy._latch_warning_refusal(self.REFUSED)
        _, step = policy._summoner_retreat_route(snapshot, [summoner], [summoner])
        return policy, snapshot, step

    def test_route_skips_a_refused_grid(self):
        _, _, step = self._first_step(True)
        self.assertEqual(step, self.EAST)

    def test_control_without_refusal_keeps_the_covered_step(self):
        _, _, step = self._first_step(False)
        self.assertEqual(step, self.REFUSED)

    def test_control_forced_walk_still_walks_with_y(self):
        policy, snapshot, step = self._first_step(True, supplies=False)
        self.assertEqual(step, self.REFUSED)
        self.assertEqual(policy._step_toward(snapshot, step), "9y")


class PositionalOscillationBreakTest(unittest.TestCase):
    """_break_positional_oscillation: the inline neighbour choice."""

    ORIGIN = Position(10, 10)
    REFUSED = Position(9, 9)
    NEXT = Position(9, 10)

    def _key(self, refused, *, supplies=True):
        floors = [
            Position(y, x) for y in range(8, 13) for x in range(8, 13)
        ]
        snapshot = _board(self.ORIGIN, floors, supplies=supplies)
        policy = _policy(snapshot)
        if refused:
            policy._latch_warning_refusal(self.REFUSED)
        # First call records the outcome marker; the same board again is a
        # no-progress decision after a two-cell back-and-forth window.
        self.assertEqual(policy._break_positional_oscillation(snapshot, "6"), "6")
        policy._position_changed = False
        for index in range(23):
            policy._osc_positions.append(
                Position(10, 11) if index % 2 == 0 else self.ORIGIN
            )
        return policy._break_positional_oscillation(snapshot, "6"), policy

    def test_breaker_skips_a_refused_grid(self):
        key, policy = self._key(True)
        self.assertEqual(key, _key_to(self.ORIGIN, self.NEXT))
        self.assertEqual(policy.last_reason, "nav:break-oscillation")

    def test_control_without_refusal_keeps_the_least_visited_grid(self):
        key, _ = self._key(False)
        self.assertEqual(key, _key_to(self.ORIGIN, self.REFUSED))

    def test_control_forced_walk_still_walks_with_y(self):
        key, _ = self._key(True, supplies=False)
        self.assertEqual(key, "7y")


class LowHpNoKitHitTest(unittest.TestCase):
    """_low_hp_no_kit_hit_key: neighbour, toward-the-shooter and cover BFS."""

    def _run(self, snapshot, refused, hostiles=()):
        policy = _policy(snapshot)
        policy._took_damage = True
        if refused is not None:
            policy._latch_warning_refusal(refused)
        key = policy._low_hp_no_kit_hit_key(snapshot, list(hostiles))
        return key, policy

    # (a) the first unexposed neighbour --------------------------------------
    ORIGIN = Position(10, 10)
    NORTH = Position(9, 10)
    SOUTH = Position(11, 10)

    def _neighbour_board(self, *, supplies=True):
        archer = replace(hostile(1, 10, 15, distance=5), name="Orc archer")
        floors = [*_row(10, 9, 14), self.NORTH, self.SOUTH]
        snapshot = _board(
            self.ORIGIN, floors, supplies=supplies,
            messages=["Orc archer fires an arrow."], monsters=[archer],
        )
        return snapshot, archer

    def test_neighbour_skips_a_refused_grid(self):
        snapshot, archer = self._neighbour_board()
        key, policy = self._run(snapshot, self.NORTH, [archer])
        self.assertEqual(key, _key_to(self.ORIGIN, self.SOUTH))
        self.assertEqual(policy.last_reason, "no-wait:flee")

    def test_neighbour_control_without_refusal(self):
        snapshot, archer = self._neighbour_board()
        key, _ = self._run(snapshot, None, [archer])
        self.assertEqual(key, _key_to(self.ORIGIN, self.NORTH))

    def test_neighbour_control_forced_walk_still_walks_with_y(self):
        snapshot, archer = self._neighbour_board(supplies=False)
        key, _ = self._run(snapshot, self.NORTH, [archer])
        self.assertEqual(key, _key_to(self.ORIGIN, self.NORTH) + "y")

    # (b) the step toward a named shooter -------------------------------------
    TOWARD = Position(10, 11)

    def _toward_board(self, *, supplies=True):
        archer = replace(hostile(1, 10, 13, distance=3), name="Orc archer")
        floors = [
            Position(y, x) for y in range(8, 13) for x in range(8, 14)
        ] + [Position(13, 8), Position(14, 8), Position(15, 8)]
        snapshot = _board(
            self.ORIGIN, floors, supplies=supplies,
            messages=["Orc archer fires an arrow."], monsters=[archer],
        )
        return snapshot, archer

    def test_toward_skips_a_refused_grid(self):
        snapshot, archer = self._toward_board()
        key, policy = self._run(snapshot, self.TOWARD, [archer])
        # The walk to cover (14, 8) instead: first step (11, 9).
        self.assertEqual(key, _key_to(self.ORIGIN, Position(11, 9)))
        self.assertEqual(policy.last_reason, "no-wait:flee")

    def test_toward_control_without_refusal(self):
        snapshot, archer = self._toward_board()
        key, _ = self._run(snapshot, None, [archer])
        self.assertEqual(key, _key_to(self.ORIGIN, self.TOWARD))

    def test_toward_control_forced_walk_still_walks_with_y(self):
        snapshot, archer = self._toward_board(supplies=False)
        key, _ = self._run(snapshot, self.TOWARD, [archer])
        self.assertEqual(key, _key_to(self.ORIGIN, self.TOWARD) + "y")

    # (c) the first step of the walk to cover ---------------------------------
    CORNER = Position(9, 9)

    def _cover_board(self, *, supplies=True):
        room = [Position(y, x) for y in range(9, 12) for x in range(9, 12)]
        floors = room + [
            Position(8, 8), Position(7, 7),
            Position(12, 10), Position(13, 10), Position(14, 10),
        ]
        return _board(
            self.ORIGIN, floors, supplies=supplies,
            messages=["Something mumbles."],
        )

    def test_cover_walk_skips_a_refused_grid(self):
        key, policy = self._run(self._cover_board(), self.CORNER)
        # The choke (13, 10) instead of (8, 8): first step (11, 9).
        self.assertEqual(key, _key_to(self.ORIGIN, Position(11, 9)))
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "no-wait:flee")

    def test_cover_control_without_refusal(self):
        key, _ = self._run(self._cover_board(), None)
        self.assertEqual(key, _key_to(self.ORIGIN, self.CORNER))

    def test_cover_control_forced_walk_still_walks_with_y(self):
        key, _ = self._run(self._cover_board(supplies=False), self.CORNER)
        self.assertEqual(key, _key_to(self.ORIGIN, self.CORNER) + "y")


class FleeFallbackTest(unittest.TestCase):
    """_flee_step: the relaxed fallback when every neighbour is avoided."""

    ORIGIN = Position(10, 10)
    REFUSED = Position(10, 11)
    OTHER = Position(9, 11)

    def _step(self, refused, *, supplies=True):
        brute = hostile(1, 10, 8, distance=2)
        floors = [
            Position(10, 9), self.REFUSED, self.OTHER, Position(10, 12),
            Position(8, 12),
        ]
        snapshot = _board(
            self.ORIGIN, floors, supplies=supplies, monsters=[brute]
        )
        policy = _policy(snapshot)
        # Every walkable neighbour is an engagement-avoided grid already.
        policy._engagement_avoid_cells |= {
            Position(10, 9), self.REFUSED, self.OTHER
        }
        if refused:
            policy._latch_warning_refusal(self.REFUSED)
        return policy._flee_step(snapshot, [brute]), policy, snapshot

    def test_fallback_never_takes_a_refused_grid(self):
        step, _, _ = self._step(True)
        self.assertEqual(step, self.OTHER)

    def test_control_without_refusal_keeps_the_best_grid(self):
        step, _, _ = self._step(False)
        self.assertEqual(step, self.REFUSED)

    def test_control_forced_walk_still_walks_with_y(self):
        step, policy, snapshot = self._step(True, supplies=False)
        self.assertEqual(step, self.REFUSED)
        self.assertEqual(policy._step_toward(snapshot, step), "6y")


class BreakoutStepTest(unittest.TestCase):
    """_breakout_step (the livelock breaker that bypasses _step_toward)."""

    ORIGIN = Position(10, 10)
    REFUSED = Position(9, 10)
    NEXT = Position(10, 9)

    def _step(self, refused, *, supplies=True):
        floors = [Position(y, x) for y in range(9, 12) for x in range(9, 12)]
        snapshot = _board(self.ORIGIN, floors, supplies=supplies)
        policy = _policy(snapshot)
        if refused:
            policy._latch_warning_refusal(self.REFUSED)
        # The failing key was east ('6'); south is well trodden.
        policy._visit_counts[Position(11, 10)] = 3
        return policy._breakout_step(snapshot, "6")

    def test_breakout_skips_a_refused_grid(self):
        self.assertEqual(self._step(True), self.NEXT)

    def test_control_without_refusal_keeps_the_first_grid(self):
        self.assertEqual(self._step(False), self.REFUSED)

    def test_control_forced_walk_keeps_the_grid(self):
        self.assertEqual(self._step(True, supplies=False), self.REFUSED)


if __name__ == "__main__":
    unittest.main()
