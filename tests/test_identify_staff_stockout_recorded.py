"""Regression pin for the 2026-10-07 Identify-staff town stop."""

import tests  # noqa: F401
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    STORE_BLACK,
    STORE_HOME,
    STORE_MAGIC,
    SV_STAFF_IDENTIFY,
    TVAL_STAFF,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "identify-staff-stockout-20261007.json.gz"


def recorded_boards():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    rows = payload["board_rows"]
    for raw in rows.values():
        # Monster knowledge does not affect the town procurement decision.
        raw["visible_monsters"] = []
        raw["detected_monsters"] = []
    return (
        parse_snapshot(rows["magic_shop"], {}),
        parse_snapshot(rows["after_magic"], {}),
    )


def policy_after_magic(magic, outside, page):
    policy = HengbotPolicy()
    policy._deepest_level = 44
    policy.consume_home_knowledge(())
    policy._town_store_attempted[STORE_HOME] = outside.turn - 1
    policy._town_store_attempted[STORE_MAGIC] = magic.turn
    policy._town_supplier_stock[STORE_MAGIC] = page
    policy._town_supplier_stock_observations[STORE_MAGIC] = (
        policy._effective_town_id(outside), magic.turn,
    )
    return policy


class IdentifyStaffStockoutRecordedTest(unittest.TestCase):
    def test_recorded_worthwhile_magic_offer_keeps_a_live_owner(self):
        magic, outside = recorded_boards()
        self.assertEqual((outside.player.level, outside.player.gold), (43, 29994))
        self.assertEqual(
            sum(
                item.charges * max(1, item.count)
                for item in outside.inventory
                if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
            ),
            3,
        )
        policy = policy_after_magic(magic, outside, magic.store)

        self.assertFalse(policy._identify_staff_ready(outside))
        self.assertFalse(policy._identify_staff_procurement_impossible(outside))
        needs = policy._enumerate_town_needs(outside)
        self.assertTrue(any(
            need.store_type == STORE_MAGIC and need.category == "identify-staff"
            for need in needs
        ))
        self.assertTrue(any(
            need.store_type == STORE_BLACK and need.category == "identify-staff"
            for need in needs
        ))
        self.assertEqual(policy._next_required_store_type(outside), STORE_MAGIC)

    def test_recorded_magic_stockout_registers_black_market_owner(self):
        magic, outside = recorded_boards()
        empty_magic = replace(
            magic.store,
            items=[
                item for item in magic.store.items
                if not (item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY)
            ],
        )
        policy = policy_after_magic(magic, outside, empty_magic)

        self.assertFalse(policy._identify_staff_procurement_impossible(outside))
        self.assertTrue(any(
            need.store_type == STORE_BLACK and need.category == "identify-staff"
            for need in policy._enumerate_town_needs(outside)
        ))

    def test_restored_single_supplier_registry_cache_is_rebuilt(self):
        magic, outside = recorded_boards()
        policy = policy_after_magic(magic, outside, magic.store)
        specs = policy._town_need_registry()
        policy._town_need_specs = tuple(
            spec for index, spec in enumerate(specs)
            if spec.category != "identify-staff"
            or not any(
                prior.category == "identify-staff"
                for prior in specs[:index]
            )
        )

        rebuilt = policy._town_need_registry()

        self.assertIn(
            1,
            {
                getattr(getattr(spec.produces, "__self__", None), "occurrence", -1)
                for spec in rebuilt
                if spec.category == "identify-staff"
            },
        )


if __name__ == "__main__":
    unittest.main()
