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

Owner 2026-11-17 (n1-b life-411, verbatim): 「想定は城の20Fから潜り城40F付近を探索することである。
なにかを曲解した実装になっている可能性が高い」.  The character (Angband 51, no *Destruction* means:
the absorbed power at 78%) had its Angband landing refused by the 50F gate; the unsafe-recall
fallback (policy._activate_safe_recall_fallback) found no entered landing between the floor
(51 - 20 = 31) and 50 (the Castle 20, the Mountain 30, dungeon 18 30), and this dive was read for
the two valves only, so the visit opened the no-safe-destination fundraising and mined the Yeek
cave 1F for hours.  ``pick_refused`` is the same dive for that fallback: the Castle first (the
owner's words), else the Mountain.  There the floor is where the dive must reach, not a ceiling:
the descent goes on to the deepest floor the depth requirements permit (49 without the means), as
the guardian valve's Angband (``angband_valve_dive``).  The switch is held
(``refused_dive_held``) so the depth floor does not end it on the next town board.

Owner 2026-11-17 (n1-a life-530, verbatim): 「49Fに帰還して上り階段を探して適正階層まで行く」.  The
Lv42 Warrior (Angband 50 refused: no *Destruction* means, no telepathy; the Castle and the Mountain
landing at 49, the over-extended depth 49 recorded in Angband) found no landing above the floor 30
and fundraised at the Yeek cave.  The fallback is one answer for every character: the Castle (else
the Mountain) is explored in the band ``CLIMB_BAND_LOW``..+``CLIMB_BAND_SPAN`` (38-42, the owner's
「40F付近」 with two floors either side; raised to the fallback depth floor when that is deeper,
owner 2026-11-13 「最新到達-20Fまで」), wherever the recall lands:

- landing above the band (n1-b's Castle 20): the ordinary descent goes down to the band (the
  11-17 n1-b reading that went on to 49 gives way to 「城40F付近を探索」);
- landing below it (n1-a's 49, deeper than the over-extended depth: the owner names the Castle,
  so that depth does not bound this switch): on every floor deeper than the band the up stairs
  are the stairs taken (``climbing``, ladder_descent's climb rung) and no stair down is
  (``capped``); the escapes decided there are no over-extension evidence (escape_count) and the
  dive is no lack of depth progress (policy_observation);
- in the band: the ordinary floor rules, no stair below the band (``capped``).

The landing and the band must meet the depth requirements and pass no guardian floor
(``reaches_band``); the recall depth itself is never reset (the executor refuses the game's
reset-recall question, fallback_depth_floor).

Owner 2026-11-19 「n1-bは次回潜行時に95Fまで登り階段で戻ること。以降、準備ができるまで鉄獄95Fで探索」:
an Angband floor deeper than the cap is climbed the same way (``climbing`` / ``climbing_floor``) and
no stair passes the cap (``capped``); the rule, its cap and its recall-depth answer are angband_cap's.
"""

from __future__ import annotations

from hengbot import angband_cap, fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND

DUNGEON_CASTLE = 12  # 城 (lib/edit/DungeonDefinitions.jsonc)
DUNGEON_MOUNTAIN = 14  # 山
DIVE_FLOOR_DUNGEONS = (DUNGEON_CASTLE, DUNGEON_MOUNTAIN)
STATE = "_alternate_dive_floor"
LEASED_REASONS = frozenset({"over_extended_dives", "no_depth_progress"})  # alternate_lease's
# The guardian valve's switches (policy._activate_safe_recall_fallback, policy_observation).
GUARDIAN_VALVE_REASONS = frozenset({"guardian_valve", "guardian_bounce_valve"})
# The unsafe-recall fallback's switch (policy._activate_safe_recall_fallback).
SAFE_FALLBACK_REASON = "safe_fallback"
# Owner 2026-11-17 「想定は城の20Fから潜り城40F付近を探索」: the Castle before the Mountain there.
REFUSED_DIVE_ORDER = (DUNGEON_CASTLE, DUNGEON_MOUNTAIN)
# Owner 2026-11-17 「49Fに帰還して上り階段を探して適正階層まで行く」 (「40F付近」): the band explored.
CLIMB_BAND_LOW = 38
CLIMB_BAND_SPAN = 4


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


def band(policy, snapshot) -> tuple[int, int]:
    """The floors the unsafe-recall fallback's Castle explores: (shallowest, deepest)."""
    low = max(CLIMB_BAND_LOW, fallback_depth_floor.floor(policy, snapshot))
    return low, low + CLIMB_BAND_SPAN


def pick_refused(policy, snapshot, *, refused_depth: int) -> int | None:
    """The unsafe-recall fallback's dive: the Castle, else the Mountain, whose landing and band
    the kit may reach (``reaches_band``), the band shallower than the refused landing, or None.
    The landing may lie above the band (the dive goes down to it) or below it (the climb)."""
    low, _high = band(policy, snapshot)
    if low >= refused_depth:
        return None
    for did in REFUSED_DIVE_ORDER:
        if (did in (snapshot.entered_dungeon_ids or ())
                and policy._fallback_destination_allowed(did)
                and reaches_band(policy, snapshot, did)):
            return did
    return None


def reaches_band(policy, snapshot, dungeon_id: int) -> bool:
    """The recall lands in ``dungeon_id`` on a floor the kit may arrive on, and the band lies
    within the dungeon, meets the depth requirements and is no blocked guardian floor."""
    info = policy._dungeon_knowledge.get(dungeon_id)
    if info is None:
        return False
    high = band(policy, snapshot)[1]
    landing = _landing(snapshot, info)
    return (info.max_depth >= high
            and policy._fallback_landing_allowed(snapshot, dungeon_id, landing, depth_floor=False)
            and not policy._missing_required_abilities(snapshot, high)
            and not policy._guardian_floor_blocked(snapshot, dungeon_id, high))


def bind_refused(policy, snapshot, alternate) -> None:
    """The unsafe-recall fallback just switched to ``alternate`` (``pick_refused``): hold it
    with its band's shallowest floor (the record; the band is read from the board, ``band``)."""
    setattr(policy, STATE, (alternate, band(policy, snapshot)[0]))


def climb_dungeon(policy) -> int | None:
    """The dungeon of the held climb switch (the unsafe-recall fallback's Castle), or None.
    A switch held before 2026-11-17's band (its record the floor) is the same switch."""
    held = getattr(policy, STATE, None)
    alternate = getattr(policy, "_alternate_dungeon", None)
    if (not held or alternate not in DIVE_FLOOR_DUNGEONS or held[0] != alternate
            or getattr(policy, "_alternate_dungeon_reason", None) != SAFE_FALLBACK_REASON):
        return None
    return alternate


def climbing_floor(policy, snapshot, floor_key) -> bool:
    """``floor_key`` is a floor of the held climb switch's dungeon deeper than its band, or an
    Angband floor deeper than the cap (angband_cap, owner 2026-11-19)."""
    if angband_cap.climbing_floor(floor_key):
        return True
    dungeon = climb_dungeon(policy)
    return (dungeon is not None and floor_key is not None and floor_key[1] > 0
            and floor_key[0] == dungeon and floor_key[1] > band(policy, snapshot)[1])


def climbing(policy, snapshot) -> bool:
    """On a floor of the held climb switch's dungeon deeper than its band, or on an Angband floor
    deeper than the cap: the up stairs."""
    return not snapshot.in_town and climbing_floor(policy, snapshot, snapshot.floor_key)


def refused_dive_held(policy, snapshot) -> bool:
    """The held switch is the unsafe-recall fallback's Castle (``pick_refused``)."""
    alternate = getattr(policy, "_alternate_dungeon", None)
    held = getattr(policy, STATE, None)
    return (alternate in DIVE_FLOOR_DUNGEONS
            and getattr(policy, "_alternate_dungeon_reason", None) == SAFE_FALLBACK_REASON
            and bool(held) and held[0] == alternate
            and reaches_band(policy, snapshot, alternate))


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
    """A descent to ``destination`` would pass the target of the dungeon being dived, or the
    Angband cap (angband_cap, owner 2026-11-19 「準備ができるまで鉄獄95Fで探索」)."""
    if angband_cap.capped(snapshot, destination):
        return True
    depth = target(policy)
    if depth is None and climb_dungeon(policy) is not None:
        depth = band(policy, snapshot)[1]  # the climb switch: no stair below its band
    return (depth is not None and snapshot.dungeon_level > 0
            and snapshot.floor_key[0] == policy._alternate_dungeon and destination > depth)
