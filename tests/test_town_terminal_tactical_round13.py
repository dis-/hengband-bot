"""Round 13: tactical rungs do not acquire a town errand terminal."""
import tests  # noqa: F401

import unittest

from hengbot import town_terminal as tt
from hengbot.claim_ladder import rung_named
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


TACTICAL = ('_blocking_escape_melee_key', '_breeder_breakthrough_escape_key', '_breeder_breakthrough_key', '_choke_engagement_key', '_detected_threat_preparation_key', '_emergency_item', '_esp_threat_rest_key', '_fruitless_disengage_key', '_immobile_breeder_giveup_key', '_item_destroying_breeder_leave_key', '_melee_swarm_combat_key', '_paralyzer_prevention_key', '_ranged_attack_key#1', '_ranged_attack_key#2', '_summoner_ranged_kill_key', '_town_random_teleport_suppression_key', '_unseen_retreat_key')


class TacticalDeclarationTest(unittest.TestCase):
    def test_tactical_rungs_keep_their_selected_key_without_town_admissions(self):
        snap = board()
        for name in TACTICAL:
            with self.subTest(rung=name):
                policy = policy_on(snap)
                family = rung_named(name).family
                self.assertFalse(policy._town_gate_exempt(family))
                self.assertEqual(tt.TERMINALS[name].mode, tt.NO_REFUSAL)
                terminal = tt.rung_terminal(policy, name, snap)
                self.assertEqual(terminal.terminal_id, tt.NO_REFUSAL)
                self.assertIn("not a town errand", terminal.args[1])
                self.assertIn("src/hengbot/", terminal.args[1])
                self.assertNotIn(name, tt.SHADOW_RUNGS)
                self.assertIsNone(tt.TERMINALS[name].intended_terminal)
                calls = []
                def act():
                    calls.append(name)
                    return "5"
                self.assertEqual(policy._town_producer_entry(name, act), "5")
                self.assertEqual(calls, [name])
                self.assertEqual(policy._decision_terminal_admissions, [])
                self.assertEqual(policy._town_visit_ledger.closed_terminals, {})


if __name__ == "__main__":
    unittest.main()
