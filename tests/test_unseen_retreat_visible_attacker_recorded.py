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
    No retreat after the player's own teleport (user 2026-10-03 11:4x,
    「テレポートで逃げた攻撃では後退しない」): the hit of 533 was left behind
    by its own Teleportation read, so the landing board 534 no longer arms
    the retreat; 534 is now the first divergence and the only landing board
    asserted.  The yield pins above stay on the recorded boards in a replay
    that forgets the posted read before the landing (declared private-state
    injection), so the pre-teleport hit arms the retreat as live armed it.
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


TELEPORT = 533  # 'rf' emergency:teleport after the unseen bolt
LANDING = 534


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

    def _replay_armed_as_live(self, last):
        rows, _board = self._replay(A_WARMUP, TELEPORT)
        # DECLARED private-state injection: forgets the posted Teleportation read so the pre-teleport hit arms the retreat as live did; the yield pin stays on recorded boards.
        self.policy._teleport_read_watch = None
        later, board = self._replay(TELEPORT + 1, last)
        return {**rows, **later}, board

    def test_hit_left_behind_by_the_teleport_does_not_arm_the_retreat(self):
        rows, board = self._replay(A_WARMUP, LANDING)
        self.assertEqual(rows[TELEPORT], self._live(TELEPORT))
        # The read relocated the player from (5, 52) to (40, 100).
        self.assertEqual(self.recorded[TELEPORT][4], [5, 52])
        self.assertEqual(
            (board.player.position.y, board.player.position.x), (40, 100))
        self.assertEqual(self._live(LANDING), ("7", "unseen:reverse-choke"))
        self.assertFalse(rows[LANDING][1].startswith("unseen:"), rows[LANDING])
        self.assertIsNone(self.policy._unseen_retreat_floor)
        self.assertIsNone(self.policy._unseen_hit_pending_floor)

    def test_replay_reproduces_live_until_the_attacker_is_adjacent(self):
        rows, _board = self._replay_armed_as_live(A_DIVERGENCE - 1)
        self.assertEqual(
            {n: rows[n] for n in range(A_WARMUP + 1, A_DIVERGENCE)},
            {n: self._live(n) for n in range(A_WARMUP + 1, A_DIVERGENCE)},
        )

    def test_adjacent_visible_attacker_is_fought_not_walked_from(self):
        rows, board = self._replay_armed_as_live(A_DIVERGENCE)
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
    """(b) loot-before-recall does not walk at critical HP.

    USER DECISION 2026-10-03 06:0x (heal-vs-teleport, verbatim):
    「次に受けるダメージ予測で判断する。基本的には回復を優先するが、回復量を
    上回るならテレポートを優先する。回復しても状況が悪化するだけだからである。」
    Board 592 (HP 219 -> 197 under an unseen caster, recall counting down) now
    heals first: the next turn is the observed 22-HP hit, below the Healing
    potion's 300.  Live read teleport there, so 592 is the first divergence.
    """

    HEAL_FIRST = 592

    def test_replay_reproduces_live_until_the_heal_first(self):
        rows, board = self._replay(B_START, self.HEAL_FIRST)
        self.assertEqual(
            {n: rows[n] for n in range(B_START, self.HEAL_FIRST)},
            {n: self._live(n) for n in range(B_START, self.HEAL_FIRST)},
        )
        self.assertEqual(self._live(self.HEAL_FIRST), ("rf", "emergency:teleport"))
        self.assertTrue(board.player.recalling)
        self.assertEqual((board.player.hp, board.player.max_hp), (197, 731))
        self.assertLess(board.player.hp, self.policy._low_hp_walk_threshold(731))
        self.assertEqual(self.policy._attributable_observed_loss(board), 22)
        healing = [i for i in board.inventory if i.is_potion and i.sval == 37]
        self.assertEqual(len(healing), 1)
        self.assertEqual(self.policy._healing_potion_effective_hp(board, healing[0]), 300)
        self.assertTrue([i for i in board.inventory if i.is_teleport_scroll])
        self.assertEqual(rows[self.HEAL_FIRST], ("q" + healing[0].slot, "unseen-recall:heal"))

    def _replay_live_teleports(self, last):
        """Replay B_START..last with the Healing potions removed from boards
        592-593 -- DECLARED CONSTRUCTED (2026-10-03 heal-vs-teleport): with no
        potion out-healing the observed hit, the heal-first rule reads the
        teleport as live did, so the later boards follow the live game."""
        import json
        from pathlib import Path
        from hengbot.cli import _consume_response_sequence
        rows, board = {}, None
        for sequence in range(B_START, last + 1):
            line = self.boards[sequence]
            if sequence in (592, 593):
                data = json.loads(line)
                data["inventory"] = [
                    entry for entry in data["inventory"]
                    if not (entry.get("tval") == 75 and entry.get("sval") == 37)
                ]
                self.assertLess(len(data["inventory"]), len(json.loads(line)["inventory"]))
                line = json.dumps(data, ensure_ascii=False)
            _decoded, snapshots = _consume_response_sequence(
                [line], self.policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
            )
            board = snapshots[-1]
            key = self.policy.choose_key(board)
            rows[sequence] = (str(key), self.policy.last_reason)
            self.policy.confirm_key_posted(key)
        return rows, board

    def test_replay_reproduces_live_through_the_teleports(self):
        rows, _board = self._replay_live_teleports(B_DIVERGENCE - 1)
        self.assertEqual(rows, {n: self._live(n) for n in range(B_START, B_DIVERGENCE)})

    def test_critical_hp_waits_for_the_recall_instead_of_collecting(self):
        rows, board = self._replay_live_teleports(B_DIVERGENCE)
        self.assertTrue(board.player.recalling)
        self.assertEqual((board.player.hp, board.player.max_hp), (108, 731))
        self.assertEqual(self._live(B_DIVERGENCE), ("7", "return:seek-loot"))
        self.assertEqual(rows[B_DIVERGENCE], ("5", "return:wait-recall"))


if __name__ == "__main__":
    unittest.main()
