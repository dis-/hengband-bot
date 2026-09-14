"""Recorded and value-level pins for fixed-quest reward locomotion."""

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_types import DecisionCandidate
from tests.test_quest_enter_approach_progress import DIRECTION_DELTA
from tests.test_quest_travel_progress import QuestTravelFixtureMixin


FIXTURE = Path(__file__).with_name("fixtures") / "reward-approach-town0.jsonl.gz"


class RewardApproachProgressPins(QuestTravelFixtureMixin, unittest.TestCase):
    def _boards(self):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    @staticmethod
    def _advance(raw, key, turn):
        derived = copy.deepcopy(raw)
        dy, dx = DIRECTION_DELTA[str(key)]
        derived["player"]["y"] += dy
        derived["player"]["x"] += dx
        derived["turn"] = turn
        return derived

    def _reward_decision(self, policy, raw):
        snapshot = parse_snapshot(raw, self.monrace)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        return key

    @staticmethod
    def _empty_reward(raw):
        derived = copy.deepcopy(raw)
        for cell in derived["grid_map"]["cells"]:
            if (cell.get("y"), cell.get("x")) == (36, 119):
                cell.pop("o", None)
        derived["grid_map"]["found_items"] = []
        return derived

    @staticmethod
    def _boxed(raw):
        derived = copy.deepcopy(raw)
        grid_map = derived["grid_map"]
        wall = next(
            i for i, entry in enumerate(grid_map["palette"])
            if entry[2] & (1 << 17)
        )
        py, px = derived["player"]["y"], derived["player"]["x"]
        blocked = {
            (py + dy, px + dx)
            for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx
        }
        rewritten = []
        for y, x0, length, palette in grid_map["runs"]:
            x1, cursor = x0 + length, x0
            for x in sorted(x for yy, x in blocked if yy == y and x0 <= x < x1):
                if cursor < x:
                    rewritten.append([y, cursor, x - cursor, palette])
                rewritten.append([y, x, 1, wall])
                cursor = x + 1
            if cursor < x1:
                rewritten.append([y, cursor, x1 - cursor, palette])
        grid_map["runs"] = rewritten
        return derived

    def test_recorded_route_and_continuation_reach_pickup_once_then_release(self):
        policy = self._policy()
        ranks, budgets = [], []
        boards = self._boards()
        # The first board is the pre-approach Home scan.  Replay the twelve
        # incident walk boards, including the board on which the old owner had
        # already retired.
        policy.confirm_key_posted(policy.choose_key(parse_snapshot(boards[0], self.monrace)))
        for raw in boards[1:]:
            snapshot = parse_snapshot(raw, self.monrace)
            key = policy.choose_key(snapshot)
            self.assertIsInstance(key, DecisionCandidate)
            self.assertEqual(key.reason, "fixedquest:reward-approach")
            ranks.append(key.route_declaration.bfs_rank)
            policy.confirm_key_posted(key)
            budgets.append(policy._town_turn_arbiter.telemetry[
                "budget_remaining_estimate"
            ])
            self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)
        self.assertEqual(ranks, list(range(14, 2, -1)))
        self.assertEqual(budgets, [3] * 12)

        current = copy.deepcopy(boards[-1])
        turn = current["turn"]
        pickup_posts = 0
        while True:
            snapshot = parse_snapshot(current, self.monrace)
            key = self._reward_decision(policy, current)
            if policy.last_reason == "fixedquest:reward-pickup":
                self.assertEqual(str(key), "g")
                pickup_posts += 1
                break
            self.assertIsInstance(key, DecisionCandidate)
            self.assertEqual(key.reason, "fixedquest:reward-approach")
            turn += 10
            current = self._advance(current, key, turn)
        self.assertEqual(pickup_posts, 1)
        empty = self._empty_reward(current)
        empty["turn"] = turn + 10
        policy.choose_key(parse_snapshot(empty, self.monrace))
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertNotEqual(policy.last_reason, "fixedquest:reward-pickup")

    def test_unchanged_rank_retires_but_no_route_is_visible_terminal(self):
        source = self._boards()[1]
        policy = self._policy()
        first = self._boards()[0]
        policy.confirm_key_posted(
            policy.choose_key(parse_snapshot(first, self.monrace))
        )
        budgets = []
        for offset in range(4):
            raw = copy.deepcopy(source)
            raw["turn"] += offset * 10
            key = policy.choose_key(parse_snapshot(raw, self.monrace))
            policy.confirm_key_posted(key)
            budgets.append(policy._town_turn_arbiter.telemetry[
                "budget_remaining_estimate"
            ])
        self.assertEqual(budgets, [3, 2, 1, 0])
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)

        boxed = self._boxed(source)
        unavailable = self._policy()
        unavailable.confirm_key_posted(
            unavailable.choose_key(parse_snapshot(first, self.monrace))
        )
        reasons = []
        for offset in range(5):
            raw = copy.deepcopy(boxed)
            raw["turn"] += offset * 10
            key = unavailable.choose_key(parse_snapshot(raw, self.monrace))
            unavailable.confirm_key_posted(key)
            reasons.append(unavailable.last_reason)
        self.assertEqual(reasons[:4], [
            "fixedquest:reward-approach:route-unavailable"
        ] * 4)
        self.assertEqual((str(key), unavailable.last_reason), (
            WAIT_KEY, "fixedquest:reward-approach:unsatisfiable"
        ))

    def test_damaged_retired_reward_claim_posts_safety_key(self):
        source = self._boxed(self._boards()[1])
        policy = self._policy()
        first = self._boards()[0]
        policy.confirm_key_posted(
            policy.choose_key(parse_snapshot(first, self.monrace))
        )
        for offset in range(4):
            raw = copy.deepcopy(source)
            raw["turn"] += offset * 10
            policy.confirm_key_posted(policy.choose_key(parse_snapshot(raw, self.monrace)))
        higher = copy.deepcopy(source)
        higher["turn"] += 50
        higher["player"]["max_hp"] += 1
        higher["player"]["hp"] += 1
        policy.confirm_key_posted(policy.choose_key(parse_snapshot(higher, self.monrace)))
        damaged = copy.deepcopy(source)
        damaged["turn"] += 60
        key = policy.choose_key(parse_snapshot(damaged, self.monrace))
        self.assertEqual((str(key), policy.last_reason), ("rf", "no-wait:escape-scroll"))
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)


if __name__ == "__main__":
    unittest.main()
