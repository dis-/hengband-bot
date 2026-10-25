"""Replay the C4-A Q2 lantern run-out (issue #47, light and fuel ROOT-FIX).

Fixture rows (copied as-is, raw encoding) are state rows 0, 4, 5, 102, 103
and 104 of c4a-q2-dark-1025/20261025-143507-loop-detected (quest 2 The Sewer,
ONCE, floor (0, 15, 2)):

  0: turn 1551699 at (1,2), worn 真鍮のランタン 104 turns, radius 2.
  1: turn 1551734 at (1,4), 100 turns.
  2: turn 1551741 at (1,5), 99 turns (below the game's faint warning).
  3: turn 1552731 at (2,6), 0 turns, radius 0.
  4: turn 1552738 at (1,5), 0 turns, own grid dark.
  5: turn 1552748 at (1,4), 0 turns, on the quest's up staircase.

No row carries oil or a torch; 帰還の詔の巻物 is in slot f.  The recorded
decisions alternated quest-strategy:q2-residual-86-sweep '6' and
dark:backtrack '4' at radius 0 until the loop detector stopped the bot.

USER DECISION 2026-10-25「油を持って入り、微かなら帰る」: below the faint
value (100) with nothing to refill or wield, the one-shot quest lock is
released and the ordinary return leaves (the quest fails); a one-shot quest
is entered with OIL_TARGET flasks while a fuel light is worn.

DECLARED CONSTRUCTED: the ~f skill-exp cache; in the controls five flasks
of oil, a permanent light and full HP.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from unittest import mock
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import SV_LITE_FEANOR, SV_FLASK_OIL, TVAL_FLASK
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import OIL_TARGET
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "light-rootfix-q2-20261025.jsonl.gz"
SHA256 = "decf4c8e3a4cc74e6d421ba8aecf5bf89cbabc21182d3bdb22d8d3464a05f27d"
SWEEP = ("6", "quest-strategy:q2-post-blue-upper-left-puddle")
READ_RECALL_FROM_F = ("rf", "return:recall")


class LightRootFixQ2RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = gzip.decompress(data).decode("utf-8").splitlines()
        assert len(cls.lines) == 6
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._crossarea_fundraising_enforced = True

    def _board(self, index):
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[index]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        board = snapshots[-1]
        # DECLARED CONSTRUCTED: the ~f skill-exp cache.
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch
        )
        return board

    def _decide(self, board):
        return self.policy.choose_key(board), self.policy.last_reason

    @staticmethod
    def _with_oil(board):
        # DECLARED CONSTRUCTED: OIL_TARGET flasks of oil in a free pack slot.
        lamp = next(item for item in board.equipment if item.is_light)
        used = {item.slot for item in board.inventory}
        slot = next(letter for letter in "abcdefghijklmnopqrstuvw" if letter not in used)
        oil = replace(
            lamp, slot=slot, tval=TVAL_FLASK, sval=SV_FLASK_OIL,
            count=OIL_TARGET, fuel=7500, name="油つぼ",
        )
        return replace(
            board, inventory=type(board.inventory)((*board.inventory, oil))
        )

    def test_fixture_is_the_recorded_lantern_run_out(self):
        fuels = []
        for index in range(6):
            board = self._board(index)
            self.assertEqual(board.floor_key, (0, 15, 2))
            lamp = next(item for item in board.equipment if item.is_light)
            self.assertTrue(lamp.is_lantern)
            fuels.append(lamp.fuel)
            self.assertEqual(self.policy._count_oil(board), 0)
            self.assertEqual(self.policy._find_recall_scroll(board).slot, "f")
        self.assertEqual(fuels, [104, 100, 99, 0, 0, 0])

    def test_faint_board_releases_the_quest_lock_and_reads_recall(self):
        board = self._board(2)
        # f0930437: the sweep's '6' (quest lock held, light-low never asked).
        self.assertTrue(self.policy._light_judgment(board).releases_one_shot_quest)
        self.assertEqual(self._decide(board), READ_RECALL_FROM_F)
        self.assertEqual(self.policy._last_return_trigger, "light-low")

    def test_lightless_pair_leaves_instead_of_alternating(self):
        first = self._decide(self._board(4))
        second = self._decide(self._board(5))
        # f0930437: ('4', 'dark:backtrack') then the sweep's '6' back off the
        # stairs, repeated until loop-detected.  Recall cannot be read in the
        # dark (policy_town.py return comment), so the return walks to the
        # staircase under its own dark rung and ascends there.
        self.assertEqual(
            [first, second],
            [("4", "dark:backtrack"), ("<", "return:ascend")],
        )

    def test_control_104_and_100_boards_keep_sweeping(self):
        for index in (0, 1):
            with self.subTest(index=index):
                self.setUp()
                board = self._board(index)
                self.assertFalse(
                    self.policy._light_judgment(board).releases_one_shot_quest
                )
                self.assertEqual(self._decide(board), SWEEP)

    def test_control_faint_board_with_oil_keeps_the_quest(self):
        board = self._with_oil(self._board(2))
        self.assertFalse(self.policy._light_judgment(board).releases_one_shot_quest)
        self.assertNotEqual(self._decide(board), READ_RECALL_FROM_F)
        self.assertTrue(self.policy._return_exit_locked(board))

    def _entry_reason(self, board):
        sink = []
        self.policy._evaluate_fixed_quest_readiness(
            board, 2, require_target_town=False, commit=False, telemetry_sink=sink
        )
        return sink[0].get("reason")

    def _entry_board(self):
        board = self._board(0)
        # DECLARED CONSTRUCTED: full HP and an admitted strategy force (the
        # recorded mid-quest character fails the profile's force check) so the
        # entry reaches the light check.
        force = mock.patch.object(
            self.policy, "_approved_strategy_force_ready", return_value=True
        )
        force.start()
        self.addCleanup(force.stop)
        return replace(board, player=replace(board.player, hp=board.player.max_hp))

    def test_one_shot_quest_entry_refused_without_oil(self):
        self.assertEqual(self._entry_reason(self._entry_board()), "light-oil")

    def test_one_shot_quest_entry_admitted_with_oil(self):
        self.assertNotEqual(
            self._entry_reason(self._with_oil(self._entry_board())), "light-oil"
        )

    def test_one_shot_quest_entry_admitted_for_a_fuelless_light(self):
        board = self._entry_board()
        lamp = next(item for item in board.equipment if item.is_light)
        # DECLARED CONSTRUCTED: the worn light is a permanent light.
        lamp = replace(lamp, sval=SV_LITE_FEANOR, fuel=0)
        board = replace(
            board,
            equipment=type(board.equipment)(
                lamp if item.is_light else item for item in board.equipment
            ),
        )
        self.assertNotEqual(self._entry_reason(board), "light-oil")


if __name__ == "__main__":
    unittest.main()
