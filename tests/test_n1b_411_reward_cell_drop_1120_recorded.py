"""n1-b life-411 2026-11-20 06:35:49, town:blocked:stage-deadline:quest (bot main d6b6f0251e).

The town drop of the owner's unsellable named artifacts (sellable_artifacts, owner 2026-11-20
「街の床に捨ててダンジョンに帰還すれば消える」) dropped ★エクスカリパー at (36,118), beside the
Outpost's reward cell (36,119) of quests 31-34; the next drops landed by drop_near on (35,118) and
on (36,119) itself.  An object on a handed-over quest's reward cell rebuilt the reward latch
(town_quest_reward.pending: Q34, finished long before), and ``fixedquest:reward-pickup`` took the
artifact back; the drop put it down again: twelve rounds (rows 244-268) until the quest stage's
deadline stopped the visit.

Now both sides:

* the town drop is made only on a plain empty floor whose whole drop_near reach (d^2 <= 10) holds
  no watched cell -- a fixed quest's reward cell, a store's or a building's entrance, a stair, a
  door, a pile not dropped there -- and walks a bounded way to the nearest such cell;
* the reward pickup takes only a pile that may be the reward: not one the bot dropped itself this
  visit, and of the reward's kind where it is known (FIXED_QUEST_REWARD_TVALS: Q34 a Ring of
  Warning, Q33 シヴァの化身のソフトレザーブーツ).

Recorded: the town-arrival checkpoint of 06:34:52 and its 270 journal rows
(tests/extract_n1b_411_reward_cell_drop_1120_fixture.py).  Rows 0-210 are decided through the
public choose_key and compared with the record (row 211 is where the drop now walks first).

DECLARED CONSTRUCTED:
* from row 211's board on: each walk step moves the player one cell, the drop removes the stack
  from the pack (the rest re-lettered) and puts one object on the player's cell; other boards
  advance the game turn by 10;
* the reward boards: row 245's recorded board (the dropped ★エクスカリパー on (36,119), the player
  on it) on the policy of row 211, with the drop memory of the recorded drops (rows 220, 242, 243:
  (36,118), (35,118), (36,119)) or none, and the pile's class changed to a ring.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import town_quest_reward
from hengbot.cli import _configure_in_store_shop_ops
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-reward-cell-drop-1120"
MATCHED = 211
REWARD_BOARD = 245
REWARD_CELL = Position(36, 119)
RECORDED_DROPS = frozenset({Position(36, 118), Position(35, 118), Position(36, 119)})
DROP_REASON, WALK_REASON = "artifact:drop-unsellable-town", "artifact:drop-walk-town"
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
TVAL_RING = 45


def quiet(call):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call()


class N1b411RewardCellDrop1120RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, cls.journal, steps = load(FIXTURE, scratch)
        with contextlib.redirect_stderr(io.StringIO()):
            _configure_in_store_shop_ops(policy, SimpleNamespace(
                in_store_shop_ops=True, decision_log=scratch / "bot-decisions.jsonl"))
        cls.replayed = []
        for recorded, supply in steps[:MATCHED]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = quiet(lambda: policy.choose_key(board))
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, board, recorded["key"], before)
        cls.board = steps[MATCHED][1]()
        cls.reward_board = steps[REWARD_BOARD][1]()
        cls.checkpoint = checkpoint_bytes(policy)
        cls.history = policy._home_disposal.history_path
        cls.history_bytes = cls.history.read_bytes() if cls.history.exists() else None

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        if self.history_bytes is not None:
            self.history.write_bytes(self.history_bytes)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def decide(self, board):
        policy = self.policy
        before = copy.copy(policy._store_visit)
        key = quiet(lambda: policy.choose_key(board))
        reason = policy.last_reason
        post(policy, board, key, before)
        return key, reason

    def test_the_recorded_rows_and_the_stop(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        reasons = [row["reason"] for row in self.journal]
        self.assertEqual(reasons[269], "town:blocked:stage-deadline:quest")
        self.assertEqual(reasons[244:269].count("fixedquest:reward-pickup"), 12)

    def test_the_drop_goes_away_from_the_reward_cell_and_the_visit_departs(self):
        policy, board = self.policy, self.board
        decided = []
        for _ in range(12):
            key, reason = self.decide(board)
            decided.append((key, reason, board.player.position))
            if reason == DROP_REASON:
                slot = key[-1]
                gone = next(item for item in board.inventory if item.slot == slot)
                grids = dict(board.grids)
                here = board.player.position
                grids[here] = replace(grids[here], object_count=grids[here].object_count + 1,
                                      object_tvals=(*grids[here].object_tvals, gone.tval))
                rest = [item for item in board.inventory if item.slot != slot]
                board = replace(board, grids=grids, turn=board.turn + 10, inventory=tuple(
                    replace(item, slot=chr(ord("a") + index)) for index, item in enumerate(rest)))
            elif reason == WALK_REASON:
                dy, dx = MOVES[key]
                here = board.player.position
                board = replace(board, turn=board.turn + 10, player=replace(
                    board.player, position=Position(here.y + dy, here.x + dx)))
            else:
                board = replace(board, turn=board.turn + 10)
            if reason.startswith("town:cross-town-bm-tour"):
                break
        reasons = [reason for _key, reason, _cell in decided]
        self.assertIn(WALK_REASON, reasons)
        drops = [(key, cell) for key, reason, cell in decided if reason == DROP_REASON]
        self.assertEqual(len(drops), 1)
        cell = drops[0][1]
        # Its whole drop_near reach holds no reward cell, entrance, stair or door.
        for grid in self.board.grids.values():
            if (grid.position.y - cell.y) ** 2 + (grid.position.x - cell.x) ** 2 <= 10:
                self.assertNotEqual(grid.position, REWARD_CELL)
                self.assertFalse(grid.has_up_stairs or grid.has_down_stairs or grid.is_door
                                 or grid.store_number >= 0 or grid.building_type >= 0
                                 or grid.building_special >= 0, grid)
        # No pickup, no reward latch: the visit goes on to its departure tour.
        self.assertFalse(any(reason.startswith(("fixedquest:", "pickup", "seek-loot"))
                             for reason in reasons), reasons)
        self.assertTrue(reasons[-1].startswith("town:cross-town-bm-tour"), reasons)
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertLessEqual(reasons.count(WALK_REASON), 40)

    def test_the_reward_pickup_leaves_the_bots_own_drop(self):
        policy, board = self.policy, self.reward_board
        here = board.grid_at(board.player.position)
        self.assertEqual((here.position, here.object_count), (REWARD_CELL, 1))
        self.assertEqual(self.journal[REWARD_BOARD]["reason"], "fixedquest:reward-pickup")
        policy._artifact_drop_memory = {"cells": RECORDED_DROPS, "pending": None}
        key, reason = self.decide(board)
        self.assertFalse(reason.startswith(("fixedquest:", "pickup")), (key, reason))
        self.assertNotEqual(key, "g")
        self.assertIsNone(policy._fixed_quest_reward_pending)

    def test_the_reward_is_matched_by_its_kind(self):
        policy, board = self.policy, self.reward_board
        here = board.grid_at(REWARD_CELL)
        # No drop memory: a sword on Q34's cell (a Ring of Warning) is still not its reward.
        self.assertNotIn(TVAL_RING, here.object_tvals)
        self.assertIsNone(town_quest_reward.pending(policy, board))
        self.assertFalse(town_quest_reward.reward_pile(policy, board, 34, here))
        # A ring there is the reward: the latch is rebuilt as before.
        grids = dict(board.grids)
        grids[REWARD_CELL] = replace(here, object_tvals=(TVAL_RING,))
        ring = replace(board, grids=grids)
        self.assertTrue(town_quest_reward.reward_pile(policy, ring, 34, grids[REWARD_CELL]))
        self.assertEqual(town_quest_reward.pending(policy, ring), 34)


if __name__ == "__main__":
    unittest.main()
