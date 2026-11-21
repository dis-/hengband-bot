"""A worn NO_AC piece on a dungeon floor: Recall at once, teleport from melee until it fires.

Owner 2026-11-21 (verbatim, LOCKED): 「AC0では打撃を受けると即死抽選がある。優先対処。」 and
「着たまま帰還を読み、打撃の届く敵を寄せない」 (no_ac_recall).  n1-b life-411 resumed at 12:02 on
Angband 95F wearing 宵闇のローブ (AC 0) and fought on.

Recorded: n1-b's town arrival of 11:26:08 (tests/fixtures/n1b-411-twilight-robe-1121, its first
three decisions: the skill list and the Home read) for the policy, and two of its 95F boards of
12:02 (tests/fixtures/n1b-411-twilight-robe-95f-1121): the first (no melee hostile within reach)
and the third (one within a turn's reach).

DECLARED CONSTRUCTED: the closing board with the Word of Recall counting down.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import no_ac_recall
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")


class N1b411TwilightRobe95fRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURES / "n1b-411-twilight-robe-1121",
                                            Path(self.scratch.name))
        for recorded, supply in steps[:3]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                self.policy.choose_key(board)
            self.policy.confirm_key_posted(recorded["key"])
        raw = json.loads(lzma.decompress(
            (FIXTURES / "n1b-411-twilight-robe-95f-1121" / "boards.json.xz").read_bytes()))
        self.boards = {name: parse_snapshot(board, self.policy._monrace_knowledge)
                       for name, board in raw.items()}

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def test_recall_at_once(self):
        board = self.boards["quiet"]
        self.assertTrue(no_ac_recall.worn(board))
        self.assertEqual(board.dungeon_level, 95)
        self.assertFalse(board.player.recalling)
        key = no_ac_recall.key(self.policy, board)
        self.assertEqual(self.policy.last_reason, no_ac_recall.RECALL_REASON)
        self.assertTrue(key.startswith("r"), key)
        self.assertTrue(self.policy._returning_to_town)

    def test_teleport_from_melee_until_the_recall_fires(self):
        board = self.boards["closing"]
        self.assertTrue(no_ac_recall._closing_melee(self.policy, board))
        recalling = replace(board, player=replace(board.player, recalling=True))
        policy = self.policy
        for _ in range(6):  # the periodic power lists first
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(recalling)
            if not policy.last_reason.startswith("periodic"):
                break
            policy.confirm_key_posted(key)
        self.assertEqual(policy.last_reason, no_ac_recall.TELEPORT_REASON)
        self.assertTrue(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
