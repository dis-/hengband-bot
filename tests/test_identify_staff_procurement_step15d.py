"""Step 1.5d pins for charged Home stock and fundraising Identify-staff buys."""

import tests  # noqa: F401
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.model import (
    STORE_MAGIC,
    SV_STAFF_IDENTIFY,
    SV_WAND_STONE_TO_MUD,
    TVAL_STAFF,
    TVAL_WAND,
    StoreState,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_shop import ProcurementHomeGate

from policy_fixtures import item, store_item
from test_identify_staff_stockout_recorded import recorded_boards


class IdentifyStaffProcurementStep15dTest(unittest.TestCase):
    def setUp(self):
        self.magic, self.outside = recorded_boards()

    def test_zero_charge_home_staff_is_not_procurement_stock(self):
        # DECLARED CONSTRUCTED from 175851 s1999 / 122258 s15-17:
        # the observed Home Identify staff are present but have no charges.
        empty_staff = item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=0)
        charged_staff = item("b", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3)
        empty_wand = item("c", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=0)
        charged_wand = item("d", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=3)
        policy = HengbotPolicy()
        policy.consume_home_knowledge((
            empty_staff, charged_staff, empty_wand, charged_wand,
        ))

        self.assertFalse(policy._procurement_class_matches(
            empty_staff, (TVAL_STAFF, SV_STAFF_IDENTIFY)
        ))
        self.assertTrue(policy._procurement_class_matches(
            charged_staff, (TVAL_STAFF, SV_STAFF_IDENTIFY)
        ))
        self.assertFalse(policy._procurement_class_matches(
            empty_wand, (TVAL_WAND, SV_WAND_STONE_TO_MUD)
        ))
        self.assertTrue(policy._procurement_class_matches(
            charged_wand, (TVAL_WAND, SV_WAND_STONE_TO_MUD)
        ))
        self.assertIs(policy._home_procurement_candidate(
            (TVAL_STAFF, SV_STAFF_IDENTIFY)
        ), charged_staff)
        self.assertEqual(policy._home_procurement_viable_class_matches(
            (TVAL_STAFF, SV_STAFF_IDENTIFY)
        ), 2)
        self.assertIs(policy._home_procurement_viable_item(
            (TVAL_STAFF, SV_STAFF_IDENTIFY)
        ), charged_staff)

    def test_zero_charge_home_staff_does_not_block_the_magic_purchase(self):
        # DECLARED CONSTRUCTED pin using the 175851 715/11 Magic offer and
        # its Home page 1, which contains only empty Identify staves.
        policy = HengbotPolicy()
        policy._deepest_level = 44
        policy.consume_home_knowledge((
            item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=0),
        ))
        policy._equipment_catalog._home = {}
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=715, charges=11, name="Staff of Identify",
        )
        snapshot = replace(
            self.magic,
            player=self.outside.player,
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )

        self.assertIs(
            policy._evaluate_purchase_home_gate(snapshot, offered),
            ProcurementHomeGate.ALLOW_PURCHASE,
        )
        self.assertEqual(policy._home_gate_telemetry["branch"], "evaluate-no-candidate")

    def test_zero_charge_home_staff_does_not_preempt_mana_food_wand(self):
        # DECLARED CONSTRUCTED from 224534 s41: the Magic page's 394/40 mana
        # wand remains eligible when Home has only an empty Identify staff.
        policy = HengbotPolicy()
        policy._deepest_level = 44
        policy.consume_home_knowledge((
            item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=0),
        ))
        policy._equipment_catalog._home = {}
        offered = store_item(
            "j", TVAL_WAND, SV_WAND_STONE_TO_MUD,
            price=394, charges=40, name="Wand of Stone to Mud",
        )
        snapshot = replace(
            self.magic,
            player=replace(self.outside.player, food_type=1),
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )
        with patch.object(policy, "_procurement_missing_amount", return_value=1):
            result = policy._evaluate_purchase_home_gate(snapshot, offered)

        self.assertIs(result, ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertEqual(policy._home_gate_telemetry["branch"], "evaluate-no-candidate")

    def test_zero_charge_home_wand_does_not_preempt_a_charged_wand(self):
        # DECLARED CONSTRUCTED pin for 214921: an empty Home wand is not
        # current Magic stock for an in-store charged-wand purchase.
        policy = HengbotPolicy()
        policy._deepest_level = 44
        policy.consume_home_knowledge((
            item("a", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=0),
        ))
        policy._equipment_catalog._home = {}
        offered = store_item(
            "j", TVAL_WAND, SV_WAND_STONE_TO_MUD,
            price=562, charges=13, name="Wand of Stone to Mud",
        )
        snapshot = replace(
            self.magic,
            player=self.outside.player,
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )

        self.assertIs(
            policy._evaluate_purchase_home_gate(snapshot, offered),
            ProcurementHomeGate.ALLOW_PURCHASE,
        )

    def test_non_worthwhile_home_identify_staff_is_an_in_gate_allow(self):
        # DECLARED CONSTRUCTED at the purchase gate: a charged Home staff is
        # present, but taking it cannot improve the 823/20 shelf replacement.
        policy = HengbotPolicy()
        policy._deepest_level = 44
        home_staff = item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3)
        policy.consume_home_knowledge((home_staff,))
        policy._equipment_catalog._home = {}
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=823, charges=20, name="Staff of Identify",
        )
        snapshot = replace(
            self.magic,
            player=self.outside.player,
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )
        with patch.object(policy, "_identify_staff_acquisition_worthwhile", return_value=False):
            result = policy._evaluate_purchase_home_gate(snapshot, offered)

        self.assertIs(result, ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "evaluate-home-stock-not-worthwhile",
        )

    def test_fundraising_identify_only_block_returns_worthwhile_staff(self):
        # DECLARED CONSTRUCTED from 122258 s53 (Telmora, 823/20): fundraising
        # is blocked only on Identify staff, and its other preparation needs
        # already hold.
        policy = HengbotPolicy()
        policy._deepest_level = 20
        policy._fundraising_mode = "prepare"
        policy._fundraising_supplies_ready = lambda _snapshot: True
        policy._fundraising_light_ready = lambda _snapshot: True
        policy._oil_below_departure_target = lambda _snapshot: False
        policy._has_withdrawable_digging_tool = lambda _snapshot: True
        policy._withdrawable_digging_tool_count = lambda _snapshot: 2
        policy._count_treasure_detection_scrolls = lambda _snapshot: 10
        policy._mining_detection_stock_target = lambda _snapshot: 1
        policy._food_ready = lambda _snapshot: True
        policy._planned_depth = lambda: 20
        with patch.object(policy, "_fundraising_identify_staff_only_block", return_value=True):
            offered = store_item(
                "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
                price=823, charges=20, name="Staff of Identify",
            )
            snapshot = replace(
                self.magic,
                player=replace(self.outside.player, gold=16558),
                inventory=self.outside.inventory,
                store=StoreState(STORE_MAGIC, [offered]),
            )
            selected = policy._legacy_next_purchase_unreserved(snapshot)

        self.assertIs(selected, offered)
        self.assertTrue(any(
            match.rung_id == "tail:identify-staff"
            for match in policy._matching_live_purchase_rungs(snapshot, offered)
        ))

    def test_identify_mining_plan_returns_staff_and_rejects_empty_staff(self):
        # DECLARED CONSTRUCTED alternate F4 trigger: the Identify mining plan
        # itself keeps the rung live, and an empty offer is never selected.
        policy = HengbotPolicy()
        policy._deepest_level = 20
        policy._fundraising_mode = "prepare"
        policy._identify_staff_mining_plan = True
        policy._fundraising_supplies_ready = lambda _snapshot: True
        policy._fundraising_light_ready = lambda _snapshot: True
        policy._oil_below_departure_target = lambda _snapshot: False
        policy._has_withdrawable_digging_tool = lambda _snapshot: True
        policy._withdrawable_digging_tool_count = lambda _snapshot: 2
        policy._count_treasure_detection_scrolls = lambda _snapshot: 10
        policy._mining_detection_stock_target = lambda _snapshot: 1
        policy._food_ready = lambda _snapshot: True
        policy._planned_depth = lambda: 20
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=823, charges=20, name="Staff of Identify",
        )
        snapshot = replace(
            self.magic,
            player=replace(self.outside.player, gold=16558),
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )
        with patch.object(policy, "_fundraising_identify_staff_only_block", return_value=False):
            self.assertIs(policy._legacy_next_purchase_unreserved(snapshot), offered)
            empty = replace(offered, charges=0, price=558)
            empty_snapshot = replace(
                snapshot, store=StoreState(STORE_MAGIC, [empty])
            )
            with patch.object(
                policy, "_identify_staff_acquisition_worthwhile", return_value=True
            ):
                self.assertIsNone(
                    policy._legacy_next_purchase_unreserved(empty_snapshot)
                )

    def test_identify_staff_rung_rejects_positive_but_not_worthwhile_offer(self):
        # DECLARED CONSTRUCTED cap-swap case: positive charges alone do not
        # make a staff useful when the current carried/shelf plan rejects it.
        policy = HengbotPolicy()
        policy._deepest_level = 20
        policy._mandatory_purchase = lambda _snapshot: None
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=823, charges=20, name="Staff of Identify",
        )
        snapshot = replace(
            self.magic,
            player=replace(self.outside.player, gold=16558),
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )
        with (
            patch.object(policy, "_fundraising_identify_staff_only_block", return_value=False),
            patch.object(policy, "_identify_staff_acquisition_worthwhile", return_value=False),
        ):
            self.assertIsNone(policy._legacy_next_purchase_unreserved(snapshot))
            self.assertFalse(any(
                match.rung_id == "tail:identify-staff"
                for match in policy._matching_live_purchase_rungs(snapshot, offered)
            ))

    def test_zero_charge_staff_is_not_selected(self):
        # DECLARED CONSTRUCTED from 122258 s19-21 (Magic 558/0).
        policy = HengbotPolicy()
        policy._deepest_level = 20
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=558, charges=0, name="Staff of Identify",
        )
        snapshot = replace(
            self.magic,
            player=replace(self.outside.player, gold=16558),
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )

        self.assertIsNone(policy._next_purchase(snapshot))

    def test_zero_charge_staff_is_not_a_typed_identify_rung_match(self):
        policy = HengbotPolicy()
        policy._deepest_level = 20
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=558, charges=0, name="Staff of Identify",
        )
        snapshot = replace(
            self.magic,
            player=replace(self.outside.player, gold=16558),
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )
        with patch.object(policy, "_identify_staff_acquisition_worthwhile", return_value=True):
            matches = policy._matching_live_purchase_rungs(snapshot, offered)

        self.assertFalse(any(
            match.rung_id == "tail:identify-staff" for match in matches
        ))

    def test_zero_charge_staff_is_not_selected_when_worthwhile_is_overridden(self):
        policy = HengbotPolicy()
        policy._deepest_level = 20
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=558, charges=0, name="Staff of Identify",
        )
        snapshot = replace(
            self.magic,
            player=replace(self.outside.player, gold=16558),
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )
        with patch.object(policy, "_identify_staff_acquisition_worthwhile", return_value=True):
            selected = policy._legacy_next_purchase_unreserved(snapshot)

        self.assertIsNone(selected)
        self.assertFalse(any(
            match.rung_id == "tail:identify-staff"
            for match in policy._matching_live_purchase_rungs(snapshot, offered)
        ))

    def test_confirmed_purchase_that_readies_identify_drops_mining_plan(self):
        # DECLARED CONSTRUCTED successful-purchase observation: added charges
        # make the carried total ready after the matching Magic buy is seen.
        policy = HengbotPolicy()
        policy._deepest_level = 20
        policy._identify_staff_mining_plan = True
        policy._mandatory_purchase = lambda _snapshot: None
        policy.consume_home_knowledge(())
        policy._equipment_catalog._home = {}
        offered = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=823, charges=20, name="Staff of Identify",
        )
        purchase_board = replace(
            self.magic,
            player=replace(self.outside.player, gold=10000),
            inventory=self.outside.inventory,
            store=StoreState(STORE_MAGIC, [offered]),
        )
        before = replace(self.outside, store=None, player=purchase_board.player)
        # DECLARED CONSTRUCTED successful-purchase observation: this uses the
        # real shop key/post confirmation before introducing its resulting board.
        bought = item(
            "z", TVAL_STAFF, SV_STAFF_IDENTIFY,
            charges=20, name="Staff of Identify",
        )
        after = replace(
            before,
            player=replace(before.player, gold=before.player.gold - 823),
            inventory=(*before.inventory, bought),
            turn=before.turn + 1,
        )
        purchase_key = policy._shop(purchase_board)
        self.assertIsNotNone(purchase_key)
        policy.confirm_key_posted(purchase_key)

        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            policy.choose_key(after)

        self.assertTrue(policy._identify_staff_ready(after))
        self.assertFalse(policy._identify_staff_mining_plan)


if __name__ == "__main__":
    unittest.main()
