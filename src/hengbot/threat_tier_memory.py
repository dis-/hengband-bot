"""Threat tiers: the decided side of the engagement (owner 2026-11-08 「境に余裕を持たせる」).

Split out of ``threat_tiers`` (maintainability review 2026-11-09, step 4): the per-floor-visit
memory of each monster's decided tier and side (``TierMemory``, ``Decided``), its forgetting
(``observe``) and the hold (``held_tier``, ``decided``).  ``threat_tiers`` re-exports every
name here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from hengbot import retreat_veto_life
from hengbot.supply_fight import supply_fight_stopped
from hengbot.threat_projection import T1, T2, T3, Assessment, SupplyPlan, adjusted_speed


# ---------------------------------------------------------------- the decided side (owner 2026-11-08)
#
# Owner 2026-11-08 (the bear pack: T2 by about 3 HP, left when seen and walked back to when hidden;
# the HP moved the reading across the T3/T2 boundary as well), answer 「境に余裕を持たせる」: once a
# monster's tier is decided, small changes of the HP or of the estimates do not flip it; fight or
# leave stays on the side decided first.
#
# The memory is per floor visit and per monster (the game's list index with its race, as
# retreat_veto_life): the decided tier, the side, the margins of the deciding reading and the
# monster's speed then.  A later reading of the engagement moves the tier only across a boundary
# it passes by the band, the reading's own reserve (D7 「余裕は最大HPの1割と、95%被害のうち大きい
# 方」, the margin the design already keeps between a plan and the HP): T3/T2 at ``free_margin``,
# T2/T1 at ``supply_margin``.  No new number.  Taken as read instead (the hard overrides): the
# 1-turn 即死 (3.1) and the stop conditions of the committed fight (D4); a monster new to the
# engagement, or faster than when decided, lets a worse reading through without the band (a
# stronger engagement, not an estimate's drift); a new floor visit forgets everything.  A better
# reading is taken only while every remembered monster of the deciding engagement is in this one:
# a pack mate out of sight keeps its side, so the visible part of a pack decided "leave" is not
# fought alone.  A monster that died, changed shape or was not shown for
# retreat_veto_life.UNSEEN_GAME_TURNS is forgotten (``observe``), as its retreat's veto is.
#
# The leave side reaches routing through the existing retreat veto: the flee rung claims the cell
# it leaves for the monsters it fled (policy ``_claim_engagement_avoid_cells``), so seek-loot and
# exploration do not walk back while the pack is remembered; a side that turns to fight lifts
# that veto (``retreat_veto_life.release``).

TIER_MEMORY = "_threat_tier_memory"
TIER_ORDER = (T1, T2, T3)            # worst first
TIER_RANK = {tier: rank for rank, tier in enumerate(TIER_ORDER)}


@dataclass
class Decided:
    tier: str
    leave: bool                       # the side: T1, or T2 with no selected target
    free_margin: float | None         # the deciding reading's margins and band (telemetry)
    supply_margin: float | None
    reserve: int
    speed: int                        # adjusted_speed when decided
    group: frozenset                  # the deciding engagement's (index, race) keys
    threat: retreat_veto_life.Threat  # name and the last board that showed it (``observe``)


@dataclass
class TierMemory:
    floor: tuple
    decided: dict = field(default_factory=dict)  # (index, race) -> Decided
    last_turn: int | None = None                 # the previous observed board


# Pickle compatibility: policy checkpoints hold a TierMemory of Decided entries
# (``policy._threat_tier_memory``) under ``hengbot.threat_tiers``, where these classes were
# defined before the split.  They keep that path, which ``threat_tiers`` re-exports, so old and
# new checkpoints load either way (tests.test_threat_tier_memory_pickle_1109).
TierMemory.__module__ = Decided.__module__ = "hengbot.threat_tiers"


def _tier_memory(policy, snapshot) -> TierMemory:
    memory = getattr(policy, TIER_MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = TierMemory(snapshot.floor_key)
        setattr(policy, TIER_MEMORY, memory)
    return memory


def observe(policy, snapshot) -> None:
    """Forget the decided sides of the monsters that are gone (once per board, before the
    routes, as ``retreat_veto_life.observe``)."""
    memory = getattr(policy, TIER_MEMORY, None)
    if memory is None or memory.last_turn == snapshot.turn:
        return
    if memory.floor != snapshot.floor_key:
        setattr(policy, TIER_MEMORY, None)
        return
    shown = retreat_veto_life.shown_by_index(snapshot)
    for key, entry in list(memory.decided.items()):
        if retreat_veto_life.gone(snapshot, key, entry.threat, shown, memory.last_turn):
            del memory.decided[key]
    memory.last_turn = snapshot.turn


def forget_floor_visit(policy) -> None:
    setattr(policy, TIER_MEMORY, None)


def engagement_reading(policy, snapshot, hostiles) -> bool:
    """A reading of the engagement itself: it holds every strategic hostile in view.  A part of
    it (one monster on a beam's line, ``me_powers``) is a question about that part, not the
    decision; it neither reads nor writes the decided side."""
    indices = {monster.index for monster in hostiles}
    return bool(indices) and all(monster.index in indices
                                 for monster in policy._strategic_hostiles(snapshot))


def _past(margin: float | None) -> float:
    return float("-inf") if margin is None else margin


def held_tier(held: str, raw: Assessment, *, worse_as_read: bool, mates_in_view: bool) -> str:
    """The tier after the reading ``raw`` of an engagement decided ``held``: each boundary
    between them is crossed only when the reading is past it by the band (``raw.reserve``)."""
    band = raw.reserve
    if TIER_RANK[raw.tier] < TIER_RANK[held]:
        if worse_as_read:
            return raw.tier
        tier = held
        if tier == T3 and -_past(raw.free_margin) >= band:
            tier = T2
        if tier == T2 and raw.tier == T1 and -_past(raw.supply_margin) >= band:
            tier = T1
        return tier
    if raw.tier == held or not mates_in_view:
        return held
    tier = held
    if tier == T1 and _past(raw.supply_margin) >= band:
        tier = T2
    if tier == T2 and raw.tier == T3 and _past(raw.free_margin) >= band:
        tier = T3
    return tier


def _as_held(raw: Assessment, tier: str) -> Assessment:
    """``raw`` with the held ``tier``.  A T2 held over a T3 reading spends nothing: its plan is
    the free win (no supply is drunk or read for a fight the free attacks win)."""
    plan = raw.supply_plan
    if tier == T2 and raw.tier == T3:
        plan = SupplyPlan(categories=(), turns=raw.free_turns or 0,
                          incoming=raw.free_incoming or 0, capacity=0, reserve=raw.reserve)
    return replace(raw, tier=tier, raw_tier=raw.tier, supply_plan=plan)


def decided(policy, snapshot, hostiles, raw: Assessment) -> Assessment:
    """The engagement's reading with its decided side held (「境に余裕を持たせる」); the memory
    is updated for its monsters."""
    if raw.tier is None:
        return raw  # past the cost cap: no reading to decide, or to hold against
    memory = _tier_memory(policy, snapshot)
    keys = [(monster.index, monster.race_id) for monster in hostiles]
    entries = [memory.decided.get(key) for key in keys]
    known = [entry for entry in entries if entry is not None]
    overridden = raw.instant_death or supply_fight_stopped(snapshot, hostiles)
    tier = raw.tier
    if known and not overridden:
        here = set(keys)
        mates = set().union(*(entry.group for entry in known))
        tier = held_tier(
            next(tier for tier in TIER_ORDER if any(entry.tier == tier for entry in known)), raw,
            worse_as_read=len(known) < len(keys) or any(
                entry is not None and adjusted_speed(monster) > entry.speed
                for monster, entry in zip(hostiles, entries)),
            mates_in_view=all(key in here for key in mates if key in memory.decided))
    leave = tier == T1 or (tier == T2 and not raw.selected)
    group, fought = frozenset(keys), []
    for monster, key, entry in zip(hostiles, keys, entries):
        if entry is not None and entry.leave and not leave:
            fought.append(key)
        if entry is not None and entry.tier == tier and not overridden:
            entry.leave = leave  # the tier holds; the selection is read as it is
            continue
        memory.decided[key] = Decided(
            tier, leave, raw.free_margin, raw.supply_margin, raw.reserve,
            adjusted_speed(monster), group, retreat_veto_life.Threat(monster.name, snapshot.turn))
    if fought:
        retreat_veto_life.release(policy, snapshot, fought)
    return raw if tier == raw.tier else _as_held(raw, tier)


def decided_sides(policy, snapshot, hostiles) -> list:
    """The remembered sides of ``hostiles`` (telemetry: reads, never writes)."""
    memory = getattr(policy, TIER_MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return []
    return [{"index": monster.index, "tier": entry.tier, "leave": entry.leave}
            for monster in hostiles
            if (entry := memory.decided.get((monster.index, monster.race_id))) is not None]
