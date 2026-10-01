import tests  # noqa: F401
import unittest

from hengbot.model import Snapshot, STORE_HOME
from hengbot.policy import HengbotPolicy
from tests.policy_fixtures import player


class CalibrationDepartureTest(unittest.TestCase):
    def test_unavailable_keeps_current_gear_and_depth_gates(self):
        policy = HengbotPolicy(monrace_knowledge={})
        snapshot = Snapshot(turn=1, player=player(1, 1, class_id=0), grids={},
                            visible_monsters=(), inventory=(), equipment=())
        self.assertTrue(policy._equipment_departure_ready(snapshot))
        self.assertIn("resist_chaos", policy._missing_required_abilities(snapshot, 31))
        self.assertIn("resist_neth", policy._missing_required_abilities(snapshot, 40))
        # Scenario input: Home has already proved unreachable this visit.
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        self.assertIsNone(policy._terminal_equipment_blocker(snapshot))

