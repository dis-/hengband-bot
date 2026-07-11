from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Position:
    y: int
    x: int

    def distance_to(self, other: "Position") -> int:
        return max(abs(self.y - other.y), abs(self.x - other.x))


# Item categories (tval), from src/object/tval-types.h.
TVAL_LITE = 39
TVAL_AMULET = 40
TVAL_RING = 45
TVAL_STAFF = 55
TVAL_WAND = 65
TVAL_ROD = 66
TVAL_SCROLL = 70
TVAL_FLASK = 77
TVAL_POTION = 75
TVAL_FOOD = 80

# Light svals (sv-lite-types.h); oil (sv-other-types.h). Torch radius 1, lantern
# radius 2 — the lantern is the upgrade we shop for.
SV_LITE_TORCH = 0
SV_LITE_LANTERN = 1
SV_FLASK_OIL = 0

# Store indices (system/enums/store-sale-type.h): the General Store sells the
# lantern, torches, oil and food.
STORE_GENERAL = 0
STORE_TEMPLE = 3


@dataclass(frozen=True)
class PlayerState:
    position: Position
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    level: int
    food: int = 0
    speed: int = 110
    exp: int = 0
    gold: int = 0
    word_recall: int = 0
    food_type: int = 0  # PlayerRaceFoodType: 0 RATION .. 4 MANA (eats device charges) .. 5 CORPSE
    blind: bool = False
    confused: bool = False
    afraid: bool = False
    poisoned: bool = False
    stunned: bool = False
    cut: bool = False
    paralyzed: bool = False
    hallucinated: bool = False

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


@dataclass(frozen=True)
class InventoryItem:
    slot: str  # inventory letter, e.g. "a"
    name: str
    count: int
    tval: int
    sval: int
    aware: bool  # the player knows what this item type does
    known: bool  # this specific item is fully identified
    charges: int = 0  # wand/staff charges (item pval)

    @property
    def is_potion(self) -> bool:
        return self.tval == TVAL_POTION

    @property
    def is_scroll(self) -> bool:
        return self.tval == TVAL_SCROLL

    @property
    def is_food(self) -> bool:
        return self.tval == TVAL_FOOD

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
    def is_oil(self) -> bool:
        return self.tval == TVAL_FLASK and self.sval == SV_FLASK_OIL


@dataclass(frozen=True)
class StoreItem:
    letter: str  # key to press to select this item at the store prompt
    name: str
    count: int
    tval: int
    sval: int
    price: int

    @property
    def is_lantern(self) -> bool:
        return self.tval == TVAL_LITE and self.sval == SV_LITE_LANTERN

    @property
    def is_torch(self) -> bool:
        return self.tval == TVAL_LITE and self.sval == SV_LITE_TORCH

    @property
    def is_oil(self) -> bool:
        return self.tval == TVAL_FLASK and self.sval == SV_FLASK_OIL


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

    @property
    def hostile(self) -> bool:
        return not self.friendly and not self.pet

    @property
    def hp_ratio(self) -> float:
        if self.max_hp <= 0:
            return 1.0
        return self.hp / self.max_hp


@dataclass(frozen=True)
class Snapshot:
    player: PlayerState
    grids: dict[Position, GridState]
    visible_monsters: list[MonsterState]
    turn: int = 0
    dungeon_turn: int = 0
    floor_key: tuple[int, int, int] = (0, 0, 0)
    inside_arena: bool = False
    width: int = 0
    height: int = 0
    inventory: list[InventoryItem] = field(default_factory=list)
    equipment: list[InventoryItem] = field(default_factory=list)
    store: "StoreState | None" = None  # present only while standing in a store

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
        # dungeon_id 0 with level 0 is the surface/town in Hengband's wilderness.
        return self.floor_key[0] == 0 and self.floor_key[1] == 0

    def grid_at(self, position: Position) -> GridState | None:
        return self.grids.get(position)


def _as_bool(value: Any) -> bool:
    return bool(value)


def parse_snapshot(data: dict[str, Any]) -> Snapshot:
    player_data = data["player"]
    status = player_data.get("status", {})
    player = PlayerState(
        position=Position(int(player_data["y"]), int(player_data["x"])),
        hp=int(player_data["hp"]),
        max_hp=int(player_data["max_hp"]),
        mp=int(player_data.get("mp", 0)),
        max_mp=int(player_data.get("max_mp", 0)),
        level=int(player_data.get("level", 1)),
        food=int(player_data.get("food", 0)),
        speed=int(player_data.get("speed", 110)),
        exp=int(player_data.get("exp", 0)),
        gold=int(player_data.get("gold", 0)),
        word_recall=int(player_data.get("word_recall", 0)),
        food_type=int(player_data.get("food_type", 0)),
        blind=_as_bool(status.get("blind", False)),
        confused=_as_bool(status.get("confused", False)),
        afraid=_as_bool(status.get("afraid", False)),
        poisoned=_as_bool(status.get("poisoned", False)),
        stunned=_as_bool(status.get("stunned", False)),
        cut=_as_bool(status.get("cut", False)),
        paralyzed=_as_bool(status.get("paralyzed", False)),
        hallucinated=_as_bool(status.get("hallucinated", False)),
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
            can_dig=known and _as_bool(terrain.get("can_dig", False)),
        )

    monsters = [
        MonsterState(
            index=int(monster_data["index"]),
            position=Position(int(monster_data["y"]), int(monster_data["x"])),
            hp=int(monster_data.get("hp", 0)),
            max_hp=int(monster_data.get("max_hp", 0)),
            distance=int(monster_data.get("distance", 0)),
            friendly=bool(monster_data.get("friendly", False)),
            pet=bool(monster_data.get("pet", False)),
            speed=int(monster_data.get("speed", 110)),
            asleep=bool(monster_data.get("asleep", False)),
            stunned=bool(monster_data.get("stunned", False)),
            confused=bool(monster_data.get("confused", False)),
            fearful=bool(monster_data.get("fearful", False)),
            name=str(monster_data.get("name", "")),
            race_id=int(monster_data.get("race_id", 0)),
        )
        for monster_data in data.get("visible_monsters", [])
    ]

    floor_data = data.get("floor", {})
    floor_key = (
        int(floor_data.get("dungeon_id", 0)),
        int(floor_data.get("level", 0)),
        int(floor_data.get("quest_id", 0)),
    )

    return Snapshot(
        player=player,
        grids=grids,
        visible_monsters=monsters,
        turn=int(data.get("turn", 0)),
        dungeon_turn=int(data.get("dungeon_turn", 0)),
        floor_key=floor_key,
        inside_arena=bool(floor_data.get("inside_arena", False)),
        width=int(floor_data.get("width", 0)),
        height=int(floor_data.get("height", 0)),
        inventory=_parse_items(data.get("inventory", [])),
        equipment=_parse_items(data.get("equipment", [])),
        store=_parse_store(data.get("store")),
    )


def _parse_store(store_data: Any) -> "StoreState | None":
    if not store_data:
        return None
    items = [
        StoreItem(
            letter=str(it.get("letter", "")),
            name=str(it.get("name", "")),
            count=int(it.get("count", 1)),
            tval=int(it.get("tval", 0)),
            sval=int(it.get("sval", -1)),
            price=int(it.get("price", 0)),
        )
        for it in store_data.get("items", [])
    ]
    return StoreState(store_type=int(store_data.get("store_type", -1)), items=items)


def _parse_items(items_data: Any) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for item_data in items_data or []:
        items.append(
            InventoryItem(
                slot=str(item_data.get("slot", "")),
                name=str(item_data.get("name", "")),
                count=int(item_data.get("count", 1)),
                tval=int(item_data.get("tval", 0)),
                sval=int(item_data.get("sval", -1)),
                aware=_as_bool(item_data.get("aware", False)),
                known=_as_bool(item_data.get("known", False)),
                charges=int(item_data.get("charges", 0)),
            )
        )
    return items
