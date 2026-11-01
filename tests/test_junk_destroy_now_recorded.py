"""Carried junk is destroyed on the first safe dungeon decision (junk-destroy-now-1102).

Owner 2026-11-02: 「本を拾ったら安全な時に壊す。後回しにする理由はない。」 and
「他のゴミも同様である」.

Recorded input ``junk-destroy-now-20261102.jsonl.gz``
(tests/extract_junk_destroy_now_1102_fixture.py), the viewing Magic-Eater n1-c
life-093 (no realm):
line 0 Yeek Cave 13F, turn 1561402, no visible monster: the board right after
it picked up 武芸の書 (106/0, slot a; slot b 97/0 already carried); the
recorded bot walked on with both books.
line 1 Angband 13F, turn 1582337, no visible monster: the board right after
it identified the just-picked-up hard leather cap (slot l, 32/2) as cursed.
line 2 the life's character response (realms ``[]``).
line 3 a recorded n1-c life-100 board with one visible cave orc.

DECLARED CONSTRUCTED (named again where built): the life-100 cave orc placed
three cells from the player on the line 0 board.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.junk_destroy_now import destroy_now_key
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures" / "junk-destroy-now-20261102.jsonl.gz"
DESTROY = "inventory:destroy-worthless-junk"


class JunkDestroyNowRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            (cls.book_line, cls.cursed_line, cls.character_line,
             cls.monster_line) = stream.read().rstrip("\n").split("\n")
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _board(self, board_line, character_line=None):
        policy = _policy(self.directory, self.monrace)
        lines = [character_line] if character_line is not None else []
        board = _consume_response_sequence(
            [*lines, board_line], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl")[1][-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return policy, board

    def test_picked_up_book_is_destroyed_on_the_next_safe_decision(self):
        policy, board = self._board(self.book_line, self.character_line)
        self.assertFalse(board.in_town)
        self.assertEqual((board.inventory[0].tval, board.inventory[0].sval), (106, 0))
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, DESTROY)
        self.assertTrue(key.endswith("ka"), key)

    def test_identified_cursed_cap_is_destroyed_on_the_next_safe_decision(self):
        # Without the character response no book is junk; the cursed cap is.
        policy, board = self._board(self.cursed_line)
        cap = next(item for item in board.inventory if item.slot == "l")
        self.assertEqual(policy._junk_class(board, cap), "cursed")
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, DESTROY)
        self.assertTrue(key.endswith("kl"), key)

    def test_control_visible_hostile_keeps_the_book(self):
        # DECLARED CONSTRUCTED: the life-100 cave orc three cells west of the
        # player on the line 0 board.
        board = json.loads(self.book_line)
        orc = json.loads(self.monster_line)["visible_monsters"][0]
        orc.update(x=board["player"]["x"] - 3, y=board["player"]["y"])
        board["visible_monsters"] = [orc]
        policy, snapshot = self._board(json.dumps(board, ensure_ascii=False),
                                       self.character_line)
        self.assertIsNone(destroy_now_key(policy, snapshot))
        policy.choose_key(snapshot)
        self.assertNotEqual(policy.last_reason, DESTROY)


if __name__ == "__main__":
    unittest.main()
