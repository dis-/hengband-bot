"""The 50F+ recall wait walks to an item over cells the map does not hold (1123).

Owner 2026-11-23 (verbatim choice): 「見ていないマスも通って向かう — 帰還の発動までに歩いて届く距離
なら、地図に無いマスも床として通る前提で品へ向かう。壁に当たったら別の道を探す。見える敵がいれば
今までどおり拾いをやめる。」  recall_wait_unknown_path ``key``, asked by policy
``_recall_wait_collect_key`` after the walk over the known floor answered nothing.

Recorded (tests/extract_recall_wait_unknown_path_1123_fixture.py), n1-c life-221 on the Mountain (山) 50F,
2026-11-23 18:43: the Word of Recall read under ``deep-teleport:recall`` (live 4695000) at
(23,153); on the next board (live 4695002, recalling, no hostile in view) the wait answered
``return:wait-recall`` '5' with an item 16 cells off at (25,168), the absorbed area mapping
(live 4694954) having remembered the walls and not the floor between.  The replay reads the
Recall on 4695000 as live did; without the change it answers the board with the absorbed
detection (``me-power:new-floor:detect-evil``, the lists being those of a later checkpoint), not
the walk.

DECLARED CONSTRUCTED:
* the absorbed-power lists (``_me_device_lists``) are those of the same life's town-arrival
  checkpoint of 21:11 (turn 4894953), the earliest the server keeps (the snapshot log does not
  carry them);
* ``test_a_hostile_in_view_stops_it``: a detected hostile is put in view on the 4695002 board;
* ``test_a_floor_above_50f_keeps_the_known_walk``: the deep floor's depth is raised to 51 for
  the call, so 50F reads as a floor above it;
* ``test_a_bump_that_leaves_the_cell_unknown_plans_again``: the wait's record of a step into the
  route's first unknown cell is set as if the previous board had sent it and the player had not
  moved.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import deep_recall_loot, recall_wait_reach, recall_wait_unknown_path
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "recall-wait-unknown-path-1123"
WAIT = 4695002
ITEM = Position(25, 168)
HERE = Position(23, 153)


class RecallWaitUnknownPath1123RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode("utf-8")
        cls.raws = [json.loads(line) for line in lines.splitlines() if line.strip()]
        cls.lists = json.loads(lzma.decompress(
            (FIXTURE / "me-device-lists.json.xz").read_bytes()).decode("utf-8"))

    def replay(self):
        """Replay up to the wait board: (policy, its raw board, the reasons decided before)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        start = parse_snapshot(copy.deepcopy(self.raws[0]), self.monrace)
        policy.prime(start)
        policy._skill_exp_cache = (0, 0, start.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED (module docstring): the absorbed-power lists.
        policy._me_device_lists = {kind: (start.turn, tuple(rows))
                                   for kind, (_turn, rows) in self.lists.items()}
        reasons = []
        decided = set()
        for raw in self.raws:
            if raw["turn"] in decided:
                continue
            decided.add(raw["turn"])
            if raw["turn"] == WAIT:
                return policy, raw, reasons
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            reasons.append((raw["turn"], policy.last_reason))
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("the wait board is not in the fixture")

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return board, key, policy.last_reason

    def route(self, policy, board):
        return recall_wait_unknown_path.path(
            policy, board, policy._strategic_hostiles(board),
            recall_wait_reach.max_path_distance(policy, board))

    def test_the_wait_walks_over_unknown_cells_to_the_item(self):
        policy, raw, reasons = self.replay()
        self.assertEqual(reasons[-1], (4695000, "deep-teleport:recall"))
        board, key, reason = self.decide(policy, raw)
        self.assertEqual((board.floor_key, board.player.position), ((14, 50, 0), HERE))
        self.assertTrue(board.player.recalling)
        self.assertEqual([m for m in board.visible_monsters if m.hostile], [])
        self.assertTrue(deep_recall_loot.applies(policy, board))

        # Recorded: ('5', 'return:wait-recall'): no known way to (25,168).
        self.assertEqual((key, reason), ("6", recall_wait_unknown_path.REASON))
        self.assertEqual(policy._loot_target, ITEM)
        route = self.route(policy, board)
        self.assertEqual(route[-1], ITEM)
        self.assertLessEqual(len(route), recall_wait_reach.max_path_distance(policy, board))
        self.assertTrue([cell for cell in route
                         if recall_wait_unknown_path._unknown(policy, board, (cell.y, cell.x))])

    def test_a_hostile_in_view_stops_it(self):
        policy, raw, _reasons = self.replay()
        raw = copy.deepcopy(raw)
        # DECLARED CONSTRUCTED (module docstring): a detected hostile put in view.
        seen = dict(raw["detected_monsters"][0], detected=False, esp=False)
        raw["visible_monsters"] = [*raw.get("visible_monsters", []), seen]

        board, _key, reason = self.decide(policy, raw)

        self.assertTrue([m for m in board.visible_monsters if m.hostile])
        self.assertNotEqual(reason, recall_wait_unknown_path.REASON)

    def test_a_floor_above_50f_keeps_the_known_walk(self):
        policy, raw, _reasons = self.replay()
        # DECLARED CONSTRUCTED (module docstring): 50F read as a floor above the deep floors.
        with mock.patch.object(recall_wait_unknown_path, "DEEP_FLOOR_DEPTH", 51):
            _board, key, reason = self.decide(policy, raw)

        self.assertNotEqual(reason, recall_wait_unknown_path.REASON)
        self.assertNotEqual(key, "6")

    def test_a_bump_that_leaves_the_cell_unknown_plans_again(self):
        policy, raw, _reasons = self.replay()
        board, key, _reason = self.decide(policy, raw)
        self.assertEqual(key, "6")
        first = next(cell for cell in self.route(policy, board)
                     if recall_wait_unknown_path._unknown(policy, board, (cell.y, cell.x)))
        here = board.player.position
        # DECLARED CONSTRUCTED (module docstring): the previous board stepped into ``first``
        # and the player is still where it stood, the cell still unknown.
        setattr(policy, recall_wait_unknown_path.MEMORY,
                (tuple(board.floor_key), board.turn - 1, here, (first.y, first.x)))

        recall_wait_unknown_path.key(policy, board, policy._strategic_hostiles(board))

        self.assertIn((first.y, first.x), policy._blocked_unknown)
        self.assertNotIn(first, self.route(policy, board))


if __name__ == "__main__":
    unittest.main()
