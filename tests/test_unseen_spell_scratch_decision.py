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

Second answer (2026-10-03): 「見える敵がいない時、見えない攻撃のかすり傷が2回
続いた場合もテレポートを読みますか？」 -- 「2回続いても1割か低HP時だけ
(Recommended)」: 「連続の規則にも同じ基準を付ける。2回続いても、合計で最大HPの
1割以上か低HP閾値未満でなければ読まず潜行を続ける。9月28日の死亡の型（マジック・
ミサイル連打）は合計が1割を超えた時点で読む。」  So the two-consecutive-losses
clause also needs the streak's total loss >= 10% of max HP or HP below the
low-HP threshold.

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
THIRD_HIT = 7393839  # HP 767
FOURTH_HIT = 7393843  # HP 756: the streak's total 841 -> 756 = 85 >= 84.1
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
                in (PREVIOUS, FIRST_HIT, SECOND_HIT, THIRD_HIT, FOURTH_HIT)
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

    def test_recorded_missile_streak_reads_when_its_total_reaches_a_tenth(self):
        # Recorded boards 7393814-7393843 in order (live: explore each time):
        # 841 -> 824 -> 779 -> 767 -> 756, every loss an unseen magic
        # missile below 10% of 841, HP above 541.  The streak totals 17, 62,
        # 74: keep exploring; 85 >= 84.1 on 7393843: read the teleport.
        # (The pre-decision bot read on 7393814; before the second answer
        # the streak clause read on 7393832.)
        first = self._board(FIRST_HIT)
        policy = self._policy(first, 841)
        expected_totals = {
            FIRST_HIT: 17, SECOND_HIT: 62, THIRD_HIT: 74, FOURTH_HIT: 85,
        }
        for turn, total in expected_totals.items():
            board = self._board(turn)
            decided = self._decide(policy, board)
            self.assertFalse(board.visible_monsters, turn)
            self.assertEqual(policy._unexplained_damage_streak_loss, total, turn)
            self.assertLess(policy._last_damage_amount, 84, turn)
            self.assertGreater(board.player.hp, policy._low_hp_walk_threshold(841))
            if turn != FOURTH_HIT:
                self.assertNotEqual(decided[1], "emergency:teleport", turn)
                self.assertFalse(policy._emergency_escape_pending, turn)
        self.assertEqual(policy._unexplained_damage_streak, 4)
        self.assertTeleport(policy, board, decided)

    def test_two_unattributed_scratches_below_the_low_hp_threshold_read(self):
        # DECLARED CONSTRUCTED: the first two hit boards with no messages
        # (no unseen-spell evidence: only the streak clause can read) and
        # HP 540 -> 530 -> 520: total 20 < 84.1, but HP 520 is below the
        # low-HP threshold 541 (and above 40%).  The Healing stack is removed
        # too, so the ladder reads (with it, heal-vs-teleport heals first).
        policy = None
        for turn, hp in ((FIRST_HIT, 530), (SECOND_HIT, 520)):
            board = replace(self._board(turn, hp=hp), messages=())
            board = replace(board, inventory=[
                item for item in board.inventory
                if not (item.is_potion and item.sval == 37)
            ])
            if policy is None:
                policy = self._policy(board, 540)
            decided = self._decide(policy, board)
        self.assertIsNone(policy._unseen_attack_evidence)
        self.assertEqual(policy._unexplained_damage_streak, 2)
        self.assertEqual(policy._unexplained_damage_streak_loss, 20)
        self.assertGreater(board.player.hp_ratio, HEAL_HP_RATIO)
        self.assertLess(board.player.hp, policy._low_hp_walk_threshold(841))
        self.assertTeleport(policy, board, decided)

    def test_two_unattributed_scratches_above_the_threshold_keep_going(self):
        # DECLARED CONSTRUCTED: as above at HP 841 -> 830 -> 820 (total 21,
        # HP above 541): no read.
        policy = None
        for turn, hp in ((FIRST_HIT, 830), (SECOND_HIT, 820)):
            board = replace(self._board(turn, hp=hp), messages=())
            if policy is None:
                policy = self._policy(board, 841)
            decided = self._decide(policy, board)
        self.assertEqual(policy._unexplained_damage_streak, 2)
        self.assertEqual(policy._unexplained_damage_streak_loss, 21)
        self.assertNotEqual(decided[1], "emergency:teleport")
        self.assertFalse(policy._emergency_escape_pending)

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
