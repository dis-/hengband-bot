"""Round 11: explicit reasons for the non-refusable selector/close family."""
import tests  # noqa: F401

import unittest

from hengbot import town_terminal as tt
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


EXPECTED = frozenset({
    '_direction_key#1',
    '_direction_key#2',
    '_explore_step#2',
    '_flee_step#2',
    '_flee_step#3',
    '_flee_step#4',
    '_home_full_skip_key',
    '_hunt_step#1',
    '_hunt_step#2',
    '_hunt_step#3',
    '_unseen_retreat_intercept_key',
    'frontier-probe',
    'oscillating-probe',
})


class NoRefusalDeclarationTest(unittest.TestCase):
    def test_the_13_classified_rungs_have_reasons_and_no_shadow(self):
        self.assertEqual(set(tt.NO_REFUSAL_REASONS), EXPECTED)
        self.assertEqual({name for name, decl in tt.TERMINALS.items()
                          if decl.mode == tt.NO_REFUSAL}, EXPECTED)
        self.assertEqual(len(tt.SHADOW_RUNGS), 76)
        self.assertTrue(EXPECTED.isdisjoint(tt.SHADOW_RUNGS))
        for name in EXPECTED:
            decl = tt.TERMINALS[name]
            self.assertIsNone(decl.intended_terminal, name)
            self.assertEqual(decl.no_refusal_reason, tt.NO_REFUSAL_REASONS[name])
            self.assertTrue(decl.no_refusal_reason.strip(), name)

    def test_each_selector_or_named_close_preserves_its_result(self):
        snap = board()
        for name in EXPECTED:
            policy = policy_on(snap)
            terminal = tt.rung_terminal(policy, name, snap)
            self.assertEqual(terminal, tt.TerminalRef(
                tt.NO_REFUSAL, (name, tt.NO_REFUSAL_REASONS[name])))
            self.assertTrue(tt.terminal_admission(policy, snap, terminal).admitted)
            selected = object()
            family = "explore" if name in {"frontier-probe", "oscillating-probe"} else None
            self.assertIs(policy._town_producer_entry(
                name, lambda: selected, family=family), selected)
            self.assertEqual(policy._decision_terminal_admissions, [])
            self.assertEqual(policy._town_visit_ledger.closed_terminals, {})


if __name__ == "__main__":
    unittest.main()
