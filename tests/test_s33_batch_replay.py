"""DECLARED CONSTRUCTED admission replay for the captured family pairings.

The tails record the holders and rejected producers but omit their restorable
checkpoint. Rebuild only that admission seam on the declared corridor, then
exercise admitted survival through choose_key. This is not a continuous tour
or a replay of the historical command effects. The physical transaction,
arrival, resume and target pins live in the other focused modules.
"""
from collections import defaultdict
from dataclasses import replace
import gzip
import json
import unittest

import tests  # noqa: F401
from hengbot.claim_register import reach, observe
from hengbot.policy import HengbotPolicy
from hengbot.model import parse_snapshot
from pathlib import Path
from test_s33_batch_admission import FIXTURE, corridor


def admission_replays():
    pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    results = []
    cases = []
    for pin in pins:
        shadow = pin["row"].get("claim", {}).get("s33_shadow") or {}
        stop = shadow.get("would_stop") or ""
        if "gate-missing:" not in stop:
            continue
        holder, foreign = shadow["holder_family"], stop.rsplit(":", 1)[1]
        if "calibration" in (holder, foreign):
            continue  # Superseded path, not current live debt.
        cases.append((pin["source"], pin["line"], holder, foreign))
    # The plan records the latest Q2 pair at 20:31:55-20:33:14, but its
    # full rotating decision rows/checkpoint are absent from the copied files.
    # DECLARED CONSTRUCTED summary-only seam; never pretend it is a source row.
    cases.append(("S33-PLAN.md latest Q2 (summary-only, DECLARED CONSTRUCTED)",
                  None, "cross-town", "quest-request"))
    for source, line, holder, foreign in cases:
        board = corridor()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = True
        claim = policy._claim_register.declare(holder, reach((10, 14)), floor=board.floor_key)
        policy._claim_register.declare_execution(claim.claim_id,
            producer=holder, work_id="captured-pair:constructed-route", state="acting",
            next_step="route.resume", arguments=("store", (10, 14)),
            expected_effect="arrive", continuation="route.resume", budget_ref="town-travel")
        mutations = []
        output = policy._town_producer_entry("capture-foreign-entry",
                    lambda: mutations.append(foreign), family=foreign)
        # The admitted decision is a real survival interruption of this holder.
        low = replace(board, player=replace(board.player, hp=1))
        key = policy.choose_key(low)
        diagnostic = policy._s33_shadow_verdict(low, key)
        results.append(dict(source=source, line=line,
            holder=holder, foreign=foreign, foreign_output=output, mutations=mutations,
            key=key, reason=policy.last_reason, would_stop=diagnostic["would_stop"],
            declaration_mismatch=policy.decision_claim["declaration_mismatch"],
            claim_verdict_conflict=policy.decision_claim["claim_verdict_conflict"]))
    return results


class CaptureAdmissionReplayTest(unittest.TestCase):
    def test_current_admission_and_admitted_survival_for_every_captured_pair(self):
        results = admission_replays()
        self.assertGreater(len(results), 30)
        self.assertTrue(any(row["holder"] == "cross-town" and row["foreign"] == "quest-request"
                            for row in results))
        for row in results:
            with self.subTest(source=row["source"], line=row["line"]):
                self.assertIsNone(row["foreign_output"])
                self.assertEqual(row["mutations"], [])
                self.assertEqual(row["key"], "R&\r")
                self.assertEqual(row["reason"], "town:recover")
                self.assertIsNone(row["would_stop"])
                self.assertIsNone(row["declaration_mismatch"])
                self.assertIsNone(row["claim_verdict_conflict"])

    def test_a1958_duplicate_target_has_a_current_admitted_identification(self):
        # DECLARED CONSTRUCTED public-decision seam: actual source h and
        # duplicate targets m/n on the isolated town corridor. The capture
        # lacks an onset checkpoint; no old command effects follow this key.
        recorded = parse_snapshot(json.loads((Path(__file__).parent /
            "fixtures/identify-scroll-target/before-rhm.json").read_text(encoding="utf8")))
        selected = tuple(item for item in recorded.inventory if item.slot in {"h", "m", "n"})
        self.assertEqual({item.slot for item in selected}, {"h", "m", "n"})
        board = replace(corridor(), inventory=selected)
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = True
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        target = next(item for item in selected if item.slot == "m")
        signature = policy._item_signature(target)
        policy._home_pending_item = signature
        claim = policy._claim_register.declare("identification",
            observe(("constructed-duplicate-identification",), 8, source="item"), floor=board.floor_key)
        policy._claim_register.declare_execution(claim.claim_id, producer="identification",
            work_id=f"identify:home-item:{signature}", state="acting",
            next_step="identification.use-carried-source", arguments=(signature, False),
            expected_effect="carried-item-identified")
        key = policy.choose_key(board)
        self.assertEqual(key, "rhm")
        self.assertEqual(policy.last_reason, "identify:normal")
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])


if __name__ == "__main__":
    unittest.main()
