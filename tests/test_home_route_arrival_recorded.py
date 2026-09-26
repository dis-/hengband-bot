import tests  # noqa: F401 -- live runtime-file isolation for bare module runs

import gzip
import json
from pathlib import Path
import unittest

from hengbot.model import Position, STORE_HOME, parse_snapshot
from hengbot.policy import (
    EquipmentTransaction,
    EquipmentTransactionPlan,
    EquipmentTransactionSession,
    HengbotPolicy,
    PHASE_HOME_PREPARE,
)
from hengbot.town_maps import TownMap


CAPTURE = (
    Path(__file__).parent / "fixtures" / "home-route-arrival-20260926.json.gz"
)


class HomeRouteArrivalRecordedTest(unittest.TestCase):
    def test_dark_home_arrival_enters_instead_of_blocking_route(self):
        with gzip.open(CAPTURE, "rt", encoding="utf-8") as stream:
            records = json.load(stream)
        self.assertEqual([row["sequence"] for row in records], [2518, 2519])
        self.assertEqual([row["key"] for row in records], ["3", "5"])
        self.assertEqual(
            [row["reason"] for row in records],
            [
                "equipment-transaction:approach-home",
                "equipment-transaction:home-route-unavailable",
            ],
        )
        self.assertEqual(
            [row["home_unsatisfied_passes"] for row in records], [16, 16]
        )
        self.assertEqual(
            [row["equipment_transaction"]["entry_blocker"] for row in records],
            [None, "session-not-executable"],
        )
        snapshots = [parse_snapshot(row["board"], {}) for row in records]
        entrance = Position(41, 131)
        self.assertEqual([s.player.position for s in snapshots], [Position(40, 130), entrance])
        self.assertTrue(all(s.store is None for s in snapshots))
        self.assertEqual(snapshots[1].grid_at(entrance).store_number, -1)
        self.assertFalse(snapshots[1].grid_at(entrance).lit)
        self.assertEqual(
            [row["transaction_next"]["item_id"] for row in records],
            ["home:33d89c1cd5b84647:0"] * 2,
        )

        # The capture's two consecutive boards run until the first changed
        # key.  Only the active transaction and remembered store coordinate
        # are reconstructed; neither invents a new observation.
        town_map = TownMap(
            "Morivant", 198, 66,
            frozenset({Position(40, 130), entrance}),
            stores={STORE_HOME: entrance},
        )
        policy = HengbotPolicy(town_maps={2: town_map})
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw",
            "home:33d89c1cd5b84647:0", item_identity="captured-target",
        )
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0), physical_context="home"
        )
        for row, snapshot in zip(records, snapshots):
            policy._floor_t = {
                (grid.position.y, grid.position.x)
                for grid in snapshot.grids.values() if grid.passable
            }
            policy._decision_sequence = row["sequence"]
            key = policy._equipment_transaction_town_key(snapshot)
            if row["sequence"] == 2518:
                self.assertEqual((key, policy.last_reason), ("3", row["reason"]))
                policy.confirm_key_posted(key)
                continue
            # R4: stop at the first divergence from the live key's reason.
            self.assertEqual(key, row["key"])
            self.assertEqual(
                policy.last_reason, "equipment-transaction:travel-home:await-entry"
            )
            self.assertNotEqual(policy.last_reason, row["reason"])
            self.assertEqual(policy._equipment_transaction_session.blockers, [])
            self.assertTrue(policy._intentional_entrance_activation)
            break


if __name__ == "__main__":
    unittest.main()
