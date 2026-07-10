from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Position:
    y: int
    x: int

    def distance_to(self, other: "Position") -> int:
        return max(abs(self.y - other.y), abs(self.x - other.x))


@dataclass(frozen=True)
class PlayerState:
    position: Position
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    level: int

    @property
    def hp_ratio(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return self.hp / self.max_hp


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


@dataclass(frozen=True)
class MonsterState:
    index: int
    position: Position
    hp: int
    max_hp: int
    distance: int
    friendly: bool
    pet: bool

    @property
    def hostile(self) -> bool:
        return not self.friendly and not self.pet


@dataclass(frozen=True)
class Snapshot:
    player: PlayerState
    grids: dict[Position, GridState]
    visible_monsters: list[MonsterState]
    turn: int = 0
    dungeon_turn: int = 0
    floor_key: tuple[int, int, int] = (0, 0, 0)


def parse_snapshot(data: dict[str, Any]) -> Snapshot:
    player_data = data["player"]
    player = PlayerState(
        position=Position(int(player_data["y"]), int(player_data["x"])),
        hp=int(player_data["hp"]),
        max_hp=int(player_data["max_hp"]),
        mp=int(player_data["mp"]),
        max_mp=int(player_data["max_mp"]),
        level=int(player_data["level"]),
    )

    grids: dict[Position, GridState] = {}
    for grid_data in data.get("nearby_grids", []):
        pos = Position(int(grid_data["y"]), int(grid_data["x"]))
        terrain = grid_data.get("terrain", {})
        flags = grid_data.get("flags", {})
        known = bool(grid_data.get("known", flags.get("known", False)))
        monster_index = int(grid_data.get("monster_index", 0))
        grids[pos] = GridState(
            position=pos,
            known=known,
            passable=known and bool(terrain.get("move", False)),
            wall=known and bool(terrain.get("wall", False)),
            has_monster=known and monster_index > 0,
            has_down_stairs=known and bool(terrain.get("down_stairs", False)),
            has_up_stairs=known and bool(terrain.get("up_stairs", False)),
            unsafe=known and bool(flags.get("unsafe", False)),
        )

    monsters = [
        MonsterState(
            index=int(monster_data["index"]),
            position=Position(int(monster_data["y"]), int(monster_data["x"])),
            hp=int(monster_data["hp"]),
            max_hp=int(monster_data["max_hp"]),
            distance=int(monster_data["distance"]),
            friendly=bool(monster_data["friendly"]),
            pet=bool(monster_data["pet"]),
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
    )
