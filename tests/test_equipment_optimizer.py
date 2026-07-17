import unittest

from hengbot.equipment_optimizer import (
    LoadoutMetrics,
    Loadout,
    OwnedEquipment,
    OwnedEquipmentCatalog,
    SLOT_MAIN_HAND,
    SLOT_MAIN_RING,
    SLOT_SUB_RING,
    SLOT_BODY,
    SLOT_SUB_HAND,
    TR_NO_TELE,
    TR_TELEPORT,
    enumerate_loadouts,
    optimize_loadout,
    random_teleport_is_suppressed,
)
from hengbot.equipment_transaction_planner import plan_equipment_transactions
from hengbot.warrior_loadout_search import enumerate_warrior_loadouts
from hengbot.model import (
    SV_DRAGON_HELM,
    SV_LITE_LANTERN,
    TVAL_ARROW,
    TVAL_HELM,
    TVAL_LITE,
    InventoryItem,
)
from hengbot.model import StoreItem


def gear(
    item_id,
    tval,
    *,
    flags=(),
    known=True,
    fully_known=True,
    ego=False,
    artifact=False,
    cursed=False,
    broken=False,
    pseudo_feeling="",
    equipped_slot=None,
    teleport_suppressed=False,
    sval=1,
):
    item = InventoryItem(
        slot=item_id,
        name=item_id,
        count=1,
        tval=tval,
        sval=sval,
        aware=known,
        known=known,
        fully_known=fully_known,
        is_equipment=True,
        is_ego=ego,
        is_artifact=artifact,
        is_cursed=cursed,
        is_broken=broken,
        pseudo_feeling=pseudo_feeling,
        known_flags=frozenset(flags),
    )
    return OwnedEquipment(
        item_id,
        item,
        "equipped" if equipped_slot else "home",
        equipped_slot=equipped_slot,
        random_teleport_suppressed=teleport_suppressed,
    )


def metrics(margin, *, dps=None, survival=None, speed=0, secondary=0, traits=()):
    return LoadoutMetrics(
        expected_dps=margin if dps is None else dps,
        survival_turns=margin if survival is None else survival,
        combat_margin=margin,
        speed_bonus=speed,
        secondary_value=secondary,
        relevant_traits=frozenset(traits),
    )


class EquipmentOptimizerTest(unittest.TestCase):
    def setUp(self):
        self.light = gear("light", 39)

    def test_enumerates_shield_two_hand_and_dual_wield_configs(self):
        sword = gear("sword", 23)
        axe = gear("axe", 22)
        shield = gear("shield", 34)
        modes = {
            loadout.hand_mode
            for loadout in enumerate_loadouts([self.light, sword, axe, shield])
        }
        self.assertEqual(
            modes,
            {"empty", "one_handed", "two_handed", "weapon_shield", "dual_wield"},
        )

    def test_digging_tool_is_never_a_combat_loadout_weapon(self):
        shovel = gear("shovel", 20)
        sword = gear("sword", 23)
        result = optimize_loadout(
            [self.light, shovel, sword],
            lambda loadout: metrics(
                1000 if "shovel" in loadout.item_ids else len(loadout.item_ids)
            ),
            depth=1,
        )

        self.assertIsNotNone(result.best)
        self.assertNotIn("shovel", result.best.loadout.item_ids)
        self.assertIn("sword", result.best.loadout.item_ids)

    def test_never_uses_one_physical_ring_twice(self):
        ring = gear("ring", 45)
        loadouts = list(enumerate_loadouts([self.light, ring]))
        self.assertTrue(any(loadout.item_ids == {"light", "ring"} for loadout in loadouts))
        self.assertTrue(all(len(loadout.slots) == len(loadout.item_ids) for loadout in loadouts))

    def test_global_synergy_beats_individually_stronger_weapon(self):
        raw_weapon = gear("raw", 23)
        utility_weapon = gear("utility", 23)
        raw_armour = gear("raw-armour", 36)
        synergy_armour = gear("synergy-armour", 36)

        def evaluate(loadout):
            ids = loadout.item_ids
            score = 10.0
            if "raw" in ids:
                score += 5.0
            if "utility" in ids:
                score += 4.0
            if "raw-armour" in ids:
                score += 4.0
            if "synergy-armour" in ids:
                score += 3.0
            if {"utility", "synergy-armour"}.issubset(ids):
                score += 5.0
            return metrics(score)

        result = optimize_loadout(
            [self.light, raw_weapon, utility_weapon, raw_armour, synergy_armour],
            evaluate,
            depth=1,
        )
        self.assertIsNotNone(result.best)
        self.assertIn("utility", result.best.loadout.item_ids)
        self.assertIn("synergy-armour", result.best.loadout.item_ids)

    def test_depth_requirements_apply_to_complete_loadout_union(self):
        fire = gear("fire-ring", 45, flags={50})
        confusion = gear("confusion-amulet", 40, flags={57})
        result = optimize_loadout(
            [self.light, fire, confusion],
            lambda loadout: metrics(float(len(loadout.item_ids))),
            depth=20,
        )
        self.assertEqual(result.best.loadout.item_ids, {"light", "fire-ring", "confusion-amulet"})

    def test_no_teleport_is_never_an_exploration_candidate(self):
        blocked = gear("blocked", 23, flags={TR_NO_TELE})
        safe = gear("safe", 23)
        result = optimize_loadout(
            [self.light, blocked, safe],
            lambda loadout: metrics(100 if "blocked" in loadout.item_ids else 1),
            depth=1,
        )
        self.assertNotIn("blocked", result.best.loadout.item_ids)

    def test_random_teleport_requires_verified_suppression(self):
        unsafe = gear("unsafe", 23, flags={TR_TELEPORT})
        safe = gear(
            "safe-teleport",
            23,
            flags={TR_TELEPORT},
            teleport_suppressed=True,
        )
        loadouts = list(enumerate_loadouts([self.light, unsafe, safe]))
        self.assertTrue(all("unsafe" not in loadout.item_ids for loadout in loadouts))
        self.assertTrue(any("safe-teleport" in loadout.item_ids for loadout in loadouts))

    def test_ego_and_artifact_need_full_identification(self):
        ego = gear("ego", 23, ego=True, fully_known=False)
        result = optimize_loadout(
            [self.light, ego], lambda loadout: metrics(1), depth=1
        )
        self.assertEqual(result.incomplete_item_ids, {"ego"})
        self.assertEqual(result.combinations_considered, 0)
        self.assertFalse(result.timed_out)
        self.assertTrue(all("ego" not in entry.loadout.item_ids for entry in result.pareto_frontier))

    def test_dragon_helm_needs_full_identification_for_random_resistance(self):
        helm = gear(
            "dragon-helm",
            TVAL_HELM,
            sval=SV_DRAGON_HELM,
            fully_known=False,
        )
        result = optimize_loadout(
            [self.light, helm], lambda loadout: metrics(1), depth=40
        )
        self.assertEqual(result.incomplete_item_ids, {"dragon-helm"})
        self.assertTrue(
            all(
                "dragon-helm" not in entry.loadout.item_ids
                for entry in result.pareto_frontier
            )
        )

    def test_unidentified_average_item_is_ignored_without_blocking(self):
        average = gear(
            "average",
            23,
            known=False,
            fully_known=False,
            pseudo_feeling="average",
        )
        result = optimize_loadout(
            [self.light, average], lambda loadout: metrics(1), depth=1
        )
        self.assertFalse(result.timed_out)
        self.assertEqual(result.incomplete_item_ids, frozenset())
        self.assertIsNotNone(result.best)
        self.assertNotIn("average", result.best.loadout.item_ids)

    def test_cursed_and_broken_items_are_not_candidates(self):
        cursed = gear("cursed", 23, cursed=True)
        broken = gear("broken", 23, broken=True)
        loadouts = list(enumerate_loadouts([self.light, cursed, broken]))
        self.assertTrue(all(not ({"cursed", "broken"} & loadout.item_ids) for loadout in loadouts))

    def test_pinned_cursed_slots_never_move_or_become_empty(self):
        cursed_ring = gear(
            "cursed-ring", 45, cursed=True, equipped_slot=SLOT_MAIN_RING
        )
        cursed_weapon = gear(
            "cursed-weapon", 23, cursed=True, equipped_slot=SLOT_MAIN_HAND
        )
        cursed_body = gear(
            "cursed-body", 36, cursed=True, equipped_slot=SLOT_BODY
        )
        alternatives = [gear("ring", 45), gear("weapon", 23), gear("body", 36)]
        pinned = {
            SLOT_MAIN_RING: cursed_ring,
            SLOT_MAIN_HAND: cursed_weapon,
            SLOT_BODY: cursed_body,
        }

        loadouts = list(
            enumerate_loadouts(
                [self.light, cursed_ring, cursed_weapon, cursed_body, *alternatives],
                pinned,
            )
        )

        self.assertTrue(loadouts)
        self.assertTrue(
            all(
                loadout.item_at(slot) == item
                for loadout in loadouts
                for slot, item in pinned.items()
            )
        )

    def test_cursed_ring_is_pinned_while_free_body_slot_is_optimized(self):
        light = gear("light", 39, equipped_slot="light")
        cursed_ring = gear(
            "cursed-ring", 45, cursed=True, equipped_slot=SLOT_MAIN_RING
        )
        old_body = gear("old-body", 36, equipped_slot=SLOT_BODY)
        better_ring = gear("better-ring", 45)
        better_body = gear("better-body", 36)
        items = [light, cursed_ring, old_body, better_ring, better_body]
        current = Loadout(
            (("light", light), (SLOT_MAIN_RING, cursed_ring), (SLOT_BODY, old_body)),
            "empty",
        )

        result = optimize_loadout(
            items,
            lambda loadout: metrics(
                (100 if "better-ring" in loadout.item_ids else 0)
                + (10 if "better-body" in loadout.item_ids else 0)
            ),
            depth=1,
            current_item_ids=current.item_ids,
        )
        plan = plan_equipment_transactions(
            items,
            current,
            result.best.loadout,
            current_pack_items=0,
            home_scan_complete=True,
        )

        self.assertEqual(result.best.loadout.item_at(SLOT_MAIN_RING), cursed_ring)
        self.assertEqual(result.best.loadout.item_at(SLOT_BODY), better_body)
        self.assertTrue(plan.executable)
        self.assertTrue(plan.actions)
        self.assertFalse(any(blocker.startswith("cursed-equipped:") for blocker in plan.blockers))

    def test_warrior_search_pins_cursed_ring_but_still_upgrades_body(self):
        cursed_ring = gear(
            "cursed-ring", 45, cursed=True, equipped_slot=SLOT_MAIN_RING
        )
        old_body = gear("old-body", 36, equipped_slot=SLOT_BODY)
        better_body = gear("better-body", 36, flags={50})
        # A strictly better free ring: without pinning, the optimizer would
        # prefer it in the *main* ring slot and drop the cursed ring, so the
        # "main ring stays cursed" assertion below genuinely fails if the pin
        # short-circuit in _slot_choices is removed (revert-proof, not a
        # coverage illusion from cursed_ring being the only ring candidate).
        # Its beneficial flag differs from better_body's so the two upgrades do
        # not collapse into one gear-state representative during compression.
        better_ring = gear("better-ring", 45, flags={51})

        loadouts = list(
            enumerate_warrior_loadouts(
                [self.light, cursed_ring, old_body, better_body, better_ring],
                current_item_ids=frozenset(
                    {self.light.id, cursed_ring.id, old_body.id}
                ),
                pinned={SLOT_MAIN_RING: cursed_ring},
            )
        )

        self.assertTrue(loadouts)
        self.assertTrue(
            all(loadout.item_at(SLOT_MAIN_RING) == cursed_ring for loadout in loadouts)
        )
        self.assertTrue(
            any(loadout.item_at(SLOT_BODY) == better_body for loadout in loadouts)
        )
        # The strictly better ring is not discarded: it is optimized into the
        # remaining free sub-ring slot instead of the pinned main-ring slot.
        self.assertTrue(
            any(loadout.item_at(SLOT_SUB_RING) == better_ring for loadout in loadouts)
        )

    def test_pinned_sub_hand_weapon_is_valid_without_main_hand_weapon(self):
        cursed_weapon = gear(
            "cursed-sub-weapon", 23, cursed=True, equipped_slot=SLOT_SUB_HAND
        )

        loadouts = list(
            enumerate_warrior_loadouts(
                [self.light, cursed_weapon],
                current_item_ids=frozenset({self.light.id, cursed_weapon.id}),
                pinned={SLOT_SUB_HAND: cursed_weapon},
            )
        )

        self.assertTrue(loadouts)
        self.assertTrue(
            all(loadout.item_at(SLOT_MAIN_HAND) is None for loadout in loadouts)
        )
        self.assertTrue(
            all(loadout.item_at(SLOT_SUB_HAND) == cursed_weapon for loadout in loadouts)
        )

    def test_cursed_ring_with_no_free_upgrade_produces_ready_noop(self):
        light = gear("light", 39, equipped_slot="light")
        cursed_ring = gear(
            "cursed-ring", 45, cursed=True, equipped_slot=SLOT_MAIN_RING
        )
        sub_ring = gear("sub-ring", 45, equipped_slot="sub_ring")
        items = [light, cursed_ring, sub_ring, gear("better-ring", 45)]
        current = Loadout(
            (
                ("light", light),
                (SLOT_MAIN_RING, cursed_ring),
                ("sub_ring", sub_ring),
            ),
            "empty",
        )

        result = optimize_loadout(
            items,
            lambda loadout: metrics(
                (200 if "sub-ring" in loadout.item_ids else 0)
                + (100 if "better-ring" in loadout.item_ids else 0)
            ),
            depth=1,
            current_item_ids=current.item_ids,
        )
        plan = plan_equipment_transactions(
            items,
            current,
            result.best.loadout,
            current_pack_items=0,
            home_scan_complete=True,
        )

        self.assertEqual(result.best.loadout, current)
        self.assertTrue(plan.executable)
        self.assertEqual(plan.actions, ())

    def test_destruction_is_required_from_fifty(self):
        chaos = gear("chaos", 45, flags={62})
        nether = gear("nether", 40, flags={60})
        telepathy = gear("telepathy", 32, flags={79})
        owned = [self.light, chaos, nether, telepathy]
        blocked = optimize_loadout(owned, lambda loadout: metrics(10), depth=50)
        ready = optimize_loadout(
            owned, lambda loadout: metrics(10), depth=50, has_destruction=True
        )
        self.assertIsNone(blocked.best)
        self.assertIsNotNone(ready.best)

    def test_speed_plus_twenty_five_is_required_only_after_eighty(self):
        requirements = frozenset({"resist_chaos", "resist_neth", "telepathy"})
        at_eighty = optimize_loadout(
            [self.light],
            lambda loadout: metrics(10, speed=0),
            depth=80,
            intrinsic_abilities=requirements,
            has_destruction=True,
        )
        at_eighty_one = optimize_loadout(
            [self.light],
            lambda loadout: metrics(10, speed=24),
            depth=81,
            intrinsic_abilities=requirements,
            has_destruction=True,
        )
        self.assertIsNotNone(at_eighty.best)
        self.assertIsNone(at_eighty_one.best)

    def test_one_percent_tie_keeps_current_loadout(self):
        current = gear("current", 23, equipped_slot=SLOT_MAIN_HAND)
        candidate = gear("candidate", 23)

        def evaluate(loadout):
            return metrics(100.5 if "candidate" in loadout.item_ids else 100.0)

        result = optimize_loadout(
            [self.light, current, candidate],
            evaluate,
            depth=1,
            current_item_ids=frozenset({"light", "current"}),
        )
        self.assertEqual(result.best.loadout.item_ids, {"light", "current"})

    def test_more_than_one_percent_replaces_current_loadout(self):
        current = gear("current", 23, equipped_slot=SLOT_MAIN_HAND)
        candidate = gear("candidate", 23)

        def evaluate(loadout):
            return metrics(102.0 if "candidate" in loadout.item_ids else 100.0)

        result = optimize_loadout(
            [self.light, current, candidate],
            evaluate,
            depth=1,
            current_item_ids=frozenset({"light", "current"}),
        )
        self.assertIn("candidate", result.best.loadout.item_ids)

    def test_finite_combat_margin_replaces_negative_infinity(self):
        empty = gear("empty", 39)
        weapon = gear("weapon", 23)

        result = optimize_loadout(
            [empty, weapon],
            lambda loadout: metrics(
                1 if "weapon" in loadout.item_ids else -float("inf")
            ),
            depth=1,
        )

        self.assertIn("weapon", result.best.loadout.item_ids)

    def test_best_selection_does_not_claim_a_disposal_proof(self):
        weak = gear("weak", 23)
        strong = gear("strong", 23)

        def evaluate(loadout):
            if "strong" in loadout.item_ids:
                return metrics(20, traits={"resist_fire"})
            if "weak" in loadout.item_ids:
                return metrics(10)
            return metrics(1)

        result = optimize_loadout([self.light, weak, strong], evaluate, depth=1)
        self.assertEqual(result.dominated_item_ids, frozenset())

    def test_timeout_returns_no_partial_best(self):
        result = optimize_loadout(
            [self.light], lambda loadout: metrics(1), depth=1, timeout_seconds=0
        )
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.best)

    def test_static_requirements_skip_expensive_evaluation(self):
        calls = 0

        def evaluate(loadout):
            nonlocal calls
            calls += 1
            return metrics(1)

        result = optimize_loadout([self.light], evaluate, depth=1)

        self.assertFalse(result.timed_out)
        self.assertEqual(result.combinations_considered, 2)
        self.assertEqual(result.invalid_combinations, 1)
        self.assertEqual(calls, 1)


class OwnedEquipmentCatalogTest(unittest.TestCase):
    @staticmethod
    def _home_item(letter, name="sword"):
        return StoreItem(
            letter=letter,
            name=name,
            count=1,
            tval=23,
            sval=1,
            price=0,
            known=True,
            fully_known=True,
            is_equipment=True,
        )

    def _full_page(self, name):
        return [
            self._home_item(chr(ord("a") + index), f"{name}-{index}")
            for index in range(12)
        ]

    def test_keeps_identical_physical_home_items(self):
        catalog = OwnedEquipmentCatalog()
        catalog.observe_home_page(
            [self._home_item("a"), self._home_item("b")]
        )
        self.assertEqual(len(catalog.items), 2)
        self.assertEqual(len({item.id for item in catalog.items}), 2)

    def test_home_scan_completes_only_when_a_page_repeats(self):
        catalog = OwnedEquipmentCatalog()
        first = self._full_page("sword")
        second = self._full_page("armour")
        self.assertFalse(catalog.observe_home_page(first))
        self.assertFalse(catalog.observe_home_page(second))
        self.assertTrue(catalog.observe_home_page(first))
        self.assertTrue(catalog.home_scan_complete)

    def test_single_short_home_page_completes_immediately(self):
        catalog = OwnedEquipmentCatalog()
        page = [
            self._home_item(chr(ord("a") + index), f"item-{index}")
            for index in range(10)
        ]

        self.assertTrue(catalog.observe_home_page(page, allow_wrap=False))
        self.assertTrue(catalog.home_scan_complete)

    def test_empty_home_scan_completes_immediately(self):
        catalog = OwnedEquipmentCatalog()

        self.assertTrue(catalog.observe_home_page([], allow_wrap=False))
        self.assertTrue(catalog.home_scan_complete)

    def test_repeated_snapshot_does_not_complete_without_page_advance(self):
        catalog = OwnedEquipmentCatalog()
        page = self._full_page("sword")

        self.assertFalse(catalog.observe_home_page(page, allow_wrap=False))
        self.assertFalse(catalog.observe_home_page(page, allow_wrap=False))
        self.assertFalse(catalog.home_scan_complete)
        self.assertTrue(catalog.observe_home_page(page, allow_wrap=True))

    def test_equipment_identity_is_not_shifted_by_preceding_consumable(self):
        catalog = OwnedEquipmentCatalog()
        consumable = StoreItem(
            letter="a", count=1, tval=70, sval=1, price=10, name="ration",
            is_equipment=False,
        )
        sword = self._home_item("b", "sword")

        catalog.observe_home_page([consumable, sword])

        self.assertEqual(len(catalog.items), 1)
        self.assertEqual(catalog.items[0].item.name, "sword")

    def test_non_equipment_pages_do_not_hide_later_weapon_pages(self):
        ammunition_page = [
            StoreItem(
                letter=chr(ord("a") + index),
                name=f"arrows-{index}",
                count=20,
                tval=TVAL_ARROW,
                sval=1,
                price=0,
                known=True,
                fully_known=True,
                is_equipment=True,
            ) for index in range(12)
        ]
        consumable_page = [
            StoreItem(
                letter=chr(ord("a") + index),
                name=f"healing potion-{index}",
                count=2,
                tval=75,
                sval=1,
                price=0,
                known=True,
                fully_known=True,
                is_equipment=False,
            ) for index in range(12)
        ]
        weapon_page = self._full_page("extra attacks trident")
        catalog = OwnedEquipmentCatalog()

        self.assertFalse(catalog.observe_home_page(ammunition_page))
        self.assertFalse(catalog.observe_home_page(consumable_page))
        self.assertFalse(catalog.observe_home_page(weapon_page))
        self.assertTrue(catalog.observe_home_page(ammunition_page))

        self.assertTrue(catalog.home_scan_complete)
        self.assertEqual(
            [owned.item.name for owned in catalog.items],
            [f"extra attacks trident-{index}" for index in range(12)],
        )

    def test_invalidation_discards_stale_home_scan(self):
        catalog = OwnedEquipmentCatalog()
        page = [self._home_item("a")]
        catalog.observe_home_page(page)
        catalog.observe_home_page(page)
        catalog.invalidate_home()
        self.assertFalse(catalog.home_scan_complete)
        self.assertEqual(catalog.items, ())

    def test_refresh_carried_preserves_equipped_slot(self):
        catalog = OwnedEquipmentCatalog()
        worn = InventoryItem(
            slot="main_hand",
            name="sword",
            count=1,
            tval=23,
            sval=1,
            aware=True,
            known=True,
            fully_known=True,
            is_equipment=True,
        )
        catalog.refresh_carried([], [worn])
        self.assertEqual(catalog.items[0].equipped_slot, "main_hand")

    def test_verified_dot_inscription_makes_random_teleport_legal(self):
        mask = InventoryItem(
            slot="a",
            name="Terror Mask {.}",
            count=1,
            tval=TVAL_HELM,
            sval=5,
            aware=True,
            known=True,
            fully_known=True,
            is_equipment=True,
            is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        catalog = OwnedEquipmentCatalog()
        catalog.refresh_carried([mask], [])

        self.assertTrue(random_teleport_is_suppressed(mask))
        self.assertTrue(catalog.items[0].random_teleport_suppressed)
        self.assertTrue(catalog.items[0].exploration_legal)

    def test_period_outside_inscription_does_not_suppress_random_teleport(self):
        mask = InventoryItem(
            slot="a", name="Terror.Mask {special}", count=1,
            tval=TVAL_HELM, sval=5, aware=True, known=True,
            fully_known=True, is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        self.assertFalse(random_teleport_is_suppressed(mask))

    def test_verified_home_inscription_is_also_legal(self):
        mask = StoreItem(
            letter="a", name="Terror Mask {special;.}", count=1,
            tval=TVAL_HELM, sval=5, price=0, known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        catalog = OwnedEquipmentCatalog()
        catalog.observe_home_page([mask])

        self.assertTrue(catalog.items[0].random_teleport_suppressed)
        self.assertTrue(catalog.items[0].exploration_legal)

    def test_refresh_carried_keeps_light_identity_when_fuel_name_changes(self):
        catalog = OwnedEquipmentCatalog()

        def lantern(fuel):
            return InventoryItem(
                slot="light",
                name=f"Brass Lantern ({fuel} turns of light)",
                count=1,
                tval=TVAL_LITE,
                sval=SV_LITE_LANTERN,
                aware=True,
                known=True,
                fully_known=True,
                is_equipment=True,
                fuel=fuel,
                known_flags=frozenset({86, 122, 127}),
            )

        catalog.refresh_carried([], [lantern(8004)])
        first_id = catalog.items[0].id
        catalog.refresh_carried([], [lantern(8003)])

        self.assertEqual(catalog.items[0].id, first_id)

    def test_ammunition_is_not_owned_loadout_equipment(self):
        arrow = StoreItem(
            letter="a",
            name="cursed arrow",
            count=1,
            tval=TVAL_ARROW,
            sval=1,
            price=0,
            known=False,
            fully_known=False,
            is_equipment=True,
            pseudo_feeling="cursed",
        )
        catalog = OwnedEquipmentCatalog()

        catalog.observe_home_page([arrow])

        self.assertEqual(catalog.items, ())


if __name__ == "__main__":
    unittest.main()
