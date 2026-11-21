"""n1-a life-531: the departure minimum's depth_abilities leaf admits the climb's 50F landing.

Owner 2026-11-22 (verbatim choice) 「城の50Fに帰還してすぐ38〜42Fへ登る」 (deep_climb).  After the
rule landed the character recalled to the Castle's 50F about thirty times (07:49-08:19); on
08:04 two trap doors dropped it 50F -> 52F -> 54F, so the Castle's recall depth became 54 and
the switch took the Mountain's 50F landing.  Every destination gate admitted it (the recall,
the depth gate, the carried means), but the departure minimum's ``depth_abilities`` leaf read the
worn kit at 50F without the exception, and with the Cure Critical Wounds potions short the
town end stopped as ``town:blocked:survival:depth_abilities`` (2026-11-22 08:25:16).

Recorded (tests/fixtures/n1a-531-mountain-climb-1122-survival, the server's town-arrival
checkpoint of 08:25:05): rows 0-12 replay, row 13 was the stop.

DECLARED CONSTRUCTED:

* the dungeon boards of the trap-door net: the recorded row-13 board moved to the Castle's
  50F and 52F (``floor_key``, ``town_flag``); no such board was journalled.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures")
CASTLE, MOUNTAIN = 12, 14
STOP = "town:blocked:survival:depth_abilities"


class SurvivalStopRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(
                FIXTURES / "n1a-531-mountain-climb-1122-survival", Path(cls.scratch.name))
            cls.replayed = replay_window("n1a-531-survival", cls.policy, iter(steps[:13]))
            cls.recorded = steps[13][0]
            cls.board = steps[13][1]()
            cls.key = cls.policy.choose_key(cls.board)
        cls.reason = cls.policy.last_reason

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_rows_before_the_stop_replay_on_the_mountain_switch(self):
        self.assertEqual(self.replayed.matched_rows, 9 + 4)
        self.assertEqual(self.recorded["reason"], STOP)
        self.assertEqual(self.policy._alternate_dungeon, MOUNTAIN)
        self.assertEqual(self.board.dungeon_recall_depths[CASTLE], 54)
        self.assertEqual(self.board.dungeon_recall_depths[MOUNTAIN], 50)

    def test_the_town_end_is_no_depth_abilities_stop(self):
        self.assertNotEqual(self.reason, STOP)
        self.assertEqual((self.key, self.reason), ("5", "town:end-mining-cycle"))

    def test_the_minimum_reads_the_climb_landing_like_every_other_gate(self):
        policy, board = self.policy, self.board
        values = policy._departure_minimum(board, 50)["values"]
        self.assertIs(values["depth_abilities"], True)
        # What is left is the Cure Critical Wounds stock (the stock-out's mining cycle answers it).
        self.assertEqual({name for name, value in values.items() if value is not True},
                         {"cure_critical_ready"})
        self.assertTrue(policy._recall_destination_safe(board, MOUNTAIN))
        self.assertTrue(policy._destination_depth_allowed(board, 50))

    def test_a_trap_door_below_the_climb_landing_is_a_named_stop(self):
        from hengbot import deep_climb

        policy = self.policy
        saved = getattr(policy, deep_climb.MEMORY, None)
        try:
            setattr(policy, deep_climb.MEMORY, None)
            # DECLARED CONSTRUCTED (module docstring).
            boards = [self.board] + [replace(self.board, floor_key=key, town_flag=False)
                                     for key in ((CASTLE, 50, 0), (CASTLE, 52, 0))]
            deep_climb.observe(policy, boards[0])
            deep_climb.observe(policy, boards[1])
            self.assertIsNone(deep_climb.stop_key(policy, boards[1]))  # the recall's arrival
            deep_climb.observe(policy, boards[2])
            self.assertEqual(deep_climb.stop_key(policy, boards[2]), "5")
            self.assertEqual(policy.last_reason, deep_climb.STOP_REASON)
        finally:
            setattr(policy, deep_climb.MEMORY, saved)


if __name__ == "__main__":
    unittest.main()
