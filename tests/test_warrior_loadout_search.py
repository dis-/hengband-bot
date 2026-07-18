import unittest
from dataclasses import replace
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
from hengbot.warrior_loadout_search import (
    _deduplicate_melee_weapons,
    _prune_dominated_catalog,
    enumerate_warrior_loadouts,
)


def owned(
    item_id, tval, *, flags=(), ac=0, to_a=0, to_h=0, to_d=0,
    sval=1, pval=0, dice=None, weight=80,
):
    item = InventoryItem(
        slot=item_id,
        name=item_id,
        count=1,
        tval=tval,
        sval=sval,
        aware=True,
        known=True,
        fully_known=True,
        is_equipment=True,
        known_flags=frozenset(flags),
        ac=ac,
        to_a=to_a,
        to_h=to_h,
        to_d=to_d,
        pval=pval,
        damage_dice_num=(dice or (2, 5))[0] if tval in {20, 21, 22, 23} else 0,
        damage_dice_sides=(dice or (2, 5))[1] if tval in {20, 21, 22, 23} else 0,
        weight=weight,
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

    def test_exact_copy_pruning_preserves_exhaustive_dual_wield_optimum(self):
        items = (
            owned("strong-sword", 23, to_h=5, to_d=7),
            owned("plain-whip-a", 21),
            owned("plain-whip-b", 21),
            owned("plain-whip-c", 21),
            owned("ring-a", 45, to_d=2),
            owned("ring-b", 45, to_d=2),
            owned("ring-c", 45, to_d=2),
            owned("light-a", 39),
            owned("light-b", 39),
        )
        exhaustive_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        pruned_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        exhaustive = optimize_loadout(
            items,
            lambda loadout: exhaustive_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(items),
        )
        pruned = optimize_loadout(
            items,
            lambda loadout: pruned_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=enumerate_warrior_loadouts(items),
        )

        self.assertFalse(pruned.timed_out)
        self.assertEqual(pruned.best.metrics, exhaustive.best.metrics)
        self.assertLess(
            pruned.combinations_considered,
            exhaustive.combinations_considered,
        )

    def test_slot_dominance_reduces_catalog_and_preserves_exact_frontier(self):
        weak = (
            owned("weak-sword", 23, to_h=1, to_d=1),
            owned("weak-cloak", 35, ac=1, to_a=1),
            owned("weak-ring", 45, to_d=1),
        )
        strong = (
            owned("strong-sword", 23, to_h=4, to_d=5),
            owned("strong-cloak", 35, ac=3, to_a=4),
            owned("strong-ring", 45, to_d=4),
        )
        support = (owned("light", 39), owned("shield", 34, ac=3, to_a=2))
        catalog = (*weak, *strong, *support)
        pruned_catalog = _prune_dominated_catalog(catalog)

        reference_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        pruned_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        reference = optimize_loadout(
            catalog,
            lambda loadout: reference_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(catalog),
        )
        reduced = optimize_loadout(
            catalog,
            lambda loadout: pruned_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(pruned_catalog),
        )

        self.assertEqual(len(pruned_catalog), len(catalog) - 1)
        self.assertNotIn(weak[1], pruned_catalog)
        self.assertIn(weak[0], pruned_catalog)
        self.assertIn(weak[2], pruned_catalog)
        self.assertEqual(reduced.best.metrics, reference.best.metrics)
        self.assertEqual(
            {entry.metrics for entry in reduced.pareto_frontier},
            {entry.metrics for entry in reference.pareto_frontier},
        )
        # Capacity-one cloak dominance still removes exactly one candidate.
        self.assertEqual(len(catalog), len(pruned_catalog) + 1)

    def test_stacking_dex_and_speed_rings_survive_single_dominator(self):
        stacking_inputs = WarriorLoadoutInputs(
            WarriorCombatInputs(
                level=20,
                natural_str=18,
                natural_dex=18,
                melee_skill=80,
                two_weapon_skill=4000,
            ),
            WarriorDefenseInputs(level=20, natural_dex=18, saving_skill=50),
            200,
            SpellSelectionContext(),
        )
        for flag, label in ((3, "dex"), (12, "speed")):
            with self.subTest(label=label):
                evaluator_inputs = stacking_inputs
                encounters = self.encounters
                if label == "speed":
                    evaluator_inputs = replace(
                        stacking_inputs,
                        defense=replace(stacking_inputs.defense, base_speed=126),
                    )
                    encounters = (
                        replace(
                            self.encounters[0],
                            knowledge=replace(
                                self.encounters[0].knowledge,
                                blows=(MonsterBlow("HIT", "INERTIA", 1, 6),),
                            ),
                        ),
                    )
                strong = owned(f"strong-{label}", 45, flags={flag}, pval=3)
                weak = owned(f"weak-{label}", 45, flags={flag}, pval=2)
                catalog = (
                    owned("sword", 23, to_d=8),
                    owned("light", 39),
                    strong,
                    weak,
                )

                pruned = _prune_dominated_catalog(catalog)
                self.assertIn(strong, pruned)
                self.assertIn(weak, pruned)

                reference_evaluator = CachedWarriorLoadoutEvaluator(
                    evaluator_inputs, encounters
                )
                reduced_evaluator = CachedWarriorLoadoutEvaluator(
                    evaluator_inputs, encounters
                )
                reference = optimize_loadout(
                    catalog,
                    lambda loadout: reference_evaluator(loadout).metrics,
                    depth=1,
                    timeout_seconds=10,
                    candidate_loadouts=exhaustive_loadouts(catalog),
                )
                reduced = optimize_loadout(
                    catalog,
                    lambda loadout: reduced_evaluator(loadout).metrics,
                    depth=1,
                    timeout_seconds=10,
                    candidate_loadouts=enumerate_warrior_loadouts(catalog),
                )

                self.assertEqual(reduced.best.metrics, reference.best.metrics)
                self.assertEqual(
                    {strong.id, weak.id},
                    {item_id for item_id in reference.best.loadout.item_ids
                     if item_id.endswith(label)},
                )

    def test_dominated_dual_wield_pair_survives_single_dominator(self):
        strong = owned("strong-sword", 23, to_h=12, to_d=20, weight=30)
        weak = owned("weak-sword", 23, to_h=10, to_d=18, weight=30)
        catalog = (
            strong,
            weak,
            owned("light", 39),
        )
        dual_wield_inputs = WarriorLoadoutInputs(
            WarriorCombatInputs(
                level=20,
                natural_str=38,
                natural_dex=38,
                melee_skill=80,
                two_weapon_skill=16000,
            ),
            WarriorDefenseInputs(level=20, natural_dex=38, saving_skill=50),
            200,
            SpellSelectionContext(),
        )

        pruned = _prune_dominated_catalog(catalog)
        self.assertIn(strong, pruned)
        self.assertIn(weak, pruned)

        reference_evaluator = CachedWarriorLoadoutEvaluator(
            dual_wield_inputs, self.encounters
        )
        reduced_evaluator = CachedWarriorLoadoutEvaluator(
            dual_wield_inputs, self.encounters
        )
        reference = optimize_loadout(
            catalog,
            lambda loadout: reference_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(catalog),
        )
        reduced = optimize_loadout(
            catalog,
            lambda loadout: reduced_evaluator(loadout).metrics,
            depth=1,
            timeout_seconds=10,
            candidate_loadouts=enumerate_warrior_loadouts(catalog),
        )

        self.assertEqual(reference.best.loadout.hand_mode, "dual_wield")
        self.assertEqual(
            {item_id for item_id in reference.best.loadout.item_ids
             if item_id.endswith("sword")},
            {strong.id, weak.id},
        )
        self.assertEqual(reduced.best.metrics, reference.best.metrics)

    def test_two_distinct_ring_dominators_prune_weakest_ring(self):
        strongest = owned("ring-plus-four", 45, to_d=4)
        strong = owned("ring-plus-three", 45, to_d=3)
        weak = owned("ring-plus-two", 45, to_d=2)

        pruned = _prune_dominated_catalog((strongest, strong, weak))

        self.assertEqual(pruned, (strongest, strong))

    def test_launcher_and_light_stage_inputs_are_pareto_frontiers(self):
        bows = tuple(
            owned(
                f"bow-{i}", 19, ac=i % 3, to_a=i % 2,
                flags=({50 + i} if i < 4 else ()),
            )
            for i in range(11)
        )
        lights = tuple(
            owned(
                f"light-{i}", 39, ac=i % 4,
                flags=({50 + i} if i < 5 else ()),
            )
            for i in range(13)
        )
        catalog = (*bows, *lights, owned("sword", 23, to_d=4))
        reduced = _prune_dominated_catalog(catalog)
        reduced_bows = [item for item in reduced if item.item.tval == 19]
        reduced_lights = [item for item in reduced if item.item.tval == 39]

        self.assertLess(len(reduced_bows), len(bows))
        self.assertLess(len(reduced_lights), len(lights))
        reference_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        reduced_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        reference = optimize_loadout(
            catalog, lambda loadout: reference_evaluator(loadout).metrics,
            depth=1, timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(catalog),
        )
        result = optimize_loadout(
            catalog, lambda loadout: reduced_evaluator(loadout).metrics,
            depth=1, timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(reduced),
        )
        self.assertEqual(result.best.metrics, reference.best.metrics)

    def test_melee_equivalent_weapons_do_not_breed_quadratic_pairs(self):
        swords = tuple(
            owned(f"sword-{i}", 23, sval=i, to_h=3, to_d=4)
            for i in range(3)
        )
        deduped = _deduplicate_melee_weapons(swords)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(
            sum(
                1 for hands in hand_configurations(deduped)
                if hands.mode == "dual_wield"
            ),
            2,
        )
        reference_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        reduced_evaluator = CachedWarriorLoadoutEvaluator(
            self.inputs, self.encounters
        )
        catalog = (*swords, owned("light", 39))
        reduced_catalog = (*deduped, owned("light", 39))
        reference = optimize_loadout(
            catalog, lambda loadout: reference_evaluator(loadout).metrics,
            depth=1, timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(catalog),
        )
        result = optimize_loadout(
            catalog, lambda loadout: reduced_evaluator(loadout).metrics,
            depth=1, timeout_seconds=10,
            candidate_loadouts=exhaustive_loadouts(reduced_catalog),
        )
        self.assertEqual(result.best.metrics, reference.best.metrics)

    def test_live_shaped_duplicate_supplies_never_enter_search(self):
        launchers = tuple(owned(f"bow-{index}", 19) for index in range(10))
        torches = tuple(owned(f"torch-{index}", 39) for index in range(13))
        melee = tuple(owned(f"whip-{index}", 21) for index in range(25))
        armour = (
            owned("body", 36, ac=8, to_a=5),
            owned("outer", 35, ac=3, to_a=2),
            owned("head", 33, ac=2, to_a=2),
            owned("arms", 31, ac=1, to_a=1),
            owned("feet", 30, ac=2, to_a=1),
        )
        items = (*launchers, *torches, *melee, *armour)
        excluded = frozenset(item.id for item in torches)
        loadouts = enumerate_warrior_loadouts(
            items, excluded_item_ids=excluded
        )
        considered = 0
        seen_ids = set()
        for loadout in loadouts:
            considered += 1
            seen_ids.update(loadout.item_ids)

        self.assertTrue(excluded.isdisjoint(seen_ids))
        self.assertTrue(
            {item.id for item in launchers[1:]}.isdisjoint(seen_ids)
        )
        self.assertTrue(
            {item.id for item in melee[2:]}.isdisjoint(seen_ids)
        )
        self.assertLess(considered, 1_000)
        self.assertFalse(loadouts.truncated)

    def test_live_shaped_hoard_has_exact_structural_bound(self):
        launchers = tuple(
            owned(f"bow-{i}", 19, ac=i % 3, flags=({50 + i} if i < 3 else ()))
            for i in range(11)
        )
        lights = tuple(
            owned(f"light-{i}", 39, ac=i % 4, flags=({55 + i} if i < 4 else ()))
            for i in range(13)
        )
        melee = tuple(
            owned(f"sword-{i}", 23, sval=i, to_h=i % 2, to_d=i % 3)
            for i in range(13)
        )
        rings = tuple(owned(f"ring-{i}", 45, to_d=i) for i in range(5))
        bodies = tuple(owned(f"body-{i}", 36, ac=i + 1, to_a=i) for i in range(6))
        catalog = (
            *launchers, *lights, *melee, *rings, *bodies,
            *(owned(f"cloak-{i}", 35, ac=i + 1) for i in range(3)),
            *(owned(f"feet-{i}", 30, ac=i + 1) for i in range(2)),
            owned("head", 33, ac=2), owned("arms", 31, ac=2),
            owned("shield", 34, ac=3),
            *(owned(f"amulet-{i}", 40, to_a=i) for i in range(3)),
        )
        self.assertEqual(len(catalog), 59)
        search = enumerate_warrior_loadouts(catalog)
        considered = sum(1 for _ in search)
        self.assertLess(considered, 10_000)
        self.assertFalse(search.truncated)


if __name__ == "__main__":
    unittest.main()
