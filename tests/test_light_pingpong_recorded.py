"""Recorded light-slot oscillation and refill controls from the Linux soak."""

import tests  # noqa: F401 -- isolate runtime files for direct module runs

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    InventoryItem,
    SV_FLASK_OIL,
    TVAL_FLASK,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).parent / "fixtures" / "light-pingpong-20261017.json.gz"


class LightPingpongRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boards = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def test_captured_consecutive_boards_do_not_swap_back(self):
        lantern_board, torch_board = map(parse_snapshot, self.boards)
        self.assertEqual((lantern_board.turn, torch_board.turn), (1336545, 1336554))
        self.assertTrue(lantern_board.can_see_own_grid)
        self.assertTrue(torch_board.can_see_own_grid)
        policy = HengbotPolicy()

        self.assertEqual(policy._choose_key(lantern_board), "wn")
        self.assertEqual(policy.last_reason, "wield-light")
        self.assertEqual(policy._choose_key(torch_board), "8")
        self.assertEqual(policy.last_reason, "explore")

    def test_low_fuel_lantern_yields_to_torch_without_oil(self):
        lantern_board, torch_board = map(parse_snapshot, self.boards)
        policy = HengbotPolicy()

        self.assertEqual(policy._choose_key(lantern_board), "wn")
        self.assertEqual(policy.last_reason, "wield-light")
        self.assertIsNone(policy._light_to_wield(torch_board))
        self.assertIsNone(policy._darkness_torch(torch_board))

    def test_carried_oil_refills_low_fuel_equipped_lantern(self):
        lantern_board = parse_snapshot(self.boards[0])
        oil = InventoryItem(
            slot="z",
            name="Flask of oil",
            count=1,
            tval=TVAL_FLASK,
            sval=SV_FLASK_OIL,
            aware=True,
            known=True,
            fuel=5000,
        )
        # DECLARED CONSTRUCTED: add one carried oil flask to the captured board.
        with_oil = replace(lantern_board, inventory=[*lantern_board.inventory, oil])
        policy = HengbotPolicy()

        key = policy._choose_key(with_oil)

        self.assertEqual(key, "\\Fz")
        self.assertEqual(policy.last_reason, "refill-light")


if __name__ == "__main__":
    unittest.main()
