"""Recorded scan entry verdicts, with no boards consumed after ON divergence.

The first state log lost the incident board: that case attaches only to the
recorded claim/gate seam, with no synthetic Snapshot. The second uses its real
outside board and the production entry gate and holder dispatch. A final-only
foreign key is deliberately a leak; shadow may excuse only the matching entry.
"""
import gzip
import hashlib
import json
import pickle
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot import town_hold
from hengbot.town_hold import reach_goal as reach
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase

FIXTURE = Path(__file__).parent / "fixtures/live37-home-scan"


def rows(label, kind):
    with gzip.open(FIXTURE / f"{label}.{kind}.jsonl.gz", "rt", encoding="utf8") as f:
        return list(map(json.loads, f))


def attachment(label):
    prior, scan = rows(label, "decisions")
    policy = HengbotPolicy()
    policy._decision_sequence = scan["decision_sequence"]
    policy._town_hold.claims._next_id = prior["claim"]["claim_id"]
    claim = policy._town_hold.claims.declare(
        "store-router", reach(tuple(prior["claim"]["goal"]["cell"])),
        opened_sequence=prior["decision_sequence"],
        floor=tuple(prior["floor"][key] for key in ("dungeon_id", "level", "quest_id")))
    declaration = prior["claim"]["execution"]
    # The recorded prior key was posted. Shadow names its awaiting holder.
    policy._town_hold.claims.declare_execution(
        claim.claim_id, producer=declaration["producer"], work_id=declaration["work_id"],
        state="awaiting", arguments=("store", tuple(declaration["arguments"][1])),
        operation_ref=f"decision:{prior['decision_sequence']}:{prior['key']}",
        expected_effect=declaration["expected_effect"],
        continuation=declaration["continuation"], budget_ref=declaration["budget_ref"])
    visit = prior["store_visit"]
    policy._store_visit = StoreVisit(
        visit["owner"], visit["purpose"], visit["store_type"],
        phase=StoreVisitPhase(visit["phase"]), opened_sequence=visit["opened_sequence"],
        opened_for_family="shop-buy", requester_families=frozenset({"shop-buy"}))
    board = None
    if label == "second":
        raw = next(row for row in rows(label, "state")
                   if row.get("type") == "player_turn" and row["turn"] == scan["turn"])
        board = parse_snapshot(raw, {})
        policy.prime(board)
        policy._map_predicate_snapshot = board
    return policy, board, scan


class Live37HomeScanTest(unittest.TestCase):
    def test_second_recorded_board_public_off_shadow_and_on_continuation(self):
        for restored in (False, True):
            for enforced in (False,):
                with self.subTest(restored=restored, enforced=enforced):
                    policy, board, scan = attachment("second")
                    # Captured ~f response precedes this decision; no invented
                    # skills and no probe patch. The log records invalidation.
                    policy.consume_skill_knowledge(json.loads(
                        (FIXTURE / "skills.json").read_text(encoding="utf8")))
                    policy._home_knowledge_invalidated = scan[
                        "equipment_optimization"]["home_knowledge_invalidated"]
                    if restored:
                        policy = pickle.loads(pickle.dumps(policy))
                    key = policy.choose_key(board)
                    if enforced:
                        # S3.3's declared route continuation resumes the posted
                        # transport under the same holder instead of inventing
                        # an unrelated one-cell walk after the deferred scan.
                        self.assertEqual((key, policy.last_reason),
                                         ("\x1b`n(.", "shop:travel"))
                        self.assertEqual(town_hold.standing_claim(policy).owner.value, "store-router")
                        self.assertEqual(town_hold.standing_claim(policy).claim_id, 8583)
                    else:
                        self.assertEqual((key, policy.last_reason), (scan["key"], scan["reason"]))
                    # The next historical board followed ~9. Do not consume it
                    # as evidence of the ON key 3 succeeding or failing.

    def test_frozen_capture_and_actual_gate_evidence(self):
        provenance = json.loads((FIXTURE / "provenance.json").read_text(encoding="utf8"))
        for name, digest in provenance["fixture_sha256"].items():
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest(), digest)
        for label, sequence, holder in (("first", 3106, 2566), ("second", 9682, 8583)):
            policy, board, scan = attachment(label)
            self.assertEqual(scan["decision_sequence"], sequence)
            self.assertEqual(scan["s33_shadow"]["holder_claim_id"], holder)
            self.assertEqual(scan["claim"]["errand_deferred"], [{
                "holder_family": "store-router", "holder_claim_id": holder,
                "deferred_family": "home-scan", "deferred_reason": "outside-scan",
                "token_would_admit": False, "token_work_identity": None}])
            self.assertEqual((scan["key"], scan["reason"]),
                             ("~9\x1b\x1b", "home:request-knowledge-scan"))
            self.assertEqual(policy._store_visit.store_type, 4)
            self.assertEqual(policy._store_visit.purpose, "shopping")
            self.assertEqual(policy._store_visit.phase.value, "entering")

if __name__ == "__main__":
    unittest.main()
