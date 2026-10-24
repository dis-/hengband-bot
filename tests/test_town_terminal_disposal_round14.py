"""Disposal keeps its selection/confirmation loop and admits the exact command."""
import tests  # noqa: F401

from dataclasses import replace
import pickle
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.item_reservation import ITEM_RESERVATION_SOURCES, ReservationVerdict
from hengbot.policy_state import normalize_policy_state
from policy_fixtures import item
import test_policy_home as home_fixtures
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


RUNGS = {"_overweight_surplus_sale_key", "_town_overflow_destroy_key",
         "_worthless_junk_destroy_key", "_full_pack_destroy_key", "_town_destroy_key",
         "verified-disposal"}


def target_board():
    target = item("a", 9, 0, name="unneeded statue", count=2, known=True)
    snap = replace(board(), inventory=[target])
    return policy_on(snap), snap, target


class DisposalAdmissionTest(unittest.TestCase):
    def test_foreign_reservation_keeps_the_denied_serializer_diagnostic(self):
        for enforced in (False, True):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                policy, snap, target = target_board()
                policy._town_claim_bar_enforced = enforced
                with patch.dict(tt.TERMINALS, {"verified-disposal":
                        tt.TERMINALS["verified-disposal"]._replace(mode=mode)}), \
                        patch("hengbot.item_reservation.item_reserved_by_other",
                              return_value=ReservationVerdict("destroy", "equipment-txn")):
                    key = policy._destroy_item_key(target, snap, policy=policy)
                self.assertIsNone(key)
                self.assertIsNone(policy._terminal_item_command)
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["terminal"][0], "item-command")
                self.assertEqual(row["codes"], ["item-command-reserved"])
                self.assertEqual(row["live"], [])
                self.assertEqual(row["mode"], mode)
                outcomes.append((key, policy.last_reason, policy._destroy_watch,
                                 repr(policy._decision_offer_buffer())))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_whole_stack_control_keeps_the_original_force_destroy_bytes(self):
        policy, snap, target = target_board()
        self.assertEqual(policy._destroy_item_key(target, snap, policy=policy), "02ka")
        self.assertEqual(policy._destroy_item_key(target), "02ka")
        self.assertIsNone(policy._terminal_item_command)
        self.assertEqual(policy._decision_terminal_admissions, [])

    def test_partial_quantity_refusal_preserves_the_existing_serializer_error(self):
        outcomes = []
        for mode in (tt.SHADOW, tt.ENFORCE):
            policy, snap, target = target_board()
            with patch.dict(tt.TERMINALS, {"verified-disposal":
                    tt.TERMINALS["verified-disposal"]._replace(mode=mode)}), \
                    patch("hengbot.item_reservation.item_reserved_by_other",
                          return_value=ReservationVerdict("overweight-surplus", quantity=0)):
                key = policy._town_item_command_entry_key(snap, "overweight-surplus", target, "shop-sell")
            self.assertIsNone(key)
            row, = policy._decision_terminal_admissions
            self.assertEqual(row["codes"], ["disposal-quantity-invalid"])
            self.assertEqual(policy.last_reason, "ownership:item-reserved:overweight-surplus:serializer-error")
            outcomes.append((key, policy.last_reason, repr(policy._decision_offer_buffer())))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_partial_control_uses_the_observed_surplus_quantity(self):
        policy, snap, target = target_board()
        with patch.object(policy, "_retention_surplus", return_value=1), \
                patch("hengbot.item_reservation.item_reserved_by_other", return_value=None):
            self.assertEqual(policy._town_item_command_entry_key(
                snap, "overweight-surplus", target, "shop-sell"), "01ka")
        self.assertIsNone(policy._terminal_item_command)

    def test_overweight_dispatch_cannot_bypass_the_selected_command_admission(self):
        fixture = home_fixtures.WeightOverloadTownTest()
        snap = fixture._snapshot()
        target = replace(snap.inventory[0], count=3, weight=1000)
        snap = replace(snap, inventory=[target])
        for reserved in (False, True):
            policy = policy_on(snap)
            policy._overweight_surplus_disposal = {"town": policy._effective_town_id(snap)}
            selection = SimpleNamespace(surplus=((0, 0, target, 3, ()),))
            verdict = ReservationVerdict("overweight-surplus", "equipment-txn") if reserved else None
            with patch.object(policy, "_weight_relief_selection", return_value=selection), \
                    patch("hengbot.item_reservation.item_reserved_by_other", return_value=verdict):
                key = policy._overweight_surplus_sale_key(snap)
            self.assertEqual(key is None, reserved)
            if reserved:
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["item-command-reserved"])
                self.assertNotIn("key", policy._overweight_surplus_disposal["pending"])

    def test_dungeon_destruction_keeps_its_bytes_without_a_town_entry(self):
        policy, snap, target = target_board()
        snap = replace(snap, floor_key=(0, 1, 1), town_flag=False)
        with patch.object(policy, "_town_item_command_entry_key", side_effect=AssertionError("town entry")):
            self.assertEqual(policy._destroy_item_key(target, snap, policy=policy), "02ka")

    def test_repeated_material_reads_are_pure_and_context_is_restored_on_error(self):
        policy, snap, target = target_board()
        policy._terminal_item_command = ("destroy", target, "identification", None)
        before = pickle.dumps(vars(policy))
        material = tt.gather_item_command(policy, snap)
        terminal = tt.item_command_intended_terminal(policy, snap)
        self.assertEqual(tt.gather_item_command(policy, snap), material)
        self.assertEqual(tt.item_command_intended_terminal(policy, snap), terminal)
        self.assertEqual(pickle.dumps(vars(policy)), before)
        previous = policy._terminal_item_command
        with patch.object(policy, "_town_producer_entry", side_effect=RuntimeError("compose failed")):
            with self.assertRaisesRegex(RuntimeError, "compose failed"):
                policy._town_item_command_entry_key(snap, "destroy", target, "identification")
        self.assertIs(policy._terminal_item_command, previous)
        del policy.__dict__["_terminal_item_command"]
        self.assertIsNone(normalize_policy_state(policy)._terminal_item_command)
        self.assertEqual(ITEM_RESERVATION_SOURCES["_terminal_item_command"][0], "selection")

    def test_all_dispatchers_preserve_selection_observation_and_named_closes(self):
        snap = board()
        policy = policy_on(snap)
        for rung in RUNGS:
            self.assertEqual(tt.TERMINALS[rung].mode, tt.ENFORCE)
            self.assertNotIn(rung, tt.SHADOW_RUNGS)
            terminal = tt.rung_terminal(policy, rung, snap)
            self.assertEqual(terminal, tt.TerminalRef(tt.NO_REFUSAL, ("item-command-dispatch",)))
            self.assertTrue(tt.terminal_admission(policy, snap, terminal).admitted)


if __name__ == "__main__":
    unittest.main()
