"""The map facts of quest 25 『幽霊屋敷』 that its battle plan stands on, computed from the map.

Owner 2026-11-06 (strategy/quests/QUEST_25.jsonc ``engagement_plan.revised_plan_draft``):
the plan is built on the cells that receive no summons.  Everything here is derived at
load time from the quest's own D-map (``QuestBattlefield``) through the projection port,
so the cells the draft lists are a test of this module, not a second copy of them
(tests/test_q25_phase_battle.py Q25GeometryTest).

Game facts (C:/hengband/src), as the draft records them:

 * A summon reaches the player when the caster can ``projectable`` the player's cell or a
   PROJECTION cell beside it (mspell-lite.cpp adjacent_grid_check), within range 18 by
   Grid::calc_distance.  A closed door stops the line, deep water does not.
 * A ball aimed at a grid drops PROJECT_STOP (spells-launcher.cpp fire_ball), flies to
   that grid over any monster and explodes there; the blast reaches every cell within its
   radius that the centre has a line to (effect-monster.cpp: (dam + r) / (r + 1)).
 * A monster acts while the player is within its vision (monster-processor.cpp
   decide_process_continue), distance as Grid::calc_distance.
 * A legend trap with no random object is always placed; with one it is placed one time
   in four (fixed-map-generator.cpp; ``QuestBattlefield.trap_cells`` and
   ``maybe_trap_cells``).
"""

from __future__ import annotations

from functools import lru_cache

from hengbot import quest_exposure
from hengbot.quest_exposure import MAX_SPELL_RANGE, PROJECTING_KINDS, game_distance, projectable

QUEST_ID = 25

# MonraceDefinitions ids of the roster (lib/edit/quests/025_HauntedHouse.jsonc legend).
IPSISSIMUS = 571
TOME = 557            # ラアルの破壊集大成
QUYL = 480            # ネクサス・クイルスルグ
HOUND = 739           # ティンダロスの猟犬
SKELETAL_T = 466      # 骸骨ティラノサウルス
SPECTRAL_T = 705      # 幽体ティラノサウルス
SPECTRE = 508
SHADOW = 665          # シャドウ・デーモン
VAMPIRE = 623         # バンパイア・ロード
DREADMASTER = 690
DRUJ = 748            # 手のドルジ
STAIRWAY = 439        # 地獄への階段
MASS = 202            # 死体の塊 (MULTIPLY)

# The cells the draft names (owner decisions quote them; the derivations are below).
START = (13, 1)
WEST_DOOR = (9, 1)            # 扉 [9,1]
MEET_RANGED = (13, 1)         # phase1: 「[13,1] から」
MEET_MELEE = (10, 1)          # phase1: beside the closed door [9,1], its south side
PHASE2_WALK = ((7, 1), (6, 1), (5, 1))   # 「(7,1)に移動、…(6,1)(5,1)と移動」
WALL_PASSER_STAND = (7, 1)    # phase1_wall_passers: 「(7,1)に移動」
IPSISSIMUS_AIM = (7, 17)      # 「[7,17]に撃ち続ければ全て倒せる」
IPSISSIMUS_PEN = ((7, 17), (8, 17), (9, 17))
STRAGGLER_STAND = (5, 1)      # 「[5,1]で倒す」
QUYL_STANDS = ((5, 2), (5, 1))            # phase3: 「[5,2] か [5,1]」
TOME_NEAR_STANDS = ((5, 5), (4, 5), (5, 6))  # phase3: 「[5,5] か [4,5][5,6]」
MASS_STAND = (1, 6)           # phase4: 「[1,6] から撃つ」
MASS_DOOR = (1, 7)
NORTH_CORRIDOR = tuple((y, x) for y in (1, 2) for x in range(8, 18))
DREADMASTER_MELEE_STAND = (1, 17)   # 「(17,1) は … [1,17] のこと」
DREADMASTER_VISION = 20
STAIRWAY_DOOR = (13, 28)
STAIRWAY_STAND = (13, 27)     # 「[13,27] から階段までは距離2」
DRUJ_DOOR = (11, 19)
DRUJ_AREA_STAND = (13, 20)    # phase7: 「13,20に移動して、11,19を岩石溶解して11,19に範囲攻撃」

# The draft's initial roster count (phase6_sweep 「初めの配置」); MASS breeds and is judged
# by sight from MASS_STAND instead.
ROSTER = {IPSISSIMUS: 3, TOME: 1, QUYL: 2, HOUND: 1, SKELETAL_T: 1, SPECTRAL_T: 1,
          SPECTRE: 2, SHADOW: 9, VAMPIRE: 1, DREADMASTER: 1, DRUJ: 1, STAIRWAY: 1, MASS: 2}

STANDABLE = frozenset({"floor", "door", "passage", "shallow_water", "deep_water", "exit", "tree"})
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))


def _key(terrain: dict) -> tuple:
    return tuple(sorted(terrain.items()))


def opened(terrain: dict, doors=()) -> dict:
    """``terrain`` with ``doors`` open (a line passes them)."""
    return {**terrain, **{tuple(cell): "floor" for cell in doors}}


def casts_on(terrain: dict, caster, cell) -> bool:
    """A never-moving caster's area spell (a summon) reaches a player on ``cell``."""
    if game_distance(caster, cell) > MAX_SPELL_RANGE:
        return False
    if projectable(terrain, caster, cell):
        return True
    return any(terrain.get(beside) in PROJECTING_KINDS and projectable(terrain, caster, beside)
               for beside in ((cell[0] + dy, cell[1] + dx) for dy, dx in _NEIGHBOURS))


@lru_cache(maxsize=16)
def _summon_counts(terrain_key: tuple, casters: tuple) -> dict:
    terrain = dict(terrain_key)
    counts = {}
    for cell, kind in terrain.items():
        if kind in STANDABLE:
            count = sum(casts_on(terrain, caster, cell) for caster in casters)
            if count:
                counts[cell] = count
    return counts


def summon_counts(terrain: dict, casters=IPSISSIMUS_PEN) -> dict:
    """Per standable cell, how many of ``casters`` summon onto a player there."""
    return _summon_counts(_key(terrain), tuple(sorted(casters)))


def summon_cells(terrain: dict, casters=IPSISSIMUS_PEN) -> frozenset:
    return frozenset(summon_counts(terrain, casters))


@lru_cache(maxsize=64)
def _line_cells(terrain_key: tuple, source: tuple) -> frozenset:
    terrain = dict(terrain_key)
    return frozenset(cell for cell, kind in terrain.items()
                     if kind in STANDABLE and cell != source
                     and game_distance(source, cell) <= MAX_SPELL_RANGE
                     and projectable(terrain, source, cell))


def line_cells(terrain: dict, source) -> frozenset:
    """The standable cells ``source`` has a direct line to (a bolt, Teleport Away)."""
    return _line_cells(_key(terrain), tuple(source))


def ball_centre(terrain: dict, stand, target, radius: int):
    """(distance, centre) of the grid a ball aimed from ``stand`` explodes on to catch
    ``target`` within ``radius``, nearest first, then by cell; None when there is none."""
    found = sorted(
        (game_distance(cell, target), cell) for cell, kind in terrain.items()
        if kind in PROJECTING_KINDS and game_distance(stand, cell) <= MAX_SPELL_RANGE
        and projectable(terrain, stand, cell) and game_distance(cell, target) <= radius
        and projectable(terrain, cell, target))
    return found[0] if found else None


def vision_cells(terrain: dict, source, vision: int, *, edge: bool = False) -> frozenset:
    """The standable cells within (``edge``: exactly at) ``vision`` of ``source``."""
    return frozenset(cell for cell, kind in terrain.items() if kind in STANDABLE and (
        game_distance(cell, source) == vision if edge else game_distance(cell, source) <= vision))


def exposure_of(cells) -> quest_exposure.Exposure:
    """An Exposure whose ``shout`` is ``cells``: the least-exposed walk crosses the fewest."""
    return quest_exposure.Exposure({}, {tuple(cell): frozenset({(0, 0)}) for cell in cells})
