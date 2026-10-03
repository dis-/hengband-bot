"""Pins: an unseen spell hit with no hostile in view reads the teleport only
when it is material.

USER DECISION 2026-10-03.  Question: 「見える敵がいない時に見えない呪文を受け
たら、どんな時にテレポートを読みますか？（今は被害が1でも読み、森32Fの潜行3回
とも緊急脱出2回ですぐ帰還している。HPほぼ満タンでのかすり傷1と6が2回含まれる）」
Answer: option 「1割以上の被害か低HP時だけ (Recommended)」 -- 「1回で最大HPの
1割以上削られた時か、HPが低HPの閾値（最大HP×50%と最大HP−300の大きい方）未満の
時だけ読む。今朝入れた見えない呪文使いの規則と同じ基準。かすり傷では読まず潜行
を続ける。」

So in ``unseen_lethal`` an unseen spell hit counts when the one move cost at
least 10% of max HP or HP is below the low-HP threshold; the other clauses
(the loss at least HP, HP under 40%, two consecutive unexplained losses, the
loss at least 40% of max HP) are unchanged.

Substrate: the 2026-09-28 death capture of test_unseen_caster_death_recorded
(Mine 23F, max HP 841, magic missiles from an unseen caster, 841 -> 17 over
about 100 boards, every single loss below 84).  The protocol-3 boards carry
no skill list, so every board here fills ``two_weapon_skill`` and
``shield_skill`` with 0 (DECLARED CONSTRUCTED, skill fields only: otherwise
the board's decision is the ~f request).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HEAL_HP_RATIO, HengbotPolicy

from test_unseen_caster_death_recorded import CAPTURE, SHA256

PREVIOUS = 7393801  # HP 841, the last board before the first missile
FIRST_HIT = 7393814  # HP 824: 「何かがマジック・ミサイルの呪文を唱えた。 <x2>」
SECOND_HIT = 7393832  # HP 779: <x4>
TELEPORT_SLOT = "e"


class UnseenSpellScratchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(CAPTURE, "rt", encoding="utf-8") as stream:
            cls.rows = {
                row["turn"]: row
                for line in stream
                if (row := json.loads(line))["turn"]
                in (PREVIOUS, FIRST_HIT, SECOND_HIT)
            }

    def _board(self, turn, **player):
        board = parse_snapshot(self.rows[turn])
        return replace(
            board,
            player=replace(
                board.player, two_weapon_skill=0, shield_skill=0, **player
            ),
        )

    def _policy(self, board, last_hp):
        seed = HengbotPolicy()
        seed._floor_key = board.floor_key
        seed._last_hp = last_hp
        return restore_checkpoint(HengbotPolicy, checkpoint(seed))

    def _decide(self, policy, board):
        key = str(policy.choose_key(board))
        policy.confirm_key_posted(key)
        return key, policy.last_reason

    def assertTeleport(self, policy, board, decided):
        scroll = [i.slot for i in board.inventory if i.is_teleport_scroll]
        self.assertEqual(scroll, [TELEPORT_SLOT])
        self.assertEqual(decided, ("r" + TELEPORT_SLOT, "emergency:teleport"))
        self.assertTrue(policy._emergency_escape_pending)

    def test_recorded_scratch_at_near_full_hp_keeps_exploring(self):
        # Recorded: 841 -> 824 (17, 2% of max HP), HP 98%, nothing in view;
        # the live 09-28 bot explored ('4'); the pre-decision bot read the
        # teleport on this board.
        board = self._board(FIRST_HIT)
        policy = self._policy(board, 841)
        self.assertEqual(self.rows[PREVIOUS]["player"]["hp"], 841)
        self.assertFalse(board.visible_monsters)
        self.assertEqual(board.player.hp, 824)
        self.assertGreater(board.player.hp, policy._low_hp_walk_threshold(841))
        decided = self._decide(policy, board)
        self.assertEqual(policy._unseen_attack_evidence, board.messages[0])
        self.assertEqual(policy._last_damage_amount, 17)
        self.assertLess(policy._last_damage_amount, board.player.max_hp * 0.10)
        self.assertNotEqual(decided[1], "emergency:teleport")
        self.assertFalse(decided[0].startswith("r"), decided)
        self.assertFalse(policy._emergency_escape_pending)

    def test_recorded_second_hit_escapes_on_the_streak(self):
        # Recorded: the next board, 824 -> 779 (45, 5%): two consecutive
        # unexplained losses -- the unchanged streak clause -- read the
        # teleport.  (Conformance: the pre-decision bot read it here too.)
        first = self._board(FIRST_HIT)
        policy = self._policy(first, 841)
        self._decide(policy, first)
        board = self._board(SECOND_HIT)
        decided = self._decide(policy, board)
        self.assertEqual(policy._last_damage_amount, 45)
        self.assertEqual(policy._unexplained_damage_streak, 2)
        self.assertTeleport(policy, board, decided)

    def test_tenth_of_max_hp_hit_reads_the_teleport(self):
        # DECLARED CONSTRUCTED: the first-hit board with HP 756 (one move
        # 841 -> 756 = 85 >= 84.1), still above the low-HP threshold 541 and
        # HP 40%; first loss of the run (streak 1).
        board = self._board(FIRST_HIT, hp=756)
        policy = self._policy(board, 841)
        decided = self._decide(policy, board)
        self.assertEqual(policy._last_damage_amount, 85)
        self.assertEqual(policy._unexplained_damage_streak, 1)
        self.assertGreater(board.player.hp_ratio, HEAL_HP_RATIO)
        self.assertGreater(board.player.hp, policy._low_hp_walk_threshold(841))
        self.assertTeleport(policy, board, decided)

    def _below_threshold(self, *, healing):
        # DECLARED CONSTRUCTED: the first-hit board with HP 523 after 540
        # (one move 17, 2%), below the low-HP threshold max(420.5, 541) but
        # above HP 40% (336.4); first loss of the run (streak 1).  Without
        # ``healing`` the Healing stack (slot c, 6) is also removed.
        board = self._board(FIRST_HIT, hp=523)
        if not healing:
            board = replace(board, inventory=[
                item for item in board.inventory
                if not (item.is_potion and item.sval == 37)
            ])
        policy = self._policy(board, 540)
        decided = self._decide(policy, board)
        self.assertEqual(policy._last_damage_amount, 17)
        self.assertEqual(policy._unexplained_damage_streak, 1)
        self.assertGreater(board.player.hp_ratio, HEAL_HP_RATIO)
        self.assertLess(board.player.hp, policy._low_hp_walk_threshold(841))
        return policy, board, decided

    def test_scratch_below_the_low_hp_threshold_reads_the_teleport(self):
        policy, board, decided = self._below_threshold(healing=False)
        self.assertIsNone(policy._find_heal_potion(board, expected_damage=1))
        self.assertTeleport(policy, board, decided)

    def test_scratch_below_the_low_hp_threshold_heals_first_when_carried(self):
        # The emergency ladder is engaged; USER DECISION 2026-10-03 06:0x
        # (heal-vs-teleport) quaffs the Healing potion (300 >= the next turn,
        # the observed 17) before the teleport.
        policy, board, decided = self._below_threshold(healing=True)
        self.assertTrue(policy._emergency_escape_pending)
        self.assertEqual(decided, ("qc", "item:heal"))

if __name__ == "__main__":
    unittest.main()
