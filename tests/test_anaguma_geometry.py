"""Anaguma (穴熊) geometry (docs/anaguma-design.md 2.3, 1.7).  DECLARED CONSTRUCTED.

Owner 2026-11-10: 「岩石溶解を用いて7方壁の窪みを作り待ち伏せする」「後続から遠距離攻撃を受けない
ようにしておくとなお良い」「動物の群れにはジグザグの通路を長めに取る」「4マス/2マスを基本とし、地形と
岩石溶解の回数が許すなら8マスまで伸ばす」.

The boards are constructed: a straight corridor along row 10 in solid granite (tunnel, not
permanent), which is the case the design's tables were computed on.  What is pinned:

- the zigzag cells of the owner's diagram and their digging order (one use per cell);
- a pocket holds (the mouth is the only open neighbour) from 2 cells, every later cell too;
- the projection port (hengbot.projection_path, a port of projection-path-calculator.cpp)
  finds no open grid that projects to the pocket from 3 cells, and from 4 cells only the
  next cell in line projects to the mouth: the breath and ball reach of the followers;
- a permanent wall stops the tunnel; an open grid beside it refuses the cell.
"""

import tests  # noqa: F401 -- isolate live runtime files
import unittest

from policy_fixtures import grid, player
from hengbot import anaguma_geometry as geo
from hengbot.model import Position, Snapshot
from hengbot.projection_path import projection_path

ROW = 10


def board(*, permanent=(), open_cells=()):
    cells = {}
    for y in range(0, 21):
        for x in range(0, 41):
            pos = Position(y, x)
            if y == ROW and 2 <= x <= 38 or (y, x) in open_cells:
                cells[pos] = grid(y, x)
            else:
                cells[pos] = grid(y, x, passable=False, tunnel=(y, x) not in permanent,
                                  permanent=(y, x) in permanent)
    return Snapshot(player(ROW, 20), cells, [], floor_key=(1, 20, 0))


def opened(snapshot, cells):
    grids = dict(snapshot.grids)
    for pos in cells:
        grids[pos] = grid(pos.y, pos.x)
    return Snapshot(snapshot.player, grids, [], floor_key=snapshot.floor_key)


def projectable(snapshot, source, target):
    def blocks(pos):
        found = snapshot.grids.get(pos)
        return found is None or not found.passable
    path = projection_path(source, target, 18, blocks)
    return not path or path[-1] == target


class ZigzagShape(unittest.TestCase):
    def test_cells_alternate_two_columns_from_a_straight_first_cell(self):
        start = Position(ROW, 20)
        cells = [geo.cell(start, (-1, 0), -1, k) for k in range(1, 7)]
        self.assertEqual(cells, [Position(9, 20), Position(8, 21), Position(7, 20),
                                 Position(6, 21), Position(5, 20), Position(4, 21)])
        for before, after in zip([start, *cells], cells):
            self.assertEqual(max(abs(before.y - after.y), abs(before.x - after.x)), 1)

    def test_eight_cells_fit_solid_granite_and_each_stage_is_a_pocket(self):
        snapshot = board()
        tunnel = geo.longest(snapshot, Position(ROW, 20), (-1, 0), -1, 8)
        self.assertEqual(len(tunnel.cells), 8)
        for length in range(2, 9):
            dug = opened(snapshot, tunnel.cells[:length])
            stage = tunnel.prefix(length)
            self.assertTrue(geo.pocket_holds(dug, stage.pocket, stage.mouth), length)

    def test_one_cell_notch_beside_the_corridor_is_no_pocket(self):
        dug = opened(board(), [Position(9, 20)])
        self.assertFalse(geo.pocket_holds(dug, Position(9, 20), Position(ROW, 20)))

    def test_permanent_rock_ends_the_tunnel(self):
        snapshot = board(permanent={(6, 21)})
        tunnel = geo.longest(snapshot, Position(ROW, 20), (-1, 0), -1, 8)
        self.assertEqual(len(tunnel.cells), 3)

    def test_open_ground_beside_a_cell_refuses_it(self):
        snapshot = board(open_cells={(5, 22)})
        tunnel = geo.longest(snapshot, Position(ROW, 20), (-1, 0), -1, 8)
        self.assertEqual(len(tunnel.cells), 3)  # c4 = (6,21) touches the open (5,22)


class Concealment(unittest.TestCase):
    def test_three_cells_hide_the_pocket_and_four_leave_one_breath_cell(self):
        snapshot = board()
        tunnel = geo.longest(snapshot, Position(ROW, 20), (-1, 0), -1, 8)
        for length in range(3, 9):
            dug = opened(snapshot, tunnel.cells[:length])
            stage = tunnel.prefix(length)
            open_cells = [pos for pos, each in dug.grids.items()
                          if each.passable and pos not in (stage.pocket, stage.mouth)]
            shooters = [pos for pos in open_cells if projectable(dug, pos, stage.pocket)]
            self.assertEqual(shooters, [], length)
            reach = sorted(pos for pos in open_cells if projectable(dug, pos, stage.mouth))
            if length >= 4:
                self.assertEqual(reach, [stage.cells[-3]], length)


if __name__ == "__main__":
    unittest.main()
