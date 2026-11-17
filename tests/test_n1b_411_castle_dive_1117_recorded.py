"""n1-b life-411 2026-11-17: Angband 51 refused for *Destruction*, the Castle 20 dives instead.

The Lv36 Magic-Eater (Angband 51 reached at 10:06, the Castle 20, the Mountain 30, dungeon 18 30)
holds no *Destruction* means: the absorbed power (21 charges) succeeds 78%, under the owner's 80%
(2026-10-31, 2026-11-04); the staves it bought at the Black Market (95% as staves) were absorbed.
The recall target was Angband 51 (alternate_lease's deepest destination); the unsafe-recall
fallback (policy._activate_safe_recall_fallback) looked for an entered landing between the
fallback depth floor (51 - 20 = 31, owner 2026-11-13) and a ceiling of 29 (the over-extended
depth 30, recorded at Angband 30 before the character went on to 51), found none, and the visit
fundraised: from 12:12 to 13:08 Yeek cave 1F mining, then fundraise:mining-hard-limit and
town:blocked:depth-gate:destination-51:missing-destruction until loop-detected (13:08:57).

Owner 2026-11-17 (verbatim): 「想定は城の20Fから潜り城40F付近を探索することである。なにかを曲解した
実装になっている可能性が高い」.  Two misreadings:
* the dive to the floor (owner 2026-11-15 「想定は城か山。城29F、山29Fをターゲットにして、浅いところ
  から潜って辿り着く。」, dive_floor) was read for the over-extension valves only, never for the
  unsafe-recall fallback, whose only other answer was the fundraising;
* an over-extended depth under the floor bounded the fallback by a ceiling below its own floor.
Now the fallback takes the Castle (dive_floor.pick_refused), holds it across town boards
(dive_floor.refused_dive_held), and the descent goes on below the floor to 49, the 50F gate
(since the owner's 2026-11-17 answer for n1-a life-530: to the band 38-42, dive_floor.band).

Recorded: the town-arrival checkpoint of 13:08:41, its 26 journal rows (row 25 the first stop)
and the sidecar files (tests/extract_n1b_411_castle_dive_1117_fixture.py).

DECLARED CONSTRUCTED:
* ``stop_policy``: rows 0-24 decided by the restored policy with the recorded keys posted (the
  replay's store screens part from the recorded ones at row 21), then every store marked tried
  this visit, the state the recorded row 24 (fundraise:fallback-exhausted-plan) left: on it the
  parent of this change decides the recorded stop.
* the Castle's recall landing raised to 45 (after a dive), for the over-extension ceiling.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import alternate_lease, destruction_use, dive_floor, fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-castle-dive-1117"
STOP_ROW = 25
STOP_REASON = "town:blocked:depth-gate:destination-51:missing-destruction"
CASTLE, MOUNTAIN = dive_floor.DUNGEON_CASTLE, dive_floor.DUNGEON_MOUNTAIN


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


class N1b411CastleDiveRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.arrival = copy.deepcopy(cls.policy)
        for recorded, supply in steps[:STOP_ROW]:
            decide(cls.policy, supply())
            post(cls.policy, recorded["key"])
        cls.board = steps[STOP_ROW][1]()

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def stop_policy(self):
        policy = copy.deepcopy(self.policy)
        policy._town_store_attempted.update({store: 10 ** 9 for store in range(1, 9)})
        return policy

    def test_a_the_recorded_stop(self):
        self.assertEqual(self.journal[STOP_ROW]["reason"], STOP_REASON)
        policy, board = self.policy, self.board
        self.assertTrue(board.in_town)
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon_reason),
                         (DUNGEON_ANGBAND, alternate_lease.DEEPEST_REASON))
        self.assertEqual(policy._last_overextended_depth, 30)
        self.assertEqual({did: board.dungeon_recall_depths[did]
                          for did in (DUNGEON_ANGBAND, CASTLE, MOUNTAIN, 18)},
                         {DUNGEON_ANGBAND: 51, CASTLE: 20, MOUNTAIN: 30, 18: 30})
        self.assertEqual((fallback_depth_floor.deepest_reached(policy, board),
                          fallback_depth_floor.floor(policy, board)), (51, 31))
        self.assertFalse(destruction_use.holds_means(policy, board))
        self.assertEqual(policy._missing_required_abilities(board, 51), {"destruction"})
        self.assertEqual(policy._missing_required_abilities(board, 49), set())
        # Every landing that passes lies under the floor 31.
        self.assertIsNone(policy._pick_alternate_dungeon(
            board, max_entry_depth=50, prefer_deepest=True, refused_dungeon=DUNGEON_ANGBAND))

    def test_b_the_stop_board_switches_to_the_castle(self):
        policy = self.stop_policy()
        key, reason = decide(policy, self.board)
        self.assertEqual(reason, "town:unsafe-recall-fallback")
        self.assertNotEqual(reason, STOP_REASON)
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon,
                          policy._alternate_dungeon_reason), (CASTLE, CASTLE, "safe_fallback"))
        post(policy, key)
        key, reason = decide(policy, self.board)
        self.assertEqual(reason, "town:recall-to-alt-dungeon")
        self.assertEqual(policy._target_dungeon_id, CASTLE)

    def test_c_the_castle_dive_is_held_to_its_band(self):
        policy, board = copy.deepcopy(self.policy), self.board
        self.assertEqual(policy._activate_safe_recall_fallback(board, 51), CASTLE)
        self.assertTrue(dive_floor.refused_dive_held(policy, board))
        # The floor does not end it on the next town board (it lands at 20 under the floor 31).
        self.assertFalse(fallback_depth_floor.settle(policy, board))
        self.assertEqual(policy._alternate_dungeon, CASTLE)
        self.assertTrue(policy._recall_destination_safe(board, CASTLE))
        # Owner 2026-11-17 (n1-a life-530) 「49Fに帰還して上り階段を探して適正階層まで行く」, n1-b's
        # own 「城40F付近を探索」: the descent goes down to the band 38-42 and no further (it went
        # on to the 50F gate before).
        self.assertIsNone(dive_floor.target(policy))
        self.assertEqual(dive_floor.band(policy, board), (38, 42))
        castle_42 = replace(board, floor_key=(CASTLE, 42, 0))
        self.assertTrue(dive_floor.capped(policy, castle_42, 43))
        self.assertFalse(dive_floor.capped(policy, replace(board, floor_key=(CASTLE, 30, 0)), 31))

    def test_d_an_over_extension_under_the_floor_bounds_nothing(self):
        # DECLARED CONSTRUCTED: the Castle's landing raised to 45 by a dive.
        board = replace(self.board, dungeon_recall_depths={
            **self.board.dungeon_recall_depths, CASTLE: 45})
        policy = copy.deepcopy(self.arrival)
        self.assertEqual(policy._activate_safe_recall_fallback(board, 51), CASTLE)
        self.assertEqual(policy._alternate_dungeon_reason, "safe_fallback")
        self.assertIsNone(getattr(policy, dive_floor.STATE))  # an ordinary landing, no dive


if __name__ == "__main__":
    unittest.main()
