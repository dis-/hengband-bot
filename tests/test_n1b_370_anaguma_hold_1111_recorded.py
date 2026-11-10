"""n1-b life-370 2026-11-11 05:42 stall:floor-dwell:anaguma:hold (Orc cave 23F, build bot-0850e2334).

Recorded: tests/fixtures/n1b-370-anaguma-hold-1111.json.xz
(tests/extract_n1b_370_anaguma_hold_1111_fixture.py).

Stone trolls (race 297, FRIENDS, not ANIMAL, no PASS_WALL/KILL_WALL) were sensed around the
player, some of them awake.  Anaguma dug a pocket (05:38, (28,168)), held it 50 game turns,
detected, held 50 more with the trolls still sensed and not on the mouth, and released it
(``pack-stays-out``).  Fifty game turns later (``RETRY_GAME_TURNS``) the same pack got a new
pocket at (25,169) and the same wait began again, until the floor-dwell guard stopped the bot.
Owner 2026-11-10: 「50ゲームターン。待った後、可能なら感知を使って状況を把握する。」 -- the wait
ends; a pack that stayed out of it is not dug for again on the floor (anaguma ``_stayed_out``).

DECLARED RECONSTRUCTED: the policy is primed on the capture's first board (turn 5997122, the
second pocket being dug) and plans afresh; the capture keeps no skill reply (the skill cache as
tests.test_anaguma_recorded).  The live Magic-Eater dug with its absorbed Stone to Mud; the
test policy has not read the power list, so (as tests.test_anaguma_recorded ``with_wand``,
DECLARED CONSTRUCTED) an identified wand of 13 charges is carried.  DECLARED CONSTRUCTED (the
successor boards of the dig and the hold): tests.test_anaguma_recorded's -- each key's effect
applied to the board, the trolls held where the board shows them.
"""
import tests  # noqa: F401 -- isolate runtime files

import copy
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import anaguma
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests import test_anaguma_recorded as _anaguma_pins

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-anaguma-hold-1111.json.xz"
STONE_TROLL = 297


class StayedOutPackRecordedTest(unittest.TestCase):
    moved = staticmethod(_anaguma_pins.AnagumaRecordedTest.moved)
    opened = staticmethod(_anaguma_pins.AnagumaRecordedTest.opened)
    with_wand = staticmethod(_anaguma_pins.AnagumaRecordedTest.with_wand)
    apply = _anaguma_pins.AnagumaRecordedTest.apply
    dig_to_hold = _anaguma_pins.AnagumaRecordedTest.dig_to_hold
    decide = _anaguma_pins.AnagumaRecordedTest.decide

    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy = _policy(Path(directory.name), self.monrace)
        raw = self.with_wand(copy.deepcopy(self.case["boards"][0]))
        self.board = parse_snapshot(raw, self.monrace)
        self.policy.prime(self.board)
        self.policy._skill_exp_cache = (0, 0, self.board.player.level, self.policy._town_visit_epoch)

    def test_recorded_second_pocket_and_hold(self):
        reasons = [row["reason"] for row in self.case["decisions"]]
        self.assertIn("anaguma:dig:absorbed-power", reasons)
        self.assertEqual(reasons[-1], anaguma.REASON_HOLD)
        trolls = [m for m in (*self.board.visible_monsters, *self.board.detected_monsters)
                  if m.race_id == STONE_TROLL]
        self.assertGreaterEqual(len([m for m in trolls if not m.asleep]), 2)

    def test_a_pack_that_stayed_out_gets_no_second_pocket(self):
        self.decide(self.policy, self.board)
        plan = anaguma.plan(self.policy)
        self.assertIsNotNone(plan, getattr(self.policy, "_anaguma_veto", None))
        self.assertIn(STONE_TROLL, plan.races)
        held, _reasons, key = self.dig_to_hold(self.board)
        self.assertEqual((key, self.policy.last_reason), ("5", anaguma.REASON_HOLD))
        # 「50ゲームターン。待った後…」: the wait, the (absent) detection, the second wait.
        board = held
        for _ in range(3):
            board = replace(board, turn=board.turn + anaguma.WAIT_GAME_TURNS)
            self.decide(self.policy, board)
        self.assertIsNone(anaguma.plan(self.policy))
        self.assertEqual(self.policy._anaguma_last_release, "pack-stays-out")
        # Past the retry window the same pack, still sensed, gets no new pocket: the floor's
        # stayed-out reading answers first.  The board is the recorded one the plan was made on
        # (the player back there, the trolls as shown).  The constructed granite of the dig
        # closes that board's floor off in the policy's memory (the dirt around, terrain 88, is
        # not on the boards), so without the reading the board is refused as ``sealed``: the
        # reading, not a plan, is what this board can show.
        last = parse_snapshot(self.with_wand(copy.deepcopy(self.case["boards"][0])), self.monrace)
        turn = board.turn
        for _ in range(4):
            turn += anaguma.RETRY_GAME_TURNS
            self.decide(self.policy, replace(last, turn=turn))
            self.assertIsNone(anaguma.plan(self.policy), self.policy.last_reason)
            self.assertFalse(self.policy.last_reason.startswith("anaguma:"), self.policy.last_reason)
        self.assertEqual(self.policy._anaguma_veto, "stayed-out")

if __name__ == "__main__":
    unittest.main()
