"""Which walls the player can tunnel through at all, and the dug cell the dark hides.

Two facts of the game's tunnel command (src/action/tunnel-execution.cpp
``exe_tunnel``, src/cmd-action/cmd-tunnel.cpp ``do_cmd_tunnel``):

* A wall without CAN_DIG (granite, magma and quartz veins, glass, trees) is
  dug through only when ``skill_dig > power + randint0(40 * power)``; with
  ``skill_dig <= power`` it never is.  n1-b life-315 (2026-11-05, Lv7
  Magic-Eater, one shovel, digging 18 shown in town) tunnelled one granite wall
  (power 40) with ``T9`` 577 times over 550,000 game turns until its lantern
  ran dry.  The mining tunnel key (policy_fundraising ``_mining_tunnel_key``,
  which the treasure dig and the walk-out dig both post through) refuses such a
  wall, so the target is released instead of dug forever.  The check reads the
  board's ``digging_skill`` only while a digging tool is worn: the skill before
  the digger is wielded does not tell what the digger adds.
* A finished tunnel turns the wall into floor (``cave_alter_feat``), and
  floor does not REMEMBER: grid.cpp ``set_terrain_id_to_grid`` clears its
  CAVE_MARK, and ``note_spot`` marks it again only when the player sees it.
  With no light (n1-b life-321 wore ★火消しライター, radius 0) the dug
  cell leaves the board, while the policy's grid memory still held the wall:
  ``T`` was asked again on floor, refused with 「そこは掘れない。」 and no turn
  passing, twelve times until the loop detector stopped it (02:05 and 02:06).
  When the board reports the tunnel finished or refused, the remembered walls
  next to the player that the board no longer shows are forgotten.

Owner 2026-11-06, the option 「見込み100回を超えたら掘らない」: 「成功の見込みから、掘り
抜くのに平均100回を超える壁は選びません。ゲームの式から数え、実際に掘り続けた回数でも
打ち切ります。」  One try succeeds with the chance exe_tunnel gives it: on CAN_DIG
rubble ``skill_dig > randint0(20 * power)``, min(skill, 20p) in 20p; on every other
wall ``skill_dig > power + randint0(40 * power)``, (skill - p) in 40p (none at
skill <= p).  ``expected_attempts`` is one over that chance.  ``not_dug`` is the
one dig predicate the dig selectors ask (the mining treasure route and tunnel,
the dig route of the walk-out dig and the dig-to-stairs breakout, the Q2 breach
dig): a wall over NOT_DUG_OVER_ATTEMPTS expected tries is not chosen, nor one
already tried that many times.  The tries are counted per cell from the game
turns the posted ``T`` took (the command repeats itself, always_repeat: one
post is up to 99 tries; a try is one player action, 100 energy, gained by
``speed_energy`` each game turn), and start again when the cell's terrain changes.

The skill is the board's while a digger is worn.  Otherwise it is the skill the
swap will give (``dig_skill``): the mining loadout strips the combat hands and
wields the first carried digger (policy_equipment ``_wield_digging_tool_key``),
the Q2 breach wields its strong digger in the main hand.  calc_skill_dig counts
each wielded TR_TUNNEL pval * 20 and each hand's melee weapon (diggers
included) weight / 10 unless heavy (calc_weapon_weight_limit: adj_str_hold,
doubled for one weapon held alone); the swap's change to those terms is
applied to the board's skill.  n1-b life-315 showed 18 with the Short Sword
(weight 80) and 36 with the Shovel (pval 1, weight 60): 18 - 8 + 20 + 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot.model import GridState, Position, Snapshot
from hengbot.policy_constants import DIRECTION_DELTAS, TUNNEL_KEY, speed_energy

# Owner 2026-11-06 「見込み100回を超えたら掘らない」: a wall that takes more tries
# than this on average is not chosen, and a dig stops after this many tries.
NOT_DUG_OVER_ATTEMPTS = 100

# tunnel.power of every TUNNEL terrain without CAN_DIG
# (lib/edit/TerrainDefinitions.jsonc, by terrain id).
TUNNEL_POWER_BY_TERRAIN_ID = {
    50: 10, 51: 20, 52: 10, 53: 20, 54: 20, 55: 20,  # magma / quartz veins
    56: 40, 57: 40, 58: 40, 59: 40,  # granite
    96: 10,  # tree
    218: 40,  # glass wall
    223: 10, 224: 20, 225: 40, 226: 40,  # on shallow water
    236: 10, 237: 20, 238: 40, 239: 40,  # on deep water
    240: 30, 241: 30, 242: 30, 243: 30,  # quartz with treasure / hidden
}
# tunnel.power of the CAN_DIG terrains (rubble), by terrain id.
CAN_DIG_POWER_BY_TERRAIN_ID = {49: 10, 222: 10, 235: 10}
# object-enchant/tr-types.h TR_TUNNEL.
TR_TUNNEL = 11
_HANDS = ("main_hand", "sub_hand")
MEMORY = "_tunnel_attempt_memory"

# The board's message after a tunnel ends the wall or meets no wall.
TUNNEL_ENDED_MESSAGES = frozenset({
    "穴を掘り終えた。", "You have finished the tunnel.",  # tunnel-execution.cpp:91
    "そこは掘れない。", "You can't tunnel through that.",  # cmd-tunnel.cpp:58
})


def _wields_weapon(item) -> bool:
    """BaseitemKey::is_melee_weapon: a digger is a melee weapon too."""
    return item.is_digging_tool or item.is_melee_weapon


def _weight_limit(snapshot: Snapshot, hands: list) -> int | None:
    """calc_weapon_weight_limit for ``hands`` (None: STR index not reported)."""
    from hengbot.warrior_equipment_evaluator import ADJ_STR_HOLD

    if not snapshot.player.stat_index:
        return None
    limit = ADJ_STR_HOLD[snapshot.player.stat_index[0]]
    # has_two_handed_weapons: one weapon held while the other hand is empty.
    if len(hands) == 1 and _wields_weapon(hands[0]):
        limit *= 2
    return limit


def _hand_terms(snapshot: Snapshot, hands: list) -> int:
    """calc_skill_dig's terms of the wielded hands."""
    limit = _weight_limit(snapshot, hands)
    total = 0
    for item in hands:
        if item.is_digging_tool or TR_TUNNEL in item.known_flags:
            total += item.pval * 20
        if _wields_weapon(item) and (limit is None or item.weight // 10 <= limit):
            total += item.weight // 10
    return total


def dig_skill(policy, snapshot: Snapshot, digger=None) -> int | None:
    """skill_dig the dig will have: the board's, or after the digger swap.

    ``digger`` is the digger the swap puts in the main hand (the Q2 breach's
    strong one); without it the mining loadout's swap: both combat hands
    stripped, the first carried digger wielded.
    """
    skill = snapshot.player.digging_skill
    if skill is None:
        return None
    worn = [item for item in snapshot.equipment if item.slot in _HANDS]
    if digger is None:
        if any(item.is_digging_tool for item in worn):
            return skill
        digger = policy._first_item(
            snapshot,
            lambda item: item.is_digging_tool
            and not policy._equip_blocked_by_identification(item),
        )
        if digger is None:
            return skill
        after = [digger]
    elif any(item is digger for item in worn):
        return skill
    else:
        after = [digger] + [item for item in worn if item.slot != "main_hand"]
    return max(1, skill - _hand_terms(snapshot, worn) + _hand_terms(snapshot, after))


def expected_attempts(skill: int | None, grid: GridState) -> float | None:
    """Average tries to tunnel ``grid`` at ``skill`` (inf: never; None: unknown)."""
    if skill is None:
        return None
    power = CAN_DIG_POWER_BY_TERRAIN_ID.get(grid.terrain_id)
    if power is not None:
        return 20 * power / min(skill, 20 * power)
    power = TUNNEL_POWER_BY_TERRAIN_ID.get(grid.terrain_id)
    if power is None:
        return None
    if skill <= power:
        return float("inf")
    return 40 * power / min(skill - power, 40 * power)


@dataclass
class Memory:
    """Tries per cell on one floor; the last posted ``T`` until it is counted."""

    floor: tuple
    tries: dict = field(default_factory=dict)  # (position, terrain_id) -> tries
    posted: tuple | None = None  # (position, terrain_id, game turn, speed)


def _memory(policy, snapshot: Snapshot) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = Memory(floor=snapshot.floor_key)
        setattr(policy, MEMORY, memory)
    return memory


def tries(policy, snapshot: Snapshot, grid: GridState) -> float:
    """The tries already spent on ``grid`` while it has its terrain."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return 0.0
    return memory.tries.get((grid.position, grid.terrain_id), 0.0)


def not_dug(policy, snapshot: Snapshot, grid: GridState, digger=None) -> bool:
    """The dig predicate: ``grid`` takes over NOT_DUG_OVER_ATTEMPTS tries.

    On average from the game's formula at ``dig_skill``, or as tried already.
    """
    expected = expected_attempts(dig_skill(policy, snapshot, digger), grid)
    return (
        (expected is not None and expected > NOT_DUG_OVER_ATTEMPTS)
        or tries(policy, snapshot, grid) >= NOT_DUG_OVER_ATTEMPTS
    )


def observe(policy, snapshot: Snapshot) -> None:
    """Every decision: count the tries the last posted ``T`` took."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.posted is None:
        return
    if memory.floor != snapshot.floor_key:
        setattr(policy, MEMORY, None)
        return
    position, terrain_id, turn, speed = memory.posted
    if snapshot.turn == turn:
        return
    memory.posted = None
    cell = (position, terrain_id)
    memory.tries[cell] = (
        memory.tries.get(cell, 0.0)
        + max(0, snapshot.turn - turn) * speed_energy(speed) / 100
    )


def remember_post(policy, snapshot: Snapshot, key) -> None:
    """The final key of a decision: a ``T`` at an adjacent wall is counted next."""
    if not isinstance(key, str) or len(key) < 2 or key[0] != TUNNEL_KEY:
        return
    delta = DIRECTION_DELTAS.get(key[1])
    if delta is None:
        return
    here = snapshot.player.position
    grid = snapshot.grids.get(Position(here.y + delta[0], here.x + delta[1]))
    if grid is None:
        return
    _memory(policy, snapshot).posted = (
        grid.position, grid.terrain_id, snapshot.turn, snapshot.player.speed,
    )


def _tunnel_ended(messages) -> bool:
    return any(
        message.split(" <x", 1)[0] in TUNNEL_ENDED_MESSAGES for message in messages
    )


def forget_dug_walls(policy, snapshot: Snapshot) -> None:
    """Drop remembered walls next to the player that a finished tunnel removed.

    Called by the grid memory's owner (``_with_grid_memory``) before the merge.
    """
    if not snapshot.grids or not _tunnel_ended(snapshot.messages):
        return
    remembered = policy._remembered_grids
    here = snapshot.player.position
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            position = Position(here.y + dy, here.x + dx)
            grid = remembered.get(position)
            if (
                grid is not None
                and grid.tunnel
                and not grid.passable
                and position not in snapshot.grids
            ):
                del remembered[position]
                policy._remembered_grid_signatures.pop(position, None)
                policy._remembered_grid_sources.pop(position, None)
