"""Recorded pin: the survival / kill ratio on the 2026-09-25 Home-withdraw board.

User decisions 2026-10-02: 「生存÷撃破の比で比べる」 and 「足切りも比に置き換える」.
tests/test_home_withdraw_failed_stock_present_recorded.py pins, on its first
changed board (index 5, the recorded '5pb1\r\x1b' Home withdraw), that the
pre-ratio optimizer keeps the worn ★大鎌『アヴァビア』 + shield kit; that pin
now runs behind the declared wall in tests/recorded_loadout.py.  This pin is
the same board under the production rule: the shield comes off for a
two-handed Avabia (survival 12.632 -> 12.174, DPS 154.8 -> 169.9, ratio
3.145 -> 3.327).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from hengbot.cli import _consume_response_sequence
from hengbot.equipment_optimizer import current_loadout
from hengbot.warrior_optimization import (
    WarriorEvaluatorCache, load_character_calibration,
    prepare_warrior_optimization,
)

import test_home_withdraw_failed_stock_present_recorded as withdraw
from test_esp_threat_rest_recorded import _policy


def _names(loadout):
    return sorted((slot, owned.item.name) for slot, owned in loadout.slots)


class MarginRatioHomeWithdrawDivergenceRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        withdraw.HomeWithdrawFailedStockPresentRecordedTest.setUpClass()
        replay = withdraw.HomeWithdrawFailedStockPresentRecordedTest
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, replay.monrace)
            policy._character_calibration_path.write_bytes(
                withdraw.CALIBRATION.read_bytes())
            cls.rows = []
            for index in range(6):
                _decoded, snapshots = _consume_response_sequence(
                    replay._board_lines(index), policy, lambda _key: True,
                    replay.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                key = policy.choose_key(board)
                cls.rows.append((str(key), policy.last_reason))
                policy.confirm_key_posted(key)
            cls.items = policy._equipment_catalog.items
            cache = WarriorEvaluatorCache()
            cls.preparation = prepare_warrior_optimization(
                policy._with_cached_skill_exp(board), cls.items, replay.monrace,
                depth=None, home_scan_complete=True, evaluator_cache=cache,
                calibration=load_character_calibration(withdraw.CALIBRATION),
            )
            cls.evaluator = cache.evaluator

    def test_the_board_is_the_recorded_home_withdraw(self):
        self.assertEqual(self.rows[5], ("5pb1\r\x1b", "home:atomic-withdraw"))
        self.assertEqual(self.preparation.blockers, ())

    def test_the_ratio_drops_the_shield_for_two_handed_avabia(self):
        result = self.preparation.result
        worn = current_loadout(self.items)
        best = result.best
        # Same kit, the shield taken off: Avabia two-handed.
        self.assertEqual(best.loadout.hand_mode, "two_handed")
        self.assertIsNone(best.loadout.item_at("sub_hand"))
        self.assertIsNotNone(worn.item_at("sub_hand"))
        self.assertIn("シールド", worn.item_at("sub_hand").item.name)
        self.assertEqual(
            best.loadout.item_ids,
            worn.item_ids - {worn.item_at("sub_hand").id},
        )
        shield = self.evaluator(worn).metrics
        two_handed = best.metrics
        self.assertAlmostEqual(shield.survival_turns, 12.632, places=3)
        self.assertAlmostEqual(shield.combat_margin, 3.145, places=3)
        self.assertAlmostEqual(shield.expected_dps, 154.8, places=1)
        self.assertAlmostEqual(two_handed.survival_turns, 12.174, places=3)
        self.assertAlmostEqual(two_handed.combat_margin, 3.327, places=3)
        self.assertAlmostEqual(two_handed.expected_dps, 169.9, places=1)

if __name__ == "__main__":
    unittest.main()
