"""Recorded Q2 suffix at a declared reconstructed residual-phase boundary.

This is not a live checkpoint or an exact lifetime replay. The original phase
history is absent from the capture. Seed its completed opening/placement work,
then send the unmodified recorded boards through public choose_key. A separate
counterfactual changes only player position/turn to follow the returned keys;
it establishes route progress, not a successful live quest completion.
"""

from __future__ import annotations

import tests  # noqa: F401
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "q2-residual-20261025.jsonl.gz"
PROVENANCE = FIXTURES / "q2-residual-20261025.provenance.json"


class Q2ResidualRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
            cls.provenance["fixture_sha256"]
        )
        cls.boards = {}
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                cls.boards.setdefault(row["capture"], []).append(row["board"])
        definitions = find_quest_definitions(Path("C:/hengband/bot-client/state.jsonl"))
        if definitions is None:
            raise unittest.SkipTest("Hengband quest definitions unavailable")
        cls.quests = load_quest_knowledge(definitions)
        cls.profiles = load_quest_strategies(
            Path(__file__).resolve().parents[1] / "strategy" / "quests"
        )

    def _policy(self, first_board):
        policy = HengbotPolicy(
            quest_knowledge=self.quests, quest_strategies=self.profiles
        )
        policy.consume_skill_knowledge(self.provenance["skill_knowledge"])
        policy.prime(policy.with_known_skill_exp(parse_snapshot(first_board)))
        # DECLARED RECONSTRUCTION: the captured decisions are already beyond
        # the ordered placement phases and the first four residual races.
        # No target, visited observation goal, router, or decision is mocked.
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            Position(*position)
            for position, _ in self.quests[2].battlefield.monster_placements
        )
        policy._q2_residual_surveyed_races.update((202, 213, 252, 153))
        return policy

    @staticmethod
    def _choose(policy, board):
        snapshot = policy.with_known_skill_exp(parse_snapshot(board))
        return policy.choose_key(snapshot), snapshot

    def test_both_captured_suffixes_keep_the_existing_target_eligible(self):
        for label, boards in self.boards.items():
            with self.subTest(capture=label):
                policy = self._policy(boards[0])
                decisions = []
                for board in boards:
                    key, snapshot = self._choose(policy, board)
                    decisions.append((snapshot.player.position, key))
                # Original 0f8835a7: every tail pair is (1,3):6, (1,4):4.
                # A reached/temporarily visible owner must not hide its stored
                # route and let another placement reverse the previous step.
                self.assertEqual(
                    decisions[-12:],
                    [(Position(*yx), "6") for yx in [
                        (1, 3), (1, 4), (1, 3), (1, 4),
                        (1, 3), (1, 4), (1, 3), (1, 4),
                        (1, 3), (1, 4), (1, 3), (1, 4),
                    ]],
                )
                self.assertEqual(policy.last_reason, "quest-strategy:q2-residual-86-sweep")

    def test_following_changed_corridor_key_reaches_and_releases_the_target(self):
        directions = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        for label, boards in self.boards.items():
            with self.subTest(capture=label):
                policy = self._policy(boards[0])
                # Stop at the first (1,4) board after returning to the opening
                # corridor. All prior inputs remain exactly as recorded.
                for board in boards:
                    key, snapshot = self._choose(policy, board)
                    if snapshot.player.position == Position(1, 4):
                        break
                route_key = (snapshot.floor_key, -86, Position(3, 7))
                target = policy._q2_phase_route_targets[route_key]
                self.assertEqual(target, Position(3, 7))
                self.assertEqual(key, "6")
                positions = [snapshot.player.position]
                # DECLARED COUNTERFACTUAL: follow the emitted moves on the
                # recorded empty corridor, retaining all other board facts.
                # This does not replay historical boards as their effects.
                for _ in range(3):
                    dy, dx = directions[key]
                    position = Position(snapshot.player.position.y + dy, snapshot.player.position.x + dx)
                    cell = snapshot.grid_at(position) or policy._remembered_grids.get(position)
                    self.assertIsNotNone(cell)
                    self.assertTrue(cell.enterable)
                    snapshot = replace(
                        snapshot,
                        player=replace(snapshot.player, position=position),
                        turn=snapshot.turn + 1,
                    )
                    positions.append(position)
                    key = policy.choose_key(snapshot)
                self.assertEqual(positions, [
                    Position(1, 4), Position(1, 5), Position(2, 6), target,
                ])
                self.assertNotIn(route_key, policy._q2_phase_route_targets)


if __name__ == "__main__":
    unittest.main()
