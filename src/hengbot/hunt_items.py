"""The floor items worth a walk before anything erases or leaves them (the hunt items).

Supervisor 2026-11-28 (under the owner's 2026-11-26 permission to change in-game choices from
measured numbers): n1-b life-419 (Magic-Eater CL50, Angband 80F, 191 floors in about 15 h) saw
405 wanted rings and amulets on the floor and picked up 28%; 41% went in its own *Destruction*
and 23% were left behind by the Recall.  Of the 11 Rings of Speed it saw, it picked up 2; 4 went
in its *Destruction*, 5 were left (C:/hengband-backups/pdca/captures/loot-before-destruction-1128,
the investigator's ledger of 2026-11-28).

A hunt item is a found floor item (grid_map ``found_items``: seen or detected) of one of these
kinds (``hunt_pile``, the one definition):

* a ring or an amulet the existing junk valuation does not throw away: an unaware kind (what it
  is is not known yet), or an aware kind of a base cost above 0 (lib/edit BaseitemDefinitions
  ``cost``: the worthless kinds the pick rules destroy) that policy ``_junk_class`` keeps;
* the Ring of Speed (``RING_OF_SPEED``) while the permanent speed misses a depth speed row
  (``speed_row_missed``: angband_cap ``speed_ceiling`` not None) -- also a ring kind above, named
  for its own reason;
* an aware kind whose base flags (BaseitemDefinitions ``flags``, ``ABILITY_BY_FLAG``) give an
  ability the next floor's depth rows ask and the character misses (policy
  ``_missing_required_abilities``), or the Staff of *Destruction* while the 50F+ means is missing.

No class or character is named: the rows and the junk valuation decide.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from hengbot import depth_gap_gear
from hengbot.model import InventoryItem, Position, TVAL_AMULET, TVAL_RING

# BaseitemDefinitions.jsonc id 136 (ring 「スピード」, tval 45 sval 31, angband_cap
# RING_OF_SPEED_DEPTH).
RING_OF_SPEED = (depth_gap_gear.TVAL_RING, depth_gap_gear.SV_RING_SPEED)
JEWELLERY_TVALS = frozenset({TVAL_RING, TVAL_AMULET})
# The base flags (lib/edit/BaseitemDefinitions.jsonc ``flags``; src/object-enchant/tr-types.h) to
# the depth rows' ability names (policy_constants RESIST_FLAG_BY_ABILITY, SPEED_GATE_LABELS).  An
# immunity covers its resistance (player-status-resist.cpp: an immune element is resisted).
ABILITY_BY_FLAG = {
    "RES_ACID": "resist_acid", "IM_ACID": "resist_acid",
    "RES_ELEC": "resist_elec", "IM_ELEC": "resist_elec",
    "RES_FIRE": "resist_fire", "IM_FIRE": "resist_fire",
    "RES_COLD": "resist_cold", "IM_COLD": "resist_cold",
    "RES_POIS": "resist_pois", "RES_FEAR": "resist_fear", "RES_LITE": "resist_lite",
    "RES_DARK": "resist_dark", "RES_BLIND": "resist_blind", "RES_CONF": "resist_conf",
    "RES_SOUND": "resist_sound", "RES_SHARDS": "resist_shard", "RES_NETHER": "resist_neth",
    "RES_NEXUS": "resist_nexus", "RES_CHAOS": "resist_chaos", "RES_DISEN": "resist_disen",
    "FREE_ACT": "free_action", "SEE_INVIS": "see_invisible", "TELEPATHY": "telepathy",
}
SPEED_FLAG = "SPEED"


@lru_cache(maxsize=1)
def _kind_flags() -> dict:
    """(tval, sval) -> the base kind's flags, read once from BaseitemDefinitions.jsonc ({} when
    the definitions are not found: the flag clause then names nothing)."""
    from hengbot.baseitem_knowledge import find_baseitem_definitions
    from hengbot.monrace_knowledge import _strip_jsonc
    path = find_baseitem_definitions(Path(__file__))
    if path is None:
        return {}
    data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    flags = {}
    for entry in data.get("baseitems", data.get("items", [])):
        kind = entry.get("itemkind", entry)
        flags[(int(kind["type_value"]), int(kind["subtype_value"]))] = frozenset(
            flag for flag in entry.get("flags", ()) if isinstance(flag, str))
    return flags


def speed_row_missed(policy, snapshot) -> bool:
    """The permanent speed misses a depth speed row (depth_gap_gear ``speed_row``, the one answer
    to it): the Ring of Speed is a hunt item."""
    from hengbot import depth_gap_gear  # import cycle
    return depth_gap_gear.speed_row(policy, snapshot) is not None


def speed_held(policy, snapshot) -> bool:
    """The character is held under the speed ceiling on a floor of the Ring of Speed hunt
    (angband_cap ``ring_hunt_floor``: Angband, from the ring's allocation depth down to the
    ceiling of the unmet +25 row)."""
    from hengbot import angband_cap  # import cycle
    return angband_cap.ring_hunt_floor(policy, snapshot)


def _next_floor_gaps(policy, snapshot) -> frozenset:
    """The depth-row abilities the next floor asks and the character misses."""
    from hengbot.item_reservation import decision_memo
    depth = snapshot.dungeon_level + 1
    return decision_memo(policy, "hunt-items-gaps", snapshot, depth, lambda: frozenset(
        policy._missing_required_abilities(snapshot, depth)))


def _closes_gap(policy, snapshot, kind) -> bool:
    from hengbot import destruction_means
    from hengbot.policy_constants import DESTRUCTION_GATE_LABEL, SPEED_GATE_LABELS
    gaps = _next_floor_gaps(policy, snapshot)
    if not gaps:
        return False
    if kind == destruction_means.STAFF and DESTRUCTION_GATE_LABEL in gaps:
        return True
    flags = _kind_flags().get(kind, frozenset())
    if SPEED_FLAG in flags and gaps & SPEED_GATE_LABELS:
        return True
    return any(ABILITY_BY_FLAG.get(flag) in gaps for flag in flags)


def _jewellery_kept(policy, snapshot, tval, sval) -> bool:
    """A ring or amulet kind the junk valuation keeps: unaware, or a base cost above 0 that
    ``_junk_class`` does not throw away."""
    if sval is None:
        return True
    cost = policy._baseitem_costs.get((tval, sval))
    if cost is not None and cost <= 0:
        return False
    probe = InventoryItem(slot="floor", name="", count=1, tval=tval, sval=sval,
                          aware=True, known=False, is_equipment=True)
    return policy._junk_class(snapshot, probe) is None


def hunt_kind(policy, snapshot, tval, sval) -> bool:
    """``(tval, sval)`` (``sval`` None: an unaware kind) is a hunt item's kind."""
    if sval is not None and (tval, sval) == RING_OF_SPEED and speed_row_missed(policy, snapshot):
        return True
    if tval in JEWELLERY_TVALS:
        return _jewellery_kept(policy, snapshot, tval, sval)
    return sval is not None and _closes_gap(policy, snapshot, (tval, sval))


def _pile_kinds(snapshot, position):
    """The (tval, sval or None) of each found item on ``position``."""
    row = next((row for row in snapshot.found_items or ()
                if (row[0], row[1]) == (position.y, position.x)), None)
    if row is None:
        return ()
    ids = (snapshot.found_item_ids or {}).get(position) or ()
    kinds = []
    for index, tval in enumerate(row[3:]):
        identity = ids[index] if index < len(ids) else None
        sval = identity.get("sval") if isinstance(identity, dict) else None
        kinds.append((tval, sval if isinstance(sval, int) and sval >= 0 else None))
    return tuple(kinds)


def hunt_pile(policy, snapshot, position) -> bool:
    """A found item of a hunt kind lies on ``position`` (``hunt_kind``)."""
    return any(hunt_kind(policy, snapshot, tval, sval) for tval, sval in _pile_kinds(snapshot, position))


def hunt_piles(policy, snapshot) -> frozenset:
    """Every found pile of the board holding a hunt item."""
    from hengbot.item_reservation import decision_memo
    return decision_memo(policy, "hunt-items-piles", snapshot, None, lambda: frozenset(
        Position(row[0], row[1]) for row in snapshot.found_items or ()
        if hunt_pile(policy, snapshot, Position(row[0], row[1]))))


def sale_only_gear(policy, snapshot, position) -> bool:
    """While the character is held at the speed ceiling (``speed_held``): the found pile on
    ``position`` is weapons and armour alone, each identified plain (describe_flavor's bonus
    marks, floor_identify ``_KNOWN``, and no ego or artifact id) and no hunt kind -- gear whose one
    worth is its sale.  Supervisor 2026-11-28 (rule 4): such a pile is not picked up in that state
    (policy_helpers ``_floor_pile_is_junk``); this replaces, for that state only, the 2026-09-23
    pickups with no distance cap.  An unidentified piece is still gone to and identified where
    it lies (floor_identify)."""
    from hengbot.floor_identify import WEAPON_ARMOUR_TVALS, _KNOWN  # import cycle
    kinds = _pile_kinds(snapshot, position)
    if not kinds or any(tval not in WEAPON_ARMOUR_TVALS for tval, _sval in kinds):
        return False
    names = (snapshot.found_item_names or {}).get(position) or ()
    ids = (snapshot.found_item_ids or {}).get(position) or ()
    for index, (tval, sval) in enumerate(kinds):
        name = names[index] if index < len(names) else None
        identity = ids[index] if index < len(ids) else None
        if not isinstance(name, str) or not _KNOWN.search(name):
            return False
        if isinstance(identity, dict) and ("ego_id" in identity or "artifact_id" in identity):
            return False
        if hunt_kind(policy, snapshot, tval, sval):
            return False
    return speed_held(policy, snapshot)


# --- the walk to the hunt piles before and during a Recall (rules 3 and 4) ------------------
#
# Supervisor 2026-11-28 (rule 3): before a Recall no emergency reads (``BEFORE_RECALL_TRIGGERS``)
# and in its countdown, the hunt piles are walked to first, nearest first: before the read at any
# distance, in the countdown within its reach (recall_wait_reach; this replaces the 2026-11-17 Q3
# order 「待ちの残りで届く所まで」 for the hunt piles only, its gates kept).  n1-b life-419
# (2026-11-28 02:19, turn 13910555): the pack-full Recall was read at (15,51) with the Rings of
# Speed 15 off at (29,48) (a cell the area mapping did not hold) and 69 off at (16,120); the wait
# picked up a 毛皮のクローク and a ルツェルン・ハンマー 1-3 cells off.  Rule 4: a full pack takes a
# hunt pile of one item for its cheapest spare (full_pack_exchange).

# The return's own loot walk reason (town_hold: a walk to a target).
SEEK_REASON = "return:seek-loot"
# The pre-read walk's decisions on a floor visit: one crossing of the widest floor (MAX_WID 198,
# src/system/angband.h) and back; past it the Recall is read as before.
WALK_DECISIONS_MAX = 2 * 198
# {"floor": floor_key, "decisions": int, "tried": set of Position (a pile stood on and not taken)}
MEMORY = "_hunt_walk_memory"


def _memory(policy, snapshot) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        memory = {"floor": snapshot.floor_key, "decisions": 0, "tried": set()}
        setattr(policy, MEMORY, memory)
    return memory


def walk_key(policy, snapshot, hostiles, *, max_path_distance=None, reason=SEEK_REASON) -> str | None:
    """The pickup of (or the room for, or the step toward) the nearest hunt pile the loot owner
    may take, else None: the shortest walk over the known floor and, on 50F+, over the cells the
    map does not hold (recall_wait_unknown_path, owner 2026-11-23 「見ていないマスも通って向かう」), within
    ``max_path_distance`` (None: any) and ``WALK_DECISIONS_MAX``.  The loot owner's block reasons
    (but a full pack) stop it; with a full pack only a pile of one item with a spare to give for
    it is gone to."""
    from hengbot import full_pack_exchange, recall_wait_unknown_path  # import cycle
    from hengbot.policy_constants import DEEP_FLOOR_DEPTH, PACK_CAPACITY

    if snapshot.in_town or policy._loot_block_reason(snapshot, hostiles, ignore_pack=True) is not None:
        return None
    memory = _memory(policy, snapshot)
    if memory["decisions"] >= WALK_DECISIONS_MAX:
        return None
    full = len(snapshot.inventory) >= PACK_CAPACITY
    if full and full_pack_exchange.spare(policy, snapshot) is None:
        return None
    piles = {position for position in hunt_piles(policy, snapshot) & policy._loot_candidates(snapshot)
             if position not in memory["tried"]
             and (not full or full_pack_exchange.single(snapshot, position))}
    if not piles:
        return None
    here = snapshot.player.position
    if here in piles:
        answer = (full_pack_exchange.key(policy, snapshot, hostiles, only=frozenset({here})) if full
                  else policy._current_floor_item_key(snapshot, pickup_reason="pickup",
                                                      trigger_reason="trigger-autodestroy"))
        if answer is None:
            memory["tried"].add(here)
            return None
        memory["decisions"] += 1
        return answer
    answer = recall_wait_unknown_path.walk(policy, snapshot, hostiles, max_path_distance, reason,
                                           candidates=piles,
                                           unknown=snapshot.dungeon_level >= DEEP_FLOOR_DEPTH)
    if answer is not None:
        memory["decisions"] += 1
    return answer
