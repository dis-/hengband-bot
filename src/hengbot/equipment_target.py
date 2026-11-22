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
  (bought, picked up, a Home piece the target's census had not seen).  The owner's event.
- ``candidate-identified``: a piece the visit already owned is known better -- *Identify*-ed or
  uncursed (its identity changed), or one this town cannot identify now allowed unidentified --
  and nothing was gained (``candidate_gains``: the new identity's excess is the same physical
  piece, item_identity ``stable_identity``, as an identity the owned set lost).  NOT covered by
  the owner's answer (E3 kept it deciding again); n1-c life-220 2026-11-22 06:53 (the feet round
  trip): the visit wore its target's 浮遊の軟革ブーツ, then *Identify* made a carried 革グローブ
  [1,+2], and the whole search, with every other slot open again, took the boots back off for the
  硬革ブーツ the target had put in Home (the 1% margin band of ``_stable_operational_best`` held
  them equal with the [1,+0] gloves, not with the [1,+2] ones).  Owner 2026-11-22 Q1 (decide
  once per visit) and E0 「往復が起きたら停止して直す」: the visit's decision stands and the
  better-known pieces join it -- the search runs over the held target (mapped, as when it is
  read again) and those pieces only (policy_equipment: every other owned piece is
  ``search_excluded``, as the finale's swap excludes all but its fixed target).  Bought,
  picked up or withdrawn pieces still open the whole owned set (E4b, 「組全体の評価で比べる」).
- ``finale-phase``: the 99F/100F preparation phase moved (finale_prep: its check step's read-only
  search, the loadout step's search in the finale's rank, the swap's fixed target, the cap lift, a
  stopped phase back to the ordinary order).  Owner Q1 「99F100Fもそれでバグらず行けるか確認」 and
  2026-11-20 「上限を外す時に初めて着け替える」: the phase decides its loadout in the visit itself.
- ``destination-band-floor``: the band of the planned departure's landing, the search's floor,
  changed (destination_band_floor; stage E4, owner Q4 「深さの条件を満たす組があれば打撃が半分を
  下回っても着て行く」: the search knows the destination, so a new destination band decides again).
- ``destruction-means-gained``: the 50F+ *Destruction* means the search reads became satisfied
  during the visit -- an owned charged staff (bought, withdrawn from the Home, picked up: the
  search's staff gate) or the absorbed power (destruction_means ``optimizer_without_gear``).  Owner
  2026-11-22 on the E3 report's question 4 (verbatim choice): 「決め直す」 -- the target and its depth
  band are decided again in that visit, so a warrior can wear the deep band's set and depart.
  Only the gain counts: the staff absorbed or used up decides nothing (the n1-b life-413 launcher
  flip: a staff the town absorbs is no means, destruction_means ``town_absorbs``).
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
from hengbot.item_identity import stable_identity

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
EVENT_CANDIDATE_IDENTIFIED = "candidate-identified"
EVENT_FINALE_PHASE = "finale-phase"
EVENT_DESTINATION_FLOOR = "destination-band-floor"
EVENT_RULES = "equipment-rules"
EVENT_DESTRUCTION_MEANS = "destruction-means-gained"
EVENT_TARGET_PIECE_LOST = "target-piece-lost"
EVENT_WORN_CURSE = "worn-curse-found"
# Every reason the visit's target is decided again (``redecide_events`` and
# ``mapped_visit_target``); the first decision of a visit is ``VISIT_START``.
REDECIDE_EVENTS = (EVENT_CANDIDATE_GAINED, EVENT_FINALE_PHASE, EVENT_DESTINATION_FLOOR,
                   EVENT_RULES, EVENT_TARGET_PIECE_LOST, EVENT_WORN_CURSE,
                   EVENT_DESTRUCTION_MEANS, EVENT_CANDIDATE_IDENTIFIED)
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
    context: tuple              # ``(finale, destination floor, rules version, means)``
                                # (policy_equipment; ``means``: ``destruction_means_key``)
    result: object              # the search's OptimizationResult (``best.loadout`` is the target)
    # ``candidate_pieces`` when it was decided: each candidate key's physical identity and
    # knowledge (a target restored from before 2026-11-22 has none: every gain then reads as
    # ``candidate-gained``).
    pieces: tuple = ()


def candidate_pieces(items, usable_unidentified) -> tuple:
    """``(key, (stable identity, knowledge))`` of the owned candidates (``candidate_counts``' keys).

    The stable identity (item_identity ``stable_identity``: kind, weight, and the knowledge-gated
    flavour and grade as None while unknown) is what stays when *Identify* changes the key; the
    knowledge is ``(aware, known, fully_known)``, what *Identify* raises."""
    pieces: dict = {}
    for owned in items:
        if loadout_banned(owned.flags):
            continue
        key = (equipment_move_identity(owned.item), bool(usable_unidentified(owned)))
        pieces.setdefault(key, (stable_identity(owned.item), _knowledge(owned.item)))
    return tuple(sorted(pieces.items(), key=lambda entry: entry[0]))


def _knowledge(item) -> tuple[bool, bool, bool]:
    return (bool(getattr(item, "aware", True)), bool(getattr(item, "known", True)),
            bool(getattr(item, "fully_known", True)))


def _better_known(before_key, before, after_key, after) -> bool:
    """Whether the piece ``after`` can be the piece ``before`` known better: the same physical
    identity (``_same_physical``) with more knowledge, or the same identity now allowed
    unidentified (the key's second part)."""
    if before is None or after is None:
        return False
    (identity, knowledge), (other, other_knowledge) = before, after
    if not _same_physical(identity, other):
        return False
    if before_key[0] == after_key[0]:
        return before_key[1] != after_key[1]
    return (all(now >= then for now, then in zip(other_knowledge, knowledge))
            and tuple(other_knowledge) != tuple(knowledge))


def _same_physical(before, after) -> bool:
    """Whether two stable identities can be one item (equipment_mutation ``same_item``)."""
    if before is None or after is None:
        return False
    return (before[0] == after[0] and before[1] == after[1]
            and (before[2] is None or after[2] is None or before[2] == after[2])
            and (before[3] is None or after[3] is None or before[3] == after[3]))


def candidate_gains(held: VisitTarget, candidates: tuple, pieces: tuple = ()) -> tuple[set, set]:
    """(acquired keys, identified keys): the candidate keys owned more than when ``held`` was
    decided, split into pieces the owned set gained and pieces it only knows better.

    A key's excess is a bucket holding more than the whole owned count the target was decided on
    (a withdrawal shows the piece in the pack while the Home census still lists it).  It is
    identified when it is covered by keys the owned set now holds fewer of (whole count, both
    buckets) whose piece it can be, known better (``_better_known``)."""
    owned_before = {key: carried + home for key, carried, home in held.candidates}
    owned_now = {key: carried + home for key, carried, home in candidates}
    excess = {key: max(carried, home) - owned_before.get(key, 0)
              for key, carried, home in candidates
              if max(carried, home) > owned_before.get(key, 0)}
    if not excess:
        return set(), set()
    lost = {key: count - owned_now.get(key, 0) for key, count in owned_before.items()
            if count > owned_now.get(key, 0)}
    held_physical = dict(getattr(held, "pieces", ()) or ())
    now_physical = dict(pieces or ())
    acquired, identified = set(), set()
    for key, count in sorted(excess.items()):
        for gone in sorted(lost):
            if count <= 0:
                break
            if lost[gone] > 0 and _better_known(gone, held_physical.get(gone),
                                                key, now_physical.get(key)):
                taken = min(count, lost[gone])
                count -= taken
                lost[gone] -= taken
        (identified if count <= 0 else acquired).add(key)
    return acquired, identified


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


def destruction_means_key(has_destruction: bool, staff_gate) -> tuple[bool, bool]:
    """The search's two 50F+ *Destruction* means (policy_equipment ``_optimizer_destruction_means``):
    the absorbed power, and an owned charged staff (its gate's presence, not its success: that
    one moves with the worn device skill, so wearing the target would read as a change)."""
    return (bool(has_destruction), staff_gate is not None)


def visit_target(policy, epoch) -> VisitTarget | None:
    """This visit's fixed target, or None (no visit, or none decided in it yet)."""
    held = getattr(policy, VISIT_TARGET_STATE, None)
    if epoch is None or not isinstance(held, VisitTarget) or held.epoch != epoch:
        return None
    return held


def fix_visit_target(policy, epoch, candidates: tuple, context: tuple, result,
                     pieces: tuple = ()) -> None:
    """The search decided the visit's target (its first decision, or a named event)."""
    setattr(policy, VISIT_TARGET_STATE, VisitTarget(epoch, candidates, context, result, pieces))


def redecide_events(held: VisitTarget, candidates: tuple, context: tuple,
                    pieces: tuple = ()) -> tuple[str, ...]:
    """The named events since ``held`` was decided, from the board's candidates and context."""
    events = []
    acquired, identified = candidate_gains(held, candidates, pieces)
    if acquired:
        events.append(EVENT_CANDIDATE_GAINED)
    elif identified:
        events.append(EVENT_CANDIDATE_IDENTIFIED)
    finale, floor, rules, means = context
    held_finale, held_floor, held_rules, held_means = held.context
    if finale != held_finale:
        events.append(EVENT_FINALE_PHASE)
    # The destination's band moved (stage E4); leaving the town (no floor) decides nothing.
    if floor is not None and floor != held_floor:
        events.append(EVENT_DESTINATION_FLOOR)
    if rules != held_rules:
        events.append(EVENT_RULES)
    if any(now and not before for now, before in zip(means, held_means)):
        events.append(EVENT_DESTRUCTION_MEANS)
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


def identified_search_exclusion(held: VisitTarget, items, candidates: tuple, pieces: tuple,
                                usable_unidentified, curse_pinned_ids=frozenset()):
    """(the owned ids a ``candidate-identified`` decision leaves out of the search, the events
    that forbid it).

    The search keeps the held target's pieces and the pieces known better
    (``candidate_gains``' identified keys); every other owned piece is out.  A target piece is
    found by the identity a move keeps or, when *Identify* changed that identity, as a better-known
    piece of the same physical identity (n1-c life-220 07:45: the target's スピードの硬革ブーツ
    gained its {+速} from the *Identify* after the one that named it).  ``target-piece-lost``
    when a target piece is neither (owned no more: decides again as before); ``worn-curse-found``
    as ``mapped_visit_target``."""
    best = getattr(held.result, "best", None)
    loadout = getattr(best, "loadout", None)
    if not isinstance(loadout, Loadout):
        return None, (EVENT_TARGET_PIECE_LOST,)
    _acquired, identified = candidate_gains(held, candidates, pieces)
    better_known = [owned for owned in items
                    if (equipment_move_identity(owned.item), bool(usable_unidentified(owned)))
                    in identified]
    keep = {owned.id for owned in better_known}
    for _slot, piece in loadout.slots:
        identity = equipment_move_identity(piece.item)
        if any(equipment_move_identity(owned.item) == identity for owned in items):
            keep.update(owned.id for owned in items
                        if equipment_move_identity(owned.item) == identity)
        elif not any(_same_physical(stable_identity(piece.item), stable_identity(owned.item))
                     for owned in better_known):
            return None, (EVENT_TARGET_PIECE_LOST,)
    for owned in items:
        if (owned.id in curse_pinned_ids and owned.origin == "equipped"
                and owned.id not in keep):
            return None, (EVENT_WORN_CURSE,)
    return frozenset(owned.id for owned in items if owned.id not in keep), ()
