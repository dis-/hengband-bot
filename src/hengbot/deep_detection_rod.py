"""The Rod of Detection (全感知のロッド) carried and zapped by every character on 50F+.

Owner 2026-11-26 (verbatim): 「50F以降は全感知のロッドを持つ」.  n1-a life-537 (Warrior Lv48, HP
1145, Angband 50F, 2026-11-26 02:04) stepped from (38,14) onto the unvisited (39,15) ('3',
explore) and was surrounded by a dragon pack (ヘル・ワイアーム, 古代万色ドラゴン, 『メガ・フレイム・
ドラゴン』...) never sensed before; it died from full HP before its next turn.  Not one trap
detection was made on that floor (the board's ``unsafe_rows``: (39,15) still CAVE_UNSAFE), and the
most likely cause is a hidden trap: the curse trap (grid/trap.cpp TrapType::TY_CURSE summons with
PM_ALLOW_GROUP | PM_ALLOW_UNIQUE) or a teleport trap.  It overrides, for 50F+, the 2026-10-23 rule
「トラップ感知は努力目標。巻物は非効率なのでロッドを拾えた場合は使用。」 (trap-detect-rod-only).

Game (C:/hengband/src): the Rod of Detection is BaseitemDefinitions.jsonc id 375 (tval 66 ROD,
sval 6 SV_ROD_DETECTION, level 30, cost 5000, pval 99: the recharge, the timeout a zap adds).
cmd-zaprod.cpp:107 zaps detect_all(detect_rad): DETECT_RAD_DEFAULT 30 (spell/spells-util.h), 3/2
through Powerful Activation (cmd-zaprod.cpp:50).  detect_all runs detect_traps(range, known=true):
detect_feat_flag (spells-detection.cpp) clears CAVE_UNSAFE on every grid within the range (a
third in a DARKNESS dungeon) and discloses the hidden traps there; it also detects doors, stairs,
gold, objects and every monster.  No ordinary shop stocks it (store/articles-on-sale.cpp: the
Magic shop sells no rod but the Pesticide's General store row); the Black Market may.

The rule (``applies``: the deepest recall depth of the character's dungeons, or the floor it
stands on, is 50F or deeper):

* own one: the carried rod is never shelved, sold or destroyed (``retained_count``, the retention
  authority's ``RETENTION_BRANCH``); with none carried, a Home rod is taken out (``home_missing``,
  the Home catalogue binder, as teleport_away_carry); with none carried or at Home, a shelved rod
  is bought first (bm_destruction_fund's "detection-rod" row of PRIORITY_WARES, rung
  "priority-ware:detection-rod"), only from the gold above the departure resupply: no Home spare
  is sold for it (the owner did not ask 「売ってでも」).  A Magic-Eater's absorbed Rod of Detection
  (me_capability.count) is the rod owned.
* use it on 50F+ (``key``, the objectives layer's rung after deep_fall_guard): whenever a walkable
  neighbour of the player is not trap-detected yet (the board's ``unsafe_rows``; without them the
  trap detections of door_detect_cover), so on arriving at a floor and before every step out of
  the area the last detection covered.  A charged carried rod is zapped; a Magic-Eater's absorbed
  one is cast by me_powers (the rod row's "deep-undetected-step" trigger, the floor occasion of the
  safe-now layer; its new-floor cast is the Detect Evil row's preferred rod, as before).  An
  absorbed Detect Traps staff serves the same trigger when the rod has no use (its row in me_powers
  after the rod's): its detect_traps clears CAVE_UNSAFE as the rod's does.
* wait only for the real recharge (n1-c life-224, 2026-11-28 16:45, Angband 95F: the absorbed rod
  read from a list shown at or before the last cast, turn 7557556, stayed "4 of 4 charging" for
  the bot while the game had it ready, and it rested 1360 game turns until the stationary bound
  stopped it, its 44 absorbed Detect Traps charges unused).  With no trap detection to use now
  the player rests in place (``WAIT_REASON``) from the first rest on the cell at most the rod's
  real recharge (``wait_deadline``, rod_recharge: a carried rod's ``pval`` ticks, an absorbed
  rod's full recharge at the unrested rate from its count, the INT and the food state), never more
  than ``MAX_WAIT_TICKS``.  An absorbed rod's list is shown again (me_device_attacks
  ``mark_stale``: me_powers_refresh browses it turn-free) once the rested rate from the list last
  shown says it is ready, so a use back is read from the game, not from the old list.  Past the bound, or with no bound
  (a fainting character, nothing shed), the cell is given up: the step goes on undetected (the
  last resort, ``GIVE_UP_EVENT`` on stderr).

Nothing refuses 50F+ without the rod (not decided: the owner was not asked).
"""

from __future__ import annotations

import sys

from hengbot import door_detect_cover, fundraising_route, me_capability, rod_recharge
from hengbot.deep_admission import DEEP_FLOOR_DEPTH
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import SV_ROD_DETECTION, TVAL_ROD

REASON = "deep-detection-rod"
ZAP_REASON = f"{REASON}:zap"
WAIT_REASON = f"{REASON}:wait-recharge"
RETENTION_BRANCH = "deep-detection-rod"
MEMORY = "_deep_detection_rod"
FAILURES_PER_PLACE = 3
# The owner's 「50F以降」: the rule's depth (as the other 50F+ rules read it, not the admission).
DEPTH = DEEP_FLOOR_DEPTH
# One rest per decision while the rod recharges: player turns (the rod's 99 at most).
WAIT_PLAYER_TURNS = 10
# The longest wait on one cell: a carried rod's full recharge (rod_recharge.DETECTION_ROD_PVAL
# ticks, 990 game turns), the wait the 2026-11-26 rule was made with.  An absorbed rod of n1-c
# life-224 (4 rods, INT index 16: adj_mag_mana 11) sheds 19 a tick unrested, 38 resting, of the
# 1584 a cast adds: 84 and 42 ticks.
MAX_WAIT_TICKS = rod_recharge.DETECTION_ROD_PVAL
GIVE_UP_EVENT = f"{REASON}:wait-given-up"
# me_powers' trigger of the trap detections cast before a step out of the detected area.
TRIGGER = "deep-undetected-step"
FAILED = frozenset({"うまくロッドを使えなかった。", "You failed to use the rod properly."})


def is_rod(item) -> bool:
    """An identified Rod of Detection."""
    return (getattr(item, "tval", None) == TVAL_ROD and item.sval == SV_ROD_DETECTION
            and getattr(item, "aware", False) and getattr(item, "count", 0) > 0)


def applies(snapshot) -> bool:
    """The character's recall depth, or the floor it stands on, is 50F or deeper."""
    if fundraising_route.recall_depth(snapshot) >= DEPTH:
        return True
    return not snapshot.in_town and snapshot.dungeon_level >= DEPTH


def absorbed(policy, snapshot) -> bool:
    """A Magic-Eater's absorbed Rod of Detection."""
    return (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            and me_capability.count(policy, snapshot, "rod", SV_ROD_DETECTION) > 0)


def carried(snapshot):
    """The pack's first Rod of Detection stack, or None."""
    return next((item for item in snapshot.inventory if is_rod(item)), None)


def owned(policy, snapshot) -> bool:
    """A rod carried, at Home or absorbed."""
    home = getattr(policy, "_home_knowledge_items", ()) or ()
    return (carried(snapshot) is not None or absorbed(policy, snapshot)
            or any(is_rod(item) for item in home))


def purchase_wanted(policy, snapshot) -> bool:
    """bm_destruction_fund's "detection-rod" row: 50F+ and no rod owned."""
    return applies(snapshot) and not owned(policy, snapshot)


def retained_count(snapshot, item) -> int:
    """The carried rods are kept (never shelved, sold or destroyed) while the rule applies."""
    return item.count if is_rod(item) and applies(snapshot) else 0


def home_missing(policy, snapshot, item) -> int:
    """1 when ``item`` is the Home rod to take out: the rule applies, none is carried or absorbed."""
    if not is_rod(item) or not applies(snapshot):
        return 0
    home = [stock for stock in (getattr(policy, "_home_knowledge_items", ()) or ()) if is_rod(stock)]
    if not home or item is not home[0]:
        return 0
    return int(carried(snapshot) is None and not absorbed(policy, snapshot))


def _ready(item) -> int:
    """The rods of the stack not charging."""
    charging = (item.charging_count if item.charging_count is not None
                else (item.count if item.charging else 0))
    return max(0, item.count - charging)


def _unsafe(snapshot, position) -> bool | None:
    """The board's CAVE_UNSAFE of ``position`` (not trap-detected), None without the rows."""
    rows = snapshot.unsafe_rows
    if rows is None or snapshot.unsafe_rows_malformed:
        return None
    if not (0 <= position.y < len(rows)) or not (0 <= position.x < len(rows[position.y])):
        return True
    return bool(rows[position.y][position.x])


def undetected_step(policy, snapshot) -> bool:
    """A walkable neighbour of the player is not trap-detected: the board's ``unsafe_rows``, else
    outside every trap detection door_detect_cover noted on this floor visit."""
    for cell in policy._walkable_neighbors(snapshot, snapshot.player.position):
        unsafe = _unsafe(snapshot, cell)
        if unsafe is None:
            unsafe = not door_detect_cover.trap_covered(policy, (cell.y, cell.x))
        if unsafe:
            return True
    return False


def _memory(policy, snapshot) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        memory = {"floor": snapshot.floor_key, "pending": None, "failed": {}}
        setattr(policy, MEMORY, memory)
    # The running wait (first rest's turn, cell, last decision sequence) and the given-up cells
    # (a record pickled before 2026-11-28 lacks them).
    memory.setdefault("wait", None)
    memory.setdefault("given_up", set())
    return memory


def observe(policy, snapshot) -> None:
    """Every decision: settle the last zap (a failure counts at its place)."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key or memory["pending"] is None:
        return
    turn, position = memory["pending"]
    if snapshot.turn == turn:
        return
    memory["pending"] = None
    if any(message in FAILED for message in snapshot.messages):
        memory["failed"][position] = memory["failed"].get(position, 0) + 1


def _deep_floor(snapshot) -> bool:
    return (not snapshot.in_town and snapshot.dungeon_level >= DEPTH
            and snapshot.store is None and not getattr(snapshot, "inside_arena", False))


def _trap_detection_ready(policy, snapshot) -> bool:
    """An absorbed power of me_powers' ``TRIGGER`` rows with a use: the Rod of Detection, else the
    Detect Traps staff (me_powers casts the first by its priority on the floor occasion)."""
    from hengbot import me_powers
    return any(TRIGGER in power.triggers and me_capability.charges(policy, snapshot, *power.ident) > 0
               for power in me_powers.POWERS)


def _absorbed_recharge(policy, snapshot):
    """(the most ticks a wait for the absorbed rod can take: a full recharge from a cast, the turn
    its list should show a use again at the rested rate), from the list last shown and the board
    (rod_recharge); None when the board does not give them."""
    from hengbot.me_power_success import int_index
    entry = (getattr(policy, "_me_device_lists", None) or {}).get("rod")
    row = me_capability.observed_row(policy, "rod", SV_ROD_DETECTION)
    index = int_index(snapshot.player)
    unrested = rod_recharge.regen_amount(snapshot.player.food_state, resting=False)
    rested = rod_recharge.regen_amount(snapshot.player.food_state, resting=True)
    if entry is None or row is None or index is None or unrested is None:
        return None
    count, charging = row.get("max"), row.get("charging")
    if not isinstance(count, int) or not isinstance(charging, int):
        return None
    longest = rod_recharge.absorbed_ready_ticks(count, count, index, unrested)
    soonest = rod_recharge.absorbed_ready_ticks(count, charging, index, rested)
    if longest is None or soonest is None:
        return None
    return longest, entry[0] + rod_recharge.game_turns(soonest)


def wait_deadline(policy, snapshot, memory, rod, recharge):
    """The last turn the wait on this cell may rest to, or None when the recharge cannot be
    bounded (no wait); ``recharge`` is the absorbed rod's ``_absorbed_recharge``.

    The wait lasts at most the real recharge of the rod held from the first rest on the cell: a
    carried rod's pval ticks, an absorbed rod's full recharge at the unrested rate; with both, the
    sooner; never more than ``MAX_WAIT_TICKS``."""
    if rod_recharge.regen_amount(snapshot.player.food_state, resting=False) is None:
        return None  # fainting: the regeneration may be 0 (starving), nothing recharges
    here = snapshot.player.position
    wait = memory["wait"]
    longest = rod_recharge.game_turns(MAX_WAIT_TICKS)
    if wait is None or wait[1] != here or snapshot.turn - wait[2] > longest:
        wait = (snapshot.turn, here, snapshot.turn)
    memory["wait"] = (wait[0], here, snapshot.turn)
    ticks = [MAX_WAIT_TICKS]
    if rod is not None:
        ticks.append(rod_recharge.carried_ready_ticks())
    if recharge is not None:
        ticks.append(recharge[0])
    return wait[0] + rod_recharge.game_turns(min(ticks))


def _give_up(memory, snapshot, deadline) -> None:
    memory["given_up"] = True
    memory["wait"] = None
    position = snapshot.player.position
    print(f"<{GIVE_UP_EVENT}> turn {snapshot.turn} at ({position.y},{position.x}): the rod held "
          f"was not ready by turn {deadline}; stepping on undetected", file=sys.stderr)


def key(policy, snapshot) -> str | None:
    """On 50F+, before a step out of the trap-detected area: zap the carried rod, else leave an
    absorbed trap detection with a use to me_powers, else wait for the rod held (carried or
    absorbed) to recharge, at most its real recharge (``wait_deadline``)."""
    from hengbot import me_device_attacks, me_powers
    from hengbot.item_reservation import reserved_item_command

    if not _deep_floor(snapshot):
        return None
    player = snapshot.player
    if player.blind or player.confused or player.hallucinated:
        return None
    rod = carried(snapshot)
    eaten = absorbed(policy, snapshot)
    if rod is None and not eaten:
        return None
    if not me_powers.utility_device_permitted(policy, snapshot):
        return None
    if not undetected_step(policy, snapshot):
        return None
    memory = _memory(policy, snapshot)
    here = player.position
    if memory["failed"].get(here, 0) >= FAILURES_PER_PLACE:
        return None
    if rod is not None and _ready(rod) > 0:
        zap = reserved_item_command(policy, snapshot, "rod", rod)
        if zap is not None:
            memory["pending"] = (snapshot.turn, here)
            memory["wait"], memory["given_up"] = None, False
            policy.last_reason = ZAP_REASON
            return zap
    if _trap_detection_ready(policy, snapshot):
        # Cast by me_powers' floor occasion (safe-now layer); declined there (its hostile rule,
        # its failures), it is not waited for either.
        memory["wait"], memory["given_up"] = None, False
        return None
    recharge = _absorbed_recharge(policy, snapshot) if eaten else None
    if recharge is not None and snapshot.turn >= recharge[1]:
        # The rested rate has the absorbed rod ready: the game shows its list again before the
        # next decision (me_powers_refresh.resume_read_key, no game time).
        me_device_attacks.mark_stale(policy, {"rod"})
    if player.recalling or policy._physical_hostiles(snapshot) or memory["given_up"]:
        return None
    deadline = wait_deadline(policy, snapshot, memory, rod, recharge)
    if deadline is None or snapshot.turn > deadline:
        _give_up(memory, snapshot, deadline)
        return None
    # The rod recharges: rest in place (a monster coming into view cuts the rest short, and the
    # ladder above answers it).
    policy._nav_exhausted = False
    policy._nav_stall_count = 0
    policy._recent.clear()  # the rest's standing still must not read as an oscillation
    policy.last_reason = WAIT_REASON
    return f"R{WAIT_PLAYER_TURNS}\r"
