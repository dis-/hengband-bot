"""Remaining refusal confirmations: compare real bodies with skipped bodies."""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import STORE_HOME
from hengbot.policy_constants import TOWN_TELEPORT_COST
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


class RefusalConfirmationTest(unittest.TestCase):
    def test_fare_refusal_preserves_the_body_record_and_reason(self):
        for destination in (0, 1):
            with self.subTest(destination=destination):
                snap = replace(board(), player=replace(board().player, gold=0))
                expected = policy_on(snap)
                self.assertIsNone(expected._town_teleport_dispatch_key(
                    snap, destination, producer="cross-town", reason="trip"))
                actual = policy_on(snap)
                decl = tt.TERMINALS["town-teleport"]
                with patch.dict(tt.TERMINALS, {
                        "town-teleport": tt.TerminalDecl(decl.intended_terminal, tt.ENFORCE)}), \
                        patch.object(actual, "_town_teleport_dispatch_key",
                                     side_effect=AssertionError("refused body ran")):
                    self.assertIsNone(actual._town_teleport_key(
                        snap, destination, producer="cross-town", reason="trip"))
                self.assertEqual(actual.town_teleport_refusal, expected.town_teleport_refusal)
                self.assertEqual(actual.last_reason, expected.last_reason)
                self.assertEqual(actual.town_teleport_refusal["required_gold"],
                                 TOWN_TELEPORT_COST * (1 if destination == 0 else 2))
                self.assertIsNone(actual._terminal_town_travel)

    def test_route_refusal_does_not_fabricate_a_fare_refusal(self):
        snap = replace(board(), player=replace(board().player, gold=2*TOWN_TELEPORT_COST))
        policy = policy_on(snap)
        decl = tt.TERMINALS["town-teleport"]
        with patch.dict(tt.TERMINALS, {
                "town-teleport": tt.TerminalDecl(decl.intended_terminal, tt.ENFORCE)}), \
                patch.object(policy, "_town_teleport_building_positions", return_value=None), \
                patch.object(policy, "_town_teleport_dispatch_key",
                             side_effect=AssertionError("refused body ran")):
            self.assertIsNone(policy._town_teleport_key(snap, 0, producer="cross-town"))
        self.assertIsNone(policy.town_teleport_refusal)
        self.assertNotEqual(policy.last_reason, "town:teleport-refused-fare")

    def test_home_full_deposit_refusal_preserves_no_step_offer(self):
        snap = board()
        rows = []
        for enforce in (False, True):
            policy = policy_on(snap)
            policy._shopping_approach_store_type = STORE_HOME
            # This branch checks presence only: the relief's state is owned by its server.
            policy._home_full_relief = object()
            decl = tt.TERMINALS["home-atomic-deposit"]
            no_steps = []
            def producer():
                if enforce:
                    raise AssertionError("refused body ran")
                return policy._atomic_home_deposit_dispatch_key(snap, snap.player.position)
            with patch.dict(tt.TERMINALS, {
                    "home-atomic-deposit": tt.TerminalDecl(
                        decl.intended_terminal, tt.ENFORCE if enforce else tt.SHADOW)}), \
                    patch.object(policy, "_offer_home_atomic_no_step",
                                 side_effect=lambda *args: no_steps.append(args)):
                self.assertIsNone(policy._town_producer_entry(
                    "home-atomic-deposit", producer, family="home-visit"))
            rows.append(no_steps)
        self.assertEqual(rows, [[("deposit", "home-full-sale-pending")]] * 2)


if __name__ == "__main__":
    unittest.main()
