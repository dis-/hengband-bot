"""Recorded pins: walking away while a visible monster claws (Forest 32F, 2026-10-03).

User (2026-10-03 03:4x, verbatim): 「いまモンスターに殴られながらただ歩行する
行動が観測された。これが優先対処」

Source: the live state / decision JSONL streams under ``jsonlog``
of the process that attached at 03:43 (copied at 03:48 before rotation).  The
fixture holds the skill_exp knowledge row (state row 1) and one board per
decision 528-596; ``.recorded.json`` holds the live (sequence, turn, key,
reason, position, visible_hostiles, threat monsters, hp, messages).  The
calibration file is the live one (observed turn 5938750, decision 525).

(a) 533 'rf' emergency:teleport (何かが魔力の矢の呪文を唱えた) armed the
    unseen-attacker retreat on 534; from 545 サーベル・タイガー stood adjacent
    and the armed retreat kept stepping (unseen:reverse-choke x25, HP
    599 -> 257).  Replay: a fresh process, warm-up board 532 (key not
    asserted, it had no floor memory), reproduces live 533-544; 545 is the
    first board with an adjacent visible hostile and the first divergence
    (R4): nothing later is asserted.
(b) 594-595 return:seek-loot '7' at HP 108/731 right after the emergency
    teleports of 592/593.  Replay: a fresh process from board 588 (recall
    already counting down on the board) reproduces live 588-593; 594 is the
    first divergence.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest

from unseen_retreat_visible_replay import (
    A_DIVERGENCE, A_WARMUP, B_DIVERGENCE, B_START, ReplayMixin,
)


class _Replay(ReplayMixin, unittest.TestCase):
    pass


class UnseenRetreatVisibleAttackerRecordedTest(_Replay):
    """(a) the armed unseen retreat yields to an adjacent visible attacker."""

    def test_recorded_rows_are_the_incident(self):
        self.assertEqual(self._live(533), ("rf", "emergency:teleport"))
        self.assertTrue(any(
            message.startswith("何か") for message in self.recorded[533][8]
        ))
        walked = [n for n in range(534, 583)
                  if self._live(n)[1] == "unseen:reverse-choke"]
        self.assertGreaterEqual(len(walked), 40)
        self.assertEqual(self.recorded[A_DIVERGENCE][6][0], ["サーベル・タイガー", 1])
        self.assertTrue(any(
            "サーベル・タイガー" in message
            for n in range(556, 583) for message in self.recorded[n][8] or []
        ))

    def test_replay_reproduces_live_until_the_attacker_is_adjacent(self):
        rows, _board = self._replay(A_WARMUP, A_DIVERGENCE - 1)
        self.assertEqual(
            {n: rows[n] for n in range(A_WARMUP + 1, A_DIVERGENCE)},
            {n: self._live(n) for n in range(A_WARMUP + 1, A_DIVERGENCE)},
        )

    def test_adjacent_visible_attacker_is_fought_not_walked_from(self):
        rows, board = self._replay(A_WARMUP, A_DIVERGENCE)
        adjacent = [
            monster for monster in board.visible_monsters
            if monster.hostile
            and monster.position.distance_to(board.player.position) <= 1
        ]
        self.assertEqual([m.name for m in adjacent], ["サーベル・タイガー"])
        self.assertEqual(
            self._live(A_DIVERGENCE), ("7", "unseen:reverse-choke")
        )
        self.assertEqual(
            rows[A_DIVERGENCE],
            ("3", "melee"),
        )
        self.assertEqual(
            rows[A_DIVERGENCE][0],
            self.policy._direction_key(board.player.position, adjacent[0].position),
        )


class LootBeforeRecallLowHpRecordedTest(_Replay):
    """(b) loot-before-recall does not walk at critical HP."""

    def test_replay_reproduces_live_through_the_teleports(self):
        rows, _board = self._replay(B_START, B_DIVERGENCE - 1)
        self.assertEqual(rows, {n: self._live(n) for n in range(B_START, B_DIVERGENCE)})

    def test_critical_hp_waits_for_the_recall_instead_of_collecting(self):
        rows, board = self._replay(B_START, B_DIVERGENCE)
        self.assertTrue(board.player.recalling)
        self.assertEqual((board.player.hp, board.player.max_hp), (108, 731))
        self.assertEqual(self._live(B_DIVERGENCE), ("7", "return:seek-loot"))
        self.assertEqual(rows[B_DIVERGENCE], ("5", "return:wait-recall"))


if __name__ == "__main__":
    unittest.main()
