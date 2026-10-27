"""#47 / #84: unchanged captured boards through public choose_key.

DECLARED CONSTRUCTED: captures contain only the tail of a long session.
Reconstruct completed opening/hold and cleared fixed source placements;
provide an unrelated skill-knowledge response so bookkeeping does not hide
quest movement. No movement, visibility, monster or inventory field is changed
in the recorded pins. Explicit replace variants below are boundary controls.
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate live runtime files
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.quest_strategies import load_quest_strategies

ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = ROOT / "tests/fixtures/quest-sweep-hold-20261027.json.gz"


class QuestSweepHoldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = {case["quest_id"]: case for case in json.load(stream)}
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.quests = load_quest_knowledge(EDIT / "quests")
        cls.profiles = load_quest_strategies(ROOT / "strategy/quests")

    def board(self, quest_id, sequence):
        row = next(row for row in self.cases[quest_id]["rows"]
                   if row["decision"]["decision_sequence"] == sequence)
        return parse_snapshot(row["board"], self.monraces)

    def policy(self, board, *, hold_complete=True, post_wave=None):
        qid = board.floor_key[2]
        profile = self.profiles[qid]
        policy = HengbotPolicy(quest_knowledge={qid: self.quests[qid]},
                               quest_strategies={qid: profile},
                               monrace_knowledge=self.monraces)
        policy.prime(board)
        policy.consume_skill_knowledge({
            "player": {"level": board.player.level},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        policy._quest_strategy_initial_hold_turns[qid] = (
            profile.engagement_plan["initial_hold_turns"] if hold_complete else 0
        )
        # Measured certificates accumulated on earlier no-enemy sweep boards
        # in the same capture (not a fabricated set of empty placements).
        policy._quest_strategy_surveyed_placements[qid] = {
            Position(*raw) for raw in self.cases[qid]["surveyed_before_rows"]
        }
        if post_wave if post_wave is not None else qid == 31:
            policy._quest_strategy_post_wave_light_attempted.add(qid)
        if qid == 31:
            policy._quest_strategy_cleared_targets[qid] = {
                (int(plan["race_id"]), *plan["target"])
                for plan in profile.engagement_plan["throwing_points"]
            }
        if qid == 22:
            policy._quest_strategy_opening_phase[qid] = 3
            policy._quest_strategy_hold_positions[qid] = Position(9, 58)
        return policy

    def decide(self, policy, board):
        key = policy.choose_key(board)
        return str(key), policy.last_reason

    def test_q31_recorded_sweep_does_not_reverse_for_distant_huorn(self):
        for sequence, expected_key in ((26621, "6"), (26622, "8"),
                                        (26623, "6"), (26624, "8")):
            with self.subTest(sequence=sequence):
                board = self.board(31, sequence)
                policy = self.policy(board)
                key, reason = self.decide(policy, board)
                # On the arrival board the own cell is finally confirmed;
                # continue north to the next target instead of retreating west.
                self.assertEqual((key, reason),
                                 (expected_key, "quest-strategy:placement-sweep"))

    def test_q22_recorded_fleeing_orc_is_followed_before_light_point(self):
        for sequence in (15413, 15415):
            with self.subTest(sequence=sequence):
                board = self.board(22, sequence)
                policy = self.policy(board)
                self.assertNotIn(22, policy._quest_strategy_post_wave_light_attempted)
                self.assertEqual(self.decide(policy, board),
                                 ("4", "quest-strategy:sweep-engage-mobile"))

    def test_q22_recorded_empty_hold_can_start_sweep(self):
        for sequence in (15412, 15414, 15416):
            board = self.board(22, sequence)
            policy = self.policy(board)
            self.assertEqual(self.decide(policy, board),
                             ("4", "quest-strategy:placement-sweep"))

    def test_recorded_targets_really_are_unconfirmed(self):
        for qid, sequence, target in ((31, 26621, Position(3, 16)),
                                      (22, 15412, Position(9, 55))):
            board = self.board(qid, sequence)
            policy = self.policy(board)
            self.assertFalse(policy._quest_cell_confirmed_empty(board, target))
            self.assertFalse(board.grid_at(target).in_view)
        self.assertFalse(self.board(31, 26621).grid_at(Position(3, 16)).allows_los)
        board = self.board(22, 15412)
        self.assertGreater(board.player.position.distance_to(Position(9, 55)),
                           board.light_radius)

    def test_q22_recorded_ranged_enemy_still_gets_shot(self):
        board = self.board(22, 15411)
        policy = self.policy(board)
        row = self.cases[22]["rows"][0]
        self.assertEqual(self.decide(policy, board),
                         (row["decision"]["key"], "quest-strategy:ranged-fire"))

    def test_q22_active_mobile_enemy_still_retakes_hold(self):
        # DECLARED CONSTRUCTED: remove fear from the recorded fleeing orc.
        board = self.board(22, 15413)
        board = replace(board, visible_monsters=[
            replace(monster, fearful=False) for monster in board.visible_monsters
        ])
        policy = self.policy(board)
        self.assertEqual(self.decide(policy, board),
                         ("6", "quest-strategy:retake-hold"))

    def test_incomplete_opening_hold_still_retakes_position(self):
        # DECLARED CONSTRUCTED: same board, opening quiet budget not completed.
        for qid, sequence, key in ((31, 26622, "4"), (22, 15413, "6")):
            board = self.board(qid, sequence)
            policy = self.policy(board, hold_complete=False, post_wave=False)
            self.assertEqual(self.decide(policy, board),
                             (key, "quest-strategy:retake-hold"))

    def test_no_sweep_profile_still_retakes_hold(self):
        # DECLARED CONSTRUCTED: disable sweep in a copy, never edit approved data.
        board = self.board(31, 26622)
        policy = self.policy(board)
        profile = self.profiles[31]
        policy._quest_strategies[31] = replace(profile, engagement_plan={
            **profile.engagement_plan, "placement_sweep": False,
        })
        self.assertEqual(self.decide(policy, board),
                         ("4", "quest-strategy:retake-hold"))

    def test_missing_battlefield_does_not_reverse_an_allowed_sweep(self):
        # DECLARED CONSTRUCTED: map metadata unavailable on a resumed board.
        # The strategy fallback can hold here, but must not change its answer
        # about returning to the entrance just because no sweep route exists.
        board = self.board(31, 26622)
        policy = self.policy(board)
        policy._quest_knowledge[31] = replace(self.quests[31], battlefield=None)
        key = policy._quest_execute_key(board, board.visible_monsters, [])
        self.assertEqual((key, policy.last_reason), ("5", "quest-strategy:hold"))

    def test_sweep_route_avoids_a_visible_stationary_enemy_halo(self):
        # DECLARED CONSTRUCTED: move the observed Huorn near the sweep goal.
        board = self.board(31, 26621)
        monster = self.board(31, 26622).visible_monsters[0]
        board = replace(board, visible_monsters=[replace(
            monster, position=Position(4, 17), distance=2,
        )])
        policy = self.policy(board)
        key, reason = self.decide(policy, board)
        self.assertEqual((key, reason), ("2", "quest-strategy:placement-sweep"))

    def test_exhausted_sweep_does_not_resume_exploration_into_enemy_halo(self):
        # DECLARED CONSTRUCTED: a later survey round on the same board, with
        # all coverage certificates and a pending ordinary exploration step.
        # A Huorn has moved next to that committed step since it was planned.
        board = self.board(31, 26621)
        monster = self.board(31, 26622).visible_monsters[0]
        board = replace(board, visible_monsters=[replace(
            monster, position=Position(4, 17), distance=2,
        )])
        policy = self.policy(board)
        navigator = QuestFloorNavigator(31, self.quests[31].battlefield)
        policy._quest_strategy_surveyed_placements[31] = {
            Position(y, x) for y, x in navigator.battlefield.terrain
            if navigator._static_walkable(Position(y, x))
        }
        policy._quest_strategy_sweep_rounds[31] = self.profiles[31].engagement_plan[
            "max_sweep_rounds"
        ]
        policy._explore_path = [Position(3, 16)]
        self.assertEqual(self.decide(policy, board),
                         ("5", "quest:blocked:placement-sweep-exhausted"))


if __name__ == "__main__":
    unittest.main()
