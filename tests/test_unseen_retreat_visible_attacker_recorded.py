"""Recorded pins: walking away while a visible monster claws (Forest 32F, 2026-10-03).

User (2026-10-03 03:4x, verbatim): 「いまモンスターに殴られながらただ歩行する
行動が観測された。これが優先対処」

Source: the live ``jsonlog/bot-state-fixed.jsonl`` / ``bot-decisions.jsonl``
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
FIXTURE = FIXTURES / "unseen-retreat-visible-20261003.jsonl.gz"
RECORDED = FIXTURES / "unseen-retreat-visible-20261003.recorded.json"
CALIBRATION = FIXTURES / "unseen-retreat-visible-20261003.character-calibration.json"
# R9: digests of the bytes with CRLF normalized to LF.
SHA256 = {
    FIXTURE: "22c63672d956347a29d704f7f37c933d4fcf3a419e1285a6b61a45f04d725d37",
    RECORDED: "3a40ca00f865bf2984e105d9cfefedacb9ce5363b72a240f774fc622d036b4ad",
    CALIBRATION: "071816f863bea7c7c6286299e32a674e016d7ea43cfdba2345277f0958712614",
}

A_WARMUP = 532
A_DIVERGENCE = 545
B_START = 588
B_DIVERGENCE = 594


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class _Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        cls.knowledge = json.loads(records[0]["line"])
        cls.boards = {
            record["sequence"]: record["line"]
            for record in records[1:]
        }
        rows = json.loads(RECORDED.read_text(encoding="utf-8"))["recorded"]
        cls.recorded = {row[0]: row for row in rows}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        self.policy._crossarea_fundraising_enforced = True  # live argv
        self.policy.consume_skill_knowledge(self.knowledge)

    def _replay(self, first, last):
        rows, board = {}, None
        for sequence in range(first, last + 1):
            _decoded, snapshots = _consume_response_sequence(
                [self.boards[sequence]], self.policy, lambda _key: True,
                self.monrace,
                knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
            )
            board = snapshots[-1]
            key = self.policy.choose_key(board)
            rows[sequence] = (str(key), self.policy.last_reason)
            self.policy.confirm_key_posted(key)
        return rows, board

    def _live(self, sequence):
        row = self.recorded[sequence]
        return (row[2], row[3])


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
