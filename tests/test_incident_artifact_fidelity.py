"""Artifact-only acceptance gate for the 2026-09-12 incident.

This is deliberately not a policy replay.  Decision records remain unattributed
recorded output, while raw snapshot candidates establish only unanimous fields
over every compatible observation.  In particular, this test does not attribute
an item, key posting, policy invocation, blocker set, warm state, or causal
effect to any historical decision.
"""

import gzip
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "destroy-recall-artifact-envelope.json.gz"


def _rows_at_sequence(rows, sequence):
    return [row for row in rows if row.get("decision_sequence") == sequence]


def _one_at_sequence(rows, sequence):
    matches = _rows_at_sequence(rows, sequence)
    if len(matches) != 1:
        raise AssertionError(f"sequence {sequence}: expected one row, got {len(matches)}")
    return matches[0]


def _compatible(decision, snapshot):
    player = snapshot["player"]
    floor = snapshot["floor"]
    return (
        snapshot["turn"] == decision["turn"]
        and (player["y"], player["x"])
        == (decision["position"]["y"], decision["position"]["x"])
        and all(
            floor[name] == decision["floor"][name]
            for name in ("dungeon_id", "level", "quest_id")
        )
        and all(
            player[name] == decision["player"][name]
            for name in ("level", "hp", "max_hp", "mp", "max_mp", "gold", "food_state")
        )
        and len(snapshot["inventory"]) == decision["inventory"]["used"]
        and snapshot["messages"] == decision["messages"]
    )


class IncidentArtifactFidelityTest(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.envelope = json.load(stream)
        cls.decisions = [entry["payload"] for entry in cls.envelope["decision_rows"]]
        cls.decision_by_physical_row = {
            entry["physical_row"]: entry["payload"]
            for entry in cls.envelope["decision_rows"]
        }
        cls.snapshot_entries = cls.envelope["snapshot_candidate_rows"]

    def test_source_identity_and_lossless_row_preservation(self):
        sources = self.envelope["sources"]
        self.assertEqual(self.envelope["head"], "f71e04b6a90efe20c185a36f25d1de9ff305365a")
        self.assertEqual(self.envelope["session_argv"], self.decisions[0]["argv"])

        fixture_rows = self.envelope["decision_rows"]
        for entry in fixture_rows:
            self.assertEqual(entry["source_sha256"], sources["decisions"]["sha256"])
            expected_kind = "session-metadata" if entry["physical_row"] == 0 else "unattributed-recorded-output"
            self.assertEqual(entry["attribution"], expected_kind)

        for entry in self.envelope["snapshot_candidate_rows"]:
            self.assertEqual(entry["source_sha256"], sources["snapshots"]["sha256"])

    def test_destroy_shapes_have_nonempty_unanimous_item_candidates(self):
        for sequence, physical_row, key, slot, projection in (
            (51, 52, "01kg", "g", [70, 15, 1, True, True]),
            (89, 90, "03kh", "h", [70, 26, 3, True, True]),
        ):
            decision = self.decision_by_physical_row[physical_row]
            self.assertEqual(decision["decision_sequence"], sequence)
            self.assertEqual([decision["reason"], decision["key"]], ["town:destroy-overflow", key])
            candidates = [
                (entry["physical_row"], entry["payload"])
                for entry in self.snapshot_entries
                if _compatible(decision, entry["payload"])
            ]
            self.assertTrue(candidates, f"sequence {sequence} has no compatible candidates")
            actual_ordinals = [index for index, _ in candidates]
            self.assertEqual(
                self.envelope["candidate_ordinals"][str(sequence)], actual_ordinals
            )
            projections = []
            for _, row in candidates:
                item = next(item for item in row["inventory"] if item["slot"] == slot)
                projections.append([
                    item["tval"], item["sval"], item["count"],
                    item["known"], item["fully_known"],
                ])
            self.assertEqual(projections, [projection] * len(candidates))

    def test_recall_shape_and_numbering_mappings(self):
        for sequence, physical_row, reason, key in (
            (91, 92, "town:recall-to-angband", "rfa"),
            (92, 93, "town:entrance-step-off:town:await-recall-confirmation", "1"),
            (93, 94, "town:cancel-unready-recall", "rf"),
        ):
            row = self.decision_by_physical_row[physical_row]
            self.assertEqual((row["decision_sequence"], row["reason"], row["key"]), (sequence, reason, key))
            self.assertEqual(row["inventory"]["free"], 4)
            self.assertEqual(row["depth_safety"]["depth"], 1)

        for physical_row, sequence in ((122, 117), (142, 133)):
            row = self.decision_by_physical_row[physical_row]
            self.assertEqual(row["decision_sequence"], sequence)
            wanted = row["shop_selector"]["wanted_purchase"]
            self.assertEqual({key: wanted[key] for key in ("category", "letter", "price")},
                             {"category": "recall", "letter": "k", "price": 237})
        for physical_row, sequence, count in ((177, 162, 10), (178, 163, 9), (185, 168, 10)):
            row = self.decision_by_physical_row[physical_row]
            self.assertEqual(row["decision_sequence"], sequence)
            reservations = row["retention_reservations"]
            recall = next(item for item in reservations if item["tval"] == 70 and item["sval"] == 11)
            self.assertEqual(recall["count"], count)
        for sequence in (122, 142, 177, 178, 185):
            self.assertTrue(_rows_at_sequence(self.decisions, sequence))

    def test_retirement_pairs_and_slot_increase_shape(self):
        for before, after, gold in (
            (104, 105, 7567), (126, 127, 7156), (146, 147, 6682),
            (162, 163, 6208), (177, 178, 5734), (192, 193, 5260),
        ):
            before_rows = _rows_at_sequence(self.decisions, before)
            after_rows = _rows_at_sequence(self.decisions, after)
            self.assertTrue(before_rows and after_rows)
            for row in before_rows:
                self.assertEqual(row["arbiter"]["owner"], "departure")
                self.assertTrue(row["arbiter"]["retired"])
                self.assertIn("departure", row["arbiter"]["retirement_set"])
                self.assertEqual((row["player"]["gold"], row["inventory"]["free"]), (gold, 4))
                self.assertEqual(self._recall_count(row), 10)
            for row in after_rows:
                self.assertEqual(row["arbiter"]["owner"], "departure")
                self.assertFalse(row["arbiter"]["retired"])
                self.assertNotIn("departure", row["arbiter"]["retirement_set"])
                self.assertEqual((row["player"]["gold"], row["inventory"]["free"]), (gold, 4))
                self.assertEqual(self._recall_count(row), 9)

        shop_before, shop_after = _one_at_sequence(self.decisions, 99), _one_at_sequence(self.decisions, 100)
        self.assertTrue(shop_before["arbiter"]["retired"])
        self.assertFalse(shop_after["arbiter"]["retired"])
        self.assertEqual((shop_before["player"]["gold"], shop_after["player"]["gold"]), (7915, 7567))

        for sequence, physical_row, reason, free, gold in (
            (251, 278, "shop:one-shot-sell", 4, 4760),
            (252, 279, "shop:one-shot-in-flight", 5, 4772),
        ):
            row = self.decision_by_physical_row[physical_row]
            self.assertEqual((row["decision_sequence"], row["reason"], row["inventory"]["free"], row["player"]["gold"]),
                             (sequence, reason, free, gold))

    def test_limitations_manifest_is_complete(self):
        required = {
            "exact-head-actions", "cli-posting-attribution", "historical-warm-state",
            "all-read-field-snapshot-equivalence", "complete-blocker-or-certification-state",
            "historical-active-procurement-protection", "causal-explanation-or-savings",
            "candidate-observation-identity", "policy-invocation-count",
        }
        self.assertEqual(set(self.envelope["limitations_manifest"]), required)
        for row in self.envelope["assertions"]:
            self.assertEqual(row["actual"], row["expected"], row["name"])

    @staticmethod
    def _recall_count(row):
        recall = next(
            item for item in row["retention_reservations"]
            if item["tval"] == 70 and item["sval"] == 11
        )
        return recall["count"]


if __name__ == "__main__":
    unittest.main()
