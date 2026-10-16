import gzip
import json
from dataclasses import replace
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import Position, STORE_HOME, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.town_maps import find_outpost_map, parse_town_map

FIXTURE = Path(__file__).parent / "fixtures/eqtxn-newchar-route-20261017.jsonl.gz"
REPO = Path(__file__).resolve().parent.parent


def captured_episode():
    row = json.loads(gzip.decompress(FIXTURE.read_bytes()).decode("utf-8"))
    snapshot = parse_snapshot(row["snapshot"])
    town_map = parse_town_map(find_outpost_map(REPO))
    policy = HengbotPolicy(town_map=town_map, town_maps={0: town_map})
    policy.prime(snapshot)
    return row, snapshot, town_map, policy


def deposit_session(snapshot, target):
    action = EquipmentTransaction(
        PHASE_HOME_PREPARE,
        "deposit",
        "pack:ec2e53c16a3761bb:1" if equipment_identity(target) == "ec2e53c16a3761bb" else "pack:unreserved:0",
        item_identity=equipment_identity(target),
        move_identity=equipment_move_identity(target),
    )
    return EquipmentTransactionSession(
        EquipmentTransactionPlan((action, action), (), 1),
        physical_context="home",
    )


class EquipmentTransactionNewCharacterRouteTest(unittest.TestCase):
    def test_captured_reserved_deposit_is_closed_before_route_retry(self):
        row, snapshot, town_map, policy = captured_episode()
        self.assertEqual(
            [(item["decision_sequence"], item["key"], item["reason"])
             for item in row["captured_decisions"]],
            [
                (4, "5", "equipment-transaction:home-route-unavailable"),
                (5, "5", "equipment-transaction:abandon-blocked"),
                (6, "5", "equipment-transaction:home-route-unavailable"),
                (7, "5", "equipment-transaction:abandon-blocked"),
                (8, "5", "equipment-transaction:home-route-repeat-terminal"),
            ],
        )
        target = next(
            item for item in snapshot.inventory
            if equipment_identity(item) == "ec2e53c16a3761bb"
        )
        self.assertEqual(snapshot.player.position, Position(45, 124))
        self.assertEqual(town_map.store_position(STORE_HOME), Position(45, 123))
        self.assertEqual(policy._retention_reservation(snapshot, target), 5)
        self.assertIn(policy._item_signature(target), policy._home_visit_keep_set(snapshot))
        self.assertEqual(
            policy._town_map_goal_route(snapshot, Position(45, 123)).remaining_edges,
            1,
        )
        session = deposit_session(snapshot, target)
        policy._equipment_transaction_session = session

        key = policy._equipment_transaction_town_key(snapshot)

        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason, "equipment-transaction:retain-reserved")
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertEqual(
            policy._equipment_transaction_visit_closure["reason"], "retain-reserved"
        )
        self.assertIsNone(policy._equipment_transaction_route_terminal)
        preparation = policy._prepare_equipment_optimization(snapshot)
        self.assertIsNone(preparation)
        self.assertEqual(
            policy._equipment_optimization_telemetry["result_source"],
            "town-visit-transaction-closed",
        )

    def test_genuinely_unreachable_home_still_reaches_visible_terminal(self):
        _row, snapshot, town_map, policy = captured_episode()
        target = next(
            item for item in snapshot.inventory
            if equipment_identity(item) == "2810c60978548246"
        )
        start = Position(10, 10)
        isolated_map = replace(town_map, walkable=frozenset({start}))
        policy._town_map = None
        policy._town_maps = {}
        policy._floor_t = frozenset()
        policy._door_t = frozenset()
        policy._rubble_t = frozenset()
        start_grid = replace(snapshot.grid_at(snapshot.player.position), position=start)
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=start),
            grids={start: start_grid},
        )
        self.assertIsNone(
            policy._town_map_goal_route(snapshot, isolated_map.store_position(STORE_HOME))
        )

        for _ in range(2):
            policy._equipment_transaction_session = deposit_session(snapshot, target)
            self.assertEqual(
                policy._equipment_transaction_town_key(snapshot), "5"
            )
            self.assertEqual(
                policy.last_reason, "equipment-transaction:home-route-unavailable"
            )
            policy._abandon_blocked_equipment_transaction(snapshot)

        self.assertEqual(
            policy._equipment_transaction_route_terminal,
            "equipment-transaction:home-route-repeat-terminal",
        )

    def test_reachable_home_withdrawal_keeps_its_route(self):
        _row, snapshot, town_map, policy = captured_episode()
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE,
            "withdraw",
            "home:recorded-swap-item:0",
            item_identity="recorded-swap-item",
        )
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            physical_context="home",
        )

        step = policy._shopping_approach_step(
            snapshot, STORE_HOME, requester="equipment-txn"
        )

        self.assertEqual(step, Position(45, 123))
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
        self.assertEqual(town_map.store_position(STORE_HOME), step)


if __name__ == "__main__":
    unittest.main()
