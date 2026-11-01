"""n1c-loops-0336-1102: the n1-c loot corridor loop of 2026-11-02 (build bot-df4001950).

life-100 (Magic-Eater, Lv27, オークの洞窟16階, 03:35-03:36, three loop-detected
stops): the only way from (42,92) to the dropped bolts at (42,70)/(42,72) is
the one-wide corridor of row 42, where a モングバット (race 235) hovered at
(42,72)-(42,77).  The grid index leaves every visible monster's cell out of
the walkable floor, so while the bat was in view the loot route had no path:
the floor-loot claim was released (``loot-retarget``) and exploration (after
the restarts, the descent route) stepped '9' out of the corridor to (41,93).
Out of view, the cell was floor again and ``seek-loot`` stepped '1' straight
back, 40 times.  The loot route now passes the cells of the visible hostiles
that do not block loot, so it is the same in and out of view.

Fixture: tests/fixtures/n1c-loot-corridor-20261102.json.gz
(tests/extract_n1c_loops_0336_1102_fixtures.py).  Every decision is the public
``choose_key`` and every posted key goes through the production executor port.
DECLARED RECONSTRUCTED: the life-100 staff sequence record is the capture's
``_me_staff_sequence``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from tests import test_d57_nav_depth_1101_recorded as nav


FIXTURES = Path(__file__).with_name("fixtures")


def _load(name):
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as stream:
        return json.load(stream)


LOOT_CASE = _load("n1c-loot-corridor-20261102.json.gz")
LOOT_CELL, CORRIDOR_EXIT = Position(42, 72), Position(41, 93)


class LootCorridorRecordedTest(nav.RecordedDrive):
    """life-100: the loot route does not depend on the bat being in view."""

    def test_recorded_rows_alternate_on_the_bat_being_in_view(self):
        rows = {row["turn"]: (row["reason"], row["key"]) for row in LOOT_CASE["decisions"]}
        boards = {raw["turn"]: raw for raw in LOOT_CASE["boards"]}
        self.assertEqual(rows[1469295], ("explore", "9"))
        self.assertEqual(rows[1469310], ("explore", "9"))
        self.assertEqual(rows[1469305], ("seek-loot", "1"))
        self.assertEqual([m["race_id"] for m in boards[1469295]["visible_monsters"]], [235])
        self.assertEqual(boards[1469305]["visible_monsters"], [])

    def test_loot_walk_heads_down_the_corridor_while_the_bat_is_in_view(self):
        # The capture keys absorbed staffs ``staff:<sval>``; the drive's power
        # screen lists them by sval (as test_n1c_5f_loop_1102_recorded).
        record = LOOT_CASE["sequence"]
        case = dict(LOOT_CASE, sequence=dict(record, absorbed={
            key.split(":")[1]: count for key, count in record["absorbed"].items()}))
        boards = copy.deepcopy(LOOT_CASE["boards"])
        policy = nav.new_policy(case, boards)
        rows = self.drive_boards(case, boards, policy)
        # The recorded boards do not follow the drive's walk; the position
        # stuck escape (``breakout``) answering that is not part of the scene.
        in_view = [(raw, key, reason) for raw, key, reason in rows
                   if nav.step_of(raw, key) is not None and raw["visible_monsters"]
                   and reason != "breakout"]
        self.assertGreaterEqual(len(in_view), 3)
        for raw, key, reason in in_view:
            step = nav.step_of(raw, key)
            self.assertEqual(reason, "seek-loot", (raw["turn"], key, reason))
            self.assertLess(step.x, raw["player"]["x"], (raw["turn"], key, reason))
            self.assertNotEqual(step, CORRIDOR_EXIT, (raw["turn"], key, reason))
        self.assertEqual(policy._loot_target, LOOT_CELL)


if __name__ == "__main__":
    unittest.main()
