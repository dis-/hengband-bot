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
 - トラップ解除 (rod 14, wand 4): disarm_trap(dir) (cmd-zaprod.cpp:168,
   cmd-zapwand.cpp:118; spell-kind/spells-beam.cpp:50), a PROJECT_THRU beam
   of KILL_TRAP (effect/effect-feature.cpp:156): removes the traps on its
   line, discloses secret doors and unlocks doors; on a chest it removes the
   trap and the lock (effect/effect-item.cpp:201).
 - トラップ/ドア破壊 (wand 5): destroy_door(dir) (spells-beam.cpp:38), KILL_DOOR
   (effect-feature.cpp:191): destroys the traps and the doors on its line.
   Both are aimed (get_aim_dir, cmd-magiceat.cpp:543,563).  Owner 2026-11-01
   「魔道具術師が罠を解除するとき、トラップ解除やトラップ/ドア破壊を取り込み済なら
   使用する」: they are asked with the trap the bot would disarm (the walk's
   trap step, policy_navigation._step_toward, or the chest pipeline's disarm
   phase) and the disarm command stays the fallback.
 - テレポート・アウェイ (rod 13, wand 3): teleport_monster(dir, MAX_PLAYER_SIGHT
   * 5) (cmd-zaprod.cpp:160, cmd-zapwand.cpp:110; spell-kind/spells-teleport.cpp:91),
   a PROJECT_BEAM of AWAY_ALL along the aimed line up to the projection range
   (project_hook): every monster on it is teleported away unless it resists
   (effect/effect-monster-evil.cpp:7-30 effect_monster_away_resist: only a
   RES_TELE race resists, always when it is also UNIQUE or RES_ALL, else when
   its level beats randint1(100)).  Owner 2026-11-01 (#47 D57) 「勝てない敵が
   射程内にいればいつでも使って良い」: aimed at a visible hostile the
   engagement judgement (``_engagement_is_winnable`` on that monster, with the
   damage per action me_ranged_first would deal beside it) says cannot be
   beaten, whether or not a scroll could be read.  ``threat_key`` asks the
   THREAT occasion once per visible hostile, nearest first, from the dungeon
   ladder after the emergency consumables.  Owner 2026-11-02 「テレポート
   アウェイがあるなら初手でフォルンをどかす。」: the QUEST_OPENING occasion is
   asked with a quest plan's opening target (quest_opening_away).
 - 全感知 (rod 6): detect_all(detect_rad) (cmd-item/cmd-zaprod.cpp:107,
   spell-kind/spells-detection.cpp:622): traps, doors, stairs, gold, objects,
   invisible and normal monsters, a superset of detect_monsters_evil.  Owner
   2026-11-01 「全感知のロッドの使い方について　邪悪感知を使うタイミングで全感知が
   使用可能なら代わりに使用する。安全なら強力発動で使う。」: the Detect Evil row
   names it ``preferred`` (cast in the row's place whenever it is usable), and
   its row's ``powerful`` "when-safe" casts it through Powerful Activation
   (me_powerful_activation; rod_effect's powerful radius is DETECT_RAD * 3 / 2,
   cmd-zaprod.cpp:50, for the same charge, cmd-magiceat.cpp:488).
 - Hunting (owner 2026-11-02 「ランダムクエスト討伐対象やガーディアンを討伐するとき、
   対象が邪悪なら邪悪感知を用いて探す」, 「全感知を使うケースは対象が邪悪であることに
   拘らない」): the "hunt-target-unseen" trigger of both rows asks hunt_target
   for the hunted race shown nowhere; a row casts only when its effect reveals
   that race (hunt_target.REVEALS), so Detect Evil searches for an EVIL target
   and the rod for any.  hunt_target.route_key then walks to the shown cell.
 - スピード (staff 22): set_acceleration, 16-45 turns (speed_dose).  Owner 2026-11-04
   「魔道具術師　取り込んだスピードが残10回以上なら、特にピンチでなくても戦闘時加速する」
   「成功率8割以上のときに限定して」: ``fight_key`` asks the FIGHT occasion in place of a
   decided attack on an awake hostile (attack_answer), after every survival rung.
 - 50F+ (PLAN-50F section 4, owner 2026-11-11 for C6 「2 3 5を入れる」): 4.3 the Detect Evil row
   (and its preferred rod) is cast again once the player stands DEEP_REDETECT_WALK from the
   floor's latest landed monster detection (``deep-explore-redetect``); 4.4 a dark room is not
   lit while a strong sleeper is in the room light's reach (``strong_sleepers_in_light_reach``);
   4.9 the Speed row is also cast on the floor rung once per floor visit while not hasted
   (``deep-arrival-unhasted``).
Every detection and mapping radius is a third in a DARKNESS dungeon.  A failed
cast (「呪文をうまく唱えられなかった！」) takes a turn and keeps the charge.

One row of ``POWERS`` per power: its kind/sval (the key is ``m`` + kind +
I2A(sval)), the effect, the named triggers, a priority, optional preferred
powers (served in the row's place, at its triggers, whenever usable), an
optional fallback (served when the row's own power has no charge), named
requirements and an optional ``POWERFUL`` condition (when it holds the power
is cast through Powerful Activation, ``U`` + kind + I2A(sval)).  A
trigger is a small named predicate in ``TRIGGERS`` with the decision
occasions that ask it (``power_key`` is called from the dungeon ladder with
one occasion: the floor rung after the survival rungs, the dark-locomotion
rung, the rest rung and the secret-wall search rung; the trap occasion
comes with the trap to aim at).  Adding a power is one
row; adding a condition is one predicate and its name in a row.

Common rules (approved): never while a hostile is visible or the character
was just hit (a row marked ``beside_harmless`` is also cast while every
visible hostile is harmless by the combat ladder's danger judgement, owner
2026-11-01 「脅威でなければ感知する」; the disarming rows likewise, owner
2026-11-01 「脅威でなければ使う」; a row marked ``against_hostile`` is cast
at a hostile, so neither rule applies to it), never with 0 charges (``me_capability.charges``: the last list the
game displayed, else the absorption record), never in town or the wilderness, and a failed use is
retried for the same trigger at the same place on the same floor until
``FAILURES_PER_PLACE`` failures (owner 2026-10-31 「最大5回まで同じ場所で試す」).
Stage 1 (Identify, Treasure Location) keeps its owners in me_staff_sequence
and policy_fundraising.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Callable

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER, power_command_refused
from hengbot.me_device_attacks import observe_lists
from hengbot.me_staff_sequence import (
    POWER_NAMES, SV_STAFF_DETECT_DOOR, SV_STAFF_DETECT_EVIL, SV_STAFF_DETECT_TRAP,
    SV_STAFF_LITE, SV_STAFF_MAPPING,
)
from hengbot import attack_answer, hunt_target, me_capability, me_power_success, me_ranged_first
from hengbot.me_device_policy import devices
from hengbot.model import (
    SV_ROD_DETECTION, SV_ROD_DISARMING, SV_ROD_MAPPING, SV_ROD_TELEPORT_AWAY, SV_STAFF_SPEED, SV_WAND_DISARMING,
    SV_WAND_TELEPORT_AWAY,
    SV_WAND_TRAP_DOOR_DEST, TVAL_ROD, TVAL_WAND, Position, game_distance,
)
from hengbot.policy_constants import DIRECTION_KEYS, MONSTER_SPELL_MAX_RANGE
from hengbot.projection_path import projection_path
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY


REASON = "me-power"
MEMORY = "_me_power_floor"
# Decision occasions (the ladder rungs that ask the table).
FLOOR = "floor"
DARK = "dark"
REST = "rest"
SECRET_SEARCH = "secret-search"
TRAP = "trap"            # asked with the trap the bot would disarm
TRAP_CELL = "trap-cell"  # asked by quest25_battle for a map trap cell not yet settled
THREAT = "threat"        # asked with each visible hostile (threat_key)
QUEST_OPENING = "quest-opening"  # asked with a quest plan's opening target (quest_opening_away)
FIGHT = "fight"          # asked in place of a decided attack (fight_key)
SEALED = "sealed"        # asked by area_mapping in a sealed pocket
MAP_AREA = "map-area"    # the effect whose area mapped_area reads

DETECT_RAD = 30          # spell/spells-util.h DETECT_RAD_DEFAULT / DETECT_RAD_MAP
LITE_RADIUS = 2          # cmd-usestaff.cpp lite_area(..., 2)
F_LIT_STANDARD = 0       # terrain-definition.h: a glowing grid in view
# A room's edge cell has five floor neighbours; a dungeon tunnel is one cell
# wide (an open space, not a corridor, is what lite_room can light).
OPEN_SPACE_NEIGHBOURS = 5
# Failed casts of one power for one trigger at one place before it is given
# up there (owner 2026-10-31 「最大5回まで同じ場所で試す」).
FAILURES_PER_PLACE = 5
# Owner 2026-11-04 「残10回以上」: the Speed row's charges.
FIGHT_SPEED_MIN_CHARGES = 10
# cmd-usestaff.cpp set_acceleration(randint1(30) + 15), one tick per 10 game turns:
# the shortest haste, for the boards whose speed field cannot show it (at +0 it is
# blank, _player_hasted).
HASTE_MIN_GAME_TURNS = 160
# PLAN-50F (deep-dive 2026-11-10/11, section 4), owner 2026-11-11 for its C6 「2 3 5を入れる」:
# items 2 (4.3 detection cadence), 3 (4.4 lighting rooms) and 5 (4.9 speed), each "only on
# 50F+" (the plan's floors where 「50F以降は敵が強い」).
DEEP_FLOOR_MIN_DEPTH = 50
# 4.3 「Re-detect after walking 25 cells from the last detection (half of DETECT_RAD 30 +
# margin)」: game distance from the latest landed monster detection of the floor visit.
DEEP_REDETECT_WALK = 25
# 4.4: how far the room light reaches from the player's cell.  lite_area lights radius 2 and
# calls lite_room (spell-kind/spells-lite.cpp:332-347), which floods from the player through LOS
# terrain (:225-251): a CAVE_ROOM grid at any distance, any other grid only within
# get_max_range() 18 (cave_temp_room_aux :189-216, system/angband-system.cpp:45-48).  Every
# monster on a lit grid that is asleep wakes: SMART always, STUPID 1 in 10, others 1 in 4
# (cave_temp_room_lite :45-77).  The board carries no CAVE_ROOM, so the reach is across the
# widest ordinary room: type 1 is 2d11+1 by up to 8 floor cells (room/rooms-normal.cpp:29-31),
# game distance 22 + 7/2 = 25.
LITE_ROOM_REACH = 25
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
    preferred: tuple = ()          # (kind, sval) served in this row's place when usable
    powerful: str | None = None    # a POWERFUL condition: then cast by Powerful Activation
    requires: tuple[str, ...] = ()
    darkness_scaled: bool = True  # radius / 3 in a DARKNESS dungeon
    aimed: bool = False           # me_device_attacks_input asks no direction
    beside_harmless: bool = False  # also while the visible hostiles are not a threat
    against_hostile: bool = False  # cast at a hostile: the hostile/hit rules do not apply

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
    # Owner 2026-11-01 「邪悪感知を使うタイミングで全感知が使用可能なら代わりに使用する。
    # 安全なら強力発動で使う。」: the rod serves the Detect Evil row's triggers.
    # Owner 2026-11-02 「対象が邪悪であることに拘らない」: the rod's own trigger
    # searches for any hunted race; the Detect Evil row's only for an EVIL one.
    Power("staff", SV_STAFF_DETECT_EVIL, POWER_NAMES[SV_STAFF_DETECT_EVIL],
          "detect-evil", DETECT_RAD, 10,
          ("new-floor", "before-rest", "hunt-target-unseen", "deep-explore-redetect"),
          preferred=(("rod", SV_ROD_DETECTION),)),
    Power("rod", SV_ROD_DETECTION, devices()[(TVAL_ROD, SV_ROD_DETECTION)].names,
          "detect-all", DETECT_RAD, 10, ("hunt-target-unseen",), powerful="when-safe"),
    Power("staff", SV_STAFF_DETECT_TRAP, POWER_NAMES[SV_STAFF_DETECT_TRAP],
          "detect-traps", DETECT_RAD, 20, ("new-floor", "left-detected-trap-area", "trap-cell-unsettled")),
    Power("staff", SV_STAFF_MAPPING, POWER_NAMES[SV_STAFF_MAPPING],
          MAP_AREA, DETECT_RAD, 30,
          ("after-destruction", "new-floor", "stairs-needed-and-unknown", "sealed-pocket",
           "loot-unreachable"),
          fallback=("staff", SV_STAFF_DETECT_DOOR), beside_harmless=True),
    # The same effect (cmd-zaprod.cpp:102), asked only where the owner named 周辺感知.
    Power("rod", SV_ROD_MAPPING, me_capability.names("rod", SV_ROD_MAPPING),
          MAP_AREA, DETECT_RAD, 31, ("after-destruction", "sealed-pocket"), beside_harmless=True),
    Power("staff", SV_STAFF_DETECT_DOOR, POWER_NAMES[SV_STAFF_DETECT_DOOR],
          "detect-doors-stairs", DETECT_RAD, 40, ("before-secret-search",)),
    Power("staff", SV_STAFF_LITE, POWER_NAMES[SV_STAFF_LITE],
          "lite-area", LITE_RADIUS, 50,
          ("light-radius-zero", "dark-room", "light-sensitive-adjacent"),
          requires=("not-darkness-dungeon",), darkness_scaled=False),
    # The Disarming powers keep the doors, so they come first; the rod
    # is ready again sooner than the wand (both refill, me_device_attacks' regenmagic
    # note), so it comes before the wand.  Owner 2026-11-01 「脅威でなければ
    # 使う」: beside harmless visible hostiles, as the mapping.
    Power("rod", SV_ROD_DISARMING, devices()[(TVAL_ROD, SV_ROD_DISARMING)].names,
          "disarm-trap", 0, 60, ("trap-to-disarm",), darkness_scaled=False, aimed=True,
          beside_harmless=True),
    Power("wand", SV_WAND_DISARMING, devices()[(TVAL_WAND, SV_WAND_DISARMING)].names,
          "disarm-trap", 0, 61, ("trap-to-disarm",), darkness_scaled=False, aimed=True,
          beside_harmless=True),
    Power("wand", SV_WAND_TRAP_DOOR_DEST, devices()[(TVAL_WAND, SV_WAND_TRAP_DOOR_DEST)].names,
          "destroy-trap-door", 0, 62, ("trap-to-disarm",), darkness_scaled=False, aimed=True,
          beside_harmless=True),
    # The rod is ready again sooner than the wand (both refill, me_device_attacks'
    # regenmagic note), so it comes before the wand.
    Power("rod", SV_ROD_TELEPORT_AWAY, devices()[(TVAL_ROD, SV_ROD_TELEPORT_AWAY)].names,
          "teleport-away", 0, 70, ("unbeatable-in-range", "quest-opening-target"),
          darkness_scaled=False,
          aimed=True, against_hostile=True),
    Power("wand", SV_WAND_TELEPORT_AWAY, devices()[(TVAL_WAND, SV_WAND_TELEPORT_AWAY)].names,
          "teleport-away", 0, 71, ("unbeatable-in-range", "quest-opening-target"),
          darkness_scaled=False,
          aimed=True, against_hostile=True),
    Power("staff", SV_STAFF_SPEED, me_capability.names("staff", SV_STAFF_SPEED),
          "speed", 0, 80, ("fight-unhasted", "deep-arrival-unhasted"),
          requires=("fight-speed-charges", "speed-reliable"),
          darkness_scaled=False, against_hostile=True),
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
    key: str = ""                   # the posted key (an aimed power's ends in its direction)
    target: Position | None = None  # what an aimed power was aimed at
    map_forgotten: bool = False     # a *Destruction* wiped what this mapping showed


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
    target: Position | None = None  # the trap of the TRAP occasion, the hostile of THREAT

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

    def radius(self, power: Power, *, unknown_is_dark: bool = False) -> int:
        """The power's radius here; ``unknown_is_dark`` takes the DARKNESS third
        when the dungeon is not in the knowledge (the smaller area is the safe
        reading of what a cast covered)."""
        darkness = self.darkness()
        if power.darkness_scaled and (darkness or (unknown_is_dark and darkness is None)):
            return power.radius // 3
        return power.radius

    @property
    def aim(self) -> str | None:
        """The direction key of a beam that reaches ``target``, else None."""
        return None if self.target is None else beam_direction(
            self.policy, self.snapshot, self.position, self.target)

    @cached_property
    def target_hostile(self):
        """The visible hostile on ``target``, else None."""
        return next((monster for monster in self.policy._physical_hostiles(self.snapshot)
                     if monster.position == self.target), None)

    @cached_property
    def hostile_visible(self) -> bool:
        return bool(self.policy._physical_hostiles(self.snapshot))

    @cached_property
    def threat_visible(self) -> bool:
        return visible_threat(self.policy, self.snapshot)


def beam_direction(policy, snapshot, origin: Position, target: Position) -> str | None:
    """The direction key whose beam reaches ``target``, else None.

    project_hook aims one grid away in the direction with PROJECT_THRU
    (spell-kind/spells-launcher.cpp:262-267, floor/geometry.h:203-210), so the
    beam runs the straight line up to get_max_range(); a known grid that stops
    the player's projection ends it (policy._stops_player_projection: a glass wall
    too).
    """
    dy, dx = target.y - origin.y, target.x - origin.x
    if (dy, dx) == (0, 0) or not (dy == 0 or dx == 0 or abs(dy) == abs(dx)):
        return None
    step = ((dy > 0) - (dy < 0), (dx > 0) - (dx < 0))
    path = projection_path(
        origin, Position(origin.y + step[0], origin.x + step[1]), MONSTER_SPELL_MAX_RANGE,
        lambda position: policy._stops_player_projection(snapshot, position), through=True)
    return DIRECTION_KEYS[step] if target in path else None


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
    """A stair the navigation owner would still walk to (its own predicate)."""
    policy, snapshot = ctx.policy, ctx.snapshot
    if needed == "down":
        return bool(policy._usable_downstairs(snapshot))
    return any(policy._is_upstairs_target(g) for g in snapshot.grids.values())


def _stairs_needed_and_unknown(ctx, power):
    # Again only DETECT_RAD from every earlier use (the area it mapped).
    radius = ctx.radius(power)
    if any(ctx.distance(use.position) < radius for use in ctx.uses_of(power)):
        return False
    needed = _needed_stairs(ctx)
    return needed is not None and not _stairs_known(ctx, needed)


def _loot_unreachable(ctx, power):
    """Owner 2026-11-13 「経路が見つからない時に周辺感知を使う」: the loot walk found loot it saw with
    no known way to it on the last boards (loot_frontier), and no earlier use mapped here."""
    from hengbot import loot_frontier

    radius = ctx.radius(power)
    if any(ctx.distance(use.position) < radius for use in ctx.uses_of(power)):
        return False
    return loot_frontier.unreachable_recently(ctx.policy, ctx.snapshot, LOOT_UNREACHABLE_GAME_TURNS)


# The loot walk's note stays fresh for one player turn at normal speed and a few boards beyond.
LOOT_UNREACHABLE_GAME_TURNS = 30


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
    if not any(grid is None or not grid.known for grid in grids):
        return False
    return not (_deep_floor(ctx) and strong_sleepers_in_light_reach(ctx.policy, snapshot))


def strong_sleepers_in_light_reach(policy, snapshot) -> list:
    """PLAN-50F 4.4 (owner 2026-11-11 C6 「3」): the room light wakes the sleepers it reaches
    (LITE_ROOM_REACH), so on 50F+ a dark room is not lit while the board shows -- in view, by
    telepathy or by a detection -- a strong one asleep within that reach.  Strong is the
    judgment the owner's 11-07 rule keeps away from even asleep (「強い敵からは離れる」): the
    engagement retreat's own, ``_material_melee_fight`` (its melee over the engagement horizon
    is a material share of HP, or disenchant_avoid keeps away from it), as policy_quest reads it.
    The light the walk needs stays: the light-radius-zero and light-sensitive-adjacent triggers."""
    here = snapshot.player.position
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile and monster.asleep
            and game_distance(here, monster.position) <= LITE_ROOM_REACH
            and policy._material_melee_fight(snapshot, monster)]


def _aimed_once(ctx, trigger) -> bool:
    """The target is on a beam's line and no power was aimed at it for
    ``trigger`` on this floor."""
    return ctx.aim is not None and not any(
        use.trigger == trigger and use.target == ctx.target for use in ctx.memory.uses)


def _trap_to_disarm(ctx, power):
    """Once per trap (a use that took its turn and left the trap leaves it to
    the disarm command)."""
    return _aimed_once(ctx, "trap-to-disarm")


def _quest_opening_target(ctx, power):
    """Once per quest plan's opening target on this floor visit (the target
    need not be in sight: the beam follows the aimed line)."""
    return _aimed_once(ctx, "quest-opening-target")


def _light_sensitive_adjacent(ctx, power):
    """A detected (not visible) hostile beside the player that light hurts."""
    races = ctx.policy._monrace_knowledge
    return any(
        monster.hostile and ctx.position.distance_to(monster.position) <= 1
        and "HURT_LITE" in getattr(races.get(monster.race_id), "flags", ())
        for monster in ctx.snapshot.detected_monsters)


def _resists_teleport_surely(ctx, monster) -> bool:
    """effect_monster_away_resist: a RES_TELE race that is UNIQUE or RES_ALL."""
    flags = getattr(ctx.policy._monrace_knowledge.get(monster.race_id), "flags", frozenset())
    return "RES_TELE" in flags and bool(flags & {"UNIQUE", "RES_ALL"})


def _cast_radius(ctx, use) -> int:
    """The radius an earlier use detected: rod_effect's powerful detect_rad is
    DETECT_RAD_DEFAULT * 3 / 2 (cmd-item/cmd-zaprod.cpp:50)."""
    radius = ctx.radius(BY_KEY[use.used])
    return radius * 3 // 2 if use.reason.endswith(POWERFUL_SUFFIX) else radius


# Owner 2026-11-02 「一定の時間ごとに使い直す」, 「1,000ゲームターン」: the hunted
# target moves, so the search is also cast again this long after the latest
# use that could have revealed it, wherever the player stands.
HUNT_REDETECT_GAME_TURNS = 1000


def _hunt_target_unseen(ctx, power):
    """The hunted random-quest target or guardian is shown nowhere, this row's
    effect reveals its race, and every earlier use that would have revealed it
    is at least its radius away (again only after moving the detection radius,
    as the mapping row) or the latest of them is HUNT_REDETECT_GAME_TURNS old
    (owner 2026-11-02, hunt_target)."""
    policy = ctx.policy
    race = hunt_target.unseen_race(policy, ctx.snapshot)
    if race is None:
        return False
    flags = hunt_target.race_flags(policy, race)
    if not hunt_target.REVEALS[power.effect](flags):
        return False
    return redetect_due(ctx.snapshot, ctx.snapshot.player.position, _revealing_uses(ctx, flags))


def _revealing_uses(ctx, flags) -> list:
    """(position, radius, turn) of every landed use that would have shown such a race."""
    return [(use.position, _cast_radius(ctx, use), use.turn) for use in ctx.memory.uses
            if (reveals := hunt_target.REVEALS.get(BY_KEY[use.used].effect)) and reveals(flags)]


def revealing_radius(policy, snapshot, flags) -> int:
    """The largest plain radius of an absorbed power with a charge whose cast can show such a
    race (its powerful reach depends on the moment, so it is not counted), else 0."""
    ctx = Context(policy, snapshot, FLOOR, None)
    return max((ctx.radius(power, unknown_is_dark=True) for power in POWERS
                if (reveals := hunt_target.REVEALS.get(power.effect)) and reveals(flags)
                and _charges(ctx, power) > 0), default=0)


def revealing_casts(policy, snapshot, flags) -> list:
    """``_revealing_uses`` of this floor visit, for a search outside the rows."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return []
    return _revealing_uses(Context(policy, snapshot, FLOOR, memory), flags)


def redetect_due(snapshot, position, casts) -> bool:
    """The search spacing: every earlier cast is its radius away, or the latest is old."""
    if not casts or snapshot.turn - max(turn for _, _, turn in casts) >= HUNT_REDETECT_GAME_TURNS:
        return True
    return all(game_distance(position, centre) >= radius for centre, radius, _ in casts)


def _area_mapping():
    # area_mapping imports this module (the rows, the hostile rule).
    from hengbot import area_mapping

    return area_mapping


def _after_destruction(ctx, power):
    return _area_mapping().due_after_destruction(ctx)


def _sealed_pocket(ctx, power):
    """area_mapping asks only when the map is wanted."""
    return True


def _status_rung_first(policy, snapshot, monster) -> bool:
    """Owner 2026-11-12 (「巻物の手当てを先にする」: 「09-18 の決まりの巻物の手当てを今までどおり
    先にし、テレポート・アウェイはその後。life-346 の死に方を繰り返さない。」): a monster the 09-18
    rungs leave by scroll -- an awake paralyser in contact, by blow or by spell in sight
    (``policy._paralyzer_prevention_key``, paralyzer_contact), or a confusion / paralysis attacker
    of the status-threat rung (``_unresisted_melee_status_threats`` with its floor latch) -- is
    left to them when it reads T1 alone only by the fear / blindness exclusion (``t2_withheld``,
    owner 2026-11-11), not sent away from here."""
    from hengbot import paralyzer_contact, threat_tiers
    if monster.asleep or not threat_tiers.tiered(policy, snapshot, [monster]).t2_withheld:
        return False
    if policy._paralyzing_monsters(snapshot, [monster]) and (
            paralyzer_contact.in_contact(policy, snapshot, monster)
            or paralyzer_contact.spell_contact(policy, snapshot, monster)):
        return True
    latch = getattr(policy, "_status_threat_latch", None)
    latched = latch[1] if latch is not None and latch[0] == snapshot.floor_key else frozenset()
    return bool(policy._unresisted_melee_status_threats(snapshot, [monster], latched=latched))


# A stunned player (timed-effect/player-stun.cpp, by ``stun_rank``, PlayerStunRank 0-5): the
# Magic-Eater's failure chance adds get_magic_chance_penalty (:135-153) before its cap of 95
# (cmd-magiceat.cpp:484-487; me_power_success owns it); a scroll's read fails on
# get_item_chance_penalty (:162-178, object-use/item-use-checker.cpp check_stun,
# read-execution.cpp:94).
STUN_MAGIC_PENALTY = me_power_success.STUN_MAGIC_PENALTY
STUN_ITEM_PENALTY = (0, 0, 0, 5, 10, 100)
MAX_FAILURE = me_power_success.MAX_FAILURE
_stun_rank = me_power_success.stun_rank


def _base_level(ident) -> int | None:
    """The BaseitemDefinitions level of a power the bot knows it of (the attack powers and
    the survival powers), else None."""
    from hengbot.me_device_attacks import POWERS
    from hengbot.me_loadout_offense import SURVIVAL_POWERS

    ident = tuple(ident)
    if ident in POWERS:
        return POWERS[ident].level
    survival = SURVIVAL_POWERS.get(ident)
    return survival[1] if survival is not None else None


def stunned_success(policy, snapshot, ident) -> int | None:
    """The power's success percent under the board's current stun (me_power_success: the game's
    rate, else the displayed row less the stun it was shown under); None without a displayed
    row, which is what says the power is absorbed."""
    row = me_capability.observed_row(policy, *ident)
    if row is None:
        return None
    return me_power_success.success_percent(policy, snapshot, ident[0], _base_level(ident), row=row)


def _stunned_scroll_first(ctx, power) -> bool:
    """Stunned, a readable Teleportation scroll is surer than the power: the THREAT power gives
    way and the leave reads the scroll (n1-b life-377, 80F 2026-11-12 13:46: stunned by a
    plasma bolt, the absorbed Teleport Away cast at 97% displayed failed and 混沌の王族
    killed the player; the scroll the sensed leave named was in the pack)."""
    snapshot = ctx.snapshot
    if not snapshot.player.stunned:
        return False
    if ctx.policy._escape_scroll(snapshot, teleport_only=True) is None:
        return False
    success = stunned_success(ctx.policy, snapshot, power.ident)
    return success is None or 100 - STUN_ITEM_PENALTY[_stun_rank(snapshot.player)] > success


def _unbeatable_in_range(ctx, power):
    """A visible hostile on a beam's line that this character cannot beat.

    Threat tiers plan step 6 (inventory 2.4): where the tiers act, it is a monster the tiers
    leave, T1 or a T2 that is not a selected target (``threat_tiers.leave_due`` on it alone);
    elsewhere, and where the tiers do not decide (T3, past the cost cap), today's winnability.
    Not while stunned with a surer Teleportation scroll to read (``_stunned_scroll_first``)."""
    monster, policy = ctx.target_hostile, ctx.policy
    if monster is None or ctx.aim is None or _resists_teleport_surely(ctx, monster):
        return False
    if _stunned_scroll_first(ctx, power):
        return False
    from hengbot import threat_tiers
    leave = threat_tiers.leave_due(policy, ctx.snapshot, [monster])
    if leave and _status_rung_first(policy, ctx.snapshot, monster):
        return False
    if leave is not None:
        return leave
    return not policy._engagement_is_winnable(
        ctx.snapshot, [monster],
        damage_against=lambda each: me_ranged_first.best_expected(policy, ctx.snapshot, each))


def _deep_floor(ctx) -> bool:
    return ctx.snapshot.dungeon_level >= DEEP_FLOOR_MIN_DEPTH


# The effects whose cast shows the monsters around it (the Detect Evil row and its preferred rod).
MONSTER_DETECTIONS = frozenset({"detect-evil", "detect-all"})


def _deep_explore_redetect(ctx, power):
    """PLAN-50F 4.3 (owner 2026-11-11 C6 「2」): on 50F+, the floor's monster detection again once
    the player stands DEEP_REDETECT_WALK from the latest landed one.  The arrival cast is the
    new-floor trigger's; a Recall already read ends the visit, so it does not re-detect."""
    if not _deep_floor(ctx) or ctx.snapshot.player.recalling:
        return False
    casts = [use for use in ctx.memory.uses if BY_KEY[use.used].effect in MONSTER_DETECTIONS]
    if not casts:
        return False
    latest = max(casts, key=lambda use: use.turn)
    return ctx.distance(latest.position) >= DEEP_REDETECT_WALK


def _deep_arrival_unhasted(ctx, power):
    """PLAN-50F 4.9 (owner 2026-11-11 C6 「5」): on 50F+ the floor visit starts hasted, 「the first
    moves of a floor decide whether a pack reaches the character」.  Once per floor visit: not
    hasted (the speed field) and no cast of this row landed on the floor.  The row's 11-04
    requirements hold here too (at least FIGHT_SPEED_MIN_CHARGES charges, a reliable cast); no
    potion is drunk for it (the plan asks the absorbed Speed only)."""
    return (_deep_floor(ctx) and not ctx.policy._player_hasted(ctx.snapshot)
            and not ctx.uses_of(power))


def _fight_unhasted(ctx, power):
    """Not hasted (the speed field), and no landed cast's shortest haste still runs."""
    return not ctx.policy._player_hasted(ctx.snapshot) and all(
        ctx.snapshot.turn - use.turn >= HASTE_MIN_GAME_TURNS for use in ctx.uses_of(power))


@dataclass(frozen=True)
class Trigger:
    name: str
    occasions: frozenset
    due: Callable
    takes_fallback: bool = True  # False: only the row's own effect answers it


TRIGGERS = {trigger.name: trigger for trigger in (
    Trigger("new-floor", frozenset({FLOOR}), _new_floor),
    Trigger("stairs-needed-and-unknown", frozenset({FLOOR}), _stairs_needed_and_unknown),
    # Owner 2026-11-13 named 周辺感知: its Door/Stairs fallback does not map.
    Trigger("loot-unreachable", frozenset({FLOOR}), _loot_unreachable, takes_fallback=False),
    Trigger("before-rest", frozenset({REST}), _before_rest),
    Trigger("before-secret-search", frozenset({SECRET_SEARCH}), _before_secret_search),
    Trigger("left-detected-trap-area", frozenset({FLOOR}), _left_detected_trap_area),
    Trigger("light-radius-zero", frozenset({DARK}), _light_radius_zero),
    Trigger("dark-room", frozenset({FLOOR}), _dark_room),
    Trigger("light-sensitive-adjacent", frozenset({FLOOR, DARK}), _light_sensitive_adjacent),
    Trigger("trap-to-disarm", frozenset({TRAP}), _trap_to_disarm),
    # Owner 2026-11-09 「罠探知があるなら使用することで確定」: the caller asks once per cell.
    Trigger("trap-cell-unsettled", frozenset({TRAP_CELL}), lambda ctx, power: True),
    Trigger("unbeatable-in-range", frozenset({THREAT}), _unbeatable_in_range),
    Trigger("quest-opening-target", frozenset({QUEST_OPENING}), _quest_opening_target),
    Trigger("hunt-target-unseen", frozenset({FLOOR}), _hunt_target_unseen),
    Trigger("deep-explore-redetect", frozenset({FLOOR}), _deep_explore_redetect),
    Trigger("fight-unhasted", frozenset({FIGHT}), _fight_unhasted),
    Trigger("deep-arrival-unhasted", frozenset({FLOOR}), _deep_arrival_unhasted),
    # Owner 2026-11-05 named 周辺感知: its Door/Stairs fallback does not map.
    Trigger("after-destruction", frozenset({FLOOR}), _after_destruction, takes_fallback=False),
    Trigger("sealed-pocket", frozenset({SEALED}), _sealed_pocket, takes_fallback=False),
)}

REQUIREMENTS = {
    # Never in a DARKNESS dungeon (lite_area does nothing); unknown is not proof.
    "not-darkness-dungeon": lambda ctx: ctx.darkness() is False,
    "fight-speed-charges": lambda ctx: me_capability.charges(
        ctx.policy, ctx.snapshot, "staff", SV_STAFF_SPEED) >= FIGHT_SPEED_MIN_CHARGES,
    "speed-reliable": lambda ctx: me_capability.reliable(
        ctx.policy, ctx.snapshot, ("staff", SV_STAFF_SPEED)),
}


def _activation():
    # me_powerful_activation imports this module (kind letters, retry bound).
    from hengbot import me_powerful_activation

    return me_powerful_activation


def _when_safe(ctx) -> bool:
    """「安全なら」: no visible hostile, not just hit, and the HP cost leaves the
    character above the ladder's low-HP rungs (me_powerful_activation.pays_safely)."""
    return (not ctx.hostile_visible and not getattr(ctx.policy, "_took_damage", False)
            and _activation().pays_safely(ctx.policy, ctx.snapshot))


POWERFUL = {"when-safe": _when_safe}
POWERFUL_SUFFIX = ":powerful"


def _powerful(ctx, power) -> bool:
    return power.powerful is not None and POWERFUL[power.powerful](ctx)


# -- charges, gates and the producer ------------------------------------------

def _charges(ctx, power) -> int:
    return me_capability.charges(ctx.policy, ctx.snapshot, *power.ident)


def _gate(policy, snapshot) -> bool:
    player = snapshot.player
    return (
        player.class_id == PLAYER_CLASS_MAGIC_EATER
        and getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) >= PROTOCOL_SCREEN_PARITY
        and not snapshot.in_town and not snapshot.on_open_wilderness
        and snapshot.dungeon_level > 0 and snapshot.store is None
        and not (player.blind or player.confused or player.hallucinated or player.paralyzed
                 or power_command_refused(snapshot))
    )


def visible_threat(policy, snapshot) -> bool:
    """A visible hostile the combat ladder judges dangerous: an unresisted
    confusion/paralysis attacker (status-threat rung), a reason to flee
    (flee rung) or a material threat (threat:reposition rung)."""
    hostiles = policy._physical_hostiles(snapshot)
    return bool(hostiles) and bool(
        policy._unresisted_melee_status_threats(snapshot, hostiles)
        or policy._should_flee(snapshot, hostiles, policy._physical_adjacent_hostiles(snapshot))
        or policy._is_material_threat(snapshot, hostiles))


def _hostiles_allow(ctx, power) -> bool:
    if power.against_hostile:
        return True
    if getattr(ctx.policy, "_took_damage", False):
        return False
    return not ctx.hostile_visible or (power.beside_harmless and not ctx.threat_visible)


def utility_device_permitted(policy, snapshot) -> bool:
    """The mapping row's hostile rule, for a carried device of the same effect."""
    return not getattr(policy, "_took_damage", False) and (
        not policy._physical_hostiles(snapshot) or not visible_threat(policy, snapshot))


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
            and _charges(ctx, power) > 0)


def _serving(ctx, power, trigger):
    """A usable preferred power, else the row's own power, or its fallback
    when the row has no charge."""
    preferred = next((BY_KEY[ident] for ident in power.preferred
                      if _usable(ctx, BY_KEY[ident], trigger)), None)
    if preferred is not None:
        return preferred
    if _charges(ctx, power) > 0:
        return power if _usable(ctx, power, trigger) else None
    if not TRIGGERS[trigger].takes_fallback:
        return None
    fallback = BY_KEY.get(power.fallback) if power.fallback is not None else None
    return fallback if fallback is not None and _usable(ctx, fallback, trigger) else None


def power_key(policy, snapshot, occasion: str, target: Position | None = None) -> str | None:
    """``m`` + kind + power (+ direction) of the first due power for
    ``occasion``, else None; ``target`` is what an aimed power is aimed at."""
    if not _gate(policy, snapshot):
        return None
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return None
    ctx = Context(policy, snapshot, occasion, memory, target)
    for power in sorted(POWERS, key=lambda each: each.priority):
        if not _hostiles_allow(ctx, power):
            continue
        for name in power.triggers:
            trigger = TRIGGERS[name]
            if occasion not in trigger.occasions:
                continue
            # The charge check is cheap; a trigger may weigh a fight.
            used = _serving(ctx, power, name)
            if used is None or not trigger.due(ctx, power):
                continue
            powerful = _powerful(ctx, used)
            reason = f"{REASON}:{name}:{used.effect}" + (POWERFUL_SUFFIX if powerful else "")
            key = ((_activation().racial_key(*used.ident) if powerful else used.key)
                   + (ctx.aim if used.aimed else ""))
            policy.last_reason = reason
            policy._offer_execution(
                key, producer="detectors", work_id=f"{REASON}:{used.effect}",
                next_step="magic-eater.power.send", arguments=(used.kind, used.sval, name),
                expected_effect=used.effect,
            )
            memory.pending = Use(power.ident, used.ident, name, ctx.position, snapshot.turn,
                                 reason, key, target)
            return key
    return None


def threat_key(policy, snapshot) -> str | None:
    """The THREAT occasion aimed at each visible hostile, nearest first."""
    for monster in sorted(policy._physical_hostiles(snapshot), key=lambda each: each.distance):
        if (key := power_key(policy, snapshot, THREAT, monster.position)) is not None:
            return key
    return None


def fight_key(policy, snapshot, key: str | None) -> str | None:
    """The FIGHT occasion's power in place of a decided attack, else ``key``."""
    if (key is None or not _gate(policy, snapshot)
            or not attack_answer.attacks_awake_hostile(policy, snapshot, key)):
        return key
    return power_key(policy, snapshot, FIGHT) or key


def mapped_areas(policy, snapshot) -> tuple:
    """(centre, radius) of every map-area this floor visit cast (the
    mapped_area module's source; a failed or refused cast is not a use)."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return ()
    ctx = Context(policy, snapshot, FLOOR, memory)
    return tuple(
        (use.position, ctx.radius(BY_KEY[use.used], unknown_is_dark=True))
        for use in memory.uses if BY_KEY[use.used].effect == MAP_AREA and not use.map_forgotten)


def map_radius(policy, snapshot) -> int:
    """What a mapping cast here covers, the smaller reading in an unknown dungeon."""
    return Context(policy, snapshot, FLOOR, None).radius(
        BY_KEY[("staff", SV_STAFF_MAPPING)], unknown_is_dark=True)


def map_charged(policy, snapshot) -> bool:
    """An absorbed mapping power has a charge."""
    return any(power.effect == MAP_AREA and me_capability.charges(policy, snapshot, *power.ident) > 0
               for power in POWERS)


def mapped_since(policy, snapshot, turn: int) -> bool:
    """A mapping landed on this floor at or after game turn ``turn``."""
    memory = getattr(policy, MEMORY, None)
    return (memory is not None and memory.floor == snapshot.floor_key
            and any(BY_KEY[use.used].effect == MAP_AREA and use.turn >= turn for use in memory.uses))


def forget_maps(policy, snapshot, centre: Position, radius: int) -> None:
    """Mappings that met a destroyed circle stop reading as a map; the row keeps them
    as uses, so its own triggers do not fire again for them."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return
    reach = map_radius(policy, snapshot) + radius
    memory.uses = [
        replace(use, map_forgotten=True)
        if BY_KEY[use.used].effect == MAP_AREA and game_distance(centre, use.position) <= reach
        else use
        for use in memory.uses]


def decision_reason(policy, key) -> str | None:
    """The power's reason when ``key`` is the pending power key, else None.

    The trap occasion is asked inside the walk (policy_navigation._step_toward)
    and a caller may name its decision after the walk returned; the executor
    answers the power's prompts only under the power's own reason
    (me_device_attacks_input.compile_device).
    """
    memory = getattr(policy, MEMORY, None)
    pending = None if memory is None else memory.pending
    return pending.reason if pending is not None and key and key == pending.key else None
