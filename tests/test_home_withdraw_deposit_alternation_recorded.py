"""Recorded 2026-09-27 Home identification / overweight owner collision.

The fixture preserves selected full state rows and decision boards from the
read-only incident capture.  Decision 591 is the first changed decision: the
live policy chose the just-withdrawn club for a staged Home deposit.  Earlier
keys are pinned exactly; later live rows prove that both operations completed
and then repeated.  The retention view at 591 is replayed from that board so
the selector sees the same visit purchases and supply reservations.
"""

from __future__ import annotations

import tests  # noqa: F401
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / (
    "home-withdraw-deposit-alternation-20260927.json.gz"
)
FIXTURE_SHA256 = "7830cbfad507724dc8228a89a477a28d26536640aa666c2d9048d3df8b652fb6"
CLUB = ("人喰いの鉄棒 (2d7) (+7,+5) (+3隠密)", 21, 16)


class HomeWithdrawDepositAlternationRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.capture = json.load(stream)
        cls.states = cls.capture["states"]
        cls.decisions = cls.capture["decisions"]

    @staticmethod
    def _club_count(items):
        return sum(item["count"] for item in items if (
            item["name"], item["tval"], item["sval"]
        ) == CLUB)

    def test_recorded_keys_and_actual_home_inventory_deltas(self):
        # R4: stop key/reason pins at the first changed decision, 591.
        expected = {
            587: ("shop:travel:await-entry", "5"),
            588: ("home:request-knowledge-scan", "~9\x1b"),
            589: ("home:route-claim-unfulfilled", "\x1b"),
            590: ("home-errand:atomic-withdraw:identification-catalog", "5  pV\x1b"),
            591: ("home:weight-overload-deposit", "5"),
        }
        for number, pair in expected.items():
            board = self.decisions[str(number)]
            self.assertEqual((board["reason"], board["key"]), pair)
        self.assertEqual(self.decisions["590"]["home_atomic_withdraw"]["selected_signature"], list(CLUB))
        self.assertEqual(self.decisions["590"]["home_atomic_withdraw"]["resolved_index"], 151)
        self.assertEqual(self.decisions["590"]["home_atomic_withdraw"]["quantity"], 1)
        self.assertEqual(self.decisions["591"]["claim"]["goal"]["expectation"][2], "dl\x1b")
        for before, withdrawn, deposited in ((1477, 1478, 1482), (1492, 1493, 1497)):
            self.assertEqual(self._club_count(self.states[str(before)]["store"]["items"]), 1)
            self.assertEqual(self._club_count(self.states[str(withdrawn)]["store"]["items"]), 0)
            self.assertEqual(self._club_count(self.states[str(withdrawn)]["inventory"]), 1)
            self.assertEqual(self._club_count(self.states[str(deposited)]["inventory"]), 0)
            self.assertEqual(self._club_count(self.states[str(deposited)]["store"]["items"]), 1)

    def test_first_divergence_preserves_identification_then_clears_weight(self):
        snapshot = parse_snapshot(self.states["1479"])
        policy = HengbotPolicy()
        board = self.decisions["591"]
        reservations = {
            tuple(row["signature"]): row["reservation"]
            for row in board["retention_reservations"]
        }
        reservation = lambda _snapshot, item: reservations.get(
            policy._item_signature(item), 0
        )
        club = next(item for item in snapshot.inventory if policy._item_signature(item) == CLUB)
        self.assertEqual(policy._inventory_weight(snapshot), 1659)
        self.assertEqual(policy._inventory_weight_limit(snapshot), 1650)
        self.assertTrue(policy._identification_flow_owns(club))
        with patch.object(policy, "_retention_reservation", side_effect=reservation):
            # Revert proof: without the new exclusion, the captured selector
            # chooses the club and recreates the live cycle.
            with patch.object(policy, "_identification_flow_owns", return_value=False):
                self.assertEqual(policy._overweight_home_deposit(snapshot).slot, "l")
            selected = policy._overweight_home_deposit(snapshot)
            self.assertEqual(selected.slot, "b")
            self.assertEqual(policy._find_home_deposit(snapshot).slot, "b")
            self.assertNotEqual(policy._item_signature(selected), CLUB)
            shed = replace(snapshot, inventory=[
                item for item in snapshot.inventory if item.slot != selected.slot
            ])
            self.assertEqual(policy._inventory_weight(shed), 1655)
            self.assertIsNone(policy._overweight_home_deposit(shed))
            self.assertIsNone(policy._find_home_deposit(shed))
            identified = replace(shed, inventory=[
                replace(item, fully_known=True) if item.slot == club.slot else item
                for item in shed.inventory if item.tval != 70 or item.sval != 13
            ])
            self.assertEqual(policy._inventory_weight(identified), 1650)
            self.assertFalse(policy._inventory_overweight(identified))
            self.assertFalse(policy._identification_flow_owns(next(
                item for item in identified.inventory if item.slot == club.slot
            )))


if __name__ == "__main__":
    unittest.main()
