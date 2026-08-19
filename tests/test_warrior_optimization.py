import inspect
import unittest
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.equipment_optimizer import (
    EvaluatedLoadout,
    Loadout,
    LoadoutMetrics,
    OptimizationResult,
    OwnedEquipment,
    SLOT_MAIN_RING,
    current_loadout,
    equipment_identity,
)
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionObservation,
    EquipmentTransactionSession,
    observe_equipment_transactions,
)
from hengbot.model import (
    InventoryItem,
    PLAYER_CLASS_WARRIOR,
    PlayerState,
    Position,
    Snapshot,
    STORE_ALCHEMIST,
    STORE_HOME,
    StoreItem,
)
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import (
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    HengbotPolicy,
)
from hengbot.warrior_optimization import (
    ConfirmedLoadoutRecord,
    INCREMENTAL_SEARCH_CATALOG_THRESHOLD,
    PLAYER_ABILITY_FLAGS,
    WarriorOptimizationPreparation,
    load_confirmed_loadout,
    prepare_warrior_optimization,
    save_confirmed_loadout,
    warrior_optimizer_input_key,
    weapon_expected_dps,
)


def _legacy_base_stat_without_gear(displayed_value, current, flag):
    """Test-only copy of the deleted pre-P1 de-gearing formula.

    Production no longer contains any per-call modify_stat_value inversion;
    the fixtures keep this copy solely to seed calibrations whose constants
    equal what the pre-P1 code derived, preserving every assertion's meaning.
    """
    from hengbot.warrior_equipment_evaluator import modify_stat_value

    equipment_bonus = sum(
        owned.item.pval for _, owned in current.slots if flag in owned.flags
    )
    return modify_stat_value(displayed_value, -equipment_bonus)


def _legacy_conservative_intrinsic(abilities, current):
    """Test-only copy of the deleted pre-P1 intrinsic-ability subtraction."""
    equipment_abilities = {
        name
        for name, flag in PLAYER_ABILITY_FLAGS.items()
        if flag in current.flags
    }
    return frozenset(abilities).difference(equipment_abilities)
from hengbot.warrior_loadout_search import (
    enumerate_single_slot_variants,
    enumerate_warrior_loadouts,
)
from hengbot.warrior_equipment_evaluator import TR_BLOWS, TR_DEX, TR_STR


def gear(
    item_id, origin, *, slot=None, tval=23, ac=0, to_a=0, to_d=0,
    to_h=0, pval=0, flags=(), dice=(1, 4), weight=30, proficiency=0,
    cursed=False,
):
    item = InventoryItem(
        slot=slot or item_id, name=item_id, count=1, tval=tval, sval=1,
        aware=True, known=True, fully_known=True, is_equipment=True,
        ac=ac, to_a=to_a, to_h=to_h, to_d=to_d, pval=pval, weight=weight,
        damage_dice_num=dice[0], damage_dice_sides=dice[1],
        known_flags=frozenset(flags), weapon_proficiency=proficiency,
        is_cursed=cursed,
    )
    return OwnedEquipment(item_id, item, origin, equipped_slot=slot)




def seed_calibration(snapshot, items=()):
    """The constants a naked observation of this fixture player would yield.

    P1 made the worn-independent calibration a MANDATORY selector input with
    no legacy fallback.  This helper computes the constants with the exact
    pre-P1 inline formulas (over the catalog's current loadout), so every
    pre-existing assertion keeps its meaning unchanged.
    """
    from hengbot.equipment_optimizer import current_loadout as _current_loadout
    from hengbot.warrior_defense_evaluator import (
        WarriorDefenseInputs,
        loadout_armor_class,
    )
    from hengbot.warrior_equipment_evaluator import modify_stat_value
    from hengbot.warrior_loadout_evaluator import (
        TR_CON,
        constitution_hp_bonus,
    )
    from hengbot.warrior_optimization import (
        CharacterCalibration,
        _equipment_speed,
        _intrinsic_flags,
    )

    player = snapshot.player
    for name, default in (
        ("race_id", -1), ("personality_id", -1), ("level", 1),
    ):
        if not hasattr(player, name):
            setattr(player, name, default)
    current = _current_loadout(items)
    displayed = tuple(getattr(player, "stat_use", ()))
    if not (len(displayed) >= 4 and displayed[0] > 0 and displayed[3] > 0):
        displayed = tuple(player.stat_cur)
    base_str = _legacy_base_stat_without_gear(displayed[0], current, TR_STR)
    base_dex = _legacy_base_stat_without_gear(displayed[3], current, TR_DEX)
    base_con = (
        _legacy_base_stat_without_gear(displayed[4], current, TR_CON)
        if len(displayed) >= 5
        else 3
    )
    current_con = modify_stat_value(
        base_con,
        sum(o.item.pval for _, o in current.slots if TR_CON in o.flags),
    )
    intrinsic = _legacy_conservative_intrinsic(
        frozenset(getattr(player, "abilities", frozenset())), current
    )
    provisional = WarriorDefenseInputs(
        level=player.level,
        natural_dex=base_dex,
        shield_skill=getattr(player, "shield_skill", 0),
        base_speed=getattr(player, "speed", 110) - _equipment_speed(current),
        saving_skill=getattr(player, "saving_skill", 0),
        intrinsic_flags=_intrinsic_flags(intrinsic),
    )
    padded = displayed + (10,) * max(0, 6 - len(displayed))
    return CharacterCalibration(
        race_id=player.race_id,
        class_id=getattr(player, "class_id", -1),
        personality_id=player.personality_id,
        level=player.level,
        stat_cur=tuple(player.stat_cur),
        base_stats=(
            base_str, padded[1], padded[2], base_dex, base_con, padded[5],
        ),
        base_hp=max(
            1,
            getattr(player, "max_hp", 1)
            - constitution_hp_bonus(current_con, player.level),
        ),
        base_ac_bonus=getattr(player, "ac", 0)
        - loadout_armor_class(current, provisional),
        intrinsic_abilities=intrinsic,
        pinned_identities=tuple(
            sorted(
                (owned.equipped_slot or "", equipment_identity(owned.item))
                for owned in items
                if getattr(owned, "origin", "") == "equipped"
                and owned.item.is_cursed
            )
        ),
    )


class WarriorOptimizationTest(unittest.TestCase):
    @staticmethod
    def _result_for(loadout):
        evaluated = EvaluatedLoadout(
            loadout, LoadoutMetrics(1.0, 1.0, 1.0)
        )
        return OptimizationResult(
            evaluated, (), (), frozenset(), 1, 1, 0, 0.0, False,
            frozenset(),
        )

    def test_reference_ac_dual_wield_brand_dps_crosses_q1_gate(self):
        main = gear(
            "main", "equipped", slot="main_hand", to_h=3, to_d=2,
            dice=(2, 4), weight=100, proficiency=6000,
        ).item
        branded_sub = gear(
            "sub", "equipped", slot="sub_hand", to_h=6, to_d=7,
            dice=(1, 5), weight=30, flags=(29,), proficiency=6000,
        ).item
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(43, 12, 16, 17), stat_use=(123, 3, 7, 38),
            level=14, melee_skill=136, two_weapon_skill=6000,
        )
        snapshot = SimpleNamespace(player=player, equipment=(main, branded_sub))
        calibration = seed_calibration(snapshot)

        self.assertGreaterEqual(
            weapon_expected_dps(snapshot, main, 24, calibration), 28
        )
        self.assertLess(
            weapon_expected_dps(snapshot, main, 100, calibration), 28
        )
        # P1: without the calibrated constants the score is unknowable and
        # the caller must fail closed.
        self.assertIsNone(weapon_expected_dps(snapshot, main, 24, None))

    def test_weapon_dps_includes_branded_off_hand(self):
        main = gear(
            "main", "equipped", slot="main_hand", to_h=3, to_d=2,
            dice=(2, 4), weight=100, proficiency=6000,
        ).item
        branded_sub = gear(
            "sub", "equipped", slot="sub_hand", to_h=6, to_d=7,
            dice=(1, 5), weight=30, flags=(29,), proficiency=6000,
        ).item
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(43, 12, 16, 17), stat_use=(123, 3, 7, 38),
            level=14, melee_skill=136, two_weapon_skill=6000,
        )
        dual = SimpleNamespace(player=player, equipment=(main, branded_sub))
        single = SimpleNamespace(player=player, equipment=(main,))
        calibration = seed_calibration(dual)

        self.assertGreater(
            weapon_expected_dps(dual, main, 24, calibration),
            weapon_expected_dps(single, main, 24, calibration),
        )

    def test_reconstructs_weapon_and_shield(self):
        weapon = gear("weapon", "equipped", slot="main_hand")
        shield = gear("shield", "equipped", slot="sub_hand", tval=34)
        loadout = current_loadout((weapon, shield))
        self.assertEqual(loadout.hand_mode, "weapon_shield")
        self.assertEqual(loadout.item_ids, frozenset({"weapon", "shield"}))

    def test_fails_closed_without_static_monster_knowledge(self):
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, stat_cur=(18, 10, 10, 18),
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        prepared = prepare_warrior_optimization(
            snapshot, (), {}, depth=1, home_scan_complete=True,
            calibration=seed_calibration(snapshot),
        )
        self.assertEqual(prepared.blockers, ("missing-monrace-knowledge",))

    def test_fails_closed_before_complete_home_scan(self):
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, stat_cur=(18, 10, 10, 18),
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        prepared = prepare_warrior_optimization(
            snapshot, (), {1: object()}, depth=1, home_scan_complete=False,
            calibration=seed_calibration(snapshot),
        )
        self.assertEqual(prepared.blockers, ("home-scan-incomplete",))

    def test_builds_transaction_for_stronger_complete_loadout(self):
        light = gear("light", "equipped", slot="light", tval=39)
        old = gear("old", "equipped", slot="main_hand")
        better = gear("better", "home", to_d=20)
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(18, 10, 10, 18),
            level=10,
            shield_skill=0,
            speed=110,
            saving_skill=30,
            abilities=frozenset(),
            ac=0,
            melee_skill=60,
            two_weapon_skill=0,
            max_hp=100,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )
        prepared = prepare_warrior_optimization(
            snapshot, (light, old, better), {1: monster}, depth=1,
            home_scan_complete=True,
            calibration=seed_calibration(snapshot, (light, old, better)),
        )
        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertIn("better", prepared.result.best.loadout.item_ids)
        self.assertTrue(
            any(
                action.kind == "withdraw" and action.item_id == "better"
                for action in prepared.transaction.actions
            )
        )

    def test_excluded_worn_light_is_not_stripped_by_transaction_plan(self):
        worn_light = gear("worn-light", "equipped", slot="light", tval=39)
        old = gear("old-sword", "equipped", slot="main_hand")
        better = gear("replacement-sword", "home", to_d=20)
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(18, 10, 10, 18),
            level=10,
            shield_skill=0,
            speed=110,
            saving_skill=30,
            abilities=frozenset(),
            ac=0,
            melee_skill=60,
            two_weapon_skill=0,
            max_hp=100,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )
        items = (worn_light, old, better)

        prepared = prepare_warrior_optimization(
            snapshot, items, {1: monster}, depth=None,
            home_scan_complete=True,
            search_excluded_item_ids=frozenset({"worn-light"}),
            calibration=seed_calibration(snapshot, items),
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertNotIn("worn-light", prepared.result.best.loadout.item_ids)
        self.assertFalse(any(
            action.kind == "takeoff" and action.item_id == "worn-light"
            for action in prepared.transaction.actions
        ))

    def test_large_catalog_uses_bounded_incremental_search(self):
        # Live 2026-07-24: a 51-item catalog at a shallow depth produced ~51,000
        # candidates that timed out the 25s search and tripped the bot's 90s
        # decision watchdog inside the evaluator.  At or above
        # INCREMENTAL_SEARCH_CATALOG_THRESHOLD, prepare must hill-climb one slot
        # at a time (enumerate_single_slot_variants) instead of the full
        # combinatorial search.  Revert-proof: the number of loadouts optimize_
        # loadout considers equals the single-slot count, which this catalog
        # makes differ from the full-search count.
        light = gear("light", "equipped", slot="light", tval=39)
        light = replace(light, item=replace(light.item, fuel=1000))
        weapon = gear("weapon", "equipped", slot="main_hand", to_d=8)
        extras = tuple(
            gear(f"{tval}-{k}", "home", tval=tval, flags=(48 + k,))
            for tval in (37, 32, 35, 30, 31, 40, 45)
            for k in range(7)
        )
        items = (light, weapon, *extras)
        self.assertGreaterEqual(len(items), INCREMENTAL_SEARCH_CATALOG_THRESHOLD)
        current_ids = frozenset({"light", "weapon"})

        incremental_count = sum(
            1
            for _ in enumerate_single_slot_variants(
                items, current_item_ids=current_ids, require_light=True
            )
        )
        full_count = sum(
            1
            for _ in enumerate_warrior_loadouts(
                items, current_item_ids=current_ids, require_light=True
            )
        )
        # The catalog must actually distinguish the two searches, or the test
        # proves nothing.
        self.assertNotEqual(incremental_count, full_count)

        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(18, 10, 10, 18),
            level=10,
            shield_skill=0,
            speed=110,
            saving_skill=30,
            abilities=frozenset(),
            ac=0,
            melee_skill=60,
            two_weapon_skill=0,
            max_hp=100,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )

        prepared = prepare_warrior_optimization(
            snapshot, items, {1: monster}, depth=1, home_scan_complete=True,
            calibration=seed_calibration(snapshot, items),
        )

        self.assertIsNotNone(prepared.result)
        self.assertFalse(prepared.result.timed_out)
        self.assertEqual(
            prepared.result.combinations_considered, incremental_count
        )

    def test_live_55_item_shape_searches_despite_incomplete_items(self):
        """The 2026-08-12 11-equipped/44-Home catalogue must enumerate."""
        equipped_specs = (
            ("light", "light", 39),
            ("weapon", "main_hand", 23),
            ("shield", "sub_hand", 34),
            ("body", "body", 37),
            ("head", "head", 32),
            ("cloak", "outer", 35),
            ("gloves", "arms", 31),
            ("boots", "feet", 30),
            ("amulet", "neck", 40),
            ("ring-a", "main_ring", 45),
            ("ring-b", "sub_ring", 45),
        )
        equipped = tuple(
            gear(item_id, "equipped", slot=slot, tval=tval)
            for item_id, slot, tval in equipped_specs
        )
        home = tuple(
            gear(
                f"home-{index}", "home",
                tval=(23, 30, 31, 32, 35, 37, 40, 45)[index % 8],
            )
            for index in range(44)
        )
        home = (
            replace(home[0], item=replace(
                home[0].item, aware=False, known=False, fully_known=False,
            )),
            replace(home[1], item=replace(
                home[1].item, aware=False, known=False, fully_known=False,
            )),
            *home[2:],
        )
        items = (*equipped, *home)
        self.assertEqual(len(items), 55)
        self.assertEqual(sum(item.origin == "equipped" for item in items), 11)
        self.assertEqual(sum(item.origin == "home" for item in items), 44)
        self.assertGreaterEqual(len(items), INCREMENTAL_SEARCH_CATALOG_THRESHOLD)

        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, stat_cur=(18, 10, 10, 18), level=30,
            shield_skill=0, speed=110, saving_skill=30, abilities=frozenset(),
            ac=0, melee_skill=60, two_weapon_skill=0, max_hp=100, max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=127, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )

        prepared = prepare_warrior_optimization(
            snapshot, items, {1: monster}, depth=None,
            home_scan_complete=True, calibration=seed_calibration(snapshot, items),
        )

        self.assertEqual(prepared.result.incomplete_item_ids, {"home-0", "home-1"})
        self.assertGreater(prepared.result.combinations_considered, 0)
        self.assertIn("incomplete-equipment-catalog", prepared.blockers)

    def test_constitution_helm_is_not_replaced_by_small_ac_gain(self):
        light = gear("light", "equipped", slot="light", tval=39)
        weapon = gear("weapon", "equipped", slot="main_hand", to_d=8)
        stat_helm = gear(
            "stat-helm", "equipped", slot="head", tval=33,
            ac=0, to_a=4, pval=3, flags=(TR_STR, TR_DEX, 4),
        )
        steel_helm = gear(
            "steel-helm", "home", tval=33, ac=6, to_a=2,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(60, 12, 16, 17, 110, 13),
            stat_use=(170, 3, 7, 68, 210, 9),
            level=25,
            shield_skill=4000,
            speed=110,
            saving_skill=57,
            abilities=frozenset(),
            ac=86,
            melee_skill=175,
            shooting_skill=130,
            two_weapon_skill=4184,
            max_hp=627,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=80, average_hp=80, speed=110, can_summon=False,
            friendly=False, level=15, armor_class=20, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 4, 6),),
        )

        prepared = prepare_warrior_optimization(
            snapshot,
            (light, weapon, stat_helm, steel_helm),
            {1: monster},
            depth=15,
            home_scan_complete=True,
            calibration=seed_calibration(
                snapshot, (light, weapon, stat_helm, steel_helm)
            ),
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(
            prepared.result.best.loadout.item_at("head"),
            stat_helm,
        )

    def test_ac_five_does_not_beat_three_strength_dexterity_constitution(self):
        light = gear("light", "equipped", slot="light", tval=39)
        weapon = gear(
            "weapon", "equipped", slot="main_hand", to_h=6, to_d=12,
        )
        crown = gear(
            "crown-of-might", "equipped", slot="head", tval=33,
            ac=0, to_a=3, pval=3, flags=(TR_STR, TR_DEX, 4),
        )
        steel_helm = gear(
            "steel-helm", "home", tval=32, ac=6, to_a=2,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(60, 12, 16, 17, 110, 14),
            stat_use=(170, 3, 7, 68, 210, 10),
            level=27,
            shield_skill=4000,
            speed=110,
            saving_skill=59,
            abilities=frozenset(),
            ac=85,
            melee_skill=181,
            shooting_skill=136,
            two_weapon_skill=4184,
            max_hp=663,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        # Weak encounters expose the former AC overvaluation most strongly:
        # AC affected both hit probability and HURT reduction, so this exact
        # five-point gain used to displace all three +3 stats.
        monster = MonraceKnowledge(
            max_hp=80, average_hp=80, speed=110, can_summon=False,
            friendly=False, level=2, armor_class=20, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 4, 6),),
        )

        prepared = prepare_warrior_optimization(
            snapshot,
            (light, weapon, crown, steel_helm),
            {1: monster},
            depth=15,
            home_scan_complete=True,
            calibration=seed_calibration(
                snapshot, (light, weapon, crown, steel_helm)
            ),
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(prepared.result.best.loadout.item_at("head"), crown)

    def test_crown_stat_threshold_is_recomputed_with_each_weapon_candidate(self):
        light = gear("light", "equipped", slot="light", tval=39)
        dagger = gear(
            "fire-dagger", "equipped", slot="main_hand", to_h=6, to_d=12,
            dice=(1, 4), weight=12, flags=(30,), proficiency=6000,
        )
        steel_helm = gear(
            "steel-helm", "equipped", slot="head", tval=32, ac=6, to_a=2,
        )
        crown = gear(
            "crown-of-might", "home", tval=33, ac=0, to_a=3,
            pval=3, flags=(TR_STR, TR_DEX, 4),
        )
        extra_attack_sword = gear(
            "extra-attack-longsword", "home", to_h=5, to_d=6,
            pval=1, flags=(TR_BLOWS,), dice=(2, 5), weight=130,
            proficiency=4000,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(60, 12, 16, 17, 110, 14),
            stat_use=(140, 3, 7, 38, 180, 10),
            level=27,
            shield_skill=4000,
            speed=110,
            saving_skill=59,
            abilities=frozenset(),
            ac=85,
            melee_skill=181,
            shooting_skill=136,
            two_weapon_skill=4184,
            max_hp=616,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=80, average_hp=80, speed=110, can_summon=False,
            friendly=False, level=2, armor_class=20, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 4, 6),),
        )

        prepared = prepare_warrior_optimization(
            snapshot,
            (light, dagger, steel_helm, crown, extra_attack_sword),
            {1: monster},
            depth=15,
            home_scan_complete=True,
            calibration=seed_calibration(
                snapshot, (light, dagger, steel_helm, crown, extra_attack_sword)
            ),
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(prepared.result.best.loadout.item_at("head"), crown)
        self.assertEqual(
            prepared.result.best.loadout.item_at("main_hand"),
            extra_attack_sword,
        )

    def test_preserves_current_free_action_despite_large_ac_gain(self):
        light = gear("light", "equipped", slot="light", tval=39)
        weapon = gear("weapon", "equipped", slot="main_hand", to_d=8)
        crown = gear(
            "crown-of-might", "equipped", slot="head", tval=33,
            ac=0, to_a=3, pval=3, flags=(TR_STR, TR_DEX, 4, 46, 61),
        )
        steel_helm = gear(
            "steel-helm", "home", tval=32, ac=20, to_a=20,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(60, 12, 16, 17, 110, 14),
            stat_use=(170, 3, 7, 68, 210, 10),
            level=27,
            shield_skill=4000,
            speed=110,
            saving_skill=59,
            abilities=frozenset({"free_action", "resist_nexus"}),
            ac=85,
            melee_skill=181,
            shooting_skill=136,
            two_weapon_skill=4184,
            max_hp=663,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=80, average_hp=80, speed=110, can_summon=False,
            friendly=False, level=15, armor_class=20, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 4, 6),),
        )

        prepared = prepare_warrior_optimization(
            snapshot,
            (light, weapon, crown, steel_helm),
            {1: monster},
            depth=15,
            home_scan_complete=True,
            calibration=seed_calibration(
                snapshot, (light, weapon, crown, steel_helm)
            ),
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(prepared.result.best.loadout.item_at("head"), crown)

    def test_cursed_equipped_ring_is_pinned_through_production_entry(self):
        # Guards the pin comprehension in prepare_warrior_optimization itself
        # (warrior_optimization.py), which is a separate copy from the one in
        # equipment_optimizer.py and is the real Warrior production path. Because
        # this entry supplies candidate_loadouts, optimize_loadout never
        # recomputes the pin, so a typo isolated to this copy would otherwise be
        # invisible to the unit tests. Revert proof: emptying that comprehension
        # drops the (non-exploration-legal) cursed ring from the candidates, the
        # planner then tries to remove it, and prepared.ready flips to False.
        light = gear("light", "equipped", slot="light", tval=39)
        cursed_ring = gear(
            "cursed-ring", "equipped", slot="main_ring", tval=45, cursed=True,
        )
        old_weapon = gear("old-weapon", "equipped", slot="main_hand")
        better_weapon = gear("better-weapon", "home", to_d=20)
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(18, 10, 10, 18),
            level=10,
            shield_skill=0,
            speed=110,
            saving_skill=30,
            abilities=frozenset(),
            ac=0,
            melee_skill=60,
            two_weapon_skill=0,
            max_hp=100,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )

        prepared = prepare_warrior_optimization(
            snapshot, (light, cursed_ring, old_weapon, better_weapon),
            {1: monster}, depth=1, home_scan_complete=True,
            calibration=seed_calibration(
                snapshot, (light, cursed_ring, old_weapon, better_weapon)
            ),
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(
            prepared.result.best.loadout.item_at(SLOT_MAIN_RING), cursed_ring
        )
        self.assertFalse(
            any(
                blocker.startswith("cursed-equipped:")
                for blocker in prepared.blockers
            )
        )
        # The free weapon slot is still optimized around the pinned cursed ring.
        self.assertIn("better-weapon", prepared.result.best.loadout.item_ids)
        self.assertTrue(
            any(
                action.kind == "withdraw" and action.item_id == "better-weapon"
                for action in prepared.transaction.actions
            )
        )

    def test_saber_loses_to_strictly_better_home_long_sword(self):
        light = gear("light", "equipped", slot="light", tval=39)
        saber = gear(
            "saber", "equipped", slot="main_hand", to_h=2, to_d=1,
            dice=(1, 7), weight=50,
        )
        gauche = gear(
            "gauche", "equipped", slot="sub_hand", to_h=3, to_d=3,
            dice=(1, 5), weight=30,
        )
        long_sword = gear(
            "long-sword", "home", to_h=5, to_d=7,
            dice=(2, 5), weight=130,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, stat_cur=(68, 10, 10, 68),
            stat_use=(68, 10, 10, 68), level=27, shield_skill=0,
            speed=110, saving_skill=40, abilities=frozenset(), ac=0,
            melee_skill=80, two_weapon_skill=4000, max_hp=494, max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=15, average_hp=15, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=100, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 6),),
        )
        with TemporaryDirectory() as directory:
            report = Path(directory) / "loadout-report.jsonl"
            prepared = prepare_warrior_optimization(
                snapshot, (light, saber, gauche, long_sword), {1: monster},
                depth=1, home_scan_complete=True, loadout_report_path=report,
                calibration=seed_calibration(
                    snapshot, (light, saber, gauche, long_sword)
                ),
            )
            record = json.loads(report.read_text(encoding="utf-8"))
        self.assertLessEqual(len(record["candidates"]), 3)
        self.assertEqual(record["candidates"][0]["rank"], 1)
        self.assertIn("melee_output", record["candidates"][0]["score"])
        self.assertIn("long-sword", {
            item["id"] for item in record["candidates"][0]["slots"].values()
        })
        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertIn("long-sword", prepared.result.best.loadout.item_ids)
        self.assertTrue(any(
            action.kind == "withdraw" and action.item_id == "long-sword"
            for action in prepared.transaction.actions
        ))

    def test_policy_dispatches_takeoff_with_equipment_slot_letter(self):
        shield = gear("shield", "equipped", slot="sub_hand", tval=34)
        action = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", "shield", "sub_hand",
            item_identity=equipment_identity(shield.item),
        )
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=1,
        )
        snapshot = SimpleNamespace(
            in_town=True, store=None, inventory=(), equipment=(shield.item,),
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )
        self.assertEqual(policy._equipment_transaction_town_key(snapshot), "tb")

    def test_policy_equips_withdrawn_shield_after_off_hand_takeoff(self):
        shield = gear("shield", "pack", slot="a", tval=34)
        action = EquipmentTransaction(
            PHASE_EQUIP, "equip", "shield", "sub_hand",
            item_identity=equipment_identity(shield.item),
        )
        policy = HengbotPolicy()
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=1,
        )
        policy._equipment_transaction_session = session
        before = SimpleNamespace(
            in_town=True, store=None, inventory=(shield.item,), equipment=(),
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )

        self.assertEqual(policy._equipment_transaction_town_key(before), "wa")
        self.assertTrue(policy.confirm_key_posted("wa"))
        equipped = SimpleNamespace(
            in_town=True, store=None, inventory=(),
            equipment=(gear("shield", "equipped", slot="sub_hand", tval=34).item,),
            player=before.player,
        )
        session.observe(observe_equipment_transactions(equipped))
        self.assertTrue(session.complete)

    def test_real_capture_deposit_confirmation_stall_releases_visibly(self):
        """03:03:57: slot n spear and Home pages stayed physically unchanged."""
        identity = "af7df9197aab84bc"
        item_id = f"pack:{identity}:0"
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "deposit", item_id,
            item_identity=identity,
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 23),
            max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
        )
        unchanged_home = EquipmentTransactionObservation.create(
            in_home=True, pack_identities=(identity,),
        )
        self.assertTrue(
            session.prepare(
                action,
                unchanged_home,
                "dn\r",
                ("home", 2242290, "n", identity),
            )
        )
        self.assertTrue(session.confirm_posted("dn\r"))

        policy = HengbotPolicy()
        policy._equipment_transaction_session = session
        policy._prepare_equipment_optimization = lambda _snapshot: None
        home = SimpleNamespace(in_town=True, store=SimpleNamespace(
            store_type=STORE_HOME, items=(),
        ))
        for _ in range(EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT - 1):
            self.assertFalse(session.observe(unchanged_home))
            self.assertEqual(policy._equipment_transaction_home_key(home), "\x1b")
            self.assertIs(policy._equipment_transaction_session, session)

        self.assertFalse(session.observe(unchanged_home))
        self.assertEqual(policy._equipment_transaction_home_key(home), "\x1b")
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:confirmation-stall-bound",
        )
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertIn(item_id, policy._equipment_transaction_failed_items)
        failure = policy.equipment_optimization_state()["transaction_last_failure"]
        self.assertFalse(failure["applied"])
        self.assertEqual(failure["item_id"], item_id)
        self.assertEqual(failure["bound"], "STORE_STUCK_LIMIT")
        self.assertEqual(
            failure["observations"], EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
        )

        # The next planning pass retains the durable catalog target but cannot
        # silently recreate the identical visit-quarantined action.
        self.assertIsNone(policy._equipment_transaction_home_key(home))
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertIn(item_id, policy._equipment_transaction_failed_items)

    def test_confirmation_inside_store_stuck_budget_completes_normally(self):
        identity = "slow-valid-item"
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "deposit", "pack:slow-valid-item:0",
            item_identity=identity,
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
        )
        before = EquipmentTransactionObservation.create(
            in_home=True, pack_identities=(identity,),
        )
        self.assertTrue(session.dispatch(action, before))
        for _ in range(EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT - 1):
            self.assertFalse(session.observe(before))
        self.assertTrue(session.observe(EquipmentTransactionObservation.create(
            in_home=False,
        )))
        self.assertTrue(session.complete)

        policy = HengbotPolicy()
        policy._equipment_transaction_session = session
        self.assertFalse(policy._release_stalled_equipment_transaction())
        self.assertIsNone(policy._equipment_transaction_last_failure)

    def test_departure_retains_target_during_home_shield_withdraw_stall(self):
        """Live shape: the optimal main hand is on; Home sub hand never moves."""
        main = gear("main", "equipped", slot="main_hand")
        shield = gear("shield", "home", slot="sub_hand", tval=34)
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", shield.id,
            item_identity=equipment_identity(shield.item),
        )
        pending_plan = EquipmentTransactionPlan((action,), (), 1)
        achieved_plan = EquipmentTransactionPlan((), (), 1)
        current = Loadout((("main_hand", main),), "one_handed")
        pending = WarriorOptimizationPreparation(
            current, None, pending_plan, (),
        )
        achieved = WarriorOptimizationPreparation(
            current, None, achieved_plan, (),
        )
        policy = HengbotPolicy()
        session = EquipmentTransactionSession(
            pending_plan, max_unconfirmed_observations=3,
        )
        before = observe_equipment_transactions(SimpleNamespace(
            inventory=(), equipment=(main.item,), store=SimpleNamespace(
                store_type=STORE_HOME,
            ),
        ))
        self.assertTrue(session.dispatch(action, before))
        policy._equipment_transaction_session = session
        policy._equipment_optimization_preparation = pending
        policy._prepare_equipment_optimization = lambda _snapshot: (
            pending if policy._equipment_transaction_session is not None else achieved
        )
        snapshot = SimpleNamespace(
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
            inventory=(), equipment=(),
        )

        self.assertFalse(policy._equipment_departure_ready(snapshot))
        session.observe(before)
        self.assertFalse(policy._equipment_departure_ready(snapshot))
        session.observe(before)
        self.assertFalse(policy._equipment_departure_ready(snapshot))
        session.observe(before)
        self.assertFalse(policy._equipment_departure_ready(snapshot))
        self.assertNotIn(shield.id, policy._equipment_transaction_failed_items)
        self.assertIs(policy._equipment_transaction_session, session)

    def test_departure_is_immediate_for_already_optimal_loadout(self):
        policy = HengbotPolicy()
        light = gear("light", "equipped", slot="light", tval=39)
        snapshot = SimpleNamespace(
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
            inventory=(), equipment=(light.item,),
        )
        policy._equipment_catalog.refresh_carried((), snapshot.equipment)
        current = current_loadout(policy._equipment_catalog.items)
        prepared = WarriorOptimizationPreparation(
            current, SimpleNamespace(best=SimpleNamespace(loadout=current)),
            EquipmentTransactionPlan((), (), 0), (),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: prepared
        self.assertTrue(policy._equipment_departure_ready(snapshot))

    def test_failed_uncomposable_transaction_opens_equipment_departure_conjunct(self):
        policy = HengbotPolicy()
        worn = gear("worn", "equipped", slot="main_hand")
        failed = gear("failed", "pack", slot="b")
        snapshot = SimpleNamespace(
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
            inventory=(failed.item,), equipment=(worn.item,),
        )
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        current = current_loadout(policy._equipment_catalog.items)
        target = Loadout((("main_hand", failed),), "one_handed")
        preparation = WarriorOptimizationPreparation(
            current,
            self._result_for(target),
            None,
            ("equipment-transaction-failed",),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: preparation
        policy._equipment_optimizer_input_key = "a" * 64
        policy._confirmed_loadout = ConfirmedLoadoutRecord(
            current.item_ids, policy._equipment_optimizer_input_key
        )
        policy._confirmed_loadout_loaded = True
        policy._home_owner_goal_pending = lambda _snapshot: False
        policy._shopping_approach_step = lambda _snapshot, _store: None

        conjuncts = {
            "equipment_departure_ready": policy._equipment_departure_ready(snapshot)
        }

        self.assertTrue(conjuncts["equipment_departure_ready"])

    def test_retired_failure_freezes_worn_target_across_optimizer_rebuild(self):
        policy = HengbotPolicy()
        worn = gear("worn", "equipped", slot="main_hand")
        failed = gear("failed", "pack", slot="b")
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, race_id=1, personality_id=1,
            level=10, stat_cur=(18, 10, 10, 18),
            stat_use=(18, 10, 10, 18), abilities=frozenset(), ac=0,
            speed=110, melee_skill=50, shooting_skill=40, saving_skill=20,
            shield_skill=0, two_weapon_skill=0, max_hp=100, max_mp=0,
        )
        snapshot = SimpleNamespace(
            player=player, inventory=(failed.item,), equipment=(worn.item,),
            in_town=True,
        )
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        current = current_loadout(policy._equipment_catalog.items)
        target = Loadout((("main_hand", failed),), "one_handed")
        policy._equipment_optimization_preparation = WarriorOptimizationPreparation(
            current,
            self._result_for(target),
            None,
            ("equipment-transaction-failed",),
        )
        policy._equipment_transaction_failed_items.add(failed.id)
        policy._equipment_optimizer_input_key = "a" * 64
        policy._confirmed_loadout = ConfirmedLoadoutRecord(
            current.item_ids, policy._equipment_optimizer_input_key
        )
        policy._confirmed_loadout_loaded = True
        policy._character_calibration = seed_calibration(
            snapshot, policy._equipment_catalog.items
        )
        policy._character_calibration_loaded = True
        policy._home_owner_goal_pending = lambda _snapshot: False
        policy._shopping_approach_step = lambda _snapshot, _store: None

        self.assertTrue(policy._retire_actionless_equipment_failure(snapshot))
        rebuilt = policy._prepare_equipment_optimization(snapshot)

        self.assertEqual(rebuilt.result.best.loadout.item_ids, current.item_ids)
        self.assertEqual(rebuilt.transaction.actions, ())
        self.assertFalse(policy._outstanding_equipment_work())
        self.assertTrue(policy._equipment_departure_ready(snapshot))
        self.assertFalse(policy._outstanding_equipment_work())

    def test_timeout_keeps_confirmed_loadout_but_requires_its_premise(self):
        policy = HengbotPolicy()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy._confirmed_loadout_path = Path(directory.name) / "confirmed-loadout.json"
        light = gear("light", "equipped", slot="light", tval=39)
        snapshot = SimpleNamespace(
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
            inventory=(), equipment=(light.item,),
        )
        policy._equipment_catalog.refresh_carried((), snapshot.equipment)
        current = current_loadout(policy._equipment_catalog.items)
        timed_out = WarriorOptimizationPreparation(
            current, SimpleNamespace(best=SimpleNamespace(loadout=current)),
            None, ("optimization-timeout",),
        )
        complete = WarriorOptimizationPreparation(
            current, SimpleNamespace(best=SimpleNamespace(loadout=current)),
            EquipmentTransactionPlan((), (), 0), (),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: complete
        policy._equipment_optimizer_input_key = "0" * 64
        self.assertTrue(policy._equipment_departure_ready(snapshot))
        policy._prepare_equipment_optimization = lambda _snapshot: timed_out
        policy._equipment_optimization_timed_out_this_visit = True
        self.assertTrue(policy._equipment_departure_ready(snapshot))

        policy._equipment_transaction_session = SimpleNamespace(executable=True)
        self.assertFalse(policy._equipment_departure_ready(snapshot))

        policy._equipment_transaction_session = None
        timed_out = WarriorOptimizationPreparation(
            current, None, None, ("optimization-timeout",),
        )
        self.assertFalse(policy._equipment_departure_ready(snapshot))
        stripped = SimpleNamespace(
            player=snapshot.player, inventory=(), equipment=(),
        )
        self.assertFalse(policy._equipment_departure_ready(stripped))

    def test_confirmed_loadout_survives_restart_and_is_input_key_bound(self):
        light = gear("light", "equipped", slot="light", tval=39)
        player_state = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, race_id=1, personality_id=2,
            stat_max=(18, 17, 16, 15, 14, 13),
        )
        snapshot = SimpleNamespace(
            player=player_state, inventory=(), equipment=(light.item,), turn=500,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "confirmed-loadout.json"
            policy = HengbotPolicy()
            policy._confirmed_loadout_path = path
            policy._equipment_catalog.refresh_carried((), snapshot.equipment)
            current = current_loadout(policy._equipment_catalog.items)
            complete = WarriorOptimizationPreparation(
                current, SimpleNamespace(best=SimpleNamespace(loadout=current)),
                EquipmentTransactionPlan((), (), 0), (),
            )
            policy._prepare_equipment_optimization = lambda _snapshot: complete
            policy._equipment_optimizer_input_key = "0" * 64
            self.assertTrue(policy._equipment_departure_ready(snapshot))
            self.assertTrue(path.is_file())

            timeout = WarriorOptimizationPreparation(
                current, SimpleNamespace(best=None), None,
                ("optimization-timeout",),
            )
            restarted = HengbotPolicy()
            restarted._confirmed_loadout_path = path
            restarted._equipment_catalog.refresh_carried((), snapshot.equipment)
            restarted._prepare_equipment_optimization = lambda _snapshot: timeout
            restarted._equipment_optimizer_input_key = "0" * 64
            restarted._equipment_optimization_timed_out_this_visit = True
            self.assertTrue(restarted._equipment_departure_ready(snapshot))

            strengthened = SimpleNamespace(
                player=SimpleNamespace(
                    **{
                        **vars(player_state),
                        "stat_max": (19, *player_state.stat_max[1:]),
                    }
                ),
                inventory=(), equipment=(light.item,), turn=501,
            )
            self.assertTrue(restarted._equipment_departure_ready(strengthened))

            blade = gear("blade", "pack", tval=23).item
            grown_catalog = SimpleNamespace(
                player=player_state, inventory=(blade,),
                equipment=(light.item,), turn=502,
            )
            restarted._equipment_catalog.refresh_carried(
                grown_catalog.inventory, grown_catalog.equipment
            )
            restarted._equipment_optimizer_input_key = "1" * 64
            self.assertFalse(restarted._equipment_departure_ready(grown_catalog))

            stripped = SimpleNamespace(
                player=player_state, inventory=(), equipment=(), turn=501,
            )
            restarted._equipment_catalog.refresh_carried((), ())
            self.assertFalse(restarted._equipment_departure_ready(stripped))

            other_character = SimpleNamespace(
                player=SimpleNamespace(
                    class_id=PLAYER_CLASS_WARRIOR, race_id=9, personality_id=2,
                    stat_max=player_state.stat_max,
                ),
                inventory=(), equipment=(light.item,), turn=1,
            )
            fresh = HengbotPolicy()
            fresh._confirmed_loadout_path = path
            fresh._equipment_catalog.refresh_carried((), other_character.equipment)
            fresh._prepare_equipment_optimization = lambda _snapshot: timeout
            fresh._equipment_optimizer_input_key = "1" * 64
            self.assertFalse(fresh._equipment_departure_ready(other_character))
            self.assertTrue(path.is_file(), "an identity mismatch must not unlink")

            successor = HengbotPolicy()
            successor._confirmed_loadout_path = path
            successor._equipment_catalog.refresh_carried((), snapshot.equipment)
            successor._prepare_equipment_optimization = lambda _snapshot: timeout
            successor._equipment_optimizer_input_key = "0" * 64
            successor._equipment_optimization_timed_out_this_visit = True
            clone = SimpleNamespace(
                player=player_state, inventory=(), equipment=(light.item,),
                turn=5001,
            )
            self.assertTrue(successor._equipment_departure_ready(clone))

    def test_confirmed_loadout_old_schema_and_hostile_shapes_fail_closed(self):
        old_schema = {
            "race_id": 1,
            "class_id": PLAYER_CLASS_WARRIOR,
            "personality_id": 2,
            "confirmed_turn": 500,
            "item_ids": ["equipped:light"],
            "catalog_item_ids": ["equipped:light"],
        }
        hostile = (
            old_schema,
            {},
            {"item_ids": [], "optimizer_input_key": "0" * 64},
            {"item_ids": ["equipped:light"], "optimizer_input_key": None},
            {"item_ids": ["equipped:light"], "optimizer_input_key": "z" * 64},
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "confirmed-loadout.json"
            for data in hostile:
                with self.subTest(data=data):
                    path.write_text(json.dumps(data), encoding="utf-8")
                    self.assertIsNone(load_confirmed_loadout(path))
            path.write_text("not json", encoding="utf-8")
            self.assertIsNone(load_confirmed_loadout(path))

    def test_confirmed_loadout_round_trips_new_input_key_schema(self):
        record = ConfirmedLoadoutRecord(
            frozenset({"equipped:weapon", "equipped:light"}), "a" * 64
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "confirmed-loadout.json"
            self.assertTrue(save_confirmed_loadout(path, record))
            self.assertEqual(load_confirmed_loadout(path), record)

    def test_optimizer_input_key_covers_search_and_planner_inputs(self):
        light = gear("light", "equipped", slot="light", tval=39)
        weapon = gear("weapon", "equipped", slot="main_hand")
        home = gear("home-upgrade", "home", to_d=20)
        player = SimpleNamespace(
            race_id=1, class_id=PLAYER_CLASS_WARRIOR, personality_id=2,
            stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18),
            level=10, shield_skill=0, speed=110, saving_skill=30,
            abilities=frozenset(), ac=0, melee_skill=60, shooting_skill=50,
            two_weapon_skill=0, max_hp=100, max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        calibration = seed_calibration(snapshot, (light, weapon))
        monster = MonraceKnowledge(
            20, 110, False, False, level=1, average_hp=20,
            armor_class=0, rarity=1,
        )

        def key(**changes):
            arguments = {
                "snapshot": snapshot,
                "items": (light, weapon),
                "knowledge": {1: monster},
                "depth": 1,
                "home_scan_complete": True,
                "has_destruction": False,
                "preserve_pack_item_ids": frozenset(),
                "search_excluded_item_ids": frozenset(),
                "calibration": calibration,
            }
            arguments.update(changes)
            return warrior_optimizer_input_key(**arguments)

        baseline = key()
        variants = (
            key(items=(light, weapon, home)),
            key(knowledge={1: replace(monster, max_hp=21)}),
            key(depth=20),
            key(home_scan_complete=False),
            key(has_destruction=True),
            key(preserve_pack_item_ids=frozenset({weapon.id})),
            key(search_excluded_item_ids=frozenset({weapon.id})),
            key(calibration=replace(
                calibration, observed_turn=calibration.observed_turn + 1,
            )),
            key(snapshot=SimpleNamespace(
                player=SimpleNamespace(**{**vars(player), "level": 11}),
                inventory=(),
            )),
            key(snapshot=SimpleNamespace(player=player, inventory=(light.item,))),
        )
        self.assertTrue(all(candidate != baseline for candidate in variants))

    def test_optimizer_input_key_ignores_transport_noise_and_catalog_order(self):
        light = gear("light", "equipped", slot="light", tval=39)
        light = replace(light, item=replace(light.item, fuel=5000))
        weapon = gear("weapon", "pack")
        player = SimpleNamespace(
            race_id=1, class_id=PLAYER_CLASS_WARRIOR, personality_id=2,
            stat_cur=(18, 10, 10, 18), level=10, shield_skill=0,
            speed=110, saving_skill=30, melee_skill=60, shooting_skill=50,
            two_weapon_skill=0, max_hp=100, max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())

        def key(items):
            return warrior_optimizer_input_key(
                snapshot, tuple(items), {}, depth=1, home_scan_complete=True,
                has_destruction=False, preserve_pack_item_ids=frozenset(),
                search_excluded_item_ids=frozenset(), calibration=None,
            )

        baseline = key((light, weapon))
        noisy_light = replace(
            light,
            item=replace(
                light.item, slot="z", name="Lantern (4999 turns of light)",
                fuel=4999, timeout=7, inscription="keep", is_bounty=True,
            ),
        )
        noisy_weapon = replace(
            weapon,
            item=replace(
                weapon.item, slot="y", timeout=9, inscription="{keep}",
                is_bounty=True,
            ),
        )

        self.assertEqual(key((noisy_light, noisy_weapon)), baseline)
        self.assertEqual(key((weapon, light)), baseline)

    def test_optimizer_input_key_orders_duplicate_ids_without_comparing_payloads(self):
        light = gear("duplicate", "equipped", slot="light", tval=39)
        weapon = replace(
            gear("duplicate", "equipped"),
            id=light.id,
        )
        player = SimpleNamespace(
            race_id=1, class_id=PLAYER_CLASS_WARRIOR, personality_id=2,
            stat_cur=(18, 10, 10, 18), level=10, shield_skill=0,
            speed=110, saving_skill=30, melee_skill=60, shooting_skill=50,
            two_weapon_skill=0, max_hp=100, max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())

        digest = warrior_optimizer_input_key(
            snapshot, (light, weapon), {}, depth=1,
            home_scan_complete=True, has_destruction=False,
            preserve_pack_item_ids=frozenset(),
            search_excluded_item_ids=frozenset(), calibration=None,
        )

        self.assertEqual(len(digest), 64)

    def test_optimizer_input_key_tracks_each_extended_item_semantic(self):
        weapon = gear("weapon", "pack")
        player = SimpleNamespace(
            race_id=1, class_id=PLAYER_CLASS_WARRIOR, personality_id=2,
            stat_cur=(18, 10, 10, 18), level=10, shield_skill=0,
            speed=110, saving_skill=30, melee_skill=60, shooting_skill=50,
            two_weapon_skill=0, max_hp=100, max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())

        def key(owned):
            return warrior_optimizer_input_key(
                snapshot, (owned,), {}, depth=1, home_scan_complete=True,
                has_destruction=False, preserve_pack_item_ids=frozenset(),
                search_excluded_item_ids=frozenset(), calibration=None,
            )

        baseline = key(weapon)
        variants = (
            replace(weapon, id="other"),
            replace(weapon, origin="home"),
            replace(weapon, equipped_slot="main_hand"),
            replace(weapon, random_teleport_suppressed=True),
            replace(weapon, item=replace(weapon.item, weight=31)),
            replace(weapon, item=replace(weapon.item, weapon_proficiency=1)),
            replace(weapon, item=replace(weapon.item, pseudo_feeling="average")),
            replace(weapon, item=replace(weapon.item, is_equipment=False)),
        )
        self.assertTrue(all(key(candidate) != baseline for candidate in variants))


if __name__ == "__main__":
    unittest.main()
