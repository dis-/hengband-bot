"""The skipped fixed quests and the per-instance strategy profile (strategy_profile, 2026-11-26).

Owner 2026-11-26 「2度勝利したので戦略を変える。…いずれも、ゲーム内選択に関して私の以前の指示を破ることを
許可する。」; the supervisor's decision: every character skipped Q18 and Q33 by default.  Since
2026-11-27 (n1-c's 8 hours at 49F without Q25's telepathy) no quest is skipped by default (whether
a quest is worth taking is quest_value's, tests/test_quest_value.py), and an instance's
``strategy-profile.json`` (beside its lives: ``~/hengbot-soak/<instance>/strategy-profile.json``)
may skip more.  These drive the real consumers -- the fixed-quest head, the acceptance at the quest
building, a taken skipped quest that must not serialize the next acceptance, the town's quest
supplies (``_quest_strategy_for_errand_or_floor``), the Q2 hold of Angband -- with the default
profile against the all-quests profile the rest of the suite runs with (tests/__init__.py).
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import quest_one_turn_kill, random_quest_hold, strategy_profile
from hengbot.flight_recorder import append_session_marker
from hengbot.model import PLAYER_CLASS_WARRIOR, Position, QuestState, Snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    FIXED_QUEST_ALLOWLIST, QUEST_STATUS_FINISHED, QUEST_STATUS_TAKEN, QUEST_STATUS_UNTAKEN,
)
from hengbot.quest_knowledge import QuestInfo, find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.town_maps import TownMap
from policy_fixtures import grid, player

ROOT = Path(__file__).resolve().parents[1]
REAL_QUESTS = load_quest_knowledge(find_quest_definitions(Path(__file__)))
REAL_STRATEGIES = load_quest_strategies(ROOT / "strategy" / "quests")

# The building (26, 98) of the town map offers the quest of building_special.
BUILDING = Position(26, 98)


def _quest(quest_id: int, status: int) -> QuestState:
    info = REAL_QUESTS[quest_id]
    return QuestState(id=quest_id, name=info.name, status=status, type=info.type,
                      level=info.level, flags=info.flags, fixed=True)


def _town_map(quest_id: int) -> TownMap:
    return TownMap(
        name="Outpost", width=198, height=66,
        walkable=frozenset(Position(y, x) for y in range(66) for x in range(198)),
        quest_buildings={quest_id: frozenset({BUILDING})},
        quest_entrances={quest_id: frozenset({Position(35, 177)})},
        reward_positions=frozenset({Position(27, 98)}),
    )


def _town_board(offered: int, quests: dict[int, QuestState]) -> Snapshot:
    # Every other allowlisted quest is done, so the head is one of ``quests``.
    quests = {**{quest_id: _quest(quest_id, QUEST_STATUS_FINISHED)
                 for quest_id in FIXED_QUEST_ALLOWLIST}, **quests}
    grids = {
        Position(26, 97): grid(26, 97),
        BUILDING: grid(26, 98, building_type=1, building_special=offered),
    }
    return Snapshot(
        player(26, 97, level=30, class_id=PLAYER_CLASS_WARRIOR), grids, [],
        floor_key=(0, 0, 0), width=198, height=66, town_flag=True, town_id=0,
        town_index=1, quests=quests,
    )


def _policy(offered: int, profile) -> HengbotPolicy:
    policy = HengbotPolicy(_town_map(offered), quest_knowledge=REAL_QUESTS,
                           quest_strategies=REAL_STRATEGIES)
    policy._instance_profile = profile
    policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
    return policy


class SkippedQuestAcceptanceTest(unittest.TestCase):
    """The castle never takes a skipped quest; a taken one serializes nothing."""

    def test_offered_q33_is_requested_only_when_not_skipped(self):
        # Q33 skipped by the instance's profile (no quest is skipped by default since 2026-11-27).
        board = _town_board(33, {33: _quest(33, QUEST_STATUS_UNTAKEN)})
        # Q33's one-turn-kill line (quest_one_turn_kill) is not what is tested here.
        patcher = patch.object(quest_one_turn_kill, "holds_back", lambda *_args: False)
        patcher.start()
        self.addCleanup(patcher.stop)

        played = _policy(33, strategy_profile.ALL_FIXED_QUESTS)
        self.assertEqual(played._fixed_quest_target(board), 33)
        self.assertEqual(played.choose_key(board), "6q\x1b")
        self.assertEqual(played.last_reason, "fixedquest:request")

        skipped = _policy(33, strategy_profile.parse({"skip_quests": [33]}))
        self.assertIsNone(skipped._fixed_quest_head(board))
        self.assertIsNone(skipped._fixed_quest_target(board))
        self.assertIsNone(skipped._fixed_quest_key(board, []))
        self.assertNotIn(33, skipped._known_fixed_quests(board))
        self.assertIsNone(skipped.approved_quest_strategy(33))
        self.assertIsNotNone(played.approved_quest_strategy(33))

    def test_offered_q18_and_q25_are_requested_by_default(self):
        # 2026-11-27: Q25 (its reward the telepathy of the 50F gate) is offered only after Q18.
        for quest_id in (18, 25):
            board = _town_board(quest_id, {quest_id: _quest(quest_id, QUEST_STATUS_UNTAKEN)})
            played = _policy(quest_id, strategy_profile.ALL_FIXED_QUESTS)
            self.assertEqual(played._fixed_quest_target(board), quest_id)
            self.assertIsNotNone(played.approved_quest_strategy(quest_id))
            skipping = _policy(quest_id, strategy_profile.parse({"skip_quests": [18, 25]}))
            self.assertIsNone(skipping._fixed_quest_target(board))

    def test_taken_skipped_quest_neither_serializes_nor_is_entered(self):
        # A taken fixed quest holds every other acceptance (_build_fixed_quest_head); a taken
        # skipped one is ignored, and the offered Q31 is taken in its place.
        quests = {33: _quest(33, QUEST_STATUS_TAKEN), 31: _quest(31, QUEST_STATUS_UNTAKEN)}
        board = _town_board(31, quests)

        played = _policy(31, strategy_profile.ALL_FIXED_QUESTS)
        self.assertEqual(played._fixed_quest_target(board), 33)

        skipped = _policy(31, strategy_profile.parse({"skip_quests": [33]}))
        self.assertEqual(skipped._fixed_quest_target(board), 31)
        self.assertIsNone(skipped._fixed_quest_enter_key(board, 33))

    def test_taken_skipped_quest_asks_no_town_supplies(self):
        # The town's quest supplies and loadout (retention, carry, purchases) read the quest
        # being prepared here: a taken Q33 has none when skipped.
        board = _town_board(31, {33: _quest(33, QUEST_STATUS_TAKEN)})

        played = _policy(31, strategy_profile.ALL_FIXED_QUESTS)
        self.assertEqual(played._quest_strategy_for_errand_or_floor(board).quest_id, 33)
        skipped = _policy(31, strategy_profile.parse({"skip_quests": [33]}))
        self.assertIsNone(skipped._quest_strategy_for_errand_or_floor(board))
        self.assertFalse(skipped._fixed_quest_prepare_return_required(board))

    def test_win_and_random_quests_are_never_skipped(self):
        profile = strategy_profile.parse({"skip_quests": [8, 9, 41],
                                          "skip_all_optional_fixed_quests_from_level": 1})
        for quest_id in (8, 9, 41, 44):
            self.assertFalse(strategy_profile.quest_skipped(profile, quest_id, REAL_QUESTS[quest_id]),
                             quest_id)
        self.assertTrue(strategy_profile.quest_skipped(profile, 1, REAL_QUESTS[1]))


class ProfileFileTest(unittest.TestCase):
    """strategy-profile.json beside the lives, the environment's file, and a bad file."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.instance = Path(self._directory.name) / "n1-a"
        self.decision_log = self.instance / "life-540" / "jsonlog" / "bot-decisions.jsonl"
        self.decision_log.parent.mkdir(parents=True)
        strategy_profile._CACHE.clear()

    def tearDown(self):
        strategy_profile._CACHE.clear()
        self._directory.cleanup()

    def _write(self, text: str, path: Path | None = None) -> Path:
        path = path or self.instance / strategy_profile.PROFILE_FILE_NAME
        path.write_text(text, encoding="utf-8")
        return path

    def test_no_file_is_the_default_skip_set(self):
        profile = strategy_profile.for_run(self.decision_log, environ={})
        self.assertIs(profile, strategy_profile.DEFAULT_PROFILE)
        self.assertEqual(profile.skipped_quests, frozenset())

    def test_instance_profile_adds_q25_and_the_castle_never_takes_it(self):
        path = self._write(json.dumps({"name": "n1-a-free", "skip_quests": [25],
                                       "a_later_key": {"x": 1}}))

        profile = strategy_profile.for_run(self.decision_log, environ={})
        self.assertEqual(profile.name, "n1-a-free")
        self.assertEqual(profile.source, str(path))
        self.assertEqual(profile.skipped_quests, frozenset({25}))
        self.assertEqual(profile.warnings, ())

        board = _town_board(25, {25: _quest(25, QUEST_STATUS_UNTAKEN)})
        self.assertEqual(_policy(25, strategy_profile.ALL_FIXED_QUESTS)._fixed_quest_target(board), 25)
        skipped = _policy(25, profile)
        self.assertIsNone(skipped._fixed_quest_target(board))
        self.assertIsNone(skipped.approved_quest_strategy(25))

    def test_a_life_directory_file_wins_over_the_instance_file(self):
        self._write(json.dumps({"name": "instance"}))
        self._write(json.dumps({"name": "life"}), self.decision_log.parent.parent / "strategy-profile.json")
        self.assertEqual(strategy_profile.for_run(self.decision_log, environ={}).name, "life")

    def test_environment_names_the_file(self):
        self._write(json.dumps({"name": "instance"}))
        named = self._write(json.dumps({"name": "named", "skip_quests": [31]}),
                            Path(self._directory.name) / "other.json")
        profile = strategy_profile.for_run(
            self.decision_log, environ={strategy_profile.PROFILE_ENV: str(named)})
        self.assertEqual((profile.name, 31 in profile.skipped_quests), ("named", True))

    def test_runtime_directory_stands_in_for_a_missing_decision_log(self):
        self._write(json.dumps({"name": "instance"}))
        profile = strategy_profile.for_run(
            None, environ={strategy_profile.RUNTIME_DIR_ENV: str(self.decision_log.parent)})
        self.assertEqual(profile.name, "instance")

    def test_level_threshold_skips_every_optional_fixed_quest_at_or_above_it(self):
        self._write(json.dumps({"skip_all_optional_fixed_quests_from_level": 22}))
        profile = strategy_profile.for_run(self.decision_log, environ={})
        policy = _policy(31, profile)

        skipped = {quest_id for quest_id in (1, 2, 14, 18, 22, 25, 28, 31, 32, 33, 34)
                   if policy.fixed_quest_skipped(quest_id)}
        # Q31 (level 22), Q32 (25), Q18 (35), Q33 (45), Q25 (48), Q28 (70).
        self.assertEqual(skipped, {18, 25, 28, 31, 32, 33})
        board = _town_board(31, {31: _quest(31, QUEST_STATUS_UNTAKEN)})
        self.assertIsNone(policy._fixed_quest_target(board))
        self.assertFalse(policy.fixed_quest_skipped(8))
        self.assertFalse(policy.fixed_quest_skipped(45))  # a random quest of level 38

    def test_malformed_file_is_the_defaults_with_a_warning(self):
        self._write("{ not json")
        profile = strategy_profile.for_run(self.decision_log, environ={})
        self.assertEqual(profile.skipped_quests, frozenset())
        self.assertIsNone(profile.skip_from_level)
        self.assertEqual(len(profile.warnings), 1)
        self.assertIn("malformed JSON", profile.warnings[0])
        self.assertIn("warnings", profile.summary())

    def test_wrong_types_fall_back_key_by_key(self):
        self._write(json.dumps({"name": 3, "skip_quests": "25",
                                "skip_all_optional_fixed_quests_from_level": "20"}))
        profile = strategy_profile.for_run(self.decision_log, environ={})
        self.assertEqual((profile.name, profile.skipped_quests, profile.skip_from_level),
                         ("default", frozenset(), None))
        self.assertEqual(len(profile.warnings), 3)
        self._write(json.dumps([25]), Path(self._directory.name) / "list.json")
        listed = strategy_profile.load(Path(self._directory.name) / "list.json")
        self.assertEqual(listed.skipped_quests, frozenset())
        self.assertTrue(listed.warnings)

    def test_session_marker_logs_the_profile_once(self):
        self._write(json.dumps({"name": "n1-a-free", "skip_quests": [25]}))
        profile = strategy_profile.for_run(self.decision_log, environ={})
        append_session_marker(self.decision_log, ["hengbot"], strategy_profile=profile.summary())
        record = json.loads(self.decision_log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["strategy_profile"]["name"], "n1-a-free")
        self.assertEqual(record["strategy_profile"]["skipped_quests"], [25])


class SkippedQ2ReleasesTheAngbandHoldTest(unittest.TestCase):
    """The Q2 hold of Angband (random_quest_hold) waits for Q2; a skipped Q2 holds nothing."""

    def test_skipped_q2_releases_the_hold(self):
        board = replace(_town_board(2, {2: _quest(2, QUEST_STATUS_UNTAKEN)}))
        played = _policy(2, strategy_profile.ALL_FIXED_QUESTS)
        self.assertTrue(random_quest_hold.hold_active(board, played))
        skipping = _policy(2, strategy_profile.parse({"skip_quests": [2]}))
        self.assertFalse(random_quest_hold.hold_active(board, skipping))
        self.assertFalse(random_quest_hold.entry_refused(board, random_quest_hold.DUNGEON_ANGBAND,
                                                         skipping))


if __name__ == "__main__":
    unittest.main()
