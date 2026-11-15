"""In town the hunt owns the town monsters it defeats: no retreat from them (n1-a life-525).

n1-a life-525 (Lv37 Warrior, 857 HP, build 3b52c43f0) stopped in town on 2026-11-15
13:31:04 (loop-detected: town blocked).  Two 殺人蜂 flew about the town.  When one was in
view the town hunt walked toward it (town:kill-mob-approach, _town_kill_mob_key: approach
and kill every town monster this character defeats); when both had flown out of sight
they were detected only, and the detected-threat preparation read them as a converging
melee pack and retreated to a choke (detected:prepare-choke).  The two owners alternated
for 200 boards (journal rows 122-321), the town-errand owner retired without progress
(town:blocked:owner-retired) and the town block stopped the bot.

Fix: the detected-threat preparation leaves detected monsters to the town hunt when, in
town, every one is a town monster this character defeats -- as it leaves the Sewer's
plan monsters to the approved Q2 strategy (policy._detected_threat_preparation_key).

Recorded: the incident capture's town-arrival checkpoint and its first 123 journal rows
(tests/extract_n1a_525_stops_1115_fixtures.py), decided through the public choose_key and
compared with the record.  Row 91 is the first detected:prepare-choke from the bees, row
122 the first of the alternation.  Rows 91, 95 and 97 are FORCED: from row 91 the fix
decides differently (row 91 resumes the departure instead of retreating), and the
recorded key is posted.

DECLARED CONSTRUCTED: row 1's character dump wrote a calibration the journal does not hold;
the arrival calibration is re-adopted with its observed turn moved to row 1's board (the
same character, level and stats; without it the equipment transaction of row 4 does not
open).  The counter-case makes the bees unbeatable (``_town_monster_unbeatable``), so the
retreat is still the preparation's.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-stops-1115" / "kill-mob"
DUMP_ROW = 1
FIRST_RETREAT_ROW = 91
ALTERNATION_ROW = 122
FORCED = {91, 95, 97}
BEE = 174
RETREAT = "detected:prepare-choke"


class N1a525KillMob1115RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, cls.journal, steps = load(FIXTURE, scratch)
        calibration = json.loads(
            (scratch / "town-arrival" / "sidecars" / "_character_calibration_path")
            .read_text(encoding="utf-8"))
        cls.replayed = []
        cls.checkpoints = {}
        cls.boards = {}
        for recorded, supply in steps:
            row = recorded["row"]
            board = supply()
            if row in (FIRST_RETREAT_ROW, ALTERNATION_ROW):
                cls.checkpoints[row] = checkpoint_bytes(policy)
                cls.boards[row] = board
            key = policy.choose_key(board)
            cls.replayed.append((row, (key, policy.last_reason),
                                 (recorded["key"], recorded["reason"])))
            policy.confirm_key_posted(recorded["key"])
            if row == DUMP_ROW:
                # DECLARED CONSTRUCTED (module docstring): the dump's calibration.
                calibration["observed_turn"] = board.turn
                dumped = scratch / "calibration-after-dump.json"
                dumped.write_text(json.dumps(calibration), encoding="utf-8")
                adopt_calibration(policy, dumped, scratch / "runtime")

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, decided, recorded in self.replayed:
            if row not in FORCED and row < ALTERNATION_ROW:
                self.assertEqual(decided, recorded, row)

    def restored(self, row):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoints[row])
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy

    def test_the_recorded_rows_retreat_from_detected_bees(self):
        for row in (FIRST_RETREAT_ROW, ALTERNATION_ROW):
            self.assertEqual(self.journal[row]["reason"], RETREAT, row)
            board = self.boards[row]
            self.assertTrue(board.in_town)
            self.assertFalse(board.visible_monsters)
            self.assertTrue(board.detected_monsters)
            self.assertEqual({monster.race_id for monster in board.detected_monsters}, {BEE})
        self.assertEqual(self.journal[ALTERNATION_ROW - 3]["reason"], "town:kill-mob-approach")

    def test_the_bees_out_of_sight_are_not_retreated_from(self):
        for row in (FIRST_RETREAT_ROW, ALTERNATION_ROW):
            policy = self.restored(row)
            board = self.boards[row]
            self.assertTrue(all(not policy._town_monster_unbeatable(board, monster)
                                for monster in board.detected_monsters))

            key = policy.choose_key(board)

            self.assertNotEqual(policy.last_reason, RETREAT, (row, key))
            self.assertIsNone(policy._detected_threat_route, row)
        # The hunt walks on to where the bee was last seen.
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")

    def test_unbeatable_detected_monsters_are_still_retreated_from(self):
        # DECLARED CONSTRUCTED (module docstring): the bees made unbeatable.
        policy = self.restored(FIRST_RETREAT_ROW)
        policy._town_monster_unbeatable = lambda snapshot, monster: True

        policy.choose_key(self.boards[FIRST_RETREAT_ROW])

        self.assertEqual(policy.last_reason, RETREAT)


if __name__ == "__main__":
    unittest.main()
