"""#47: voluntary Forest destinations are excluded at one shared authority.

DECLARED CONSTRUCTED: small two-entrance surface boards exercise the public
choose_key, followed by the production OperationExecutor with a faithful fake
game (no running game connection). Before controls remove only the exclusion,
which reproduces the pre-change destination policy. The recorded recall pins
reuse guardian-recall-pingpong's retained inputs and declared equipment/P2
walls; no decision producer is mocked.
"""
import tests  # noqa: F401 -- isolate runtime files

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.input_executor import Operation
from hengbot.model import (
    Snapshot, Position, TVAL_FOOD, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
)
from hengbot.policy import HengbotPolicy, NO_DEPTH_PROGRESS_DIVE_LIMIT
from hengbot.spectator import spectator_recall_destination
from policy_fixtures import player, grid, item
from tests.test_input_executor import ProductionHarness, command_screen
from tests import test_guardian_recall_pingpong_recorded as recorded

FOREST = 7
ABILITIES = frozenset({
    "free_action", "resist_conf", "resist_fire", "resist_pois",
    "resist_cold", "resist_elec", "resist_acid", "resist_chaos",
})


class ExcludeForestTest(ProductionHarness):
    def _policy(self):
        return HengbotPolicy(dungeon_knowledge={
            1: DungeonInfo(1, "Angband", 1, 127, 30),
            2: DungeonInfo(2, "Yeek cave", 1, 13, 1),
            3: DungeonInfo(3, "Orc cave", 10, 23, 5),
            7: DungeonInfo(7, "Forest", 15, 32, 5),
        })

    def _board(self):
        return Snapshot(
            player(10, 10, abilities=ABILITIES),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, entrance=True,
                                      entrance_dungeon_id=7),
                Position(10, 9): grid(10, 9),
                Position(10, 8): grid(10, 8, entrance=True,
                                     entrance_dungeon_id=2),
            }, [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10),
                       item("f", TVAL_FOOD, 35, count=10)],
            entered_dungeon_ids=(1, 3, 7), conquered_dungeon_ids=(3, 7),
            dungeon_recall_depths={1: 40, 3: 10, 7: 24},
        )

    def _post(self, key, reason):
        game, _client, executor = self.make()
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome,
                         "ready")
        game.screens = [command_screen(3)]
        result = executor.submit(Operation(47, reason, key, executor.ready_board),
                                 deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, [str(key)])

    def test_public_main_target_and_committed_target_leave_forest(self):
        for committed in (False, True):
            for before, expected in ((True, 7), (False, 3)):
                with self.subTest(committed=committed, before=before):
                    policy = self._policy()
                    if committed:
                        policy._conquest_committed = 7
                    board = replace(self._board(), conquered_dungeon_ids=())
                    with patch("hengbot.dungeon_knowledge.EXCLUDED_EXPLORATION_DUNGEONS",
                               frozenset() if before else frozenset({7})):
                        key = policy.choose_key(board)
                    self.assertEqual(policy._target_dungeon_id, expected)
                    self.assertEqual(policy._conquest_committed, expected)
                    self.assertEqual(spectator_recall_destination(policy, board)["dungeon_id"],
                                     expected)
                    self._post(key, policy.last_reason)

    def test_public_level_fit_switch_uses_another_landing(self):
        for before, expected in ((True, 7), (False, 3)):
            with self.subTest(before=before):
                policy = self._policy()
                policy._no_depth_progress_dives = NO_DEPTH_PROGRESS_DIVE_LIMIT
                board = replace(self._board(), angband_recall_unlocked=True,
                                recall_dungeon_id=1, recall_depth=40)
                with patch("hengbot.dungeon_knowledge.EXCLUDED_EXPLORATION_DUNGEONS",
                           frozenset() if before else frozenset({7})):
                    key = policy.choose_key(board)
                self.assertEqual(policy._alternate_dungeon, expected)
                self.assertEqual(policy._target_dungeon_id, expected)
                self.assertEqual(policy._dungeon_entry_depth(board, expected, via_recall=True),
                                 board.dungeon_recall_depths[expected])
                self._post(key, policy.last_reason)

    def test_public_walking_discards_saved_forest_target_and_routes_left(self):
        for before, expected, key_expected in ((True, 7, "6"), (False, 2, "4")):
            with self.subTest(before=before):
                policy = self._policy()
                policy._alternate_dungeon = 7
                policy._target_dungeon_id = 7
                board = replace(self._board(), entered_dungeon_ids=(1, 7))
                with patch("hengbot.dungeon_knowledge.EXCLUDED_EXPLORATION_DUNGEONS",
                           frozenset() if before else frozenset({7})):
                    key = policy.choose_key(board)
                self.assertEqual((key, policy.last_reason),
                                 (key_expected, "seek-downstairs"))
                self.assertEqual(policy._active_dungeon_target(), expected)
                self.assertEqual(policy._descent_target_goal,
                                 Position(10, 12 if before else 8))
                self._post(key, policy.last_reason)

    def test_public_inside_forest_and_saved_recall_do_not_reselect_it(self):
        for inside in (False, True):
            policy = self._policy()
            policy._alternate_dungeon = 7
            policy._target_dungeon_id = 7
            board = replace(self._board(), recall_dungeon_id=7, recall_depth=24,
                            floor_key=(7, 24, 0) if inside else (0, 0, 0),
                            town_flag=not inside)
            key = policy.choose_key(board)
            self.assertEqual(policy._target_dungeon_id, 3)
            self.assertEqual(policy._alternate_dungeon, 3)
            # Forest's saved 24F must not leak into the Yeek recall depth.
            self.assertEqual(policy._dungeon_entry_depth(board, 2, via_recall=True), 1)
            self._post(key, policy.last_reason)

    def test_saved_exclusion_uses_safe_deeper_candidate_without_progress_bound(self):
        for retained in ("_target_dungeon_id", "_alternate_dungeon", "_conquest_committed"):
            with self.subTest(retained=retained):
                policy = self._policy()
                setattr(policy, retained, FOREST)
                # Excluding a destination says nothing about excessive depth.
                # Orc 25F is safe here even though Forest's saved landing is 24F
                # and the progress watermark has never been set.
                board = replace(self._board(), recall_dungeon_id=7, recall_depth=24,
                                dungeon_recall_depths={1: 40, 3: 25, 7: 24})
                key = policy.choose_key(board)
                self.assertEqual(policy._target_dungeon_id, 3)
                self.assertEqual(policy._alternate_dungeon, 3)
                self.assertEqual(policy._target_dungeon_reason, "safe_fallback")
                self._post(key, policy.last_reason)

    def test_recall_chooser_rejects_exclusion_even_without_optional_safety_gates(self):
        policy = self._policy()
        board = self._board()
        policy._target_dungeon_id = 7
        for safety in (False, True):
            for guardian in (False, True):
                self.assertIsNone(policy._town_recall_destination(
                    board, safety_gate=safety, guardian_gate=guardian)[0])

    def test_fundraising_modes_keep_the_existing_yeek_destination(self):
        # Mining/scavenging already select only Yeek Cave. They never selected
        # Forest before this change; controls pin that fact instead of inventing
        # a Forest fundraising chooser.
        for mode in ("mine", "scavenge"):
            policy = self._policy()
            policy._fundraising_mode = mode
            policy._target_dungeon_id = 7
            policy._alternate_dungeon = 7
            board = self._board()
            key = policy.choose_key(board)
            self.assertEqual(policy._active_dungeon_target(), 2)
            self.assertNotEqual(policy._target_dungeon_id, 7)
            self._post(key, policy.last_reason)


class RecordedForestRecallTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        recorded.GuardianRecallPingPongRecordedTest.setUpClass()
        cls.source = recorded.GuardianRecallPingPongRecordedTest

    def test_public_recall_and_spectator_use_new_destination_and_its_own_depth(self):
        for before in (True, False):
            with self.subTest(before=before), TemporaryDirectory() as directory:
                directory = Path(directory)
                with recorded.recorded_equipment_decisions("guardian"), patch(
                    "hengbot.dungeon_knowledge.EXCLUDED_EXPLORATION_DUNGEONS",
                    frozenset() if before else frozenset({7}),
                ):
                    policy = self.source._new_policy(directory)
                    for index in range(recorded.FIRST_RECALL + 1):
                        board = self.source._consume(policy, index, directory)
                        with recorded._pre_p2_departure_count():  # DECLARED WALL (P2)
                            key = policy.choose_key(board)
                        if index < recorded.FIRST_RECALL:
                            policy.confirm_key_posted(key)
                    target = policy._target_dungeon_id
                    if before:
                        self.assertEqual(target, 7)
                    else:
                        self.assertNotEqual(target, 7)
                    self.assertEqual(policy.last_reason, "town:recall-to-alt-dungeon")
                    self.assertEqual(key, "rf" + policy._recall_selection_key(board, target))
                    destination = spectator_recall_destination(policy, board)
                    self.assertEqual(destination["dungeon_id"], target)
                    self.assertEqual(destination["depth"], board.dungeon_recall_depths[target])
                    self.assertEqual(destination["reason"], "safe_fallback")
                    # Production follow executor, using only a fake control peer.
                    ExcludeForestTest._post(self, key, policy.last_reason)

    def test_public_forest_only_fallback_uses_existing_guardian_no_destination_stop(self):
        from hengbot.cli import _policy_final_stop_required

        for before in (True, False):
            with self.subTest(before=before), TemporaryDirectory() as directory:
                directory = Path(directory)
                with recorded.recorded_equipment_decisions("guardian"), patch(
                    "hengbot.dungeon_knowledge.EXCLUDED_EXPLORATION_DUNGEONS",
                    frozenset() if before else frozenset({7}),
                ):
                    policy = self.source._new_policy(directory)
                    for index in range(recorded.FIRST_RECALL + 1):
                        board = self.source._consume(policy, index, directory)
                        if index == recorded.FIRST_RECALL:
                            # NAMED CHANGE: the blocked Orc guardian landing
                            # is latched and Forest is the only fallback.
                            board = replace(board, entered_dungeon_ids=(1, 3, 7))
                            policy._alternate_dungeon = 3
                            policy._target_dungeon_id = 3
                            policy._conquest_committed = None
                        with recorded._pre_p2_departure_count():  # DECLARED WALL (P2)
                            key = policy.choose_key(board)
                        if index < recorded.FIRST_RECALL:
                            policy.confirm_key_posted(key)
                    if before:
                        self.assertEqual(policy._alternate_dungeon, 7)
                    else:
                        self.assertNotEqual(policy._alternate_dungeon, 7)
                        self.assertEqual(policy.last_reason,
                                         "town:blocked:guardian-bounce-no-alternate")
                        # The production follow driver stops before posting a
                        # key, so this cannot start another guardian round trip.
                        self.assertTrue(_policy_final_stop_required(policy))
                        policy.choose_key(board)
                        self.assertEqual(policy.last_reason,
                                         "town:blocked:guardian-bounce-no-alternate")
