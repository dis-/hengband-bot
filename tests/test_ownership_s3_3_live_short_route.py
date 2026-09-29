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
FIXTURE_SHA256 = "d101903ad128bfcc890f9ef21bcb25c2a57a04fcb33f80ee8920eac4aff91f6c"


class LiveShortRouteTest(unittest.TestCase):
    def test_awaiting_entrance_route_continues_under_claim_140(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         FIXTURE_SHA256)
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            recorded = json.load(stream)
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


if __name__ == "__main__":
    unittest.main()
