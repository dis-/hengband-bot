"""Pins: no unchecked walking move at low HP or right after a hit.

USER DECISION 2026-10-03 04:0x (verbatim): 「低HPのときの優先度を再度確認。
特に「危険を確認せず歩行」は最悪手。普通に死ぬ。」 and the threshold answer
「HP50%と最大HP-300の大きい方を閾値とする」.  Below max(max_hp * 0.5,
max_hp - 300) -- 431 of this character's 731 -- or right after taking damage,
no walking move that was not checked for danger; instead healing potion ->
teleport/recall -> fight the adjacent enemy.  A flee step is allowed only if
it neither adds adjacent hostiles nor turns away from an adjacent attacker at
least as fast as the player.

DECLARED CONSTRUCTED on the recorded Forest 32F boards of the live 03:43
process (fixture of test_unseen_retreat_visible_attacker_recorded):
* board 532 (live explore, nothing in view) with HP set to 420 on two boards
  (below the threshold, no hit) and the rest rung's cap spent (declared
  wall), with or without the healing potions;
* board 545 (サーベル・タイガー adjacent; the replay through 544 reproduces
  live) with the tiger replaced by a ピンク・ホラー (CONFUSE bite), the
  character's rConf removed and the speed potion / healing potions / escape
  scrolls removed, so that the ladder's own answer is
  ``status-threat:retreat``; for the adjacency case two 腐った死体 are
  placed next to that retreat's square (on grids the dark board does not
  know).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import copy
import unittest
from dataclasses import replace

from hengbot.model import Position, SV_POTION_SPEED
from hengbot.policy_constants import HEAL_POTION_SVALS, QUAFF_KEY

from test_unseen_retreat_visible_attacker_recorded import _Replay

PINK_HORROR = 242
ZOMBIE = 125
LOW_HP = 300
JUST_BELOW = 420  # threshold 431 of 731; a hit too small for the emergency rung


def _strip(board, *, heal=True, speed=False, teleport=False, recall=False):
    def drop(item):
        return (
            (heal and item.is_potion and item.sval in HEAL_POTION_SVALS)
            or (speed and item.is_potion and item.sval == SV_POTION_SPEED)
            or (teleport and item.is_teleport_scroll)
            or (recall and item.is_recall_scroll)
        )
    return replace(board, inventory=[i for i in board.inventory if not drop(i)])


class _Boards(_Replay):
    def _decide(self, board):
        policy = copy.deepcopy(self.policy)
        key = policy.choose_key(board)
        return str(key), policy.last_reason

    def _board_532_low(self):
        """Board 532 (live explore, nothing in view) at HP 420 on two boards
        (no hit), with the rest rung's cap spent -- DECLARED WALL: the live
        audit's 'explore after resting is refused' path."""
        from hengbot.cli import _consume_response_sequence
        from hengbot.policy import REST_CAP
        from pathlib import Path
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[532]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        board = snapshots[-1]
        self.assertEqual(self._live(532), ("1", "explore"))
        self.assertFalse([m for m in board.visible_monsters if m.hostile])
        low = replace(board, player=replace(board.player, hp=JUST_BELOW))
        warm = self.policy.choose_key(low)  # baseline HP 420 (not asserted)
        self.policy.confirm_key_posted(warm)
        self.policy._rest_count = REST_CAP
        return replace(low, turn=low.turn + 10)

    def _board_545(self, *, speed, extras=()):
        _rows, _board = self._replay(532, 544)
        from hengbot.cli import _consume_response_sequence
        from pathlib import Path
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[545]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        board = snapshots[-1]
        tiger = board.visible_monsters[0]
        self.assertEqual(tiger.name, "サーベル・タイガー")
        horror = replace(tiger, race_id=PINK_HORROR, name="ピンク・ホラー", speed=speed)
        crowd = [
            replace(tiger, index=tiger.index + 50 + n, race_id=ZOMBIE,
                    name="腐った死体", speed=100, position=cell,
                    distance=cell.distance_to(board.player.position))
            for n, cell in enumerate(extras)
        ]
        abilities = type(board.player.abilities)(
            a for a in board.player.abilities if a != "resist_conf"
        )
        board = replace(
            board,
            player=replace(board.player, hp=LOW_HP, abilities=abilities),
            visible_monsters=[horror, *crowd],
        )
        return _strip(board, speed=True, teleport=True, recall=True)


class LowHpExploreTest(_Boards):
    """HP 420 of 731, nothing in view, rest refused: no exploring walk."""

    def test_ladder_alone_would_explore(self):
        board = self._board_532_low()
        self.assertGreater(board.player.hp, board.player.max_hp * 0.5)
        self.assertLess(board.player.hp, board.player.max_hp - 300)

    def test_heal_instead_of_explore(self):
        board = self._board_532_low()
        key, reason = self._decide(board)
        potion = self.policy._find_heal_potion(board, expected_damage=1)
        self.assertEqual((key, reason), (QUAFF_KEY + potion.slot, "item:heal"))

    def test_no_potion_reads_recall_rather_than_walking(self):
        board = _strip(self._board_532_low())
        key, reason = self._decide(board)
        recall = next(i for i in board.inventory if i.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot, reason)


class LowHpFleeStepTest(_Boards):
    """Board 545 with an adjacent confusion attacker and no consumables."""

    def test_slower_attacker_retreat_is_kept(self):
        key, reason = self._decide(self._board_545(speed=100))
        self.assertEqual((key, reason), ("7", "status-threat:retreat"))

    def test_turning_away_from_an_equal_speed_attacker_fights_instead(self):
        board = self._board_545(speed=110)
        self.assertEqual(board.player.speed, 110)
        key, reason = self._decide(board)
        horror = board.visible_monsters[0]
        self.assertEqual(
            (key, reason),
            (self.policy._direction_key(board.player.position, horror.position), "melee"),
        )

    def test_retreat_into_more_adjacent_hostiles_fights_instead(self):
        board = self._board_545(
            speed=100, extras=(Position(29, 87), Position(29, 88))
        )
        key, reason = self._decide(board)
        horror = board.visible_monsters[0]
        self.assertEqual(
            (key, reason),
            (self.policy._direction_key(board.player.position, horror.position), "melee"),
        )


class LowHpNoKitUnseenHitTest(_Boards):
    """追加決定2 (10-03 05:1x, verbatim): 「近接で敵の方向が分からなければ
    ランダムな方向に攻撃。遠距離で射線が切れなければ遮蔽と敵のうち近い方に
    移動。」  Board 534 (nothing in view) at HP 420 after a hit, with no
    healing potion, teleport or recall scroll -- DECLARED CONSTRUCTED."""

    def _hit_board(self, message):
        _rows, _board = self._replay(532, 533)
        from hengbot.cli import _consume_response_sequence
        from pathlib import Path
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[534]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        board = snapshots[-1]
        self.assertFalse([m for m in board.visible_monsters if m.hostile])
        board = replace(
            board, player=replace(board.player, hp=JUST_BELOW),
            messages=[message],
        )
        return _strip(board, teleport=True, recall=True)

    def test_unseen_melee_attacks_a_direction_instead_of_walking(self):
        board = self._hit_board("何かに噛まれた。")
        key, reason = self._decide(board)
        self.assertEqual(reason, "no-wait:attack")
        self.assertEqual(key[0], "+")  # do_cmd_alter: attacks what is there
        self.assertIn(key[1:], set("12346789"))

    def test_unseen_ranged_steps_to_cover(self):
        board = self._hit_board("何かが魔力の矢の呪文を唱えた。")
        key, reason = self._decide(board)
        self.assertEqual(reason, "no-wait:flee")
        offsets = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
                   "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
        dy, dx = offsets[key]
        here = board.player.position
        step = Position(here.y + dy, here.x + dx)
        # Cover for an attacker of unknown square: the nearest choke square
        # (independent BFS over the known walkable squares).
        from collections import deque
        from hengbot.policy_constants import SUMMONER_CHOKE_NEIGHBORS
        policy = copy.deepcopy(self.policy)
        policy._build_grid_index(board)

        def cover(cell):
            return policy._open_neighbor_count(board, cell) <= SUMMONER_CHOKE_NEIGHBORS - 1

        distance = {here: 0}
        queue = deque([here])
        while queue:
            cell = queue.popleft()
            for neighbor in policy._walkable_neighbors(board, cell):
                if neighbor not in distance:
                    distance[neighbor] = distance[cell] + 1
                    queue.append(neighbor)
        nearest = min(d for cell, d in distance.items() if d and cover(cell))
        self.assertIn(step, distance)
        self.assertTrue(cover(step) or any(
            cover(cell) and d == nearest and max(
                abs(cell.y - step.y), abs(cell.x - step.x)
            ) <= nearest - 1
            for cell, d in distance.items()
        ), (key, nearest))


if __name__ == "__main__":
    unittest.main()
