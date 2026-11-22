"""No arrival at 50F+ without the *Destruction* means by a trap door or a Teleport Level.

Owner 2026-11-22 (verbatim): 「上りの間は即死以外でもテレポートを許すが、そもそも50Fに降りない方を
しっかり作ること」.  n1-a life-531 on the Castle's 50F climb (deep_climb) fell through two trap
doors (50F -> 52F -> 54F, 2026-11-22 08:04) and lost the climb's landing; on 2026-11-19 19:59 it
had entered the Mountain's 50F, no stair the policy took (the depth gate refuses every one).

What the game does (C:/hengband/src):

- A trap door (grid/trap.cpp hit_trap, TrapType::TRAPDOOR) drops the player exactly one floor
  (FloorChangeMode::DOWN), unless levitating (「落とし戸を飛び越えた。」); on a quest floor it hurts
  and changes nothing.  None is placed on a dungeon's last floor, the arena or a quest
  (FloorType::select_random_trap).  A random trap is placed hidden (place_trap_at: ``mimic``):
  it is shown by a trap detection (detect_feat_flag, which also clears CAVE_UNSAFE in its range:
  the board's ``unsafe_rows``), by the passive search of a step (a chance, skill_srh) or by
  stepping on it.  A disarm that fails badly sets it off.
- Teleport Level (spell-kind/spells-world.cpp teleport_level) goes up or down at random, always
  down on the dungeon's first floor and always up on its last one or a quest floor.  A monster's
  TELE_LEVEL and a nexus hit cast it on the player unless the player resists nexus (or saves).
- There is no Deep Descent scroll in this game (object-use/read/scroll-read-executor.cpp).

A floor change is *sanctioned* (``sanctioned``) when it lands above 50F, or on the Castle's 50F
landing of the held climb (deep_climb, owner 2026-11-22 「城の50Fに帰還してすぐ38〜42Fへ登る」).
On a floor where a fall would land unsanctioned (``at_risk``: no *Destruction* means, not
levitating, a trap door possible here):

- the known trap cells are kept off by every walk (``refresh_avoid``, the shared avoid set) and
  no step enters one, a disarm included (``step_refused``);
- before a walk leaves the detected area (a walkable neighbour still CAVE_UNSAFE), the traps are
  detected (``key``: the absorbed Detect Traps, a carried Staff or Scroll of Detect Traps, a Rod of
  Trap Location or of Detection);
- without a detection means, a 49F floor is left (``key``: the up stairs underfoot, else Word of
  Recall, waited for in place) -- the fall would newly reach 50F; on the climb's 50F+ floors the
  climb goes on (the owner's exception put it there) and a fall stops the bot
  (deep_climb.stop_key);
- no stair down is taken onto such a floor without a detection means (``descent_refused``,
  asked by ``_is_descent_target``): the connected stairs put a descent on an up staircase
  (floor-changer.cpp set_stairs), so the leave and the descent would alternate.  The last
  escape down the stairs underfoot (``_down_stairs_underfoot_key``) is kept: the leave follows
  on the floor below;
- the leave by the up stairs is an escape by stairs (fled_floor_stairs ``note_flight``, owner
  2026-10-31 「逃げた階に戻らないための決定」, the one record of a floor left that the descent owners
  read): the stair it lands on leads back to the saved floor left, and is not taken again.
  ``descent_refused`` reads the means held, ``key`` the means usable on the board: the absorbed
  Detect Traps is not cast while a hostile is in view (me_powers ``_hostiles_allow``).  n1-c
  life-220 (Magic-Eater Lv32, Angband, 2026-11-22 10:24): the 49F arrival stair stood in view of
  five sleeping ogres, the leave went up onto 48F's down stair and ``descend`` loaded the same
  49F, 20 times until the loop detector stopped the bot.  Another down stair of the floor above
  is a new floor.

Teleport Level is not read where its downward half lands unsanctioned (``teleport_level_refused``,
asked by every reader: the immobile summoner's exits, the item-destroying breeder's leave and the
threat escape's means).
"""
from __future__ import annotations

from hengbot import fled_floor_stairs
from hengbot.model import (
    SV_ROD_DETECTION, SV_SCROLL_DETECT_TRAP, SV_STAFF_DETECT_TRAP, TVAL_ROD, TVAL_SCROLL,
    TVAL_STAFF,
)
from hengbot.policy_constants import (
    DEEP_FLOOR_DEPTH, DESCEND_MIN_HP_RATIO, UP_STAIRS_KEY, WAIT_KEY,
)

SV_ROD_DETECT_TRAP = 0   # sv-definition/sv-rod-types.h (トラップ感知のロッド)
REASON = "deep-fall-guard"
DETECT_REASON = f"{REASON}:detect-traps"
ASCEND_REASON = f"{REASON}:ascend"
RECALL_REASON = f"{REASON}:recall"
WAIT_RECALL_REASON = f"{REASON}:wait-recall"
STEP_REFUSED_REASON = f"{REASON}:trap-step-refused"
MEMORY = "_deep_fall_guard"
FAILURES_PER_PLACE = 3
FAILED = frozenset({
    "杖をうまく使えなかった。", "You failed to use the staff properly.",
    "うまくロッドを使えなかった。", "You failed to use the rod properly.",
    "呪文をうまく唱えられなかった！", "You failed to get the magic off!",
})


def sanctioned(policy, dungeon_id: int, depth: int) -> bool:
    """A floor change landing on ``depth`` of ``dungeon_id`` needs no *Destruction* means: above
    50F, or the held climb's 50F landing (deep_climb)."""
    from hengbot import deep_climb, dive_floor

    return depth < DEEP_FLOOR_DEPTH or (
        depth == deep_climb.LANDING and dive_floor.climb_dungeon(policy) == dungeon_id)


def _exposed(policy, snapshot) -> bool:
    """A dungeon floor of no quest, without the *Destruction* means (the board's own)."""
    from hengbot import destruction_use

    floor_key = getattr(snapshot, "floor_key", None)
    if (getattr(snapshot, "in_town", False) or not floor_key or floor_key[1] <= 0
            or floor_key[2] != 0 or getattr(snapshot, "inside_arena", False)
            or policy._on_random_quest_floor(snapshot)):
        return False
    return not destruction_use.holds_means(policy, snapshot)


def _last_floor(policy, snapshot) -> bool:
    info = policy._dungeon_knowledge.get(snapshot.floor_key[0])
    return info is not None and snapshot.dungeon_level >= info.max_depth


def at_risk(policy, snapshot) -> bool:
    """A trap door here would land unsanctioned."""
    from hengbot import ability_sources

    return (_exposed(policy, snapshot) and not _last_floor(policy, snapshot)
            and not ability_sources.has_ability(snapshot.player, "levitation")
            and not sanctioned(policy, snapshot.floor_key[0], snapshot.dungeon_level + 1))


def holds_detection(policy, snapshot) -> bool:
    """A trap detection ``key`` could use: a carried Rod of Trap Location / Detection, a charged
    Staff or a Scroll of Detect Traps, or the Magic-Eater's absorbed Detect Traps (no state)."""
    from hengbot import me_capability
    from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER

    for item in snapshot.inventory:
        if not item.known or not item.aware or item.count <= 0:
            continue
        if item.tval == TVAL_ROD and item.sval in (SV_ROD_DETECT_TRAP, SV_ROD_DETECTION):
            return True
        if item.tval == TVAL_STAFF and item.sval == SV_STAFF_DETECT_TRAP and item.charges > 0:
            return True
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_DETECT_TRAP:
            return True
    if getattr(snapshot.player, "class_id", None) != PLAYER_CLASS_MAGIC_EATER:
        return False
    return (me_capability.charges(policy, snapshot, "staff", SV_STAFF_DETECT_TRAP) > 0
            or any(me_capability.charges(policy, snapshot, "rod", sval) > 0
                   for sval in (SV_ROD_DETECT_TRAP, SV_ROD_DETECTION)))


def descent_refused(policy, snapshot, destination: int) -> bool:
    """A stair down onto ``destination`` would put the character where a trap door lands
    unsanctioned, without a trap detection: the descent is not taken.  Without it the 49F
    floor's leave (``key``: the up stairs underfoot, where the connected stairs put a descent)
    and the descent into it would alternate.  A random quest's floor has no trap door, nor the
    dungeon's last floor (FloorType::select_random_trap)."""
    from hengbot import ability_sources, destruction_use, random_quest_hold

    if (snapshot.in_town or snapshot.dungeon_level <= 0 or not snapshot.floor_key
            or snapshot.floor_key[2] != 0):
        return False
    dungeon = snapshot.floor_key[0]
    if sanctioned(policy, dungeon, destination + 1):
        return False
    info = policy._dungeon_knowledge.get(dungeon)
    if info is not None and destination >= info.max_depth:
        return False
    if destination in random_quest_hold._pending_random_levels(policy, snapshot, dungeon):
        return False
    if destruction_use.holds_means(policy, snapshot):
        return False
    if ability_sources.has_ability(snapshot.player, "levitation"):
        return False
    return not holds_detection(policy, snapshot)


def teleport_level_refused(policy, snapshot) -> bool:
    """A Teleport Level read here could go down onto an unsanctioned floor."""
    return (_exposed(policy, snapshot) and not _last_floor(policy, snapshot)
            and not sanctioned(policy, snapshot.floor_key[0], snapshot.dungeon_level + 1))


def _trap_cells(snapshot) -> set:
    return {position for position, grid in snapshot.grids.items() if grid.trap}


def refresh_avoid(policy, snapshot) -> None:
    """Every decision: on an at-risk floor every known trap cell joins the shared avoid set."""
    if not at_risk(policy, snapshot):
        return
    cells = _trap_cells(snapshot) - {snapshot.player.position}
    if cells - policy._engagement_avoid_cells:
        policy._engagement_avoid_cells |= cells


def step_refused(policy, snapshot, grid) -> bool:
    """No step onto a known trap, a disarm included, on an at-risk floor."""
    if grid is None or not grid.trap or not at_risk(policy, snapshot):
        return False
    policy.last_reason = STEP_REFUSED_REASON
    return True


def _unsafe(snapshot, position) -> bool:
    rows = snapshot.unsafe_rows
    if rows is None or snapshot.unsafe_rows_malformed:
        return True
    if not (0 <= position.y < len(rows)) or not (0 <= position.x < len(rows[position.y])):
        return True
    return bool(rows[position.y][position.x])


def _undetected_neighbour(policy, snapshot) -> bool:
    return any(_unsafe(snapshot, cell)
               for cell in policy._walkable_neighbors(snapshot, snapshot.player.position))


def _memory(policy, snapshot) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        memory = {"floor": snapshot.floor_key, "pending": None, "failed": {}, "done": set()}
        setattr(policy, MEMORY, memory)
    return memory


def observe(policy, snapshot) -> None:
    """Every decision: settle the last detection (a failed use counts at its place)."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key or memory["pending"] is None:
        return
    turn, position = memory["pending"]
    if snapshot.turn == turn:
        return
    memory["pending"] = None
    if any(message in FAILED for message in snapshot.messages):
        memory["failed"][position] = memory["failed"].get(position, 0) + 1
    else:
        memory["done"].add(position)


def _detection_key(policy, snapshot) -> str | None:
    from hengbot import me_powers
    from hengbot.item_reservation import reserved_item_command

    key = me_powers.power_key(policy, snapshot, me_powers.TRAP_CELL)
    if key is not None:
        return key
    player = snapshot.player
    if player.blind or player.confused or player.hallucinated:
        return None
    for tval, svals, verb in ((TVAL_ROD, (SV_ROD_DETECT_TRAP, SV_ROD_DETECTION), "rod"),
                              (TVAL_STAFF, (SV_STAFF_DETECT_TRAP,), "staff"),
                              (TVAL_SCROLL, (SV_SCROLL_DETECT_TRAP,), "read")):
        for item in snapshot.inventory:
            if item.tval != tval or item.sval not in svals or not item.known or not item.aware:
                continue
            if tval == TVAL_STAFF and item.charges <= 0:
                continue
            if tval == TVAL_ROD and item.charging:
                continue
            if tval == TVAL_SCROLL and not policy._can_read_scrolls(snapshot):
                continue
            key = reserved_item_command(policy, snapshot, verb, item)
            if key is not None:
                return key
    return None


def key(policy, snapshot):
    """On an at-risk floor, before a walk leaves the detected area: detect the traps, else (on a
    floor whose fall would newly reach 50F) leave it."""
    from hengbot import deep_climb, deep_teleport

    if not at_risk(policy, snapshot) or not _undetected_neighbour(policy, snapshot):
        return None
    from hengbot import me_powers
    from hengbot.model import game_distance

    memory = _memory(policy, snapshot)
    here = snapshot.player.position
    if here in memory["done"] or (
            (snapshot.unsafe_rows is None or snapshot.unsafe_rows_malformed)
            and any(game_distance(here, place) <= me_powers.DETECT_RAD - 2
                    for place in memory["done"])):
        # Detected from here (or, without the board's flags, from near enough).
        return None
    if memory["failed"].get(here, 0) < FAILURES_PER_PLACE:
        detect = _detection_key(policy, snapshot)
        if detect is not None:
            memory["pending"] = (snapshot.turn, here)
            policy.last_reason = DETECT_REASON
            return detect
    if deep_climb.on_floor(policy, snapshot):
        # The owner's exception put the climb on 50F+: it goes on (deep_climb.key); a fall stops
        # the bot (deep_climb.stop_key).
        return None
    grid = snapshot.grid_at(here)
    if grid is not None and policy._is_upstairs_target(grid) \
            and snapshot.player.hp_ratio >= DESCEND_MIN_HP_RATIO:
        # The connected stairs land this leave on the down stair of the saved floor above whose
        # ``special`` is this very floor (fled_floor_stairs): that stair is not a descent target
        # again, so a detection held but not usable here (``_detection_key``: a visible hostile,
        # the failures, blindness) does not alternate with the descent (n1-c life-220).
        fled_floor_stairs.note_flight(policy, snapshot)
        policy.last_reason = ASCEND_REASON
        return UP_STAIRS_KEY
    if snapshot.player.recalling:
        # The Recall counts down (15-35 turns): no walk across the undetected floor meanwhile.
        policy.last_reason = WAIT_RECALL_REASON
        return WAIT_KEY
    return deep_teleport._recall_key(policy, snapshot, RECALL_REASON)
