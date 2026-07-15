import unittest
from itertools import product

from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_optimizer import (
    FIXED_SLOTS,
    SLOT_MAIN_RING,
    SLOT_SUB_RING,
    Loadout,
    OwnedEquipment,
    hand_configurations,
    optimize_loadout,
    slot_for,
)
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.monster_ranged_evaluator import SpellSelectionContext
from hengbot.warrior_defense_evaluator import WarriorDefenseInputs
from hengbot.warrior_equipment_evaluator import WarriorCombatInputs
from hengbot.warrior_loadout_evaluator import (
    CachedWarriorLoadoutEvaluator,
    WarriorLoadoutInputs,
)
from hengbot.warrior_loadout_search import enumerate_warrior_loadouts


def owned(item_id, tval, *, flags=(), ac=0, to_a=0, to_h=0, to_d=0):
    item = InventoryItem(
        slot=item_id,
        name=item_id,
        count=1,
        tval=tval,
        sval=1,
        aware=True,
        known=True,
        fully_known=True,
        is_equipment=True,
        known_flags=frozenset(flags),
        ac=ac,
        to_a=to_a,
        to_h=to_h,
        to_d=to_d,
        damage_dice_num=2 if tval in {20, 21, 22, 23} else 0,
        damage_dice_sides=5 if tval in {20, 21, 22, 23} else 0,
        weight=80,
        weapon_proficiency=4000,
    )
    return OwnedEquipment(item_id, item, "home")


def exhaustive_loadouts(items):
    legal = tuple(item for item in items if item.exploration_legal)
    rings = tuple(item for item in legal if item.item.tval == 45)
    fixed_pools = [
        (None, *(item for item in legal if slot_for(item.item) == slot))
        for slot in FIXED_SLOTS
    ]
    for hands in hand_configurations(legal):
        for main_ring in (None, *rings):
            for sub_ring in (None, *rings):
                if (
                    main_ring is not None
                    and sub_ring is not None
                    and main_ring.id == sub_ring.id
                ):
                    continue
                for fixed in product(*fixed_pools):
                    slots = []
                    if main_ring is not None:
                        slots.append((SLOT_MAIN_RING, main_ring))
                    if sub_ring is not None:
                        slots.append((SLOT_SUB_RING, sub_ring))
                    slots.extend(
                        (slot, item)
                        for slot, item in zip(FIXED_SLOTS, fixed)
                        if item is not None
                    )
                    if hands.main is not None:
                        slots.append(("main_hand", hands.main))
                    if hands.sub is not None:
                        slots.append(("sub_hand", hands.sub))
                    yield Loadout(tuple(slots), hands.mode)


class WarriorLoadoutSearchTest(unittest.TestCase):
    def setUp(self):
        race = MonraceKnowledge(
            max_hp=80,
            average_hp=80,
            speed=110,
            can_summon=False,
            friendly=False,
            level=10,
            spell_frequency=0,
            blows=(MonsterBlow("HIT", "HURT", 1, 6),),
        )
        self.encounters = (EncounterTarget(1, 1.0, race),)
        self.inputs = WarriorLoadoutInputs(
            WarriorCombatInputs(
                level=20,
                natural_str=38,
                natural_dex=38,
                melee_skill=80,
                two_weapon_skill=4000,
            ),
            WarriorDefenseInputs(level=20, natural_dex=38, saving_skill=50),
            200,
            SpellSelectionContext(),
        )

    def test_compressed_search_matches_exhaustive_best(self):
        items = (
            owned("sword", 23, to_h=4, to_d=5),
            owned("axe", 21, to_h=2, to_d=7),
            owned("shield", 34, ac=3, to_a=2),
            owned("ring-hit", 45, to_h=3),
            owned("ring-damage", 45, to_d=4),
            owned("light", 39),
            owned("weak-body", 36, flags={50}, ac=4, to_a=1),
            owned("strong-body", 36, flags={50}, ac=8, to_a=5),
            owned("gloves", 31, ac=1, to_a=2),
        )
        exhaustive_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        compressed_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        exhaustive = optimize_loadout(
            items,
            lambda loadout: exhaustive_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(items),
        )
        compressed = optimize_loadout(
            items,
            lambda loadout: compressed_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=enumerate_warrior_loadouts(items),
        )

        self.assertFalse(exhaustive.timed_out)
        self.assertFalse(compressed.timed_out)
        self.assertEqual(compressed.best.metrics, exhaustive.best.metrics)
        self.assertLess(
            compressed.combinations_considered,
            exhaustive.combinations_considered,
        )

    def test_dual_wield_search_includes_both_ring_assignments(self):
        items = (
            owned("sword", 23),
            owned("axe", 21),
            owned("ring-hit", 45, to_h=3),
            owned("ring-damage", 45, to_d=4),
            owned("light", 39),
        )
        assignments = {
            (
                loadout.item_at(SLOT_MAIN_RING).id,
                loadout.item_at(SLOT_SUB_RING).id,
            )
            for loadout in enumerate_warrior_loadouts(items)
            if loadout.hand_mode == "dual_wield"
            and loadout.item_at(SLOT_MAIN_RING) is not None
            and loadout.item_at(SLOT_SUB_RING) is not None
        }

        self.assertIn(("ring-hit", "ring-damage"), assignments)
        self.assertIn(("ring-damage", "ring-hit"), assignments)


if __name__ == "__main__":
    unittest.main()
