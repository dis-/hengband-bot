"""The 99F/100F battle's lost target: searched by detection, the floor regenerated only after.

Owner 2026-11-21 (verbatim, LOCKED) 「感知で回る・作り直した階でも一巡する」, on n1-c life-217's first
99F expedition (capture n1c-217-20261121-99f-quick-return): the arrival sweep's *Destruction*
teleported Oberon (a QUESTOR) away; the battle knew neither where it was nor where it was last
seen and answered nothing, so the kill-quest regeneration took the stairs 99F -> 98F -> 99F at
12:29:04 with the floor unsearched.  Now the quest search's lap with its detections searches the
floor (quest_target_search ``finale_searching``), and the stairs regenerate it only after one
whole coverage without the target (``finale_swept``).  And the reset-recall-depth answer read
the cap without the expedition's lift: the recall read on 98F (12:29:06) answered y and the
saved 99F fell to 98F (angband_cap.reset_recall_depth, the operation's ``cap_lifted``).

Fixture tests/fixtures/n1c-99f-quick-return-1121 (test_n1c_217_99f_quick_return_1121_recorded):
the town-arrival checkpoint after that return and the recorded boards 1984 (98F, saved depth 99),
1991 (the new 99F, Oberon detected) and 1994 (99F, Oberon shown nowhere, on the up stairs).

DECLARED CONSTRUCTED:
* the expedition's mark (finale_prep ``lifted``) and no return latched, as in that test;
* the battle past its sweep with no last-seen cell (as after the sweep teleported Oberon away);
* the search's one whole coverage (``sweeps.count``) for the regeneration case;
* threat_tiers' T1 verdict on Oberon (the recorded hunt verdict).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import (
    angband_cap, angband_finale, angband_finale_battle, finale_prep, hunt_target,
    quest_target_search, threat_tiers,
)
from hengbot.cli import _cap_lifted
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-99f-quick-return-1121"


class FinaleTargetSearchRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(self.policy)
        held.lifted, held.step = True, finale_prep.DONE  # DECLARED: the expedition's mark
        self.policy._returning_to_town, self.policy._last_return_trigger = False, None  # DECLARED
        # DECLARED: no list re-read at the decision's head (me_powers_refresh.resume_read_key
        # answers before the board is observed, so the 98F board would not be seen).
        self.policy._me_power_resume_reads = False
        rows = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
        self.raw = {row["line"]: row["board"] for row in rows}
        self.boards = {line: parse_snapshot(board, self.policy._monrace_knowledge)
                       for line, board in self.raw.items()}

    def tearDown(self):
        self.scratch.cleanup()

    def decide(self, line):
        board = self.boards[line]
        with contextlib.redirect_stdout(io.StringIO()):
            key = self.policy.choose_key(board)
        if key:
            self.policy.confirm_key_posted(key)
        return board

    def lost_on_99f(self):
        """98F, then the 99F with Oberon shown nowhere; DECLARED: the battle past its sweep with
        no last-seen cell."""
        self.decide(1984)
        board = self.decide(1994)
        held = angband_finale_battle.battle(self.policy, board)
        held.phase, held.last_seen = angband_finale_battle.BATTLE, None
        return board

    def test_a_lost_target_is_searched_and_the_stairs_wait_for_one_whole_coverage(self):
        board = self.lost_on_99f()
        self.assertIsNone(angband_finale_battle.target_monster(board))
        self.assertTrue(angband_finale_battle.lost(self.policy, board))
        self.assertTrue(quest_target_search.finale_searching(self.policy, board))
        self.assertTrue(quest_target_search.searching(self.policy, board))
        # The recorded 12:29:04 regeneration does not start on an unsearched floor.
        here = board.grid_at(board.player.position)
        self.assertTrue(self.policy._is_upstairs_target(here))
        self.assertIsNone(self.policy._start_kill_quest_regeneration(board))
        # DECLARED: the lap covered the floor once and the target was not shown.
        quest_target_search._memory(self.policy, board).sweeps.count = (
            quest_target_search.FINALE_SWEEPS_TO_REGENERATE)
        self.assertTrue(quest_target_search.finale_swept(self.policy, board))
        self.assertFalse(quest_target_search.finale_searching(self.policy, board))
        self.assertEqual(self.policy._start_kill_quest_regeneration(board), "<")
        self.assertEqual(self.policy.last_reason, "quest:regen:ascend")

    def test_a_last_seen_cell_reached_empty_is_forgotten(self):
        board = self.lost_on_99f()
        held = angband_finale_battle.battle(self.policy, board)
        held.last_seen = (board.player.position.y, board.player.position.x)  # DECLARED
        self.assertFalse(angband_finale_battle.lost(self.policy, board))
        angband_finale_battle._observe(self.policy, board, held)
        self.assertIsNone(held.last_seen)
        self.assertTrue(angband_finale_battle.lost(self.policy, board))

    def test_no_t1_verdict_stops_the_hunt_for_oberon(self):
        self.decide(1984)
        board = self.boards[1991]
        self.assertIsNotNone(angband_finale_battle.target_monster(board))  # Oberon detected
        with mock.patch.object(threat_tiers, "cannot_win", return_value=True):  # DECLARED
            self.decide(1991)
        self.assertFalse(hunt_target.quest_target_unbeatable(self.policy, board))
        self.assertEqual(hunt_target.target_race(self.policy, board),
                         angband_finale.target_race(board))

    def test_the_expedition_keeps_the_saved_99f_at_the_recall_question(self):
        observation = self.raw[1984]  # 98F, the saved depth 99 (the recorded 12:29:06 read)
        self.assertEqual(observation["progress"]["dungeon_recall_depths"]["1"], 99)
        self.assertTrue(angband_cap.reset_recall_depth(observation))  # the cap's own answer
        self.assertTrue(_cap_lifted(self.policy))
        self.assertFalse(angband_cap.reset_recall_depth(observation, lifted=True))
        finale_prep.phase(self.policy).lifted = False
        self.assertFalse(_cap_lifted(self.policy))


if __name__ == "__main__":
    unittest.main()
