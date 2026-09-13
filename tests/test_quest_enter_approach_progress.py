"""Public-path pins for the quest entrance approach envelope."""

import copy
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy_constants import QUEST_STATUS_COMPLETED, WAIT_KEY
from hengbot.policy_types import DecisionCandidate
from tests.test_quest_travel_progress import QuestTravelFixtureMixin


INCIDENT = Path(__file__).with_name("fixtures") / "quest-enter-approach-stage2f.jsonl"
TURNS = (2857031, 2857040, 2857052, 2857062, 2857071, 2857084, 2857092)
DIRECTION_DELTA = {
    "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
    "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
}


class QuestEnterApproachProgressPins(QuestTravelFixtureMixin, unittest.TestCase):
    def _records(self):
        with open(INCIDENT, encoding="utf-8") as stream:
            return [(json.loads(line), line) for line in stream]

    def _incident_boards(self):
        wanted = set(TURNS)
        boards = {
            raw["turn"]: raw for raw, _line in self._records()
            if raw.get("type") == "player_turn" and raw.get("turn") in wanted
        }
        self.assertEqual(tuple(boards), TURNS)
        return [boards[turn] for turn in TURNS]

    def _seed_through_incident(self, *, maps=True, stop_turn=TURNS[0]):
        """Dispatch every response and decide every board in recorded order."""
        policy = self._policy(maps=maps)
        primed = False
        attributions = []
        for raw, line in self._records():
            if raw.get("type") == "player_turn":
                if raw.get("turn") == stop_turn:
                    break
                snapshot = parse_snapshot(raw, self.monrace)
                if not primed:
                    policy.prime(snapshot)
                    primed = True
                key = policy.choose_key(snapshot)
                policy.confirm_key_posted(key)
                attributions.append(policy.decision_attribution)
            else:
                self._dispatch(policy, line)
        self.assertTrue(primed)
        return policy, attributions

    @staticmethod
    def _advance(raw, key, turn):
        derived = copy.deepcopy(raw)
        dy, dx = DIRECTION_DELTA[str(key)]
        derived["player"]["y"] += dy
        derived["player"]["x"] += dx
        derived["turn"] = turn
        return derived

    def test_positive_ordered_replay_reaches_entrance_and_enters(self):
        policy, seed_attributions = self._seed_through_incident()
        ranks, budgets, attributions = [], [], []
        current = None
        for raw in self._incident_boards():
            current = copy.deepcopy(raw)
            snapshot = parse_snapshot(current, self.monrace)
            key = policy.choose_key(snapshot)
            self.assertIsInstance(key, DecisionCandidate)
            self.assertEqual(key.reason, "quest:enter:approach")
            ranks.append(key.route_declaration.bfs_rank)
            policy.confirm_key_posted(key)
            budgets.append(policy._town_turn_arbiter.telemetry["budget_remaining_estimate"])
            attributions.append(policy.decision_attribution)
            self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)
        self.assertEqual(budgets, [3] * 7)
        self.assertTrue(all(after < before for before, after in zip(ranks, ranks[1:])))
        self.assertIn("town-errand", seed_attributions)

        # Derived continuation: apply each real emitted direction to the same
        # public board until the disclosed entrance is reached.
        turn = current["turn"]
        turn += 10
        current = self._advance(current, key, turn)
        continuation_steps = 0
        while True:
            snapshot = parse_snapshot(current, self.monrace)
            positions = policy._fixed_quest_entrance_positions(snapshot, 22)
            if snapshot.player.position in positions:
                break
            key = policy.choose_key(snapshot)
            self.assertIsInstance(key, DecisionCandidate)
            self.assertEqual(key.reason, "quest:enter:approach")
            policy.confirm_key_posted(key)
            self.assertEqual(
                policy._town_turn_arbiter.telemetry["budget_remaining_estimate"], 3,
                (continuation_steps, snapshot.player.position, str(key),
                 key.route_declaration.bfs_rank),
            )
            turn += 10
            current = self._advance(current, key, turn)
            continuation_steps += 1
            self.assertLess(continuation_steps, 100)
        # The captured warrior still had unfinished equipment work.  Derive a
        # non-warrior public player at the reached tile so the entry boundary
        # itself is eligible without assigning policy state.
        current["player"]["class_id"] = 1
        enter = policy.choose_key(parse_snapshot(current, self.monrace))
        self.assertEqual((enter, policy.last_reason), (">y", "quest:enter"))

    def test_final_identity_staleness_and_arbiter_preview_are_read_only(self):
        policy, _ = self._seed_through_incident()
        snapshot = parse_snapshot(self._incident_boards()[0], self.monrace)
        key = policy.choose_key(snapshot)
        clone = DecisionCandidate(
            str(key), reason=key.reason, decision_identity=key.decision_identity,
            route_declaration=key.route_declaration,
        )
        self.assertTrue(policy._valid_quest_travel_declaration(snapshot, key))
        self.assertFalse(policy._valid_quest_travel_declaration(snapshot, clone))
        policy.confirm_key_posted(key)
        fresh = policy.choose_key(snapshot)
        self.assertFalse(policy._valid_quest_travel_declaration(snapshot, key))
        self.assertTrue(policy._valid_quest_travel_declaration(snapshot, fresh))

        arbiter = policy._town_turn_arbiter
        arbiter._retired["quest-request"] = ("fixed",)
        before = (copy.deepcopy(arbiter._retired), copy.deepcopy(arbiter._recurrences))
        self.assertTrue(arbiter.preview_may_select(
            fresh.reason,
            policy._town_arbiter_progress_vector(snapshot, fresh.reason, fresh),
            retirement_key=("changed",),
        ))
        self.assertEqual((arbiter._retired, arbiter._recurrences), before)

    @staticmethod
    def _without_entrance(raw):
        derived = copy.deepcopy(raw)
        for cell in (derived.get("grid_map") or {}).get("cells", []):
            cell.pop("q", None)
        return derived

    @staticmethod
    def _boxed(raw):
        """Derived known-entrance/no-path public board."""
        derived = copy.deepcopy(raw)
        grid_map = derived["grid_map"]
        wall = next(i for i, entry in enumerate(grid_map["palette"]) if entry[2] & (1 << 17))
        py, px = derived["player"]["y"], derived["player"]["x"]
        blocked = {(py + dy, px + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                   if dy or dx}
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

    def test_derived_route_failures_retire_retain_restore_and_change_status(self):
        source = self._incident_boards()[0]

        # Derived missing metadata: no static maps and no emitted entrance.
        unknown_policy, _ = self._seed_through_incident(maps=False)
        unknown = parse_snapshot(self._without_entrance(source), self.monrace)
        unknown_key = unknown_policy.choose_key(unknown)
        self.assertNotEqual(
            getattr(unknown_key, "reason", None),
            "quest:enter:approach:route-unavailable",
        )

        # Derived on-entrance/no-exit: entry itself remains the legal action.
        on_entrance = copy.deepcopy(source)
        on_entrance["player"].update({"x": 99, "y": 63})
        on_entrance["player"]["class_id"] = 1
        entered, _ = self._seed_through_incident(maps=False)
        enter_key = entered.choose_key(parse_snapshot(on_entrance, self.monrace))
        self.assertEqual((enter_key, entered.last_reason), (">y", "quest:enter"))

        policy, _ = self._seed_through_incident(maps=False)
        boxed = self._boxed(source)
        clearance, budgets = [], []
        for offset in range(5):
            current = copy.deepcopy(boxed)
            current["turn"] += offset * 10
            if offset >= 4:
                current["player"]["gold"] -= offset
            snapshot = parse_snapshot(current, self.monrace)
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            clearance.append(policy._quest_entry_route_unavailable_clearance_key(snapshot))
            budgets.append(policy._town_turn_arbiter.telemetry["budget_remaining_estimate"])
        self.assertEqual(budgets[:4], [3, 2, 1, 0])
        self.assertTrue(all(value == clearance[0] for value in clearance))
        self.assertEqual((str(key), policy.last_reason),
                         (WAIT_KEY, "quest:enter:approach:unsatisfiable"))
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)

        # A public max-HP transition makes _took_damage true while the lower
        # board is still at full HP, reaching the damaged-WAIT rewrite seam.
        higher = copy.deepcopy(boxed)
        higher["turn"] += 60
        higher["player"]["max_hp"] += 1
        higher["player"]["hp"] += 1
        policy.confirm_key_posted(policy.choose_key(parse_snapshot(higher, self.monrace)))
        lowered = copy.deepcopy(boxed)
        lowered["turn"] += 70
        lowered_key = policy.choose_key(parse_snapshot(lowered, self.monrace))
        policy.confirm_key_posted(lowered_key)
        self.assertEqual((str(lowered_key), policy.last_reason),
                         (WAIT_KEY, "quest:enter:approach:unsatisfiable"))
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)

        restored = parse_snapshot(source, self.monrace)
        restored_key = policy.choose_key(restored)
        self.assertIsInstance(restored_key, DecisionCandidate)
        self.assertEqual(restored_key.reason, "quest:enter:approach")
        self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)

        changed = copy.deepcopy(boxed)
        next(q for q in changed["progress"]["quests"] if q["id"] == 22)["status"] = QUEST_STATUS_COMPLETED
        policy.choose_key(parse_snapshot(changed, self.monrace))
        self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)

    def test_taken_q22_cross_town_uses_stage1_clearance_values(self):
        policy = self._policy()
        records = super()._records()
        taken_progress = copy.deepcopy(self._incident_boards()[0]["progress"])

        def taken_q22(raw):
            derived = copy.deepcopy(raw)
            derived["progress"] = copy.deepcopy(taken_progress)
            return derived

        first = parse_snapshot(taken_q22(records[0][1]), self.monrace)
        policy.prime(first)
        initial = policy.choose_key(first)
        policy.confirm_key_posted(initial)
        budgets = []
        for _number, raw, _line in records[2:]:
            snapshot = parse_snapshot(taken_q22(raw), self.monrace)
            self.assertIsNone(policy._quest_entry_route_unavailable_clearance_key(snapshot))
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            if policy.last_reason == "fixedquest:q22-travel":
                budgets.append(policy._town_turn_arbiter.telemetry["budget_remaining_estimate"])
        self.assertTrue(budgets)
        self.assertEqual(budgets, [3, 3, 3, 3, 3, 2, 3, 3, 3, 3, 3, 3])
        self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)


if __name__ == "__main__":
    unittest.main()
