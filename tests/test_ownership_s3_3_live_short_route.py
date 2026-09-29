"""Decision 224 of the 2026-09-29 live stop, with its recorded board and claim.

The capture has a policy-state projection, not a restorable policy checkpoint.
The claim register is therefore rebuilt from the decision row; the board is
unmodified. The preceding travel ended at distance five from its entrance.
"""

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

import tests  # noqa: F401
from hengbot.claim_register import ClaimState, reach
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ENTRANCE_TRAVEL_MACRO, HengbotPolicy
from hengbot.policy_types import TownTravelProgress


FIXTURE = Path(__file__).parent / "fixtures/s33-live-short-entrance-224.json.gz"
FIXTURE_SHA256 = "c57f7f152b6deb983bc666260351834e8e0bcdab61c54c88c515fec176ad4321"


class LiveShortRouteTest(unittest.TestCase):
    @staticmethod
    def _recording():
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            return json.load(stream)

    def test_awaiting_entrance_route_continues_under_claim_140(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         FIXTURE_SHA256)
        recorded = self._recording()
        row = recorded["decision"]
        prior = recorded["prior_decision"]
        board = parse_snapshot(recorded["snapshot"], load_monrace_knowledge(
            Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")))
        claim_row = row["claim"]
        self.assertEqual((row["decision_sequence"], row["reason"],
                          claim_row["claim_id"], claim_row["goal"]["cell"],
                          claim_row["distance"], claim_row["state"]),
                         (224, "ownership:holder-silent:store-router", 140,
                          [31, 150], 5, "awaiting"))
        self.assertEqual((prior["decision_sequence"], prior["reason"],
                          prior["claim"]["distance"]),
                         (223, "town:travel-entrance", 59))
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = True
        policy._decision_sequence = 223
        policy._claim_register._next_id = 140
        claim = policy._claim_register.declare(
            "store-router", reach(tuple(claim_row["goal"]["cell"])),
            opened_sequence=223, floor=board.floor_key,
            opened_turn=board.turn - 1,
        )
        policy._claim_register._claim = replace(claim, state=ClaimState.AWAITING)
        # The fixture predates serialized declarations. Rebuild the posted
        # route identity from decision 223, as the live declaration writer does.
        policy._claim_register.declare_execution(
            claim.claim_id, work_id="route:entrance:31:150",
            producer="store-router", state="awaiting",
            next_step="route.resume", arguments=("entrance", (31, 150)),
            operation_ref="decision:223", expected_effect="store-page-open",
            continuation="route.resume", budget_ref="route-existing-budget",
        )
        policy._town_travel_state = TownTravelProgress(
            Position(31, 150), prior["claim"]["distance"], 0, 0,
            prior["turn"],
        )
        key = policy._town_holder_wait_key(policy._claim_register.current, board)
        self.assertEqual(key, ENTRANCE_TRAVEL_MACRO)
        self.assertEqual(policy._town_travel_state.best_distance, 5)
        self.assertEqual(policy._claim_register.current.claim_id, 140)
        self.assertEqual(policy._claim_register.current.goal.cell, (31, 150))
        self.assertEqual(policy._claim_register.current.budget,
                         claim_row["budget"])
        self.assertTrue(policy._claim_register.current.is_open)
        self.assertNotEqual(policy.last_reason, "ownership:holder-silent:store-router")

    def test_open_store_reach_walks_when_plan_identity_is_lost(self):
        # Class scenario: the 224 board with the recorded store goal from
        # decision 219, but no shopping plan or visit. This is not a replay
        # of decision 219; it covers the same awaiting-state final branch.
        recorded = self._recording()
        board = parse_snapshot(recorded["snapshot"], load_monrace_knowledge(
            Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")))
        store = recorded["store_route_decision"]
        self.assertEqual((store["decision_sequence"],
                          store["claim"]["goal"]["cell"]),
                         (219, [31, 119]))
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = True
        claim = policy._claim_register.declare(
            "store-router", reach((31, 119)), floor=board.floor_key,
        )
        policy._claim_register._claim = replace(claim, state=ClaimState.AWAITING)
        policy._claim_register.declare_execution(
            claim.claim_id, work_id="route:store:31:119",
            producer="store-router", state="awaiting",
            next_step="route.resume", arguments=("store", (31, 119)),
            operation_ref="decision:219", expected_effect="store-page-open",
            continuation="route.resume", budget_ref="route-existing-budget",
        )
        key = policy._town_holder_wait_key(policy._claim_register.current, board)
        self.assertIn(key, "12346789")
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(policy._claim_register.current.goal.cell, (31, 119))


if __name__ == "__main__":
    unittest.main()
