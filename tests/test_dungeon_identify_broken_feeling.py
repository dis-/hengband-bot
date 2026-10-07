"""Dungeon identification skips equipment already sensed as broken.

Live 2026-10-08: 21 Identify staff charges were spent in one dive, partly on
equipment whose pseudo feeling was already {壊れている} (broken) and which the
bot then destroyed.  Broken is not in PROTECTED_UNKNOWN_FEELINGS, so disposal
needs no identification; the dungeon identification selector must agree.
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import tests  # noqa: F401
from tests.test_home_light_alternation import _fresh_policy
from tests import test_home_light_alternation_cli as d6_pins


class DungeonIdentifyBrokenFeelingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sandbox = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _target_slot(self, snapshot):
        return next(item.slot for item in snapshot.inventory
                    if item.is_equipment and not item.known)

    def test_unsensed_unknown_equipment_is_still_identified(self):
        policy = _fresh_policy(self.sandbox)
        snapshot = d6_pins.PromptGatedIdentificationPins._snapshot()
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "identify:dungeon-equipment")
        self.assertEqual(key[-1], self._target_slot(snapshot))

    def test_broken_feeling_equipment_is_not_identified(self):
        policy = _fresh_policy(self.sandbox)
        snapshot = d6_pins.PromptGatedIdentificationPins._snapshot()
        slot = self._target_slot(snapshot)
        snapshot = replace(snapshot, inventory=tuple(
            replace(item, pseudo_feeling="broken") if item.slot == slot else item
            for item in snapshot.inventory))
        policy.choose_key(snapshot)
        self.assertNotEqual(policy.last_reason, "identify:dungeon-equipment")


if __name__ == "__main__":
    unittest.main()
