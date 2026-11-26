"""The device skill of a loadout and the *Destruction* staff gate it opens.

Owner 2026-11-15 「装備で魔法道具使用能力を向上させて杖の成功率を上げることで先に進む
ことができる」 (n1-a life-525: tests/test_n1a_525_device_skill_1115_recorded.py).
"""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace
from types import SimpleNamespace

from hengbot import destruction_use, device_skill
from hengbot.attack_expectation import device_use_success
from hengbot.equipment_optimizer import (
    SLOT_ARMS, SLOT_HEAD, SLOT_LIGHT, SLOT_MAIN_HAND, SLOT_NECK, TR_FREE_ACT, TR_TELEPATHY,
    Loadout, current_loadout, divable_depth, optimize_loadout, required_abilities,
)
from hengbot.warrior_loadout_search import enumerate_single_slot_variants
from test_warrior_loadout_search import owned

MM = device_skill.TR_MAGIC_MASTERY


def equipped(item_id, tval, slot, **kw):
    return replace(owned(item_id, tval, **kw), origin="equipped", equipped_slot=slot)


class DeviceSkillFormulaTest(unittest.TestCase):
    def test_the_staff_needs_skill_sixty_for_eighty_percent(self):
        # use-execution.cpp: chance = skill - 50 (the staff's level); 80% at chance 10.
        self.assertEqual(destruction_use.STAFF_LEVEL, 50)
        self.assertEqual(destruction_use.reliable_skill(), 60)
        self.assertAlmostEqual(device_use_success(60, 50), 0.8)
        self.assertLess(device_use_success(59, 50), 0.8)
        # n1-a life-525: skill 31 is 1/69, and the Home's +3 gloves and +1 amulet make 63.
        self.assertAlmostEqual(device_use_success(31, 50) * 100, 100 / 69)
        self.assertAlmostEqual(device_use_success(63, 50), 11 / 13)

    def test_adj_int_dev_is_the_game_table(self):
        # player-status-table.cpp adj_int_dev: 3..18/220+, 38 entries.
        table = device_skill.ADJ_INT_DEV
        self.assertEqual(len(table), 38)
        self.assertEqual((table[5], table[15], table[25], table[37]), (1, 3, 8, 20))

    def test_the_gate_reads_eight_per_mastery_pval_and_the_int_adjustment(self):
        player = SimpleNamespace(device_skill=31)
        worn_helm = equipped("helm", 32, SLOT_HEAD)
        worn = Loadout(((SLOT_HEAD, worn_helm),), "empty")
        gate = device_skill.staff_gate(player, worn, 8, 0, 60)
        # INT 8 adds adj_int_dev[5] = 1: the gear-free part is 30.
        self.assertEqual((gate.base, gate.skill(worn)), (30, 31))
        gloves = owned("gloves", 31, flags=(MM,), pval=3)
        amulet = owned("amulet", 40, flags=(MM,), pval=1)
        both = Loadout(((SLOT_HEAD, worn_helm), (SLOT_ARMS, gloves), (SLOT_NECK, amulet)), "empty")
        self.assertEqual(gate.skill(both), 63)
        self.assertTrue(gate.opens(both))
        self.assertFalse(gate.opens(Loadout(((SLOT_ARMS, gloves),), "empty")))
        # An INT +10 crown: INT 8 -> 18 (index 15, +3 instead of +1).
        crown = owned("crown", 33, flags=(device_skill.TR_INT,), pval=10)
        self.assertEqual(gate.skill(Loadout(((SLOT_HEAD, crown),), "empty")), 33)
        # MAGIC_MASTERY without its flag known adds nothing.
        self.assertEqual(device_skill.item_mastery(owned("plain", 31, pval=3)), 0)

    def test_mastery_bound_takes_the_best_per_slot(self):
        rows = ((31, 24), (31, 8), (40, 8), (45, 8), (45, 16), (45, 8), (23, 16), (21, 16))
        # Arms 24, neck 8, the two best rings 24, the two hands 32.
        self.assertEqual(device_skill.mastery_bound(rows), 88)
        self.assertEqual(device_skill.mastery_bound(((99, 40), (31, -8))), 0)


class DestructionBandTest(unittest.TestCase):
    """A loadout reaches 50F+ with an owned staff only at the reliable skill."""

    def setUp(self):
        self.light = equipped("light", 39, SLOT_LIGHT)
        self.weapon = equipped("weapon", 23, SLOT_MAIN_HAND)
        self.helm = equipped("helm", 32, SLOT_HEAD)
        self.fa_gloves = equipped("fa-gloves", 31, SLOT_ARMS, flags=(TR_FREE_ACT,), ac=5)
        self.sage = equipped("sage", 40, SLOT_NECK, flags=(TR_FREE_ACT,))
        self.mm_gloves = owned("mm-gloves", 31, flags=(MM,), pval=3)
        self.mm_amulet = owned("mm-amulet", 40, flags=(MM,), pval=1)
        self.esp_helm = owned("esp-helm", 32, flags=(TR_TELEPATHY,))
        self.fa_ring = owned("fa-ring", 45, flags=(TR_FREE_ACT,))
        self.items = (self.light, self.weapon, self.helm, self.fa_gloves, self.sage,
                      self.mm_gloves, self.mm_amulet, self.esp_helm, self.fa_ring)
        self.current = frozenset({"light", "weapon", "helm", "fa-gloves", "sage"})
        worn = current_loadout(self.items)
        self.gate = device_skill.staff_gate(SimpleNamespace(device_skill=31), worn, 8, 0, 60)
        self.target = frozenset({"light", "weapon", "esp-helm", "mm-gloves", "mm-amulet",
                                 "fa-ring"})

    def search(self, gate):
        return list(enumerate_single_slot_variants(
            self.items, current_item_ids=self.current, require_light=True,
            required_flags=frozenset({TR_FREE_ACT}),
            repair_flags=frozenset({TR_FREE_ACT, TR_TELEPATHY}), staff_gate=gate))

    def test_the_completion_wears_the_mastery_gear_with_telepathy_and_keeps_free_action(self):
        found = {loadout.item_ids: loadout for loadout in self.search(self.gate)}
        # Gloves and amulet (+32: 63) displace both Free Action pieces; the helm adds
        # telepathy and the ring puts Free Action back.
        self.assertIn(self.target, found)
        self.assertEqual(self.gate.skill(found[self.target]), 63)
        # Every completion keeps Free Action (required) and the reliable skill.
        completions = set(found) - {loadout.item_ids for loadout in self.search(None)}
        self.assertTrue(completions)
        for ids in completions:
            self.assertIn(TR_FREE_ACT, found[ids].flags)
            self.assertTrue(self.gate.opens(found[ids]))
        # Without a gate the set is out of the search's reach.
        self.assertNotIn(self.target, {loadout.item_ids for loadout in self.search(None)})

    def test_the_fifty_band_needs_the_staffs_skill(self):
        # The character has every 80F resistance of its own; the gear brings the rest.
        intrinsic = required_abilities(80) - {"telepathy", "free_action"}
        loadouts = self.search(self.gate)
        result = optimize_loadout(
            self.items, lambda _loadout: _metrics(), depth=None, intrinsic_abilities=intrinsic,
            current_item_ids=self.current, candidate_loadouts=loadouts,
            require_light=True, require_body=False, staff_gate=self.gate)
        self.assertEqual(result.chosen_depth, 80)
        self.assertEqual(result.best.loadout.item_ids, self.target)
        without = optimize_loadout(
            self.items, lambda _loadout: _metrics(), depth=None, intrinsic_abilities=intrinsic,
            current_item_ids=self.current, candidate_loadouts=loadouts,
            require_light=True, require_body=False)
        self.assertLess(without.chosen_depth, 50)
        best = result.best.loadout
        # +10 worn (the 70-80F speed, 2026-11-26).
        self.assertEqual(divable_depth(best, intrinsic_abilities=intrinsic,
                                       staff_gate=self.gate, player_speed=120), 80)
        self.assertEqual(divable_depth(best, intrinsic_abilities=intrinsic), 49)
        self.assertEqual(divable_depth(best, intrinsic_abilities=intrinsic,
                                       has_destruction=True, player_speed=120), 80)
        # One mastery pval short (55): no 50F band.
        weak = Loadout(tuple((slot, item) for slot, item in best.slots if item.id != "mm-amulet"),
                       best.hand_mode)
        self.assertEqual(divable_depth(weak, intrinsic_abilities=intrinsic,
                                       staff_gate=self.gate), 49)


def _metrics():
    from hengbot.equipment_optimizer import LoadoutMetrics
    return LoadoutMetrics(
        expected_dps=10.0, survival_turns=100.0, combat_margin=1.0, secondary_value=0.0,
        speed_bonus=10, relevant_traits=frozenset(), evaluation_complete=True)


if __name__ == "__main__":
    unittest.main()
