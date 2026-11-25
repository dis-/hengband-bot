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
  safe-now layer; its new-floor cast is the Detect Evil row's preferred rod, as before).  While
  the rod held recharges, the player rests in place until it is charged (``WAIT_REASON``): a step
  out of the detected area is exactly what the owner's rule is for.

Nothing refuses 50F+ without the rod (not decided: the owner was not asked).
"""

from __future__ import annotations

from hengbot import door_detect_cover, fundraising_route, me_capability
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


def key(policy, snapshot) -> str | None:
    """On 50F+, before a step out of the trap-detected area: zap the carried rod, else wait for
    the rod held (carried or absorbed) to recharge."""
    from hengbot import me_powers
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
            policy.last_reason = ZAP_REASON
            return zap
    if eaten and me_capability.charges(policy, snapshot, "rod", SV_ROD_DETECTION) > 0:
        # The absorbed rod is cast by me_powers' floor occasion (safe-now layer); declined there
        # (its hostile rule, its failures), it is not waited for either.
        return None
    if player.recalling or policy._physical_hostiles(snapshot):
        return None
    # The rod recharges: rest in place (a monster coming into view cuts the rest short, and the
    # ladder above answers it).
    policy._nav_exhausted = False
    policy._nav_stall_count = 0
    policy._recent.clear()  # the rest's standing still must not read as an oscillation
    policy.last_reason = WAIT_REASON
    return f"R{WAIT_PLAYER_TURNS}\r"
