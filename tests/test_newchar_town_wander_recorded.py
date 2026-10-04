"""R4 capture pins for the 2026-09-28 poor-character town wander.

Source decisions SHA256: 482c2d5e7cd5b677721ebf7d2f4e2eaa0e330c4d93c19097307a03a6269405e7.
Source state SHA256: ed281bb83ebf67a4dc2c04388c8d2ea13b88607977dde4e69a91c4899f80b3fe.
Rows retain their original one-based source lines and complete board values.
"""

import tests  # noqa: F401  -- bare-module runtime isolation

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownErrandPlan


FIXTURE = Path(__file__).parent / "fixtures" / "newchar-town-wander-20260928.jsonl.gz"
FIXTURE_SHA256 = "8e903bc8dccb31ed7d8b111ed4bd40a512e7c50e40867b04c2539390ea4cf672"


class NewCharacterTownWanderRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = {(row["kind"], row["source_line"]): row["value"]
                        for row in map(json.loads, stream)}

    def snapshot(self, line):
        return parse_snapshot(self.rows["state", line], {})

    def test_purchase_was_affordable_and_completed_before_wander(self):
        observed = self.rows["decisions", 345]
        before = self.rows["decisions", 346]
        after = self.rows["decisions", 347]
        self.assertEqual(observed["shop_selector"]["winning_rung"],
                         "shop:observe-and-leave")
        self.assertEqual(observed["store_visit"]["store_type"], 4)
        self.assertEqual((before["reason"], before["key"]),
                         ("shop:one-shot-buy", "pr5\r\r\x1b"))
        self.assertEqual(before["shop_selector"]["wanted_purchase"], {
            "category": "treasure-detection", "name": "財宝感知の巻物",
            "letter": "r", "price": 25, "count": 46,
        })
        self.assertEqual((before["player"]["gold"], after["player"]["gold"]),
                         (136, 11))
        self.assertEqual(self.snapshot(497).player.gold, 11)
        self.assertEqual(after["town_plan"],
                         {"stops": ["Alchemist"], "index": 1,
                          "inserted_this_visit": [], "skipped_latched": []})
        self.assertEqual(after["fundraising"]["mode"], "prepare")
        self.assertIsNone(after.get("departure_block"))
        self.assertEqual(after["descent_refusal"], "recall-departure-shortage")
        self.assertEqual(after["arbiter"]["decision_attribution"], "town-plan")
        self.assertEqual(self.rows["decisions", 348]["reason"], "stuck:wander")

    def test_exhausted_partial_kit_resolves_to_fundraising_fallback(self):
        snapshot = self.snapshot(497)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_errand_plan = TownErrandPlan(stops=[4], index=1)
        self.assertEqual(policy._count_treasure_detection_scrolls(snapshot), 5)
        self.assertFalse(policy._has_digging_tool(snapshot))
        self.assertFalse(policy._fundraising_supplies_ready(snapshot))
        self.assertIsNone(policy._town_recall_destination(
            snapshot, guardian_gate=False)[0])
        self.assertEqual(policy._town_special_key(snapshot), "5")
        self.assertEqual(policy.last_reason, "fundraise:fallback-exhausted-plan")
        # Authoritative detection poverty decision: the five carried scrolls
        # veto detection-less scavenging even when the digging kit is partial.
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertTrue(policy._fundraising_departure_ready(snapshot))
        entrance = policy._town_walk_in_entrance(snapshot)
        self.assertEqual(entrance, Position(31, 150))
        self.assertTrue(policy._is_descent_target(snapshot, snapshot.grid_at(entrance)))

    def test_restored_exhausted_plan_keeps_the_fallback_owner(self):
        snapshot = self.snapshot(497)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_errand_plan = TownErrandPlan(stops=[4], index=1)
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertEqual(restored._town_errand_plan.index, 1)
        self.assertEqual(restored._town_special_key(snapshot), "5")
        self.assertEqual(restored.last_reason, "fundraise:fallback-exhausted-plan")
        # Restart obeys the same carried-detection veto as the fresh policy.
        self.assertEqual(restored._fundraising_mode, "prepare")

    def test_wander_skips_recorded_building_and_store_entrances(self):
        for line, entrance in ((497, Position(37, 91)),
                               (549, Position(25, 71))):
            with self.subTest(line=line):
                snapshot = self.snapshot(line)
                policy = HengbotPolicy()
                entrance_grid = snapshot.grid_at(entrance)
                self.assertIsNotNone(entrance_grid)
                self.assertTrue(entrance_grid.store_number >= 0
                                or entrance_grid.building_type >= 0)
                ordinary = Position(snapshot.player.position.y,
                                    snapshot.player.position.x + 1)
                policy._visit_counts[ordinary] = 100
                policy._visit_counts[entrance] = 0
                with patch.object(policy, "_walkable_neighbors",
                                  return_value=[entrance, ordinary]):
                    self.assertEqual(policy._least_visited_neighbor(snapshot), ordinary)
                with patch.object(policy, "_walkable_neighbors",
                                  return_value=[entrance]):
                    self.assertIsNone(policy._least_visited_neighbor(snapshot))

    def test_recorded_wander_entered_the_building(self):
        decision = self.rows["decisions", 400]
        before = self.snapshot(549)
        after = self.snapshot(550)
        self.assertEqual((decision["reason"], decision["key"]),
                         ("stuck:wander", "8"))
        self.assertEqual(before.player.position, Position(26, 71))
        self.assertEqual(after.player.position, Position(25, 71))
        self.assertEqual(after.grid_at(after.player.position).building_type, 13)


if __name__ == "__main__":
    unittest.main()
