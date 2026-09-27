"""Recorded 2026-09-27 Outpost Home handoff after the Alchemist visit.

The capture gives the complete Home knowledge response, the input board of
decision 20135, and the decision/departure trace. The in-memory Home plan and
pending withdrawal are reconstructed from that trace. This is the declared
wall: earlier shopping decisions are pinned as recorded facts, then the Home
approach producer runs on the recorded 20135 board. Its first divergence is a
filed Home take instead of the recorded blocked/probe window. The old
identification-only plan projection is retained to exercise the exact refusal.
"""

import tests  # noqa: F401

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import STORE_HOME, TVAL_BOLT, _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownErrandPlan
from hengbot.protocol import snapshot_protocol_version


FIXTURE = (
    Path(__file__).parent / "fixtures"
    / "town-home-candidate-stall-20260927.json.gz"
)
FIXTURE_SHA256 = "99501ba3dfb757fd0387229b6410915e30737d4ef08c73438104e77554742e6c"


class TownHomeCandidateStallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.capture = json.load(stream)
        cls.board = parse_snapshot(cls.capture["board"])

    def _stalled_handoff(self):
        policy = HengbotPolicy()
        policy.prime(self.board)
        knowledge = self.capture["knowledge"]
        policy.consume_home_knowledge(tuple(_parse_items(
            knowledge["knowledge"]["items"],
            protocol=snapshot_protocol_version(knowledge),
        )))
        carried = next(
            item for item in self.board.inventory if item.tval == TVAL_BOLT
        )
        home_bolts = next(
            item for item in policy._home_knowledge_items
            if item.tval == TVAL_BOLT and item.name == carried.name
        )
        # The recorded plan still labels Home as the post-Alchemist identify
        # stop. The source scroll was consumed and its errand is no longer live.
        policy._town_errand_plan = TownErrandPlan(
            [4, STORE_HOME, 3, 2, 6],
            {STORE_HOME: ("identification-withdrawal",)},
            index=1,
        )
        policy._home_pending_item = policy._item_signature(home_bolts)
        policy._home_pending_quantity = 13
        policy._home_withdrawal_queued = True
        policy._home_candidate_waiting = True
        return policy, carried, home_bolts

    def test_capture_pins_first_divergence_and_two_failed_conjuncts(self):
        pins = {row["decision_sequence"]: row for row in self.capture["pins"]}
        self.assertEqual(
            [(pins[n]["key"], pins[n]["reason"]) for n in
             (20113, 20114, 20116, 20118, 20119, 20120, 20122, 20123, 20135)],
            [
                ("5pr1\r\x1b", "home-errand:atomic-withdraw:identification"),
                ("rgk" + "\x1b" * 8, "identify:full"),
                ("dj\x1b", "home:weight-overload-deposit"),
                ("~9\x1b\x1b", "home:request-knowledge-scan"),
                ("\x1b`n%.", "shop:travel"),
                ("\x1b", "town-progress-invariant:continue-observed-shop"),
                ("pi2\r\r\x1b", "shop:one-shot-buy"),
                ("8", "probe"),
                ("5", "town:blocked:no-actionable-claim-owner"),
            ],
        )
        self.assertEqual(
            pins[20135]["departure_block"]["failed"],
            ["home_candidate_resolved", "home_pending_item_clear"],
        )
        self.assertEqual(pins[20135]["town_plan"]["index"], 1)
        self.assertTrue(pins[20135]["home_candidate_waiting"])
        policy, carried, home_bolts = self._stalled_handoff()
        self.assertEqual((carried.count, home_bolts.count), (86, 20))
        self.assertEqual(len(policy._home_knowledge_items), 174)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertTrue(any(
            "HEAVY_CURSE" in item["name"]
            for item in self.capture["board"]["equipment"]
            if item["slot"] == "body"
        ))
        self.assertTrue(any(
            item["tval"] == 70 and item.get("sval") == 15
            for item in self.capture["knowledge"]["knowledge"]["items"]
        ))

    def test_new_pending_ammo_owns_stale_identification_home_stop(self):
        policy, _, home_bolts = self._stalled_handoff()
        self.assertFalse(policy._home_errand.active)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_HOME],
            ("identification-withdrawal",),
        )
        step = policy._shopping_approach_step(
            self.board, STORE_HOME, requester="store-router"
        )
        self.assertIsNotNone(step)
        self.assertEqual(policy._home_visit.request.item_identity,
                         policy._item_signature(home_bolts))
        self.assertEqual(policy._home_visit.request.quantity, 13)
        self.assertIsNone(policy.home_route_refusal_state())

    def test_without_concrete_take_stale_identification_stop_still_waits(self):
        policy, _, _ = self._stalled_handoff()
        policy._home_pending_item = None
        policy._home_withdrawal_queued = False
        self.assertIsNone(policy._shopping_approach_step(
            self.board, STORE_HOME, requester="store-router"
        ))
        self.assertIsNone(policy._home_visit.request)

    def test_observed_ammo_gain_resolves_both_recorded_departure_failures(self):
        policy, _, _ = self._stalled_handoff()
        # The Home operation composer releases the queued address when it
        # posts the take; this board represents its confirming inventory gain.
        policy._home_withdrawal_queued = False
        observed = replace(
            self.board,
            inventory=[
                replace(item, count=99) if item.tval == TVAL_BOLT else item
                for item in self.board.inventory
            ],
        )
        self.assertIsNone(policy._town_item_processing_key(observed))
        self.assertIsNone(policy._home_pending_item)
        policy._release_stale_home_candidate_waiting(observed)
        conjuncts = policy._recall_town_departure_conjuncts(observed)
        self.assertTrue(conjuncts["home_candidate_resolved"])
        self.assertTrue(conjuncts["home_pending_item_clear"])


if __name__ == "__main__":
    unittest.main()
