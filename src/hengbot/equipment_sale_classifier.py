"""Observation-only equipment sale classification; emits no game commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Iterable, Mapping

from hengbot.equipment_optimizer import (
    ABILITY_FLAG, EquipmentItem, EvaluatedLoadout, LoadoutEvaluator, OwnedEquipment,
    SLOT_MAIN_HAND, SLOT_MAIN_RING, SLOT_SUB_HAND, SLOT_SUB_RING, _prefer, current_loadout,
    launcher_is_high_grade, optimize_loadout, slot_for, usable_light_candidate,
)
from hengbot.launcher_damage import best_obtainable_launcher_damage, launcher_dominates
from hengbot.model import (
    PLAYER_CLASS_WARRIOR, SV_DRAGON_SHIELD,
    SV_PAIR_OF_DRAGON_GREAVE, item_requires_full_identification,
)
from hengbot.policy_constants import (
    HOME_SALE_FREE_SLOT_TARGET, HOME_SALE_KEEP_TOP_ALWAYS,
    HOME_SALE_KEEP_TOP_WHEN_SPACE,
)
from hengbot.warrior_loadout_search import (
    BENEFICIAL_GEAR_FLAGS, WarriorSingleSlotSearch, _loadout_value_signature,
    _slot_capacity, disposable_dominated_item_ids,
)


@dataclass(frozen=True)
class EquipmentSaleClassification:
    sold_ids: frozenset[str]
    pareto_ids: frozenset[str]
    needs_identification_ids: frozenset[str]
    reasons: Mapping[str, str]
    dominators: Mapping[str, tuple[str, ...]]
    blockers: tuple[str, ...] = ()
    # The optimizer's per-slot result lets the Home pressure policy choose its
    # fallback in a stable weakest-first order without inventing a second score.
    performance: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    eligible_ids: frozenset[str] = frozenset()
    # Slot-local, best-first ranks include protected items when they can be
    # scored. They still occupy a keep position, as required by the 2026-10-08
    # sale rule.
    ranks: Mapping[str, int] = field(default_factory=dict)


def equipment_sale_fallback_order(
    classification: EquipmentSaleClassification,
    *,
    excluded_ids: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Return safe classified candidates weakest-first with an ID tie-break."""
    candidates = classification.eligible_ids - classification.sold_ids - excluded_ids
    return tuple(sorted(
        candidates,
        key=lambda item_id: (
            classification.performance.get(item_id, (float("inf"), float("inf"))),
            item_id,
        ),
    ))


def equipment_sale_plan(
    classification: EquipmentSaleClassification,
    *,
    home_ids: frozenset[str],
    free_home_slots: int,
    target_free_slots: int = HOME_SALE_FREE_SLOT_TARGET,
) -> tuple[str, ...]:
    """Apply permanent rank-21 sales, J-D sales, then pressure fallback."""
    rank = classification.ranks
    selected_ids = {
        item_id for item_id in classification.sold_ids
        if rank.get(item_id, 0) > HOME_SALE_KEEP_TOP_ALWAYS
    }
    selected_ids.update(
        item_id for item_id, item_rank in rank.items()
        if item_rank > HOME_SALE_KEEP_TOP_WHEN_SPACE
        and item_id in classification.eligible_ids
    )
    selected = sorted(selected_ids)
    # Rank-21+ items are sold even when Home already has room, and their
    # projected slots count toward the target.
    projected = free_home_slots + len(home_ids & selected_ids)
    if projected >= target_free_slots:
        return tuple(selected)
    already = frozenset(selected)
    for item_id in equipment_sale_fallback_order(
        classification, excluded_ids=already,
    ):
        item_rank = rank.get(item_id, 0)
        if not HOME_SALE_KEEP_TOP_ALWAYS < item_rank <= HOME_SALE_KEEP_TOP_WHEN_SPACE:
            continue
        selected.append(item_id)
        if item_id in home_ids:
            projected += 1
        if projected >= target_free_slots:
            break
    return tuple(selected)


def equipment_sale_scope(owned: OwnedEquipment, scope: str) -> bool:
    item = owned.item
    armour_or_weapon = item.tval in {19, 21, 22, 23, 30, 31, 32, 33, 34, 35, 36, 37, 38}
    if armour_or_weapon and (item.is_ego or item.pseudo_feeling == "excellent"):
        return True
    return scope == "J" and (
        (item.tval in {40, 45} and not item.is_ego and bool(item.known_flags or item.pval
                                     or item.to_h or item.to_d or item.to_a))
        or item.tval == 38
        or (item.tval, item.sval) in {(34, SV_DRAGON_SHIELD), (30, SV_PAIR_OF_DRAGON_GREAVE)}
    )


def _sale_slot(owned: OwnedEquipment) -> str | None:
    # slot_for leaves the two hand/ring classes to hand_configurations and
    # _slot_choices. Use those same classes, with their existing capacities.
    if owned.item.tval in {21, 22, 23}:
        return SLOT_MAIN_HAND
    if owned.item.tval == 45:
        return SLOT_MAIN_RING
    if owned.item.tval == 34:
        return "sub_hand"
    return slot_for(owned.item)


def classify_equipment_sales(
    items: Iterable[OwnedEquipment],
    evaluator: LoadoutEvaluator,
    *,
    class_id: int,
    home_scan_complete: bool,
    catalogue_current: bool,
    scope: str = "E",
    duplicates: str = "S",
    reserved_ids: frozenset[str] = frozenset(),
    intrinsic_abilities: frozenset[str] = frozenset(),
    has_destruction: bool = False,
    obtainable_ammunition: Iterable[EquipmentItem] = (),
    timeout_seconds: float = 25.0,
) -> EquipmentSaleClassification:
    """Prove surplus against retained owned copies in the current character.

    Scores are actual single-slot trials of the confirmed worn set, using the
    optimizer's hand legality and preference. Required abilities, resistances,
    slays and brands must also be covered by each retained dominator.
    ``reserved_ids`` is supplied by the policy's existing ownership authorities.
    No scope choice is installed in the live policy by this measurement API.
    """
    if scope not in {"E", "J"} or duplicates not in {"S", "D"}:
        raise ValueError("scope must be E/J and duplicates S/D")
    catalog = tuple(items)
    ammunition = tuple(obtainable_ammunition)
    unknown = frozenset(
        owned.id for owned in catalog
        if not owned.item.known or owned.identification_incomplete
        or (item_requires_full_identification(owned.item) and not owned.item.fully_known)
    )
    reasons: dict[str, str] = {}
    protected = set(reserved_ids)
    for owned in catalog:
        if owned.item.is_artifact:
            reasons[owned.id] = "artifact"
        elif owned.id in unknown:
            reasons[owned.id] = "needs-identification"
        elif owned.id in reserved_ids or owned.item.is_torch or usable_light_candidate(owned):
            reasons[owned.id] = "reservation-or-light"
        elif owned.origin == "equipped":
            reasons[owned.id] = "current-loadout"
        elif not owned.exploration_legal or _sale_slot(owned) is None:
            reasons[owned.id] = "unevaluable-or-illegal"
        elif not equipment_sale_scope(owned, scope):
            reasons[owned.id] = "outside-scope"
        if owned.id in reasons:
            protected.add(owned.id)
    blockers = tuple(reason for blocked, reason in (
        (class_id != PLAYER_CLASS_WARRIOR, "unsupported-class"),
        (not home_scan_complete, "home-scan-incomplete"),
        (not catalogue_current, "stale-catalogue"),
    ) if blocked)
    if blockers:
        return EquipmentSaleClassification(
            frozenset(), frozenset(), unknown, reasons, {}, blockers, {}, frozenset(),
        )

    current = current_loadout(catalog)
    pinned = {slot: owned for slot, owned in current.slots if owned.item.is_cursed}
    # Do not lose a dominated item before scoring it: each trial is generated
    # from the worn set plus that one physical spare, and protects its identity.
    scores: dict[str, EvaluatedLoadout] = {}
    trials = {current}
    for owned in catalog:
        if not owned.exploration_legal or owned.id in unknown:
            continue
        seed = tuple(item for item in catalog if item.id in current.item_ids or item.id == owned.id)
        slots = (_sale_slot(owned),)
        if owned.item.tval == 45:
            slots = (SLOT_MAIN_RING, SLOT_SUB_RING)
        elif owned.item.tval in {21, 22, 23}:
            slots = (SLOT_MAIN_HAND, SLOT_SUB_HAND)
        searches = (
            WarriorSingleSlotSearch(seed, current.item_ids | {owned.id}, {**pinned, slot: owned})
            for slot in slots if slot not in pinned or pinned[slot].id == owned.id
        )
        loadouts = (current,) if owned.id in current.item_ids else (
            loadout for search in searches for loadout in search
        )
        for loadout in loadouts:
            trials.add(loadout)
            if owned.id not in loadout.item_ids:
                continue
            entry = EvaluatedLoadout(loadout, evaluator(loadout))
            if not entry.metrics.evaluation_complete:
                continue
            incumbent = scores.get(owned.id)
            if incumbent is None or _prefer(entry, incumbent, frozenset()):
                scores[owned.id] = entry

    # Include normal optimized neighbours as well as individually protected
    # trials. The latter keep resistance-swap candidates visible to every band.
    trials.update(WarriorSingleSlotSearch(catalog, current.item_ids, pinned))
    result = optimize_loadout(
        catalog, evaluator, depth=None, current_item_ids=current.item_ids,
        candidate_loadouts=sorted(trials, key=lambda loadout: (sorted(loadout.item_ids), loadout.hand_mode)),
        intrinsic_abilities=intrinsic_abilities, has_destruction=has_destruction,
        obtainable_ammunition=ammunition, timeout_seconds=timeout_seconds,
    )
    if result.timed_out or result.search_truncated or result.best is None:
        return EquipmentSaleClassification(
            frozenset(), frozenset(), unknown, reasons, {},
            ("optimization-incomplete",), {}, frozenset(),
        )
    for entry in (result.best, *result.band_best_loadouts):
        for item_id in entry.loadout.item_ids - protected:
            reasons[item_id] = "optimizer-or-band-winner"
            protected.add(item_id)

    # Scope limits which identities may be sold and ranked, while protected
    # identities inside that scope still consume a rank.
    eligible = tuple(
        owned for owned in catalog
        if owned.id in scores and equipment_sale_scope(owned, scope)
    )
    damage = {owned.id: best_obtainable_launcher_damage(owned.item, ammunition)
              for owned in eligible if owned.item.tval == 19}
    # IDs are stable physical-copy identifiers. Protection precedes IDs so a
    # D duplicate always keeps worn/reserved/winner copies before surplus ones.
    copy_order = {owned.id: (owned.id not in protected, owned.id) for owned in catalog}
    cover_flags = BENEFICIAL_GEAR_FLAGS | frozenset(ABILITY_FLAG.values()) | frozenset(range(48, 64))

    def dominates(left: OwnedEquipment, right: OwnedEquipment) -> bool:
        if left.id == right.id or _sale_slot(left) != _sale_slot(right):
            return False
        if not (left.flags & cover_flags).issuperset(right.flags & cover_flags):
            return False
        # Unmodeled/adverse flags cannot be interpreted as a safe upgrade.
        if left.flags - BENEFICIAL_GEAR_FLAGS != right.flags - BENEFICIAL_GEAR_FLAGS:
            return False
        identical = _loadout_value_signature(left) == _loadout_value_signature(right)
        if identical:
            if left.item.tval == 19 and (
                left.item.ammo_tval is None or left.item.ammo_tval != right.item.ammo_tval
                or (int(left.item.is_artifact), int(launcher_is_high_grade(left.item)))
                < (int(right.item.is_artifact), int(launcher_is_high_grade(right.item)))
            ):
                return False
            return duplicates == "D" and copy_order[left.id] < copy_order[right.id]
        if left.item.tval == 19:
            return launcher_dominates(left.item, right.item, damage[left.id], damage[right.id])
        a, b = scores[left.id], scores[right.id]
        strictly_preferred = _prefer(a, b, frozenset()) and not _prefer(b, a, frozenset())
        equal_score = (a.metrics.combat_margin, a.metrics.secondary_value) == (
            b.metrics.combat_margin, b.metrics.secondary_value,
        )
        return strictly_preferred or (equal_score and left.flags & BENEFICIAL_GEAR_FLAGS > right.flags & BENEFICIAL_GEAR_FLAGS)

    witnesses = {owned.id: tuple(other.id for other in eligible if dominates(other, owned))
                 for owned in eligible}
    # Same retained-witness capacity rule as disposable_dominated_item_ids:
    # never sell the witnesses needed to justify another sale in this batch.
    retained = frozenset(owned.id for owned in catalog if owned.id in protected
                        or len(witnesses.get(owned.id, ())) < _slot_capacity(owned))
    sold = frozenset(owned.id for owned in eligible if owned.id not in protected
                     and len(set(witnesses[owned.id]) & retained) >= _slot_capacity(owned))
    for owned in catalog:
        reasons.setdefault(owned.id, "dominated" if owned.id in sold else "slot-capacity-or-uncovered-trait")
    # Compare exactly the existing strict Pareto proof under the same safety
    # and scope guards; D's physical-copy rule intentionally adds no R1 proof.
    pareto = disposable_dominated_item_ids(eligible, frozenset(protected))
    # Rank every scoreable physical item by its best single-slot evaluation.
    # Stable IDs break exact ties; protected equipment remains in the ranking.
    grouped: dict[str, list[str]] = {}
    for owned in eligible:
        if owned.id in scores:
            grouped.setdefault(_sale_slot(owned) or "", []).append(owned.id)
    ranks: dict[str, int] = {}

    def compare_score(left_id: str, right_id: str) -> int:
        left, right = scores[left_id], scores[right_id]
        left_preferred = _prefer(left, right, frozenset())
        right_preferred = _prefer(right, left, frozenset())
        if left_preferred != right_preferred:
            return -1 if left_preferred else 1
        return (left_id > right_id) - (left_id < right_id)

    for ids in grouped.values():
        for rank, item_id in enumerate(sorted(
            ids, key=cmp_to_key(compare_score),
        ), start=1):
            ranks[item_id] = rank

    return EquipmentSaleClassification(
        sold, pareto, unknown, reasons,
        {item_id: tuple(w for w in witnesses[item_id] if w in retained) for item_id in sold},
        (),
        {item_id: (entry.metrics.combat_margin, entry.metrics.secondary_value)
         for item_id, entry in scores.items()},
        frozenset(owned.id for owned in eligible if owned.id not in protected),
        ranks,
    )
