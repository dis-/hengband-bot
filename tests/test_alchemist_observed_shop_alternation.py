"""Recorded pins for the Alchemist observed-page owner alternation."""

from __future__ import annotations

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from tests.policy_fixtures import item, store_item

from hengbot.model import (
    STORE_ALCHEMIST,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    SV_SCROLL_STAR_IDENTIFY,
    TVAL_SCROLL,
    TVAL_SOFT_ARMOR,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "alchemist-observed-shop-alternation-20260916.jsonl.gz"
)
PROVENANCE = FIXTURE.with_suffix("").with_suffix(".provenance.txt")

# Frozen from bot-decisions.jsonl lines 8623-8627 at HEAD 4f6a523.
# The R4 comparisons use turns 3024656, 3024665, 3024720, and 3024728;
# turn 3024676 is retained because the fixture commentary refers to its retry.
RECORDED_DECISIONS = {
    3_024_656: ("\x1b", "shop:observe-and-leave"),
    3_024_665: ("\x1b`n%.", "shop:travel"),
    3_024_676: ("\x1b`n%.", "store:entry-interrupted-replan"),
    3_024_720: ("\x1b", "town-progress-invariant:continue-observed-shop"),
    3_024_728: ("7", "shop:approach"),
}


def recorded_rows() -> list[dict]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class AlchemistObservedShopAlternationTest(unittest.TestCase):
    @staticmethod
    def _post_alchemist_home_policy(snapshot):
        policy = HengbotPolicy()
        stored_source = store_item(
            "h", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY,
            name="stored star identify",
        )
        incomplete_armour = store_item(
            "M", TVAL_SOFT_ARMOR, 10, name="incomplete ego armour",
            known=True, fully_known=False, is_equipment=True, is_ego=True,
        )
        policy.consume_home_knowledge((stored_source, incomplete_armour))
        policy._equipment_catalog.home_scan_complete = True
        policy._home_candidate_waiting = True
        policy._town_store_attempted[STORE_HOME] = (
            "observed-operation-uncomposable"
        )
        policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn
        policy._town_errand_plan = policy._build_town_errand_plan(
            snapshot, policy._enumerate_live_store_claims(snapshot)
        )
        return policy

    def test_fixture_is_the_byte_faithful_incident_window(self):
        with gzip.open(FIXTURE, "rb") as stream:
            frozen = stream.read()
        provenance = PROVENANCE.read_text(encoding="utf-8")
        recorded_sha256 = next(
            line.split(":", 1)[1].strip()
            for line in provenance.splitlines()
            if line.startswith("Decompressed sha256:")
        )
        self.assertEqual(hashlib.sha256(frozen).hexdigest(), recorded_sha256)
        rows = recorded_rows()
        self.assertEqual(len(rows), 17)
        self.assertEqual((rows[0]["turn"], rows[-1]["turn"]), (
            3_024_656, 3_024_766,
        ))

    def test_three_entries_freeze_owner_needs_shelf_and_prompt_keys(self):
        rows = recorded_rows()
        pages = [
            row for row in rows
            if row.get("store", {}).get("store_type") == STORE_ALCHEMIST
        ]
        self.assertEqual([row["turn"] for row in pages], [
            3_024_720, 3_024_738, 3_024_759,
        ])
        for page in pages:
            shelf = {
                (item["letter"], item["name"], item["price"])
                for item in page["store"]["items"]
            }
            self.assertIn(("j", "帰還の詔の巻物", 233), shelf)
            self.assertIn(("l", "*鑑定*の巻物", 2326), shelf)

        prompt = next(
            row for row in rows
            if row["turn"] == 3_024_720 and "store" not in row
        )
        self.assertEqual(prompt["messages"], ["トラベルを継続しますか？[y/n]"])
        self.assertEqual(RECORDED_DECISIONS[3_024_665], (
            "\x1b`n%.", "shop:travel",
        ))
        self.assertEqual(RECORDED_DECISIONS[3_024_676], (
            "\x1b`n%.", "store:entry-interrupted-replan",
        ))

    def test_recorded_route_owner_consumes_page_at_first_r4_divergence(self):
        rows = recorded_rows()
        # Consume the final board available to each live decision. The 3024676
        # command-barrier retry has no executor metadata in bot-state JSONL, so
        # its identical posted travel key is represented by the resulting
        # 3024720 store page, not replayed as a counterfactual policy decision.
        route = [
            rows[1],  # 3024656 Weapon Shop page
            rows[3],  # 3024665 surface: real Alchemist route entry point
            rows[7],  # 3024720 observed Alchemist page
            rows[8],  # 3024728 adjacent outside composition boundary
        ]
        policy = HengbotPolicy()
        replay = []
        for raw in route:
            snapshot = parse_snapshot(raw, {})
            replay.append((snapshot.turn, policy.choose_key(snapshot), policy.last_reason))

        self.assertEqual(replay[:2], [
            (3_024_656, "\x1b",
             "town-progress-invariant:continue-observed-shop"),
            (3_024_665, *RECORDED_DECISIONS[3_024_665]),
        ])
        self.assertEqual(replay[2], (
            3_024_720, *RECORDED_DECISIONS[3_024_720],
        ))
        live = RECORDED_DECISIONS[3_024_728]
        self.assertEqual(live, (
            "7", "shop:approach",
        ))
        self.assertEqual(replay[3], (
            3_024_728, "5", "shop:one-shot-sell",
        ))
        print(f"replay={replay[3][1:]!r} live={live!r}")
        self.assertEqual(policy._store_visit.owner, "shop-one-shot")
        self.assertEqual(policy._store_visit.store_type, STORE_ALCHEMIST)
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertFalse(policy._store_visit.operation_released)
        self.assertEqual(policy._store_visit.operation_key, "d0y\x1b")
        self.assertEqual(policy._acquire_store_visit_attempt, {
            "acquire_store_visit_called": True,
            "requested_owner": "shop-one-shot",
            "requested_store": STORE_ALCHEMIST,
            "acquire_result": "granted-observed-outside",
        })
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_ALCHEMIST],
            ("low-level-sale", "identification-source"),
        )
        self.assertFalse(any(
            reason == "town:blocked:owner-retired"
            for _, _, reason in replay
        ))

    def test_component_general_store_uses_the_same_outside_handoff(self):
        # Component test: preserve the recorded player/inventory/page shape,
        # changing only the shop identity and matching entrance glyph.
        rows = recorded_rows()
        inside = parse_snapshot(rows[7], {})
        outside = parse_snapshot(rows[8], {})
        inside = replace(
            inside, store=replace(inside.store, store_type=STORE_GENERAL),
        )
        entrance = outside.grid_at(outside.player.position)
        outside = replace(
            outside,
            grids={
                **outside.grids,
                outside.player.position: replace(
                    entrance, store_number=STORE_GENERAL,
                ),
            },
        )
        policy = HengbotPolicy()

        leave = policy.choose_key(inside)
        composed = policy.choose_key(outside)

        self.assertEqual((leave, composed, policy.last_reason), (
            "\x1b", "7", "explore",
        ))
        self.assertIsNone(policy._shop_observation)
        self.assertNotEqual(policy._store_visit.store_type, STORE_GENERAL)
        self.assertNotEqual(policy.last_reason, "shop:approach")

    def test_uncomposable_home_verdict_survives_without_carried_source(self):
        outside = parse_snapshot(recorded_rows()[8], {})
        policy = self._post_alchemist_home_policy(outside)
        home_claims = [
            need for need in policy._enumerate_live_store_claims(outside)
            if need.store_type == STORE_HOME
        ]

        decisions = [
            policy._next_required_store_type(outside)
            for _ in range(3)
        ]

        self.assertEqual(
            [(need.category, need.ordering_class) for need in home_claims],
            [
                ("identification-withdrawal", "post-alchemist-home"),
                ("equipment-catalog", "home-first"),
                ("equipment-work", "post-alchemist-home"),
            ],
        )
        self.assertEqual(decisions, [STORE_MAGIC, STORE_MAGIC, STORE_MAGIC])
        self.assertEqual(
            policy._town_store_attempted[STORE_HOME],
            "observed-operation-uncomposable",
        )
        self.assertNotEqual(policy.last_reason, "town:blocked:owner-retired")

    def test_carried_identify_source_reopens_post_alchemist_home(self):
        outside = parse_snapshot(recorded_rows()[8], {})
        policy = self._post_alchemist_home_policy(outside)
        carried_source = item(
            "z", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY,
            name="carried star identify",
        )
        with_source = replace(
            outside, inventory=[*outside.inventory, carried_source]
        )

        self.assertEqual(policy._next_required_store_type(with_source), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)


if __name__ == "__main__":
    unittest.main()
