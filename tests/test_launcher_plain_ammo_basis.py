"""Every launcher is compared with the plain store round of its kind (owner 2026-11-22).

Owner (verbatim): 「射撃武器の比較には店で買える並の矢弾を使って。」 and 「近接の増え方も入れて全体で
比べる」.  The shot is launcher_damage.plain_ammo_turn_damage (combat/shoot.cpp exec_shoot,
test_hit_fire and critical_shot), read by the evaluator's ``ranged_dps``; the optimizer has no
launcher-only order before the whole loadout, so the rounds a launcher happens to own do not
decide.  CONSTRUCTED items after n1-b life-413's two launchers.
"""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest

from hengbot.equipment_optimizer import Loadout, LoadoutMetrics, OwnedEquipment, optimize_loadout
from hengbot.launcher_damage import (
    plain_ammo_turn_damage,
    shot_critical_factor,
    shot_hit_chance,
)
from hengbot.model import StoreItem
from hengbot.warrior_equipment_evaluator import WarriorCombatInputs
from hengbot.warrior_loadout_evaluator import warrior_ranged_offense_dps

TR_XTRA_MIGHT = 82


def launcher(name, sval, to_h, to_d, **fields):
    return StoreItem(letter="?", name=name, count=1, tval=19, sval=sval, price=0, aware=True,
                     known=True, fully_known=True, is_equipment=True, to_h=to_h, to_d=to_d,
                     weapon_proficiency=4000, weapon_proficiency_rank=1, weight=60, **fields)


def ammo(tval, dice, sides, to_h=0, to_d=0):
    return StoreItem(letter="?", name="ammo", count=40, tval=tval, sval=1, price=0, aware=True,
                     known=True, fully_known=True, to_h=to_h, to_d=to_d,
                     damage_dice_num=dice, damage_dice_sides=sides)


CROSSBOW = OwnedEquipment("equipped:xbow", launcher(
    "ライト・クロスボウ (x3) (+10,+10)", 23, 10, 10), "equipped", equipped_slot="bow")
ROBIN = OwnedEquipment("home:robin", launcher(
    "★森の狩人ロビンフッドのショート・ボウ (x3) (+15,+17)", 12, 15, 17, is_artifact=True,
    known_flags=frozenset({TR_XTRA_MIGHT})), "home")
COMBAT = WarriorCombatInputs(level=40, natural_str=18, natural_dex=18, melee_skill=100,
                             shooting_skill=72, class_id=16)
PLAIN_ARROWS = ammo(17, 1, 4)
PLAIN_BOLTS = ammo(18, 1, 5)
STEEL_BOLTS = ammo(18, 3, 5, to_h=2, to_d=5)   # 鋼鉄のクロスボウの矢 (3d5) (+2,+5)


def choose(ammunition):
    def evaluate(loadout):
        return LoadoutMetrics(expected_dps=10.0, survival_turns=100.0, combat_margin=10.0,
                              ranged_dps=warrior_ranged_offense_dps(loadout, COMBAT))
    candidates = tuple(Loadout((("bow", bow),), "empty") for bow in (CROSSBOW, ROBIN))
    result = optimize_loadout((CROSSBOW, ROBIN), evaluate, depth=1,
                              current_item_ids=frozenset({CROSSBOW.id}),
                              candidate_loadouts=candidates, obtainable_ammunition=ammunition)
    return result.best.loadout.item_at("bow").id


class PlainAmmoBasisTest(unittest.TestCase):
    def test_the_owned_rounds_do_not_decide(self):
        """With the owned steel bolts the crossbow read 60 a turn against the bow's 58.5 with
        plain arrows; on the same plain rounds the bow wins, whatever bolts are owned."""
        self.assertEqual(choose((PLAIN_ARROWS, STEEL_BOLTS)), ROBIN.id)
        self.assertEqual(choose((PLAIN_ARROWS, PLAIN_BOLTS)), ROBIN.id)

    def test_the_shot_formula(self):
        """The crossbow (+10,+10) at skill_thb 100 and to_h_b 20, the plain bolt 1d5 (weight 3):
        chance 100 + (10 + 20 + 10) * 3 = 220 against AC 100 (75); the critical power
        100 + (10 + 20) * 3 + 10 * 40 = 590, x1.5 / x2 / x3 on 300 / 150 / 50 of 500; one shot
        of (3 + 10) x 3 every 1.2 turns."""
        hit = 0.05 + 0.90 * (220 - 75) / 220
        critical = 0.059 * (1.5 * 300 + 2 * 150 + 3 * 50) / 500 + 0.941
        self.assertAlmostEqual(shot_hit_chance(220, 100), hit)
        self.assertAlmostEqual(shot_critical_factor(590, 3), critical)
        self.assertAlmostEqual(
            plain_ammo_turn_damage(CROSSBOW.item, skill_thb=100, to_h_b=20),
            hit * 39 * critical * 100 / 120)

    def test_extra_might_and_strength(self):
        """The bow's own extra might makes it x3; the STR term scales tmul (shoot.cpp:518)."""
        plain = plain_ammo_turn_damage(ROBIN.item, skill_thb=100)
        without = plain_ammo_turn_damage(
            launcher("ショート・ボウ", 12, 15, 17, is_artifact=True), skill_thb=100)
        self.assertAlmostEqual(plain / without, 3 / 2)
        self.assertAlmostEqual(
            plain_ammo_turn_damage(ROBIN.item, skill_thb=100, str_td=10) / plain, 1.1)


if __name__ == "__main__":
    unittest.main()
