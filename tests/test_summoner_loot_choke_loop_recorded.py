"""Recorded regression for a detected summoner choke hold losing to loot.

Owner 2026-11-10 (穴熊, docs/anaguma-design.md section 9): against the existing choke wait
「掘れるなら掘る」.  The recorded board carries a Stone to Mud wand, so the pocket is dug before
the hold (``test_recorded_board_digs_a_pocket_first``); the hold-and-expiry pin is the board
without the wand (DECLARED CONSTRUCTED: the wand removed), where no pocket can be dug.
"""

import tests  # noqa: F401
from recorded_junk_scope import choose_past_junk_key
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import anaguma
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, WAIT_KEY


FIXTURE = Path(__file__).parent / "fixtures" / "summoner-loot-choke-loop-20261008.jsonl.gz"
FIXTURE_SHA256 = "c77928d5bf41078e79e8b16a3384005f62304ed9d4ea543fc7166c8642ad81fb"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
HOLD_TURNS = 50 * 10


class SummonerLootChokeLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.records = [json.loads(line) for line in stream]
        cls.by_reason = {record["decision"]["reason"]: record for record in cls.records}
        cls.knowledge = load_monrace_knowledge(MONRACES)

    @staticmethod
    def without_stone_to_mud(board):
        """DECLARED CONSTRUCTED: the board without its Stone to Mud wand (no pocket to dig)."""
        return replace(board, inventory=[item for item in board.inventory
                                         if not (item.tval == TVAL_WAND
                                                 and item.sval == SV_WAND_STONE_TO_MUD)])

    def test_recorded_board_digs_a_pocket_first(self):
        loot_board = parse_snapshot(self.by_reason["seek-loot"]["board"], self.knowledge)
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy.prime(loot_board)
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            choose_past_junk_key(policy, loot_board)
        self.assertEqual(policy.last_reason, anaguma.REASON_DIG)
        self.assertIsNotNone(anaguma.plan(policy))

    def test_recorded_choke_hold_blocks_loot_and_expires_once(self):
        recorded_loot = self.by_reason["seek-loot"]
        recorded_prepare = self.by_reason["detected:prepare-choke"]
        loot_board = self.without_stone_to_mud(parse_snapshot(recorded_loot["board"], self.knowledge))
        prepare_board = self.without_stone_to_mud(
            parse_snapshot(recorded_prepare["board"], self.knowledge))
        self.assertEqual(
            (loot_board.player.position.y, loot_board.player.position.x), (38, 70)
        )
        self.assertEqual(
            (prepare_board.player.position.y, prepare_board.player.position.x),
            (38, 71),
        )
        self.assertEqual(recorded_loot["decision"]["key"], "6")

        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy.prime(loot_board)
        started = self.records[0]["decision"]["turn"]
        policy._detected_threat_hold = (loot_board.floor_key, started)
        policy._detected_threat_hold_position = loot_board.player.position

        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = choose_past_junk_key(policy, loot_board)
        # The detected pack holds no summoner: the hold is named for it
        # (summoner-avoid-narrow-1102; recorded as summoner:hold-choke).
        self.assertEqual(self.records[0]["decision"]["reason"], "summoner:hold-choke")
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, "detected:hold-choke"))

        still_held = replace(loot_board, turn=started + HOLD_TURNS)
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = choose_past_junk_key(policy, still_held)
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, "detected:hold-choke"))

        released = replace(loot_board, turn=started + HOLD_TURNS + 1)
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = choose_past_junk_key(policy, released)
        self.assertEqual((key, policy.last_reason), ("6", "seek-loot"))

        # The same unseen detection cannot start a fresh hold on the next
        # preparation board after the 50-turn episode has expired.
        after_release = replace(prepare_board, turn=started + HOLD_TURNS + 11)
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = choose_past_junk_key(policy, after_release)
        self.assertEqual(policy.last_reason, "seek-loot")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(policy._detected_threat_hold[1], started)


if __name__ == "__main__":
    unittest.main()
