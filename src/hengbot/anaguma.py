"""Anaguma (穴熊): dig a zigzag pocket with Stone to Mud and fight a pack from it.

Owner 2026-11-10 (verbatim, the request): 「群れに対抗するための戦術を追加する。岩石溶解を
用いて7方壁の窪みを作り待ち伏せする方法である。後続から遠距離攻撃を受けないようにしておくと
なお良い。穴熊と呼称する。」  The answers of the same day are the locked spec
(docs/anaguma-design.md section 9):

- animal packs 「動物の群れにはジグザグの通路を長めに取る。すると、動物の後退する動きが後続に
  阻まれ順に近寄ってくる。最後の一匹は近寄ってこないのでこちらから詰める動きが別途必要になる。」
- the last animal 「範囲→加速→出口まで追う　を基本的には採用するが、加速は魔道具術師など消耗品を
  使用しない場合に限定する」
- length 「4マス/2マスを基本とし、地形と岩石溶解の回数が許すなら8マスまで伸ばす」
- reserve 「魔道具術師の場合は自然回復するので残さなくて良い。それ以外なら1回残す。」
- ranged packs 「常に使う。…高威力攻撃を持つ個体は通常の生存ルーチンで対応する。」 (no gate here)
- existing chokes 「掘れるなら掘る」; summoners 「使う」; abandoning 「今の基準のまま」
- waiting 「50ゲームターン。待った後、可能なら感知を使って状況を把握する。」
- floors 「ランダムクエストの階も使う」 (not fixed quests, town or the wilderness)

The pack: two or more hostile monsters of one FRIENDS race (MonraceDefinitions), at least one
awake and able to move.  An animal pack (ANIMAL, no PASS_WALL/KILL_WALL) needs 4 cells; any
other pack 2.  A monster that passes or kills walls anywhere in view or detection vetoes the
pocket (monster-floor/monster-move.cpp:76-96).  A player walled in on every side
(``sealed_pocket.sealed_region``) plans none: no pack walks to it, and its Stone to Mud is the way
out (owner 2026-11-05 「*破壊*後全方位壁なら岩石溶解で脱出すれば良い」).  A pack of which half
or more is expected to run from the player (``run_chance``, the game's ``mon_will_run``) gets
no pocket, and a plan not yet dug is dropped (owner 2026-11-10 「弱いoの群れなど…自分から逃げる
群れに対しては効果が薄い…使う相手を絞って」).
A wall-passer or runners veto, once read, holds for ``RETRY_GAME_TURNS``, and a released plan is
not made again for the same pack on the floor within that window (``_latched``, ``key``).

Phases of the plan (``Plan``):

- ``walk``  to the start cell ``S`` (an open cell beside the rock);
- ``dig``   from the cell reached, melt the next tunnel cell (one use, ``sealed_pocket.melt_at_key``)
            and step into it; past the base length, go on while the next cell, the charges and the
            pack's arrival time allow, up to 8;
- ``hold``  on the pocket: strike the monster on the mouth, else wait (``anaguma:hold``).  After
            50 game turns with no pack member beside the player, a detection is used when one is
            at hand; an animal pack still known then gets the close-in, any other plan ends;
- ``close`` (animal packs, the last one): an area attack aimed into the mouth while the animal
            is in its blast; else the Magic-Eater's absorbed Speed (never a potion); then step out
            and strike, following it along the tunnel up to its exit, where the plan ends.

The arrival time of a member is its path length to ``S`` over the known floor (unknown grids
count as floor) divided by its moves per player move (core/speed-table.cpp extract_energy,
``speed_energy``); the dig time is the walk plus, per cell, one step and 1/p uses (p the device
success, attack_expectation.device_use_success, item level 10, BaseitemDefinitions id 273).

The existing escape criteria release the plan (``_should_flee``).  On the pocket a walk out is
never the escape: *Destruction* (destruction_use) and then the escape scroll; with neither the
plan ends and the ladder below answers.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from hengbot import (
    anaguma_geometry as geo, area_mapping, attack_expectation, breeder_area_attack, combat_answer,
    destruction_use, me_absorbed_substitutes, me_capability, me_device_attacks, sealed_pocket,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import (
    SV_STAFF_SPEED, SV_WAND_STONE_TO_MUD, TVAL_ROD, TVAL_STAFF, TVAL_WAND, Position, Snapshot,
    game_distance,
)
from hengbot.policy_constants import DIRECTION_KEYS, WAIT_KEY, speed_energy
from hengbot.threat_projection import adjusted_speed

MEMORY = "_anaguma_plan"

REASON_WALK = "anaguma:walk"
REASON_DIG = "anaguma:dig"
REASON_STEP = "anaguma:step"
REASON_HOLD = "anaguma:hold"
REASON_MELEE = "melee:anaguma"
REASON_DETECT = "anaguma:detect"
REASON_ESCAPE = "anaguma:escape-scroll"
REASON_CLOSE_AREA = "ranged:anaguma-close-area"
REASON_CLOSE_HASTE = "anaguma:close-haste"
REASON_CLOSE_STEP = "anaguma:close-step"
REASON_CLOSE_MELEE = "melee:anaguma-close"
# Reasons that keep the player on one cell by design (cli.STATIONARY_EXEMPT_REASONS).
STATIONARY = frozenset({REASON_DIG, REASON_DIG + me_absorbed_substitutes.CAST_SUFFIX,
                        REASON_HOLD, REASON_DETECT, REASON_CLOSE_HASTE})

ANIMAL_LENGTH = 4       # 「4マス/2マスを基本」
OTHER_LENGTH = 2
MAX_LENGTH = 8          # 「8マスまで伸ばす」
WAIT_GAME_TURNS = 50    # 「50ゲームターン」
WALK_RADIUS = 8         # how far the start cell may be
ARRIVAL_SEARCH = 60     # path steps searched for a member's arrival
STONE_TO_MUD_LEVEL = 10  # BaseitemDefinitions.jsonc id 273
MIN_SUCCESS = 0.2
PACK_MIN = 2
WALL_FLAGS = ("PASS_WALL", "KILL_WALL")
RETRY_GAME_TURNS = 50   # a refused site search is not repeated sooner on the same floor
# monster-floor/monster-sweep-grid.cpp mon_will_run (:35-72), the game's own constants.
RUN_LEVEL_BONUS = 25    # m_lev = race level + (m_idx & 0x08) + 25
RUN_INDEX_BIT = 0x08    # the m_idx bit added to m_lev (internal: the player never sees it)
RUN_LEVEL_MARGIN = 4    # m_lev > p_lev + 4: never runs; m_lev + 4 <= p_lev: always runs
RUN_HP_SHIFT = 2        # p_chp << 2, m_chp << 2 (the current HP counted four times)
RUN_NEAR = 5            # cdis <= 5: a monster this near does not run (it comes on)
UINT32 = 0xFFFFFFFF     # p_val, m_val and their products are uint32_t
# 「効果が薄い」: no pocket when at least half of the pack is expected to run (the request's line).
RUNNING_SHARE = 1 / 2


@dataclass
class Plan:
    floor: tuple
    tunnel: geo.Zigzag            # every cell that may be dug (the 8-cell bound or less)
    length: int                   # the cells this plan digs now
    minimum: int                  # 4 (animal pack) or 2
    animal: bool
    races: frozenset
    phase: str = "walk"
    contact_turn: int = 0         # game turn of the last contact (start, a blow, a strike)
    detected_turn: int | None = None
    target: Position | None = None
    hasted: bool = False
    history: list = field(default_factory=list)

    @property
    def cells(self) -> tuple:
        return self.tunnel.cells[:self.length]

    @property
    def pocket(self) -> Position:
        return self.cells[-1]

    @property
    def mouth(self) -> Position:
        return self.tunnel.before(self.length - 1)


def plan(policy) -> Plan | None:
    return getattr(policy, MEMORY, None)


def _release(policy, why: str) -> None:
    current = plan(policy)
    if current is not None:
        policy._anaguma_last_release = why
        policy._anaguma_released = current
    setattr(policy, MEMORY, None)


def _latched(policy, name: str, scope, reading: bool, turn: int) -> bool:
    """A veto reading held on its decided side (owner 2026-11-08 「脅威度の段は境に余裕を
    持たせる（一度決めた側に固定）」).

    A reading that flips with the player's cell -- a wall-passer at the edge of detection, a
    pack member crossing the 5-cell line of ``run_chance`` -- turned the plan on and off on
    alternate steps (n1-b life-367, オークの洞窟23階, 2026-11-11: ``anaguma:walk`` from (34,124)
    to the start (33,123), released there by a sleeping poltergeist detected only from that
    cell, re-made on the way back; loop-detected twice).  A true reading holds the veto at once;
    it lifts only after ``RETRY_GAME_TURNS`` of false readings in the same ``scope``.
    """
    latches = getattr(policy, "_anaguma_latches", None)
    if latches is None:
        latches = policy._anaguma_latches = {}
    key_ = (name, scope)
    if reading:
        latches[key_] = turn
        return True
    seen = latches.get(key_)
    if seen is None:
        return False
    if turn - seen < RETRY_GAME_TURNS:
        return True
    del latches[key_]
    return False


# ---------------------------------------------------------------- facts

def _knowledge(policy, monster):
    return policy._monrace_knowledge.get(monster.race_id)


def _flags(policy, monster) -> frozenset:
    knowledge = _knowledge(policy, monster)
    return frozenset() if knowledge is None else knowledge.flags


def _hostiles(snapshot: Snapshot) -> list:
    """Every hostile the board shows: in view and detected."""
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile]


def wall_passer(policy, snapshot: Snapshot) -> bool:
    return any(flag in _flags(policy, monster) for monster in _hostiles(snapshot)
               for flag in WALL_FLAGS)


def _pack(policy, snapshot: Snapshot) -> tuple[frozenset, bool] | None:
    """(races, animal) of the pack on the board, else None."""
    groups: dict[int, list] = {}
    for monster in _hostiles(snapshot):
        flags = _flags(policy, monster)
        if "FRIENDS" in flags and "NEVER_MOVE" not in flags:
            groups.setdefault(monster.race_id, []).append(monster)
    races = {race for race, members in groups.items()
             if len(members) >= PACK_MIN and any(not member.asleep for member in members)}
    if not races:
        return None
    animal = any("ANIMAL" in _flags(policy, groups[race][0]) for race in races)
    return frozenset(races), animal


def _members(snapshot: Snapshot, races) -> list:
    return [monster for monster in _hostiles(snapshot) if monster.race_id in races]


def _runs_at(m_lev: int, snapshot: Snapshot, monster) -> bool:
    """The level and HP half of ``mon_will_run`` for one ``m_lev`` (monster-sweep-grid.cpp:55-71)."""
    player = snapshot.player
    p_lev = player.level
    if m_lev > p_lev + RUN_LEVEL_MARGIN:
        return False
    if m_lev + RUN_LEVEL_MARGIN <= p_lev:
        return True
    p_val = (p_lev * player.max_hp + (player.hp << RUN_HP_SHIFT)) & UINT32
    m_val = (m_lev * monster.max_hp + (monster.hp << RUN_HP_SHIFT)) & UINT32
    return (p_val * monster.max_hp) & UINT32 > (m_val * player.max_hp) & UINT32


def run_chance(snapshot: Snapshot, monster) -> float:
    """1, 1/2 or 0: whether ``monster`` runs from the player instead of walking to the pocket.

    Owner 2026-11-10 (verbatim): 「穴熊に関して　弱いoの群れなど、レベル差などの影響で自分から
    逃げる群れに対しては効果が薄い。モンスターが逃走する条件を調べて使う相手を絞って」

    The game (monster-floor/monster-sweep-grid.cpp:35-72, ``mon_will_run``)::

        if (monster.cdis > MAX_PLAYER_SIGHT + 5) return false;
        if (monster.is_fearful()) return true;
        if (monster.cdis <= 5) return false;
        m_lev = monrace.level + (m_idx & 0x08) + 25;
        if (m_lev > p_lev + 4) return false;
        if (m_lev + 4 <= p_lev) return true;
        p_val = (p_lev * p_mhp) + (p_chp << 2);  m_val = (m_lev * m_mhp) + (m_chp << 2);
        return p_val * m_mhp > m_val * p_mhp;

    A running monster takes ``run_away`` (:527-529) and none of the pack deciders (the hiding
    and surrounding moves are ``!will_run`` only, :479-487), so beyond 5 cells it keeps away
    and never reaches the pocket's mouth.  Here: a fearful member runs; a member within
    ``RUN_NEAR`` already comes on; any other is judged by the level and HP rule (one beyond
    MAX_PLAYER_SIGHT + 5 walks in until that rule applies).  The player's level and HP are
    the board's; the monster's level is its race's and its HP the bot's estimate from the
    health display (model._estimated_monster_hp).  Fair play: the ``m_idx & 0x08`` bit is
    internal, so a member whose answer differs with and without it counts 1/2.
    """
    if monster.fearful:
        return 1.0
    if game_distance(snapshot.player.position, monster.position) <= RUN_NEAR:
        return 0.0
    base = monster.level + RUN_LEVEL_BONUS
    runs = (_runs_at(base, snapshot, monster), _runs_at(base + RUN_INDEX_BIT, snapshot, monster))
    return sum(runs) / len(runs)


def runners(snapshot: Snapshot, races) -> bool:
    """At least ``RUNNING_SHARE`` of the pack is expected to run (``run_chance``): no pocket."""
    members = _members(snapshot, races)
    if not members:
        return False
    return sum(run_chance(snapshot, monster) for monster in members) >= RUNNING_SHARE * len(members)


def _dug(snapshot: Snapshot, current: Plan) -> bool:
    """A cell of the plan is open already (the dig has begun)."""
    return any(geo.open_cell(snapshot.grid_at(cell)) for cell in current.cells)


def magic_eater(snapshot: Snapshot) -> bool:
    return snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER


def _wand_charges(snapshot: Snapshot) -> int:
    return sum(item.charges for item in snapshot.inventory
               if item.tval == TVAL_WAND and item.sval == SV_WAND_STONE_TO_MUD and item.charges > 0)


def usable_charges(policy, snapshot: Snapshot) -> int:
    """Charges a dig may spend: 「魔道具術師の場合は…残さなくて良い。それ以外なら1回残す。」"""
    total = _wand_charges(snapshot)
    if magic_eater(snapshot):
        total += max(0, me_capability.charges(policy, snapshot, "wand", SV_WAND_STONE_TO_MUD))
        return total
    return total - 1


def _success(snapshot: Snapshot) -> float:
    return max(MIN_SUCCESS, attack_expectation.device_use_success(
        snapshot.player.device_skill, STONE_TO_MUD_LEVEL))


def _floor_allowed(policy, snapshot: Snapshot) -> bool:
    if snapshot.in_town or snapshot.dungeon_level <= 0 or getattr(snapshot, "inside_arena", False):
        return False
    return snapshot.floor_key[2] == 0 or policy._on_random_quest_floor(snapshot)


def _able(snapshot: Snapshot) -> bool:
    player = snapshot.player
    return not (player.blind or player.confused or player.hallucinated or player.recalling
                or getattr(player, "paralyzed", False))


# ---------------------------------------------------------------- time

def _approach_lengths(snapshot: Snapshot, members, limit: int) -> dict:
    """Steps from the nearest awake member over the known floor, closed doors and rubble
    (monsters ignored).  Where this does not reach, ``_arrival`` takes the straight game
    distance, the least any path can be: both err toward an earlier arrival."""
    seen = {monster.position: 0 for monster in members if not monster.asleep}
    queue = deque(seen)
    while queue:
        here = queue.popleft()
        if seen[here] >= limit:
            continue
        for around in geo.neighbours(here):
            if around in seen:
                continue
            grid = snapshot.grid_at(around)
            if grid is None or not grid.known or not (
                    grid.passable or grid.is_closed_door or grid.is_rubble):
                continue
            seen[around] = seen[here] + 1
            queue.append(around)
    return seen


def _rate(snapshot: Snapshot, members) -> float:
    """The fastest awake member's moves per player move (core/speed-table.cpp)."""
    mine = max(1, speed_energy(snapshot.player.speed))
    rates = [speed_energy(adjusted_speed(monster)) / mine for monster in members if not monster.asleep]
    return max(rates, default=1.0)


def _arrival(lengths: dict, rate: float, start: Position, members=()) -> float:
    """Player moves before the first awake member can reach ``start``."""
    steps = lengths.get(start)
    if steps is None:
        steps = min((game_distance(monster.position, start) for monster in members
                     if not monster.asleep), default=None)
    return float("inf") if steps is None else steps / max(rate, 0.01)


def _dig_time(walk: int, cells: int, success: float) -> float:
    return walk + cells * (1 + 1 / success)


# ---------------------------------------------------------------- planning

def _walk_lengths(policy, snapshot: Snapshot) -> dict:
    start = snapshot.player.position
    seen = {start: 0}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        if seen[here] >= WALK_RADIUS:
            continue
        for around in policy._walkable_neighbors(snapshot, here):
            if around not in seen:
                seen[around] = seen[here] + 1
                queue.append(around)
    return seen


def _candidate(policy, snapshot: Snapshot, races, animal: bool) -> Plan | None:
    minimum = ANIMAL_LENGTH if animal else OTHER_LENGTH
    charges = usable_charges(policy, snapshot)
    if charges < minimum:
        policy._anaguma_veto = "charges"
        return None
    members = _members(snapshot, races)
    success = _success(snapshot)
    origin = snapshot.player.position
    here_gap = min((game_distance(origin, monster.position) for monster in members), default=0)
    lengths = _approach_lengths(snapshot, members, ARRIVAL_SEARCH)
    rate = _rate(snapshot, members)
    best = None
    for start, walk in _walk_lengths(policy, snapshot).items():
        if any(monster.position == start for monster in members):
            continue
        if min((game_distance(start, monster.position) for monster in members), default=0) < here_gap:
            continue  # no closer to the pack than now (the choke route's rule)
        arrival = _arrival(lengths, rate, start, members)
        if arrival <= _dig_time(walk, minimum, success) + 1:
            continue
        for axis in geo.AXES:
            for side in geo.SIDES:
                tunnel = geo.longest(snapshot, start, axis, side, min(MAX_LENGTH, charges))
                if tunnel is None or len(tunnel.cells) < minimum:
                    continue
                key = (_dig_time(walk, minimum, success), -len(tunnel.cells), walk)
                if best is None or key < best[0]:
                    best = (key, tunnel)
    if best is None:
        policy._anaguma_veto = "no-site"
        return None
    tunnel = best[1]
    return Plan(snapshot.floor_key, tunnel, minimum, minimum, animal, races,
                contact_turn=snapshot.turn)


# ---------------------------------------------------------------- acting

def _melt(policy, snapshot: Snapshot, wall: Position) -> str | None:
    if sealed_pocket.worn_out(policy, snapshot, wall):
        return None
    return sealed_pocket.melt_at_key(policy, snapshot, wall, REASON_DIG)


def _step(policy, snapshot: Snapshot, target: Position, reason: str) -> str | None:
    step = target if game_distance(snapshot.player.position, target) <= 1 else (
        policy._position_target_step(snapshot, target))
    if step is None:
        return None
    policy.last_reason = reason
    return policy._step_toward(snapshot, step)


def _index(current: Plan, position: Position) -> int:
    """-1 on the start cell, k-1 on c_k, None off the tunnel."""
    if position == current.tunnel.start:
        return -1
    try:
        return current.tunnel.cells.index(position)
    except ValueError:
        return None


def _extend(policy, snapshot: Snapshot, current: Plan, standing: int) -> None:
    """「地形と岩石溶解の回数が許すなら8マスまで伸ばす」: one more cell while it fits."""
    while current.length < len(current.tunnel.cells):
        longer = geo.zigzag(snapshot, current.tunnel.start, current.tunnel.axis, current.tunnel.side,
                            current.length + 1, dug=standing + 1)
        if longer is None:
            return
        remaining = current.length + 1 - (standing + 1)
        members = _members(snapshot, current.races)
        # The pack walks to the start and on through the cells already open.
        arrival = _arrival(_approach_lengths(snapshot, members, ARRIVAL_SEARCH),
                           _rate(snapshot, members), current.tunnel.start, members) + standing + 1
        if (usable_charges(policy, snapshot) < remaining
                or arrival <= _dig_time(0, remaining, _success(snapshot)) + 1):
            return
        current.length += 1


def _dig_key(policy, snapshot: Snapshot, current: Plan) -> str | None:
    here = snapshot.player.position
    standing = _index(current, here)
    if standing is None:
        return _step(policy, snapshot, current.tunnel.start, REASON_WALK)
    if standing + 1 >= current.length:
        current.phase = "hold"
        current.contact_turn = snapshot.turn
        return None
    if standing + 1 >= current.minimum - 1:
        _extend(policy, snapshot, current, standing)
    target = current.tunnel.cells[standing + 1]
    grid = snapshot.grid_at(target)
    if geo.open_cell(grid):
        valid = geo.zigzag(snapshot, current.tunnel.start, current.tunnel.axis, current.tunnel.side,
                           standing + 2, dug=standing + 2)
        if valid is None:
            return _shorten(policy, snapshot, current, standing)
        return _step(policy, snapshot, target, REASON_STEP)
    if not geo.diggable(grid):
        return _shorten(policy, snapshot, current, standing)
    melt = _melt(policy, snapshot, target)
    if melt is None:
        return _shorten(policy, snapshot, current, standing)
    return melt


def _shorten(policy, snapshot: Snapshot, current: Plan, standing: int) -> str | None:
    """The next cell cannot be dug: hold where the player stands when that is a pocket."""
    if standing + 1 >= OTHER_LENGTH and geo.pocket_holds(
            snapshot, current.tunnel.cells[standing], current.tunnel.before(standing), presume=True):
        current.length = standing + 1
        current.phase = "hold"
        current.contact_turn = snapshot.turn
        return None
    _release(policy, "dig-refused")
    return None


def _escape_key(policy, snapshot: Snapshot) -> str | None:
    """「今の基準のまま」 left the pocket: *Destruction*, then the escape scroll; no walk."""
    used = destruction_use.key(policy, snapshot)
    if used is not None:
        return used
    scroll = policy._escape_scroll(snapshot)
    if scroll is not None:
        policy.last_reason = REASON_ESCAPE
        return policy._read_key(snapshot, scroll)
    return None


def _detect_key(policy, snapshot: Snapshot, current: Plan) -> str | None:
    """「待った後、可能なら感知を使って状況を把握する」: a rod of Detection, a staff of Detect
    Evil for an evil pack, or the absorbed power of either."""
    if not area_mapping.device_usable_now(policy, snapshot):
        return None
    evil = any("EVIL" in getattr(policy._monrace_knowledge.get(race), "flags", ())
               for race in current.races)
    # The carried device under the bare reason (an item command), else the absorbed power
    # under its owner (me_absorbed_substitutes.cast sets ``REASON_DETECT`` + CAST_SUFFIX).
    for tval, ident, wanted in ((TVAL_ROD, me_absorbed_substitutes.DETECTION[0], True),
                                (TVAL_STAFF, me_absorbed_substitutes.DETECTION[1], evil)):
        if not wanted:
            continue
        kind, sval = ident
        item = next((each for each in snapshot.inventory if each.tval == tval and each.sval == sval
                     and area_mapping.device_ready(each, kind)), None)
        used = None if item is None else reserved_item_command(policy, snapshot, kind, item)
        if used is not None:
            policy.last_reason = REASON_DETECT
            return used
        used = me_absorbed_substitutes.cast(policy, snapshot, ident, REASON_DETECT)
        if used is not None:
            return used
    return None


def _area_into_mouth(policy, snapshot: Snapshot, current: Plan, target) -> str | None:
    """「範囲」: the area attack aimed at the mouth whose blast reaches ``target``."""
    here = snapshot.player.position
    offset = (current.mouth.y - here.y, current.mouth.x - here.x)
    direction = DIRECTION_KEYS.get(offset)
    if direction is None:
        return None
    blocks = breeder_area_attack._blocker(snapshot)
    best = None
    for each in breeder_area_attack._means(policy, snapshot):
        if each.power.shape not in ("ball", "breath") or not each.power.aimed:
            continue
        hits = breeder_area_attack._hits(snapshot, each.power, offset, blocks)
        if target.position not in hits:
            continue
        damage = each.success * breeder_area_attack._damage(
            policy, snapshot, each.power, target, hits[target.position])
        if best is None or damage > best[0]:
            best = (damage, each)
    if best is None:
        return None
    sent = best[1].send(direction)
    if sent is not None and policy.last_reason != me_device_attacks.DEVICE_REASON:
        # A carried device (an item command).  An absorbed power keeps the owner its
        # ``send`` set (me_device_attacks.device_key): me_device_attacks_input answers
        # that owner's kind, power and aim prompts and closes a charging power's.
        policy.last_reason = REASON_CLOSE_AREA
    return sent


def _haste_key(policy, snapshot: Snapshot) -> str | None:
    """「加速は魔道具術師など消耗品を使用しない場合に限定」: the absorbed Speed only."""
    if not magic_eater(snapshot) or policy._player_hasted(snapshot):
        return None
    return me_absorbed_substitutes.cast(policy, snapshot, ("staff", SV_STAFF_SPEED), REASON_CLOSE_HASTE)


def _close_key(policy, snapshot: Snapshot, current: Plan) -> str | None:
    """The last animal (design 5.1): area, haste, step out and strike, chase to the exit."""
    members = _members(snapshot, current.races)
    here = snapshot.player.position
    if len(members) > 1:
        _release(policy, "close-more-than-one")
        return None
    if members:
        current.target = members[0].position
    adjacent = [monster for monster in members if game_distance(here, monster.position) <= 1]
    if adjacent:
        answer = combat_answer.adjacent_attack(policy, snapshot, adjacent, REASON_CLOSE_MELEE)
        if answer is not None:
            return answer.key
    if current.target is None:
        _release(policy, "close-lost")
        return None
    if here == current.pocket and members:
        area = _area_into_mouth(policy, snapshot, current, members[0])
        if area is not None:
            return area
    if not current.hasted:
        current.hasted = True
        haste = _haste_key(policy, snapshot)
        if haste is not None:
            return haste
    standing = _index(current, here)
    if standing is None or standing < 0:
        _release(policy, "close-exit")   # 「出口まで追う」: the start cell is the exit
        return None
    following = current.tunnel.before(standing)
    return _step(policy, snapshot, following, REASON_CLOSE_STEP)


def _hold_key(policy, snapshot: Snapshot, current: Plan) -> str | None:
    here = snapshot.player.position
    if here != current.pocket or not geo.pocket_holds(snapshot, current.pocket, current.mouth, presume=True):
        _release(policy, "pocket-lost")
        return None
    members = _members(snapshot, current.races)
    adjacent = [monster for monster in policy._physical_hostiles(snapshot)
                if game_distance(here, monster.position) <= 1]
    if adjacent or getattr(policy, "_took_damage", False):
        # Contact: a monster on the mouth, or a hit taken (a breath into the mouth).
        current.contact_turn = snapshot.turn
        current.detected_turn = None
    if adjacent:
        answer = combat_answer.adjacent_attack(policy, snapshot, adjacent, REASON_MELEE)
        if answer is not None:
            return answer.key
    if snapshot.turn - current.contact_turn < WAIT_GAME_TURNS:
        policy.last_reason = REASON_HOLD
        return WAIT_KEY
    if current.detected_turn is None:
        current.detected_turn = snapshot.turn
        detect = _detect_key(policy, snapshot, current)
        if detect is not None:
            return detect
    if current.animal and len(members) == 1:
        current.phase = "close"
        current.target = members[0].position
        return _close_key(policy, snapshot, current)
    if members and snapshot.turn - current.detected_turn < WAIT_GAME_TURNS:
        policy.last_reason = REASON_HOLD
        return WAIT_KEY
    _release(policy, "pack-gone" if not members else "pack-stays-out")
    return None


def holds(policy, snapshot: Snapshot) -> bool:
    """The player stands on the pocket of a holding plan (``_forbid_wait_while_damaged``)."""
    current = plan(policy)
    return (current is not None and current.floor == snapshot.floor_key and current.phase == "hold"
            and snapshot.player.position == current.pocket)


def key(policy, snapshot: Snapshot, hostiles) -> str | None:
    """The Anaguma rung (dungeon_ladder floor-avoidance layer); None leaves the board below.

    A plan released on this floor is not made again for the same pack (any race in common)
    within ``RETRY_GAME_TURNS``: once made, a plan stays until it ends or is released, and its
    release holds (n1-b life-367, ``_latched``)."""
    policy._anaguma_released = None
    answer = _decide(policy, snapshot, hostiles)
    released = policy._anaguma_released
    if released is not None and released.floor == snapshot.floor_key:
        policy._anaguma_retry = (snapshot.floor_key, released.races, snapshot.turn)
    return answer


def _decide(policy, snapshot: Snapshot, hostiles) -> str | None:
    current = plan(policy)
    if current is not None and current.floor != snapshot.floor_key:
        _release(policy, "floor-changed")
        current = None
    if not _floor_allowed(policy, snapshot) or not _able(snapshot):
        if current is not None:
            _release(policy, "unable")
        return None
    if policy._escape_state.owner is not None:
        if current is not None:
            _release(policy, "escape-owner")
        return None
    if _latched(policy, "wall-passer", snapshot.floor_key, wall_passer(policy, snapshot), snapshot.turn):
        if current is not None:
            _release(policy, "wall-passer")
        policy._anaguma_veto = "wall-passer"
        return None
    adjacent = [monster for monster in hostiles
                if game_distance(snapshot.player.position, monster.position) <= 1]
    if current is not None and hostiles and policy._should_flee(snapshot, hostiles, adjacent):
        on_pocket = current.phase in ("hold", "close") or (
            current.phase == "dig" and _index(current, snapshot.player.position) not in (None, -1))
        _release(policy, "flee")
        return _escape_key(policy, snapshot) if on_pocket else None
    if (current is not None and current.phase in ("walk", "dig") and not _dug(snapshot, current)
            and _latched(policy, "runners", (snapshot.floor_key, current.races),
                         runners(snapshot, current.races), snapshot.turn)):
        _release(policy, "runners")   # not dug yet: a pack that runs never comes to the mouth
        policy._anaguma_veto = "runners"
        return None
    if current is None:
        found = _pack(policy, snapshot)
        if found is None:
            return None
        races, animal = found
        if sealed_pocket.sealed_region(policy, snapshot) is not None:
            # Walled in: no pack walks to the player, and the charges are the way out
            # (sealed_pocket, owner 2026-11-05 「*破壊*後全方位壁なら岩石溶解で脱出すれば良い」).
            policy._anaguma_veto = "sealed"
            return None
        if hostiles and policy._should_flee(snapshot, hostiles, adjacent):
            policy._anaguma_veto = "flee"
            return None
        if adjacent:
            policy._anaguma_veto = "contact"
            return None
        if _latched(policy, "runners", (snapshot.floor_key, races), runners(snapshot, races), snapshot.turn):
            policy._anaguma_veto = "runners"
            return None
        retry = getattr(policy, "_anaguma_retry", None)
        if (retry is not None and retry[0] == snapshot.floor_key and retry[1] & races
                and snapshot.turn - retry[2] < RETRY_GAME_TURNS):
            policy._anaguma_veto = "retry-window"
            return None
        refused = getattr(policy, "_anaguma_refused", None)
        if (refused is not None and refused[0] == snapshot.floor_key and refused[1] == races
                and snapshot.turn - refused[2] < RETRY_GAME_TURNS):
            return None
        current = _candidate(policy, snapshot, races, animal)
        if current is None:
            policy._anaguma_refused = (snapshot.floor_key, races, snapshot.turn)
            return None
        setattr(policy, MEMORY, current)
    if current.phase in ("walk", "dig"):
        current.phase = "dig" if _index(current, snapshot.player.position) is not None else "walk"
        if adjacent:
            standing = _index(current, snapshot.player.position)
            if standing is not None and standing + 1 >= OTHER_LENGTH and geo.pocket_holds(
                    snapshot, current.tunnel.cells[standing], current.tunnel.before(standing), presume=True):
                current.length = standing + 1
                current.phase = "hold"
            else:
                _release(policy, "contact-before-pocket")
                return None
        else:
            dig = _dig_key(policy, snapshot, current)
            if dig is not None or plan(policy) is None:
                return dig
    if current.phase == "hold":
        return _hold_key(policy, snapshot, current)
    if current.phase == "close":
        return _close_key(policy, snapshot, current)
    return None
