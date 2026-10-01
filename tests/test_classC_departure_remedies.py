"""Class C production seams, with explicitly constructed counterfactuals.

The live36 attachment supplies the real outside board and recorded knowledge,
prices, calibration depth and ledger (its existing fixture documents the walls).
Variations below change exported pack/map/player facts and declare equipment
retirement/no-effect route evidence. They are NOT subsequent live36 boards or
effects of any replayed key. No screen, selector or ready predicate is mocked.
The unchanged live27/live36 modules cover the public recorded production chain.
"""
import tests  # noqa: F401 -- runtime-file isolation
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import TVAL_STAFF, SV_STAFF_IDENTIFY, TVAL_POTION, SV_POTION_CURE_CRITICAL
from hengbot.policy import HengbotPolicy, REST_MACRO, RESTOCK_WAIT_MACRO
from hengbot.policy_constants import FOOD_TYPE_RATION, LANTERN_REFILL_FUEL
from test_live36_weight import attachment


class DepartureRemedyTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy, self.board, _capture = attachment(Path(directory.name))

    def _retire_equipment(self, board):
        # Constructed equipment-work exhaustion for the actual worn set.
        # It must not retire independently executable supply or deposit work.
        self.policy._refresh_carried_equipment_catalog(board)
        self.policy._equipment_retired_worn_item_ids = frozenset(
            owned.id for owned in self.policy._equipment_catalog.items
            if owned.origin == "equipped"
        )
        self.policy._town_store_attempted.clear()

    def test_retired_equipment_does_not_erase_supply_and_deposit_producers(self):
        board = self.board
        initial = checkpoint(self.policy)
        routes = {
            0: ("5", "shop:travel:await-entry"),
            3: ("\x1b`n$.", "shop:travel"),
            4: ("\x1b`n%.", "shop:travel"),
            5: ("\x1b`n&.", "shop:travel"),
            7: ("\x1b`n(.", "shop:travel"),
        }
        cases = (
            ("identify_staff_ready", replace(board, inventory=tuple(
                replace(item, count=1, charges=19, pval=19)
                if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
                else item for item in board.inventory if item.slot not in "jk"
            )), 5),
            ("recall_departure_ready", replace(board, inventory=tuple(
                item for item in board.inventory if not item.is_recall_scroll
            )), 3),
            ("food_ready", replace(board, inventory=tuple(
                item for item in board.inventory if item.tval != TVAL_STAFF
            )), 5),
            ("teleport_ready", replace(board, inventory=tuple(
                item for item in board.inventory if not item.is_teleport_scroll
            )), 4),
            ("cure_critical_ready", replace(board, inventory=tuple(
                item for item in board.inventory
                if not (item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL)
            )), 3),
            ("light_ready", replace(board,
                inventory=tuple(item for item in board.inventory if not item.is_oil),
                equipment=tuple(item for item in board.equipment if not item.is_light)
            ), 0),
            ("inventory_weight_ready", board, 7),
        )
        for leaf, changed, expected_store in cases:
            with self.subTest(leaf=leaf):
                self.policy = restore_checkpoint(HengbotPolicy, initial)
                self._retire_equipment(changed)
                saved = checkpoint(self.policy)
                for policy in (self.policy, restore_checkpoint(HengbotPolicy, saved)):
                    self.assertEqual(policy._recall_town_departure_conjuncts(changed)[leaf], False)
                    self.assertEqual(policy._departure_supplier_core(changed), (expected_store, True))
                    self.assertEqual(policy._departure_supplier_counterfactual(changed), expected_store)
                    step = policy._shopping_approach_step(
                        changed, expected_store, router_plan_stop=True)
                    self.assertIsNotNone(step)
                    key = policy._shopping_approach_key(changed, step, "shop:travel")
                    self.assertEqual((key, policy.last_reason), routes[expected_store])
                    print("CLASS C SUPPLIER", leaf, expected_store, repr(key), policy.last_reason)
                    self.assertEqual(policy._shopping_approach_store_type, expected_store)
                    self.assertEqual(policy._town_blocked_reason, None)
                    # Keep the optional-work suppression meaning of exhaustion.
                    self.assertEqual(policy._launcher_enchant_registration_actionable(changed), False)

    def _mapless_refused_staff_routes(self):
        # Constructed mapless surface: the recorded town dimensions no longer
        # match a static map and no exported store entrance is available.
        # Empty remembered shelves and unchanged no-effect evidence describe
        # failed shop work, not failed mining or recovery. No Home UI is made.
        board = replace(self.board, width=self.board.width + 1,
            grids={position: replace(grid, store_number=-1)
                   for position, grid in self.board.grids.items()},
            inventory=tuple(
                replace(item, count=1, charges=19, pval=19)
                if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
                else item for item in self.board.inventory if item.slot not in "jk"
            ))
        self.policy._town_supplier_stock = {
            store: replace(page, items=[])
            for store, page in self.policy._town_supplier_stock.items()
        }
        self.policy._town_store_attempted.clear()
        self.policy._town_visit_ledger.nonhome_attempted_without_effect.update({
            store: self.policy._town_observable_effect_state(board)
            for store in range(7)
        })
        return board

    def test_exhausted_shop_router_offers_stockout_mining_before_stop(self):
        board = self._mapless_refused_staff_routes()
        self.assertEqual(self.policy._departure_supplier_core(board), (None, False))
        saved = checkpoint(self.policy)
        for policy in (self.policy, restore_checkpoint(HengbotPolicy, saved)):
            policy._next_required_store_type(board)
            self.assertEqual(policy._town_blocked_reason, None)
            key = policy._town_special_key(board)
            self.assertEqual((key, policy.last_reason), ("5", "town:identify-staff-stockout-mining"))
            self.assertEqual(policy._planned_mining_runs, 1)
            self.assertEqual(policy._identify_staff_mining_plan, True)
            self.assertEqual(policy._identify_staff_ready(board), False)
            # Stop here: no later historical board is an effect of this key.

    def test_exhausted_shop_router_preserves_existing_recovery_owner(self):
        board = self._mapless_refused_staff_routes()
        board = replace(board, player=replace(board.player,
            hp=board.player.max_hp - 1, mp=max(0, board.player.max_mp - 1),
            stunned=True, food_state="full"))
        self.policy._town_visit_ledger.nonhome_attempted_without_effect.update({
            store: self.policy._town_observable_effect_state(board)
            for store in range(7)
        })
        self.policy._next_required_store_type(board)
        self.assertEqual(self.policy._town_blocked_reason, None)
        self.assertEqual(self.policy._town_special_key(board), REST_MACRO)
        self.assertEqual(self.policy.last_reason, "town:recover")

    def test_existing_stockout_plan_does_not_become_permission_to_depart(self):
        board = self._mapless_refused_staff_routes()
        # Constructed existing-plan boundary, not evidence of a live mining
        # outcome. The new routing rule must preserve the one-run guard and
        # the hard departure gate when no remaining producer can emit a key.
        self.policy._identify_staff_mining_plan = True
        self.policy._next_required_store_type(board)
        self.assertEqual(self.policy._town_special_key(board), "5")
        self.assertEqual(self.policy.last_reason, "town:blocked:departure-unsatisfiable")
        self.assertEqual(self.policy._identify_staff_ready(board), False)
        self.assertEqual(self.policy._planned_mining_runs, None)

    def test_newly_installed_supply_restock_is_offered_on_the_same_board(self):
        base = self._mapless_refused_staff_routes()
        base = replace(base, inventory=tuple(
            replace(item, charges=20, pval=20) if item.tval == TVAL_STAFF else item
            for item in base.inventory
        ))
        # Constructed supply-specific boards, not effects of any posted key.
        # The ration case represents the ordinary ration-eating food branch.
        cases = (
            ("food_ready", replace(base, player=replace(base.player, food_type=FOOD_TYPE_RATION)), "general"),
            ("light_ready", replace(base,
                equipment=tuple(replace(item, fuel=LANTERN_REFILL_FUEL) if item.is_light else item for item in base.equipment),
                inventory=tuple(item for item in base.inventory if not item.is_oil)), "general"),
            ("teleport_ready", replace(base, inventory=tuple(
                item for item in base.inventory if not item.is_teleport_scroll)), "alchemist"),
            ("cure_critical_ready", replace(base, inventory=tuple(
                item for item in base.inventory
                if not (item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL))), "temple"),
        )
        saved = checkpoint(self.policy)
        for leaf, board, supplier in cases:
            with self.subTest(leaf=leaf):
                policy = restore_checkpoint(HengbotPolicy, saved)
                policy._town_store_attempted.update({store: board.turn for store in (0, 3, 4, 5)})
                policy._town_visit_ledger.nonhome_attempted_without_effect.update({
                    store: policy._town_observable_effect_state(board) for store in range(7)
                })
                self.assertEqual(policy._town_restock_wait_until, None)
                self.assertEqual(policy._recall_town_departure_conjuncts(board)[leaf], False)
                key = policy._town_special_key(board)
                print("CLASS C SAME BOARD", leaf, repr(key), policy.last_reason)
                self.assertEqual((key, policy.last_reason), (RESTOCK_WAIT_MACRO, "town:wait-restock:" + supplier))
                self.assertEqual(policy._town_blocked_reason, None)
                self.assertGreater(policy._town_restock_wait_until, board.turn)
                self.assertEqual(policy._recall_town_departure_conjuncts(board)[leaf], False)


if __name__ == "__main__":
    unittest.main()
