import tests  # noqa: F401
import unittest
from unittest.mock import patch

from hengbot.model import Snapshot
from hengbot.policy import HengbotPolicy
from tests.policy_fixtures import player


class CalibrationDepartureTest(unittest.TestCase):
    def test_unavailable_keeps_current_gear_and_depth_gates(self):
        policy = HengbotPolicy(monrace_knowledge={})
        snapshot = Snapshot(turn=1, player=player(1, 1, class_id=0), grids={},
                            visible_monsters=(), inventory=(), equipment=())
        with patch.object(policy, "_validated_character_calibration", return_value=None):
            self.assertTrue(policy._equipment_departure_ready(snapshot))
            self.assertIn("resist_chaos", policy._missing_required_abilities(snapshot, 31))
            self.assertIn("resist_neth", policy._missing_required_abilities(snapshot, 40))

