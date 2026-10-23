"""ROOT-FIX S2-d: the space-reserve Home deposit's terminal.

``_town_space_deposit_key`` declares ``("home-deposit", ("space-reserve",))``
while the pack reserve can be restored at Home.  While stage-2 quest travel
owns the town (``_fixed_quest_prepare_return_required``, rung #1) the rung
does not apply: the check moved from the key's body into its intended
terminal.  The deposit yields to the town order's reward work
(``town-order-step4-pending``, served by quest-request); the rung is SHADOW
until the S2 ENFORCE flip, so that refusal is recorded only.

Board: the CONSTRUCTED goldburn seam (row 3512, Telmora; see
test_goldburn_shopping_constructed).  Actionability, the predicate and the
order step are DECLARED CONSTRUCTED patches.
"""

import tests  # noqa: F401

import unittest
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import (
    NOT_APPLICABLE,
    REFUSAL_SERVERS,
    Server,
    TerminalRef,
    gather_home_deposit,
    verdict_home_deposit,
)
from test_goldburn_shopping_constructed import board

RUNG = "_town_space_deposit_key"
DEPOSIT = TerminalRef("home-deposit", ("space-reserve",))


def _entry(policy, snap):
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    calls = []
    key = policy._town_producer_entry(RUNG, lambda: calls.append("ran") or "7")
    return key, calls, policy._decision_terminal_admissions


class SpaceDepositTerminalTest(unittest.TestCase):
    def run_rung(self, *, actionable=True, required=False, step4=False):
        policy = HengbotPolicy()
        snap = board()
        with patch.object(HengbotPolicy, "_town_space_deposit_actionable",
                          return_value=actionable), \
                patch.object(HengbotPolicy, "_fixed_quest_prepare_return_required",
                             return_value=required), \
                patch.object(HengbotPolicy, "_town_order_step4_pending",
                             return_value=step4):
            return town_terminal.rung_terminal(policy, RUNG, snap), _entry(policy, snap)

    def test_quest_return_owns_the_town_the_rung_does_not_apply(self):
        terminal, (key, calls, rows) = self.run_rung(required=True)
        self.assertEqual(terminal, NOT_APPLICABLE)
        self.assertEqual((key, calls, rows), (None, [], []))

    def test_control_without_quest_return_the_deposit_runs(self):
        terminal, (key, calls, rows) = self.run_rung()
        self.assertEqual(terminal, DEPOSIT)
        self.assertEqual((key, calls, rows), ("7", ["ran"], []))

    def test_nothing_to_deposit_has_no_terminal(self):
        terminal, (key, calls, _rows) = self.run_rung(actionable=False)
        self.assertIsNone(terminal)
        self.assertEqual((key, calls), ("7", ["ran"]))

    def test_order_reward_work_refuses_in_shadow(self):
        terminal, (key, calls, rows) = self.run_rung(step4=True)
        self.assertEqual(terminal, DEPOSIT)
        # SHADOW: recorded, the producer still runs.
        self.assertEqual((key, calls), ("7", ["ran"]))
        row, = rows
        self.assertEqual((row["terminal"], row["codes"], row["mode"]),
                         (["home-deposit", ["space-reserve"]],
                          ["town-order-step4-pending"], "shadow"))
        self.assertEqual(REFUSAL_SERVERS["town-order-step4-pending"],
                         (Server("quest-request"),))

    def test_verdict_branches(self):
        policy = HengbotPolicy()
        snap = board()
        with patch.object(HengbotPolicy, "_town_order_step4_pending", return_value=True):
            self.assertEqual(verdict_home_deposit(gather_home_deposit(policy, snap)).codes,
                             ("town-order-step4-pending",))
        self.assertTrue(verdict_home_deposit(gather_home_deposit(policy, snap)).admitted)


class SpaceDepositBodyTest(unittest.TestCase):
    def test_the_body_no_longer_asks_the_quest_predicate(self):
        # The terminal owns the check; called directly, the body walks on.
        policy = HengbotPolicy()
        snap = board()
        with patch.object(HengbotPolicy, "_town_space_deposit_actionable", return_value=True), \
                patch.object(HengbotPolicy, "_fixed_quest_prepare_return_required",
                             return_value=True), \
                patch.object(HengbotPolicy, "_town_claims_active",
                             return_value=False) as claims:
            policy._town_space_deposit_key(snap)
        self.assertEqual(claims.call_count, 1)


if __name__ == "__main__":
    unittest.main()
