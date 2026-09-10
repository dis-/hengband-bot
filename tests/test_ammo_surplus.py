from __future__ import annotations

from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

from hengbot.model import STORE_WEAPON, StoreItem, StoreState, parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "departure-blocked-ammo-fragmentation-20260910.json.gz"
)
LAUNCHER_FIXTURE = (
    Path(__file__).parent / "fixtures" / "launcher-post-swap-live-2237771.json.gz"
)


def captured_rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8-sig") as stream:
        return json.load(stream)


def drive_captured_window():
    policy = HengbotPolicy()
    decisions = []
    snapshot = None
    for row in captured_rows():
        snapshot = parse_snapshot(row["snapshot"], {})
        key = policy.choose_key(snapshot)
        decisions.append((key, policy.last_reason))
        if key:
            policy.confirm_key_posted(key)
    assert snapshot is not None
    return policy, snapshot, decisions


class AmmoSurplusTest(unittest.TestCase):
    def test_live_post_swap_releases_all_incompatible_ammo_to_home(self):
        with gzip.open(LAUNCHER_FIXTURE, "rt", encoding="utf-8") as stream:
            snapshot = parse_snapshot(json.load(stream), {})
        policy = HengbotPolicy()
        bolts = [item for item in snapshot.inventory if item.tval == 18]
        arrows = [item for item in snapshot.inventory if item.tval == 17]

        self.assertEqual(sum(item.count for item in bolts), 86)
        self.assertEqual(
            [policy._retention_surplus(snapshot, item) for item in bolts],
            [item.count for item in bolts],
        )
        self.assertTrue(any(
            policy._retention_reservation(snapshot, item) > 0 for item in arrows
        ))
        self.assertIn(policy._find_home_deposit(snapshot), bolts)

    def test_weakest_stack_is_surplus_away_from_exact_carry_target(self):
        policy, snapshot, _decisions = drive_captured_window()
        weakest = next(item for item in snapshot.inventory if item.slot == "o")

        best = next(item for item in snapshot.inventory if item.slot == "t")
        for count in (74, 81):
            changed = replace(weakest, count=count)
            changed_snapshot = replace(
                snapshot,
                inventory=[
                    changed if item is weakest else item
                    for item in snapshot.inventory
                    if item.tval != weakest.tval or item in (weakest, best)
                ],
            )
            self.assertEqual(
                policy._count_matching_ammo(changed_snapshot),
                24 + count,
            )
            self.assertEqual(
                policy._retention_surplus(changed_snapshot, changed),
                count,
            )

    def test_captured_inferior_stack_routes_to_home(self):
        policy, snapshot, decisions = drive_captured_window()
        weakest = next(item for item in snapshot.inventory if item.slot == "o")
        inferior_dense = next(item for item in snapshot.inventory if item.slot == "q")
        best = next(item for item in snapshot.inventory if item.slot == "t")

        final_key, final_reason = decisions[-1]
        self.assertTrue(final_key)
        self.assertNotEqual(final_reason, "town:blocked:departure-unsatisfiable")
        self.assertEqual(policy._retention_surplus(snapshot, weakest), 3)
        self.assertEqual(policy._retention_surplus(snapshot, inferior_dense), 0)
        self.assertEqual(policy._retention_surplus(snapshot, best), 0)
        self.assertEqual(
            [
                policy._retention_surplus(snapshot, item)
                for item in snapshot.inventory
                if item.slot in "opqrst"
            ],
            [3, 0, 0, 0, 0, 0],
        )
        self.assertIs(policy._find_home_deposit(snapshot), weakest)
        self.assertIsNone(policy._full_pack_destroy_key(snapshot))

    def test_post_shed_shortfall_reaches_normal_supplier(self):
        policy, snapshot, _decisions = drive_captured_window()
        weakest = next(item for item in snapshot.inventory if item.slot == "o")
        inferior_dense = next(item for item in snapshot.inventory if item.slot == "q")
        self.assertIs(policy._find_home_deposit(snapshot), weakest)
        self.assertEqual(policy._retention_surplus(snapshot, inferior_dense), 0)

        # Apply the inventory observation produced by that whole-stack Home
        # deposit.  Store routing is outside this pin; the real normal-purchase
        # producer and its quantity consumer remain unwalled.
        offered = StoreItem(
            letter="a",
            name="crossbow bolts",
            count=20,
            tval=weakest.tval,
            sval=weakest.sval,
            price=2,
        )
        after_deposit = replace(
            snapshot,
            inventory=[item for item in snapshot.inventory if item is not weakest],
            store=StoreState(
                STORE_WEAPON,
                [offered],
                stock_num=1,
                page_top=0,
            ),
        )

        self.assertEqual(policy._count_matching_ammo(after_deposit), 96)
        self.assertIs(policy._next_purchase_unreserved(after_deposit), offered)
        self.assertEqual(policy._purchase_quantity(after_deposit, offered), 3)


if __name__ == "__main__":
    unittest.main()
