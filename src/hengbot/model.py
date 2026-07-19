from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hengbot.monrace_knowledge import MonraceKnowledge


class MissingMonraceKnowledgeError(ValueError):
    pass


@dataclass(frozen=True)
class Position:
    y: int
    x: int

    def distance_to(self, other: "Position") -> int:
        return max(abs(self.y - other.y), abs(self.x - other.x))


# Item categories (tval), from src/object/tval-types.h.
TVAL_BOTTLE = 2  # empty bottles ('!'), left behind by quaffed potions — pure junk
TVAL_CHEST = 7  # chests ('&') — trapped/locked loot containers
TVAL_WHISTLE = 4
TVAL_SPIKE = 5
TVAL_FIGURINE = 8
TVAL_STATUE = 9
TVAL_CAPTURE = 11
TVAL_SHOT = 16
TVAL_ARROW = 17
TVAL_BOLT = 18
TVAL_BOW = 19
TVAL_DIGGING = 20
TVAL_HAFTED = 21  # maces/hammers ('\')
SV_HAFTED_WIZSTAFF = 21
TVAL_POLEARM = 22  # spears/axes ('/')
TVAL_SWORD = 23  # edged weapons ('|')
# sv-bow-types.h launcher subtypes (ammo matching)
SV_BOW_SLING = 2
SV_BOW_SHORT = 12
SV_BOW_LONG = 13
SV_BOW_LIGHT_XBOW = 23
SV_BOW_HEAVY_XBOW = 24
TVAL_BOOTS = 30
TVAL_GLOVES = 31
TVAL_HELM = 32
TVAL_CROWN = 33
TVAL_SHIELD = 34
TVAL_CLOAK = 35
TVAL_SOFT_ARMOR = 36
TVAL_HARD_ARMOR = 37
TVAL_DRAG_ARMOR = 38
TVAL_LITE = 39
TVAL_AMULET = 40
TVAL_RING = 45
TVAL_CARD = 50
TVAL_STAFF = 55
TVAL_WAND = 65
TVAL_ROD = 66
TVAL_SCROLL = 70
TVAL_FLASK = 77
TVAL_POTION = 75
TVAL_FOOD = 80
TVAL_LIFE_BOOK = 90
TVAL_SORCERY_BOOK = 91
TVAL_NATURE_BOOK = 92
TVAL_CHAOS_BOOK = 93
TVAL_DEATH_BOOK = 94
TVAL_TRUMP_BOOK = 95
TVAL_ARCANE_BOOK = 96
TVAL_CRAFT_BOOK = 97
TVAL_DEMON_BOOK = 98
TVAL_CRUSADE_BOOK = 99
TVAL_MUSIC_BOOK = 105
TVAL_HISSATSU_BOOK = 106
TVAL_HEX_BOOK = 107

# These base items receive a random resistance even when they are neither ego
# items nor artifacts.  Normal identification does not reveal that resistance.
SV_DRAGON_SHIELD = 6
SV_DRAGON_HELM = 7
SV_PAIR_OF_DRAGON_GREAVE = 4
SV_SET_OF_DRAGON_GLOVES = 3
RANDOM_RESIST_DRAGON_PROTECTORS = frozenset(
    {
        (TVAL_SHIELD, SV_DRAGON_SHIELD),
        (TVAL_HELM, SV_DRAGON_HELM),
        (TVAL_BOOTS, SV_PAIR_OF_DRAGON_GREAVE),
        (TVAL_GLOVES, SV_SET_OF_DRAGON_GLOVES),
    }
)
SPELLBOOK_TVALS = frozenset(range(TVAL_LIFE_BOOK, TVAL_CRUSADE_BOOK + 1)) | {
    TVAL_MUSIC_BOOK,
    TVAL_HISSATSU_BOOK,
    TVAL_HEX_BOOK,
}

# Light svals (sv-lite-types.h); oil (sv-other-types.h). Torch radius 1, lantern
# radius 2 — the lantern is the upgrade we shop for.
SV_LITE_TORCH = 0
SV_LITE_LANTERN = 1
SV_POTION_SLEEP = 11
SV_POTION_SPEED = 29
SV_SCROLL_DETECT_INVISIBLE = 30
SV_SCROLL_DETECT_TRAP = 28
SV_SCROLL_LIGHT = 24
SV_SCROLL_DETECT_ITEM = 27
SV_SCROLL_DETECT_DOOR = 29
SV_SCROLL_BLESSING = 33
SV_FLASK_OIL = 0
SV_SCROLL_PHASE_DOOR = 8
SV_SCROLL_WORD_OF_RECALL = 11
SV_SCROLL_IDENTIFY = 12
SV_SCROLL_STAR_IDENTIFY = 13
SV_SCROLL_REMOVE_CURSE = 14
SV_SCROLL_STAR_REMOVE_CURSE = 15
SV_SCROLL_ENCHANT_WEAPON_TO_HIT = 17
SV_SCROLL_ENCHANT_WEAPON_TO_DAM = 18
SV_SCROLL_DETECT_TREASURE = 26
SV_SCROLL_TELEPORT = 9
SV_SCROLL_HOLY_CHANT = 34
SV_SCROLL_STAR_DESTRUCTION = 41
SV_POTION_CURE_CRITICAL = 36
SV_POTION_HEALING = 37
SV_POTION_RESIST_COLD = 31
# Restore-stat potions (sv-potion-types.h), sold by the Alchemist. Each undoes the
# drain on one ability; the character screen shows which stat is drained.
STAT_NAMES = ("str", "int", "wis", "dex", "con", "chr")
SV_POTION_RESTORE_STR = 42
SV_POTION_RESTORE_INT = 43
SV_POTION_RESTORE_WIS = 44
SV_POTION_RESTORE_DEX = 45
SV_POTION_RESTORE_CON = 46
SV_POTION_RESTORE_CHR = 47
RESTORE_POTION_SVAL_BY_STAT = {
    "str": SV_POTION_RESTORE_STR,
    "int": SV_POTION_RESTORE_INT,
    "wis": SV_POTION_RESTORE_WIS,
    "dex": SV_POTION_RESTORE_DEX,
    "con": SV_POTION_RESTORE_CON,
    "chr": SV_POTION_RESTORE_CHR,
}
# Permanent stat-GAIN potions (sv-potion-types.h): Potion of Strength/…/Charisma
# each raise one ability, Augmentation raises them all. One-shot upgrades with no
# downside — the bot drinks them on sight.
SV_POTION_INC_STR = 48
SV_POTION_INC_INT = 49
SV_POTION_INC_WIS = 50
SV_POTION_INC_DEX = 51
SV_POTION_INC_CON = 52
SV_POTION_INC_CHR = 53
SV_POTION_AUGMENTATION = 55
STAT_GAIN_POTION_SVALS = frozenset(
    {
        SV_POTION_INC_STR,
        SV_POTION_INC_INT,
        SV_POTION_INC_WIS,
        SV_POTION_INC_DEX,
        SV_POTION_INC_CON,
        SV_POTION_INC_CHR,
        SV_POTION_AUGMENTATION,
    }
)
SV_STAFF_IDENTIFY = 5
SV_STAFF_DESTRUCTION = 29
SV_WAND_TELEPORT_AWAY = 3
SV_WAND_STONE_TO_MUD = 6
SV_ROD_IDENTIFY = 2
SV_ROD_LITE = 15
SV_DIGGING_SHOVEL = 1
SV_DIGGING_PICK = 4

# Store indices (system/enums/store-sale-type.h): the General Store sells the
# lantern, torches, oil and food.
STORE_GENERAL = 0
STORE_ARMOURY = 1
STORE_WEAPON = 2  # the Weapon Smith buys/sells melee weapons and ammo
STORE_TEMPLE = 3
STORE_ALCHEMIST = 4
STORE_MAGIC = 5
STORE_BLACK = 6
STORE_HOME = 7

DUNGEON_ANGBAND = 1
DUNGEON_YEEK_CAVE = 2
PLAYER_CLASS_WARRIOR = 0


@dataclass(frozen=True)
class PlayerState:
    position: Position
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    level: int
    food_state: str = "unknown"
    speed: int = 110
    exp: int = 0
    gold: int = 0
    recalling: bool = False
    food_type: int = 0  # PlayerRaceFoodType: 0 RATION .. 4 MANA (eats device charges) .. 5 CORPSE
    blind: bool = False
    confused: bool = False
    afraid: bool = False
    poisoned: bool = False
    stunned: bool = False
    cut: bool = False
    paralyzed: bool = False
    hallucinated: bool = False
    class_id: int = -1
    race_id: int = -1
    personality_id: int = -1
    ac: int = 0
    main_hand_blows: int = 0
    sub_hand_blows: int = 0
    main_hand_to_h: int = 0
    sub_hand_to_h: int = 0
    main_hand_to_d: int = 0
    sub_hand_to_d: int = 0
    drained_stats: tuple[str, ...] = ()  # ability names below their max (e.g. "str", "con")
    abilities: frozenset[str] = frozenset()  # resistances / telepathy / free_action the char HAS
    stat_cur: tuple[int, ...] = ()  # six natural values, before equipment pval
    stat_max: tuple[int, ...] = ()
    stat_use: tuple[int, ...] = ()  # six currently modified values
    stat_index: tuple[int, ...] = ()  # indices used by Hengband's adjustment tables
    melee_skill: int = 0
    saving_skill: int = 0
    device_skill: int = 0
    stealth_skill: int = 0
    two_weapon_skill: int = 0
    shield_skill: int = 0

    @property
    def hp_ratio(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return self.hp / self.max_hp

    @property
    def mp_ratio(self) -> float:
        if self.max_mp <= 0:
            return 1.0
        return self.mp / self.max_mp

    @property
    def hungry(self) -> bool:
        return self.food_state in {"hungry", "weak", "fainting"}

    @property
    def fainting(self) -> bool:
        return self.food_state == "fainting"


@dataclass(frozen=True)
class InventoryItem:
    slot: str  # inventory letter, e.g. "a"
    name: str
    count: int
    tval: int
    sval: int
    aware: bool  # the player knows what this item type does
    known: bool  # this specific item is fully identified
    fully_known: bool = False  # this item has been *identified*
    charges: int = 0  # wand/staff charges (item pval)
    pval: int = 0
    fuel: int = 0  # remaining turns for torches, lanterns, and oil flasks
    timeout: int = 0
    is_equipment: bool = False
    is_ego: bool = False
    is_artifact: bool = False
    is_cursed: bool = False
    inscription: str = ""
    is_broken: bool = False
    is_bounty: bool = False
    to_h: int = 0
    to_d: int = 0
    to_a: int = 0
    ac: int = 0
    damage_dice_num: int = 0
    damage_dice_sides: int = 0
    known_flags: frozenset[int] = frozenset()
    pseudo_feeling: str = ""
    weight: int = 0  # internal decipounds, displayed to the player as pounds
    weapon_proficiency: int = 0

    @property
    def is_potion(self) -> bool:
        return self.tval == TVAL_POTION

    @property
    def is_empty_bottle(self) -> bool:
        # tval TV_BOTTLE is exclusively the "Empty Bottle" junk left by quaffing
        # a potion; it has no flavour, so it is always identified on sight.
        return self.tval == TVAL_BOTTLE

    @property
    def is_scroll(self) -> bool:
        return self.tval == TVAL_SCROLL

    @property
    def is_food(self) -> bool:
        return self.tval == TVAL_FOOD

    @property
    def is_spellbook(self) -> bool:
        return self.tval in SPELLBOOK_TVALS

    @property
    def is_wand_staff(self) -> bool:
        return self.tval in (TVAL_STAFF, TVAL_WAND)

    @property
    def is_light(self) -> bool:
        return self.tval == TVAL_LITE

    @property
    def is_lantern(self) -> bool:
        return self.tval == TVAL_LITE and self.sval == SV_LITE_LANTERN

    @property
    def is_torch(self) -> bool:
        return self.tval == TVAL_LITE and self.sval == SV_LITE_TORCH

    @property
    def is_oil(self) -> bool:
        return self.tval == TVAL_FLASK and self.sval == SV_FLASK_OIL

    @property
    def is_recall_scroll(self) -> bool:
        return (
            self.aware
            and self.tval == TVAL_SCROLL
            and self.sval == SV_SCROLL_WORD_OF_RECALL
        )

    @property
    def is_teleport_scroll(self) -> bool:
        return self.aware and self.tval == TVAL_SCROLL and self.sval == SV_SCROLL_TELEPORT

    @property
    def is_treasure_detection_scroll(self) -> bool:
        return (
            self.aware
            and self.tval == TVAL_SCROLL
            and self.sval == SV_SCROLL_DETECT_TREASURE
        )

    @property
    def is_digging_tool(self) -> bool:
        # Every item of tval TV_DIGGING is a digger; the sval only sets digging
        # power (SV_SHOVEL..SV_MATTOCK = 1..7). Gating on the plain shovel/pick
        # svals alone would reject upgraded diggers (gnomish/dwarven shovel,
        # orcish/dwarven pick, mattock) and make fundraising think it has none.
        return self.tval == TVAL_DIGGING

    @property
    def is_melee_weapon(self) -> bool:
        # A main-hand melee weapon: TV_HAFTED / TV_POLEARM / TV_SWORD. Excludes the
        # digger (TV_DIGGING, its own category) and bows/ammo. Used to re-arm the
        # combat weapon after mining swapped a digging tool into the main hand.
        return self.tval in (TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD)

    @property
    def is_chest(self) -> bool:
        return self.tval == TVAL_CHEST

    @property
    def is_launcher(self) -> bool:
        # TV_BOW covers every launcher (sling/bows/crossbows). The special
        # non-firing svals (Crimson, Harp) are excluded by ammo matching: they
        # have no ammo tval, so ammo_tval returns None for them.
        return self.tval == TVAL_BOW

    @property
    def ammo_tval(self) -> int | None:
        """The ammo tval this launcher fires (do_cmd_fire's tval_ammo).

        Mirrors get_arrow_kind(): sling -> TV_SHOT, short/long bow -> TV_ARROW,
        crossbows -> TV_BOLT (sv-bow-types.h: SLING=2, SHORT=12, LONG=13,
        LIGHT_XBOW=23, HEAVY_XBOW=24).
        """
        if self.tval != TVAL_BOW:
            return None
        if self.sval == SV_BOW_SLING:
            return TVAL_SHOT
        if self.sval in (SV_BOW_SHORT, SV_BOW_LONG):
            return TVAL_ARROW
        if self.sval in (SV_BOW_LIGHT_XBOW, SV_BOW_HEAVY_XBOW):
            return TVAL_BOLT
        return None

    @property
    def is_ammo(self) -> bool:
        return self.tval in (TVAL_SHOT, TVAL_ARROW, TVAL_BOLT)


@dataclass(frozen=True)
class StoreItem:
    letter: str  # key to press to select this item at the store prompt
    name: str
    count: int
    tval: int
    sval: int
    price: int
    aware: bool = True
    known: bool = True

    @property
    def is_ammo(self) -> bool:
        return self.tval in (TVAL_SHOT, TVAL_ARROW, TVAL_BOLT)
    fully_known: bool = True
    is_equipment: bool = False
    is_ego: bool = False
    is_artifact: bool = False
    is_cursed: bool = False
    inscription: str = ""
    is_broken: bool = False
    to_h: int = 0
    to_d: int = 0
    to_a: int = 0
    ac: int = 0
    damage_dice_num: int = 0
    damage_dice_sides: int = 0
    known_flags: frozenset[int] = frozenset()
    charges: int = 0
    pval: int = 0
    pseudo_feeling: str = ""
    weight: int = 0
    weapon_proficiency: int = 0

    @property
    def is_lantern(self) -> bool:
        return self.tval == TVAL_LITE and self.sval == SV_LITE_LANTERN

    @property
    def is_torch(self) -> bool:
        return self.tval == TVAL_LITE and self.sval == SV_LITE_TORCH

    @property
    def is_oil(self) -> bool:
        return self.tval == TVAL_FLASK and self.sval == SV_FLASK_OIL

    @property
    def is_recall_scroll(self) -> bool:
        return self.tval == TVAL_SCROLL and self.sval == SV_SCROLL_WORD_OF_RECALL

    @property
    def is_teleport_scroll(self) -> bool:
        return self.tval == TVAL_SCROLL and self.sval == SV_SCROLL_TELEPORT
    @property
    def is_treasure_detection_scroll(self) -> bool:
        return self.tval == TVAL_SCROLL and self.sval == SV_SCROLL_DETECT_TREASURE

    @property
    def is_digging_tool(self) -> bool:
        # Every item of tval TV_DIGGING is a digger; the sval only sets digging
        # power (SV_SHOVEL..SV_MATTOCK = 1..7). Gating on the plain shovel/pick
        # svals alone would reject upgraded diggers (gnomish/dwarven shovel,
        # orcish/dwarven pick, mattock) and make fundraising think it has none.
        return self.tval == TVAL_DIGGING

    @property
    def is_melee_weapon(self) -> bool:
        """A combat melee weapon, excluding digging tools and missile weapons."""
        return self.tval in (TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD)


def item_requires_full_identification(item: InventoryItem | StoreItem) -> bool:
    """Return whether normal identification can leave combat traits hidden."""
    return (
        (item.is_ego and not (item.known and item.is_cursed))
        or item.is_artifact
        or (item.tval, item.sval) in RANDOM_RESIST_DRAGON_PROTECTORS
    )


@dataclass(frozen=True)
class StoreState:
    store_type: int
    items: list["StoreItem"] = field(default_factory=list)


@dataclass(frozen=True)
class GridState:
    position: Position
    known: bool
    passable: bool
    wall: bool
    has_monster: bool
    has_down_stairs: bool
    has_up_stairs: bool
    unsafe: bool
    is_closed_door: bool = False
    is_door: bool = False  # any door, open or closed (only enterable orthogonally)
    trap: bool = False
    object_count: int = 0
    has_entrance: bool = False  # wilderness/town dungeon entrance (enter with '>')
    store_number: int = -1  # -1 = not a store; else the StoreSaleType index
    can_dig: bool = False  # terrain is a dig target (rubble / vein / granite)
    monster_index: int = 0
    has_gold: bool = False
    entrance_dungeon_id: int = -1
    building_type: int = -1
    has_quest_enter: bool = False
    has_quest_exit: bool = False
    quest_id: int = -1
    building_special: int = -1

    @property
    def is_store(self) -> bool:
        return self.store_number >= 0

    @property
    def is_rubble(self) -> bool:
        """A pile of rubble: diggable and blocks movement, but is NOT a wall
        (granite/veins carry the wall flag; rubble does not) and clears quickly
        (tunnel power 10). We tunnel through it with 'T'+direction."""
        return self.can_dig and not self.wall and not self.passable

    @property
    def is_descent(self) -> bool:
        """A tile we can go down from with the '>' command."""
        return self.has_down_stairs or self.has_entrance

    @property
    def enterable(self) -> bool:
        """A grid we can step onto or into with a single move command.

        Floors (``passable``) can be walked onto directly; a closed door is
        opened by moving into it, which is also a legal single move command.
        """
        return self.known and (self.passable or self.is_closed_door)


@dataclass(frozen=True)
class MonsterState:
    index: int
    position: Position
    hp: int
    max_hp: int
    distance: int
    friendly: bool
    pet: bool
    speed: int = 110
    asleep: bool = False
    stunned: bool = False
    confused: bool = False
    fearful: bool = False
    name: str = ""
    race_id: int = 0
    can_summon: bool = False
    level: int = 0
    max_melee_damage: int = 0
    max_ranged_damage: int = 0
    can_multiply: bool = False

    @property
    def hostile(self) -> bool:
        return not self.friendly and not self.pet

    @property
    def hp_ratio(self) -> float:
        if self.max_hp <= 0:
            return 1.0
        return self.hp / self.max_hp


@dataclass(frozen=True)
class QuestState:
    id: int
    name: str = ""
    status: int = 0
    type: int = 0
    level: int = 0
    dungeon_id: int = 0
    r_idx: int = 0
    cur_num: int = 0
    max_num: int = 0
    num_mon: int = 0
    flags: int = 0
    complev: int = 0
    comptime: int = 0
    fixed: bool = False
    has_reward: bool = False
    reward_artifact_id: int | None = None
    reward_baseitem_id: int = 0
    reward_instant_artifact: bool = False


@dataclass(frozen=True)
class Snapshot:
    player: PlayerState
    grids: dict[Position, GridState]
    visible_monsters: list[MonsterState]
    turn: int = 0
    floor_key: tuple[int, int, int] = (0, 0, 0)
    inside_arena: bool = False
    width: int = 0
    height: int = 0
    inventory: list[InventoryItem] = field(default_factory=list)
    equipment: list[InventoryItem] = field(default_factory=list)
    store: "StoreState | None" = None  # present only while standing in a store
    recall_dungeon_id: int = 0
    entered_dungeon_ids: tuple[int, ...] = ()
    conquered_dungeon_ids: tuple[int, ...] = ()  # dungeons whose final guardian is dead
    visited_town_ids: tuple[int, ...] | None = None
    # Deepest level reached in the recall-target dungeon (where Word of Recall
    # lands). Persists in the save across bot restarts, unlike the policy's
    # in-memory watermark; 0 when an older emitter did not send it.
    recall_depth: int = 0
    yeek_cave_conquered: bool = False
    angband_recall_unlocked: bool = False
    quests: dict[int, QuestState] = field(default_factory=dict)
    # From the emitter's floor.in_town (AngbandWorld::is_in_any_town). None when an
    # older emitter did not send it, so in_town falls back to the floor heuristic.
    town_flag: bool | None = None
    town_id: int = -1
    town_index: int = 0

    def in_bounds(self, position: Position) -> bool:
        # With unknown dimensions, treat everything as in-bounds (no filtering).
        if self.width <= 0 or self.height <= 0:
            return True
        return 0 <= position.y < self.height and 0 <= position.x < self.width

    @property
    def dungeon_level(self) -> int:
        return self.floor_key[1]

    @property
    def in_town(self) -> bool:
        # The emitter's flag is authoritative: it is True ONLY on a real town tile
        # (is_in_any_town), which the surface open-wilderness — sharing dungeon_id
        # 0 / level 0 with the town — is NOT. Fall back to the old (imprecise)
        # surface heuristic only when an older emitter omits the flag.
        if self.town_flag is not None:
            return self.town_flag
        return self.floor_key[0] == 0 and self.floor_key[1] == 0

    @property
    def on_open_wilderness(self) -> bool:
        # On the surface (level 0) but NOT a town tile: the open wilderness, where
        # out-of-depth monsters roam and there are no stores. The bot must treat it
        # as a hostile transit zone, never a place to shop/explore/fight.
        return self.floor_key[1] == 0 and not self.in_town

    def grid_at(self, position: Position) -> GridState | None:
        return self.grids.get(position)


def _as_bool(value: Any) -> bool:
    return bool(value)


# Stand-in HP/max-HP for a monster whose identity is hidden by hallucination:
# large enough that the hunt heuristic treats it as "not clearly beatable" (so
# the bot does not chase an unidentified threat) while melee/flee, which key off
# position, still engage or disengage it normally.
UNKNOWN_MONSTER_HP = 9999


def _estimated_monster_hp(max_hp: int, health: str) -> int:
    upper_percent = {
        "unhurt": 100,
        "lightly_wounded": 99,
        "wounded": 59,
        "badly_wounded": 24,
        "almost_dead": 9,
    }.get(health, 100)
    return max(1, (max_hp * upper_percent + 99) // 100)


def parse_snapshot(
    data: dict[str, Any], monrace_knowledge: dict[int, MonraceKnowledge] | None = None
) -> Snapshot:
    player_data = data["player"]
    status = player_data.get("status", {})
    melee = player_data.get("melee", {})
    stats = player_data.get("stats", {})
    drained_stats = tuple(
        name
        for name in STAT_NAMES
        if isinstance(stats.get(name), dict) and _as_bool(stats[name].get("drained", False))
    )
    abilities = frozenset(
        key for key, value in player_data.get("abilities", {}).items() if _as_bool(value)
    )
    stat_names = tuple(STAT_NAMES)
    stat_cur = tuple(int(stats.get(name, {}).get("cur", 0)) for name in stat_names)
    stat_max = tuple(int(stats.get(name, {}).get("max", 0)) for name in stat_names)
    stat_use = tuple(int(stats.get(name, {}).get("use", 0)) for name in stat_names)
    stat_index = tuple(int(stats.get(name, {}).get("index", 0)) for name in stat_names)
    skills = player_data.get("skills", {})
    player = PlayerState(
        position=Position(int(player_data["y"]), int(player_data["x"])),
        hp=int(player_data["hp"]),
        max_hp=int(player_data["max_hp"]),
        mp=int(player_data.get("mp", 0)),
        max_mp=int(player_data.get("max_mp", 0)),
        level=int(player_data.get("level", 1)),
        food_state=str(player_data.get("food_state", "unknown")),
        speed=int(player_data.get("speed", 110)),
        exp=int(player_data.get("exp", 0)),
        gold=int(player_data.get("gold", 0)),
        recalling=_as_bool(player_data.get("recalling", False)),
        food_type=int(player_data.get("food_type", 0)),
        blind=_as_bool(status.get("blind", False)),
        confused=_as_bool(status.get("confused", False)),
        afraid=_as_bool(status.get("afraid", False)),
        poisoned=_as_bool(status.get("poisoned", False)),
        stunned=_as_bool(status.get("stunned", False)),
        cut=_as_bool(status.get("cut", False)),
        paralyzed=_as_bool(status.get("paralyzed", False)),
        hallucinated=_as_bool(status.get("hallucinated", False)),
        class_id=int(player_data.get("class_id", -1)),
        race_id=int(player_data.get("race_id", -1)),
        personality_id=int(player_data.get("personality_id", -1)),
        ac=int(player_data.get("ac", 0)),
        main_hand_blows=int(melee.get("main_hand_blows", 0)),
        sub_hand_blows=int(melee.get("sub_hand_blows", 0)),
        main_hand_to_h=int(melee.get("main_hand_to_h", 0)),
        sub_hand_to_h=int(melee.get("sub_hand_to_h", 0)),
        main_hand_to_d=int(melee.get("main_hand_to_d", 0)),
        sub_hand_to_d=int(melee.get("sub_hand_to_d", 0)),
        drained_stats=drained_stats,
        abilities=abilities,
        stat_cur=stat_cur,
        stat_max=stat_max,
        stat_use=stat_use,
        stat_index=stat_index,
        melee_skill=int(skills.get("melee", 0)),
        saving_skill=int(skills.get("saving", 0)),
        device_skill=int(skills.get("device", 0)),
        stealth_skill=int(skills.get("stealth", 0)),
        two_weapon_skill=int(skills.get("two_weapon", 0)),
        shield_skill=int(skills.get("shield", 0)),
    )

    grids: dict[Position, GridState] = {}
    for grid_data in data.get("nearby_grids", []):
        pos = Position(int(grid_data["y"]), int(grid_data["x"]))
        terrain = grid_data.get("terrain", {})
        flags = grid_data.get("flags", {})
        known = bool(grid_data.get("known", flags.get("known", False)))
        monster_index = int(grid_data.get("monster_index", 0))
        move = known and _as_bool(terrain.get("move", False))
        door = known and _as_bool(terrain.get("door", False))
        grids[pos] = GridState(
            position=pos,
            known=known,
            passable=move,
            wall=known and _as_bool(terrain.get("wall", False)),
            has_monster=known and monster_index > 0,
            has_down_stairs=known and _as_bool(terrain.get("down_stairs", False)),
            has_up_stairs=known and _as_bool(terrain.get("up_stairs", False)),
            unsafe=known and _as_bool(flags.get("unsafe", False)),
            is_closed_door=door and not move,
            is_door=door,
            trap=known and _as_bool(terrain.get("trap", False)),
            object_count=int(grid_data.get("object_count", 0)),
            has_entrance=known and _as_bool(terrain.get("entrance", False)),
            store_number=int(grid_data.get("store_number", -1)) if known else -1,
            can_dig=known
            and (
                _as_bool(terrain.get("can_dig", False))
                or _as_bool(terrain.get("has_gold", False))
            ),
            monster_index=monster_index if known else 0,
            has_gold=known and _as_bool(terrain.get("has_gold", False)),
            entrance_dungeon_id=(
                int(grid_data.get("entrance_dungeon_id", -1)) if known else -1
            ),
            building_type=int(grid_data.get("building_type", -1)) if known else -1,
            has_quest_enter=known and _as_bool(terrain.get("quest_enter", False)),
            has_quest_exit=known and _as_bool(terrain.get("quest_exit", False)),
            quest_id=int(grid_data.get("quest_id", -1)) if known else -1,
            building_special=(
                int(grid_data.get("building_special", -1)) if known else -1
            ),
        )

    positions = {
        grid.monster_index: grid.position
        for grid in grids.values()
        if grid.monster_index > 0
    }
    knowledge_by_id = monrace_knowledge or {}
    monsters: list[MonsterState] = []
    for monster_data in data.get("visible_monsters", []):
        index = int(monster_data["index"])
        position = positions.get(index)
        if position is None:
            continue
        friendly = bool(monster_data.get("friendly", False))
        pet = bool(monster_data.get("pet", False))
        if monster_data.get("hallucinated", False):
            # Identity is unknowable while hallucinating; we still know a monster
            # occupies this tile (the player sees a random symbol there). Treat it
            # as a threat of unknown strength so the bot keeps defending itself —
            # it will not rest into it, will melee it if adjacent, and will flee
            # when hurt — without ever looking up (absent) monrace knowledge.
            monsters.append(
                MonsterState(
                    index=index,
                    position=position,
                    hp=UNKNOWN_MONSTER_HP,
                    max_hp=UNKNOWN_MONSTER_HP,
                    distance=player.position.distance_to(position),
                    friendly=friendly,
                    pet=pet,
                )
            )
            continue
        race_id = int(monster_data.get("race_id", 0))
        knowledge = knowledge_by_id.get(race_id)
        if knowledge is None:
            raise MissingMonraceKnowledgeError(
                f"missing monster knowledge for race_id={race_id}"
            )
        max_hp = knowledge.max_hp
        health = str(monster_data.get("health", "unhurt"))
        monsters.append(
            MonsterState(
                index=index,
                position=position,
                hp=_estimated_monster_hp(max_hp, health),
                max_hp=max_hp,
                distance=player.position.distance_to(position),
                friendly=friendly,
                pet=pet,
                speed=knowledge.speed,
                asleep=bool(monster_data.get("asleep", False)),
                stunned=bool(monster_data.get("stunned", False)),
                confused=bool(monster_data.get("confused", False)),
                fearful=bool(monster_data.get("fearful", False)),
                name=str(monster_data.get("name", "")),
                race_id=race_id,
                can_summon=knowledge.can_summon,
                level=knowledge.level,
                max_melee_damage=knowledge.max_melee_damage,
                max_ranged_damage=knowledge.max_ranged_damage,
                can_multiply=knowledge.can_multiply,
            )
        )

    floor_data = data.get("floor", {})
    floor_key = (
        int(floor_data.get("dungeon_id", 0)),
        int(floor_data.get("level", 0)),
        int(floor_data.get("quest_id", 0)),
    )

    progress = data.get("progress", {})
    quests: dict[int, QuestState] = {}
    for quest_data in progress.get("quests", []):
        quest_id = int(quest_data.get("id", 0))
        quests[quest_id] = QuestState(
            id=quest_id,
            name=str(quest_data.get("name", "")),
            status=int(quest_data.get("status", 0)),
            type=int(quest_data.get("type", 0)),
            level=int(quest_data.get("level", 0)),
            dungeon_id=int(quest_data.get("dungeon_id", 0)),
            r_idx=int(quest_data.get("r_idx", 0)),
            cur_num=int(quest_data.get("cur_num", 0)),
            max_num=int(quest_data.get("max_num", 0)),
            num_mon=int(quest_data.get("num_mon", 0)),
            flags=int(quest_data.get("flags", 0)),
            complev=int(quest_data.get("complev", 0)),
            comptime=int(quest_data.get("comptime", 0)),
            fixed=_as_bool(quest_data.get("fixed", False)),
            has_reward=_as_bool(quest_data.get("has_reward", False)),
            reward_artifact_id=(
                int(quest_data["reward_artifact_id"])
                if quest_data.get("reward_artifact_id") is not None
                else None
            ),
            reward_baseitem_id=int(quest_data.get("reward_baseitem_id", 0)),
            reward_instant_artifact=_as_bool(
                quest_data.get("reward_instant_artifact", False)
            ),
        )
    return Snapshot(
        player=player,
        grids=grids,
        visible_monsters=monsters,
        turn=int(data.get("turn", 0)),
        floor_key=floor_key,
        inside_arena=bool(floor_data.get("inside_arena", False)),
        width=int(floor_data.get("width", 0)),
        height=int(floor_data.get("height", 0)),
        town_flag=(
            _as_bool(floor_data["in_town"]) if "in_town" in floor_data else None
        ),
        town_id=int(floor_data.get("town_id", -1)),
        town_index=int(floor_data.get("town_index", 0)),
        inventory=_parse_items(data.get("inventory", [])),
        equipment=_parse_items(data.get("equipment", [])),
        store=_parse_store(data.get("store")),
        recall_dungeon_id=int(progress.get("recall_dungeon_id", 0)),
        entered_dungeon_ids=tuple(
            int(dungeon_id) for dungeon_id in progress.get("entered_dungeon_ids", [])
        ),
        conquered_dungeon_ids=tuple(
            int(dungeon_id) for dungeon_id in progress.get("conquered_dungeon_ids", [])
        ),
        visited_town_ids=(
            tuple(int(town_id) for town_id in progress["visited_town_ids"])
            if "visited_town_ids" in progress
            else None
        ),
        recall_depth=int(progress.get("recall_depth", 0)),
        yeek_cave_conquered=_as_bool(progress.get("yeek_cave_conquered", False)),
        angband_recall_unlocked=_as_bool(
            progress.get("angband_recall_unlocked", False)
        ),
        quests=quests,
    )


def _parse_store(store_data: Any) -> "StoreState | None":
    if not store_data:
        return None
    items = []
    for it in store_data.get("items", []):
        dice = it.get("damage_dice", {})
        name = str(it.get("name", ""))
        tval = int(it.get("tval", 0))
        charges = _store_item_charges(it, name=name, tval=tval)
        items.append(StoreItem(
            letter=str(it.get("letter", "")),
            name=name,
            count=int(it.get("count", 1)),
            tval=tval,
            sval=int(it.get("sval", -1)),
            price=int(it.get("price", 0)),
            aware=_as_bool(it.get("aware", False)),
            known=_as_bool(it.get("known", False)),
            fully_known=_as_bool(it.get("fully_known", False)),
            is_equipment=_as_bool(it.get("is_equipment", False)),
            is_ego=_as_bool(it.get("is_ego", False)),
            is_artifact=_as_bool(it.get("is_artifact", False)),
            is_cursed=_as_bool(it.get("is_cursed", False)),
            inscription=str(it.get("inscription", "")),
            is_broken=_as_bool(it.get("is_broken", False)),
            to_h=int(it.get("to_h", 0)),
            to_d=int(it.get("to_d", 0)),
            to_a=int(it.get("to_a", 0)),
            ac=int(it.get("ac", 0)),
            damage_dice_num=int(dice.get("num", 0)),
            damage_dice_sides=int(dice.get("sides", 0)),
            known_flags=frozenset(int(flag) for flag in it.get("known_flags", [])),
            charges=charges,
            pval=charges if tval in {TVAL_WAND, TVAL_STAFF} else int(it.get("pval", 0)),
            pseudo_feeling=str(it.get("pseudo_feeling", "")),
            weight=int(it.get("weight", 0)),
            weapon_proficiency=int(it.get("weapon_proficiency", 0)),
        ))
    return StoreState(store_type=int(store_data.get("store_type", -1)), items=items)


_STORE_CHARGES_RE = re.compile(r"[\(（]\s*(\d+)\s*(?:回分|charges?)\s*[\)）]", re.IGNORECASE)


def _store_item_charges(item_data: Any, *, name: str, tval: int) -> int:
    """Recover player-visible device charges omitted by ordinary store JSON."""
    if tval not in {TVAL_WAND, TVAL_STAFF}:
        return int(item_data.get("pval", 0))
    if "charges" in item_data:
        return int(item_data["charges"])
    if "pval" in item_data:
        return int(item_data["pval"])
    match = _STORE_CHARGES_RE.search(name)
    return int(match.group(1)) if match else 0


def _parse_items(items_data: Any) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for item_data in items_data or []:
        dice = item_data.get("damage_dice", {})
        items.append(
            InventoryItem(
                slot=str(item_data.get("slot", "")),
                name=str(item_data.get("name", "")),
                count=int(item_data.get("count", 1)),
                tval=int(item_data.get("tval", 0)),
                sval=int(item_data.get("sval", -1)),
                aware=_as_bool(item_data.get("aware", False)),
                known=_as_bool(item_data.get("known", False)),
                fully_known=_as_bool(item_data.get("fully_known", False)),
                charges=int(item_data.get("charges", 0)),
                pval=int(item_data.get("pval", 0)),
                fuel=int(item_data.get("fuel", 0)),
                timeout=int(item_data.get("timeout", 0)),
                is_equipment=_as_bool(item_data.get("is_equipment", False)),
                is_ego=_as_bool(item_data.get("is_ego", False)),
                is_artifact=_as_bool(item_data.get("is_artifact", False)),
                is_cursed=_as_bool(item_data.get("is_cursed", False)),
                inscription=str(item_data.get("inscription", "")),
                is_broken=_as_bool(item_data.get("is_broken", False)),
                is_bounty=_as_bool(item_data.get("is_bounty", False)),
                to_h=int(item_data.get("to_h", 0)),
                to_d=int(item_data.get("to_d", 0)),
                to_a=int(item_data.get("to_a", 0)),
                ac=int(item_data.get("ac", 0)),
                damage_dice_num=int(dice.get("num", 0)),
                damage_dice_sides=int(dice.get("sides", 0)),
                known_flags=frozenset(
                    int(flag) for flag in item_data.get("known_flags", [])
                ),
                pseudo_feeling=str(item_data.get("pseudo_feeling", "")),
                weight=int(item_data.get("weight", 0)),
                weapon_proficiency=int(item_data.get("weapon_proficiency", 0)),
            )
        )
    return items
