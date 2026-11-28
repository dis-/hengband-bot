"""rod_recharge against the game's recharge, simulated tick by tick (n1-c life-224, 2026-11-28).

The simulation is written from the game source, not from rod_recharge: hpmp/hp-mp-regenerator.cpp
:145-156 (an absorbed rod's charge drops every tick), cmd-item/cmd-magiceat.cpp:571-572 (a cast
adds pval * EATER_ROD_CHARGE), player-info/magic-eater-data-type.cpp:66-71 (usable while the charge
is at most pval * (count - 1) * EATER_ROD_CHARGE), cmd-magiceat.cpp:284-288 (the list's charging),
inventory/recharge-processor.cpp:84-103 (a carried rod stack's timeout).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot import rod_recharge

PVAL = 99
EATER_ROD_CHARGE = 16
# player/player-status-table.cpp:62-68, written out by stat (3..18/220+).
ADJ_MAG_MANA_BY_STAT = {3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 1, 9: 2, 10: 3, 11: 4, 12: 5, 13: 5,
                        14: 6, 15: 7, 16: 8, 17: 9, "18/00": 10, "18/10": 11, "18/50": 13,
                        "18/100": 18, "18/220": 30}
STAT_INDEX = {3: 0, 7: 4, 8: 5, 12: 9, 17: 14, "18/00": 15, "18/10": 16, "18/50": 20,
              "18/100": 25, "18/220": 37}


def _shed(regen, int_index, count):
    mult = 30 + rod_recharge.ADJ_MAG_MANA[int_index]
    return (regen * mult * (count + 10) * EATER_ROD_CHARGE) // (30 * 16 * 197)


def _charging(charge):
    return (charge - 1) // (EATER_ROD_CHARGE * PVAL) + 1 if charge > 0 else 0


def _usable(charge, count):
    return charge <= PVAL * (count - 1) * EATER_ROD_CHARGE


def _simulated_ticks(charge, count, int_index, regen):
    ticks = 0
    while not _usable(charge, count):
        charge = max(0, charge - _shed(regen, int_index, count))
        ticks += 1
    return ticks


class TableTest(unittest.TestCase):
    def test_adj_mag_mana_matches_the_source_table(self):
        self.assertEqual(len(rod_recharge.ADJ_MAG_MANA), 38)
        for stat, index in STAT_INDEX.items():
            self.assertEqual(rod_recharge.ADJ_MAG_MANA[index], ADJ_MAG_MANA_BY_STAT[stat], stat)


class AbsorbedRodTest(unittest.TestCase):
    def test_the_bound_holds_for_every_charge_a_list_row_can_show(self):
        for count in (1, 2, 4, 11):
            for int_index in (0, 9, 16, 25, 37):
                for regen in (98, 197, 394):
                    shed = rod_recharge.absorbed_shed_per_tick(count, int_index, regen)
                    self.assertEqual(shed, _shed(regen, int_index, count))
                    # Every charge a cast can leave (at most count casts' worth), read as its row.
                    for charge in range(0, count * PVAL * EATER_ROD_CHARGE + 1, 37):
                        bound = rod_recharge.absorbed_ready_ticks(count, _charging(charge),
                                                                  int_index, regen)
                        real = _simulated_ticks(charge, count, int_index, regen)
                        self.assertGreaterEqual(bound, real, (count, int_index, regen, charge))
                        # The bound is the real time of the row's worst charge (a row with a use
                        # is ready now).
                        shown = _charging(charge)
                        worst = shown * PVAL * EATER_ROD_CHARGE
                        expected = (_simulated_ticks(worst, count, int_index, regen)
                                    if shown >= count else 0)
                        self.assertEqual(bound, expected, (count, int_index, regen, charge))

    def test_n1c_224_detection_rod(self):
        # 4 absorbed rods, INT 18/12 (stat_index 16): 19 a tick unrested, 38 resting.
        self.assertEqual(rod_recharge.absorbed_shed_per_tick(4, 16, 197), 19)
        self.assertEqual(rod_recharge.absorbed_shed_per_tick(4, 16, 394), 38)
        self.assertEqual(rod_recharge.absorbed_ready_ticks(4, 4, 16, 197), 84)
        self.assertEqual(rod_recharge.absorbed_ready_ticks(4, 4, 16, 394), 42)
        self.assertEqual(rod_recharge.absorbed_ready_ticks(4, 3, 16, 197), 0)

    def test_fainting_is_not_bounded(self):
        self.assertIsNone(rod_recharge.regen_amount("fainting", resting=True))
        self.assertEqual(rod_recharge.regen_amount("weak", resting=True), 196)
        self.assertEqual(rod_recharge.regen_amount("normal", resting=False), 197)


class CarriedRodTest(unittest.TestCase):
    def test_one_rod_of_a_stack_is_ready_within_pval_ticks(self):
        for number in (1, 2, 5):
            for charging in range(1, number + 1):
                timeout, ticks = charging * PVAL, 0
                while (timeout + PVAL - 1) // PVAL >= number and timeout > 0:
                    timeout -= min((timeout + PVAL - 1) // PVAL, number)
                    ticks += 1
                self.assertLessEqual(ticks, rod_recharge.carried_ready_ticks(), (number, charging))


if __name__ == "__main__":
    unittest.main()
