"""Recorded pins: the emergency-return flag stops loot only while the return progresses.

USER DECISION 2026-10-02 19:0x 「帰還が進んでいる間だけ止める」: 拾いを止める
のは、帰還の巻物を読んで帰還を待っている間や出口へ向かっている間だけ。帰還も
階段も使えない階では旗が立っていても拾う。

Live 2026-10-02 18:26-18:28 (session 35788), Angband 24F, random quest 41
(TAKEN, exit locked): decision 6521 posted ``emergency:teleport`` and set
``_emergency_return_active``; the floor never changed, so the flag stayed up
and ``_normal_loot_key#2`` was never asked again (ownership-claims decision
6524: the suspended floor-loot claim closed ``loot-suppressed:emergency-return``;
588 decisions, 195 with visible loot, 0 ``seek-loot``).

Substrate: capture ``autorecover-20261002-182813-exit-no-marker`` (the same
process), whose ring keeps the boards of decisions 6995-7108.  A fresh policy
is fed 6995 (warm-up; the fresh process's restart prime answers
``trigger-autodestroy`` with the live key '7').  DECLARED WALL: after 6995 the
flag is raised as the live process carried it since 6521 (no floor change in
between).  Before the fix the replay reproduces every live (key, reason) of
6996-6998 -- ``explore`` while loot is visible and no hostile is in view (probe
printed with the fix reverted, 2026-10-02 round report).  With
the fix 6996 picks the loot up; it is the first divergence (R4), so nothing is
asserted past it.
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
FIXTURE = FIXTURES / "loot-suppression-quest-floor-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "loot-suppression-quest-floor-20261002.boundaries.json"
CASTLE_FIXTURE = FIXTURES / "castle-top-floor-exit-20261002.jsonl.gz"
CALIBRATION = FIXTURES / "wild-ambush-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "74148cc1085cf01a4c05617ea19eda7cbd49808038e6b4c6c7927b4ead3639d0",
    BOUNDARIES: "18c6291f0be195d5f68d7180d19605e5b809a49ca89dc44545b9531a516d1556",
    CASTLE_FIXTURE: "a6469df8e139299e623602f9f389e4bbfe7458ffca5f1f7b7edf32c3637b6873",
    CALIBRATION: "a71a507ffe45da1e8ca3c32a59886b3be1c88c6f68b4c6f5d691ab51e0fb6ce5",
}
QUEST_FLOOR = (1, 24, 41)
WARM_UP = 6995
PINNED = 6996
LIVE_EXPLORE = (6996, 6997, 6998)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _load():
    for path, digest in SHA256.items():
        assert _sha(path) == digest, path
    boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    fields = boundaries["recorded_fields"]
    recorded = {
        row[0]: dict(zip(fields, row)) for row in boundaries["recorded"]
    }
    ends = {int(k): v for k, v in boundaries["board_end"].items()}
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        lines = [json.loads(line)["line"] for line in stream]
    return recorded, ends, lines


class LootSuppressionReturningRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.recorded, cls.ends, cls.lines = _load()
        with gzip.open(CASTLE_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.knowledge = json.loads(stream.readline())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        self.policy._crossarea_fundraising_enforced = True  # live argv
        self.policy.consume_skill_knowledge(self.knowledge)  # declared wall
        self._fed = -1

    def _board(self, sequence):
        end = self.ends[sequence]
        rows = self.lines[self._fed + 1: end + 1]
        self._fed = end
        _decoded, snapshots = _consume_response_sequence(
            rows, self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        return snapshots[-1]

    def _decide(self, sequence):
        board = self._board(sequence)
        key = self.policy.choose_key(board)
        self.policy.confirm_key_posted(key)
        return board, (str(key), self.policy.last_reason)

    def _warm_up_with_live_flag(self):
        _board, row = self._decide(WARM_UP)
        self.assertEqual(row[0], self.recorded[WARM_UP]["key"])
        # DECLARED WALL: the live process raised the flag at 6521
        # (emergency:teleport) on this same floor and carried it here.
        self.policy._emergency_return_active = True

    def _live(self, sequence):
        row = self.recorded[sequence]
        return (row["key"], row["reason"])

    def test_recorded_rows_are_the_incident(self):
        for sequence in LIVE_EXPLORE:
            self.assertEqual(self._live(sequence)[1], "explore")
            self.assertEqual(self.recorded[sequence]["visible_hostiles"], 0)
        self.assertEqual(
            self.recorded[PINNED]["visible_loot"], [[14, 45], [15, 44]]
        )
        self.assertNotIn(
            "seek-loot", {row["reason"] for row in self.recorded.values()}
        )

    def test_locked_quest_floor_picks_up_visible_loot_despite_the_flag(self):
        self._warm_up_with_live_flag()
        board, row = self._decide(PINNED)
        self.assertEqual(board.floor_key, QUEST_FLOOR)
        self.assertTrue(self.policy._quest_floor_exit_locked(board))
        self.assertTrue(self.policy._emergency_return_active)
        self.assertFalse(board.player.recalling)
        self.assertFalse(self.policy._returning_to_town)
        # First divergence (R4): live explored away from the visible loot.
        self.assertEqual(self._live(PINNED), ("7", "explore"))
        self.assertEqual(row, ("3", "seek-loot"))

    def test_recall_under_way_still_suppresses_normal_loot(self):
        self._warm_up_with_live_flag()
        board = self._board(PINNED)
        # DECLARED WALL: a Word of Recall read on this floor whose activation
        # is being confirmed -- exactly the watch _read_dungeon_recall_scroll_key
        # records on this board.
        self.policy._dungeon_recall_issue_watch = (
            board.floor_key,
            board.turn,
            sum(item.count for item in board.inventory if item.is_recall_scroll),
        )
        self.assertTrue(self.policy._emergency_return_progressing(board))
        key = self.policy.choose_key(board)
        self.assertEqual((str(key), self.policy.last_reason), self._live(PINNED))


if __name__ == "__main__":
    unittest.main()
