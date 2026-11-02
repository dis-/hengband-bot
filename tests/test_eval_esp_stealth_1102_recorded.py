"""Owner 2026-11-02: the equipment comparison values telepathy highly, stealth somewhat.

Owner: 「装備の比較方法は定義済のはずだが、改めて答えるとその中ではテレパシーを
高く評価、隠密を多少評価する」.  The comparison (survival / kill ratio, user
decision 2026-10-02) now carries equipment_utility.utility_value as a relative
bonus: full telepathy +10%, each limited ESP kind +1% (at most +5%), stealth
+0.5% per pval point.

Recorded board: the n1-a life-464 Warrior (Lv40) town board of decision 2293,
tests/fixtures/gloves-phase-1102.json.gz, replayed through the public
choose_key exactly as tests.test_gloves_phase_1102_recorded does.  The
production optimizer wrapper (_prepare_equipment_optimization) then runs on
that board's catalog (142 items: the incremental one-slot search from the worn
loadout).

DECLARED CONSTRUCTED (besides the replay's own calibration / ~f / ~9 seams):
one Home item per test, a copy of an owned item with one change:
- the worn ドラゴン・グローブ [4,+11] {r時} with to_a 8 (3 less AC) and
  TR_TELEPATHY;
- the Home ★センゲル王の金属帽子 [3,+12] (+3) with TR_STEALTH added (its
  pval 3 then also counts as stealth +3).
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import unittest
from dataclasses import replace

from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.equipment_utility import (
    STEALTH_POINT_BONUS,
    TELEPATHY_BONUS,
    TR_STEALTH,
    TR_TELEPATHY,
)
import test_gloves_phase_1102_recorded as gloves

WORN_GLOVES = "equipped:8f2b0ceb6cf8a721:0"
HOME_HEAD = "home:82938e84b092fb7f:0"  # ★センゲル王の金属帽子 [3,+12] (+3)



class EquipmentUtilityRecordedTest(unittest.TestCase):
    # The gloves file's fixture loading and replay, not its tests.
    setUpClass = classmethod(
        gloves.DragonGlovesNotJunkRecordedTest.setUpClass.__func__)
    setUp = gloves.DragonGlovesNotJunkRecordedTest.setUp
    _replay = gloves.DragonGlovesNotJunkRecordedTest._replay

    def _best_with_home_copy(self, source_id, change, copy_id):
        policy, _decided = self._replay(gloves.OUTSIDE_ROW)
        board = policy._decision_input_snapshot
        catalog = policy._equipment_catalog
        source = next(entry for entry in catalog.items if entry.id == source_id)
        # DECLARED CONSTRUCTED: the changed copy in Home (see the docstring).
        catalog._home[copy_id] = OwnedEquipment(copy_id, change(source.item), "home")
        preparation = policy._prepare_equipment_optimization(board)
        self.assertEqual(preparation.blockers, ())
        return preparation.result.best

    def test_telepathy_gloves_beat_the_higher_ac_worn_pair(self):
        best = self._best_with_home_copy(
            WORN_GLOVES,
            lambda item: replace(item, to_a=item.to_a - 3,
                                 known_flags=item.known_flags | {TR_TELEPATHY}),
            "home:telepathy-gloves")
        self.assertEqual(best.loadout.item_at("arms").id, "home:telepathy-gloves")
        self.assertEqual(best.metrics.utility_value, TELEPATHY_BONUS)

    def test_stealth_breaks_the_tie_of_an_equal_helm(self):
        best = self._best_with_home_copy(
            HOME_HEAD,
            lambda item: replace(item, known_flags=item.known_flags | {TR_STEALTH}),
            "home:stealth-helm")
        self.assertEqual(best.loadout.item_at("head").id, "home:stealth-helm")
        self.assertAlmostEqual(best.metrics.utility_value, 3 * STEALTH_POINT_BONUS)


if __name__ == "__main__":
    unittest.main()
