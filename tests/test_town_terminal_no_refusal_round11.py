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
        round12 = {
            "_conquest_loot_key", "_esp_threat_hunt_key",
            "_fundraising_combat_equipment_key", "_pack_pressure_identify_key",
            "_return_to_town_key#1", "_return_to_town_key#2", "_return_to_town_key#3",
            "_unprofitable_unique_disengage_key", "_wield_digging_tool_key",
            "_step_toward", "_step_toward:departure", "_step_toward:escape",
            "_step_toward:hunt", "_step_toward:positioning",
            "_dig_to_known_downstairs_key", "_entrance_travel_key", "idle-fallback",
            "navigator.decide",
        }
        round13 = {'_released_restock_store_key', '_recall_restock_key', '_summoner_ranged_kill_key', '_unseen_retreat_key', '_emergency_item', '_fruitless_disengage_key', '_town_random_teleport_suppression_key', '_blocking_escape_melee_key', '_paralyzer_prevention_key', '_ranged_attack_key#2', '_immobile_breeder_giveup_key', '_detected_threat_preparation_key', '_breeder_breakthrough_key', '_item_destroying_breeder_leave_key', '_ranged_attack_key#1', '_choke_engagement_key', '_esp_threat_rest_key', '_melee_swarm_combat_key', '_breeder_breakthrough_escape_key'}
        round14 = {"_home_catalogue_work_key", "_home_full_knowledge_key",
                   "home-errand-knowledge", "home-full-knowledge", "home-knowledge-after-exit",
                   "_town_order_step4_key#1", "_town_order_step4_key#2", "town-progress-committed-loot"}
        round15 = {'_chest_processing_key#1', '_kill_quest_floor_recovery_key', '_start_kill_quest_regeneration', '_normal_loot_key#2', '_normal_loot_key#1', '_chest_processing_key#2'}
        # 2026-10-31 dungeon-only rungs: the Greater Hell-Beast mining abort and
        # the D45 re-arm of a combat hand the digger swap left empty.
        dungeon_1031 = {'_mining_unbeatable_unique_abort_key', '_mining_loadout_rollback_key'}
        classified = EXPECTED | round12 | round13 | round14 | round15 | dungeon_1031
        self.assertEqual(set(tt.NO_REFUSAL_REASONS), classified)
        self.assertEqual({name for name, decl in tt.TERMINALS.items()
                          if decl.mode == tt.NO_REFUSAL}, classified)
        self.assertEqual(len(tt.SHADOW_RUNGS), 0)
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
