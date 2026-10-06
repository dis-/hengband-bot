"""Recorded partial-page continuation; stop sequential replay at changed ~9.

The final catalogue adoption attaches separately to the real 1124 ~9 response,
not to the historical 1065 re-entry's effect. No future board is invented.
"""
import gzip
import hashlib
import json
from pathlib import Path
import unittest

import tests  # noqa: F401 -- runtime file isolation
from hengbot.claim_register import observe
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy, HOME_KNOWLEDGE_MACRO
from hengbot.cli import _consume_response_sequence

FIXTURE = Path(__file__).parent / "fixtures/catcycle"


def rows(kind):
    with gzip.open(FIXTURE / f"{kind}.jsonl.gz", "rt", encoding="utf8") as source:
        return list(map(json.loads, source))


def attach(enforced=False, crossarea=True):
    raw = rows("state")
    boards = [parse_snapshot(row, {}) for row in raw[:3]]
    policy = HengbotPolicy()
    policy._town_claim_bar_enforced = enforced
    policy._crossarea_fundraising_enforced = crossarea
    policy.prime(boards[0])
    policy.consume_skill_knowledge(raw[3])
    # Recorded registration at 1063, not a fabricated successful operation.
    recorded = rows("decisions")[0]
    policy._decision_sequence = recorded["decision_sequence"]
    goal = recorded["claim"]["goal"]
    holder = policy._claim_register.declare("equipment-txn", observe(
        goal["expectation"], goal["within"], goal["source"]),
        opened_sequence=recorded["decision_sequence"], floor=boards[0].floor_key)
    declaration = recorded["claim"]["execution"]
    policy._claim_register.declare_execution(
        holder.claim_id, producer=declaration["producer"],
        work_id=declaration["work_id"], state=declaration["state"],
        next_step=declaration["next_step"],
        expected_effect=declaration["expected_effect"],
        continuation=declaration["continuation"])
    return policy, boards, raw[-1]


class CatcycleTest(unittest.TestCase):
    def test_frozen_recorded_cycle_and_posted_actions(self):
        provenance = json.loads((FIXTURE / "provenance.json").read_text(encoding="utf8"))
        for name, digest in provenance["fixture_sha256"].items():
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes().replace(
                b"\r\n", b"\n")).hexdigest(), digest)
        decisions = rows("decisions")
        self.assertEqual(len(decisions), 63)
        self.assertEqual([(r["key"], r["reason"]) for r in decisions[1:61]],
                         [(key, reason) for _ in range(30) for key, reason in (
                             ("\x1b", "equipment-transaction:catalogue-leave-for-scan"),
                             ("5", "equipment-transaction:travel-home:await-entry"))])
        posted = rows("posted-characters")
        self.assertEqual([(r["decision"]["sequence"], r["character"])
                          for r in posted if r["decision"]["sequence"] in (1064, 1065)],
                         [(1064, "\x1b"), (1065, "5")])

    def test_partial_home_requests_catalogue_before_other_errands(self):
        for enforced, crossarea in ((False, True), (True, False), (False, False)):
            for restored in (False, True):
                with self.subTest(enforced=enforced, crossarea=crossarea, restored=restored):
                    policy, boards, _ = attach(enforced, crossarea)
                    # Public outside entry prepares the registered work.
                    key = policy.choose_key(boards[0])
                    self.assertEqual(key, rows("decisions")[0]["key"])
                    policy.confirm_key_posted(key)
                    holder_id = policy._claim_register.current.claim_id
                    if not (enforced or crossarea):
                        # Supplemental legacy declaration keeps this path
                        # callable with either sequencing switch OFF.
                        key = policy._home_catalogue_work_key(boards[1])
                        policy._record_decision_claim(boards[1], key)
                    else:
                        key = policy.choose_key(boards[1])
                    self.assertEqual((key, policy.last_reason),
                                     (HOME_KNOWLEDGE_MACRO,
                                      "equipment-transaction:catalogue-request-knowledge"))
                    self.assertEqual((boards[1].store.stock_num, len(boards[1].store.items)), (63, 52))
                    policy.confirm_key_posted(key)
                    if restored:
                        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
                    key = policy.choose_key(boards[2])
                    self.assertEqual((key, policy.last_reason),
                                     ("", "equipment-transaction:catalogue-await-knowledge"))
                    self.assertEqual(policy.decision_claim["claim_id"], holder_id)
                    self.assertEqual(policy.decision_claim["owner"], "equipment-txn")
                    self.assertIsNone(policy.decision_claim["violation"])
                    self.assertEqual(policy._claim_register.current.execution.continuation,
                                     "home.catalogue.acquire")
                    self.assertFalse(policy._home_knowledge_current)
                    # Diverges from recorded 1065's 5: no later historic board.

    def test_in_home_catalogue_reply_adopts_before_next_home_work(self):
        from tempfile import TemporaryDirectory
        for restored in (False, True):
            policy, boards, reply = attach()
            key = policy._home_catalogue_work_key(boards[1])
            policy._record_decision_claim(boards[1], key)
            policy.confirm_key_posted(key)
            holder_id = policy._claim_register.current.claim_id
            if restored:
                policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
            with TemporaryDirectory() as raw:
                _consume_response_sequence([json.dumps(reply)], policy,
                    lambda _key: True, {}, knowledge_ledger_path=Path(raw) / "knowledge.jsonl")
            self.assertEqual(len(policy._home_knowledge_items), 63)
            self.assertTrue(policy._home_knowledge_current)
            self.assertFalse(policy._home_knowledge_invalidated)
            # Independently attach the recorded entrance to the adopted state;
            # this is not a sequential replay of the changed 1065 decision.
            policy.choose_key(boards[2])
            closed = policy.decision_claim["closed_claim"]
            self.assertEqual(closed["claim_id"], holder_id)
            self.assertEqual((closed["closed"], closed["closed_reason"]),
                             ("complete", "home-knowledge-current"))

    def test_posted_scan_waits_for_reply_without_reissuing(self):
        # Supplemental delayed-response seam, not a historical next-board claim.
        policy, boards, _ = attach()
        key = policy._home_catalogue_work_key(boards[1])
        policy._record_decision_claim(boards[1], key)
        policy.confirm_key_posted(key)
        scan = policy.choose_key(boards[2])
        self.assertEqual(scan, "")
        self.assertEqual(policy.last_reason,
                         "equipment-transaction:catalogue-await-knowledge")
        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        key = policy.choose_key(boards[2])
        self.assertEqual(key, "")
        self.assertEqual(policy.last_reason, "equipment-transaction:catalogue-await-knowledge")
        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertEqual(policy._claim_register.current.execution.state, "awaiting")
        self.assertEqual(policy._claim_register.current.execution.operation_ref,
                         f"decision:{policy._decision_sequence - 2}:{HOME_KNOWLEDGE_MACRO}")


if __name__ == "__main__":
    unittest.main()
