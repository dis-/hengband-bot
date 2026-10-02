"""Recorded pins: death to an unseen caster amid a visible swarm (Forest, 2026-10-03 05:33).

User (2026-10-03, verbatim): 「修正し、同じ盤面で修正が確認できそうなら再開。
できなさそうなら新規キャラクターでクイックスタート。」

Source: C:/hengband-backups/state-logs/death-20261003-0533/
autorecover-20261003-053323-stuck-prompt-emergency-cure-critical
.{bot-state-fixed,bot-decisions}.jsonl.gz (bot commit 06087963).  The fixture
holds one state row per decision 3032-3047 (turns 06036357-06036488) and, as
row 0, the same character's skill_exp knowledge row (unseen-retreat-visible
-20261003, CL35, the closest one recorded; this capture has none).  The
calibration file is the live one (observed turn 6033321).

The killer, 闇の蜘蛛『シェロブ』, is never in the visible or detected
monsters.  With 12-32 visible hostiles the 3-turn projection (operational,
visible hostiles only) stayed 127-230 against HP 600-731 while the unseen
caster's 秘孔 / 「指さして恐ろしげに」 / 暗黒のブレス / クモの召喚 landed:

(A) 06036391: HP 730 -> 629 with 「何かがあなたを指さして恐ろしげに呪文を
    唱えた！」 and the bot meleed (weakest first) for five more boards.
    R4: a fresh process from 06036357 reproduces the recorded decisions up
    to the first divergence, which must be at or before 06036391 and be an
    emergency teleport read.  Every later board is counterfactual (the
    recorded game never teleported), so nothing later in that chain is
    asserted.
(B) 06036428: HP 600 -> 310 and blind (暗黒のブレス); the emergency cure was
    right, but the cured board 06036437 (HP 337, 21 visible) dropped the
    pending escape and meleed.  Single-board decision with the recorded
    policy state reconstructed by replay: a fresh process on 06036417 (warm
    up) and 06036428 reproduces the recorded keys, then 06036437 must read
    teleport.
(C) 06036459: HP 307 -> 295 with the unseen caster's 「指さして恐ろしげに」
    again among 28 visible hostiles.  Single-board decision: a fresh process
    on 06036445 (warm up, reproduces the recorded melee), then 06036459 must
    read teleport.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "lethal-unseen-caster-20261003.jsonl.gz"
RECORDED = FIXTURES / "lethal-unseen-caster-20261003.recorded.json"
CALIBRATION = FIXTURES / "lethal-unseen-caster-20261003.character-calibration.json"
# R9: digests of the bytes with CRLF normalized to LF.
SHA256 = {
    FIXTURE: "97d6ac6fe58fef4c80259a47da085a50939cecac48c4c32d88e240b43d46743f",
    RECORDED: "84807ee2e0f24f3b6db2e6fb719a281bf578f51bbc450821177a928580b42641",
    CALIBRATION: "89681faaab50a350d0994cd790788bb424bd4f8a12f1f7801767c327c7773f4c",
}

A_START = 6036357
A_LATEST_DIVERGENCE = 6036391
B_WARMUP = 6036417
B_CURE = 6036428
B_CURED = 6036437
C_WARMUP = 6036445
C_BOARD = 6036459
B_ONLY = 6036472
UNSEEN_CAST = "何かがあなたを指さして恐ろしげに呪文を唱えた！"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class _Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        assert records[0]["role"] == "knowledge"
        cls.knowledge = json.loads(records[0]["line"])
        cls.boards = {record["turn"]: record["line"] for record in records[1:]}
        cls.turns = sorted(cls.boards)
        rows = json.loads(RECORDED.read_text(encoding="utf-8"))["recorded"]
        cls.recorded = {row[1]: row for row in rows}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        self.policy.consume_skill_knowledge(self.knowledge)

    def _decide(self, turn, line=None):
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[turn] if line is None else line],
            self.policy, lambda _key: True,
            self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        board = snapshots[-1]
        key = self.policy.choose_key(board)
        reason = self.policy.last_reason
        self.policy.confirm_key_posted(key)
        return board, str(key), reason

    def _live(self, turn):
        row = self.recorded[turn]
        return (row[2], row[3])

    def _constructed(self, recorded_turn, **fields):
        """The recorded board line for ``recorded_turn`` with ``fields`` replaced."""
        board = json.loads(self.boards[recorded_turn])
        board.update(fields)
        return json.dumps(board, ensure_ascii=False)

    def _without_unseen_cast(self, turn):
        board = json.loads(self.boards[turn])
        messages = [m for m in board["messages"] if m != UNSEEN_CAST]
        self.assertEqual(len(messages), len(board["messages"]) - 1, turn)
        return self._constructed(turn, messages=messages)

    def assertTeleportRead(self, board, key, reason):
        scrolls = [item.slot for item in board.inventory if item.is_teleport_scroll]
        self.assertTrue(scrolls)
        self.assertEqual(key, "r" + scrolls[0])
        self.assertEqual(reason, "emergency:teleport")


class LethalUnseenCasterRecordedTest(_Replay):
    def test_recorded_rows_are_the_incident(self):
        self.assertEqual(self._live(A_START), ("rf", "emergency:teleport"))
        self.assertEqual(
            [self._live(turn)[1] for turn in self.turns if A_START < turn < B_CURE],
            ["melee"] * 8,
        )
        self.assertEqual(self.recorded[A_LATEST_DIVERGENCE][4], 629)
        self.assertIn(
            "何かがあなたを指さして恐ろしげに呪文を唱えた！",
            self.recorded[A_LATEST_DIVERGENCE][5],
        )
        self.assertEqual(self._live(B_CURE), ("qb", "emergency:cure-critical"))
        self.assertEqual(self.recorded[B_CURE][4], 310)
        self.assertEqual(self._live(B_CURED), ("3", "melee"))
        self.assertEqual(self.recorded[B_CURED][4], 337)
        self.assertEqual(self._live(C_BOARD), ("4", "melee"))

    def test_a_first_divergence_is_the_teleport_on_the_unseen_cast(self):
        for turn in self.turns:
            board, key, reason = self._decide(turn)
            if (key, reason) != self._live(turn):
                break
        else:
            self.fail("replay never diverged from the recorded melee")
        self.assertLessEqual(turn, A_LATEST_DIVERGENCE)
        self.assertEqual(turn, A_LATEST_DIVERGENCE)
        self.assertTeleportRead(board, key, reason)

    def test_b_cured_board_keeps_the_owed_escape(self):
        for turn in (B_WARMUP, B_CURE):
            _board, key, reason = self._decide(turn)
            self.assertEqual((key, reason), self._live(turn), turn)
        board, key, reason = self._decide(B_CURED)
        self.assertFalse(board.player.blind)
        self.assertGreater(len(board.visible_monsters), 20)
        self.assertTeleportRead(board, key, reason)

    def test_c_unseen_cast_among_visible_hostiles_escapes(self):
        _board, key, reason = self._decide(C_WARMUP)
        self.assertEqual((key, reason), self._live(C_WARMUP))
        board, key, reason = self._decide(C_BOARD)
        self.assertGreater(len(board.visible_monsters), 20)
        self.assertTeleportRead(board, key, reason)


class ObservedLossAndCarryGatesConstructedTest(_Replay):
    """Review pins (2026-10-03) for the observed-loss emergency and the carry.

    The death capture has no board where the observed one-move loss alone is
    lethal: both boards with loss x 3 >= HP (06036428, 06036472) also carry
    the unseen caster's line.  The carry pins need the cured board without
    hostiles and past its deadline, which the recording never shows.
    """

    def test_observed_loss_alone_escapes(self):
        # DECLARED CONSTRUCTED: on 06036459 and 06036472 only ``messages`` is
        # changed -- the unseen caster's 「指さして恐ろしげに」 line is
        # removed, so the unseen-caster emergency (A) cannot fire.  HP, the
        # 28-29 visible hostiles and every other field are recorded; the
        # observed loss on 06036472 (295 -> 182 = 113) comes from the real
        # observation pipeline over the recorded 06036459 HP.
        _board, key, reason = self._decide(C_WARMUP)
        self.assertEqual((key, reason), self._live(C_WARMUP))
        _board, key, reason = self._decide(
            C_BOARD, self._without_unseen_cast(C_BOARD)
        )
        # Without its unseen line the board decides as recorded.
        self.assertEqual((key, reason), self._live(C_BOARD))
        board, key, reason = self._decide(B_ONLY, self._without_unseen_cast(B_ONLY))
        hostiles = [monster for monster in board.visible_monsters if monster.hostile]
        self.assertGreater(len(hostiles), 20)
        self.assertFalse(any("何か" in message for message in board.messages))
        self.assertFalse(board.player.poisoned or board.player.cut)
        self.assertEqual(board.player.hp, 182)
        # The visible-hostile projection stays under HP; one move cost 113.
        self.assertLess(
            self.policy.threat_prediction(board, hostiles, 3)["operational_total"],
            board.player.hp,
        )
        self.assertTeleportRead(board, key, reason)

    def _cure_sets_the_carry(self):
        for turn in (B_WARMUP, B_CURE):
            _board, key, reason = self._decide(turn)
            self.assertEqual((key, reason), self._live(turn), turn)

    def test_carry_without_hostiles_in_view_does_not_teleport(self):
        self._cure_sets_the_carry()
        # DECLARED CONSTRUCTED: the recorded cured board 06036437 with
        # ``visible_monsters`` and ``detected_monsters`` emptied; HP 337, the
        # turn and the rest are recorded.
        board, key, reason = self._decide(
            B_CURED,
            self._constructed(B_CURED, visible_monsters=[], detected_monsters=[]),
        )
        self.assertFalse(board.player.blind)
        self.assertEqual(board.visible_monsters, [])
        self.assertNotEqual(reason, "emergency:teleport")
        self.assertFalse(key.startswith("r"), key)

    def test_expired_carry_does_not_teleport(self):
        self._cure_sets_the_carry()
        # DECLARED CONSTRUCTED: the recorded cured board 06036437 with only
        # ``turn`` moved past the cure's deadline.  The quaff at 06036428
        # (speed +0, 10 energy a game turn) is followed by the next player
        # board within ceil(250 / 10) = 25 game turns (06036453); 06036454
        # means another action came between the cure and this board.
        board, key, reason = self._decide(
            B_CURED, self._constructed(B_CURED, turn=B_CURE + 25 + 1)
        )
        self.assertFalse(board.player.blind)
        self.assertGreater(len(board.visible_monsters), 20)
        self.assertNotEqual(reason, "emergency:teleport")
        self.assertFalse(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
