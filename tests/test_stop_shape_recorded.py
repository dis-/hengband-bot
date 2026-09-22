"""Recorded pins: the stop-shape classifier on the three stops of 2026-09-23.

Fixture: tests/fixtures/ownership-stop-shapes-20260923.jsonl.gz, written by
tests/extract_ownership_stop_shapes_fixture.py from the automatic captures and
pinned here by sha256.  It holds each capture's own ``meta.json`` (the stop
kind and the driver's 20-reason window as it stood at the stop) and the last
24 decision rows projected onto the fields the classifier reads.

pin_vacuity: the pins do not call the classifier with hand-made arguments.
Each one drives the production ledger (``OwnershipMetricsLedger``) over the
frozen rows exactly as ``cli._write_decision`` does, then stops it with the
recorded kind and reason window exactly as ``cli.incident_stop`` does, and
reads the shape out of the record the ledger wrote.  A classifier that only
worked when called directly would fail here.

Expected shapes (design section 6, S0):
  01:43 no-key-exhausted -> unobserved-effect (the store visit is still
        entering on decision 1905's posted sequence, and decision 1906 says so
        in its reason: store:entry-await-observation)
  03:44 loop-detected    -> no-exit (one owner, town-plan, emitted
        town:blocked:equipment-calibration-required for the whole window with
        its arbiter claim already retired)
  06:00 loop-detected    -> ownership-alternation (seek-loot and
        detected:prepare-choke took the decision from each other for nine
        cycles in the dungeon, where no arbiter runs)
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import tests  # noqa: F401  (bare runs stay isolated from runtime files)
from hengbot.ownership_metrics import OwnershipMetricsLedger
from hengbot.stop_shape import (
    SHAPE_NO_EXIT,
    SHAPE_OTHER,
    SHAPE_OWNERSHIP_ALTERNATION,
    SHAPE_UNOBSERVED_EFFECT,
    classify_stop,
    producer_identity,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ownership-stop-shapes-20260923.jsonl.gz"
FIXTURE_SHA256 = "c8f4e20b9fb9dcde9281c2be58fd1951eec5f64dc5bb837acd3edcd1d77c1f02"
EXPECTED = {
    "20260923-014342-no-key-exhausted": SHAPE_UNOBSERVED_EFFECT,
    "20260923-034402-loop-detected": SHAPE_NO_EXIT,
    "20260923-060018-loop-detected": SHAPE_OWNERSHIP_ALTERNATION,
}


def _records() -> dict[str, dict]:
    with gzip.open(FIXTURE, "rb") as stream:
        return {
            record["capture"]: record
            for record in (json.loads(line) for line in stream)
        }


class RecordedStopShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _records()

    def _ledger_verdict(self, capture: str) -> dict:
        """The record the production ledger writes for this recorded stop."""
        record = self.records[capture]
        with tempfile.TemporaryDirectory(prefix="hengbot-stop-shape-") as root:
            ledger = OwnershipMetricsLedger(Path(root) / "ownership-metrics.jsonl")
            ledger.note_session_start({"time": "2026-09-23T00:00:00+0900"})
            for row in record["rows"]:
                ledger.note_decision(row)
            return ledger.note_stop(
                record["meta"]["kind"], record["meta"]["last_reasons"]
            )

    def test_fixture_is_the_frozen_capture_evidence(self):
        self.assertEqual(
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256
        )
        self.assertEqual(sorted(self.records), sorted(EXPECTED))
        for capture, record in self.records.items():
            with self.subTest(capture=capture):
                self.assertEqual(len(record["meta"]["last_reasons"]), 20)
                self.assertEqual(len(record["rows"]), 24)
                self.assertTrue(capture.startswith(record["meta"]["time"][:4]))
                # The trailing stop report is not a decision and was dropped.
                self.assertNotEqual(
                    record["rows"][-1]["reason"], record["meta"]["kind"]
                )

    def test_each_recorded_stop_has_its_expected_shape(self):
        for capture, shape in EXPECTED.items():
            with self.subTest(capture=capture):
                self.assertEqual(self._ledger_verdict(capture)["shape"], shape)

    def test_the_0143_stop_names_the_operation_whose_effect_was_never_seen(self):
        verdict = self._ledger_verdict("20260923-014342-no-key-exhausted")
        self.assertEqual(verdict["rule"], "posted-operation-effect-unobserved")
        evidence = verdict["evidence"]
        self.assertEqual(evidence["terminal_reason"], "store:entry-await-observation")
        self.assertEqual(evidence["in_flight_clause"], "entering-with-posted-sequence")
        self.assertEqual(evidence["posted_sequence"], 1905)
        self.assertIs(evidence["operation_effect_observed"], False)
        self.assertEqual(evidence["terminal_decision_sequence"], 1906)
        # The turn was held by town-errand while detectors produced the post
        # one decision earlier: a relabelled emit, recorded but not the rule.
        self.assertEqual(evidence["arbiter_owner"], "town-errand")
        self.assertEqual(evidence["arbiter_producer_owner"], "store-router")

    def test_the_0344_stop_names_the_owner_that_could_not_be_cleared(self):
        verdict = self._ledger_verdict("20260923-034402-loop-detected")
        self.assertEqual(verdict["rule"], "repeated-reason-suffix")
        evidence = verdict["evidence"]
        self.assertEqual(
            evidence["repeated_reason"],
            "town:blocked:equipment-calibration-required",
        )
        self.assertEqual(evidence["repeated_decisions"], 20)
        self.assertEqual(evidence["repeated_producer"], "town-plan")
        self.assertIs(evidence["arbiter_retired"], True)

    def test_the_0600_stop_names_both_producers_and_the_cycles(self):
        verdict = self._ledger_verdict("20260923-060018-loop-detected")
        self.assertEqual(verdict["rule"], "alternating-producer-suffix")
        evidence = verdict["evidence"]
        self.assertEqual(
            evidence["alternating_producers"],
            ["misc:seek-loot", "unregistered:detected"],
        )
        self.assertEqual(evidence["cycles"], 9)
        self.assertEqual(evidence["alternating_decisions"], 18)
        # The dungeon has no arbiter at all, which is the design's blind spot.
        self.assertIsNone(evidence["arbiter_owner"])
        self.assertIsNone(evidence["arbiter_producer_owner"])

    def test_the_three_shapes_are_not_interchangeable(self):
        """Each capture's window decides only its own shape.

        Revert-proof: a classifier that returned one shape for everything, or
        that read only the stop kind (two of the three stops share
        ``loop-detected``), cannot pass this.
        """
        verdicts = {
            capture: self._ledger_verdict(capture)["shape"] for capture in EXPECTED
        }
        self.assertEqual(len(set(verdicts.values())), 3)
        kinds = {self.records[c]["meta"]["kind"] for c in EXPECTED}
        self.assertEqual(len(kinds), 2)

    def test_a_window_with_no_evidence_is_other_rather_than_a_shape(self):
        """``other`` is not a bucket for unproven ownership claims."""
        verdict = classify_stop(
            kind="stuck-prompt",
            reasons=["explore", "melee", "seek-loot", "explore"],
            terminal={"reason": "explore", "decision_sequence": 12},
        )
        self.assertEqual(verdict.shape, SHAPE_OTHER)
        self.assertEqual(verdict.rule, "no-rule-matched")

    def test_producer_identity_separates_the_arbiter_catch_all_families(self):
        self.assertEqual(producer_identity("town:blocked:x"), "town-plan")
        self.assertEqual(producer_identity("shop:travel"), "store-router")
        # Both of these land in the arbiter's catch-alls and must stay apart.
        self.assertNotEqual(producer_identity("seek-loot"), producer_identity("melee"))
        self.assertNotEqual(
            producer_identity("seek-loot"), producer_identity("detected:prepare-choke")
        )


if __name__ == "__main__":
    unittest.main()
