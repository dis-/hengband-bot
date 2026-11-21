"""A drained stat does not move the loadout: n1-b life-413's main_ring round trip (2026-11-22).

n1-b life-413 (Magic-Eater Lv37) came back from Quest 25 with STR drained (natural 84 -> 74).
At the drained STR the loadout search put 殺戮の指輪 (+13,+7) in place of the worn
腕力の指輪 (+5) {+腕} (decisions 272/279, melee 257.5).  The visit then bought and drank
腕力復活の薬 (decision 363); the visible STR changed, the calibration was dropped and
re-derived by the next dump (policy_calibration ``_validated_character_calibration`` ->
``visible-current-changed``, then the new constants reset the search signature), and the
search at the restored STR (decision 373, melee 261.5) put the strength ring back:
A -> B -> A, the E0 stop ``town:blocked:equipment-slot-flipflop:main_ring``.

The answer changed because the selector read the drained ``stat_cur`` as the character's,
although the same visit restores it (base-status.cpp res_stat sets stat_cur to stat_max).
warrior_optimization ``loadout_natural_stats`` reads a drained stat at its printed maximum,
so the drained and the restored boards choose the same ring and the visit wears it once.

Recorded: tests/extract_n1b_413_ring_flipflop_fixture.py (boards of decisions 363 and 373,
the arrival's worn strength ring, the restored calibration; the drained calibration is
declared constructed there).  The catalogue is the board's worn set plus the other ring at
Home: the slot the round trip moved, every other slot as worn.  It reproduces the live
melee of both searches (257.516 / 261.507).
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import lzma
import pickle
import unittest
from pathlib import Path

import hengbot.policy  # noqa: F401 -- import order (circular import when run alone)
from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.warrior_optimization import loadout_natural_stats, prepare_warrior_optimization

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-ring-flipflop-1122" / "recorded.pkl.xz"
STRENGTH_RING = "腕力の指輪 (+5) {+腕}"
DRAINED_MELEE = 257.5164060378876     # loadout-report 02:23:45-02:24:11 (natural STR 74)
RESTORED_MELEE = 261.50658817763696   # loadout-report 02:24:16 (natural STR 84)


class RingFlipflopRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.recorded = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))

    def choose(self, board, other_ring, calibration):
        """The search's ring and melee: the board's worn set, the other ring at Home."""
        items = tuple(OwnedEquipment(f"equipped:{item.slot}", item, "equipped",
                                     equipped_slot=item.slot)
                      for item in board.equipment if item.is_equipment)
        items += (OwnedEquipment("home:ring", other_ring, "home"),)
        preparation = prepare_warrior_optimization(
            board, items, self.recorded["knowledge"], depth=80, home_scan_complete=True,
            has_destruction=True, calibration=calibration, timeout_seconds=120.0)
        self.assertEqual(preparation.blockers, ())
        best = preparation.result.best
        return best.loadout.item_at("main_ring").item.name, best.metrics.expected_dps

    def test_recorded_boards(self):
        drained, restored = self.recorded["drained_board"], self.recorded["restored_board"]
        self.assertEqual(self.recorded["decisions"], (363, 373))
        self.assertEqual(drained.player.drained_stats, ("str",))
        self.assertEqual(restored.player.drained_stats, ())
        self.assertEqual(drained.player.stat_max[0], 84)
        self.assertEqual(self.recorded["drained_calibration"].natural_stats[0], 74)
        self.assertEqual(self.recorded["restored_calibration"].natural_stats[0], 84)

    def test_restored_strength_chooses_the_strength_ring(self):
        """Decision 373 as recorded (control: main and the fix agree)."""
        restored = self.recorded["restored_board"]
        killing = next(item for item in restored.equipment if item.slot == "main_ring")
        self.assertNotEqual(killing.name, STRENGTH_RING)
        ring, melee = self.choose(restored, self.recorded["strength_ring"],
                                  self.recorded["restored_calibration"])
        self.assertEqual(ring, STRENGTH_RING)
        self.assertAlmostEqual(melee, RESTORED_MELEE, places=6)

    def test_drained_strength_chooses_the_same_ring(self):
        """Decision 363's board, STR still drained: the ring the restore will want.

        On main the drained natural STR chose 殺戮の指輪 (melee 257.5), the first half of
        the round trip."""
        ring, melee = self.choose(self.recorded["drained_board"], self.recorded["strength_ring"],
                                  self.recorded["drained_calibration"])
        self.assertEqual(ring, STRENGTH_RING)
        self.assertAlmostEqual(melee, RESTORED_MELEE, places=6)
        self.assertNotAlmostEqual(melee, DRAINED_MELEE, places=3)

    def test_loadout_natural_stats_reads_the_drained_stat_at_its_maximum(self):
        drained = self.recorded["drained_board"].player
        calibration = self.recorded["drained_calibration"]
        self.assertEqual(loadout_natural_stats(calibration, drained),
                         (84, *calibration.natural_stats[1:]))
        restored = self.recorded["restored_calibration"]
        self.assertEqual(loadout_natural_stats(restored, self.recorded["restored_board"].player),
                         restored.natural_stats)


if __name__ == "__main__":
    unittest.main()
