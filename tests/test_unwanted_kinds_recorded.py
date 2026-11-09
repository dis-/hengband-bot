"""Unwanted kinds are destroyed, never kept (owner 2026-11-02, cheap-books-1102).

Owner: 「1冊目、2冊目の安い本で枠を埋めるのをやめたい。拾ったら捨てて。」 and
「像、人形、モンスターボールも不要物に追加。」

Recorded input ``cheap-books-20261102.jsonl.gz`` (tests/extract_cheap_books_1102_fixture.py):
line 0 the viewing Magic-Eater n1-c life-072's first town board after a Recall
(turn 1657801), its pack holding slot a ヘックスの魔法書 x2 (107/0), b 武芸の書
(106/0) and c 暗黒の魔法書 (94/0); line 1 a recorded n1-c character response
whose sheet lists no realm (a Magic-Eater has none).  The recorded bot spent
this board on ``me-staff:read-powers`` and carried the three books on.

DECLARED CONSTRUCTED (named again where built): a character response listing
the Hex realm (id 18) in place of the recorded empty list, and a capture ball
(tval 11 sval 0) in place of the recorded slot c book.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures" / "cheap-books-20261102.jsonl.gz"


class UnwantedKindsRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.board_line, cls.character_line = stream.read().rstrip("\n").split("\n")
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _consume(self, policy, line):
        return _consume_response_sequence(
            [line], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl")[1]

    def _arrival(self, character_line=None):
        policy = _policy(self.directory, self.monrace)
        if character_line is not None:
            self._consume(policy, character_line)
        board = self._consume(policy, self.board_line)[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return policy, board

    def test_recorded_magic_eater_destroys_its_first_book(self):
        policy, board = self._arrival(self.character_line)
        self.assertTrue(board.in_town)
        self.assertEqual([(item.tval, item.sval) for item in board.inventory[:3]],
                         [(107, 0), (106, 0), (94, 0)])
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")
        self.assertTrue(key.endswith("ka"), key)

    def test_control_own_realm_book_stays(self):
        # DECLARED CONSTRUCTED: the recorded character response with the Hex
        # realm (id 18) listed; the Hex book (slot a) stays, b goes.
        character = json.loads(self.character_line)
        character["character"]["realms"] = [{"id": 18, "name": "Hex"}]
        policy, board = self._arrival(json.dumps(character, ensure_ascii=False))
        self.assertIsNone(policy._junk_class(board, board.inventory[0]))
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")
        self.assertTrue(key.endswith("kb"), key)

    def test_capture_ball_goes_while_the_realms_are_unobserved(self):
        # No character response yet: no book is unwanted, a capture ball is.
        policy, board = self._arrival()
        self.assertIsNone(policy._junk_class(board, board.inventory[0]))
        # DECLARED CONSTRUCTED: a capture ball in place of the slot c book.
        ball = InventoryItem("c", "モンスター・ボール", 1, 11, 0, True, True)
        board = replace(board, inventory=type(board.inventory)(
            ball if item.slot == "c" else item for item in board.inventory))
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")
        self.assertTrue(key.endswith("kc"), key)


if __name__ == "__main__":
    unittest.main()
