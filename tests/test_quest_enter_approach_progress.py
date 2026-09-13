"""Incident-faithful pins for the quest entrance approach envelope."""

import copy
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_types import DecisionCandidate
from test_quest_travel_progress import QuestTravelFixtureMixin


INCIDENT = Path(__file__).with_name("fixtures") / "quest-enter-approach-stage2f.jsonl"
TURNS = (2857031, 2857040, 2857052, 2857062, 2857071, 2857084, 2857092)


class QuestEnterApproachProgressPins(QuestTravelFixtureMixin, unittest.TestCase):
    def _incident_boards(self):
        wanted = set(TURNS)
        boards = {}
        with open(INCIDENT, encoding="utf-8") as stream:
            for line in stream:
                raw = json.loads(line)
                turn = raw.get("turn")
                if turn in wanted and raw.get("type") == "player_turn":
                    boards[turn] = raw
        self.assertEqual(tuple(boards), TURNS)
        return [boards[turn] for turn in TURNS]

    def _seeded_policy(self, *, maps=True):
        policy = self._policy(maps=maps)
        primed = False
        with open(INCIDENT, encoding="utf-8") as stream:
            for line in stream:
                raw = json.loads(line)
                if raw.get("turn") == TURNS[0] and raw.get("type") == "player_turn":
                    break
                if raw.get("type") == "player_turn":
                    snapshot = parse_snapshot(raw, self.monrace)
                    if not primed:
                        policy.prime(snapshot)
                        primed = True
                    key = policy.choose_key(snapshot)
                    policy.confirm_key_posted(key)
                else:
                    self._dispatch(policy, line)
        self.assertTrue(primed)
        return policy

    def test_positive_real_producer_preserves_budget(self):
        policy = self._seeded_policy()
        boards = self._incident_boards()[:6]
        ranks = []
        budgets = []
        for raw in boards:
            snapshot = parse_snapshot(raw, self.monrace)
            key = policy.choose_key(snapshot)
            self.assertIsInstance(key, DecisionCandidate)
            self.assertEqual(key.reason, "quest:enter:approach")
            self.assertTrue(policy._valid_quest_travel_declaration(snapshot, key))
            ranks.append(key.route_declaration.bfs_rank)
            policy.confirm_key_posted(key)
            budgets.append(policy._town_turn_arbiter.telemetry["budget_remaining_estimate"])
            self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)
        self.assertTrue(all(after < before for before, after in zip(ranks, ranks[1:])))
        self.assertEqual(budgets, [3] * 6)

    def test_final_envelope_identity_is_unforgeable_and_preview_read_only(self):
        policy = self._seeded_policy()
        raw = self._incident_boards()[0]
        snapshot = parse_snapshot(raw, self.monrace)
        key = policy.choose_key(snapshot)
        before = policy._town_turn_arbiter.telemetry["budget_remaining_estimate"]
        clone = DecisionCandidate(
            str(key), reason=key.reason,
            decision_identity=key.decision_identity,
            route_declaration=key.route_declaration,
        )
        self.assertTrue(policy._valid_quest_travel_declaration(snapshot, key))
        self.assertFalse(policy._valid_quest_travel_declaration(snapshot, clone))
        policy._town_arbiter_progress_vector(snapshot, key.reason, key)
        self.assertEqual(
            policy._town_turn_arbiter.telemetry["budget_remaining_estimate"], before
        )

    @staticmethod
    def _without_entrance(raw):
        result = copy.deepcopy(raw)
        for cell in (result.get("grid_map") or {}).get("cells", []):
            cell.pop("q", None)
        return result

    def test_unavailable_retires_to_named_terminal_and_retains_on_transients(self):
        policy = self._seeded_policy(maps=False)
        raw = self._without_entrance(self._incident_boards()[0])
        snapshot = parse_snapshot(raw, self.monrace)
        keys = []
        clearance = []
        budgets = []
        for offset in range(6):
            board = copy.deepcopy(raw)
            board["turn"] += offset * 10
            if offset == 4:
                board["player"]["hp"] = 1
                board["player"]["gold"] -= 1
            current = parse_snapshot(board, self.monrace)
            key = policy.choose_key(current)
            policy.confirm_key_posted(key)
            keys.append((str(key), policy.last_reason))
            clearance.append(policy._quest_entry_route_unavailable_clearance_key(current))
            budgets.append(policy._town_turn_arbiter.telemetry["budget_remaining_estimate"])
        self.assertEqual(budgets[:4], [3, 2, 1, 0])
        self.assertTrue(all(value == clearance[0] for value in clearance))
        self.assertEqual(keys[-1], (WAIT_KEY, "quest:enter:approach:unsatisfiable"))
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)


if __name__ == "__main__":
    unittest.main()
