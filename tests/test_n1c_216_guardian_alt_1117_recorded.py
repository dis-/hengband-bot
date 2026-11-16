"""n1-c life-216 2026-11-17: the guardian valve takes Angband and dives from 44F to the floor 45F.

n1-c (Lv46 Magic-Eater) reached the Castle's 65F and the Mountain's 50F, both the last floor of
their dungeon with an unbeaten guardian (皇帝『レイザーク』, 大鷲王『ソロンドール』).  The fallback
depth floor is 45 (the deepest reached 65 less 20, owner 2026-11-13); Angband's recall landing
44 was one floor under it and the Glass castle's 40 too, so the guardian valve found no
alternate and the visit stopped on ``town:blocked:guardian-bounce-no-alternate`` (01:50:46).

Owner 2026-11-17 「下限まで潜れるなら鉄獄を選ぶ」: the guardian valve takes Angband although its
landing is above the floor when the floor is within Angband's depth, meets the depth
requirements and is no guardian floor the kit cannot pass; the recall lands on 44 and the
ordinary Angband descent goes on to 45 and below (``dive_floor.angband_valve_dive``).

Recorded: tests/fixtures/n1c-216-guardian-alt-1117 (tests/extract_n1c_216_guardian_alt_1117_fixture.py),
the 01:50:34 town-arrival checkpoint and its 42 journal rows; rows 0-40 replay as recorded and
are posted with their recorded keys, row 41 is the stop.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import dive_floor, fallback_depth_floor
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-guardian-alt-1117"
STOP_ROW = 41
CASTLE, MOUNTAIN, GLASS_CASTLE = dive_floor.DUNGEON_CASTLE, dive_floor.DUNGEON_MOUNTAIN, 20
STOP = "town:blocked:guardian-bounce-no-alternate"
SWITCHED = "town:entrance-step-off:town:unsafe-recall-fallback"
NO_SAFE_TELEPATHY = ("town:entrance-step-off:fundraising:no-safe-destination:depth-gate:"
                     "destination-50:missing-telepathy")


class GuardianAltTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _rows, decisions = load(FIXTURE, Path(cls.scratch.name))
        for recorded, supply in decisions[:STOP_ROW]:
            board = supply()
            key = policy.choose_key(board)
            assert (key, policy.last_reason) == (recorded["key"], recorded["reason"]), recorded
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        recorded, supply = decisions[STOP_ROW]
        assert recorded["reason"] == STOP, recorded
        cls.board = supply()
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def test_the_stop_board(self):
        policy, board = self.policy, self.board
        self.assertEqual(fallback_depth_floor.floor(policy, board), 45)
        self.assertEqual({did: board.dungeon_recall_depths[did]
                          for did in (DUNGEON_ANGBAND, CASTLE, MOUNTAIN, GLASS_CASTLE)},
                         {DUNGEON_ANGBAND: 44, CASTLE: 65, MOUNTAIN: 50, GLASS_CASTLE: 40})
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason),
                         (MOUNTAIN, "guardian_valve"))
        for did in (CASTLE, MOUNTAIN):
            depth = board.dungeon_recall_depths[did]
            self.assertEqual(policy._dungeon_knowledge[did].max_depth, depth)
            self.assertTrue(policy._guardian_floor_blocked(board, did, depth), did)
        # Angband's landing is safe; only the floor refused it.
        self.assertTrue(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        self.assertFalse(fallback_depth_floor.landing_allowed(policy, board, 44))

    def test_the_guardian_valve_recalls_to_angband_and_dives_to_the_floor(self):
        policy, board = self.policy, self.board
        key = policy.choose_key(board)
        # Unfixed: ("7", "town:blocked:guardian-bounce-no-alternate").
        self.assertEqual((key, policy.last_reason), ("7", SWITCHED))
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason,
                          policy._target_dungeon_id), (DUNGEON_ANGBAND, "guardian_valve",
                                                       DUNGEON_ANGBAND))
        self.assertTrue(dive_floor.angband_valve_dive(policy, board, 44))
        self.assertTrue(dive_floor.angband_valve_held(policy, board))
        # The depth floor does not end the switch on the next town board.
        self.assertFalse(fallback_depth_floor.settle(policy, board))
        self.assertEqual(policy._alternate_dungeon, DUNGEON_ANGBAND)
        # No ceiling on the Angband descent: the floor is a target, not a limit.
        self.assertIsNone(dive_floor.target(policy))

    def _assert_still_stops(self, reason=STOP):
        policy, board = self.policy, self.board
        self.assertFalse(dive_floor.angband_valve_dive(policy, board, 44))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("7", reason))
        self.assertNotEqual(policy._alternate_dungeon, DUNGEON_ANGBAND)

    def test_control_the_floor_is_angbands_guardian_floor(self):
        policy = self.policy
        info = policy._dungeon_knowledge[DUNGEON_ANGBAND]
        guardian = policy._dungeon_knowledge[CASTLE].guardian_id
        # DECLARED CONSTRUCTED: Angband ends at the floor 45 with the Castle's unbeaten guardian.
        policy._dungeon_knowledge[DUNGEON_ANGBAND] = replace(info, max_depth=45,
                                                             guardian_id=guardian)
        self.assertTrue(policy._guardian_floor_blocked(self.board, DUNGEON_ANGBAND, 45))
        self._assert_still_stops()

    def test_control_the_floor_fails_the_depth_requirements(self):
        policy, board = self.policy, self.board
        # DECLARED CONSTRUCTED: the deepest reached 70, so the floor is 50 (telepathy required
        # from 50F), and the player without telepathy; the landing 44 does not require it.
        policy._deepest_level = 70
        self.board = board = replace(board, player=replace(
            board.player, abilities=board.player.abilities - {"telepathy"}))
        self.assertEqual(fallback_depth_floor.floor(policy, board), 50)
        self.assertEqual(policy._missing_required_abilities(board, 50), frozenset({"telepathy"}))
        self.assertTrue(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        # The Mountain landing 50 now lacks telepathy too: the unsafe-recall fallback's own next
        # rule (fundraising for the missing ability) decides, never Angband.
        self._assert_still_stops(NO_SAFE_TELEPATHY)

    def test_control_the_floor_is_below_angbands_depth(self):
        policy = self.policy
        info = policy._dungeon_knowledge[DUNGEON_ANGBAND]
        # DECLARED CONSTRUCTED: Angband ends at 44, above the floor.
        policy._dungeon_knowledge[DUNGEON_ANGBAND] = replace(info, max_depth=44, guardian_id=0)
        self._assert_still_stops()


if __name__ == "__main__":
    unittest.main()
