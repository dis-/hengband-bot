"""n1-c life-195 2026-11-11 19:10 loop-detected (Orc cave 23F, build bot-2d3ec8136).

Recorded: tests/fixtures/n1c-195-acid-loop-1111.json.xz
(tests/extract_n1c_195_acid_loop_1111_fixture.py).  Every decision is the public ``choose_key``
of a policy built as the live one (tests.support.recorded._policy).

North of the dirt corridor (50,177) lies a room floored with a shallow acid puddle (浅い酸の沼,
terrain 232, ACID_PUDDLE: hp-mp-processor.cpp deals its damage every 10 game turns,
``deal_damege_by_feat``), (46..49, 174..187), with an open door at each end: (45,174) on the west,
where an ウルク (race 313) stood, and (45,187) on the east.  The exploration stepped '8' from the
dirt onto the puddle at (49,177); there the ウルク came into view and each shot at it became the
step off (damaging_ground.leave_first) across the puddle to the far side (owner 2026-11-09
「渡った先へ出る」): '9', '6', '6' to (48,180), heading for the east door, since the west door was
held.  From (48,180) the wall hid the ウルク, the exploration walked '4' back towards its goal
over the puddle, the ウルク came into view again, and the step off walked '6' again: on the
puddle at both cells every time, until the loop guard.

Now the step off, once it leaves the puddle, keeps leaving it: a walker's step onto another cell
of the puddle is the step off too (damaging_ground.step_off_key), and the safe cell across stays
its goal while it is free (``_crossing``), whether or not the monster that held the other door is
in view.  Once off, the puddle the step off left is given up for the floor visit (claimed as the
engagement retreats claim the cells they leave), so no walker leads back onto it.

DECLARED RECONSTRUCTION: the policy is primed on the dirt board (turn 4667997) and seeded with the
stop's remembered terrain and visit counts (as tests.test_dungeon_stops_1103_recorded's SEEDS), and
the deferred loot (10,44) the stop's ledger held (``_nav_ledger_deferred_loot``).  The first board
is decided only to stand the policy on the dirt (its exploration goal is not the live one, which
came from boards before the ring: (42,179) through the held west door); every later board decides
as recorded before the fix.
DECLARED SYNTHESIS (the walk across): after the fix the player is not where the recorded boards
show it, so the walk across moves the player of the board of (48,180) (turn 4668039, nothing in
view) along the steps the policy takes.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import damaging_ground
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_DELTAS
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-195-acid-loop-1111.json.xz"
STEP_OFF = damaging_ground.STEP_REASON
ACID, DIRT = 232, 88
DRY = Position(50, 177)
EAST_DOOR, WEST_DOOR = Position(45, 187), Position(45, 174)
DEFERRED_LOOT = Position(10, 44)
OUT_OF_VIEW = 4  # the board of (48,180), where the wall hides the ウルク


class AcidCrossingRecurrenceRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.recorded = {row["turn"]: (row["key"], row["reason"]) for row in cls.case["decisions"]}

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.case["boards"][0]
        policy.prime(parse_snapshot(copy.deepcopy(first), self.monrace))
        policy.consume_skill_knowledge({
            "player": {"level": first["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        # SEEDS: the stop's remembered terrain, visit counts and deferred loot.
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in self.case["terrain"][f"{name}_t"])
        for row in self.case["visits"]:
            policy._visit_counts[Position(*row["key"])] = row["count"]
        policy._nav_ledger_deferred_loot.add(DEFERRED_LOOT)
        policy._deferred_loot.add(DEFERRED_LOOT)
        return policy

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return board, key

    def round(self, policy, boards):
        rows = []
        for raw in boards:
            board, key = self.decide(policy, raw)
            rows.append((board.player.position, key, policy.last_reason))
        return rows

    def walk_across(self, policy):
        """(policy, rows of (position, key, reason)) from (48,180) until a step is not taken
        (DECLARED SYNTHESIS)."""
        self.round(policy, self.case["boards"][:OUT_OF_VIEW])
        raw = self.case["boards"][OUT_OF_VIEW]
        here = Position(raw["player"]["y"], raw["player"]["x"])
        turn = raw["turn"]
        rows = []
        for _ in range(12):
            moved = copy.deepcopy(raw)
            moved["turn"] = turn
            moved["player"]["y"], moved["player"]["x"] = here.y, here.x
            board, key = self.decide(policy, moved)
            rows.append((here, key, policy.last_reason, board))
            if damaging_ground.hurts_here(policy, board) is False:
                break
            offset = DIRECTION_DELTAS[(key or "").lstrip("\x1b")]
            here = Position(here.y + offset[0], here.x + offset[1])
            turn += 10
        return rows

    def test_recorded_round(self):
        rows = [(raw["player"]["y"], raw["player"]["x"], self.recorded[raw["turn"]])
                for raw in self.case["boards"]]
        self.assertEqual(rows, [
            (50, 177, ("8", "explore")),
            (49, 177, ("9", STEP_OFF)),
            (48, 178, ("6", STEP_OFF)),
            (48, 179, ("6", STEP_OFF)),
            (48, 180, ("4", "explore")),
            (48, 179, ("6", STEP_OFF)),
            (48, 180, ("4", "explore")),
            (48, 179, ("6", STEP_OFF)),
            (48, 180, ("4", "explore")),
            (48, 179, ("7", "hunt")),
        ])
        for raw in self.case["boards"]:
            board = parse_snapshot(copy.deepcopy(raw), self.monrace)
            terrain = board.grid_at(board.player.position).terrain_id
            self.assertEqual(terrain, DIRT if board.player.position == DRY else ACID)
            seen = [(m["y"], m["x"]) for m in raw["visible_monsters"]]
            if self.recorded[raw["turn"]][1] == STEP_OFF:
                self.assertIn((WEST_DOOR.y, WEST_DOOR.x), seen)
            if self.recorded[raw["turn"]][1] == "explore" and board.player.position != DRY:
                self.assertEqual(seen, [])

    def test_the_puddle_decides_as_recorded_up_to_the_hidden_door(self):
        rows = self.round(self.policy(), self.case["boards"][:OUT_OF_VIEW])
        self.assertEqual([(key, reason) for _here, key, reason in rows[1:]],
                         [self.recorded[raw["turn"]] for raw in self.case["boards"][1:OUT_OF_VIEW]])

    def test_the_step_off_keeps_crossing_when_the_held_door_is_out_of_view(self):
        # Recorded: '4' explore, back over the puddle towards the west door.
        policy = self.policy()
        rows = self.round(policy, self.case["boards"][:OUT_OF_VIEW + 1])
        self.assertEqual(rows[-1][1:], ("6", STEP_OFF))

    def test_no_walker_steps_back_over_the_puddle_in_the_recorded_round(self):
        # The recorded boards keep the player on the puddle's two cells: every decision on them
        # is the step off towards the east door ('6'), the hunt's step '7' onto the puddle too.
        rows = self.round(self.policy(), self.case["boards"])
        for here, key, reason in rows[1:]:
            self.assertEqual(reason, STEP_OFF, (here, key))
        self.assertEqual([key for here, key, _reason in rows if here.x >= 179], ["6"] * 7)

    def test_the_walk_across_reaches_the_east_door(self):
        policy = self.policy()
        rows = self.walk_across(policy)
        cells = [here for here, _key, _reason, _board in rows]
        self.assertEqual(len(cells), len(set(cells)), cells)
        self.assertEqual(cells[-1], EAST_DOOR)
        for here, key, reason, board in rows[:-1]:
            self.assertTrue(damaging_ground.hurts_at(policy, board, here))
            self.assertEqual(reason, STEP_OFF, (here, key))

    def test_the_puddle_left_is_given_up(self):
        policy = self.policy()
        rows = self.walk_across(policy)
        here, key, reason, board = rows[-1]
        veto = policy._walk_veto(board)
        for wet in [cell for cell, _key, _reason, _board in rows[:-1]] + [
                Position(raw["player"]["y"], raw["player"]["x"]) for raw in self.case["boards"][1:]]:
            self.assertIn(wet, veto)
        offset = DIRECTION_DELTAS.get((key or "").lstrip("\x1b"))
        if offset is not None:
            step = Position(here.y + offset[0], here.x + offset[1])
            self.assertFalse(damaging_ground.hurts_at(policy, board, step), (key, reason))


if __name__ == "__main__":
    unittest.main()
