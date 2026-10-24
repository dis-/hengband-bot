import tests  # noqa: F401

from dataclasses import replace
import unittest

from hengbot import policy_town as policy_town_module
from hengbot.model import Position, STORE_HOME
from tests.test_town_decision_speed_caches import (
    build_policy,
    load_rows,
    parse_board,
)


class TownDecisionSpeed2CachePins(unittest.TestCase):
    def test_same_board_next_preparation_hits_signature_cache(self):
        from unittest.mock import patch
        from tests.test_policy_equipment import EquipmentQuarantineInvariantTest
        from hengbot import policy_equipment

        policy, board, _ring, _identity = (
            EquipmentQuarantineInvariantTest()._policy_with_home_ring())
        with patch.object(policy_equipment, 'prepare_warrior_optimization',
                          wraps=policy_equipment.prepare_warrior_optimization) as search:
            first = policy._prepare_equipment_optimization(board, depth_override=31)
            self.assertIsNotNone(first.result)
            self.assertEqual(search.call_count, 1)
            self.assertEqual(policy._equipment_optimization_telemetry['result_source'],
                             'fresh-search')
            # End the transaction owner so its early return cannot masquerade
            # as a signature hit; no board or equipment input changes.
            policy._equipment_transaction_session = None
            policy._decision_sequence += 1
            second = policy._prepare_equipment_optimization(board, depth_override=31)
            self.assertIs(second, first)
            self.assertEqual(policy._equipment_optimization_telemetry['result_source'],
                             'signature-cache-hit')
            self.assertEqual(search.call_count, 1)

    def test_claim_candidate_cache_pin(self):
        from tests.test_town_decision_speed_caches import TownDecisionSpeedCacheTest
        TownDecisionSpeedCacheTest().test_recorded_board_pins_claim_candidate_reuse()

    def test_map_offer_cache_pin(self):
        from tests.test_town_decision_speed_caches import TownDecisionSpeedCacheTest
        TownDecisionSpeedCacheTest().test_unchanged_map_reuses_fixed_quest_offers()

    def test_store_position_index_cache_pin(self):
        from tests.test_town_decision_speed_caches import TownDecisionSpeedCacheTest
        TownDecisionSpeedCacheTest().test_town_fact_refresh_reuses_store_position_index()

    def test_region_change_discards_store_position_index(self):
        board = parse_board(load_rows("A")[0])
        policy = build_policy()
        policy.prime(board)
        position = Position(1, 1)
        policy._town_fact_region = policy._grid_region(board)
        policy._town_fact_snapshot = None
        policy._town_store_positions = {STORE_HOME: {position}}
        policy_town_module._town_store_position_indices[policy] = {
            position: [STORE_HOME]
        }
        floor_key = board.floor_key
        changed_floor = (floor_key[0] + 1, *floor_key[1:])
        changed = replace(board, floor_key=changed_floor, grids={})
        policy._emitted_t = set()

        policy._refresh_town_facts(changed)

        self.assertEqual(policy._town_store_positions, {})
        self.assertEqual(
            policy_town_module._town_store_position_index(policy), {}
        )


if __name__ == "__main__":
    unittest.main()
