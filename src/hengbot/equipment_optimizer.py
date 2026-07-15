"""Exact complete-loadout search for town equipment decisions.

This module deliberately knows nothing about keyboard input or Home pages.  It
accepts a stable catalog of owned, fully identified items and enumerates every
legal complete loadout.  Combat arithmetic is supplied by a class-specific
evaluator so that the search cannot silently fall back to the old per-slot
heuristics while the Warrior formula is being completed.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from itertools import combinations, product
from math import isfinite
from time import monotonic
from typing import Callable, Iterable, Iterator

from hengbot.model import (
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_SHOT,
    InventoryItem,
    StoreItem,
    item_requires_full_identification,
)


EquipmentItem = InventoryItem | StoreItem
AMMUNITION_TVALS = frozenset({TVAL_SHOT, TVAL_ARROW, TVAL_BOLT})

SLOT_BOW = "bow"
SLOT_MAIN_HAND = "main_hand"
SLOT_SUB_HAND = "sub_hand"
SLOT_MAIN_RING = "main_ring"
SLOT_SUB_RING = "sub_ring"
SLOT_NECK = "neck"
SLOT_LIGHT = "light"
SLOT_BODY = "body"
SLOT_OUTER = "outer"
SLOT_HEAD = "head"
SLOT_ARMS = "arms"
SLOT_FEET = "feet"

FIXED_SLOTS = (
    SLOT_BOW,
    SLOT_NECK,
    SLOT_LIGHT,
    SLOT_BODY,
    SLOT_OUTER,
    SLOT_HEAD,
    SLOT_ARMS,
    SLOT_FEET,
)

TR_RES_ACID = 48
TR_RES_ELEC = 49
TR_RES_FIRE = 50
TR_RES_COLD = 51
TR_RES_POIS = 52
TR_RES_CONF = 57
TR_RES_NETHER = 60
TR_RES_CHAOS = 62
TR_NO_TELE = 68
TR_TELEPATHY = 79
TR_DRAIN_EXP = 89
TR_TELEPORT = 90
TR_AGGRAVATE = 91
TR_ADD_L_CURSE = 118
TR_ADD_H_CURSE = 119
TR_DRAIN_HP = 120
TR_CALL_ANIMAL = 128
TR_CALL_DEMON = 129
TR_CALL_DRAGON = 130
TR_CALL_UNDEAD = 131
TR_COWARDICE = 132
TR_BERS_RAGE = 149
TR_SELF_FIRE = 158
TR_SELF_ELEC = 159
TR_SELF_COLD = 160
TR_PERSISTENT_CURSE = 161

# Flags whose behavior makes an exploration loadout unusable for the present
# bot.  Temporary curse state is handled separately: such an item is held for
# uncursing and is not an optimization candidate until the curse is gone.
FORBIDDEN_EXPLORATION_FLAGS = frozenset(
    {
        TR_NO_TELE,
        71,  # TY_CURSE / ancient curse
        TR_DRAIN_EXP,
        TR_AGGRAVATE,
        TR_ADD_L_CURSE,
        TR_ADD_H_CURSE,
        TR_DRAIN_HP,
        TR_CALL_ANIMAL,
        TR_CALL_DEMON,
        TR_CALL_DRAGON,
        TR_CALL_UNDEAD,
        TR_COWARDICE,
        TR_BERS_RAGE,
        TR_SELF_FIRE,
        TR_SELF_ELEC,
        TR_SELF_COLD,
        TR_PERSISTENT_CURSE,
    }
)

# These flags have no selection or disposal value under the agreed policy.
IGNORED_DOMINANCE_FLAGS = frozenset(
    {
        9,  # SEARCH
        38,  # RIDING (the bot does not ride)
        72,  # WARNING
        80,  # SLOW_DIGEST
        81,  # REGEN
        84, 85, 86, 87,  # item elemental durability
    }
)

ABILITY_FLAG = {
    "resist_acid": TR_RES_ACID,
    "resist_elec": TR_RES_ELEC,
    "resist_fire": TR_RES_FIRE,
    "resist_cold": TR_RES_COLD,
    "resist_pois": TR_RES_POIS,
    "resist_conf": TR_RES_CONF,
    "resist_neth": TR_RES_NETHER,
    "resist_chaos": TR_RES_CHAOS,
    "telepathy": TR_TELEPATHY,
}


def required_abilities(depth: int) -> frozenset[str]:
    if 20 <= depth <= 25:
        return frozenset({"resist_conf", "resist_fire"})
    if 26 <= depth <= 30:
        return frozenset(
            {"resist_pois", "resist_cold", "resist_elec", "resist_acid"}
        )
    if 31 <= depth <= 39:
        return frozenset({"resist_chaos"})
    if 40 <= depth <= 49:
        return frozenset({"resist_chaos", "resist_neth"})
    if depth >= 50:
        return frozenset({"resist_chaos", "resist_neth", "telepathy"})
    return frozenset()


@dataclass(frozen=True)
class OwnedEquipment:
    """One physical item in the owned-equipment catalog."""

    id: str
    item: EquipmentItem
    origin: str  # equipped, pack, home, or store-simulation
    equipped_slot: str | None = None
    random_teleport_suppressed: bool = False

    @property
    def flags(self) -> frozenset[int]:
        return self.item.known_flags

    @property
    def evaluable(self) -> bool:
        if self.item.is_broken or self.item.is_cursed or not self.item.known:
            return False
        return not (
            item_requires_full_identification(self.item)
            and not self.item.fully_known
        )

    @property
    def identification_incomplete(self) -> bool:
        # An average pseudo-ID is intentionally not worth an Identify charge.
        # It remains illegal for exploration and is handled by the ordinary
        # sale/destruction path, but must not block optimization forever.
        if not self.item.known:
            return self.item.pseudo_feeling != "average"
        return (
            item_requires_full_identification(self.item)
            and not self.item.fully_known
        )

    @property
    def exploration_legal(self) -> bool:
        if not self.evaluable or self.flags.intersection(FORBIDDEN_EXPLORATION_FLAGS):
            return False
        return TR_TELEPORT not in self.flags or self.random_teleport_suppressed


@dataclass(frozen=True)
class HandConfiguration:
    main: OwnedEquipment | None
    sub: OwnedEquipment | None
    two_handed: bool = False

    @property
    def mode(self) -> str:
        if self.main is not None and self.sub is not None:
            return "dual_wield" if _is_weapon(self.sub.item) else "weapon_shield"
        if self.main is not None:
            return "two_handed" if self.two_handed else "one_handed"
        return "empty"


@dataclass(frozen=True)
class Loadout:
    slots: tuple[tuple[str, OwnedEquipment], ...]
    hand_mode: str

    def item_at(self, slot: str) -> OwnedEquipment | None:
        return next((item for name, item in self.slots if name == slot), None)

    @property
    def item_ids(self) -> frozenset[str]:
        return frozenset(item.id for _, item in self.slots)

    @property
    def flags(self) -> frozenset[int]:
        result: set[int] = set()
        for _, item in self.slots:
            result.update(item.flags)
        return frozenset(result)


@dataclass(frozen=True)
class LoadoutMetrics:
    expected_dps: float
    survival_turns: float
    combat_margin: float
    speed_bonus: int = 0
    secondary_value: float = 0.0
    relevant_traits: frozenset[str] = frozenset()
    evaluation_complete: bool = True


@dataclass(frozen=True)
class EvaluatedLoadout:
    loadout: Loadout
    metrics: LoadoutMetrics


@dataclass(frozen=True)
class OptimizationResult:
    best: EvaluatedLoadout | None
    alternatives: tuple[EvaluatedLoadout, ...]
    pareto_frontier: tuple[EvaluatedLoadout, ...]
    dominated_item_ids: frozenset[str]
    combinations_considered: int
    combinations_evaluated: int
    invalid_combinations: int
    elapsed_seconds: float
    timed_out: bool
    incomplete_item_ids: frozenset[str]
    search_truncated: bool = False


LoadoutEvaluator = Callable[[Loadout], LoadoutMetrics]


def _catalog_signature(item: EquipmentItem) -> tuple:
    """Player-visible identity used only to count physical duplicate items."""
    # Light-source display names include the remaining fuel (for example,
    # "Brass Lantern (8000 turns of light)"). Fuel drops on every movement,
    # but it does not change the item's loadout value. Using that volatile name
    # here invalidates the complete-loadout cache on every town step.
    stable_name = None if item.tval == 39 else item.name
    return (
        stable_name,
        item.tval,
        item.sval,
        item.count,
        item.known,
        item.fully_known,
        item.is_ego,
        item.is_artifact,
        item.is_cursed,
        item.is_broken,
        item.to_h,
        item.to_d,
        item.to_a,
        item.ac,
        item.damage_dice_num,
        item.damage_dice_sides,
        item.pval,
        tuple(sorted(item.known_flags)),
    )


def _catalog_digest(signature: tuple) -> str:
    return sha1(repr(signature).encode("utf-8")).hexdigest()[:16]


def equipment_identity(item: EquipmentItem) -> str:
    """Stable player-visible identity across pack, equipment, and Home moves.

    Physically identical duplicates intentionally share an identity. Transaction
    confirmation counts them instead of pretending the UI exposes which copy
    moved.
    """
    return _catalog_digest(_catalog_signature(item))


class OwnedEquipmentCatalog:
    """Persistent carried gear plus a wrap-detected scan of every Home page."""

    def __init__(self) -> None:
        self._carried: dict[str, OwnedEquipment] = {}
        self._home: dict[str, OwnedEquipment] = {}
        self._home_seen_pages: set[tuple[tuple, ...]] = set()
        self._home_occurrences: dict[tuple, int] = {}
        self.home_scan_complete = False

    def refresh_carried(
        self,
        inventory: Iterable[InventoryItem],
        equipment: Iterable[InventoryItem],
    ) -> None:
        carried: dict[str, OwnedEquipment] = {}
        occurrences: dict[tuple[str, tuple], int] = {}
        for origin, items in (("pack", inventory), ("equipped", equipment)):
            for item in items:
                if not item.is_equipment or item.tval in AMMUNITION_TVALS:
                    continue
                signature = _catalog_signature(item)
                occurrence_key = (origin, signature)
                occurrence = occurrences.get(occurrence_key, 0)
                occurrences[occurrence_key] = occurrence + 1
                item_id = f"{origin}:{_catalog_digest(signature)}:{occurrence}"
                carried[item_id] = OwnedEquipment(
                    item_id,
                    item,
                    origin,
                    equipped_slot=item.slot if origin == "equipped" else None,
                    # Random teleport requires an explicit inscription/verification
                    # transaction.  A display-name guess is not sufficient proof.
                    random_teleport_suppressed=False,
                )
        self._carried = carried

    def observe_home_page(self, items: Iterable[StoreItem]) -> bool:
        """Record one page; return True after the page sequence wraps."""
        page_items = tuple(
            item
            for item in items
            if item.is_equipment and item.tval not in AMMUNITION_TVALS
        )
        page = tuple(_catalog_signature(item) for item in page_items)
        if page in self._home_seen_pages:
            self.home_scan_complete = True
            return True
        self._home_seen_pages.add(page)
        for item, signature in zip(page_items, page):
            occurrence = self._home_occurrences.get(signature, 0)
            self._home_occurrences[signature] = occurrence + 1
            item_id = f"home:{_catalog_digest(signature)}:{occurrence}"
            self._home[item_id] = OwnedEquipment(item_id, item, "home")
        return False

    def invalidate_home(self) -> None:
        self._home.clear()
        self._home_seen_pages.clear()
        self._home_occurrences.clear()
        self.home_scan_complete = False

    @property
    def items(self) -> tuple[OwnedEquipment, ...]:
        return tuple((*self._carried.values(), *self._home.values()))


def current_loadout(items: Iterable[OwnedEquipment]) -> Loadout:
    """Reconstruct the currently worn loadout from a catalog snapshot."""
    slots = tuple(
        sorted(
            (
                (item.equipped_slot, item)
                for item in items
                if item.origin == "equipped" and item.equipped_slot is not None
            ),
            key=lambda entry: entry[0],
        )
    )
    by_slot = dict(slots)
    main = by_slot.get(SLOT_MAIN_HAND)
    sub = by_slot.get(SLOT_SUB_HAND)
    if main is not None and sub is not None:
        hand_mode = "weapon_shield" if _is_shield(sub.item) else "dual_wield"
    elif main is not None:
        hand_mode = (
            "two_handed"
            if main.item.tval == 22 or main.item.weight > 99
            else "one_handed"
        )
    else:
        hand_mode = "empty"
    return Loadout(slots, hand_mode)


def slot_for(item: EquipmentItem) -> str | None:
    return {
        19: SLOT_BOW,
        30: SLOT_FEET,
        31: SLOT_ARMS,
        32: SLOT_HEAD,
        33: SLOT_HEAD,
        35: SLOT_OUTER,
        36: SLOT_BODY,
        37: SLOT_BODY,
        38: SLOT_BODY,
        39: SLOT_LIGHT,
        40: SLOT_NECK,
    }.get(item.tval)


def _is_weapon(item: EquipmentItem) -> bool:
    # TV_DIGGING (20) occupies a hand while mining, but it is not a combat
    # weapon. Including it here lets the optimizer equip a shovel, while the
    # town re-arm gate immediately restores a real weapon, creating a cycle.
    return item.tval in {21, 22, 23}


def _is_shield(item: EquipmentItem) -> bool:
    return item.tval == 34


def _is_ring(item: EquipmentItem) -> bool:
    return item.tval == 45


def hand_configurations(items: Iterable[OwnedEquipment]) -> Iterator[HandConfiguration]:
    weapons = [item for item in items if _is_weapon(item.item)]
    shields = [item for item in items if _is_shield(item.item)]

    yield HandConfiguration(None, None)
    for weapon in weapons:
        # Hengband automatically uses both free hands for polearms and weapons
        # over 9.9 lb.  Lighter non-polearms remain genuinely one-handed.
        if weapon.item.tval == 22 or weapon.item.weight > 99:
            yield HandConfiguration(weapon, None, True)
        else:
            yield HandConfiguration(weapon, None, False)
        for shield in shields:
            yield HandConfiguration(weapon, shield)
    for main, sub in combinations(weapons, 2):
        yield HandConfiguration(main, sub)
        yield HandConfiguration(sub, main)


def _ring_configurations(items: Iterable[OwnedEquipment]) -> Iterator[tuple[OwnedEquipment, ...]]:
    rings = [item for item in items if _is_ring(item.item)]
    yield ()
    for ring in rings:
        yield (ring,)
    yield from combinations(rings, 2)


def enumerate_loadouts(items: Iterable[OwnedEquipment]) -> Iterator[Loadout]:
    """Enumerate every legal slot/hand assignment without quality pruning."""
    legal = [item for item in items if item.exploration_legal]
    pools: list[tuple[OwnedEquipment | None, ...]] = []
    for slot in FIXED_SLOTS:
        candidates = tuple(item for item in legal if slot_for(item.item) == slot)
        pools.append((None, *candidates))

    for fixed, hands, rings in product(
        product(*pools), hand_configurations(legal), _ring_configurations(legal)
    ):
        assigned: list[tuple[str, OwnedEquipment]] = [
            (slot, item)
            for slot, item in zip(FIXED_SLOTS, fixed)
            if item is not None
        ]
        if hands.main is not None:
            assigned.append((SLOT_MAIN_HAND, hands.main))
        if hands.sub is not None:
            assigned.append((SLOT_SUB_HAND, hands.sub))
        if rings:
            assigned.append((SLOT_MAIN_RING, rings[0]))
        if len(rings) == 2:
            assigned.append((SLOT_SUB_RING, rings[1]))
        yield Loadout(tuple(assigned), hands.mode)


def _meets_requirements(
    loadout: Loadout,
    metrics: LoadoutMetrics,
    *,
    depth: int,
    intrinsic_abilities: frozenset[str],
    has_destruction: bool,
) -> bool:
    if not metrics.evaluation_complete:
        return False
    if not _meets_static_requirements(
        loadout,
        depth=depth,
        intrinsic_abilities=intrinsic_abilities,
        has_destruction=has_destruction,
    ):
        return False
    if depth >= 81 and metrics.speed_bonus < 25:
        return False
    return True


def _meets_static_requirements(
    loadout: Loadout,
    *,
    depth: int,
    intrinsic_abilities: frozenset[str],
    has_destruction: bool,
) -> bool:
    """Reject loadouts whose failure does not depend on combat evaluation."""
    if loadout.item_at(SLOT_LIGHT) is None:
        return False
    abilities = set(intrinsic_abilities)
    for name, flag in ABILITY_FLAG.items():
        if flag in loadout.flags:
            abilities.add(name)
    if not required_abilities(depth).issubset(abilities):
        return False
    if depth >= 50 and not has_destruction:
        return False
    return True


def _pareto_dominates(left: EvaluatedLoadout, right: EvaluatedLoadout) -> bool:
    lm = left.metrics
    rm = right.metrics
    left_traits = lm.relevant_traits
    right_traits = rm.relevant_traits
    no_worse = (
        lm.expected_dps >= rm.expected_dps
        and lm.survival_turns >= rm.survival_turns
        and lm.combat_margin >= rm.combat_margin
        and lm.speed_bonus >= rm.speed_bonus
        and lm.secondary_value >= rm.secondary_value
        and left_traits.issuperset(right_traits)
    )
    strictly_better = (
        lm.expected_dps > rm.expected_dps
        or lm.survival_turns > rm.survival_turns
        or lm.combat_margin > rm.combat_margin
        or lm.speed_bonus > rm.speed_bonus
        or lm.secondary_value > rm.secondary_value
        or left_traits > right_traits
    )
    return no_worse and strictly_better


def _prefer(
    candidate: EvaluatedLoadout,
    incumbent: EvaluatedLoadout,
    current_item_ids: frozenset[str],
) -> bool:
    cm = candidate.metrics
    im = incumbent.metrics
    if not isfinite(cm.combat_margin) or not isfinite(im.combat_margin):
        if cm.combat_margin != im.combat_margin:
            return cm.combat_margin > im.combat_margin
        if cm.secondary_value != im.secondary_value:
            return cm.secondary_value > im.secondary_value
        candidate_is_current = candidate.loadout.item_ids == current_item_ids
        incumbent_is_current = incumbent.loadout.item_ids == current_item_ids
        return candidate_is_current and not incumbent_is_current
    threshold = abs(im.combat_margin) * 0.01
    difference = cm.combat_margin - im.combat_margin
    if difference > threshold:
        return True
    if difference < -threshold:
        return False
    if cm.secondary_value != im.secondary_value:
        return cm.secondary_value > im.secondary_value
    candidate_is_current = candidate.loadout.item_ids == current_item_ids
    incumbent_is_current = incumbent.loadout.item_ids == current_item_ids
    return candidate_is_current and not incumbent_is_current


def optimize_loadout(
    items: Iterable[OwnedEquipment],
    evaluator: LoadoutEvaluator,
    *,
    depth: int,
    intrinsic_abilities: frozenset[str] = frozenset(),
    has_destruction: bool = False,
    current_item_ids: frozenset[str] = frozenset(),
    timeout_seconds: float = 5.0,
    candidate_loadouts: Iterable[Loadout] | None = None,
) -> OptimizationResult:
    """Find the best complete loadout, failing closed if exact search times out."""
    catalog = tuple(items)
    incomplete = frozenset(
        item.id for item in catalog if item.identification_incomplete
    )
    started = monotonic()
    # An incomplete catalog can never produce an actionable result. Avoid an
    # expensive exact search whose partial answer prepare_warrior_optimization
    # must discard anyway; town processing first needs to identify or uncurse
    # every owned candidate.
    if incomplete:
        return OptimizationResult(
            best=None,
            alternatives=(),
            pareto_frontier=(),
            dominated_item_ids=frozenset(),
            combinations_considered=0,
            combinations_evaluated=0,
            invalid_combinations=0,
            elapsed_seconds=monotonic() - started,
            timed_out=False,
            incomplete_item_ids=incomplete,
        )
    considered = evaluated_count = invalid = 0
    evaluated: list[EvaluatedLoadout] = []
    frontier: list[EvaluatedLoadout] = []
    timed_out = False

    loadouts = enumerate_loadouts(catalog) if candidate_loadouts is None else candidate_loadouts
    for loadout in loadouts:
        if timeout_seconds <= 0 or monotonic() - started > timeout_seconds:
            timed_out = True
            break
        considered += 1
        if not _meets_static_requirements(
            loadout,
            depth=depth,
            intrinsic_abilities=intrinsic_abilities,
            has_destruction=has_destruction,
        ):
            invalid += 1
            continue
        metrics = evaluator(loadout)
        if not _meets_requirements(
            loadout,
            metrics,
            depth=depth,
            intrinsic_abilities=intrinsic_abilities,
            has_destruction=has_destruction,
        ):
            invalid += 1
            continue
        entry = EvaluatedLoadout(loadout, metrics)
        evaluated.append(entry)
        evaluated_count += 1
        if any(_pareto_dominates(other, entry) for other in frontier):
            continue
        frontier = [
            other for other in frontier if not _pareto_dominates(entry, other)
        ]
        frontier.append(entry)

    # A partial result is never safe to act on: timeout means stop town departure.
    if timed_out:
        best = None
        frontier = []
    else:
        # Operational selection applies the 1% anti-churn threshold to every
        # viable loadout.  The strict Pareto frontier is retained separately for
        # storage/disposal; using it here would discard the current loadout for a
        # mathematically positive but operationally insignificant 0.5% gain.
        best = None
        for candidate in evaluated:
            if best is None or _prefer(candidate, best, current_item_ids):
                best = candidate

    alternatives = tuple(
        sorted(
            frontier,
            key=lambda entry: (
                entry.metrics.combat_margin,
                entry.metrics.secondary_value,
            ),
            reverse=True,
        )[:5]
    )

    # Disposal proof is deliberately separate from best-loadout selection. The
    # previous all-loadouts-by-all-loadouts proof was cubic at terminal Home
    # sizes. Until a conservative slot-local proof is available, retaining an
    # uncertain item at Home is the agreed safe behavior.
    dominated_ids: set[str] = set()

    return OptimizationResult(
        best=best,
        alternatives=alternatives,
        pareto_frontier=tuple(frontier),
        dominated_item_ids=frozenset(dominated_ids),
        combinations_considered=considered,
        combinations_evaluated=evaluated_count,
        invalid_combinations=invalid,
        elapsed_seconds=monotonic() - started,
        timed_out=timed_out,
        incomplete_item_ids=incomplete,
        search_truncated=bool(getattr(candidate_loadouts, "truncated", False)),
    )
