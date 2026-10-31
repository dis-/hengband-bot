"""The Magic-Eater's absorbed utility powers as one table (owner 2026-10-31, #47).

Owner: 「魔道具術師の二段階目で取り込んだ魔法道具の使用ロジックを作る。それぞれ効果を
確認して使用ルールを提案。」 -> on the proposal: 「案はこれで良い。今後条件を追加する
可能性があること、取り込み魔法道具は今後も増えることに留意して保守性を維持するように
作って。」 (memory me-stage2-power-usage-decision-20261031).

Effects (the game's source; ``do_cmd_magic_eater`` calls ``staff_effect`` with
powerful=false, cmd-item/cmd-magiceat.cpp:577):
 - 周辺感知 (sval 9): map_area(DETECT_RAD_MAP 30), terrain only, no secret doors
   (spell-kind/spells-floor.cpp:153-199).
 - ドア/階段感知 (13): detect_doors + detect_stairs (30), discloses secret doors.
 - 邪悪存在感知 (15): detect_monsters_evil (30); the marked monsters go to the
   existing detected-threat rungs (no new retreat rule).
 - トラップ感知 (12): detect_traps (30, known): CAVE_IN_DETECT within range - 1
   (spells-detection.cpp:73-77).  The area is not on the board, so it is
   remembered here from the use points (trap-detect-rod-only, 2026-10-23).
 - 光 (8): lite_area(2d8, radius 2) and lite_room; nothing in a DARKNESS
   dungeon (spell-kind/spells-lite.cpp:331-348).
Every detection and mapping radius is a third in a DARKNESS dungeon.  A failed
cast (「呪文をうまく唱えられなかった！」) takes a turn and keeps the charge.

One row of ``POWERS`` per power: its kind/sval (the key is ``m`` + kind +
I2A(sval)), the effect, the named triggers, a priority, an optional fallback
(served when the row's own power has no charge) and named requirements.  A
trigger is a small named predicate in ``TRIGGERS`` with the decision
occasions that ask it (``power_key`` is called from the dungeon ladder with
one occasion: the floor rung after the survival rungs, the dark-locomotion
rung, the rest rung and the secret-wall search rung).  Adding a power is one
row; adding a condition is one predicate and its name in a row.

Common rules (approved): never while a hostile is visible or the character
was just hit, never with 0 charges (the last list the game displayed, else
the absorption record), never in town or the wilderness, and a failed use is
retried for the same trigger at the same place on the same floor until
``FAILURES_PER_PLACE`` failures (owner 2026-10-31 「最大5回まで同じ場所で試す」).
Stage 1 (Identify, Treasure Location) keeps its owners in me_staff_sequence
and policy_fundraising.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.me_device_attacks import observe_lists
from hengbot.me_staff_sequence import (
    POWER_NAMES, SV_STAFF_DETECT_DOOR, SV_STAFF_DETECT_EVIL, SV_STAFF_DETECT_TRAP,
    SV_STAFF_LITE, SV_STAFF_MAPPING, absorbed_charges,
)
from hengbot.model import Position
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY


REASON = "me-power"
MEMORY = "_me_power_floor"
# Decision occasions (the ladder rungs that ask the table).
FLOOR = "floor"
DARK = "dark"
REST = "rest"
SECRET_SEARCH = "secret-search"

DETECT_RAD = 30          # spell/spells-util.h DETECT_RAD_DEFAULT / DETECT_RAD_MAP
LITE_RADIUS = 2          # cmd-usestaff.cpp lite_area(..., 2)
F_LIT_STANDARD = 0       # terrain-definition.h: a glowing grid in view
# A room's edge cell has five floor neighbours; a dungeon tunnel is one cell
# wide (an open space, not a corridor, is what lite_room can light).
OPEN_SPACE_NEIGHBOURS = 5
# Failed casts of one power for one trigger at one place before it is given
# up there (owner 2026-10-31 「最大5回まで同じ場所で試す」).
FAILURES_PER_PLACE = 5
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)

# cmd-magiceat.cpp: the kind question ([A] staff, [B] wand, [C] rod) and the
# power letter, I2A(sval) below 26, then '0' + sval - 26.
KIND_LETTER = {"staff": "A", "wand": "B", "rod": "C"}


def encode_letter(sval: int) -> str:
    return chr(ord("a") + sval) if sval < 26 else str(sval - 26)


def decode_letter(letter: str) -> int:
    return ord(letter) - ord("a") if letter.isalpha() else int(letter) + 26


def kind_of(letter: str) -> str:
    return next(kind for kind, each in KIND_LETTER.items() if each == letter)


@dataclass(frozen=True)
class Power:
    kind: str
    sval: int
    names: tuple[str, str]       # the list's baseitem name (ja, en)
    effect: str
    radius: int
    priority: int
    triggers: tuple[str, ...]
    fallback: tuple | None = None  # (kind, sval) served when this has no charge
    requires: tuple[str, ...] = ()
    darkness_scaled: bool = True  # radius / 3 in a DARKNESS dungeon
    aimed: bool = False           # me_device_attacks_input asks no direction

    @property
    def ident(self) -> tuple:
        # (kind, sval): staff 15 (Detect Evil) is not wand 15 (Magic Missile).
        return (self.kind, self.sval)

    @property
    def letter(self) -> str:
        return encode_letter(self.sval)

    @property
    def key(self) -> str:
        return "m" + KIND_LETTER[self.kind] + self.letter


POWERS = (
    Power("staff", SV_STAFF_DETECT_EVIL, POWER_NAMES[SV_STAFF_DETECT_EVIL],
          "detect-evil", DETECT_RAD, 10, ("new-floor", "before-rest")),
    Power("staff", SV_STAFF_DETECT_TRAP, POWER_NAMES[SV_STAFF_DETECT_TRAP],
          "detect-traps", DETECT_RAD, 20, ("new-floor", "left-detected-trap-area")),
    Power("staff", SV_STAFF_MAPPING, POWER_NAMES[SV_STAFF_MAPPING],
          "map-area", DETECT_RAD, 30, ("new-floor", "stairs-needed-and-unknown"),
          fallback=("staff", SV_STAFF_DETECT_DOOR)),
    Power("staff", SV_STAFF_DETECT_DOOR, POWER_NAMES[SV_STAFF_DETECT_DOOR],
          "detect-doors-stairs", DETECT_RAD, 40, ("before-secret-search",)),
    Power("staff", SV_STAFF_LITE, POWER_NAMES[SV_STAFF_LITE],
          "lite-area", LITE_RADIUS, 50,
          ("light-radius-zero", "dark-room", "light-sensitive-adjacent"),
          requires=("not-darkness-dungeon",), darkness_scaled=False),
)
BY_KEY = {power.ident: power for power in POWERS}


@dataclass(frozen=True)
class Use:
    served: tuple      # (kind, sval) of the row whose trigger fired
    used: tuple        # (kind, sval) cast: the row's own power or its fallback
    trigger: str
    position: Position
    turn: int
    reason: str = ""


@dataclass
class FloorMemory:
    """What the powers did on the current floor visit (reset on a floor change)."""
    floor: tuple
    turn: int
    uses: list = field(default_factory=list)
    failed: Counter = field(default_factory=Counter)  # (used ident, trigger, position) -> failures
    pending: Use | None = None


@dataclass(frozen=True)
class Context:
    policy: object
    snapshot: object
    occasion: str
    memory: FloorMemory

    @property
    def position(self) -> Position:
        return self.snapshot.player.position

    def distance(self, other: Position) -> int:
        return game_distance(self.position, other)

    def uses_of(self, power: Power) -> list:
        """Uses that served this row or cast this power."""
        return [use for use in self.memory.uses if power.ident in (use.served, use.used)]

    def darkness(self) -> bool | None:
        info = getattr(self.policy, "_dungeon_knowledge", {}).get(self.snapshot.floor_key[0])
        return None if info is None else "DARKNESS" in info.flags

    def radius(self, power: Power) -> int:
        if power.darkness_scaled and self.darkness():
            return power.radius // 3
        return power.radius


def game_distance(a: Position, b: Position) -> int:
    """Grid::calc_distance (system/grid-type-definition.cpp:19-38)."""
    dy, dx = abs(a.y - b.y), abs(a.x - b.x)
    distance = max(dy, dx) + min(dy, dx) // 2
    if dy == 0 or dx == 0:
        return distance
    squared = dy * dy + dx * dx
    while True:
        # C++ integer division truncates toward zero (Python's // floors).
        numerator = squared - distance * distance
        error = abs(numerator) // (2 * distance) * (1 if numerator >= 0 else -1)
        if error == 0:
            return distance
        distance += error


# -- triggers: one named predicate each ---------------------------------------

def _new_floor(ctx, power):
    return not ctx.uses_of(power)


def _needed_stairs(ctx):
    """'up' while returning on foot, 'down' while descending, else None."""
    policy, snapshot = ctx.policy, ctx.snapshot
    if policy._returning_to_town:
        if snapshot.player.recalling or policy._count_recall_scrolls(snapshot) > 0:
            return None
        return "up"
    return None if policy._descent_is_blocked(snapshot) else "down"


def _stairs_known(ctx, needed):
    policy, grids = ctx.policy, ctx.snapshot.grids.values()
    if needed == "down":
        return bool(policy._remembered_downstairs) or any(g.has_down_stairs for g in grids)
    return any(policy._is_upstairs_target(g) for g in grids)


def _stairs_needed_and_unknown(ctx, power):
    # Again only DETECT_RAD from every earlier use (the area it mapped).
    radius = ctx.radius(power)
    if any(ctx.distance(use.position) < radius for use in ctx.uses_of(power)):
        return False
    needed = _needed_stairs(ctx)
    return needed is not None and not _stairs_known(ctx, needed)


def _before_rest(ctx, power):
    return not any(use.position == ctx.position for use in ctx.uses_of(power))


def _before_secret_search(ctx, power):
    radius = ctx.radius(power)
    return all(ctx.distance(use.position) >= radius for use in ctx.uses_of(power))


def _left_detected_trap_area(ctx, power):
    # CAVE_IN_DETECT is set within range - 1 of each use: on its edge the
    # next step can leave the area.
    edge = ctx.radius(power) - 1
    uses = ctx.uses_of(power)
    return bool(uses) and all(ctx.distance(use.position) >= edge for use in uses)


def _light_radius_zero(ctx, power):
    return ctx.policy._is_dark(ctx.snapshot)


def _floor_cell(grid):
    return (grid is not None and grid.known and grid.passable
            and not grid.wall and not grid.is_door)


def _dark_room(ctx, power):
    """An open space whose floor beyond the light radius is not lit.

    The board carries no CAVE_ROOM; protocol 3 prints a glowing floor in
    view as F_LIT_STANDARD (view/display-map.cpp:169-183), so a lit room
    shows its floor beyond the player's light and a dark one does not.
    """
    snapshot = ctx.snapshot
    radius = snapshot.light_radius
    if (not isinstance(radius, int) or radius < 1 or ctx.policy._is_dark(snapshot)
            or any(ctx.distance(use.position) <= power.radius for use in ctx.uses_of(power))):
        return False
    here = ctx.position
    open_cells = sum(_floor_cell(snapshot.grid_at(Position(here.y + dy, here.x + dx)))
                     for dy, dx in _NEIGHBOURS)
    if open_cells < OPEN_SPACE_NEIGHBOURS:
        return False
    ring = [Position(here.y + dy, here.x + dx)
            for dy in range(-radius - 1, radius + 2) for dx in range(-radius - 1, radius + 2)
            if game_distance(here, Position(here.y + dy, here.x + dx)) == radius + 1]
    grids = [snapshot.grid_at(cell) for cell in ring]
    if any(_floor_cell(grid) and grid.map_lighting == F_LIT_STANDARD for grid in grids):
        return False
    return any(grid is None or not grid.known for grid in grids)


def _light_sensitive_adjacent(ctx, power):
    """A detected (not visible) hostile beside the player that light hurts."""
    races = ctx.policy._monrace_knowledge
    return any(
        monster.hostile and ctx.position.distance_to(monster.position) <= 1
        and "HURT_LITE" in getattr(races.get(monster.race_id), "flags", ())
        for monster in ctx.snapshot.detected_monsters)


@dataclass(frozen=True)
class Trigger:
    name: str
    occasions: frozenset
    due: Callable


TRIGGERS = {trigger.name: trigger for trigger in (
    Trigger("new-floor", frozenset({FLOOR}), _new_floor),
    Trigger("stairs-needed-and-unknown", frozenset({FLOOR}), _stairs_needed_and_unknown),
    Trigger("before-rest", frozenset({REST}), _before_rest),
    Trigger("before-secret-search", frozenset({SECRET_SEARCH}), _before_secret_search),
    Trigger("left-detected-trap-area", frozenset({FLOOR}), _left_detected_trap_area),
    Trigger("light-radius-zero", frozenset({DARK}), _light_radius_zero),
    Trigger("dark-room", frozenset({FLOOR}), _dark_room),
    Trigger("light-sensitive-adjacent", frozenset({FLOOR, DARK}), _light_sensitive_adjacent),
)}

REQUIREMENTS = {
    # Never in a DARKNESS dungeon (lite_area does nothing); unknown is not proof.
    "not-darkness-dungeon": lambda ctx: ctx.darkness() is False,
}


# -- charges, gates and the producer ------------------------------------------

def charges(policy, snapshot, power: Power) -> int:
    """The power's charges in the last list the game displayed for its kind.

    Before any list of that kind was displayed in this life, the absorption
    record (me_staff_sequence.absorbed_charges) serves a staff.
    """
    lists = getattr(policy, "_me_device_lists", None) or {}
    if power.kind not in lists:
        return absorbed_charges(policy, snapshot, power.sval) if power.kind == "staff" else 0
    row = next((row for row in lists[power.kind][1] if row.get("name") in power.names), None)
    if row is None:
        return 0
    if power.kind == "rod":
        charging, count = row.get("charging"), row.get("max")
        return count - charging if isinstance(charging, int) and isinstance(count, int) else 0
    current = row.get("current")
    return current if isinstance(current, int) else 0


def _gate(policy, snapshot) -> bool:
    player = snapshot.player
    return (
        player.class_id == PLAYER_CLASS_MAGIC_EATER
        and getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) >= PROTOCOL_SCREEN_PARITY
        and not snapshot.in_town and not snapshot.on_open_wilderness
        and snapshot.dungeon_level > 0 and snapshot.store is None
        and not (player.blind or player.confused or player.hallucinated or player.paralyzed)
        and not policy._physical_hostiles(snapshot)
        and not getattr(policy, "_took_damage", False)
    )


def observe(policy, snapshot) -> None:
    """Every decision: remember the displayed lists, settle the previous use."""
    observe_lists(policy, snapshot)
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        setattr(policy, MEMORY, None)
        return
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key or snapshot.turn < memory.turn:
        setattr(policy, MEMORY, FloorMemory(snapshot.floor_key, snapshot.turn))
        return
    pending = memory.pending
    if pending is not None:
        if snapshot.completed_operation_owner == pending.reason:
            refusal = (snapshot.completed_operation_receipt or {}).get("refusal")
            if isinstance(refusal, str) and refusal.startswith("failed"):
                memory.failed[(pending.used, pending.trigger, pending.position)] += 1
            elif snapshot.turn > pending.turn:
                memory.uses.append(pending)
            # Same turn, no refusal: the list closed the prompt (no charge).
            memory.pending = None
        elif snapshot.turn != pending.turn:
            memory.pending = None
    memory.turn = snapshot.turn


def _usable(ctx, power, trigger) -> bool:
    return (all(REQUIREMENTS[name](ctx) for name in power.requires)
            and ctx.memory.failed[(power.ident, trigger, ctx.position)] < FAILURES_PER_PLACE
            and charges(ctx.policy, ctx.snapshot, power) > 0)


def _serving(ctx, power, trigger):
    """The row's own power, or its fallback when the row has no charge."""
    if charges(ctx.policy, ctx.snapshot, power) > 0:
        return power if _usable(ctx, power, trigger) else None
    fallback = BY_KEY.get(power.fallback) if power.fallback is not None else None
    return fallback if fallback is not None and _usable(ctx, fallback, trigger) else None


def power_key(policy, snapshot, occasion: str) -> str | None:
    """``m`` + kind + power of the first due power for ``occasion``, else None."""
    if not _gate(policy, snapshot):
        return None
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return None
    ctx = Context(policy, snapshot, occasion, memory)
    for power in sorted(POWERS, key=lambda each: each.priority):
        for name in power.triggers:
            trigger = TRIGGERS[name]
            if occasion not in trigger.occasions or not trigger.due(ctx, power):
                continue
            used = _serving(ctx, power, name)
            if used is None:
                continue
            reason = f"{REASON}:{name}:{used.effect}"
            policy.last_reason = reason
            policy._offer_execution(
                used.key, producer="detectors", work_id=f"{REASON}:{used.effect}",
                next_step="magic-eater.power.send", arguments=(used.kind, used.sval, name),
                expected_effect=used.effect,
            )
            memory.pending = Use(power.ident, used.ident, name, ctx.position, snapshot.turn, reason)
            return used.key
    return None
