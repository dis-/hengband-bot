"""A process restarted on the finale's floor takes the expedition's mark again (n1-c life-217).

Recorded (capture n1c-217-20261121-death-100f, captures/20261121-144112-exit-no-marker): n1-c was
restarted at 14:41:02 on Angband 100F from the save of its 14:24 stop, the Serpent of Chaos and its
summons beside it.  The expedition's mark (finale_prep ``lifted``) lives in the process only, so
the new process had none: no angband-finale reason at all, the ordinary rungs answered
(emergency:heal, emergency:recall 'rg', ranged shots, emergency:seek-upstairs) and the character
died at 14:41:09.  Its first board (tests/fixtures/n1c-finale-restart-1121): 100F, quest 9 (the
Serpent) TAKEN, carrying 21 Restore Mana and 12 *Healing* (the ordinary play carries neither:
consumable_policy sends them to the Home).

The policy: n1-c life-217's 12:29:10 checkpoint (tests/fixtures/n1c-99f-quick-return-1121).

DECLARED CONSTRUCTED: the fresh process's phase (finale_prep's Phase as a new process starts it:
no board seen), no return latched, no list re-read at the decision's head; for the ordinary case,
the board's Restore Mana and *Healing* taken out of the pack.
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

from hengbot import angband_cap, angband_finale, angband_finale_battle, finale_prep
from hengbot.model import DUNGEON_ANGBAND, parse_snapshot
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")


class FinaleRestartStateRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURES / "n1c-99f-quick-return-1121",
                                             Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        setattr(self.policy, finale_prep.STATE, finale_prep.Phase())  # DECLARED: a fresh process
        self.policy._returning_to_town, self.policy._last_return_trigger = False, None  # DECLARED
        self.policy._me_power_resume_reads = False  # DECLARED
        rows = json.loads(lzma.decompress(
            (FIXTURES / "n1c-finale-restart-1121" / "boards.json.xz").read_bytes()))
        self.board = parse_snapshot(rows[0]["board"], self.policy._monrace_knowledge)

    def tearDown(self):
        self.scratch.cleanup()

    def decide(self, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = self.policy.choose_key(board)
        return key, self.policy.last_reason

    def test_the_restarted_process_on_100f_is_the_expedition(self):
        board = self.board
        self.assertEqual((board.floor_key[0], board.dungeon_level), (DUNGEON_ANGBAND, 100))
        self.assertFalse(angband_finale.quest_done(board))
        _key, reason = self.decide(board)
        self.assertTrue(finale_prep.lifted(self.policy))
        self.assertTrue(finale_prep.expedition_evident(self.policy, board))
        self.assertIsNone(angband_cap.cap(DUNGEON_ANGBAND, self.policy))
        self.assertTrue(angband_finale_battle.applies(self.policy, board))
        self.assertNotIn(reason, {"emergency:recall", "emergency:seek-upstairs"})
        # No Word of Recall but the battle's own (finale_prep ``recall_closed``).
        self.assertIsNone(self.policy._find_recall_scroll(board))

    def test_no_finale_carry_is_no_expedition(self):
        kinds = {angband_finale.RESTORE_MANA, angband_finale.STAR_HEALING}
        board = replace(self.board, inventory=tuple(
            item for item in self.board.inventory if (item.tval, item.sval) not in kinds))
        self.assertFalse(finale_prep.expedition_evident(self.policy, board))
        self.decide(board)
        self.assertFalse(finale_prep.lifted(self.policy))


if __name__ == "__main__":
    unittest.main()
