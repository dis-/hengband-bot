"""The Magic-Eater's battle on Angband 99F (Oberon) and 100F (the Serpent of Chaos).

Owner 2026-11-20 (verbatim, the directive this module carries out line by line):
「降りたらフロアを破壊しながら一巡し、対象以外のモンスターを極力減らす。この作業時のみ対象を巻き込んでも良い。
加速し耐性の薬を飲み、なるべく距離をとって相対するように岩石溶解を使って射線を通す。可能なら相手の移動後に射線が
通るようにして、先手を取ること。
コストを払った後にHPが800ポイント残ることを確認して強力発動ロケットで攻撃する。
攻撃を受けてHPが400を下回った時は*体力回復*の薬で回復する。
召喚または攻撃を受けてHPが800を下回ったとき、または対象が距離2より近づいたときテレポートの巻物で離脱する。
対象が破壊範囲内にいないとき、対象以外のあらゆるモンスターを破壊で排除する。必要なら強力発動で範囲を広げる。
破壊を使用した後は周辺感知で地形把握する。
テレポートによる離脱後、安全が確保できたらHPや取り込み魔法道具回数を必要に応じて回復。
回復できたら最後に対象をみた座標に向かって移動。場所を把握できたら岩石溶解を使うところから繰り返し。
帰還による離脱は成功時と魔力復活の薬を予定の倍以上使ったときのみ。」

The game (C:/hengband/src):
* *Destruction* (spell-kind/spells-floor.cpp destroy_area) deletes every monster in its circle but
  a QUESTOR, which is healed to full and teleported away; Oberon and the Serpent are the floors'
  QUESTORs.  Hence the sweep may take the target in (it is unhurt then) and the battle's
  *Destruction* waits for the target to be outside the circle.  The staff's radius is
  13 + randint0(5), the Powerful Activation's 18 + randint0(5) (cmd-item/cmd-usestaff.cpp:282):
  destruction_use.GUARANTEED_RADIUS / WORST_RADIUS and ``POWERED_SURE`` / ``POWERED_WORST`` here.
* The Rocket (cmd-item/cmd-zapwand.cpp:56-57, :301-303) through Powerful Activation: a radius-3
  ball of 250 + 2 x level x 3 (me_device_attacks ``powered``); Powerful Activation costs
  10 + (level - 10) / 2 hit points at worst (racial/class-racial-switcher.cpp:229-235, a
  Magic-Eater has no mana: me_powerful_activation ``cost``), paid on a failure too.
* *Healing* (quaff-effects.cpp) heals 1000; Teleportation (read-execution) moves 100 grids.

The per-board order (``key``), the first that answers wins:
 1. the recall: on success (the floor's quest no longer TAKEN) or with twice the Restore Mana
    target used (angband_finale ``restore_mana_overspent``), and nowhere else;
 2. *Healing* below 400 HP after a hit;
 3. the Teleportation scroll: below 800 HP after a hit or a summon, or the target closer than
    distance 2; the next boards recover (``RECOVER``);
 4. the arrival sweep (``SWEEP``): *Destruction* on every other monster within its circle, the
    target allowed, walking to the next one; the map after each use (周辺感知);
 5. the recovery after a teleport: once no awake hostile is in view, Restore Mana while the
    rocket can take a potion's refill, then rest to full HP; then on to the last-seen cell;
 6. the battle: *Destruction* (powered when only it reaches) on the other monsters while the
    target is outside its worst circle; haste and the Resistance potion; the powered Rocket when
    a line projects and HP - cost >= 800; else the stand on one of the eight rays of the target,
    as far as the Rocket reaches, opened with Stone to Mud, its last wall kept until the target
    is off the ray so that the target's own move opens the line (the first action is ours).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import angband_finale, destruction_use, me_capability, me_device_attacks
from hengbot.model import Position, game_distance

REASON = "angband-finale"
RECALL_REASON = f"{REASON}:recall"
STAR_HEAL_REASON = f"{REASON}:star-healing"
HEAL_REASON = f"{REASON}:healing"
TELEPORT_REASON = f"{REASON}:teleport"
SWEEP_SUFFIX = f":{REASON}-sweep"
CLEAR_SUFFIX = f":{REASON}-clear"
SWEEP_WALK_REASON = f"{REASON}:sweep-walk"
MAP_REASON = f"{REASON}:map"
HASTE_REASON = f"{REASON}:haste"
RESIST_REASON = f"{REASON}:resistance"
RESTORE_MANA_REASON = f"{REASON}:restore-mana"
REST_REASON = f"{REASON}:rest"
APPROACH_REASON = f"{REASON}:approach"
STAND_WALK_REASON = f"{REASON}:stand-walk"
MELT_REASON = f"{REASON}:melt"
HOLD_REASON = f"{REASON}:hold"
RECALL_TRIGGER = "angband-finale"
AFTER_DESTRUCTION = "after-destruction"  # me_powers' trigger of the map after a *Destruction*

# Owner 2026-11-20's lines.
FIRE_HP_AFTER_COST = 800
STAR_HEAL_BELOW = 400
TELEPORT_BELOW = 800
TELEPORT_CLOSER_THAN = 2
# The Rocket's reach: get_max_range() 18 (angband-system.cpp:45-48); the stand is at least
# TELEPORT_CLOSER_THAN + 1 away so that standing there is no teleport.
ROCKET_RANGE = 18
STAND_MIN_DISTANCE = TELEPORT_CLOSER_THAN + 1
ROCKET = ("wand", 29)
POWERED_SURE = 18
POWERED_WORST = 22
# The boards the last wall is kept while the target stands on the ray (「可能なら」: then opened).
LAST_WALL_HOLD = 10
# The boards a fully open stand waits for the target to cross its ray before a new stand.
OPEN_STAND_WAIT = 20
# The stands tried for a route, best first (each one BFS).
STAND_ROUTE_TRIES = 6
DIRECTIONS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))

SWEEP, BATTLE, RECOVER = "sweep", "battle", "recover"
MEMORY = "_angband_finale_battle"


@dataclass
class Stand:
    cell: tuple[int, int]
    aim: tuple[int, int]              # the target's cell the ray was drawn from
    step: tuple[int, int]             # the ray's direction from the aim toward the stand
    distance: int
    held: int = 0                     # boards the last wall was kept / the open ray waited


@dataclass
class Battle:
    floor: tuple | None = None
    phase: str = SWEEP
    last_seen: tuple[int, int] | None = None
    prev_hp: int | None = None
    attacked: bool = False
    summoned: bool = False
    stand: Stand | None = None
    swept_out: set = field(default_factory=set)  # monsters the sweep's walk could not reach


def battle(policy, snapshot) -> Battle:
    held = getattr(policy, MEMORY, None)
    if held is None or held.floor != snapshot.floor_key:
        held = Battle(floor=snapshot.floor_key, prev_hp=snapshot.player.hp)
        setattr(policy, MEMORY, held)
    return held


def applies(policy, snapshot) -> bool:
    return (angband_finale.magic_eater(snapshot) and angband_finale.lifted(policy)
            and angband_finale.on_finale_floor(snapshot))


def _known_hostiles(snapshot) -> list:
    seen = {}
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if monster.hostile and monster.index not in seen:
            seen[monster.index] = monster
    return list(seen.values())


def target_monster(snapshot):
    race = angband_finale.target_race(snapshot)
    return next((monster for monster in _known_hostiles(snapshot) if monster.race_id == race), None)


def others(snapshot) -> list:
    race = angband_finale.target_race(snapshot)
    return [monster for monster in _known_hostiles(snapshot) if monster.race_id != race]


def _observe(policy, snapshot, held: Battle) -> None:
    from hengbot import me_powerful_activation, summon_response  # import cycle
    hp = snapshot.player.hp
    # The Powerful Activation's own HP cost is no hit (me_powerful_activation ``own_cost``).
    held.attacked = (held.prev_hp is not None and hp < held.prev_hp
                     and not me_powerful_activation.own_cost(policy, snapshot))
    held.prev_hp = hp
    held.summoned = any(summon_response.summons_of(message) for message in snapshot.messages)
    target = target_monster(snapshot)
    if target is not None:
        held.last_seen = (target.position.y, target.position.x)


# -- the items ---------------------------------------------------------------------------

def _carried(snapshot, kind):
    return next((item for item in snapshot.inventory
                 if (item.tval, item.sval) == kind and item.aware and item.count > 0), None)


def _quaff(policy, snapshot, kind, reason) -> str | None:
    from hengbot.item_reservation import reserved_item_command
    potion = _carried(snapshot, kind)
    if potion is None:
        return None
    policy.last_reason = reason
    return reserved_item_command(policy, snapshot, "quaff", potion)


def _teleport(policy, snapshot) -> str | None:
    scroll = _carried(snapshot, angband_finale.TELEPORT)
    if scroll is None or not policy._can_read_scrolls(snapshot):
        return None
    policy.last_reason = TELEPORT_REASON
    return policy._read_key(snapshot, scroll)


def _recall(policy, snapshot) -> str | None:
    """Word of Recall under the directive's two cases (once_quest_recall.read_key, deliberate:
    this rule decided the leave)."""
    from hengbot import once_quest_recall, return_start
    if snapshot.player.recalling:
        return None
    if not policy._returning_to_town or policy._last_return_trigger != RECALL_TRIGGER:
        return_start.start(policy, RECALL_TRIGGER)
    return once_quest_recall.read_key(policy, snapshot, RECALL_REASON, deliberate=True)


def recall_permitted(policy, snapshot) -> bool:
    """The directive's recall cases on this floor (policy ``_quest_floor_exit_locked`` lets
    them through)."""
    return applies(policy, snapshot) and (
        angband_finale.quest_done(snapshot)
        or angband_finale.restore_mana_overspent(policy, snapshot))


# -- the rocket -------------------------------------------------------------------------

def _rocket_power(policy):
    return next((power for power, _row in me_device_attacks.held_powers(policy)
                 if power.ident == ROCKET), None)


def rocket_charges(policy, snapshot) -> int:
    return max(0, me_capability.charges(policy, snapshot, *ROCKET))


def fire_hp_holds(snapshot) -> bool:
    """「コストを払った後にHPが800ポイント残る」: the worst cost of the Powerful Activation."""
    from hengbot import me_powerful_activation
    player = snapshot.player
    return player.hp - me_powerful_activation.cost(player.level) >= FIRE_HP_AFTER_COST


def _rocket(policy, snapshot, target) -> str | None:
    power = _rocket_power(policy)
    if (power is None or rocket_charges(policy, snapshot) <= 0
            or not me_device_attacks.can_use_powers(snapshot)):
        return None
    return me_device_attacks.device_target_key(
        policy, me_device_attacks.powered(power), target.position, snapshot)


def _refill_worth(policy, snapshot) -> bool:
    """A Restore Mana's rocket refill lands whole (spells-status.cpp restore_mana: a power
    gains count / 3, 3 below ten, never past its count)."""
    from hengbot import restore_mana_target
    count = me_capability.count(policy, snapshot, *ROCKET)
    if count <= 0:
        return False
    return rocket_charges(policy, snapshot) <= count - restore_mana_target.uses_per_potion(count)


def _restore_mana(policy, snapshot) -> str | None:
    if not _refill_worth(policy, snapshot):
        return None
    return _quaff(policy, snapshot, angband_finale.RESTORE_MANA, RESTORE_MANA_REASON)


# -- *Destruction* and the map --------------------------------------------------------

def _map_key(policy, snapshot) -> str | None:
    """「破壊を使用した後は周辺感知で地形把握する」: the absorbed map power's FLOOR occasion
    (me_powers, the after-destruction trigger), else a carried device (area_mapping)."""
    from hengbot import area_mapping, me_powers
    if not area_mapping.mapping_due(policy, snapshot):
        return None
    key = me_powers.power_key(policy, snapshot, me_powers.FLOOR, only=AFTER_DESTRUCTION)
    if key is None:
        key = area_mapping.after_destruction_key(policy, snapshot)
    return key


def _within(snapshot, monsters, radius) -> list:
    here = snapshot.player.position
    return [monster for monster in monsters if game_distance(here, monster.position) <= radius]


def _destroy(policy, snapshot, subjects, suffix, *, powerful=False) -> str | None:
    """destruction_use's use on ``subjects`` (its gates: a clear head, a floor it touches)."""
    subject_list = list(subjects)

    def in_range(_policy, _snapshot, _target):
        return bool(subject_list)
    return destruction_use.key(policy, snapshot, in_range=in_range, suffix=suffix,
                               powerful=powerful)


def _sweep_key(policy, snapshot, held: Battle) -> str | None:
    """The arrival sweep: the other monsters destroyed, the target allowed in the circle."""
    mapped = _map_key(policy, snapshot)
    if mapped is not None:
        return mapped
    rest = [monster for monster in others(snapshot) if monster.index not in held.swept_out]
    if not rest or not destruction_use.means_in_hand(policy, snapshot):
        held.phase = BATTLE
        return None
    near = _within(snapshot, rest, destruction_use.GUARANTEED_RADIUS)
    if near:
        used = _destroy(policy, snapshot, near, SWEEP_SUFFIX)
        if used is not None:
            return used
    here = snapshot.player.position
    for monster in sorted(rest, key=lambda each: game_distance(here, each.position)):
        step = destruction_use.walk_step(policy, snapshot, monster)
        if step is not None:
            key = policy._step_toward(snapshot, step)
            policy.last_reason = SWEEP_WALK_REASON
            return key
        held.swept_out.add(monster.index)
    held.phase = BATTLE
    return None


def _clear_key(policy, snapshot, held: Battle) -> str | None:
    """「対象が破壊範囲内にいないとき、対象以外のあらゆるモンスターを破壊で排除する。必要なら強力発動で
    範囲を広げる。」  The target's cell is where it is seen, else where it was last seen."""
    rest = others(snapshot)
    if not rest:
        return None
    here = snapshot.player.position
    target = target_monster(snapshot)
    aim = target.position if target is not None else (
        Position(*held.last_seen) if held.last_seen is not None else None)
    distance = game_distance(here, aim) if aim is not None else None
    if distance is None or distance > destruction_use.WORST_RADIUS:
        near = _within(snapshot, rest, destruction_use.GUARANTEED_RADIUS)
        if near:
            used = _destroy(policy, snapshot, near, CLEAR_SUFFIX)
            if used is not None:
                return used
    if distance is None or distance > POWERED_WORST:
        reach = _within(snapshot, rest, POWERED_SURE)
        if reach:
            return _destroy(policy, snapshot, reach, CLEAR_SUFFIX, powerful=True)
    return None


# -- the stand (Stone to Mud) ------------------------------------------------------------

def _grid(snapshot, cell):
    return snapshot.grid_at(Position(*cell))


def _open(grid) -> bool:
    return grid is not None and grid.known and grid.passable and not grid.wall


def _walls_between(snapshot, stand: Stand) -> list | None:
    """The cells between the stand and the aim that stop the Rocket (a wall, an unknown grid),
    nearest the stand first; None when one of them cannot be melted (a permanent wall)."""
    walls = []
    for k in range(stand.distance - 1, 0, -1):
        cell = (stand.aim[0] + stand.step[0] * k, stand.aim[1] + stand.step[1] * k)
        grid = _grid(snapshot, cell)
        if grid is not None and grid.known and getattr(grid, "permanent", False):
            return None
        if not _open(grid):
            walls.append(cell)
    return walls


def _candidates(policy, snapshot, aim) -> list:
    from hengbot import sealed_pocket
    charges = sealed_pocket.melt_charges(policy, snapshot)
    found = []
    for step in DIRECTIONS:
        for distance in range(ROCKET_RANGE, STAND_MIN_DISTANCE - 1, -1):
            cell = (aim[0] + step[0] * distance, aim[1] + step[1] * distance)
            if not _open(_grid(snapshot, cell)):
                continue
            stand = Stand(cell, aim, step, distance)
            walls = _walls_between(snapshot, stand)
            if walls is None or len(walls) > charges:
                continue
            # 「なるべく距離をとって」: the farthest first, then the fewest walls.
            found.append(((-distance, len(walls)), stand))
    found.sort(key=lambda pair: pair[0])
    return [stand for _, stand in found]


def _choose_stand(policy, snapshot, aim) -> Stand | None:
    here = (snapshot.player.position.y, snapshot.player.position.x)
    for tried, stand in enumerate(_candidates(policy, snapshot, aim)):
        if tried >= STAND_ROUTE_TRIES:
            break
        if stand.cell == here:
            return stand
        target = Position(*stand.cell)
        if policy._nearest_goal_step(snapshot, lambda grid, goal=target: grid.position == goal) is not None:
            return stand
    return None


def _on_ray(stand: Stand, cell) -> bool:
    dy, dx = cell[0] - stand.cell[0], cell[1] - stand.cell[1]
    sy, sx = -stand.step[0], -stand.step[1]
    steps = max(abs(dy), abs(dx))
    return 0 < steps <= ROCKET_RANGE and (dy, dx) == (sy * steps, sx * steps)


def _stand_key(policy, snapshot, held: Battle, target) -> str | None:
    """「なるべく距離をとって相対するように岩石溶解を使って射線を通す。可能なら相手の移動後に射線が通る
    ようにして、先手を取ること。」"""
    from hengbot import sealed_pocket
    from hengbot.policy_constants import WAIT_KEY
    aim = (target.position.y, target.position.x)
    stand = held.stand
    if stand is None or not _open(_grid(snapshot, stand.cell)):
        stand = held.stand = _choose_stand(policy, snapshot, aim)
    if stand is None:
        return None
    here = (snapshot.player.position.y, snapshot.player.position.x)
    if here != stand.cell:
        goal = Position(*stand.cell)
        step = policy._nearest_goal_step(snapshot, lambda grid: grid.position == goal)
        if step is None:
            held.stand = None
            return None
        key = policy._step_toward(snapshot, step)
        policy.last_reason = STAND_WALK_REASON
        return key
    walls = _walls_between(snapshot, stand)
    if walls is None:
        held.stand = None
        return None
    on_ray = _on_ray(stand, aim)
    if walls:
        if len(walls) == 1 and on_ray and stand.held < LAST_WALL_HOLD:
            # The last wall waits: opened now, the line would be the target's first.
            stand.held += 1
            policy.last_reason = HOLD_REASON
            return WAIT_KEY
        stand.held = 0
        return sealed_pocket.melt_at_key(policy, snapshot, Position(*walls[0]), MELT_REASON)
    if stand.held >= OPEN_STAND_WAIT:
        held.stand = None
        return None
    stand.held += 1
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


# -- the board ------------------------------------------------------------------------------

def _safe(policy, snapshot) -> bool:
    """「安全が確保できたら」: no awake hostile in view."""
    return not any(monster.hostile and not monster.asleep for monster in snapshot.visible_monsters)


def _recover_key(policy, snapshot, held: Battle) -> str | None:
    from hengbot.policy_constants import REST_MACRO
    if not _safe(policy, snapshot):
        return None
    restored = _restore_mana(policy, snapshot)
    if restored is not None:
        return restored
    if snapshot.player.hp < snapshot.player.max_hp:
        policy.last_reason = REST_REASON
        return REST_MACRO
    held.phase = BATTLE
    held.stand = None
    return None


def _approach_key(policy, snapshot, held: Battle) -> str | None:
    """「最後に対象をみた座標に向かって移動」."""
    if held.last_seen is None:
        return None
    goal = Position(*held.last_seen)
    if snapshot.player.position == goal:
        return None
    step = policy._nearest_goal_step(snapshot, lambda grid: grid.position == goal)
    if step is None:
        return None
    key = policy._step_toward(snapshot, step)
    policy.last_reason = APPROACH_REASON
    return key


def _fight_key(policy, snapshot, held: Battle, target) -> str | None:
    from hengbot import haste_read, line_of_fire, resist_potion, speed_dose
    if not haste_read.hasted(policy, snapshot):
        dose = speed_dose.key(policy, snapshot, HASTE_REASON)
        if dose is not None:
            return dose
    if not resist_potion.covered(snapshot.player):
        drink = resist_potion.quaff_key(policy, snapshot, RESIST_REASON)
        if drink is not None:
            return drink
    here = snapshot.player.position
    if line_of_fire.player_projectable(policy, snapshot, here, target.position):
        if rocket_charges(policy, snapshot) <= 0:
            return _quaff(policy, snapshot, angband_finale.RESTORE_MANA, RESTORE_MANA_REASON)
        if not fire_hp_holds(snapshot):
            # Not named by the directive: the Potion of Healing it carries raises the HP to the
            # shot's 800 + cost (reported to the owner as a question).
            return _quaff(policy, snapshot, angband_finale.HEALING, HEAL_REASON)
        held.stand = None
        return _rocket(policy, snapshot, target)
    return _stand_key(policy, snapshot, held, target)


def key(policy, snapshot) -> str | None:
    """The finale's answer on this board, else None (the ladder below)."""
    small = _small_floor(policy, snapshot)
    if small is not None:
        return small
    if not applies(policy, snapshot):
        return None
    held = battle(policy, snapshot)
    _observe(policy, snapshot, held)
    player = snapshot.player
    if recall_permitted(policy, snapshot):
        recall = _recall(policy, snapshot)
        if recall is not None:
            return recall
    target = target_monster(snapshot)
    distance = game_distance(player.position, target.position) if target is not None else None
    if held.attacked and player.hp < STAR_HEAL_BELOW:
        healed = _quaff(policy, snapshot, angband_finale.STAR_HEALING, STAR_HEAL_REASON)
        if healed is not None:
            return healed
    if ((player.hp < TELEPORT_BELOW and (held.attacked or held.summoned))
            or (distance is not None and distance < TELEPORT_CLOSER_THAN)):
        away = _teleport(policy, snapshot)
        if away is not None:
            held.phase, held.stand = RECOVER, None
            return away
    if held.phase == SWEEP:
        swept = _sweep_key(policy, snapshot, held)
        if swept is not None:
            return swept
    if held.phase == RECOVER:
        recovered = _recover_key(policy, snapshot, held)
        if recovered is not None:
            return recovered
    mapped = _map_key(policy, snapshot)
    if mapped is not None:
        return mapped
    cleared = _clear_key(policy, snapshot, held)
    if cleared is not None:
        return cleared
    if target is not None:
        return _fight_key(policy, snapshot, held, target)
    return _approach_key(policy, snapshot, held)


def _small_floor(policy, snapshot) -> str | None:
    """The option before the descent: on an Angband floor of the 95F exploration or deeper,
    short of 99F (angband_finale ``small_floor_key``)."""
    from hengbot.model import DUNGEON_ANGBAND
    if (snapshot.in_town or snapshot.floor_key[0] != DUNGEON_ANGBAND
            or snapshot.dungeon_level < angband_finale.PREPARE_DEPTH):
        return None
    return angband_finale.small_floor_key(policy, snapshot)
