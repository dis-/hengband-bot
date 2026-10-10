"""Step 1.5d2 F2 selector and disposal boundary pins."""

from __future__ import annotations

import tests  # noqa: F401
import json
import unittest
import tests
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import (
    GridState, Position, STORE_MAGIC, TVAL_BOW, TVAL_WAND, parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_types import TownVisitLedger
from hengbot.town_maps import find_town_map, parse_town_map


FIXTURES = Path(__file__).parent / "fixtures"


def _board(name):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return parse_snapshot(raw)


class Step15d2F2Test(unittest.TestCase):
    def test_224534_skips_both_rows_of_the_sold_wand_class(self):
        board = _board("step1.5d2-224534-shelf.json")
        policy = HengbotPolicy()
        policy._observe(board)
        policy._town_visit_sale_signatures.add((TVAL_WAND, 15))

        # Pure preflight must not mutate the visit ledger while it continues
        # the established ladder past both same-class shelf rows.
        before = set(getattr(
            policy._town_visit_ledger, "purchase_churn_exclusions", set()
        ))
        selected = policy._next_purchase(board)
        self.assertIsNotNone(selected)
        self.assertNotIn(selected.letter, {"k", "l"})
        self.assertEqual(
            getattr(policy._town_visit_ledger, "purchase_churn_exclusions", set()),
            before,
        )

        selected = policy._next_purchase(board, commit_churn=True)
        self.assertIsNotNone(selected)
        self.assertNotIn(selected.letter, {"k", "l"})
        self.assertEqual(
            policy._town_visit_ledger.purchase_churn_class_exclusions,
            {(STORE_MAGIC, TVAL_WAND, 15)},
        )
        skipped = policy._town_visit_ledger.purchase_churn_exclusions
        expected = {
            policy._item_signature(item)
            for item in board.store.items if item.letter in {"k", "l"}
        }
        self.assertEqual({signature for _, signature in skipped}, expected)
        self.assertEqual(len(skipped), 2)
        changed_rows = tuple(
            replace(item, letter={"k": "z", "l": "y"}.get(item.letter, item.letter),
                    name=f"rendered {item.name}", price=max(1, item.price - 1))
            if item.letter in {"k", "l"} else item
            for item in board.store.items
        )
        changed_page = replace(
            board, player=replace(board.player, gold=board.player.gold + 1),
            store=replace(board.store, items=changed_rows),
        )
        still_selected = policy._next_purchase(changed_page)
        self.assertIsNotNone(still_selected)
        self.assertNotEqual((still_selected.tval, still_selected.sval),
                            (TVAL_WAND, 15))

        # DECLARED CONSTRUCTED: fresh Home knowledge and the live depth
        # requirement are seeded on the same captured shelf; the required
        # Identify rung is the fuller staff at row o after the sold wand class.
        town_map = parse_town_map(find_town_map(1, Path("C:/hengband/lib/edit")))
        required_policy = HengbotPolicy(town_map=town_map)
        required_policy._observe(board)
        required_policy._build_grid_index(board)
        required_policy._home_knowledge_current = True
        required_policy._equipment_catalog.home_scan_complete = True
        required_policy._town_visit_sale_signatures.add((TVAL_WAND, 15))
        required = required_policy._departure_blocking_page_purchase(board)
        self.assertIsNotNone(required)
        self.assertEqual(required.item.letter, "o")

    def test_ledger_defaults_and_exclusions_survive_independent_replacement(self):
        policy = HengbotPolicy()
        old = policy._town_visit_ledger
        old.purchase_churn_exclusions.add((STORE_MAGIC, ("wand", TVAL_WAND, 15)))
        old.purchase_churn_class_exclusions.add((STORE_MAGIC, TVAL_WAND, 15))
        replacement = TownVisitLedger()
        replacement.purchase_churn_exclusions.update(old.purchase_churn_exclusions)
        replacement.purchase_churn_class_exclusions.update(
            old.purchase_churn_class_exclusions
        )
        policy._town_visit_ledger = replacement
        self.assertIn((STORE_MAGIC, TVAL_WAND, 15),
                      policy._town_visit_ledger.purchase_churn_class_exclusions)

        del policy._town_visit_ledger.__dict__["purchase_churn_exclusions"]
        del policy._town_visit_ledger.__dict__["purchase_churn_class_exclusions"]
        normalize_policy_state(policy)
        self.assertEqual(policy._town_visit_ledger.purchase_churn_exclusions, set())
        self.assertEqual(
            policy._town_visit_ledger.purchase_churn_class_exclusions, set()
        )

    def test_required_purchase_is_not_blocked_by_optional_kit_reserve(self):
        board = _board("step1.5d2-224534-shelf.json")
        town_map = parse_town_map(find_town_map(1, Path("C:/hengband/lib/edit")))
        policy = HengbotPolicy(town_map=town_map)
        policy._observe(board)
        policy._build_grid_index(board)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        staff = next(item for item in board.store.items if item.letter == "o")
        low_gold = replace(
            board, player=replace(board.player, gold=staff.price)
        )
        # DECLARED CONSTRUCTED: required Identify staff is affordable, while
        # an optional fundraising kit reserve exceeds the remaining gold.
        with patch.object(policy, "_fundraising_kit_reserve", return_value=1000):
            selected = policy._departure_blocking_page_purchase(low_gold)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.item.letter, "o")

    def test_040900_completed_disposal_requires_all_three_completion_facts(self):
        board = _board("step1.5d2-040900-shelf.json")
        policy = HengbotPolicy()
        policy._observe(board)
        # DECLARED CONSTRUCTED: the producer marker and absent-pack boundary
        # represent the 040900 S42 completed launcher sale.
        signature = ("sold launcher", 19, 24)
        policy._pending_disposal_item = signature
        policy._pending_disposal_slot = "a"
        absent = replace(board, inventory=())
        self.assertTrue(policy._pending_disposal_completed(absent))

        policy._home_pending_item = signature
        self.assertFalse(policy._pending_disposal_completed(absent))
        policy._home_pending_item = None
        policy._home_atomic_withdraw_pending = (STORE_MAGIC, signature)
        self.assertFalse(policy._pending_disposal_completed(absent))

    def test_completed_disposal_composes_required_buy_and_preserves_home_controls(self):
        board = _board("step1.5d2-040900-shelf.json")
        town_map = parse_town_map(find_town_map(1, Path("C:/hengband/lib/edit")))
        policy = HengbotPolicy(town_map=town_map)
        policy._observe(board)
        policy._build_grid_index(board)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True

        # DECLARED CONSTRUCTED from the 040900 S42 board: seed a weak pack
        # launcher beside the recorded equipped launcher, then ask the real
        # producer to file its slot and signature before the absent-pack state.
        weak = replace(
            board.inventory[0], slot="a", name="Short Bow (1d1) (+0,+0)",
            tval=TVAL_BOW, sval=1, is_equipment=True, damage_dice_num=1,
            damage_dice_sides=1, to_h=0, to_d=0, pval=0,
            known_flags=frozenset(), is_ego=False, is_artifact=False,
        )
        with_launcher = replace(board, inventory=(weak, *board.inventory))
        policy._begin_pack_dominated_launcher_disposal(with_launcher)
        signature = policy._pending_disposal_item
        self.assertEqual(policy._pending_disposal_slot, "a")
        absent = replace(with_launcher, inventory=tuple(
            item for item in with_launcher.inventory if item.slot != "a"
        ))
        key = policy._shop_core(absent)
        self.assertTrue(key.startswith("pl"), key)
        self.assertEqual(policy.last_reason, "shop:buy-device-food")
        self.assertIsNone(policy._pending_disposal_item)

        for field, value in (
            ("_home_pending_item", signature),
            ("_home_atomic_withdraw_pending", (STORE_MAGIC, signature)),
        ):
            control = HengbotPolicy(town_map=town_map)
            control._observe(board)
            control._pending_disposal_slot = "a"
            control._pending_disposal_item = signature
            setattr(control, field, value)
            self.assertFalse(control._pending_disposal_completed(absent))
            self.assertEqual(control._pending_disposal_item, signature)

    def test_constructed_refusal_with_required_buy_stops_without_second_producer(self):
        board = _board("step1.5d2-040900-shelf.json")
        town_map = parse_town_map(find_town_map(1, Path("C:/hengband/lib/edit")))
        policy = HengbotPolicy(town_map=town_map)
        policy._observe(board)
        policy._build_grid_index(board)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        policy._decision_sequence = 89
        policy._shop_observation = (board.store, 88)
        pos = board.player.position
        entrance = GridState(
            position=pos, known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_MAGIC,
        )
        # DECLARED CONSTRUCTED: outside composition boundary at the observed
        # store entrance; no store page is attached to the current snapshot.
        outside = replace(board, store=None, grids={pos: entrance})

        def refused(_snapshot):
            policy.last_reason = "equipment:sale-complete"
            return "\x1b"

        with patch.object(policy, "_shop", side_effect=refused) as shop, \
                patch.object(policy, "_shop_purchase_key", create=True) as second_producer:
            key = policy._atomic_shop_transaction_key(outside)
        self.assertEqual(shop.call_count, 1)
        second_producer.assert_not_called()
        self.assertEqual(
            policy.last_reason,
            "town:blocked:shop-required-operation-uncomposable",
        )
        self.assertIsNotNone(policy._shop_observation)
        self.assertEqual(
            policy._shop_selector_diagnostics["required-page-continuation"]["cause"],
            "composition-mismatch",
        )
        self.assertIn(
            "town:blocked:shop-required-operation-uncomposable",
            __import__("hengbot.policy_constants", fromlist=[
                "POLICY_FINAL_STOP_REASONS"
            ]).POLICY_FINAL_STOP_REASONS,
        )


if __name__ == "__main__":
    unittest.main()
