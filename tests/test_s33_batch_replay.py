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


class CaptureAdmissionReplayTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
