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
from hengbot.claim_register import reach
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
    policy._claim_register._next_id = prior["claim"]["claim_id"]
    claim = policy._claim_register.declare(
        "store-router", reach(tuple(prior["claim"]["goal"]["cell"])),
        opened_sequence=prior["decision_sequence"],
        floor=tuple(prior["floor"][key] for key in ("dungeon_id", "level", "quest_id")))
    declaration = prior["claim"]["execution"]
    # The recorded prior key was posted. Shadow names its awaiting holder.
    policy._claim_register.declare_execution(
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
            for enforced in (False, True):
                with self.subTest(restored=restored, enforced=enforced):
                    policy, board, scan = attachment("second")
                    # Captured ~f response precedes this decision; no invented
                    # skills and no probe patch. The log records invalidation.
                    policy.consume_skill_knowledge(json.loads(
                        (FIXTURE / "skills.json").read_text(encoding="utf8")))
                    policy._home_knowledge_invalidated = scan[
                        "equipment_optimization"]["home_knowledge_invalidated"]
                    policy._town_claim_bar_enforced = enforced
                    if restored:
                        policy = pickle.loads(pickle.dumps(policy))
                    key = policy.choose_key(board)
                    if enforced:
                        self.assertEqual((key, policy.last_reason), ("3", "shop:approach"))
                        self.assertEqual(policy.decision_claim["owner"], "store-router")
                        self.assertEqual(policy.decision_claim["claim_id"], 8583)
                        self.assertIsNone(policy.decision_claim["violation"])
                    else:
                        self.assertEqual((key, policy.last_reason), (scan["key"], scan["reason"]))
                        self.assertIsNone(policy.decision_claim["s33_shadow"]["would_stop"])
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

    def test_recorded_scan_off_shadow_and_on_gate(self):
        for label in ("first", "second"):
            for restored in (False, True):
                with self.subTest(label=label, restored=restored):
                    policy, board, scan = attachment(label)
                    if restored:
                        policy = pickle.loads(pickle.dumps(policy))
                    # Real producer entry, then exactly the recorded OFF key.
                    self.assertFalse(policy._defer_town_errand(
                        "home-scan", "outside-scan"))
                    policy.last_reason = scan["reason"]
                    if restored:
                        policy = pickle.loads(pickle.dumps(policy))
                    before = pickle.dumps(policy)
                    shadow = policy._s33_shadow_verdict(board, scan["key"])
                    self.assertEqual(pickle.dumps(policy), before)
                    self.assertIsNone(shadow["would_stop"])
                    self.assertIn("home-scan", shadow["would_skip_families"])
                    on = pickle.loads(before)
                    on._town_claim_bar_enforced = True
                    self.assertTrue(on._defer_town_errand(
                        "home-scan", "outside-scan"))
                    self.assertEqual(on._claim_register.current.claim_id,
                                     scan["s33_shadow"]["holder_claim_id"])

    def test_ungated_or_unrelated_entry_cannot_hide_foreign_output(self):
        for label in ("first", "second"):
            for entry in (None, ("home-scan", "other-entry"), ("rumor", "outside-scan")):
                policy, board, scan = attachment(label)
                if entry is not None:
                    policy._defer_town_errand(entry[0], entry[1])
                policy.last_reason = scan["reason"]
                self.assertEqual(policy._s33_shadow_verdict(board, scan["key"])["would_stop"],
                                 "ownership:gate-missing:home-scan")

    def test_matching_gate_does_not_hide_invalid_holder(self):
        policy, board, scan = attachment("second")
        policy._defer_town_errand("home-scan", "outside-scan")
        policy.last_reason = scan["reason"]
        policy._claim_register.declare_execution(
            policy._claim_register.current.claim_id, producer="store-router",
            work_id="route:store:37,91", state="awaiting", arguments=(),
            continuation="route.resume")
        self.assertEqual(policy._s33_shadow_verdict(board, scan["key"])["would_stop"],
                         "ownership:declaration-stale:store-router")


if __name__ == "__main__":
    unittest.main()
