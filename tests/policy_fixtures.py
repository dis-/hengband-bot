"""Shared fixture constructors for policy tests."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.equipment_optimizer import OwnedEquipmentCatalog, current_loadout
from hengbot.model import (
    GridState, InventoryItem, MonsterState, PlayerState, Position, StoreItem,
    SV_LITE_TORCH, TVAL_LITE,
)
from hengbot.policy import (
    FUNDRAISING_START_GOLD, INSCRIBE_KEY, LEAVE_STORE_KEY, WAIT_KEY,
)

def store_item(letter, tval, sval, *, price=100, count=1, name="wares", **kwargs):
    return StoreItem(
        letter=letter,
        name=name,
        count=count,
        tval=tval,
        sval=sval,
        price=price,
        **kwargs,
    )


def grid(
    y,
    x,
    *,
    known=True,
    passable=True,
    monster=False,
    downstairs=False,
    upstairs=False,
    closed_door=False,
    open_door=False,
    unsafe=False,
    trap=False,
    objects=0,
    object_tvals=(),
    entrance=False,
    rubble=False,
    gold=False,
    can_dig=False,
    tunnel=False,
    permanent=False,
    entrance_dungeon_id=-1,
    building_type=-1,
    has_quest_enter=False,
    has_quest_exit=False,
    quest_id=-1,
    building_special=-1,
    lit=False,
    in_view=False,
    allows_los=None,
    terrain_id=-1,
    marked=True,
):
    pos = Position(y, x)
    walkable = (passable and not closed_door and not rubble) or open_door
    return GridState(
        position=pos,
        known=known,
        passable=known and walkable,
        wall=known and not passable and not closed_door and not open_door and not rubble,
        has_monster=monster,
        has_down_stairs=downstairs,
        has_up_stairs=upstairs,
        unsafe=unsafe,
        is_closed_door=known and closed_door,
        is_door=known and (closed_door or open_door),
        trap=trap,
        object_count=objects,
        object_tvals=tuple(object_tvals),
        has_entrance=entrance,
        can_dig=known and (rubble or can_dig),
        # Older unit fixtures used can_dig/gold before the emitter exposed the
        # authoritative TUNNEL flag. Preserve their intended terrain while new
        # tests can set tunnel independently of can_dig.
        tunnel=known and (tunnel or rubble or can_dig or gold),
        permanent=known and permanent,
        has_gold=known and gold,
        entrance_dungeon_id=entrance_dungeon_id,
        building_type=building_type,
        has_quest_enter=known and has_quest_enter,
        has_quest_exit=known and has_quest_exit,
        quest_id=quest_id if known else -1,
        building_special=building_special if known else -1,
        lit=known and lit,
        in_view=known and in_view,
        allows_los=(known and walkable) if allows_los is None else allows_los,
        terrain_id=terrain_id,
        marked=marked,
    )


def _public_shop_inner(testcase, policy, snapshot):
    """Assert the public door-composed boundary, returning its inner grammar."""
    store_type = snapshot.store.store_type
    position = snapshot.player.position
    entrance = snapshot.grids.get(position, grid(position.y, position.x))
    observed = replace(
        snapshot,
        grids={
            **snapshot.grids,
            position: replace(entrance, store_number=store_type),
        },
        town_flag=True,
    )
    testcase.assertEqual(policy.choose_key(observed), LEAVE_STORE_KEY)
    outside = replace(observed, store=None, turn=observed.turn + 1)
    composed = policy.choose_key(outside)
    # Outside pack inscription is intentionally not wrapped in a store visit.
    if composed.startswith(INSCRIBE_KEY):
        return composed
    if policy._store_visit is None or not policy._store_visit.operation_posted:
        return composed
    testcase.assertEqual(composed, WAIT_KEY)
    operation = policy.choose_key(replace(observed, turn=outside.turn + 1))
    testcase.assertTrue(operation.endswith(LEAVE_STORE_KEY))
    return operation[:-1]


def player(y, x, *, hp=20, max_hp=20, mp=0, max_mp=0, level=1, food=12000, food_type=0, gold=FUNDRAISING_START_GOLD, word_recall=0, afraid=False, confused=False, blind=False, poisoned=False, cut=False, class_id=-1, main_hand_blows=0, main_hand_to_h=0, main_hand_to_d=0, drained_stats=(), abilities=frozenset(), speed=110):
    if food < 500:
        food_state = "fainting"
    elif food < 1000:
        food_state = "weak"
    elif food < 2000:
        food_state = "hungry"
    elif food < 10000:
        food_state = "normal"
    elif food < 15000:
        food_state = "full"
    else:
        food_state = "gorged"
    return PlayerState(
        Position(y, x),
        hp=hp,
        max_hp=max_hp,
        mp=mp,
        max_mp=max_mp,
        level=level,
        food_state=food_state,
        gold=gold,
        recalling=word_recall > 0,
        food_type=food_type,
        afraid=afraid,
        confused=confused,
        blind=blind,
        poisoned=poisoned,
        cut=cut,
        class_id=class_id,
        main_hand_blows=main_hand_blows,
        main_hand_to_h=main_hand_to_h,
        main_hand_to_d=main_hand_to_d,
        drained_stats=drained_stats,
        abilities=abilities,
        speed=speed,
    )


def item(
    slot,
    tval,
    sval,
    *,
    aware=True,
    known=None,
    fully_known=False,
    count=1,
    name="item",
    charges=0,
    fuel=None,
    is_equipment=False,
    is_ego=False,
    is_artifact=False,
    is_cursed=False,
    inscription="",
    is_broken=False,
    is_bounty=False,
    to_h=0,
    to_d=0,
    to_a=0,
    ac=0,
    pval=0,
    known_flags=frozenset(),
    damage_dice_num=0,
    damage_dice_sides=0,
    pseudo_feeling="",
):
    if known is None:
        known = aware
    if fuel is None:
        fuel = 5000 if tval == TVAL_LITE and sval == SV_LITE_TORCH else 0
    return InventoryItem(
        slot=slot, name=name, count=count, tval=tval, sval=sval, aware=aware,
        known=known, fully_known=fully_known, charges=charges, fuel=fuel,
        is_equipment=is_equipment, is_ego=is_ego, is_artifact=is_artifact,
        is_cursed=is_cursed, inscription=inscription, is_broken=is_broken,
        to_h=to_h, to_d=to_d,
        is_bounty=is_bounty,
        to_a=to_a, ac=ac, pval=pval, known_flags=known_flags,
        damage_dice_num=damage_dice_num,
        damage_dice_sides=damage_dice_sides,
        pseudo_feeling=pseudo_feeling,
    )


def set_known_target(policy):
    preparation = SimpleNamespace(
        # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
        result=SimpleNamespace(
            best=SimpleNamespace(loadout=SimpleNamespace(item_ids=frozenset()))
        )
    )
    policy._equipment_optimization_preparation = preparation
    return preparation


def set_completed_equipment_optimization(policy):
    """Install a known, already-worn zero-action optimizer result."""
    def prepare(snapshot):
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        worn = current_loadout(policy._equipment_catalog.items)
        policy._equipment_optimizer_input_key = "0" * 64
        return SimpleNamespace(
            ready=True,
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=worn)),
            transaction=SimpleNamespace(actions=()),
            blockers=(),
        )

    policy._prepare_equipment_optimization = prepare
    return prepare


def seed_confirmed_loadout(policy, snapshot):
    """Pass a zero-action completion through the production record gate."""
    if policy._confirmed_loadout_path is None:
        directory = TemporaryDirectory()
        policy._test_confirmed_loadout_directory = directory
        policy._confirmed_loadout_path = Path(directory.name) / "confirmed-loadout.json"
    previous = policy._prepare_equipment_optimization
    previous_catalog = policy._equipment_catalog
    try:
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._equipment_catalog = OwnedEquipmentCatalog()
        # TEST_FAKERY_LINT_ALLOW: subject-precompleted: test seeds an independently established loadout prerequisite before exercising a later gate
        set_completed_equipment_optimization(policy)
        if not policy._equipment_departure_ready(snapshot):
            raise AssertionError("fixture cannot complete its worn loadout")
    finally:
        policy._prepare_equipment_optimization = previous
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._equipment_catalog = previous_catalog


def seed_character_calibration(policy, snapshot):
    """Give the policy the P1 worn-independent constants for this snapshot.

    Stage P1 makes a valid unequipped calibration a hard input of the loadout
    optimizer (it fails closed with ``calibration-required`` otherwise).  Test
    fixtures cannot run the multi-visit town calibration phase, so this helper
    computes the constants with the same de-gearing formulas the pre-P1 code
    applied inline — for every fixture snapshot the calibrated constants are
    therefore *identical* to what the legacy derivation produced, and every
    pre-existing assertion keeps its exact meaning.
    """
    from hengbot.equipment_optimizer import (
        OwnedEquipment,
        current_loadout,
        equipment_identity,
    )
    from hengbot.warrior_defense_evaluator import (
        WarriorDefenseInputs,
        loadout_armor_class,
    )
    from hengbot.warrior_equipment_evaluator import (
        TR_DEX,
        TR_STR,
        modify_stat_value,
    )
    from hengbot.warrior_loadout_evaluator import TR_CON, constitution_hp_bonus
    from hengbot.warrior_optimization import (
        PLAYER_ABILITY_FLAGS,
        CharacterCalibration,
        _equipment_speed,
        _intrinsic_flags,
    )

    def _base_stat_without_current_gear(displayed_value, current, flag):
        # Test-only copy of the deleted pre-P1 formula: production contains
        # no per-call modify_stat_value inversion any more.
        equipment_bonus = sum(
            worn.item.pval for _, worn in current.slots if flag in worn.flags
        )
        return modify_stat_value(displayed_value, -equipment_bonus)

    def _conservative_intrinsic_abilities(abilities, current):
        equipment_abilities = {
            name
            for name, flag in PLAYER_ABILITY_FLAGS.items()
            if flag in current.flags
        }
        return frozenset(abilities).difference(equipment_abilities)

    p = snapshot.player
    equipped = tuple(
        OwnedEquipment(
            f"calibration-seed:{index}", worn, "equipped", equipped_slot=worn.slot
        )
        for index, worn in enumerate(snapshot.equipment)
        if worn.is_equipment
    )
    current = current_loadout(equipped)
    displayed = tuple(
        p.stat_use
        if len(p.stat_use) >= 4 and p.stat_use[0] > 0 and p.stat_use[3] > 0
        else p.stat_cur
    )
    padded = displayed + (10,) * max(0, 6 - len(displayed))
    base_str = _base_stat_without_current_gear(padded[0], current, TR_STR)
    base_dex = _base_stat_without_current_gear(padded[3], current, TR_DEX)
    # Mirror the legacy fallback exactly: a 4-entry displayed vector meant CON
    # was defaulted, so the calibrated constant must be the same default.
    base_con = (
        _base_stat_without_current_gear(padded[4], current, TR_CON)
        if len(displayed) >= 5
        else 3
    )
    base_stats = (
        base_str, padded[1], padded[2], base_dex, base_con, padded[5],
    )
    current_con = modify_stat_value(
        base_con,
        sum(worn.item.pval for _, worn in current.slots if TR_CON in worn.flags),
    )
    intrinsic = _conservative_intrinsic_abilities(p.abilities, current)
    provisional = WarriorDefenseInputs(
        level=p.level,
        natural_dex=base_dex,
        shield_skill=p.shield_skill,
        base_speed=p.speed - _equipment_speed(current),
        saving_skill=p.saving_skill,
        intrinsic_flags=_intrinsic_flags(intrinsic),
    )
    policy._character_calibration = CharacterCalibration(
        race_id=p.race_id,
        class_id=p.class_id,
        personality_id=p.personality_id,
        level=p.level,
        stat_cur=tuple(p.stat_cur),
        base_stats=base_stats,
        base_hp=max(1, p.max_hp - constitution_hp_bonus(current_con, p.level)),
        base_ac_bonus=p.ac - loadout_armor_class(current, provisional),
        intrinsic_abilities=intrinsic,
        pinned_identities=tuple(
            sorted(
                (worn.slot, equipment_identity(worn))
                for worn in snapshot.equipment
                if worn.is_equipment and worn.is_cursed
            )
        ),
    )
    policy._character_calibration_loaded = True


def hostile(
    index,
    y,
    x,
    *,
    hp=10,
    max_hp=10,
    distance=1,
    asleep=False,
    speed=110,
    can_summon=False,
    can_multiply=False,
    max_melee_damage=0,
    max_ranged_damage=0,
    race_id=0,
):
    return MonsterState(
        index=index,
        position=Position(y, x),
        hp=hp,
        max_hp=max_hp,
        distance=distance,
        friendly=False,
        pet=False,
        speed=speed,
        asleep=asleep,
        can_summon=can_summon,
        can_multiply=can_multiply,
        max_melee_damage=max_melee_damage,
        max_ranged_damage=max_ranged_damage,
        race_id=race_id,
    )

