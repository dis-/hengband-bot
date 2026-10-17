"""Recorded replay for the Q31 survey-throw-point / placement-sweep loop."""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation for bare module runs
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = ROOT / "tests/fixtures/q31-survey-sweep-20261018.jsonl.gz"
SURVEY = "quest-strategy:survey-throw-point"
SWEEP = "quest-strategy:placement-sweep"
CLEARED = "quest-strategy:survey-target-cleared"
RECOVER = "quest-strategy:recover-defeated-target-torches"
LOOP_SEQUENCES = tuple(range(105, 124))
TARGET_6_4 = (329, 6, 4)
TARGET_3_3 = (329, 3, 3)


def captured_rows() -> tuple[dict, list[dict]]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    return rows[0], rows[1:]


class Q31SurveySweepRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quest = load_quest_knowledge(EDIT / "quests")[31]
        cls.monraces = load_monrace_knowledge(
            EDIT / "MonraceDefinitions.jsonc"
        )
        cls.profile = load_quest_strategies(ROOT / "strategy/quests")[31]
        cls.knowledge, cls.rows = captured_rows()

    def policy(self) -> HengbotPolicy:
        # The capture is a whole restarted run (decision 1 retakes the hold),
        # so a fresh policy plus the run's one ~f knowledge answer is the
        # recorded starting state.
        policy = HengbotPolicy(
            quest_knowledge={31: self.quest},
            quest_strategies={31: self.profile},
            monrace_knowledge=self.monraces,
        )
        policy.consume_skill_knowledge(self.knowledge)
        return policy

    def snapshot(self, row):
        return parse_snapshot(row["board"], self.monraces)

    def decide(self, policy, snapshot):
        policy.prime(snapshot)
        key = policy.choose_key(snapshot)
        return key, policy.last_reason

    def test_recorded_alternation_no_longer_reverses(self):
        self.assertEqual(len(self.rows), 141)
        recorded = {row["decision_sequence"]: row for row in self.rows}
        # The capture records the survey/sweep reversal on consecutive boards.
        self.assertEqual(
            [recorded[sequence]["key"] for sequence in LOOP_SEQUENCES],
            ["2", "8"] * 9 + ["2"],
        )
        self.assertEqual(
            [recorded[sequence]["reason"] for sequence in LOOP_SEQUENCES],
            [SURVEY, SWEEP] * 9 + [SURVEY],
        )

        policy = self.policy()
        replayed = {}
        for row in self.rows:
            snapshot = self.snapshot(row)
            key, reason = self.decide(policy, snapshot)
            replayed[row["decision_sequence"]] = (
                key,
                reason,
                snapshot.player.position,
                set(policy._quest_strategy_cleared_targets.get(31, ())),
            )

        # The first certified-empty target is recorded where it is seen
        # instead of walking to a stand beyond the light radius.
        self.assertEqual(replayed[99][2], Position(5, 1))
        self.assertEqual(replayed[99][1], CLEARED)
        self.assertIn(TARGET_3_3, replayed[99][3])
        self.assertEqual(replayed[101][2], Position(6, 2))
        self.assertEqual(replayed[101][1], CLEARED)
        self.assertIn(TARGET_6_4, replayed[101][3])

        # Replaying the boards of the recorded loop gives one direction
        # (north, to the bolt left on the (6,4) recovery lane) on both cells.
        positions = [replayed[sequence][2] for sequence in LOOP_SEQUENCES]
        self.assertEqual(
            positions, [Position(8, 4), Position(9, 4)] * 9 + [Position(8, 4)]
        )
        loop = [
            replayed[sequence][:2] for sequence in LOOP_SEQUENCES
            if replayed[sequence][1] != "nav:break-oscillation"
        ]
        self.assertGreaterEqual(len(loop), len(LOOP_SEQUENCES) - 1)
        self.assertEqual(set(loop), {("8", RECOVER)})

    def test_survey_still_steps_toward_stand_for_an_occupied_target(self):
        policy = self.policy()
        by_sequence = {row["decision_sequence"]: row for row in self.rows}
        # Boards 1-98 replay identically before and after the change.
        for row in self.rows:
            if row["decision_sequence"] > 98:
                break
            self.decide(policy, self.snapshot(row))
        board = self.snapshot(by_sequence[105])
        self.assertEqual(board.player.position, Position(8, 4))
        target = board.grid_at(Position(6, 4))
        self.assertFalse(target.has_monster)

        # DECLARED CONSTRUCTED: the recorded (8,4) board with the remembered
        # (6,4) target cell marked occupied. The survey has no clearing
        # evidence, so it still takes one step toward the reviewed stand.
        occupied = replace(
            board,
            grids={
                **board.grids,
                Position(6, 4): replace(target, has_monster=True),
            },
        )
        key, reason = self.decide(policy, occupied)
        self.assertEqual((key, reason), ("2", SURVEY))
        self.assertNotIn(
            TARGET_6_4, policy._quest_strategy_cleared_targets.get(31, set())
        )

        # The recorded board itself certifies (6,4) empty from (8,4).
        key, reason = self.decide(policy, board)
        self.assertEqual(reason, CLEARED)
        self.assertIn(
            TARGET_6_4, policy._quest_strategy_cleared_targets.get(31, set())
        )


if __name__ == "__main__":
    unittest.main()
