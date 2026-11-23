"""A killed finale target leaves the Restore Mana plan (owner 2026-11-24, restore_mana_target).

Owner, verbatim (2026-11-24): 「サーペントだけで計算し直す — 倒した標的のHPは目標から外す。オベロンを
倒した後の100Fの目標は、サーペントだけの計算の2倍（今は62本）にする。」

Recorded (tests/extract_finale_bm_entry_1124_fixture.py, ``n1b-416-finale-bm-entry-1124``): n1-b
life-416's town-arrival checkpoint of 2026-11-24 02:42:34 (turn 4601311), its first board.  Oberon
was killed on 99F at 02:20: the board's quest 8 (008_Oberon) reads FINISHED (4), quest 9
(009_SerpentOfChaos) TAKEN (1).  Four rockets absorbed, so a potion restores 3 uses; a Powerful
Activation rocket deals 550: 1.5 x 30000 / (3 x 0.9 x 550) = 30.3 -> 31, carried twice: 62.  Both
targets (the rule before) gave 1.5 x 40989 / 1485 = 41.4 -> 42 and 84.  The Home and pack own 76.

DECLARED CONSTRUCTED: the quest statuses of ``test_*_constructed`` (Oberon back to TAKEN, both
FINISHED) and the expedition's Restore Mana used of the recall rule.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, restore_mana_target
from hengbot.policy_constants import QUEST_STATUS_FINISHED, QUEST_STATUS_TAKEN
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-bm-entry-1124"
OBERON, SERPENT = 860, 862
OBERON_QUEST, SERPENT_QUEST = 8, 9


class RestoreManaTargetKilled1124RecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        self.board = steps[0][1]()
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(self.board)

    def tearDown(self):
        self.scratch.cleanup()

    def with_statuses(self, **statuses):
        quests = dict(self.board.quests)
        for quest_id, status in ((OBERON_QUEST, statuses["oberon"]), (SERPENT_QUEST, statuses["serpent"])):
            quests[quest_id] = replace(quests[quest_id], status=status)
        return replace(self.board, quests=quests)

    def test_the_recorded_quests(self):
        self.assertEqual(self.board.quests[OBERON_QUEST].status, QUEST_STATUS_FINISHED)
        self.assertEqual(self.board.quests[SERPENT_QUEST].status, QUEST_STATUS_TAKEN)

    def test_after_oberon_the_plan_is_the_serpents_alone(self):
        figures = restore_mana_target.plan(self.policy, self.board)
        self.assertEqual(figures["target_hp"], {SERPENT: 30000})
        self.assertEqual(figures["killed"], [OBERON])
        self.assertEqual((figures["target"], figures["carry"], figures["held"]), (31, 62, 76))
        self.assertFalse(restore_mana_target.wanted(self.policy, self.board))

    def test_every_reader_follows_the_plan(self):
        self.assertEqual(angband_finale.restore_mana_goal(self.policy, self.board), 31)
        self.assertEqual(angband_finale.restore_mana_carry(self.policy, self.board), 62)
        rows = angband_finale.readiness(self.policy, self.board)
        self.assertEqual(rows["owned"]["restore_mana"]["required"], 62)
        self.assertTrue(rows["owned"]["restore_mana"]["ready"])
        self.assertEqual(rows["carried"]["restore_mana"]["required"], 62)
        self.assertEqual(angband_finale.shortage(self.policy, self.board, angband_finale.RESTORE_MANA), 0)

    def test_the_recall_rule_counts_against_the_serpents_plan(self):
        memory = angband_finale.memory(self.policy)
        memory.restore_mana_used = 61  # DECLARED
        self.assertFalse(angband_finale.restore_mana_overspent(self.policy, self.board))
        memory.restore_mana_used = 62  # DECLARED: twice the Serpent's plan
        self.assertTrue(angband_finale.restore_mana_overspent(self.policy, self.board))

    def test_both_alive_keeps_both_targets_constructed(self):
        board = self.with_statuses(oberon=QUEST_STATUS_TAKEN, serpent=QUEST_STATUS_TAKEN)
        figures = restore_mana_target.plan(self.policy, board)
        self.assertEqual(figures["target_hp"], {OBERON: 10989, SERPENT: 30000})
        self.assertEqual((figures["target"], figures["carry"]), (42, 84))
        self.assertTrue(restore_mana_target.wanted(self.policy, board))
        self.assertEqual(angband_finale.shortage(self.policy, board, angband_finale.RESTORE_MANA), 8)

    def test_both_killed_collects_nothing_constructed(self):
        board = self.with_statuses(oberon=QUEST_STATUS_FINISHED, serpent=QUEST_STATUS_FINISHED)
        figures = restore_mana_target.plan(self.policy, board)
        self.assertEqual((figures["target"], figures["carry"]), (0, 0))
        self.assertFalse(restore_mana_target.wanted(self.policy, board))
        angband_finale.memory(self.policy).restore_mana_used = 5  # DECLARED
        self.assertFalse(angband_finale.restore_mana_overspent(self.policy, board))


if __name__ == "__main__":
    unittest.main()
