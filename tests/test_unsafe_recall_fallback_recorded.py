"""Recorded pins: the unsafe-recall fallback is bounded by the refused depth.

Live incident 2026-09-23 18:23:29-18:23:54 (protocol 3).  A bot process started
on the parked town game and stopped 25 seconds later, after 16 decisions, on
``town:blocked:owner-retired``.  Its four preceding decisions are
``town:blocked:depth-gate:destination-50:missing-destruction``: the objective
was Angband, whose recall arrival depth is 50, and the character (CL33) carries
no Scroll of *Destruction* and no Staff of Destruction, so
``_recall_destination_safe(snapshot, DUNGEON_ANGBAND)`` is false.  Nothing in
town could change that -- the recorded ``procurement_requirements`` is empty and
the character holds 16,288 gold -- so the town-plan owner burnt its budget and
retired.  The 18:22 capture of the previous process ends on the same two
reasons, which is why the restart reproduced the stop in 25 seconds.

Root cause: ``_activate_safe_recall_fallback`` bounded its alternates by
``snapshot.recall_depth``.  That is the destination the Word of Recall
currently points at, not the destination the caller refused.  On the recorded
board the scroll still pointed at the Yeek cave (depth 13) while the refused
destination was Angband's 50, so the fallback demanded a landing depth below 12
and rejected every dungeon the character had entered -- Orc cave 23, Forest 21,
Castle 22, Mountain 25 -- although the character is missing no required ability
at any of them.  The bound is now the refused arrival depth, which the caller
already computes for its own gate message.

Substrate: the last six emitter rows of the retained snapshot ring, whose final
row carries the stop's turn (tests/extract_unsafe_recall_fallback_fixture.py).
The process decided only 16 times and the ring also covers the previous
process, so no whole-lifetime replay exists; the boards are observed through
the public response path on a fresh policy and the producer under test is run
on the final board, in the manner of test_entrance_travel_retired_recorded.
Walls, each declared:
- the policy is fresh, not the live process's policy (unavailable).  Home
  history/disposal files live in a temporary directory;
- DECLARED WALL: the objective is Angband.  The recorded reason names
  ``destination-50``, which only the Angband branch of
  ``_town_departure_key`` can produce, and the recorded
  ``dungeon_recall_depths`` gives Angband depth 50; a fresh policy has not yet
  selected that objective, so the tests set ``_target_dungeon_id``;
- DECLARED WALL: the protocol-3 ~f skill values are the live ones (4000
  two-weapon, 4002 shield, read at CL33 on the recorded 18:23 board).  A fresh
  policy would spend its first decision requesting them; the live process had
  already read them.  No pin below depends on either value.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import DUNGEON_ANGBAND
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import (
    DESTRUCTION_GATE_LABEL,
    DESTRUCTION_USE_IMPLEMENTED,
    WAIT_KEY,
    required_depth_gates,
)

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "unsafe-recall-fallback-20260923.jsonl.gz"
FIXTURE_SHA256 = (
    "8f14b68d77f33107d4be043803c0b27dd9f21d5de14dab83f9a5706c9d85674f"
)
BOUNDARIES_SHA256 = (
    "81a47ba8b28ceb3fd3ed05695db7cb82dc423b9bba88e89167bbbece59da8901"
)
# The live ~f values (see the module wall).
SKILL_EXP = (4000, 4002)
ANGBAND_ARRIVAL_DEPTH = 50
FALLBACK_REASON = "town:unsafe-recall-fallback"
RECORDED_GATE_REASON = (
    "town:blocked:depth-gate:destination-50:missing-destruction"
)


class UnsafeRecallFallbackRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        cls.boundaries = json.loads(
            boundaries_path.read_text(encoding="utf-8")
        )
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == cls.boundaries["input_rows"]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.policy = _policy(self.directory, self.monrace)
        _decoded, snapshots = _consume_response_sequence(
            self.lines, self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.board = snapshots[-1]
        # DECLARED WALLS (see the module docstring).
        self.policy._target_dungeon_id = DUNGEON_ANGBAND
        self.policy._skill_exp_cache = (
            *SKILL_EXP,
            self.board.player.level,
            self.policy._town_visit_epoch,
        )

    def _independent(self):
        """Deep copy whose cached NeedSpec closures are rebuilt on the copy."""
        clone = copy.deepcopy(self.policy)
        clone._town_need_specs = None
        return clone

    def test_f0_recorded_board_reproduces_the_refused_destination(self):
        board = self.board
        self.assertEqual(board.turn, self.boundaries["stop_turn"])
        self.assertEqual(
            [board.player.position.y, board.player.position.x],
            [
                self.boundaries["stop_position"]["y"],
                self.boundaries["stop_position"]["x"],
            ],
        )
        self.assertEqual(
            self.boundaries["recorded"][-2][1], RECORDED_GATE_REASON
        )
        self.assertEqual(
            self.boundaries["recorded"][-1][1], "town:blocked:owner-retired"
        )
        # Nothing in town could satisfy the gate: no requirement, plenty of gold.
        self.assertEqual(self.boundaries["recorded_procurement"], [])
        self.assertGreater(board.player.gold, 10000)

        self.assertTrue(board.angband_recall_unlocked)
        self.assertEqual(
            self.policy._dungeon_entry_depth(
                board, DUNGEON_ANGBAND, via_recall=True
            ),
            ANGBAND_ARRIVAL_DEPTH,
        )
        self.assertIn(
            DESTRUCTION_GATE_LABEL, required_depth_gates(ANGBAND_ARRIVAL_DEPTH)
        )
        self.assertFalse(self.policy._has_destruction_method(board))
        self.assertEqual(
            sorted(
                self.policy._missing_required_abilities(
                    board, ANGBAND_ARRIVAL_DEPTH
                )
            ),
            [DESTRUCTION_GATE_LABEL],
        )
        self.assertFalse(
            self.policy._recall_destination_safe(board, DUNGEON_ANGBAND)
        )
        # The refused destination is not the destination the scroll points at.
        self.assertEqual(board.recall_depth, 13)

    def test_f1_the_refused_depth_bounds_the_fallback(self):
        policy = self._independent()
        board = self.board

        # REVERT-PROOF: the recorded board's own recall depth (13) bounds the
        # alternates at 12 and rejects every dungeon the character entered.
        self.assertIsNone(
            policy._pick_alternate_dungeon(
                board, max_entry_depth=max(1, board.recall_depth - 1)
            )
        )
        alternate = policy._activate_safe_recall_fallback(
            board, ANGBAND_ARRIVAL_DEPTH
        )
        self.assertIsNotNone(alternate)
        self.assertNotEqual(alternate, DUNGEON_ANGBAND)
        landing = board.dungeon_recall_depths[alternate]
        self.assertLess(landing, ANGBAND_ARRIVAL_DEPTH)
        self.assertEqual(
            sorted(policy._missing_required_abilities(board, landing)), []
        )
        self.assertEqual(policy._target_dungeon_id, alternate)

    def test_f2_the_town_terminal_takes_the_fallback_instead_of_blocking(self):
        policy = self._independent()

        key = policy._town_special_key(self.board)

        # Live: no key here, then the depth-gate block and owner-retired stop.
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, FALLBACK_REASON))
        self.assertIsNone(policy._town_blocked_reason)
        self.assertNotEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertEqual(
            policy._alternate_dungeon, policy._target_dungeon_id
        )

    def test_f3_gate_and_fallback_still_refuse_when_nothing_is_safe(self):
        policy = self._independent()
        # The same board with no entered dungeon other than the refused one.
        alone = replace(self.board, entered_dungeon_ids=frozenset({DUNGEON_ANGBAND}))

        self.assertIsNone(
            policy._activate_safe_recall_fallback(alone, ANGBAND_ARRIVAL_DEPTH)
        )
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        # The depth gate itself is unchanged: depth 50 is still refused, with
        # the recorded reason.
        self.assertFalse(
            policy._destination_depth_allowed(alone, ANGBAND_ARRIVAL_DEPTH)
        )
        self.assertEqual(
            f"town:blocked:{policy.last_reason}", RECORDED_GATE_REASON
        )

    def test_f4_a_safe_destination_is_not_diverted(self):
        """CHANGED 2026-09-23 by user decision
        「*破壊*を使用するロジックを実装するまでは実際に50F以降に潜ることを
        禁止する」: while ``DESTRUCTION_USE_IMPLEMENTED`` is False, 50F+ is
        refused outright, so even a character whose ability set carries the
        gate label is diverted.  The undiverted behaviour this pin asserted is
        the behaviour the flag restores, and it is asserted below under the
        flipped flag -- the fallback itself is unchanged.
        """
        policy = self._independent()
        # The same board with the *Destruction* gate satisfied by the character.
        safe = replace(
            self.board,
            player=replace(
                self.board.player,
                abilities=frozenset(
                    {*self.board.player.abilities, DESTRUCTION_GATE_LABEL}
                ),
            ),
        )

        self.assertFalse(DESTRUCTION_USE_IMPLEMENTED)
        self.assertFalse(policy._recall_destination_safe(safe, DUNGEON_ANGBAND))
        self.assertEqual(policy._town_special_key(safe), WAIT_KEY)
        self.assertEqual(policy.last_reason, FALLBACK_REASON)
        self.assertNotEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)

        restored = self._independent()
        with patch(
            "hengbot.policy_constants.DESTRUCTION_USE_IMPLEMENTED", True
        ):
            self.assertTrue(
                restored._recall_destination_safe(safe, DUNGEON_ANGBAND)
            )
            self.assertIsNone(restored._town_special_key(safe))
            self.assertEqual(restored._target_dungeon_id, DUNGEON_ANGBAND)
            self.assertIsNone(restored._alternate_dungeon)


if __name__ == "__main__":
    unittest.main()
