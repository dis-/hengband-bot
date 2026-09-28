"""Captured first unseen caster hit and independent HP-loss escape pins."""

import tests  # noqa: F401
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HEAL_HP_RATIO, HengbotPolicy


CAPTURE = Path(
    "C:/hengband/bot-client/jsonlog/"
    "incident-20260928-0458-death-unseen-magic-missile.state.jsonl.gz"
)
SHA256 = "ce1667110e02d5f979979d6c78e9d3beae32ba30ca6db7ba1fe901fdc32b1ae5"
DECISIONS = CAPTURE.with_name(CAPTURE.name.replace(".state.", ".decisions."))
DECISIONS_SHA256 = "033e88e2fc4224183d13ff4c7dfce1f443b08a1ebd1ad1fa11a9c21dccc8368e"
FIRST_TURN = 7393814


class UnseenCasterDeathRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == SHA256
        assert hashlib.sha256(DECISIONS.read_bytes()).hexdigest() == DECISIONS_SHA256
        with gzip.open(CAPTURE, "rt", encoding="utf-8") as stream:
            cls.raw = next(
                row
                for line in stream
                if (row := json.loads(line))["turn"] == FIRST_TURN
            )
        with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
            cls.decisions = {
                row["decision_sequence"]: row
                for line in stream
                if (row := json.loads(line))["decision_sequence"] in (27367, 27368)
            }
        cls.board = parse_snapshot(cls.raw)

    def test_first_captured_hit_escapes_with_teleport(self):
        board = self.board
        self.assertEqual(
            (
                self.decisions[27367]["turn"],
                self.decisions[27367]["key"],
                self.decisions[27367]["player"]["hp"],
            ),
            (7393801, "1", 841),
        )
        self.assertEqual(
            (
                self.decisions[27368]["turn"],
                self.decisions[27368]["reason"],
                self.decisions[27368]["key"],
            ),
            (FIRST_TURN, "explore", "4"),
        )
        self.assertEqual(
            self.decisions[27368]["threat_prediction"]["operational_total"], 0
        )
        self.assertEqual(
            (board.floor_key, board.player.hp, board.player.max_hp),
            ((3, 23, 0), 824, 841),
        )
        self.assertGreater(board.player.hp_ratio, HEAL_HP_RATIO)
        self.assertFalse(board.visible_monsters)
        self.assertEqual(board.messages[0], "何かがマジック・ミサイルの呪文を唱えた。 <x2>")
        seed = HengbotPolicy()
        seed._floor_key = board.floor_key
        seed._last_hp = 841
        policy = restore_checkpoint(HengbotPolicy, checkpoint(seed))
        policy._observe(board)
        self.assertEqual(policy._unseen_attack_evidence, board.messages[0])
        self.assertEqual(policy._emergency_item(board, []), "re")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_message_families_and_failed_cast_are_presence_evidence(self):
        for message in (
            "何かがマジック・ミサイルの呪文を唱えた。 <x2>",
            "何かは呪文を唱えようとしたが失敗した。",
            "何かが炎のブレスを吐いた。",
            "何かがファイア・ボールの呪文を唱えた。",
            "何かが矢を放った。",
            "何かがあなたを指さして呪った。",
            "何かがロケットを発射した。",
            "It casts a magic missile.",
            "Something breathes fire.",
            "It points at you and curses.",
            "It mumbles.",
        ):
            with self.subTest(message=message):
                self.assertTrue(HengbotPolicy._is_unseen_attack_message(message))

    def test_unattributed_sustained_loss_escapes(self):
        board = replace(self.board, messages=())
        seed = HengbotPolicy()
        seed._floor_key = board.floor_key
        seed._last_hp = 841
        policy = restore_checkpoint(HengbotPolicy, checkpoint(seed))
        policy._observe(board)
        self.assertIsNone(policy._unseen_attack_evidence)
        self.assertEqual(policy._unexplained_damage_streak, 1)
        next_board = replace(
            board, player=replace(board.player, hp=807), turn=board.turn + 1
        )
        policy._observe(next_board)
        self.assertEqual(policy._unexplained_damage_streak, 2)
        self.assertEqual(policy._emergency_item(next_board, []), "re")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_visible_monster_does_not_count_as_unseen_loss(self):
        board = replace(self.board, messages=(), visible_monsters=(object(),))
        policy = HengbotPolicy()
        policy._took_damage = True
        policy._last_damage_amount = 11
        policy._unexplained_damage_streak = 2
        self.assertIsNone(policy._emergency_item(board, []))


if __name__ == "__main__":
    unittest.main()
