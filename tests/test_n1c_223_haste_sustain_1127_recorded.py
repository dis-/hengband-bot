"""The 70-80F speed +10 is met by sustained Speed doses, and the haste is kept up there (n1-c life-223).

Recorded (tests/extract_n1c_223_haste_sustain_1127_fixture.py, ``n1c-223-haste-sustain-1127``):
the town-arrival checkpoint of 2026-11-27 13:40:48 (Zombie Magic-Eater CL46, HP 1074, permanent
speed +3, absorbed Speed 99 charges at a reliable rate).  Under the 2026-11-26 row (permanent +10
from 70F) Angband's speed ceiling was 69F, where the Ring of Speed (level 80) is out of depth; the
character's Angband recall depth was 69.  Rows 0-74 replay the recorded keys through the public
``choose_key`` (full state); row 75 diverges with or without this change (the calibration reads a
character dump the live game wrote that the journal does not carry: stale-dump-file), so the gates
are read on row 75's board: they admit 70-90F (haste_sustain ``row_met``: 99 doses of the 20 a p90
dive takes) and the ceiling is 90F (80F before owner 2026-11-28 moved the +25 row to 91F).  The recorded visit went on to read Word of Recall to Angband.

DECLARED CONSTRUCTED: the upkeep (``after_ladder``) on the last board moved onto Angband 75F (the
floor, the town flag, an awake hostile in view, the haste shown or not); the dose counts lowered
by replacing the absorbed-power charge reader.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_cap, haste_sustain, me_capability
from hengbot.model import DUNGEON_ANGBAND, MonsterState, Position
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import MID_SPEED_GATE_LABEL
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-223-haste-sustain-1127"
REPLAYED_ROWS = 75


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class HasteSustain223RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        for recorded, supply in steps[:REPLAYED_ROWS]:
            key, reason = decide(policy, supply())
            assert (key, reason) == (recorded["key"], recorded["reason"]), recorded["row"]
            post(policy, key)
        cls.policy, cls.board = policy, steps[REPLAYED_ROWS][1]()
        cls.reasons = [row["reason"] for row in journal]

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_recorded_visit_recalls_to_angband(self):
        self.assertIn("town:recall-to-angband", self.reasons[REPLAYED_ROWS:])

    def test_sustained_doses_admit_70_to_80f(self):
        policy, board = self.policy, self.board
        self.assertEqual(haste_sustain.uses(policy, board), 99)
        for depth in (70, 75, 80, 85, 90):
            self.assertNotIn(MID_SPEED_GATE_LABEL,
                             policy._missing_required_abilities(board, depth, owned=True), depth)
        # Owner 2026-11-28: the +25 row starts at 91F, the ceiling is 90F.
        self.assertEqual(angband_cap.speed_ceiling(policy, board), 90)

    def test_too_few_doses_keep_the_ceiling_at_69f(self):
        policy, board = self.policy, self.board
        with mock.patch.object(me_capability, "charges",
                               return_value=haste_sustain.DIVE_HASTE_USES - 1):
            self.assertIn(MID_SPEED_GATE_LABEL,
                          policy._missing_required_abilities(board, 70, owned=True))
            self.assertEqual(angband_cap.speed_ceiling(policy, board), 69)

    def floor(self, *, hasted=False, hostile=True):
        hostiles = [MonsterState(index=7, position=Position(1, 1), hp=100, max_hp=100, distance=5,
                                 friendly=False, pet=False)] if hostile else []
        speed = self.board.player.speed_display
        display = (speed[0], speed[1], "yellow" if hasted else "light_green", speed[3])
        player = replace(self.board.player, speed_display=display)
        return replace(self.board, floor_key=(DUNGEON_ANGBAND, 75, 0), town_flag=False,
                       visible_monsters=hostiles, detected_monsters=[], player=player)

    def test_the_upkeep_doses_before_an_ordinary_action(self):
        policy = self.policy
        policy.last_reason = "explore"
        setattr(policy, haste_sustain.MEMORY, None)
        key = haste_sustain.after_ladder(policy, self.floor(), "4")
        self.assertNotEqual(key, "4")
        self.assertTrue(policy.last_reason.startswith(haste_sustain.REASON), policy.last_reason)

    def test_the_upkeep_leaves_escapes_and_quiet_floors_alone(self):
        policy = self.policy
        policy.last_reason = "emergency:teleport"
        self.assertEqual(haste_sustain.after_ladder(policy, self.floor(), "r"), "r")
        policy.last_reason = "explore"
        self.assertEqual(haste_sustain.after_ladder(policy, self.floor(hostile=False), "4"), "4")

    def test_a_recast_waits_out_the_shortest_haste(self):
        policy = self.policy
        board = self.floor(hasted=True)
        policy.last_reason = "explore"
        setattr(policy, haste_sustain.MEMORY, (board.floor_key, board.turn - 10))
        self.assertEqual(haste_sustain.after_ladder(policy, board, "4"), "4")
        setattr(policy, haste_sustain.MEMORY,
                (board.floor_key, board.turn - haste_sustain.RENEW_GAME_TURNS))
        self.assertNotEqual(haste_sustain.after_ladder(policy, board, "4"), "4")

    def test_below_the_reserve_the_floor_starts_a_return(self):
        policy, floor = self.policy, self.floor()
        self.assertNotIn(MID_SPEED_GATE_LABEL, policy._missing_required_abilities(floor, 75))
        with mock.patch.object(me_capability, "charges",
                               return_value=haste_sustain.RETURN_RESERVE_USES - 1):
            self.assertIn(MID_SPEED_GATE_LABEL, policy._missing_required_abilities(floor, 75))


class HasteSustainConstantsTest(unittest.TestCase):
    def test_the_dive_takes_twenty_doses(self):
        self.assertEqual(haste_sustain.DIVE_GAME_TURNS, 13263)
        self.assertEqual(haste_sustain.DIVE_HASTE_USES, 20)


if __name__ == "__main__":
    unittest.main()
