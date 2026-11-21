"""The intended loadout of this visit: the one place that reads and writes the search's target.

Equipment review 2026-11-22 (maintainability-review-equip-1122, stage E2): the loadout search
(``policy_equipment._prepare_equipment_optimization``) stores its result, the target, in
``_equipment_optimization_preparation`` and its input signature in
``_equipment_optimization_signature``; seven modules read the target and force a re-search by
assigning the signature, each by the attribute.  E2 gathers both behind this module without
changing what any of them does:

- readers ask :func:`loadout_target` (and :func:`loadout_target_blockers` /
  :func:`loadout_target_result`, the two reads most callers make of it);
- the search itself keeps its memo through :func:`loadout_search_signature` /
  :func:`record_loadout_search`;
- every other writer stays where it is but calls a named function here --
  :func:`invalidate_loadout_search` (a forced re-search), :func:`replace_loadout_target` (the
  target rewritten, the signature kept), :func:`set_unsearched_loadout_target` (a target not
  produced by a search: the signature forgotten), :func:`clear_loadout_target` (both forgotten).

The names are unique in the package: the town work census resolves calls by bare name.

``scripts/equipment_writer_lint.py`` fails a direct read or write of the two attributes outside
this module and pins, per module, the calls of the writers.

Stage E3 (2026-11-22, behaviour-changing) fixes the target per town visit.  Owner Q1 (verbatim):
「基本的にはそれで良い。99F100Fもそれでバグらず行けるか確認」 to "decide the target loadout once at the
start of each town visit and do not change it during the visit; decide again only on named events --
buying, picking up, withdrawing from Home an item (the owned set gained a candidate)".  The first
search of a visit that chose a loadout is the visit's target (:func:`fix_visit_target`); every later
decision of the visit that would have searched again re-reads that target instead, mapped onto the
board's catalogue ids (:func:`mapped_visit_target`), unless one of ``REDECIDE_EVENTS`` happened
(:func:`redecide_events`).  So the old re-search triggers -- the forced resets of
``SEARCH_RESETTERS``, the calibration's, the worn set changed by applying the target, the shelves'
ammunition, a stat restored, a destination switched -- no longer change the target within a visit.

The events (each names why the visit decided again; the visit journal's ``search`` row carries it):

- ``candidate-gained``: the owned set holds more of some piece than when the target was decided
  (bought, picked up, a Home piece the target's census had not seen, a piece *Identify*-ed or
  uncursed -- its identity changed -- or one this town cannot identify now allowed unidentified).
  The owner's event.
- ``finale-phase``: the 99F/100F preparation phase moved (finale_prep: its check step's read-only
  search, the loadout step's search in the finale's rank, the swap's fixed target, the cap lift, a
  stopped phase back to the ordinary order).  Owner Q1 「99F100Fもそれでバグらず行けるか確認」 and
  2026-11-20 「上限を外す時に初めて着け替える」: the phase decides its loadout in the visit itself.
- ``destination-band-floor``: destination_band_floor engaged a floor (owner 2026-11-21; Q4 of
  this review 「深さの条件を満たす組があれば打撃が半分を下回っても着て行く」).
- ``equipment-rules``: the rules table changed under a restored target (a new build).
- ``target-piece-lost``: a piece of the target is owned no more (sold, destroyed, stolen) --
  NOT covered by the owner's answer; it decides again as before E3 and is reported.
- ``worn-curse-found``: a worn piece the target takes off was found cursed (its take-off
  refused) -- NOT covered by the owner's answer; it decides again as before E3 and is reported.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from hengbot.equipment_optimizer import Loadout, equipment_move_identity
from hengbot.equipment_rules import loadout_banned

# The policy's two attributes (rows of state_registry, owner "equipment_target").
TARGET_STATE = "_equipment_optimization_preparation"
SIGNATURE_STATE = "_equipment_optimization_signature"

# The writer functions, by name (scripts/equipment_writer_lint.py pins their callers).
TARGET_WRITERS = frozenset({"init_loadout_target", "record_loadout_search", "replace_loadout_target",
                            "set_unsearched_loadout_target", "clear_loadout_target",
                            "fix_visit_target"})
# The visit's fixed target (stage E3; a row of state_registry, owner "equipment_target").
VISIT_TARGET_STATE = "_equipment_visit_target"

EVENT_CANDIDATE_GAINED = "candidate-gained"
EVENT_FINALE_PHASE = "finale-phase"
EVENT_DESTINATION_FLOOR = "destination-band-floor"
EVENT_RULES = "equipment-rules"
EVENT_TARGET_PIECE_LOST = "target-piece-lost"
EVENT_WORN_CURSE = "worn-curse-found"
# Every reason the visit's target is decided again (``redecide_events`` and
# ``mapped_visit_target``); the first decision of a visit is ``VISIT_START``.
REDECIDE_EVENTS = (EVENT_CANDIDATE_GAINED, EVENT_FINALE_PHASE, EVENT_DESTINATION_FLOOR,
                   EVENT_RULES, EVENT_TARGET_PIECE_LOST, EVENT_WORN_CURSE)
VISIT_START = "visit-start"
SEARCH_RESETTERS = frozenset({"invalidate_loadout_search", "forget_loadout_search_in_state"})


def init_loadout_target(policy) -> None:
    """A new policy: no target, no search memo."""
    policy._equipment_optimization_signature = None
    policy._equipment_optimization_preparation = None


# --- readers -------------------------------------------------------------------------------

def loadout_target(policy):
    """The intended loadout of this visit: the search's last preparation, or None."""
    return getattr(policy, TARGET_STATE, None)


def loadout_target_blockers(policy) -> tuple:
    """The target's blockers (``()`` with no target)."""
    return getattr(loadout_target(policy), "blockers", ())


def loadout_target_result(policy):
    """The target's search result (None with no target or no result)."""
    return getattr(loadout_target(policy), "result", None)


def loadout_search_signature(policy):
    """The input signature the stored target was searched with (None: re-search)."""
    return getattr(policy, SIGNATURE_STATE, None)


# --- writers -------------------------------------------------------------------------------

def record_loadout_search(policy, signature, preparation) -> None:
    """The search's own store: the target and the signature it was searched with."""
    policy._equipment_optimization_signature = signature
    policy._equipment_optimization_preparation = preparation


def invalidate_loadout_search(policy) -> None:
    """Force the next decision to search again; the stored target stays readable."""
    policy._equipment_optimization_signature = None


def replace_loadout_target(policy, preparation) -> None:
    """The target rewritten in place (re-planned, re-keyed); the search memo is kept."""
    policy._equipment_optimization_preparation = preparation


def set_unsearched_loadout_target(policy, preparation) -> None:
    """A target the search did not produce for the current signature: store it, re-search next."""
    policy._equipment_optimization_signature = None
    policy._equipment_optimization_preparation = preparation


def clear_loadout_target(policy) -> None:
    """No target and no search memo."""
    policy._equipment_optimization_signature = None
    policy._equipment_optimization_preparation = None


def forget_loadout_search_in_state(state: dict) -> None:
    """A restored state whose calibration is stale: drop the search memo (policy_state)."""
    state[SIGNATURE_STATE] = None


# --- the visit's fixed target (stage E3) ------------------------------------------------

@dataclass(frozen=True)
class VisitTarget:
    """The target this town visit decided, and what it was decided on."""
    epoch: object               # policy._town_visit_epoch of the visit
    candidates: tuple           # ``candidate_counts`` when it was decided
    context: tuple              # ``(finale, destination floor, rules version)`` (policy_equipment)
    result: object              # the search's OptimizationResult (``best.loadout`` is the target)


def candidate_counts(items, usable_unidentified) -> tuple:
    """The owned pieces the search may choose from: ``(key, carried, Home)`` counts.

    ``key`` is the identity a move keeps (where a piece is, its inscription and its stack's count
    are not part of it: wearing the target or a deposit gains nothing) and whether the piece is
    allowed unidentified because this town cannot identify it (``usable_unidentified(owned)``,
    policy_identification: a candidate it was not before).  A banned piece is never a candidate.
    Carried (worn and pack) and Home are counted apart: a withdrawal shows the piece in the pack
    while the Home census still lists it until it is read again (n1-c life-217 2026-11-21, the
    Gold Dragon Scale Mail withdrawn by the finale's supplies step), so a gain is a bucket
    holding more than the whole owned count the target was decided on (``redecide_events``)."""
    counts: dict = {}
    for owned in items:
        if loadout_banned(owned.flags):
            continue
        key = (equipment_move_identity(owned.item), bool(usable_unidentified(owned)))
        carried, home = counts.get(key, (0, 0))
        number = max(1, getattr(owned.item, "count", 1) or 1)
        counts[key] = ((carried, home + number) if owned.origin == "home"
                       else (carried + number, home))
    return tuple(sorted((key, carried, home) for key, (carried, home) in counts.items()))


def visit_target(policy, epoch) -> VisitTarget | None:
    """This visit's fixed target, or None (no visit, or none decided in it yet)."""
    held = getattr(policy, VISIT_TARGET_STATE, None)
    if epoch is None or not isinstance(held, VisitTarget) or held.epoch != epoch:
        return None
    return held


def fix_visit_target(policy, epoch, candidates: tuple, context: tuple, result) -> None:
    """The search decided the visit's target (its first decision, or a named event)."""
    setattr(policy, VISIT_TARGET_STATE, VisitTarget(epoch, candidates, context, result))


def redecide_events(held: VisitTarget, candidates: tuple, context: tuple) -> tuple[str, ...]:
    """The named events since ``held`` was decided, from the board's candidates and context."""
    events = []
    owned_before = {key: carried + home for key, carried, home in held.candidates}
    if any(max(carried, home) > owned_before.get(key, 0) for key, carried, home in candidates):
        events.append(EVENT_CANDIDATE_GAINED)
    finale, floor, rules = context
    held_finale, held_floor, held_rules = held.context
    if finale != held_finale:
        events.append(EVENT_FINALE_PHASE)
    # A floor engaged now (a destination switch that leaves it unread decides nothing).
    if floor is not None and floor != held_floor:
        events.append(EVENT_DESTINATION_FLOOR)
    if rules != held_rules:
        events.append(EVENT_RULES)
    return tuple(events)


def mapped_visit_target(held: VisitTarget, items, curse_pinned_ids=frozenset()):
    """(the held result with its target on the catalogue's ids, the events that forbid it).

    A piece of the target is found by the identity a move keeps: first the same catalogue id,
    then the piece worn in that slot, then a worn, a pack and a Home one (ids in order); a stack
    serves as many slots as its count.  None and ``target-piece-lost`` when one is owned no more;
    None and ``worn-curse-found`` when a worn piece the player saw cursed sits in a slot the
    target fills with another."""
    best = getattr(held.result, "best", None)
    loadout = getattr(best, "loadout", None)
    if not isinstance(loadout, Loadout):
        return None, (EVENT_TARGET_PIECE_LOST,)
    used: Counter = Counter()
    origin_rank = {"equipped": 0, "pack": 1, "home": 2}
    by_identity: dict = {}
    for owned in items:
        by_identity.setdefault(equipment_move_identity(owned.item), []).append(owned)
    slots = []
    for slot, piece in loadout.slots:
        pool = [owned for owned in by_identity.get(equipment_move_identity(piece.item), ())
                if used[owned.id] < max(1, getattr(owned.item, "count", 1) or 1)]
        if not pool:
            return None, (EVENT_TARGET_PIECE_LOST,)
        chosen = min(pool, key=lambda owned, slot=slot, piece=piece: (
            owned.id != piece.id,
            not (owned.origin == "equipped" and owned.equipped_slot == slot),
            origin_rank.get(owned.origin, 3), owned.id))
        used[chosen.id] += 1
        slots.append((slot, chosen))
    mapped = Loadout(tuple(slots), loadout.hand_mode)  # the search's own slot order
    for owned in items:
        if (owned.id in curse_pinned_ids and owned.origin == "equipped"
                and getattr(mapped.item_at(owned.equipped_slot), "id", None) != owned.id):
            return None, (EVENT_WORN_CURSE,)
    return replace(held.result, best=replace(best, loadout=mapped)), ()
