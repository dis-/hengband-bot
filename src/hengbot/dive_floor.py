"""The Castle or the Mountain, dived to the fallback depth floor when no landing fits.

Owner 2026-11-15 (verbatim), asked what n1-c should do when the over-extension switch finds no
landing (Angband 49F too hard; the fallback depth floor 29 = the deepest reached 49 less 20,
owner 2026-11-13; the only entered landing in 29-48 the Chameleon cave 30, never a fallback):
「想定は城か山。城29F、山29Fをターゲットにして、浅いところから潜って辿り着く。」

When the over-extension valve or the no-depth-progress valve finds no entered landing between
the floor and the depth that was too hard (``_pick_alternate_dungeon``), the Castle or the
Mountain may be the switch although its recall landing is above the floor: the target depth
is the floor, the recall lands where the save holds it and the stairs go down to the target.

- Candidates: the two the owner names (lib/edit/DungeonDefinitions.jsonc id 12 城 Castle,
  depth 20-65; id 14 山 Mountain, depth 25-50), entered (an alternate that was never entered is
  no walk-in target, ``_observe``), reaching the target (its max depth), the target shallower
  than the depth that was too hard, the ordinary fallback checks on the landing
  (``_fallback_destination_allowed``, ``_fallback_landing_allowed`` without the floor) and the
  depth requirements and the guardian floor at the target.  The Chameleon cave never is
  (owner 2026-11-11 「絶対に入れない」).  Of the two the deeper landing, the one nearer the
  target (the Mountain 25 before the Castle 20 for n1-c).
- The target is held with the switch (``_alternate_dive_floor``: the dungeon and the depth) and
  read only while that dungeon is the leased alternate; the lease, its doubling and the end on
  the deepest destination are unchanged (alternate_lease, owner 2026-11-11), and the depth floor
  does not end a switch whose target is at or below it (fallback_depth_floor.settle).
- The descent: the ordinary descent of the ladder (the descent layer takes a known downstairs
  once the loot and safety rungs above it decline, exploration finds one otherwise) with the
  target as its ceiling -- the shape of the untaken kill quest's depth steering in
  ``_is_descent_target``: a stair below the target is no descent target (``capped``); on the
  target floor the idle layer's exhausted floor takes the up stairs to a fresh one as on any
  floor whose descent is refused.
"""

from __future__ import annotations

from hengbot import fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND

DUNGEON_CASTLE = 12  # 城 (lib/edit/DungeonDefinitions.jsonc)
DUNGEON_MOUNTAIN = 14  # 山
DIVE_FLOOR_DUNGEONS = (DUNGEON_CASTLE, DUNGEON_MOUNTAIN)
STATE = "_alternate_dive_floor"
LEASED_REASONS = frozenset({"over_extended_dives", "no_depth_progress"})  # alternate_lease's
# The guardian valve's switches (policy._activate_safe_recall_fallback, policy_observation).
GUARDIAN_VALVE_REASONS = frozenset({"guardian_valve", "guardian_bounce_valve"})


def _landing(snapshot, info) -> int:
    return snapshot.dungeon_recall_depths.get(info.id, info.min_depth)


def pick(policy, snapshot, *, too_hard: int) -> int | None:
    """The Castle or the Mountain to dive to the floor, or None."""
    target = fallback_depth_floor.floor(policy, snapshot)
    if target >= too_hard:
        return None
    best, best_landing = None, -1
    for did in DIVE_FLOOR_DUNGEONS:
        info = policy._dungeon_knowledge.get(did)
        if (info is None or did not in (snapshot.entered_dungeon_ids or ())
                or did == policy._alternate_dungeon
                or not reaches(policy, snapshot, did)
                or not policy._fallback_destination_allowed(did)):
            continue
        landing = _landing(snapshot, info)
        if (landing > target
                or not policy._fallback_landing_allowed(snapshot, did, landing, depth_floor=False)):
            continue
        if landing > best_landing:
            best, best_landing = did, landing
    return best


def reaches(policy, snapshot, dungeon_id: int) -> bool:
    """A dive in ``dungeon_id`` can reach the floor: the floor is within the dungeon's depth,
    meets the depth requirements and is no guardian floor the kit cannot pass."""
    target = fallback_depth_floor.floor(policy, snapshot)
    info = policy._dungeon_knowledge.get(dungeon_id)
    return (info is not None and info.max_depth >= target
            and not policy._missing_required_abilities(snapshot, target)
            and not policy._guardian_floor_blocked(snapshot, dungeon_id, target))


def angband_valve_dive(policy, snapshot, landing: int) -> bool:
    """The guardian valve's Angband landing ``landing`` is above the floor and dives to it.

    Owner 2026-11-17 (n1-c life-216, Castle 65 and the Mountain 50 both on their unbeaten
    guardian floors, Angband 44 against the floor 45): 「下限まで潜れるなら鉄獄を選ぶ」.  The
    recall lands where the save holds it and the ordinary Angband descent goes on to the floor
    and below (no ``capped`` ceiling: the target is the floor, not a limit)."""
    return (not fallback_depth_floor.landing_allowed(policy, snapshot, landing)
            and reaches(policy, snapshot, DUNGEON_ANGBAND))


def angband_valve_held(policy, snapshot) -> bool:
    """The held switch is the guardian valve's Angband that dives to the floor."""
    return (getattr(policy, "_alternate_dungeon", None) == DUNGEON_ANGBAND
            and getattr(policy, "_alternate_dungeon_reason", None) in GUARDIAN_VALVE_REASONS
            and angband_valve_dive(policy, snapshot,
                                   fallback_depth_floor.landing_depth(
                                       policy, snapshot, DUNGEON_ANGBAND)))


def bind(policy, snapshot, alternate) -> None:
    """A valve just switched to ``alternate``: hold the target when it is a dive to the floor."""
    info = policy._dungeon_knowledge.get(alternate)
    target = fallback_depth_floor.floor(policy, snapshot)
    if (alternate in DIVE_FLOOR_DUNGEONS and info is not None
            and _landing(snapshot, info) < target <= info.max_depth):
        setattr(policy, STATE, (alternate, target))
    else:
        setattr(policy, STATE, None)


def target(policy) -> int | None:
    """The held target depth, while its dungeon is the leased alternate."""
    held = getattr(policy, STATE, None)
    if (not held or held[0] != getattr(policy, "_alternate_dungeon", None)
            or getattr(policy, "_alternate_dungeon_reason", None) not in LEASED_REASONS):
        return None
    return held[1]


def capped(policy, snapshot, destination: int) -> bool:
    """A descent to ``destination`` would pass the target of the dungeon being dived."""
    depth = target(policy)
    return (depth is not None and snapshot.dungeon_level > 0
            and snapshot.floor_key[0] == policy._alternate_dungeon and destination > depth)
