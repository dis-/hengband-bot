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
from tests.test_quest_travel_progress import QuestTravelProgressPins


class QuestPrepareReturnStage2Pins(QuestTravelProgressPins):
    """Reuse only the real-policy fixture construction from the stage-1 pin."""

    __unittest_skip__ = False
    SNAPSHOTS = (
        QuestTravelProgressPins.__module__  # keep unittest discovery explicit
    )

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
                observations.append((number, key, declaration, vector))
            if number == 312:
                break
        self.assertEqual([item[0] for item in observations], [309, 310, 311, 312])
        self.assertEqual([item[1].reason if isinstance(item[1], DecisionCandidate)
                          else "fixedquest:prepare-return" for item in observations],
                         ["fixedquest:prepare-return"] * 4)
        self.assertIsNone(observations[0][2])
        self.assertEqual(len(observations[0][3]), 8)
        self.assertEqual(
            [item[2].producer_branch for item in observations[1:]],
            ["return-1", "return-1", "return-1"],
        )
        # The existing recurrence detector has consumed its unchanged 3/2/1/0
        # allowance by the fourth public producer observation.
        self.assertEqual(policy._town_turn_arbiter.telemetry["budget_remaining_estimate"], 0)
        self.assertIn("quest-request", policy._town_turn_arbiter._retired)
        self.assertEqual(snapshot.turn, 2855985)

    @staticmethod
    def _route_failure(raw, variant):
        derived = copy.deepcopy(raw)
        cells = derived["grid_map"]["cells"]
        for cell in cells:
            if cell.get("b") == 4:
                cell.pop("b")
                cell.pop("p", None)
        if variant in {"known-no-path", "on-inn-no-exit"}:
            cells.append({"x": 0, "y": 0, "b": 4, "p": 0})
        if variant == "on-inn-no-exit":
            derived["player"]["x"] = 0
            derived["player"]["y"] = 0
            grid_map = derived["grid_map"]
            floor_index = next(
                index for index, entry in enumerate(grid_map["palette"])
                if entry[2] & (1 << 5)
            )
            grid_map["runs"] = [[0, 0, 1, floor_index]]
            grid_map["h"] = 1
            grid_map["w"] = 1
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
                self.assertTrue(all(vector == vectors[0] for vector in vectors[:4]))
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
                restored = parse_snapshot(raw, self.monrace)
                restored_key = policy.choose_key(restored)
                self.assertIsInstance(restored_key, DecisionCandidate)
                self.assertEqual(restored_key.reason, "fixedquest:prepare-return")

    def test_procurement_preserves_real_return_3_unavailable_candidate(self):
        raw = self._stage2_records()[-5]
        seed = self._route_failure(raw, "no-inn")
        policy = self._policy(maps=False)
        policy.prime(parse_snapshot(seed, self.monrace))
        # These walls model an unrelated actionable procurement result.  They
        # are consulted only after choose_key's real quest producer has made
        # the candidate on this same policy instance.
        policy._town_procurement_progress_key = lambda _snapshot: (
            "7", "shop:approach"
        )
        policy._town_result_makes_progress = lambda _snapshot, key: key == "7"
        key = policy.choose_key(parse_snapshot(seed, self.monrace))
        policy.confirm_key_posted(key)
        self.assertIsInstance(key, DecisionCandidate)
        self.assertEqual(key.reason, "fixedquest:prepare-return:route-unavailable")
        self.assertEqual(key.route_declaration.producer_branch, "return-3")

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
        self.assertEqual(len(policy._town_arbiter_progress_vector(
            snapshot, collision.reason, collision
        )), 8)


if __name__ == "__main__":
    unittest.main()
