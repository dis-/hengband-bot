"""Quest 25: a roster monster no walk reaches, opened by melting a granite wall and shot.

n1-c life-211 (2026-11-15 09:25-09:36): the sweep's detection (phase6_sweep) showed a Nexus
quylthulg (480) on [7,4], the map's sealed pocket 『Z』 -- rows 6-9, columns 2-5, permanent walls
and the granite [9,3] (QUEST_25 ``phase1`` (6): the hound's pocket, 「花崗岩 [9,3] を抜けて」).  No
walk reaches it, and the quest (KILL_ALL) is won only with it dead.  Owner 2026-11-15 (answer to
「[9,3] を溶かして撃ってよいか、岩石溶解が無い時はどうするか」): 「溶かして撃つ・無ければ帰還」.

``key`` (the sweep, quest25_battle ``_sweep``, when every cell its detection showed is one no walk
reaches):

 1. The plan of the cell (``plan``), from the map and the board, not from fixed cells: a wall of the
    map the board shows known and not permanent (granite; Stone to Mud turns it to floor,
    effect-feature.cpp KILL_WALL), a standable cell beside it a walk reaches, and from that cell,
    with the wall melted, a line of fire to the target's cell (quest_exposure ``projectable``).
    The nearest such stand by the walk.  On the shipped map: the granite [9,3] from [10,2].
 2. The walk to the stand; there, while the board shows the wall, Stone to Mud aimed at it
    (quest25_battle ``_melt_key``: the absorbed power first, then a carried wand).
 3. Then the shot at the target's cell, as phase 3 shoots a quylthulg (owner 2026-11-06
    「範囲攻撃があればネクサス・クイルスルグを倒すまたはショートテレポートさせるまで撃つ」): the strongest
    attack aimed at the cell (quest25_battle ``_unseen_fire``: unseen, an attack aimed at the grid;
    seen, the launcher too).  A kill line ends it (the kill count); a monster seen elsewhere is the
    sweep's again (it walks to it); shots in a row with no hit, pain or kill line (the owner's
    「当たらない撃ちで補う」 count, ``pen_misses_to_escaped``) say it moved (BLINK, TELE_AWAY): the
    cell is forgotten and the sweep detects again.
 3a. A target no line from beside the wall reaches, the melted wall's own cell does: the stand melts
    it, the player steps onto the melted cell and shoots from there (``fire_cell``).  n1-b life-416
    (2026-11-23 00:50, turn 2507389): the sweep's detection showed the second Nexus quylthulg on
    [8,3]; from [10,2] the line to [8,3] crosses the permanent [9,2], every other cell beside
    [9,3] is a permanent wall or inside the pocket, so no stand was found and the sweep held on
    [8,21] for 90,000 game turns (``stall:floor-dwell:quest-strategy:hold``).  The owner's
    「溶かして撃つ」 is the melt and the shot; the cell it is shot from is the plan's.
 4. With no Stone to Mud (no absorbed power, no carried wand) and the wall still standing: the
    floor is given up (``_unviable_quest_floor``, the leave the ONCE quest's hold does not reverse,
    as the random quest's T1 target gives it up, owner 2026-11-13 「階を諦めて帰還する」) and Word of
    Recall is read (``RECALL_REASON``; the quest fails, once_quest_recall ``read_key``).
"""

from __future__ import annotations

from hengbot import once_quest_recall, quest_exposure
from hengbot import quest25_battle as battle_mod
from hengbot import quest25_geometry as geo
from hengbot.model import Position
from hengbot.policy_constants import WAIT_KEY
from hengbot.unseen_strike import message_text

WALK_REASON = f"{battle_mod.REASON}:walk-to-melt"
RECALL_REASON = f"{battle_mod.REASON}:sealed-pocket-recall"
STEP_IN_REASON = f"{battle_mod.REASON}:step-into-melted"
# No wall of the map opens a line to a remembered sealed cell, from beside it or from its own
# cell: the sweep's hold had no end (owner 2026-11-19 「来ないなら待ち続けない」), a named stop.
NO_LINE_REASON = "quest:blocked:quest25-sealed-pocket-no-line"
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))


def _grid(ctx, cell):
    return ctx.snapshot.grid_at(Position(*cell))


def _granite(ctx, cell) -> bool:
    """A map wall the board shows known, not permanent and not yet melted."""
    grid = _grid(ctx, cell)
    return (ctx.terrain.get(cell) == "wall" and grid is not None and grid.known
            and not grid.permanent and not grid.passable)


def melted(ctx, cell) -> bool:
    """The board shows the wall turned to floor."""
    grid = _grid(ctx, cell)
    return grid is not None and grid.known and grid.passable


def _opened(ctx, wall) -> dict:
    return {**ctx.open_terrain(), tuple(wall): "floor"}


def _fires_from(ctx, wall, stand, target):
    """The cell the shot leaves from with ``wall`` melted: ``stand`` when a line reaches
    ``target`` from it, else the melted wall's own cell when one does from there; None."""
    terrain = _opened(ctx, wall)
    if quest_exposure.projectable(terrain, stand, target):
        return stand
    if tuple(wall) != tuple(target) and quest_exposure.projectable(terrain, tuple(wall), target):
        return tuple(wall)
    return None


def plan(ctx, target):
    """(wall, stand) of the nearest stand a walk reaches beside a granite wall of the map from which,
    the wall melted, a line of fire reaches ``target`` -- from the stand, else from the melted wall's
    own cell (``fire_cell``); a stand that shoots itself first.  None without one."""
    target = tuple(target)
    best = None
    for wall, kind in ctx.terrain.items():
        if kind != "wall" or not (_granite(ctx, wall) or melted(ctx, wall)):
            continue
        for dy, dx in _NEIGHBOURS:
            stand = (wall[0] + dy, wall[1] + dx)
            if ctx.terrain.get(stand) not in geo.STANDABLE or stand == target:
                continue
            fire = _fires_from(ctx, wall, stand, target)
            if fire is None:
                continue
            steps = 0 if stand == ctx.here else len(battle_mod._path(ctx, {stand}))
            if stand != ctx.here and steps < 2:
                continue
            rank = (fire != stand, steps)
            if best is None or rank < best[0]:
                best = (rank, wall, stand)
    return None if best is None else (best[1], best[2])


def fire_cell(ctx, target, wall, stand):
    """Where the planned shot at ``target`` leaves from (``_fires_from``)."""
    return _fires_from(ctx, wall, stand, tuple(target)) or tuple(stand)


def note_shot(ctx) -> None:
    """The board after a shot at the pocket: answered (a hit, pain or kill line) or one more miss."""
    battle = ctx.battle
    if battle.pocket is None or not battle.pocket_shot:
        return
    battle.pocket_shot = False
    names = battle_mod._names(ctx.policy, geo.QUYL)
    texts = [message_text(message) for message in ctx.snapshot.messages]
    answered = any(battle_mod._killed_name(text) is not None or text.endswith(battle_mod._HIT_LINES)
                   or any(line in text for line in battle_mod._HIT_LINES_EN)
                   or battle_mod._pain_of(text, names) for text in texts)
    battle.pocket_misses = 0 if answered else battle.pocket_misses + 1
    if any(battle_mod._killed_name(text) is not None for text in texts):
        # Killed (the kill count reads the line): the cell is done, the sweep looks again.
        target = tuple(battle.pocket[0])
        left = tuple(cell for cell in battle.detected or () if tuple(cell) != target)
        battle.detected, battle.detect_turn, battle.pocket = (left or None), -1, None


def _kept(ctx, target):
    """The (wall, stand) the plan chose for ``target`` while it is still the one being opened.

    Once the player stands on the melted cell, a plan made again from there finds the cells inside
    the pocket a walk away and would move the stand in beside the target (n1-b life-416: [8,4]
    beside [8,3]); the chosen stand and the cell it shoots from stay the plan's."""
    pocket = ctx.battle.pocket
    if pocket is None or tuple(pocket[0]) != tuple(target):
        return None
    wall = tuple(pocket[1])
    if not (_granite(ctx, wall) or melted(ctx, wall)):
        return None
    return wall, tuple(pocket[2])


def key(ctx, cells) -> str | None:
    """The sweep's step for remembered ``cells`` no walk reaches (the module docstring); None when
    none of them can be opened (the sweep holds)."""
    battle = ctx.battle
    for target in cells:
        found = _kept(ctx, target) or plan(ctx, target)
        if found is None:
            continue
        wall, stand = found
        if battle.pocket is None or tuple(battle.pocket[0]) != tuple(target):
            battle.pocket, battle.pocket_misses, battle.pocket_shot = (tuple(target), wall, stand), 0, False
        if battle.pocket_misses >= ctx.values.pen_misses_to_escaped:
            # 「ショートテレポートさせるまで撃つ」: it moved; the cell is forgotten, the sweep detects again.
            left = tuple(cell for cell in battle.detected or () if tuple(cell) != tuple(target))
            battle.detected, battle.detect_turn, battle.pocket = (left or None), -1, None
            return None
        if not melted(ctx, wall) and not battle_mod._can_melt(ctx):
            # 「無ければ帰還」: the floor is given up (the deliberate leave once_quest_recall ``held``
            # does not reverse, policy ``_latch_unviable_quest_return``), then Recall is read.
            ctx.policy._unviable_quest_floor = ctx.snapshot.floor_key
            recall = once_quest_recall.read_key(ctx.policy, ctx.snapshot, RECALL_REASON)
            return recall if recall is not None else battle_mod._hold(ctx)
        fire = fire_cell(ctx, target, wall, stand)
        if ctx.here not in {stand, fire}:
            return battle_mod._walk(ctx, {stand}, WALK_REASON) or battle_mod._hold(ctx)
        if not melted(ctx, wall):
            if ctx.here != stand:
                return battle_mod._walk(ctx, {stand}, WALK_REASON) or battle_mod._hold(ctx)
            return battle_mod._melt_key(ctx, wall) or battle_mod._hold(ctx)
        if ctx.here != fire:
            # The map still draws the wall, so the walk does not cross it: the one step onto the
            # melted cell beside the stand (the board shows it floor).
            return battle_mod._step(ctx, fire, STEP_IN_REASON)
        seen = bool(battle_mod._seen_at(ctx, geo.QUYL, {tuple(target)}))
        shot = battle_mod._unseen_fire(ctx, tuple(target), geo.QUYL, seen=seen)
        if shot is not None and battle.pocket is not None:
            battle.pocket_shot = True
        return shot or battle_mod._hold(ctx)
    return None


def no_line_key(ctx) -> str:
    """Every remembered cell is sealed and no melt opens a line to it (``key`` found no plan)."""
    ctx.policy.last_reason = NO_LINE_REASON
    return WAIT_KEY
