"""Stage-2 prepare-return pins from source records 60-64 / decisions 47-51.

The five public boards are turns 2856703, 2856709, 2856714, 2856725 and
2856732 from the preserved town-3 incident.  Every assertion drives the real
producer through ``choose_key`` on the same policy which consumes the result.
"""

import copy
import gzip
import json
import unittest

from hengbot.model import parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_types import DecisionCandidate
from tests.test_quest_travel_progress import QuestTravelFixtureMixin


class QuestPrepareReturnStage2Pins(QuestTravelFixtureMixin, unittest.TestCase):
    """Reuse only the real-policy fixture construction from the stage-1 pin."""

    def _stage2_records(self):
        path = self._root() / "tests/fixtures/quest-prepare-return-town3-walk-stage2.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    def _return_1_records(self):
        path = self._root() / "tests/fixtures/quest-prepare-return-town1-recurrence-stage2.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return list(zip(range(292, 329), (json.loads(line) for line in stream)))

    @staticmethod
    def _root():
        from pathlib import Path
        return Path(__file__).resolve().parents[1]

    def test_l_return_3_walk_partial_uses_final_route_rank(self):
        policy = self._policy()
        rows = self._stage2_records()
        observed = []
        for index, raw in enumerate(rows):
            snapshot = parse_snapshot(raw, self.monrace)
            if index == 0:
                policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            if raw["turn"] < 2856703:
                continue
            self.assertIsInstance(key, DecisionCandidate)
            self.assertEqual(key.reason, "fixedquest:prepare-return")
            declaration = key.route_declaration
            self.assertEqual(declaration.producer_branch, "return-3")
            observed.append((str(key), declaration.bfs_rank))
            self.assertEqual(
                policy._town_turn_arbiter.telemetry["budget_remaining_estimate"], 3
            )
            self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)
        self.assertEqual([key for key, _rank in observed], ["7", "8", "9", "9", "9"])
        self.assertTrue(all(a > b for a, b in zip(
            [rank for _key, rank in observed],
            [rank for _key, rank in observed][1:],
        )))

    def test_q_return_1_recurrence_retires_without_step_off_credit(self):
        policy = self._policy()
        observations = []
        for number, raw in self._return_1_records():
            line = json.dumps(raw, ensure_ascii=False)
            if raw.get("type") in {"character", "look", "knowledge", "store"}:
                self._dispatch(policy, line)
                continue
            snapshot = parse_snapshot(raw, self.monrace)
            if number == 292:
                policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            if 309 <= number <= 312:
                declaration = getattr(key, "route_declaration", None)
                vector = policy._town_turn_arbiter._vector_by_owner.get("quest-request")
                observations.append((
                    number, key, policy.last_reason, declaration, vector,
                    policy._town_turn_arbiter.telemetry[
                        "budget_remaining_estimate"
                    ], snapshot,
                    "quest-request" in policy._town_turn_arbiter._retired,
                ))
            if number == 312:
                following = copy.deepcopy(raw)
                following["turn"] += 1
                terminal_key = policy.choose_key(parse_snapshot(following, self.monrace))
                policy.confirm_key_posted(terminal_key)
                terminal = (terminal_key, policy.last_reason)
                break
        self.assertEqual([item[0] for item in observations], [309, 310, 311, 312])
        self.assertEqual(
            [item[2] for item in observations],
            ["fixedquest:prepare-return"] * 4,
        )
        self.assertIsNone(observations[0][3])
        self.assertEqual(
            observations[0][4],
            policy._town_arbiter_progress_vector(
                observations[0][6], observations[0][2]
            ),
        )
        self.assertEqual(
            [item[3].producer_branch for item in observations[1:]],
            ["return-1", "return-1", "return-1"],
        )
        # The first step-off has no declaration and the two distinct declared
        # route vectors do not consume recurrence allowance.  Only record 312
        # repeats record 310, so the measured public sequence is 3/3/3/0.
        self.assertEqual([item[5] for item in observations], [3, 3, 3, 0])
        self.assertTrue(observations[-1][7])
        self.assertEqual(observations[-1][6].turn, 2855985)
        self.assertEqual(terminal, ("\x1b`n!.", "shop:travel"))

    @staticmethod
    def _route_failure(raw, variant):
        derived = copy.deepcopy(raw)
        cells = derived["grid_map"]["cells"]
        for cell in cells:
            if cell.get("b") == 4:
                cell.pop("b")
                cell.pop("p", None)
        if variant in {"known-no-path", "on-inn-no-exit"}:
            cells.append({"x": 88, "y": 15, "b": 4, "p": 0})
        if variant in {"known-no-path", "on-inn-no-exit"}:
            if variant == "on-inn-no-exit":
                derived["player"]["x"] = 88
                derived["player"]["y"] = 15
            grid_map = derived["grid_map"]
            wall_index = next(
                index for index, entry in enumerate(grid_map["palette"])
                if entry[2] & (1 << 17)
            )
            blocked = {
                (y, x) for y in range(14, 17) for x in range(87, 90)
                if (y, x) != (15, 88)
            }
            rewritten = []
            for y, x0, length, palette_index in grid_map["runs"]:
                x1 = x0 + length
                cursor = x0
                for x in sorted(x for yy, x in blocked if yy == y and x0 <= x < x1):
                    if cursor < x:
                        rewritten.append([y, cursor, x - cursor, palette_index])
                    rewritten.append([y, x, 1, wall_index])
                    cursor = x + 1
                if cursor < x1:
                    rewritten.append([y, cursor, x1 - cursor, palette_index])
            grid_map["runs"] = rewritten
        return derived

    def test_n_return_3_route_failure_variants_retire_and_restore(self):
        raw = self._stage2_records()[-5]
        for variant in ("no-inn", "known-no-path", "on-inn-no-exit"):
            with self.subTest(variant=variant):
                policy = self._policy(maps=False)
                seed = self._route_failure(raw, variant)
                policy.prime(parse_snapshot(seed, self.monrace))
                vectors, budgets = [], []
                key = None
                for offset in range(7):
                    current = copy.deepcopy(seed)
                    current["turn"] += offset * 10
                    snapshot = parse_snapshot(current, self.monrace)
                    key = policy.choose_key(snapshot)
                    policy.confirm_key_posted(key)
                    if policy.last_reason.startswith("fixedquest:prepare-return"):
                        vectors.append(policy._town_turn_arbiter._vector_by_owner.get(
                            "quest-request"
                        ))
                        budgets.append(policy._town_turn_arbiter.telemetry[
                            "budget_remaining_estimate"
                        ])
                self.assertTrue(all(vector == vectors[0] for vector in vectors))
                self.assertEqual(budgets[:4], [3, 2, 1, 0])
                self.assertEqual(key, WAIT_KEY)
                self.assertEqual(
                    policy.last_reason, "fixedquest:prepare-return:unsatisfiable"
                )
                incidental = copy.deepcopy(seed)
                incidental["turn"] += 100
                incidental["player"]["gold"] -= 1
                incidental_key = policy.choose_key(
                    parse_snapshot(incidental, self.monrace)
                )
                policy.confirm_key_posted(incidental_key)
                self.assertEqual(incidental_key, WAIT_KEY)
                self.assertEqual(
                    policy.last_reason, "fixedquest:prepare-return:unsatisfiable"
                )
                self.assertIn("quest-request", policy._town_turn_arbiter._retired)
                restored = parse_snapshot(raw, self.monrace)
                restored_key = policy.choose_key(restored)
                self.assertIsInstance(restored_key, DecisionCandidate)
                self.assertEqual(restored_key.reason, "fixedquest:prepare-return")

    def test_procurement_preserves_real_return_3_unavailable_candidate(self):
        raw = self._stage2_records()[-5]
        seed = self._route_failure(raw, "no-inn")
        policy = self._policy(maps=False)
        policy.prime(parse_snapshot(seed, self.monrace))
        snapshot = parse_snapshot(seed, self.monrace)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        self.assertIsInstance(key, DecisionCandidate)
        self.assertEqual(key.reason, "fixedquest:prepare-return:route-unavailable")
        self.assertEqual(key.route_declaration.producer_branch, "return-3")
        # Seam unit: this capture has no publicly observed affordable supplier,
        # so the real downstream procurement consumer is invoked directly only
        # after choose_key produced the provenance-bearing candidate.
        self.assertIs(policy._town_procurement_decision(snapshot, key), key)

    def test_n_return_3_hostile_suppression_does_not_resurrect_retirement(self):
        raw = self._stage2_records()[-5]
        seed = self._route_failure(raw, "no-inn")
        policy = self._policy(maps=False)
        policy.prime(parse_snapshot(seed, self.monrace))
        for offset in range(4):
            current = copy.deepcopy(seed)
            current["turn"] += offset * 10
            key = policy.choose_key(parse_snapshot(current, self.monrace))
            policy.confirm_key_posted(key)
        self.assertEqual(policy.last_reason, "fixedquest:prepare-return:route-unavailable")
        self.assertEqual(
            policy._town_turn_arbiter.telemetry["budget_remaining_estimate"], 0
        )
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)

        hostile = copy.deepcopy(seed)
        hostile["turn"] += 50
        x, y = hostile["player"]["x"], hostile["player"]["y"]
        hostile["grid_map"]["cells"].append({"x": x + 1, "y": y, "m": 1})
        hostile["visible_monsters"] = [{"index": 1, "race_id": 1}]
        hostile_key = policy.choose_key(parse_snapshot(hostile, self.monrace))
        policy.confirm_key_posted(hostile_key)
        self.assertEqual(policy.last_reason, "melee")
        hostile_retained = "quest-request" in policy._town_turn_arbiter._retired

        safe = copy.deepcopy(seed)
        safe["turn"] += 60
        safe_key = policy.choose_key(parse_snapshot(safe, self.monrace))
        policy.confirm_key_posted(safe_key)
        self.assertEqual(
            (str(safe_key), policy.last_reason,
             policy._town_turn_arbiter.telemetry["budget_remaining_estimate"]),
            (WAIT_KEY, "fixedquest:prepare-return:unsatisfiable", 0),
        )
        self.assertTrue(hostile_retained)
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)

    def test_w_return_3_equal_key_distinct_candidate_has_no_authority(self):
        raw = self._stage2_records()[-5]
        policy = self._policy()
        snapshot = parse_snapshot(raw, self.monrace)
        policy.prime(snapshot)
        key = policy.choose_key(snapshot)
        self.assertIsInstance(key, DecisionCandidate)
        collision = DecisionCandidate(
            str(key), reason=key.reason,
            decision_identity=key.decision_identity,
            route_declaration=key.route_declaration,
        )
        self.assertTrue(policy._valid_quest_travel_declaration(snapshot, key, key.reason))
        self.assertFalse(policy._valid_quest_travel_declaration(
            snapshot, collision, collision.reason
        ))
        self.assertEqual(
            policy._town_arbiter_progress_vector(
                snapshot, collision.reason, collision
            ),
            policy._town_arbiter_progress_vector(snapshot, collision.reason),
        )

    def test_x_return_3_fare_crossing_after_retirement_is_measured(self):
        raw = self._stage2_records()[-5]
        seed = self._route_failure(raw, "no-inn")
        policy = self._policy(maps=False)
        policy.prime(parse_snapshot(seed, self.monrace))
        budgets = []
        for offset in range(7):
            current = copy.deepcopy(seed)
            current["turn"] += offset * 10
            key = policy.choose_key(parse_snapshot(current, self.monrace))
            policy.confirm_key_posted(key)
            budgets.append(policy._town_turn_arbiter.telemetry[
                "budget_remaining_estimate"
            ])
        crossed = copy.deepcopy(seed)
        crossed["turn"] += 100
        crossed["player"]["gold"] = 499
        low_key = policy.choose_key(parse_snapshot(crossed, self.monrace))
        policy.confirm_key_posted(low_key)
        low = (str(low_key), policy.last_reason,
               policy._town_turn_arbiter.telemetry["budget_remaining_estimate"])
        low_retained = "quest-request" in policy._town_turn_arbiter._retired
        crossed["turn"] += 10
        crossed["player"]["gold"] = 500
        high_key = policy.choose_key(parse_snapshot(crossed, self.monrace))
        policy.confirm_key_posted(high_key)
        high = (str(high_key), policy.last_reason,
                policy._town_turn_arbiter.telemetry["budget_remaining_estimate"])
        self.assertEqual(budgets[:4], [3, 2, 1, 0])
        self.assertEqual(low[1], "identify:full")
        self.assertEqual(
            high,
            (WAIT_KEY, "fixedquest:prepare-return:unsatisfiable", 0),
        )
        self.assertTrue(low_retained)
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)


if __name__ == "__main__":
    unittest.main()
