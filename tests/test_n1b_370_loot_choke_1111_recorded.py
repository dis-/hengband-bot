"""Loot, the detected-pack retreat and Anaguma keep a decision (n1-b life-370, 2026-11-11).

n1-b life-370 (Magic-Eater Lv 42), オークの洞窟23階, stopped with ``loop-detected`` at 15:32 on
(17,123)-(20,125).  Two awake scaven warriors (FRIENDS, level 12) paced a closed room behind the
wall at (14-15,123-124) and came no nearer; hill orcs and an orc shaman stood awake 18-20 cells
down the corridor y=20.

- From (17,123) the scaven are within the convergence window: ``detected:prepare-choke`` chose
  the covered cell (20,123) and walked (18,124), (19,125), (20,124).
- At (20,124) the orcs come into view.  Any awake hostile in view released the retreat and the
  hold's latch for "the visible channel", which has nothing to do at 20 cells; ``seek-loot``
  walked back to (17,123) and the window opened again.
- ``anaguma:walk`` was made at (19,125), where the scaven are within ``RUN_NEAR``, for a start
  beyond it, where the same scaven read as running: released on arrival, and made again after
  ``RETRY_GAME_TURNS``, shorter than the loop.

The fix (owner 2026-11-08 「一度決めた側に固定」): only a hostile the visible channel can answer
ends the retreat (``_visible_channel_answers``), and a pocket released because its pack runs is
not planned again on the floor (``anaguma._release``).

Recorded (tests/fixtures/n1b-370-loot-choke-1111.json.xz,
tests/extract_n1b_370_loot_choke_1111_fixture.py): the 69 player-turn boards before the stop,
decided in order by one policy's public ``choose_key``.

DECLARED RECONSTRUCTED: the capture keeps no skill reply (as test_anaguma_recorded); the
absorption record and the floor's device uses come from the stop's policy summary, because the
uses before the first board (the floor's detections) are not in the capture, and the replay
would otherwise spend the boards casting them.  DECLARED CONSTRUCTED: the turns moved to reach
the hold's end, and the orc moved within reach for the control.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import anaguma
from hengbot.me_powers import MEMORY, FloorMemory, Use
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DETECTED_THREAT_HOLD_MAX_GAME_TURNS, RANGED_MAX_DISTANCE
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-loot-choke-1111.json.xz"
SCAVEN = 1136
HILL_ORC = 149
CHOKE = Position(20, 123)
SIGHT_CELL = Position(20, 124)
WINDOW_CELL = Position(17, 123)
RETREAT = "detected:prepare-choke"
HOLD = "detected:hold-choke"
LOOT = "seek-loot"


class LootChokeLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.board(self.data["boards"][0])
        policy.prime(first)
        # DECLARED RECONSTRUCTED (module docstring).
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(self.data["absorbed"]))
        uses = [Use(served=tuple(row["served"]), used=tuple(row["used"]), trigger=row["trigger"],
                    position=Position(*row["position"]), turn=row["turn"], reason=row["reason"],
                    key=row["key"])
                for row in self.data["floor_uses"]]
        setattr(policy, MEMORY, FloorMemory(floor=first.floor_key, turn=first.turn, uses=uses))
        return policy

    def board(self, raw, *, turn=None):
        raw = copy.deepcopy(raw)
        if turn is not None:
            raw["turn"] = turn
        return parse_snapshot(raw, self.monrace)

    def decide(self, policy, board):
        policy._anaguma_veto = None
        key = policy.choose_key(policy.with_known_skill_exp(board))
        return key, policy.last_reason

    def first_board(self, position, *, after=0, orcs=False):
        for raw in self.data["boards"]:
            board = self.board(raw)
            if raw["turn"] > after and board.player.position == position and (
                    not orcs or board.visible_monsters):
                return raw
        self.fail(f"no board at {position}")

    def walk_to_sight_cell(self, policy):
        """Every recorded board in order, up to the first the orcs show from the sight cell
        with a retreat under way (the boards before it make the floor's memory)."""
        rows = []
        for raw in self.data["boards"]:
            board = self.board(raw)
            rows.append((board.player.position,) + self.decide(policy, board))
            if (board.player.position == SIGHT_CELL and board.visible_monsters
                    and rows[-2][2] == RETREAT):
                return rows, raw
        self.fail("the retreat did not reach the cell")

    # ------------------------------------------------------------ the record

    def test_the_record_alternates_the_three_walkers(self):
        tail = [row["reason"] for row in self.data["decisions"] if row["reason"] != "loop-detected"][-50:]
        self.assertGreaterEqual(tail.count(RETREAT), 15)
        self.assertGreaterEqual(tail.count(LOOT), 15)
        self.assertGreaterEqual(tail.count(anaguma.REASON_WALK), 3)

    def test_the_orcs_are_out_of_every_reach_and_the_scaven_stay_behind_their_wall(self):
        seen = self.board(self.first_board(SIGHT_CELL, orcs=True))
        self.assertTrue(seen.visible_monsters)
        for monster in seen.visible_monsters:
            self.assertFalse(monster.asleep)
            self.assertGreater(monster.distance, 18)
        scaven = [self.board(raw).detected_monsters for raw in self.data["boards"][-30:]]
        cells = {m.position for row in scaven for m in row if m.race_id == SCAVEN}
        self.assertTrue(cells)
        self.assertTrue(all(cell.y in (14, 15) and cell.x in (123, 124) for cell in cells), cells)

    # ------------------------------------------------------------ the pins

    def test_the_retreat_keeps_the_decision_past_the_far_orcs_and_holds_at_its_cell(self):
        """Recorded: ``seek-loot`` '9' back from (20,124).  Now the step on to (20,123)."""
        policy = self.policy()
        rows, raw = self.walk_to_sight_cell(policy)
        self.assertEqual(rows[-1], (SIGHT_CELL, "4", RETREAT), rows)
        self.assertEqual(policy._detected_threat_route[1], CHOKE)
        board = self.board(self.first_board(CHOKE), turn=self.board(raw).turn + 5)
        self.assertTrue(board.visible_monsters)
        self.assertEqual(self.decide(policy, board), ("5", HOLD))
        self.assertIsNotNone(policy._detected_threat_hold)

    def test_the_hold_ends_once_for_the_floor_and_loot_is_not_interrupted_at_the_wall(self):
        """The whole cycle: retreat, the bounded hold, then loot past the window cell for good.
        DECLARED CONSTRUCTED: the turns moved past the hold's bound."""
        policy = self.policy()
        _rows, raw = self.walk_to_sight_cell(policy)
        arrived = self.first_board(CHOKE)
        started = self.board(raw).turn + 5
        self.assertEqual(self.decide(policy, self.board(arrived, turn=started)), ("5", HOLD))
        during = started + DETECTED_THREAT_HOLD_MAX_GAME_TURNS
        self.assertEqual(self.decide(policy, self.board(arrived, turn=during)), ("5", HOLD))
        after = during + 1
        key, reason = self.decide(policy, self.board(arrived, turn=after))
        self.assertNotIn(reason, (RETREAT, HOLD), key)
        for later, cell in ((10, Position(19, 125)), (20, Position(18, 124)), (30, WINDOW_CELL)):
            with self.subTest(cell=cell):
                row = self.board(self.first_board(cell, after=raw["turn"]), turn=after + later)
                key, reason = self.decide(policy, row)
                self.assertNotIn(reason, (RETREAT, HOLD), (key, row.player.position))

    def test_an_orc_within_arrow_range_still_hands_the_retreat_over(self):
        """Control.  DECLARED CONSTRUCTED: a hill orc moved within ``RANGED_MAX_DISTANCE``."""
        policy = self.policy()
        _rows, seen = self.walk_to_sight_cell(policy)
        self.assertIsNotNone(policy._detected_threat_route)
        board = self.board(seen, turn=seen["turn"] + 6)
        near = Position(SIGHT_CELL.y, SIGHT_CELL.x - RANGED_MAX_DISTANCE)
        moved = replace(board, visible_monsters=[
            replace(m, position=near, distance=RANGED_MAX_DISTANCE) if m.race_id == HILL_ORC else m
            for m in board.visible_monsters])
        key, reason = self.decide(policy, moved)
        self.assertIsNone(policy._detected_threat_route)
        self.assertNotEqual(reason, RETREAT, key)


if __name__ == "__main__":
    unittest.main()
