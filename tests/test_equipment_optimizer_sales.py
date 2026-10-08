"""Part A pins: recorded Home and constructed safety/capacity counterexamples."""
import tests  # noqa: F401 -- isolate runtime files

from dataclasses import replace
import importlib.util
from pathlib import Path
import unittest

from hengbot.equipment_optimizer import OwnedEquipment, current_loadout, optimize_loadout
from hengbot.equipment_sale_classifier import (
    _sale_slot, classify_equipment_sales, equipment_sale_plan,
    equipment_sale_scope,
)
from hengbot.launcher_damage import best_obtainable_launcher_damage, launcher_dominates
from hengbot.model import InventoryItem, PLAYER_CLASS_WARRIOR

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("measure_equipment_sales", ROOT / "scripts/measure_equipment_sales.py")
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


def copy_gear(item_id, *, tval=45, sval=1, flags=(), **changes):
    """Declared constructed physical copies; all identity/ID fields explicit."""
    item = InventoryItem(slot=item_id, name=item_id, count=1, tval=tval, sval=sval,
                         aware=True, known=True, fully_known=True, is_equipment=True,
                         known_flags=frozenset(flags))
    return OwnedEquipment(item_id, replace(item, **changes), "home")


class TestRecordedEquipmentSaleClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.catalog, cls.snapshot, cls.evaluator, cls.options = measurement.recorded_inputs()
        cls.results = {
            scope + duplicates: classify_equipment_sales(
                cls.catalog.items, lambda loadout: cls.evaluator(loadout).metrics,
                scope=scope, duplicates=duplicates, **cls.options,
            )
            for scope, duplicates in (("E", "S"), ("E", "D"), ("J", "S"), ("J", "D"))
        }

    def classify(self, catalog, **options):
        return classify_equipment_sales(
            catalog, lambda loadout: self.evaluator(loadout).metrics,
            **{**self.options, **options},
        )

    def test_recorded_catalogue_numbers(self):
        home = {owned.id for owned in self.catalog.items if owned.origin == "home"}
        self.assertEqual(len(home), 231)
        self.assertEqual(len(self.data["home"]["knowledge"]["items"]), 240)
        self.assertEqual(self.data["home"]["turn"], 15798381)
        self.assertTrue(self.options["catalogue_current"])
        # This branch's J scope excludes ego jewelry: the recorded JD count is 44.
        for key, expected in {"ES": 41, "ED": 41, "JS": 42, "JD": 44}.items():
            with self.subTest(variant=key):
                result = self.results[key]
                self.assertEqual(result.blockers, ())
                self.assertEqual(len(home & result.sold_ids), expected)
                self.assertEqual(len(home & result.pareto_ids), 1)
                self.assertFalse(home & result.needs_identification_ids)

    def test_recorded_jd_rank_sale_counts(self):
        result = self.results["JD"]
        home = {owned.id: owned for owned in self.catalog.items
                if owned.origin == "home"}
        selected = set(equipment_sale_plan(
            result, home_ids=frozenset(home), free_home_slots=9,
        )) & home.keys()
        counts = {}
        for item_id, owned in home.items():
            slot = _sale_slot(owned)
            row = counts.setdefault(slot, [0, 0, 0, 0])
            rank = result.ranks.get(item_id, 0)
            if item_id in selected and rank > 20:
                row[1] += 1  # unconditional rank-21+ rule
            elif item_id in selected and item_id in result.sold_ids:
                row[0] += 1  # J-D in ranks 11-20
            elif item_id in selected:
                row[2] += 1  # Home-capacity fallback
            else:
                row[3] += 1  # kept
        self.assertEqual(
            counts,
            {"arms": [0, 0, 0, 2], "body": [2, 18, 0, 21],
             "bow": [0, 0, 0, 4], "feet": [0, 0, 0, 5],
             "head": [0, 0, 0, 11], "light": [0, 0, 0, 4],
             "main_hand": [0, 78, 0, 38],
             "main_ring": [0, 8, 0, 19], "neck": [0, 0, 0, 6],
             "outer": [0, 0, 0, 8], "sub_hand": [0, 0, 0, 7]},
        )

    def test_recorded_artifacts_and_worn_never_selected(self):
        artifacts = {owned.id for owned in self.catalog.items if owned.origin == "home" and owned.item.is_artifact}
        self.assertEqual(len(artifacts), 28)
        worn = current_loadout(self.catalog.items).item_ids
        for result in self.results.values():
            self.assertFalse(result.sold_ids & artifacts)
            self.assertFalse(result.sold_ids & worn)
            for item_id, witnesses in result.dominators.items():
                self.assertNotIn(item_id, witnesses)
                self.assertFalse(set(witnesses) & result.sold_ids)

    def test_unidentified_never_selected_and_counted_separately(self):
        # Start from a genuinely selected recorded candidate, then remove ID
        # evidence. The failure case is meaningful, not an already-kept item.
        target = next(owned for owned in self.catalog.items if owned.id in self.results["ES"].sold_ids)
        for changes in ({"known": False}, {"fully_known": False}):
            catalog = tuple(replace(owned, item=replace(owned.item, **changes)) if owned.id == target.id else owned
                            for owned in self.catalog.items)
            result = self.classify(catalog)
            self.assertNotIn(target.id, result.sold_ids)
            self.assertIn(target.id, result.needs_identification_ids)

    def test_reservation_never_selected(self):
        target = next(owned for owned in self.catalog.items if owned.id in self.results["ES"].sold_ids)
        result = self.classify(self.catalog.items, reserved_ids=self.options["reserved_ids"] | {target.id})
        self.assertNotIn(target.id, result.sold_ids)
        self.assertEqual(result.reasons[target.id], "reservation-or-light")

    def test_artifact_guard_on_otherwise_sale_candidate(self):
        target = next(owned for owned in self.catalog.items if owned.id in self.results["ES"].sold_ids)
        catalog = tuple(replace(owned, item=replace(owned.item, is_artifact=True)) if owned.id == target.id else owned
                        for owned in self.catalog.items)
        result = self.classify(catalog)
        self.assertNotIn(target.id, result.sold_ids)
        self.assertEqual(result.reasons[target.id], "artifact")

    def test_class_and_scan_freshness_gates(self):
        for options, blocker in (({"class_id": 1}, "unsupported-class"),
                                 ({"home_scan_complete": False}, "home-scan-incomplete"),
                                 ({"catalogue_current": False}, "stale-catalogue")):
            with self.subTest(blocker=blocker):
                result = self.classify(self.catalog.items, **options)
                self.assertFalse(result.sold_ids)
                self.assertIn(blocker, result.blockers)

    def test_strict_identical_copies_never_mutually_dominate(self):
        worn = tuple(owned for owned in self.catalog.items if owned.origin == "equipped")
        copies = tuple(copy_gear(f"identical-ring-{i}", flags=(53,)) for i in range(4))
        result = self.classify((*worn, *copies), scope="J", duplicates="S")
        self.assertFalse(result.blockers)
        self.assertFalse(result.sold_ids)
        duplicate = self.classify((*worn, *copies), scope="J", duplicates="D")
        self.assertEqual(len(duplicate.sold_ids), 2)
        self.assertFalse(duplicate.pareto_ids)
        for witnesses in duplicate.dominators.values():
            self.assertEqual(len(witnesses), 2)

    def test_fixed_slot_duplicates_keep_one_and_reserved_copy(self):
        worn = tuple(owned for owned in self.catalog.items if owned.origin == "equipped")
        copies = tuple(copy_gear(f"identical-cloak-{i}", tval=35, flags=(53,), is_ego=True) for i in range(3))
        result = self.classify((*worn, *copies), duplicates="D", reserved_ids=frozenset({copies[-1].id}))
        self.assertEqual(result.sold_ids, frozenset({copies[0].id, copies[1].id}))
        self.assertNotIn(copies[-1].id, result.sold_ids)

    def test_unique_quest_ability_and_resistance_swap_kept(self):
        worn = tuple(owned for owned in self.catalog.items if owned.origin == "equipped")
        for flag in (46, 48, 57, 62, 79):
            unique = copy_gear("quest-or-resistance", tval=31, is_ego=True, flags=(flag,), to_a=-10)
            better_ac = copy_gear("higher-ac", tval=31, is_ego=True, to_a=50)
            result = self.classify((*worn, unique, better_ac))
            self.assertNotIn(unique.id, result.sold_ids)

    def test_melee_needs_two_retained_dominators(self):
        worn = tuple(owned for owned in self.catalog.items if owned.origin == "equipped" and not owned.item.is_melee_weapon)
        spare = copy_gear("melee-spare", tval=23, is_ego=True, damage_dice_num=1, damage_dice_sides=4, weight=10)
        better = copy_gear("melee-better", tval=23, is_ego=True, damage_dice_num=1, damage_dice_sides=4, to_d=50, weight=10)
        one = self.classify((*worn, spare, better))
        self.assertNotIn(spare.id, one.sold_ids)
        two = self.classify((*worn, spare, better, replace(better, id="melee-better-copy")))
        self.assertIn(spare.id, two.sold_ids)
        self.assertEqual(len(two.dominators[spare.id]), 2)

    def test_scope_j_explicit_base_flag_items(self):
        ordinary_ring = copy_gear("plain-ring")
        magic_ring = copy_gear("magic-ring", flags=(62,))
        dragon_boots = copy_gear("dragon-boots", tval=30, sval=4, flags=(62,))
        for owned in (magic_ring, dragon_boots):
            self.assertFalse(equipment_sale_scope(owned, "E"))
            self.assertTrue(equipment_sale_scope(owned, "J"))
        self.assertFalse(equipment_sale_scope(ordinary_ring, "J"))

    def test_depth_none_exposes_lower_band_winner_after_selection(self):
        chaos = copy_gear("chaos-body", tval=37, flags=(62,), is_ego=True, ac=5)
        fire_action = copy_gear("shallow-body", tval=37, flags=(46, 50, 57), is_ego=True, ac=50)
        result = optimize_loadout(
            (chaos, fire_action), lambda loadout: self.evaluator(loadout).metrics,
            depth=None, require_light=False, timeout_seconds=120,
        )
        self.assertFalse(result.timed_out)
        self.assertEqual(result.chosen_depth, 25)
        self.assertIn(fire_action.id, result.best.loadout.item_ids)
        winner_ids = set().union(*(entry.loadout.item_ids for entry in result.band_best_loadouts))
        self.assertNotIn(chaos.id, winner_ids)
        self.assertIn(fire_action.id, winner_ids)

    def test_owned_launcher_proof_ammo_flags_grade_and_crossbow_rule(self):
        short = copy_gear("short-bow", tval=19, sval=12, is_ego=True, to_d=1)
        long = copy_gear("long-bow", tval=19, sval=13, is_ego=True, to_d=5)
        crossbow = copy_gear("crossbow", tval=19, sval=23, is_ego=True, to_d=50)
        ammo = (copy_gear("arrow", tval=17, damage_dice_num=1, damage_dice_sides=4).item,)
        damage = lambda owned: best_obtainable_launcher_damage(owned.item, ammo)
        self.assertTrue(launcher_dominates(long.item, short.item, damage(long), damage(short)))
        self.assertFalse(launcher_dominates(crossbow.item, short.item, 200, damage(short)))
        self.assertFalse(launcher_dominates(long.item, replace(short.item, known_flags=frozenset({62})), damage(long), damage(short)))
        self.assertFalse(launcher_dominates(replace(long.item, is_ego=False), short.item, damage(long), damage(short)))
        # Same-ammo constraint is stronger; the shared legacy route still pins
        # the Light Crossbow preference even when arbitrary damage is larger.
        ordinary = replace(short.item, is_ego=False, to_d=100)
        self.assertFalse(launcher_dominates(ordinary, crossbow.item, 500, 10, same_ammo=False))


if __name__ == "__main__":
    unittest.main()
