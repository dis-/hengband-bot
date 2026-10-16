"""Replay the C4-A breeder refill board through the production policy.

The JSONL board is captured evidence. Policy-only latch/emergency-return
fields are absent from the capture and are DECLARED CONSTRUCTED in the replay
setup below. The emergency flag reproduces the recorded clear-path decision on
the pre-fix branch; the breeder latch is the recorded active floor intent.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "breeder-refill-20261016.jsonl.gz"
BOUNDARIES = FIXTURES / "breeder-refill-20261016.boundaries.json"


class BreederRefillEscapeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.board_line = stream.readline()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._crossarea_fundraising_enforced = True
        # DECLARED CONSTRUCTED: the capture starts on a live process board;
        # its startup ~f skill-exp exchange is outside this one-row fixture.
        # These unused single-weapon skill values satisfy that protocol gate.
        self.policy._skill_exp_cache = (0, 0, 19, None)
        _decoded, snapshots = _consume_response_sequence(
            [self.board_line], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        self.board = snapshots[-1]
        # DECLARED CONSTRUCTED: policy checkpoints were not part of the
        # capture. Restore the active latch, existing return intent and the
        # sole inferred stale gate.
        self.policy._breeder_breakthrough_floor = self.board.floor_key
        self.policy._emergency_return_active = True
        self.policy._returning_to_town = True

    def test_recorded_refill_board_exits_by_recall(self):
        recorded = self.boundaries
        self.assertEqual(
            (recorded["recorded_key"], recorded["recorded_reason"]),
            ("9", "breeder-breakthrough:clear-escape-path"),
        )
        self.assertEqual(self.board.turn, recorded["turn"])
        self.assertEqual(self.board.floor_key, tuple(recorded["floor"]))
        self.assertEqual(
            (self.board.player.position.y, self.board.player.position.x),
            tuple(recorded["position"]),
        )
        self.assertIsNone(self.policy._fundraising_mode)
        self.assertIsNone(self.policy._active_quest_id(self.board))
        self.assertFalse(self.board.player.blind)
        self.assertFalse(self.board.player.confused)
        self.assertEqual(self.policy._find_recall_scroll(self.board).count, 9)
        self.assertTrue(self.policy._can_read_scrolls(self.board))
        self.assertIsNone(self.policy._dungeon_recall_confirmation_key(self.board))

        key = self.policy._breeder_breakthrough_key(
            self.board, self.policy._strategic_hostiles(self.board)
        )

        self.assertEqual(key, "rf")
        self.assertEqual(self.policy.last_reason, "breeder-breakthrough:recall")

    def test_active_quest_floor_keeps_recall_suppressed(self):
        with patch.object(self.policy, "_active_quest_id", return_value=41):
            key = self.policy._breeder_breakthrough_key(
                self.board, self.policy._strategic_hostiles(self.board)
            )
        self.assertEqual(key, "9")
        self.assertEqual(
            self.policy.last_reason, "breeder-breakthrough:clear-escape-path"
        )
        self.assertNotEqual(self.policy.last_reason, "breeder-breakthrough:recall")

    def test_fundraising_mine_keeps_recall_suppressed(self):
        self.policy._fundraising_mode = "mine"
        key = self.policy._breeder_breakthrough_key(
            self.board, self.policy._strategic_hostiles(self.board)
        )
        self.assertNotEqual(key, "rf")
        self.assertNotEqual(self.policy.last_reason, "breeder-breakthrough:recall")

    def test_without_the_latch_ordinary_combat_keeps_fighting(self):
        self.policy._breeder_breakthrough_floor = None
        key = self.policy.choose_key(self.board)
        self.assertEqual(key, "6")
        self.assertEqual(self.policy.last_reason, "melee")


if __name__ == "__main__":
    unittest.main()
