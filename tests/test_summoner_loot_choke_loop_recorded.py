"""Recorded regression for a detected summoner choke hold losing to loot."""

import tests  # noqa: F401
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import parse_snapshot
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

    def test_recorded_choke_hold_blocks_loot_and_expires_once(self):
        recorded_loot = self.by_reason["seek-loot"]
        recorded_prepare = self.by_reason["detected:prepare-choke"]
        loot_board = parse_snapshot(recorded_loot["board"], self.knowledge)
        prepare_board = parse_snapshot(recorded_prepare["board"], self.knowledge)
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
            key = policy.choose_key(loot_board)
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, "summoner:hold-choke"))

        still_held = replace(loot_board, turn=started + HOLD_TURNS)
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(still_held)
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, "summoner:hold-choke"))

        released = replace(loot_board, turn=started + HOLD_TURNS + 1)
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(released)
        self.assertEqual((key, policy.last_reason), ("6", "seek-loot"))

        # The same unseen detection cannot start a fresh hold on the next
        # preparation board after the 50-turn episode has expired.
        after_release = replace(prepare_board, turn=started + HOLD_TURNS + 11)
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(after_release)
        self.assertEqual(policy.last_reason, "seek-loot")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(policy._detected_threat_hold[1], started)


if __name__ == "__main__":
    unittest.main()
