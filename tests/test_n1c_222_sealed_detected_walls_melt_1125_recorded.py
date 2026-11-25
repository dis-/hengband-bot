"""n1-c life-222's sealed pocket after its *Destruction* (2026-11-25, Magic-Eater Lv45, Mountain 50F).

What happened (the decision tail, turns 6850601-6851310): after the *Destruction* the player stood
in a 171-cell pocket reaching beyond the circle (centre (23,175), worst radius 17), so the melt
right after a *Destruction* did not answer.  The absorbed Detect Doors was cast at (38,192)
('mAn', me-power:before-secret-search, turn 6850601), and then the wall search ('s', ladder_idle)
and its walk to the next wall (seek-secret-wall) took 173 of the next 200 decisions, on walls the
cast had reached (within DETECT_RAD_DEFAULT 30 of (38,192)), until the 全感知 of 6851315.

Owner 2026-11-25 「感知が届いた壁はサーチせず溶かして出る」 (door_detect_cover): those walls count as
searched, and the sealed pocket is melted out at once (sealed_pocket, livelock:stone-to-mud).

Recorded: tests/fixtures/n1c-222-destruction-approach-1125.jsonl.gz (the floor from its arrival,
tests/extract_n1c_222_destruction_approach_1125_fixture.py) and the absorbed power lists of the
same capture's town-arrival checkpoint (tests/fixtures/n1c-222-me-lists-1125.json).  A fresh
policy decides every recorded board of the floor from its arrival through the public
``choose_key``, so the *Destruction* circle, the detection's use and the pocket are the replay's
own.  The replay is open: the recorded boards after the first melt do not show it, so each later
board is melted again (the assertion is that no board of the stretch searches).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import door_detect_cover, sealed_pocket
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, parse_snapshot
from tests.support.recorded import _policy
from tests.test_n1c_222_destruction_approach_kept_guardian_1125_recorded import (
    ARRIVAL, BOARDS, LISTS, MONRACE, _cell, _decide,
)

CAST = 6850601      # 'mAn' at (38,192): the absorbed Detect Doors
DETECTION = 6851315  # the 全感知 that ends the stretch
STRETCH = [turn for turn in sorted(BOARDS) if CAST < turn < DETECTION]
SEARCHING = {"search", "seek-secret-wall"}


def _replay():
    with TemporaryDirectory() as directory:
        policy = _policy(Path(directory), MONRACE)
        first = parse_snapshot(copy.deepcopy(BOARDS[ARRIVAL]), MONRACE)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(BOARDS[ARRIVAL]), turn=ARRIVAL - 1,
                          _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
            observe_lists(policy, parse_snapshot(listed, MONRACE))
        decided, previous = {}, None
        for turn in sorted(BOARDS):
            if turn > DETECTION:
                break
            key, previous = _decide(policy, copy.deepcopy(BOARDS[turn]), previous)
            decided[turn] = (_cell(BOARDS[turn]), key, policy.last_reason)
        return policy, decided


class SealedDetectedWallsMeltRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy, cls.decided = _replay()

    def test_the_cast_is_recorded_at_its_radius(self):
        self.assertEqual(self.decided[CAST][2], "me-power:before-secret-search:detect-doors-stairs")
        casts = door_detect_cover.casts(self.policy, parse_snapshot(copy.deepcopy(BOARDS[DETECTION]), MONRACE))
        self.assertIn((Position(38, 192), 30), casts)

    def test_the_first_board_after_the_cast_melts(self):
        # Recorded: seek-secret-wall '7' at (38,192).
        cell, _key, reason = self.decided[STRETCH[0]]
        self.assertEqual(cell, (38, 192))
        self.assertTrue(reason.startswith(sealed_pocket.REASON), reason)

    def test_no_board_of_the_stretch_searches(self):
        # Recorded: 173 searches and their walks between the cast and the 全感知.
        reasons = [self.decided[turn][2] or "" for turn in STRETCH]
        self.assertFalse(SEARCHING & set(reasons), sorted(set(reasons)))
        self.assertTrue(all(reason.startswith(sealed_pocket.REASON) for reason in reasons),
                        sorted(set(reasons)))


class SealedDetectedWallsRevertProofTest(unittest.TestCase):
    def test_without_the_cover_the_walls_are_searched(self):
        with mock.patch.object(door_detect_cover, "covered", lambda policy, cell: False):
            _policy_, decided = _replay()
        reasons = [decided[turn][2] or "" for turn in STRETCH]
        self.assertEqual(decided[STRETCH[0]][2], "seek-secret-wall")
        self.assertGreater(sum(reason == "search" for reason in reasons), 100)


if __name__ == "__main__":
    unittest.main()
