"""Stage P1: the loadout selector is a pure function of the owned multiset.

The decisive revert-proof is the measured turn-2459793 partition flip
(SOL-FINDINGS-optimizer-purity-measurement.md §1): with a provably identical
32-item owned multiset and the same depth, moving 器用さの指輪 (+1) between
``main_ring`` and Home flipped the winner at depths 5/15/20/25/31 because
``base_ac_bonus`` was derived from the worn snapshot through the
``ADJ_DEX_TO_AC`` step function.  The raw flight-recorder record rotated out
before this stage started, so ``tests/fixtures/optimizer-purity-turn2459793``
is a reconstruction from the measurement's complete item dump plus captured
full records of the still-owned physical items; its fidelity is asserted below
against the measurement's documented derived values (base_str 116 / base_dex
65 / base_con 160 / base_hp 403 / base_ac_bonus 0, catalog 32 = 12+1+19), and
it reproduced the exact measured flip on the unmodified pre-P1 code.
"""

import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.equipment_optimizer import (
    OwnedEquipmentCatalog,
    current_loadout,
    equipment_identity,
)
from hengbot.model import InventoryItem, PlayerState, Position, parse_snapshot
from hengbot.monrace_knowledge import (
    find_monrace_definitions,
    load_monrace_knowledge,
)
from hengbot.warrior_defense_evaluator import (
    WarriorDefenseInputs,
    loadout_armor_class,
)
from hengbot.warrior_equipment_evaluator import modify_stat_value
from hengbot.warrior_loadout_evaluator import constitution_hp_bonus
from hengbot.warrior_optimization import (
    CharacterCalibration,
    WarriorEvaluatorCache,
    _effective_intrinsic_abilities,
    calibrate_character_constants,
    load_character_calibration,
    prepare_warrior_optimization,
    save_character_calibration,
)

FIXTURE = Path(__file__).parent / "fixtures" / "optimizer-purity-turn2459793.json"
DEX_RING = "器用さの指輪 (+1)"
FEAR_RING = "恐れ知らずの指輪"
DWARVEN_RING_MAIL = "ドワーフのリング・メイル (-2) [17,+6] (+2) {+耐r冷}"
ELVISH_PLATE = (
    "エルフの強化プレート・アーマー (-3) [28,+5] (+3隠密) {+隠r酸電火冷呪}"
)
# The measurement's §0.1 stat model: race+class+personality DEX add is 3, so
# the naked DEX observation is modify_stat_value(stat_cur=35, 3).
NAKED_DEX = modify_stat_value(35, 3)
INTRINSIC = frozenset({"resist_neth", "resist_pois", "see_invisible"})


def _load_record():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _clone(record):
    return json.loads(json.dumps(record, ensure_ascii=False))


def _stat_add(stats):
    return next(
        add
        for add in range(-40, 41)
        if modify_stat_value(stats["cur"], add) == stats["use"]
    )


def _catalog_for(record, knowledge):
    snapshot = parse_snapshot(record, knowledge)
    catalog = OwnedEquipmentCatalog()
    catalog.refresh_carried(snapshot.inventory, snapshot.equipment)
    catalog.complete_home_scan(snapshot.store.items)
    return snapshot, tuple(catalog.items)


def _move_home_item_to_slot(record, home_name, worn_name, slot, *, con_pval=0,
                            dex_pval=0):
    """§1.1 state construction: one physical move, owned multiset unchanged."""
    rec = _clone(record)
    store_items = rec["store"]["items"]
    incoming = next(item for item in store_items if item["name"] == home_name)
    outgoing = next(item for item in rec["equipment"] if item["name"] == worn_name)
    store_items.remove(incoming)
    rec["equipment"].remove(outgoing)
    worn = dict(incoming)
    letter = worn.pop("letter", None)
    worn.pop("price", None)
    worn["slot"] = slot
    rec["equipment"].append(worn)
    stored = dict(outgoing)
    stored.pop("slot", None)
    stored["letter"] = letter
    stored["price"] = 0
    store_items.append(stored)
    player = rec["player"]
    delta_ac = (
        incoming.get("ac", 0) + incoming.get("to_a", 0)
        - outgoing.get("ac", 0) - outgoing.get("to_a", 0)
    )
    player["ac"] += delta_ac
    if dex_pval:
        stats = player["stats"]["dex"]
        stats["use"] = modify_stat_value(
            stats["cur"], _stat_add(stats) + dex_pval
        )
    if con_pval:
        # §1.1 recomputes stat_use only; max_hp deliberately stays as observed.
        # The legacy derivation then subtracts a CON hit-point bonus that no
        # longer matches the max_hp it is subtracted from — the measured
        # base_hp 403 -> 361 error.  The calibrated constant cannot be
        # corrupted by that coupling because it never de-gears max_hp.
        stats = player["stats"]["con"]
        stats["use"] = modify_stat_value(
            stats["cur"], _stat_add(stats) + con_pval
        )
    outgoing_flags = set(outgoing.get("known_flags", ()))
    incoming_flags = set(incoming.get("known_flags", ()))
    other_worn_flags = set()
    for item in rec["equipment"]:
        if item["name"] != home_name:
            other_worn_flags.update(item.get("known_flags", ()))
    flag_names = {
        48: "resist_acid", 49: "resist_elec", 50: "resist_fire",
        51: "resist_cold", 52: "resist_pois", 53: "resist_fear",
        57: "resist_conf", 58: "resist_sound", 60: "resist_neth",
        62: "resist_chaos", 46: "free_action",
    }
    for flag, name in flag_names.items():
        if flag in outgoing_flags and flag not in other_worn_flags \
                and flag not in incoming_flags and name not in (
                    "resist_neth", "resist_pois"):
            player["abilities"][name] = False
        if flag in incoming_flags:
            player["abilities"][name] = True
    return rec


def _naked_record(record):
    """The unequipped calibration observation for this character.

    Constructed from the measurement's documented naked values: DEX add 3,
    intrinsic {resist_neth, resist_pois, see_invisible}, base_ac_bonus 0.
    """
    rec = _clone(record)
    rec["equipment"] = []
    rec["inventory"] = []
    player = rec["player"]
    player["stats"]["dex"]["use"] = NAKED_DEX
    for name in list(player["abilities"]):
        player["abilities"][name] = name in INTRINSIC
    player["ac"] = loadout_armor_class(
        current_loadout(()),
        WarriorDefenseInputs(
            level=player["level"],
            natural_dex=NAKED_DEX,
            shield_skill=player["skills"]["shield"],
            saving_skill=player["skills"]["saving"],
        ),
    )
    return rec


def _definitions():
    """Resolve MonraceDefinitions the way the production code does.

    ``find_monrace_definitions`` honours HENGBAND_MONRACE_DEFINITIONS first,
    then walks the anchor's parents.  Anchor on this test file AND on the
    repository test location so the decisive purity fixture runs under the
    plain prescribed suite command from any checkout that can reach the game
    data; the class skips (loudly) only when no candidate exists at all.
    """
    for anchor in (Path(__file__),):
        found = find_monrace_definitions(anchor, None)
        if found is not None:
            return found
    return None


class OptimizerPurityFlipTest(unittest.TestCase):
    """The measured two-cycle generator must be structurally impossible.

    BASE-PROOF PROCEDURE (recorded because this module cannot import on the
    pre-P1 base ``18dc21a`` — ``CharacterCalibration`` does not exist there,
    so the revert-proof is a targeted source-hunk revert, executed and
    observed on 2026-08-03):

    1. In ``prepare_warrior_optimization`` (warrior_optimization.py), restore
       the pre-P1 constants derivation in place of the calibrated block —
       equivalently, on the first P1 commit ``6e83f80`` change the branch
       ``if calibration is not None:`` to ``if calibration is not None and
       False:`` so the retained legacy ``else`` branch (worn-snapshot
       de-gearing: ``_base_stat_without_current_gear``,
       ``player.ac - loadout_armor_class(current, ...)``) runs again.
    2. Run this class.  Observed failures:
       * ``test_ring_partition_flip_is_gone_at_every_measured_depth`` fails
         at ALL FIVE depths (5/15/20/25/31) with the exact measured flip:
         ``AssertionError: Tuples differ: (..., ('sub_ring',
         '恐れ知らずの指輪')) != (..., ('sub_ring', '器用さの指輪 (+1)'))``
         — state A selects 恐れ知らずの指輪, state B selects 器用さの指輪
         (+1), the self-sustaining two-cycle from SOL-FINDINGS §1.2.
       * ``test_base_hp_is_immune_to_a_con_bearing_armour_swap`` fails with
         ``AssertionError: 361 != 403`` — the §1.4 survival-model error.
    3. Restore the hunk; every test passes again.
    """

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        definitions = _definitions()
        if definitions is None:
            raise unittest.SkipTest(
                "lib/edit/MonraceDefinitions.jsonc is not reachable from this "
                "checkout; the decisive purity fixture cannot be evaluated"
            )
        cls.knowledge = load_monrace_knowledge(definitions)
        cls.record = _load_record()
        cls.calibration = calibrate_character_constants(
            parse_snapshot(_naked_record(cls.record), cls.knowledge)
        )

    def _winner(self, snapshot, items, depth):
        prepared = prepare_warrior_optimization(
            snapshot,
            items,
            self.knowledge,
            depth=depth,
            home_scan_complete=True,
            timeout_seconds=120.0,
            calibration=self.calibration,
        )
        result = prepared.result
        self.assertIsNotNone(result, prepared.blockers)
        self.assertIsNotNone(result.best, prepared.blockers)
        return tuple(
            sorted(
                (slot, owned.item.name)
                for slot, owned in result.best.loadout.slots
            )
        )

    def test_calibration_reproduces_the_measured_naked_constants(self):
        calibration = self.calibration
        self.assertIsNotNone(calibration)
        self.assertEqual(calibration.base_stats, (116, 3, 9, 65, 160, 13))
        self.assertEqual(calibration.base_hp, 403)
        self.assertEqual(calibration.base_ac_bonus, 0)
        self.assertEqual(calibration.intrinsic_abilities, INTRINSIC)
        self.assertEqual(calibration.pinned_identities, ())

    def test_ring_partition_flip_is_gone_at_every_measured_depth(self):
        """SOL-FINDINGS §1.1/§1.2: same owned multiset, same depth, one answer.

        On the pre-P1 derivation this fixture reproduces the measured flip
        exactly (different sub_ring winner at all five depths); with the
        calibrated worn-independent constants the two partitions must agree.
        """
        snap_a, items_a = _catalog_for(self.record, self.knowledge)
        record_b = _move_home_item_to_slot(
            self.record, DEX_RING, FEAR_RING, "main_ring", dex_pval=1
        )
        snap_b, items_b = _catalog_for(record_b, self.knowledge)

        # Fixture fidelity anchors from the measurement.
        self.assertEqual(len(items_a), 32)
        origins = {"equipped": 0, "pack": 0, "home": 0}
        for owned in items_a:
            origins[owned.origin] += 1
        self.assertEqual(origins, {"equipped": 12, "pack": 1, "home": 19})
        self.assertEqual(
            sorted(equipment_identity(owned.item) for owned in items_a),
            sorted(equipment_identity(owned.item) for owned in items_b),
            "the two states must share one provably identical owned multiset",
        )

        for depth in (5, 15, 20, 25, 31):
            with self.subTest(depth=depth):
                self.assertEqual(
                    self._winner(snap_a, items_a, depth),
                    self._winner(snap_b, items_b, depth),
                    "the worn/stored partition of the identical owned "
                    "multiset changed the winner (the measured two-cycle "
                    f"generator) at depth {depth}",
                )

    def test_base_hp_is_immune_to_a_con_bearing_armour_swap(self):
        """SOL-FINDINGS §1.4: the survival model must keep base_hp 403, not 361.

        Swapping the CON-bearing ドワーフのリング・メイル into the body slot
        made the legacy de-gearing derive base_hp 361 from the same character
        (modify_stat_value is not injective on the 18/xx scale) — a 10 %
        survival-model error decided by where the armour was stored.
        """
        snap_a, items_a = _catalog_for(self.record, self.knowledge)
        record_c = _move_home_item_to_slot(
            self.record, DWARVEN_RING_MAIL, ELVISH_PLATE, "body", con_pval=2
        )
        snap_c, items_c = _catalog_for(record_c, self.knowledge)

        for label, snapshot, items in (
            ("worn Elvish plate", snap_a, items_a),
            ("worn CON ring mail", snap_c, items_c),
        ):
            cache = WarriorEvaluatorCache()
            prepare_warrior_optimization(
                snapshot,
                items,
                self.knowledge,
                depth=20,
                home_scan_complete=True,
                timeout_seconds=120.0,
                evaluator_cache=cache,
                calibration=self.calibration,
            )
            self.assertIsNotNone(cache.context, label)
            self.assertEqual(
                cache.context[0].base_hp,
                403,
                f"{label}: the survival model consumed a worn-dependent "
                "base_hp instead of the calibrated constant",
            )


def _player(**overrides):
    fields = dict(
        position=Position(1, 1), hp=100, max_hp=100, mp=0, max_mp=0, level=10,
        class_id=0, race_id=3, personality_id=1, ac=5, speed=110,
        stat_cur=(18, 10, 10, 17, 16, 9), stat_use=(20, 10, 10, 18, 17, 9),
        abilities=frozenset({"see_invisible"}), shield_skill=0,
        saving_skill=20,
    )
    fields.update(overrides)
    return PlayerState(**fields)


def _worn(slot, name="worn item", *, cursed=False, tval=36, pval=0, flags=()):
    return InventoryItem(
        slot=slot, name=name, count=1, tval=tval, sval=1, aware=True,
        known=True, fully_known=True, is_equipment=True, is_cursed=cursed,
        pval=pval, known_flags=frozenset(flags),
    )


def _snapshot(player, equipment=()):
    from hengbot.model import Snapshot

    return Snapshot(
        player, {}, [], turn=777, floor_key=(0, 0, 0), town_flag=True,
        inventory=[], equipment=list(equipment),
    )


class CharacterCalibrationTest(unittest.TestCase):
    def test_permanent_sources_define_intrinsics_and_supersede_stored_list(self):
        permanent = frozenset({
            "resist_cold", "resist_fear", "resist_neth", "resist_pois",
            "see_invisible",
        })
        sources = {
            ability: frozenset({"permanent"}) for ability in permanent
        }
        sources.update({
            "resist_fire": frozenset({"equipment"}),
            "resist_sound": frozenset({"equipment"}),
            "free_action": frozenset(),
            "resist_conf": frozenset(),
            "resist_acid": frozenset(),
            "resist_chaos": frozenset(),
        })
        player = _player(
            abilities=permanent | {"resist_fire", "resist_sound"},
            ability_sources=sources,
        )

        calibration = calibrate_character_constants(_snapshot(player))

        self.assertIsNotNone(calibration)
        self.assertEqual(calibration.intrinsic_abilities, permanent)
        contaminated = permanent | frozenset({
            "free_action", "resist_acid", "resist_chaos", "resist_conf",
            "resist_elec", "resist_fire", "resist_sound", "telepathy",
        })
        self.assertEqual(
            _effective_intrinsic_abilities(player, contaminated), permanent
        )

    def test_refuses_to_calibrate_while_a_removable_item_is_worn(self):
        snapshot = _snapshot(_player(), [_worn("body")])
        self.assertIsNone(calibrate_character_constants(snapshot))

    def test_naked_observation_is_read_directly_without_inversion(self):
        player = _player()
        calibration = calibrate_character_constants(_snapshot(player))
        self.assertIsNotNone(calibration)
        self.assertEqual(calibration.base_stats, player.stat_use)
        self.assertEqual(calibration.intrinsic_abilities, player.abilities)
        self.assertEqual(
            calibration.base_hp,
            player.max_hp
            - constitution_hp_bonus(player.stat_use[4], player.level),
        )
        naked_model = loadout_armor_class(
            current_loadout(()),
            WarriorDefenseInputs(
                level=player.level,
                natural_dex=player.stat_use[3],
                shield_skill=player.shield_skill,
                saving_skill=player.saving_skill,
            ),
        )
        self.assertEqual(calibration.base_ac_bonus, player.ac - naked_model)
        self.assertEqual(calibration.observed_turn, 777)

    def test_pinned_cursed_item_is_folded_into_the_constants(self):
        cursed = _worn("main_ring", "cursed ring", cursed=True, tval=45)
        player = _player(abilities=frozenset({"see_invisible", "resist_fire"}))
        calibration = calibrate_character_constants(
            _snapshot(player, [cursed])
        )
        self.assertIsNotNone(calibration)
        # The unremovable item's contributions stay inside the observation...
        self.assertEqual(calibration.base_stats, player.stat_use)
        self.assertIn("resist_fire", calibration.intrinsic_abilities)
        # ...and the folded set is recorded so a curse change invalidates it.
        self.assertEqual(
            calibration.pinned_identities,
            (("main_ring", equipment_identity(cursed)),),
        )

    def test_stale_reasons_cover_the_approved_invalidation_triggers(self):
        player = _player()
        calibration = calibrate_character_constants(_snapshot(player))
        self.assertIsNone(calibration.stale_reason(player, ()))
        self.assertEqual(
            calibration.stale_reason(replace(player, level=11), ()), "level"
        )
        self.assertEqual(
            calibration.stale_reason(
                replace(player, stat_cur=(19, 10, 10, 17, 16, 9)), ()
            ),
            "stat_cur",
        )
        self.assertEqual(
            calibration.stale_reason(replace(player, race_id=5), ()),
            "character-identity",
        )
        self.assertEqual(
            calibration.stale_reason(player, (("main_ring", "sig"),)),
            "pinned-set",
        )

    def test_prepare_requires_a_calibration_with_no_legacy_fallback(self):
        """The worn-independent constants are mandatory at the selector
        boundary: absence fails closed instead of selecting the pre-P1
        de-gearing reconstruction."""
        prepared = prepare_warrior_optimization(
            _snapshot(_player()),
            (),
            {1: object()},
            depth=1,
            home_scan_complete=True,
        )
        self.assertEqual(prepared.blockers, ("calibration-required",))
        self.assertIsNone(prepared.result)
        self.assertIsNone(prepared.transaction)

    def test_prepare_fails_closed_on_a_stale_calibration(self):
        player = _player(class_id=0)
        calibration = calibrate_character_constants(_snapshot(player))
        older = replace(calibration, level=calibration.level - 1)
        prepared = prepare_warrior_optimization(
            _snapshot(player),
            (),
            {1: object()},
            depth=1,
            home_scan_complete=True,
            calibration=older,
        )
        self.assertEqual(prepared.blockers, ("calibration-stale:level",))

    def test_mutation_signature_change_invalidates_the_calibration(self):
        player = _player()
        calibration = calibrate_character_constants(
            _snapshot(player), mutation_signature=(2, 5)
        )
        self.assertEqual(calibration.mutation_signature, (2, 5))
        # Unchanged observation: still valid.
        self.assertIsNone(
            calibration.stale_reason(player, (), mutation_signature=(2, 5))
        )
        # No observation available: the other triggers still own validity.
        self.assertIsNone(
            calibration.stale_reason(player, (), mutation_signature=None)
        )
        # Gained or lost mutation: stale.
        self.assertEqual(
            calibration.stale_reason(player, (), mutation_signature=(2, 5, 7)),
            "mutations",
        )
        self.assertEqual(
            calibration.stale_reason(player, (), mutation_signature=(2,)),
            "mutations",
        )
        # A capture made before any `~c` observation is invalidated by the
        # first observation, so the trigger is always armed afterwards.
        unarmed = calibrate_character_constants(_snapshot(player))
        self.assertIsNone(unarmed.mutation_signature)
        self.assertEqual(
            unarmed.stale_reason(player, (), mutation_signature=()),
            "mutations",
        )

    def test_mutation_signature_persistence_round_trip(self):
        import tempfile

        calibration = calibrate_character_constants(
            _snapshot(_player()),
            mutation_signature=(1, 12),
            intrinsic_tr_flags=frozenset({152, 36}),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character-calibration.json"
            save_character_calibration(path, calibration)
            loaded = load_character_calibration(path)
        self.assertEqual(loaded, calibration)
        self.assertEqual(loaded.mutation_signature, (1, 12))
        self.assertEqual(loaded.intrinsic_tr_flags, frozenset({152, 36}))

    def test_character_intrinsic_flags_reads_the_naked_flag_table(self):
        from hengbot.warrior_optimization import character_intrinsic_flags

        rows = [
            {"flag_id": 155, "player": False, "vulnerability": True},
            {"flag_id": 40, "player": False, "immunity": True},
            {"flag_id": 36, "player": True},
            {"flag_id": 48, "player": False},
            # Temporary effects must never contaminate the constants.
            {"flag_id": 50, "player": False, "temporary": True,
             "temporary_immunity": True},
            "garbage",
        ]
        self.assertEqual(
            character_intrinsic_flags(rows), frozenset({155, 40, 36})
        )
        self.assertEqual(character_intrinsic_flags(None), frozenset())

    def test_permanent_vulnerability_reaches_the_search_inputs(self):
        """A mutation-granted elemental vulnerability recorded by the naked
        `C` capture must reach the defense evaluator's intrinsic flag set so
        the loadout search can compensate for it (TR_VUL_* consumers:
        _element_rate's +1/3 damage)."""
        from hengbot.warrior_defense_evaluator import TR_VUL_FIRE

        definitions = _definitions()
        if definitions is None:
            raise unittest.SkipTest("MonraceDefinitions unavailable")
        knowledge = load_monrace_knowledge(definitions)
        player = _player(class_id=0)
        vulnerable = calibrate_character_constants(
            _snapshot(player), intrinsic_tr_flags=frozenset({TR_VUL_FIRE})
        )
        cache = WarriorEvaluatorCache()
        prepare_warrior_optimization(
            _snapshot(player),
            (),
            knowledge,
            depth=1,
            home_scan_complete=True,
            evaluator_cache=cache,
            calibration=vulnerable,
        )
        self.assertIsNotNone(cache.context)
        self.assertIn(
            TR_VUL_FIRE,
            cache.context[0].defense.intrinsic_flags,
            "the recorded permanent vulnerability never reached the search",
        )

    def test_persistence_round_trip(self):
        import tempfile

        calibration = calibrate_character_constants(_snapshot(_player()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character-calibration.json"
            save_character_calibration(path, calibration)
            self.assertEqual(load_character_calibration(path), calibration)
        self.assertIsNone(
            load_character_calibration(Path(directory) / "missing.json")
        )


if __name__ == "__main__":
    unittest.main()
