"""Quest 25: landed in a room whose only way out is a great-hall door.

Owner 2026-11-12 (n1-c life-200; strategy/quests/QUEST_25.jsonc ``sealed_rooms``):
「待って向かってくる敵がいれば迎撃する。100ターンで切り上げる。どこに落ちたかによって作戦は変わる。
左中央ならイプシシマスの召還を受けないようにラアルとクイルスルグを範囲攻撃で倒す。そのあと全快にして
加速してイプシシマスを遠距離最大火力で倒す。右なら全快にして加速してイプシシマスを遠距離最大火力で倒し、
続いて大広間の残りを倒す。」

n1-c life-200 (2026-11-12 12:03:02): a Teleportation dropped the player on [13,11] in the
south-middle room; the plan walked back to its post through the door [10,11] into the hall, a
quylthulg threw it east (TELE_AWAY) into the hounds, and it died there.

The rooms (quest25_geometry.SEALED_ROOM_DOORS): 左 the south-west room (door [10,6]), 中央 the
south-middle room ([10,11]), 右 the south-east-ish room ([10,15]).  While the hall is dangerous
(the battle phases the teleport rule covers, quest_no_teleport.q25_hall_forbids), a board on one
of them runs this plan instead of the phase's own step (quest25_battle._phase_key), in steps:

 1. ``wait``: ``sealed_room_wait_actions`` (100) player actions on a cell of the room that no
    Ipsissimus summons onto with the door open and not beside the door; what comes is fought
    (``_engage``: beside, the blow; else a shot).
 2. 左・中央 ``clear``: the door opened (Stone to Mud from a summon-safe cell, else opened from
    beside it), then each quylthulg and the tome by a ball from a summon-safe cell of the room
    (geometry: radius 2 reaches [9,8] and [9,9] from both rooms, [9,13] from the middle one).
    No ball, or one that cannot reach what is left: the plan ends (the phase's own order goes on).
    ``ipsissimus``: 「全快にして」 the between-phases recharge and full HP (no enemy in view), then
    the phase-2 attack on the pen (``_ipsissimus``: 「加速して」 on its walk, the strongest attack).
 3. 右 ``prepare``: the recharge and full HP, the door opened, haste; ``ipsissimus``: from the
    room cell with a direct line to the pen cell aimed at and the fewest summoners, the strongest
    ranged attack (``_pen_shot``: the misses count the pen as escaped as on [5,1]); then
    ``hall``: the quylthulgs (``_quyls``) and the tome (``_tome``), the phases' own steps.
 4. ``done``: the phase's own order again; leaving the room forgets the plan (a new landing
    starts it over).  The ``ipsissimus`` and ``hall`` steps go on out of the room (the walk to
    the pen's stand, a throw by a quylthulg) until they end.

A target shot ``ROOM_SHOT_LIMIT`` times without a kill is left (a quylthulg blinks away).
"""
from __future__ import annotations

from hengbot import quest25_battle as battle_mod
from hengbot import quest25_geometry as geo
from hengbot.model import Position
from hengbot.quest_exposure import game_distance, projectable

# Shots at one target of the clear without a kill line before it is left to the phases.
ROOM_SHOT_LIMIT = 20
LEFT_CENTRE = frozenset({"left", "centre"})
# The steps that go on once the player is out of the room (the pen's walk, a throw, the hall).
OUT_OF_ROOM_STEPS = frozenset({"ipsissimus", "hall"})


def applies(ctx) -> bool:
    """The hall is dangerous (the teleport rule's phases)."""
    through = ctx.values.no_teleport_through_phase
    return ctx.battle.phase <= battle_mod.phase_index(through)


def _state(ctx):
    room = ctx.battle.room
    return None if room is None else dict(zip(("name", "actions", "step", "turn", "shots"), room))


def _save(ctx, state) -> None:
    ctx.battle.room = (state["name"], state["actions"], state["step"], state["turn"], state["shots"])


def key(ctx) -> str | None:
    """The room's step, else None (not in a room, the plan done, or nothing for it to do)."""
    found = geo.sealed_room_of(ctx.terrain, ctx.here)
    state = _state(ctx)
    if not applies(ctx):
        ctx.battle.room = None
        return None
    if found is None and state is not None and state["step"] in OUT_OF_ROOM_STEPS:
        # The pen and the hall are fought out of the room too: the plan goes on.
        found = (state["name"], geo.SEALED_ROOM_DOORS[state["name"]])
    if found is None:
        ctx.battle.room = None
        return None
    name, door = found
    if state is None or state["name"] != name:
        state = {"name": name, "actions": 0, "step": "wait", "turn": None, "shots": 0}
    if state["turn"] != int(ctx.snapshot.turn):
        state["actions"] += 1
        state["turn"] = int(ctx.snapshot.turn)
    _save(ctx, state)
    if state["step"] == "wait":
        if state["actions"] < ctx.values.sealed_room_wait_actions:
            return _wait(ctx, name, door)
        state["step"] = "clear" if name in LEFT_CENTRE else "prepare"
        _save(ctx, state)
    if state["step"] == "clear":
        found_key = _clear(ctx, state, door)
        if found_key is not None:
            return found_key
        state = _state(ctx)
        if state["step"] == "clear":
            state["step"] = "done"
            _save(ctx, state)
            return None
    if state["step"] == "prepare":
        found_key = _prepare_right(ctx, door)
        if found_key is not None:
            return found_key
        state["step"] = "ipsissimus"
        _save(ctx, state)
    if state["step"] == "ipsissimus":
        found_key = (_ipsissimus_from_room(ctx, door) if name == "right"
                     else _ipsissimus_after_clear(ctx))
        if found_key is not None:
            return found_key
        # The pen done goes on to the hall (右); a pen no room cell reaches is the phases'.
        state["step"] = ("hall" if name == "right" and not battle_mod._ipsissimus_alive(ctx)
                         else "done")
        _save(ctx, state)
    if state["step"] == "hall":
        found_key = _rest_of_hall(ctx)
        if found_key is not None:
            return found_key
        state["step"] = "done"
        _save(ctx, state)
    return None


# -- the wait ---------------------------------------------------------------------------


def _safe_cells(ctx, door) -> list:
    """The room's cells no Ipsissimus summons onto with the door open, nearest first."""
    opened = geo.opened(ctx.terrain, [door])
    summons = geo.summon_cells(opened)
    cells = [cell for cell in geo.room_cells(ctx.terrain, door) if cell not in summons]
    return sorted(cells, key=lambda cell: (game_distance(cell, ctx.here), cell))


def _wait(ctx, name, door) -> str | None:
    targets = battle_mod._fight_targets(ctx)
    if targets and (answer := battle_mod._engage(ctx, targets)) is not None:
        return answer
    posts = [cell for cell in _safe_cells(ctx, door) if game_distance(cell, door) > 1]
    if posts and ctx.here not in posts:
        walked = battle_mod._walk(ctx, {posts[0]})
        if walked is not None:
            return walked
    return battle_mod._hold(ctx)


# -- the door ---------------------------------------------------------------------------


def _door_open(ctx, door) -> bool:
    grid = ctx.snapshot.grid_at(Position(*door))
    if grid is not None and grid.known and not grid.is_door:
        return True   # melted (Stone to Mud leaves floor)
    return not ctx.door_closed(door)


def _open_door(ctx, door, stand) -> str | None:
    """Stone to Mud from ``stand`` (a summon-safe cell with a line to the door), else the door
    opened from beside it."""
    if battle_mod._can_melt(ctx):
        if ctx.here != stand:
            return battle_mod._walk(ctx, {stand})
        return battle_mod._melt_key(ctx, door)
    if game_distance(ctx.here, door) <= 1:
        ctx.policy.last_reason = battle_mod.OPEN_REASON
        return ctx.policy._step_toward(ctx.snapshot, Position(*door))
    beside = {cell for cell in geo.room_cells(ctx.terrain, door) if game_distance(cell, door) == 1}
    return battle_mod._walk(ctx, beside)


def _melt_stand(ctx, door, preferred=None):
    lined = [cell for cell in _safe_cells(ctx, door) if projectable(ctx.terrain, cell, door)]
    if preferred is not None and preferred in lined:
        return preferred
    return lined[0] if lined else None


# -- 左・中央: the tome and the quylthulgs by balls, then the pen ----------------------------


def _left(ctx) -> list:
    """(cell, race) of the quylthulgs, then the tome, still on the floor."""
    placements = ctx.navigator.battlefield.monster_placements
    found = []
    if ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]:
        found += [(tuple(cell), geo.QUYL) for cell, race in placements
                  if race == geo.QUYL and tuple(cell) not in ctx.battle.quyls_done]
    if ctx.kills(geo.TOME) < geo.ROSTER[geo.TOME]:
        found += [(tuple(cell), geo.TOME) for cell, race in placements if race == geo.TOME]
    return found


def _ball_plan(ctx, door, targets):
    """(cell, race, stand, centre) of the first target a ball catches from a summon-safe cell."""
    opened = geo.opened(ctx.terrain, [door])
    safe = _safe_cells(ctx, door)
    for cell, race in targets:
        for radius in sorted({row[1] for row in battle_mod._balls(ctx, race)}, reverse=True):
            for stand in safe:
                centre = geo.ball_centre(opened, stand, cell, radius)
                if centre is not None:
                    return cell, race, stand, centre[1]
    return None


def _clear(ctx, state, door) -> str | None:
    targets = _left(ctx)
    if not targets:
        state["step"] = "ipsissimus"
        _save(ctx, state)
        return None
    shots = state["shots"]
    target = targets[0]
    if shots >= ROOM_SHOT_LIMIT:
        if target[1] != geo.QUYL:
            return None   # the tome is left to the phases' own order
        ctx.battle.quyls_done = ctx.battle.quyls_done | {target[0]}
        state["shots"] = 0
        _save(ctx, state)
        targets = _left(ctx)
        if not targets:
            state["step"] = "ipsissimus"
            _save(ctx, state)
            return None
    fighting = battle_mod._fight_targets(ctx)
    if any(monster.distance <= 1 for monster in fighting):
        return battle_mod._engage(ctx, fighting)
    plan = _ball_plan(ctx, door, targets)
    if plan is None:
        return None   # no ball reaches what is left: the phases' own order
    cell, race, stand, centre = plan
    if not _door_open(ctx, door):
        melt_from = _melt_stand(ctx, door, stand)
        return _open_door(ctx, door, melt_from if melt_from is not None else stand)
    if ctx.here != stand:
        return battle_mod._walk(ctx, {stand})
    if race == geo.QUYL:
        ctx.battle.aimed_quyl = cell
    shot = battle_mod._fire_at(ctx, centre, race, area_only=True)
    if shot is not None:
        state = _state(ctx)
        state["shots"] += 1
        _save(ctx, state)
    return shot


def note_kill(ctx) -> None:
    """A kill line resets the clear's shot count (called once per board)."""
    state = _state(ctx)
    if state is not None and any(battle_mod._killed_name(battle_mod.message_text(message))
                                 for message in ctx.snapshot.messages):
        state["shots"] = 0
        _save(ctx, state)


def _full(ctx) -> str | None:
    """「全快にして」: the between-phases recharge, then full HP, on a board with no enemy in view."""
    if ctx.in_view():
        return None
    return battle_mod._recharge_key(ctx) or battle_mod._full_hp_key(ctx)


def _ipsissimus_after_clear(ctx) -> str | None:
    if not battle_mod._ipsissimus_alive(ctx):
        return None
    targets = battle_mod._fight_targets(ctx)
    if any(monster.distance <= 1 for monster in targets):
        return battle_mod._engage(ctx, targets)
    return _full(ctx) or battle_mod._ipsissimus(ctx)


# -- 右: the pen from the room, then the rest of the hall ---------------------------------


def _prepare_right(ctx, door) -> str | None:
    if not battle_mod._ipsissimus_alive(ctx):
        return None
    targets = battle_mod._fight_targets(ctx)
    if targets:
        return battle_mod._engage(ctx, targets)
    if (full := _full(ctx)) is not None:
        return full
    if not _door_open(ctx, door):
        stand = _melt_stand(ctx, door)
        return _open_door(ctx, door, stand if stand is not None else ctx.here)
    return battle_mod._haste(ctx)


def _pen_aims(ctx) -> list:
    seen = [(monster.position.y, monster.position.x) for monster in ctx.hostiles()
            if monster.race_id == geo.IPSISSIMUS
            and (monster.position.y, monster.position.x) in geo.IPSISSIMUS_PEN]
    return seen or list(geo.IPSISSIMUS_PEN)


def _ipsissimus_from_room(ctx, door) -> str | None:
    if not battle_mod._ipsissimus_alive(ctx):
        return None
    targets = [monster for monster in battle_mod._fight_targets(ctx) if monster.distance <= 1]
    if targets:
        return battle_mod._engage(ctx, targets)
    opened = geo.opened(ctx.terrain, [door])
    counts = geo.summon_counts(opened)
    room = geo.room_cells(ctx.terrain, door)
    for aim in _pen_aims(ctx):
        stands = sorted((counts.get(cell, 0), game_distance(cell, ctx.here), cell) for cell in room
                        if projectable(opened, cell, aim))
        if not stands:
            continue
        stand = stands[0][2]
        if ctx.here != stand:
            return battle_mod._walk(ctx, {stand}) or battle_mod._hold(ctx)
        if (haste := battle_mod._haste(ctx)) is not None:
            return haste
        return battle_mod._pen_shot(ctx, battle_mod._fire_at(ctx, aim, geo.IPSISSIMUS))
    return None


def _rest_of_hall(ctx) -> str | None:
    """「続いて大広間の残りを倒す」: the quylthulgs, then the tome, by the phases' own steps."""
    if not battle_mod._quyls_done(ctx):
        return battle_mod._quyls(ctx)
    if not battle_mod._tome_done(ctx):
        return battle_mod._tome(ctx)
    return None
