"""Spectator recall destination and its reason (#47, owner request 2026-10-25).

The owner asked 「観戦ページに帰還先の選択理由も付けたい」 and locked the scope to
the chosen destination only: the dungeon, the arrival floor and why it was
chosen.  Every assignment of the voluntary recall target records a reason code
next to it (``_target_dungeon_reason``); the spectator snapshot copies the
target, the dungeon's name from the bot's static knowledge, the recall arrival
floor the bot itself expects and that code.  No decision reads any of it.

Each pin drives the real producer that assigns the target -- the policy
constructor, ``choose_key`` over a recorded board, ``_observe`` or
``_fixed_quest_key`` -- and reads the field out of the real ``SpectatorWriter``
file.  Substrates (each declared):
- tests/fixtures/guardian-recall-pingpong-20260925.jsonl.gz, decided from a
  restarted policy exactly as test_guardian_recall_pingpong_recorded's
  ``_fixed_until_first_recall`` (its P2 departure-count wall included).  The
  recorded decision 1 retargets Angband (recall unlocked), decision 8 takes the
  unsafe-recall fallback to Forest, decision 9 re-applies that alternate;
- NAMED CHANGE for the guardian valve: on the recorded decision-13 board
  Forest's landing is moved onto its own guardian floor 31 (as that module's
  ``ALL_BLOCKED_LANDINGS``), so the recall reader switches through the valve;
- the conquest and quest pins reuse the constructed boards of
  test_policy_quest's DungeonConquestTest and FixedQuestTest;
- the observation's own alternate switches (over-extended dives, guardian
  bounces only, no depth progress) reuse test_policy_observation's
  OverExtensionDungeonSwitchTest dives.
Owner decision 2026-10-25 「ずっと出す」: while an alternate stays the target,
the reason it was switched to is shown, not a generic one
(``_alternate_dungeon_reason``, display-only like the target's reason).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE
from hengbot.policy import EMPTY_DIVE_LIMIT, NO_DEPTH_PROGRESS_DIVE_LIMIT, HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from hengbot.spectator import SpectatorWriter
from tests import test_guardian_recall_pingpong_recorded as pingpong
from tests import test_input_executor as executor_pins
from tests import test_policy_observation as observation_pins
from tests import test_policy_quest as quest_pins
from tests import test_spectator as spectator_pins


def _written(policy, snapshot):
    """The spectator file the real writer produces after this decision."""
    with TemporaryDirectory() as directory:
        path = Path(directory) / "spectate.json"
        writer = SpectatorWriter(path, clock=lambda: 1_000_000.0)
        assert writer.observe(snapshot, "", policy.last_reason, None, None,
                              policy=policy)
        return json.loads(path.read_text(encoding="utf-8"))


def _destination(policy, snapshot):
    return _written(policy, snapshot).get("recall_destination")


class RecordedRecallDestinationTest(unittest.TestCase):
    """Recorded guardian-recall-pingpong boards, decided by a restarted policy."""

    @classmethod
    def setUpClass(cls):
        pingpong.GuardianRecallPingPongRecordedTest.setUpClass()
        cls.source = pingpong.GuardianRecallPingPongRecordedTest

    def setUp(self):
        self.enterContext(pingpong.recorded_equipment_decisions("guardian"))
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def _decide_through(self, last):
        """Decide recorded decisions 0..last; the policy, board and key of ``last``."""
        policy = self.source._new_policy(self.directory)
        for index in range(last + 1):
            board = self.source._consume(policy, index, self.directory)
            with pingpong._pre_p2_departure_count():  # DECLARED WALL (P2)
                key = policy.choose_key(board)
            if index == last:
                return policy, board, key
            policy.confirm_key_posted(key)
        raise AssertionError("unreachable")

    def test_initial_yeek_cave_target_before_any_retarget(self):
        policy, board, _key = self._decide_through(0)
        self.assertEqual(policy.last_reason, "periodic:skill-exp-knowledge")
        destination = _destination(policy, board)
        self.assertEqual(
            destination,
            {
                "dungeon_id": DUNGEON_YEEK_CAVE,
                "dungeon_name": policy._dungeon_knowledge[DUNGEON_YEEK_CAVE].name,
                "depth": policy._dungeon_entry_depth(
                    board, DUNGEON_YEEK_CAVE, via_recall=True),
                "reason": "initial_yeek_cave",
            },
        )
        self.assertEqual(
            destination["depth"], board.dungeon_recall_depths[DUNGEON_YEEK_CAVE])

    def test_angband_recall_unlocked_retargets_angband(self):
        policy, board, _key = self._decide_through(1)
        self.assertTrue(board.angband_recall_unlocked)
        destination = _destination(policy, board)
        self.assertEqual(destination["dungeon_id"], DUNGEON_ANGBAND)
        self.assertEqual(
            destination["dungeon_name"],
            policy._dungeon_knowledge[DUNGEON_ANGBAND].name)
        self.assertEqual(
            destination["depth"],
            policy._dungeon_entry_depth(board, DUNGEON_ANGBAND, via_recall=True))
        self.assertEqual(destination["reason"], "angband_recall_unlocked")

    def test_unsafe_recall_fallback_names_forest_and_its_landing(self):
        policy, board, key = self._decide_through(pingpong.FALLBACK)
        self.assertEqual(
            (key, policy.last_reason),
            ("1", "town:entrance-step-off:town:unsafe-recall-fallback"))
        self.assertEqual(
            _destination(policy, board),
            {
                "dungeon_id": pingpong.FOREST,
                "dungeon_name": policy._dungeon_knowledge[pingpong.FOREST].name,
                "depth": pingpong.FOREST_LANDING,
                "reason": "safe_fallback",
            },
        )

    def test_the_next_observation_reapplies_the_alternate(self):
        # CHANGED 2026-10-25 by owner decision 「ずっと出す」 (own new test of
        # this branch): the re-applied alternate keeps the reason it was
        # switched to (was alternate_dungeon from the next decision on).
        policy, board, _key = self._decide_through(pingpong.FALLBACK + 1)
        destination = _destination(policy, board)
        self.assertEqual(destination["dungeon_id"], pingpong.FOREST)
        self.assertEqual(destination["depth"], pingpong.FOREST_LANDING)
        self.assertEqual(destination["reason"], "safe_fallback")

    def test_guardian_valve_is_told_apart_from_the_safe_fallback(self):
        policy, _board, key = self._decide_through(pingpong.FIRST_RECALL - 1)
        policy.confirm_key_posted(key)
        board = self.source._consume(policy, pingpong.FIRST_RECALL, self.directory)
        # NAMED CHANGE (module docstring): Forest lands on its guardian floor.
        blocked = replace(board, dungeon_recall_depths={
            **board.dungeon_recall_depths, pingpong.FOREST: 31})
        self.assertTrue(policy._guardian_floor_blocked(blocked, pingpong.FOREST, 31))
        with pingpong._pre_p2_departure_count():  # DECLARED WALL (P2)
            policy.choose_key(blocked)
        self.assertEqual(
            policy.last_reason, "town:entrance-step-off:town:unsafe-recall-fallback")
        destination = _destination(policy, blocked)
        self.assertNotEqual(destination["dungeon_id"], pingpong.FOREST)
        self.assertEqual(
            destination["depth"],
            blocked.dungeon_recall_depths[destination["dungeon_id"]])
        self.assertEqual(destination["reason"], "guardian_valve")
        # The next decision's observation re-applies the alternate and keeps
        # the valve's reason (owner decision 「ずっと出す」).
        with pingpong._pre_p2_departure_count():  # DECLARED WALL (P2)
            policy.choose_key(blocked)
        again = _destination(policy, blocked)
        self.assertEqual(again["dungeon_id"], destination["dungeon_id"])
        self.assertEqual(again["reason"], "guardian_valve")


class ObservedAlternateReasonTest(unittest.TestCase):
    """The observation's own alternate switches, on test_policy_observation's boards."""

    def setUp(self):
        self.source = observation_pins.OverExtensionDungeonSwitchTest(
            "test_switches_after_a_run_of_over_extended_dives")

    def test_over_extended_dives_switch_and_keep_their_reason(self):
        policy = self.source._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self.source._run_dive(policy, **self.source.OVEREXTENDED)
        town = self.source._town()
        self.assertEqual(
            _destination(policy, town),
            {"dungeon_id": 3, "dungeon_name": "Orc Cave",
             "depth": policy._dungeon_entry_depth(town, 3, via_recall=True),
             "reason": "over_extended_dives"},
        )
        policy._observe(town)  # the next observation re-applies the alternate
        self.assertEqual(_destination(policy, town)["reason"], "over_extended_dives")

    def test_guardian_bounces_only_switch_through_the_bounce_valve(self):
        policy = self.source._policy()
        policy._conquest_committed = 4
        policy._target_dungeon_id = 4
        for _ in range(EMPTY_DIVE_LIMIT):
            self.source._guardian_bounce(policy, "guardian-kit-insufficient")
        town = self.source._town(conquered=(3, 7, 14), angband_unlocked=False)
        destination = _destination(policy, town)
        self.assertEqual(destination["dungeon_id"], 3)
        self.assertEqual(destination["reason"], "guardian_bounce_valve")

    def test_looted_dives_without_new_depth_switch_for_no_depth_progress(self):
        policy = self.source._policy()
        for _ in range(NO_DEPTH_PROGRESS_DIVE_LIMIT):
            self.source._run_dive(
                policy, loot=4, emergencies=0, level=19, recall_depth=19)
        destination = _destination(policy, self.source._town(recall_depth=19))
        self.assertEqual(destination["dungeon_id"], 7)
        self.assertEqual(destination["reason"], "no_depth_progress")

    def test_restored_alternate_without_its_reason_shows_the_generic_reason(self):
        policy = self.source._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self.source._run_dive(policy, **self.source.OVEREXTENDED)
        del policy._alternate_dungeon_reason  # a state from before the round
        # The fixture's optimizer closure is not picklable; a deep copy runs
        # the same __setstate__ upgrade as an unpickled checkpoint.
        restored = copy.deepcopy(policy)
        self.assertIsNone(restored._alternate_dungeon_reason)
        town = self.source._town()
        restored._observe(town)
        destination = _destination(restored, town)
        self.assertEqual(destination["dungeon_id"], 3)
        self.assertEqual(destination["reason"], "alternate_dungeon")


class ConstructedRecallDestinationTest(unittest.TestCase):
    def test_conquest_target_overrides_angband(self):
        source = quest_pins.DungeonConquestTest(
            "test_targets_beatable_yeek_guardian_even_after_angband_is_unlocked")
        policy = source._yeek_guardian_policy()
        snapshot = replace(
            source._minotaur_snapshot(1),
            entered_dungeon_ids=(1, 2),
            angband_recall_unlocked=True,
        )
        policy._observe(snapshot)
        destination = _destination(policy, snapshot)
        self.assertEqual(destination["dungeon_id"], DUNGEON_YEEK_CAVE)
        self.assertEqual(
            destination["depth"],
            policy._dungeon_entry_depth(snapshot, DUNGEON_YEEK_CAVE, via_recall=True))
        self.assertEqual(destination["reason"], "conquest")

    def test_taken_kill_quest_targets_its_dungeon(self):
        source = quest_pins.FixedQuestTest("test_q14_taken_targets_yeek_for_walk_in_descent")
        policy, snapshot = source._q14_town_fixture(QUEST_STATUS_TAKEN)
        self.assertIsNone(policy._fixed_quest_key(snapshot, []))
        destination = _destination(policy, snapshot)
        self.assertEqual(destination["dungeon_id"], DUNGEON_YEEK_CAVE)
        self.assertEqual(destination["reason"], "quest_dungeon")

    def test_a_target_without_a_known_name_omits_the_name(self):
        policy = HengbotPolicy()
        snapshot = spectator_pins.SpectatorWriterTest._snapshot()
        policy._target_dungeon_id = 999  # no such dungeon in the knowledge
        self.assertEqual(
            _destination(policy, snapshot),
            {"dungeon_id": 999, "depth": 1, "reason": "initial_yeek_cave"})

    def test_no_target_omits_the_field(self):
        policy = HengbotPolicy()
        snapshot = spectator_pins.SpectatorWriterTest._snapshot()
        policy._target_dungeon_id = None
        self.assertNotIn("recall_destination", _written(policy, snapshot))

    def test_checkpoint_saved_before_the_reason_restores_it_as_unknown(self):
        policy = HengbotPolicy()
        snapshot = spectator_pins.SpectatorWriterTest._snapshot()
        del policy._target_dungeon_reason  # a checkpoint from before #47
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertIsNone(restored._target_dungeon_reason)
        destination = _destination(restored, snapshot)
        self.assertEqual(destination["dungeon_id"], DUNGEON_YEEK_CAVE)
        self.assertIsNone(destination["reason"])


class RecallDestinationFollowControlTest(executor_pins.ProductionHarness):
    """Control: the recorded follow replay decides the same with and without the field."""

    def _replay(self, sandbox, **kwargs):
        return spectator_pins.SpectatorFollowReplayTest._replay(self, sandbox, **kwargs)

    def test_keys_and_reasons_are_identical_with_and_without_the_field(self):
        with TemporaryDirectory() as with_dir, TemporaryDirectory() as without_dir:
            result, keys, rows, _recorded, _game = self._replay(
                Path(with_dir), spectate=True)
            with_file = json.loads(
                (Path(with_dir) / "spectate.json").read_text(encoding="utf-8"))
            with patch("hengbot.spectator.spectator_recall_destination",
                       return_value=None):
                bare_result, bare_keys, bare_rows, _recorded, _game = self._replay(
                    Path(without_dir), spectate=True)
            without_file = json.loads(
                (Path(without_dir) / "spectate.json").read_text(encoding="utf-8"))
        self.assertIn("recall_destination", with_file)
        self.assertNotIn("recall_destination", without_file)
        decided = spectator_pins.SpectatorFollowReplayTest._decided
        self.assertEqual(result, bare_result)
        self.assertEqual(keys, bare_keys)
        self.assertEqual(decided(rows), decided(bare_rows))
        self.assertEqual(len(decided(rows)), spectator_pins.REPLAYED)


if __name__ == "__main__":
    unittest.main()
