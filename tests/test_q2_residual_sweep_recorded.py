"""Recorded replay for the Q2 residual-placement sweep loop."""

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
from hengbot.policy_constants import Q2_RESIDUAL_SWEEP_RACES
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.quest_strategies import load_quest_strategies
from policy_fixtures import hostile


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = ROOT / "tests/fixtures/q2-residual-sweep-20261018.jsonl.gz"
SWEEP_REASON = "quest-strategy:q2-residual-86-sweep"
LOOP_SEQUENCES = (527, 528, 529, 530)


def captured_rows() -> list[dict]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class Q2ResidualSweepRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quest = load_quest_knowledge(EDIT / "quests")[2]
        cls.monraces = load_monrace_knowledge(
            EDIT / "MonraceDefinitions.jsonc"
        )
        cls.profile = load_quest_strategies(ROOT / "strategy/quests")[2]

    def policy(self) -> HengbotPolicy:
        policy = HengbotPolicy(
            quest_knowledge={2: self.quest},
            quest_strategies={2: self.profile},
            monrace_knowledge=self.monraces,
        )
        # The capture begins in the already-approved residual pass. Restore
        # the earlier Q2 phase gates and leave race 86 as the active sweep.
        policy._q2_cleared_races.update(self.profile.priority_targets)
        policy._q2_surveyed_placements.update(
            Position(*position)
            for position, _ in self.quest.battlefield.monster_placements
        )
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_residual_surveyed_races.update(
            race_id for race_id in Q2_RESIDUAL_SWEEP_RACES
            if race_id != 86
        )
        return policy

    def test_recorded_loop_replay_keeps_advancing_toward_one_route_target(self):
        rows = captured_rows()
        self.assertEqual(len(rows), 52)
        policy = self.policy()
        navigator = QuestFloorNavigator(2, self.quest.battlefield)
        replayed = {}

        for row in rows:
            snapshot = policy._with_grid_memory(
                parse_snapshot(row["board"], self.monraces)
            )
            key = policy._q2_phase_key(snapshot, self.profile, navigator)
            if row["decision_sequence"] in LOOP_SEQUENCES:
                replayed[row["decision_sequence"]] = (
                    key,
                    policy.last_reason,
                    snapshot.player.position,
                    dict(policy._q2_phase_route_targets),
                )

        # The capture records the 6/4 reversal on consecutive boards.
        recorded = {row["decision_sequence"]: row for row in rows}
        self.assertEqual(
            tuple(recorded[sequence]["key"] for sequence in LOOP_SEQUENCES),
            ("6", "4", "6", "4"),
        )
        self.assertEqual(
            tuple(recorded[sequence]["reason"] for sequence in LOOP_SEQUENCES),
            (SWEEP_REASON,) * 4,
        )

        # Replaying those same boards now retains one target and gives the
        # eastward step on both positions, so executing it advances the route.
        self.assertEqual(
            tuple(replayed[sequence][0] for sequence in LOOP_SEQUENCES),
            ("6", "6", "6", "6"),
        )
        self.assertEqual(
            tuple(replayed[sequence][1] for sequence in LOOP_SEQUENCES),
            (SWEEP_REASON,) * 4,
        )
        self.assertEqual(
            tuple(replayed[sequence][2] for sequence in LOOP_SEQUENCES),
            (Position(1, 2), Position(1, 3), Position(1, 2), Position(1, 3)),
        )
        for sequence in LOOP_SEQUENCES:
            route_targets = replayed[sequence][3]
            self.assertIn(
                ((0, 15, 2), -86, Position(3, 7)), route_targets
            )
            self.assertEqual(
                route_targets[((0, 15, 2), -86, Position(3, 7))],
                Position(3, 7),
            )

    def test_visible_residual_monster_is_approached_then_fought(self):
        rows = captured_rows()
        recorded = next(row for row in rows if row["decision_sequence"] == 527)
        source = parse_snapshot(recorded["board"], self.monraces)
        policy = self.policy()
        navigator = QuestFloorNavigator(2, self.quest.battlefield)

        # DECLARED CONSTRUCTED: retain the recorded floor and inventory frame,
        # but place a visible race-86 multiplier on its fixed Q2 placement.
        approach_target = hostile(1, 3, 7, distance=6, race_id=86)
        approach = replace(
            source,
            inventory=[],
            equipment=[],
            visible_monsters=[approach_target],
        )
        approach_key = policy._q2_phase_key(
            approach, self.profile, navigator
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-close-residual-multiplier-no-ammo",
        )
        self.assertEqual(approach_key, "6")

        # DECLARED CONSTRUCTED: advance to a neighboring cell while the same
        # visible residual monster remains, then require the melee attack.
        adjacent = replace(
            approach,
            player=replace(approach.player, position=Position(2, 6)),
            visible_monsters=[hostile(1, 3, 7, distance=1, race_id=86)],
        )
        fight_key = policy._q2_phase_key(adjacent, self.profile, navigator)
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-melee-corpse-attack",
        )
        self.assertEqual(fight_key, "3")


if __name__ == "__main__":
    unittest.main()
