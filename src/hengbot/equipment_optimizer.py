"""Exact complete-loadout search for town equipment decisions.

This module deliberately knows nothing about keyboard input or Home pages.  It
accepts a stable catalog of owned, fully identified items and enumerates every
legal complete loadout.  Combat arithmetic is supplied by a class-specific
evaluator so that the search cannot silently fall back to the old per-slot
heuristics while the Warrior formula is being completed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cmp_to_key
from hashlib import sha1
import re
from itertools import combinations, product
from math import isfinite
from time import monotonic
from typing import Callable, Iterable, Iterator, Mapping

from hengbot import me_power_success, torch_release
from hengbot.item_identity import without_player_inscription
from hengbot.model import (
    ARMOUR_TVALS,
    BAD_PSEUDO_FEELINGS,
    SV_LITE_FEANOR,
    SV_LITE_LANTERN,
    TVAL_AMULET,
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_BOW,
    TVAL_DIGGING,
    TVAL_HAFTED,
    TVAL_LITE,
    TVAL_POLEARM,
    TVAL_RING,
    TVAL_SHOT,
    TVAL_SWORD,
    InventoryItem,
    StoreItem,
    flag_light_radius,
    item_requires_full_identification,
    lights_nothing,
)
from hengbot.speed_valuation import (
    BASE_SPEED,
    field_strong_speed_energy,
    loadout_speed,
    meets_speed_gate,
    time_device,
    time_melee,
    time_ranged,
    weighted_margin,
)
from hengbot.policy_constants import (
    DEEP_FLOOR_DEPTH,
    SPEED_GATE_DEPTH,
)
from hengbot.equipment_rules import (
    DEPTH_ABILITY_REQUIREMENTS,
    EXPLORATION_FORBIDDEN_FLAGS,
    LIGHT_CROSSBOW_SVAL,
    TR_NO_TELE,
    launcher_is_high_grade,
    ordinary_launcher_yields_to_light_crossbow,
    required_abilities_for_depth,
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

# USER DECISION 2026-09-29 「空いた鎧の欄は必ず埋める」, generalised from the
# body slot (``require_body``) to the other armour slots on 2026-10-02.  The
# shield is a hand configuration (sub_hand) and is deliberately not listed.
FILL_REQUIRED_ARMOR_SLOTS = (SLOT_OUTER, SLOT_HEAD, SLOT_ARMS, SLOT_FEET)

TR_FREE_ACT = 46
TR_RES_ACID = 48
TR_RES_ELEC = 49
TR_RES_FIRE = 50
TR_RES_COLD = 51
TR_RES_POIS = 52
TR_RES_CONF = 57
TR_RES_NETHER = 60
TR_RES_CHAOS = 62
TR_TELEPATHY = 79
TR_TELEPORT = 90


# The exploration ban is equipment_rules.EXPLORATION_FORBIDDEN_FLAGS (the one table of the
# owner's equipment rules).

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
    "free_action": TR_FREE_ACT,
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


_INSCRIPTION_BLOCK = re.compile(r"\{[^{}]*\.[^{}]*\}")


# PlayerMutationType::BAD_LUCK (src/mutation/mutation-flag-types.h): with it a
# pseudo-ID feeling is swapped 1 time in 13 (simple-perception.cpp
# sense_inventory_aux), so {average} may hide a cursed item.
MUTATION_BAD_LUCK = 92
# BAD_PSEUDO_FEELINGS (model): such an item is never worn unidentified.
# The bot's own in-game inscription on equipment it picked up on the Q34 floor
# (owner 2026-10-31: 「Q34で拾った品を覚える必要があるなら銘を刻むこと」).
Q34_ITEM_TAG = "Q34"
# Weapons held in the hands (melee weapons, diggers and launchers): a Q34 one is
# wielded only once identified (owner 2026-11-09 「Q34の武器は未鑑定で握らない」).
Q34_WIELD_IDENTIFY_FIRST_TVALS = frozenset({
    TVAL_BOW, TVAL_DIGGING, TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD})
_Q34_TAG = re.compile(r"(?<![0-9A-Za-z])Q34(?![0-9A-Za-z])")


def average_feeling_trusted(mutation_signature: Iterable[int] | None) -> bool:
    """Owner Q-B (2026-10-22): trust {average} only without bad luck on screen.

    「戦士の重い擬似鑑定の {並} を、壊すための鑑定の代わりにしてよい（不運の
    突然変異が無いと画面で確かめられる時だけ）」.  ``mutation_signature`` is the
    mutation list of the last ``C`` screen; ``None`` (not seen yet) is not
    trusted.  Owner 2026-10-31 applies the same condition to wearing an
    unidentified {average} light (「並なら付けて良い」).
    """
    return (mutation_signature is not None
            and MUTATION_BAD_LUCK not in tuple(mutation_signature))


def average_hides_modifiers(item: EquipmentItem) -> bool:
    """An unidentified ring or amulet sensed {average}: its numbers stay hidden.

    pseudo_value_check_heavy (perception/simple-perception.cpp) answers
    FEEL_AVERAGE for every uncursed, non-ego ring or amulet without reading its
    values; a Ring of Constitution always has pval >= 1 (apply-magic-ring.cpp).
    n1-c life-130 2026-11-04 15:21: an Eldritch Horror's lose_all_info took the
    KNOWN flag of two rings of (+3) and (+4), they were sensed {average}, and
    the sheet's +9 CON refused every C screen (visible-modifier-mismatch).
    """
    return (not item.known and item.pseudo_feeling == "average"
            and item.tval in (TVAL_RING, TVAL_AMULET))


def average_feeling_uninformative(item: EquipmentItem) -> bool:
    """An unidentified item sensed {average} that the feeling tells nothing about.

    A ring or amulet (average_hides_modifiers) or a kind still unaware (its
    flavor not learnt): {average} reveals neither what it is nor its numbers.
    Owner 2026-11-06 「並で何も分からない品だけ — 指輪・首飾りと、種類がまだ
    分からない品は、並でも鑑定する」; a weapon, armour or light sensed
    {average} stays read as having no modifier.  n1-c life-146 10:58: the Q31
    reward ディリシウムの指輪 {並} and ダメージの指輪 {並} went to Home unidentified.
    """
    return (not item.known and item.pseudo_feeling == "average"
            and (average_hides_modifiers(item) or not getattr(item, "aware", True)))


def awaits_identification(item: EquipmentItem) -> bool:
    """An unidentified item that plain Identify still has something to reveal.

    The one {average} exemption every identification owner shares: an item
    sensed {average} is not worth an Identify charge, unless the feeling is
    uninformative (average_feeling_uninformative).
    """
    return not item.known and (item.pseudo_feeling != "average"
                               or average_feeling_uninformative(item))


def average_without_modifiers(item: EquipmentItem, trusted: bool) -> bool:
    """An unidentified item sensed {average}, read as having no modifier.

    Owner 2026-11-04 「修正なしとして使う」 for the C screen's worn gear, under
    the trust rule of average_feeling_trusted(): n1-b life-307 wore a Q34
    {average} cloak for its whole life and the sheet refused every C screen,
    so no optimizer compared its five carried weapons (pack-full-no-room).
    The feeling says nothing about jewellery (average_hides_modifiers).
    """
    return (trusted and not item.known and item.pseudo_feeling == "average"
            and not average_hides_modifiers(item))


def average_light_without_modifiers(item: EquipmentItem, trusted: bool) -> bool:
    """An unidentified light sensed {average} has no stat, AC or hit modifier.

    pseudo_value_check_heavy (perception/simple-perception.cpp) senses
    {average} only for an item that is no artifact or ego, not cursed or
    broken, with to_a <= 0 and to_h + to_d <= 0; every light base item that
    is not INSTA_ART has parameter_value 0 and no stat flag
    (lib/edit/BaseitemDefinitions.jsonc: torch, brass lantern, Feanorian
    lamp).  ``trusted`` is average_feeling_trusted() of the same C screen:
    bad luck can swap a feeling.  Owner 2026-10-31 wears such a light
    unidentified (「並なら付けて良い」), so the C screen can read its zero
    modifiers instead of refusing the calibration.
    """
    return item.tval == TVAL_LITE and average_without_modifiers(item, trusted)


def average_armour_without_modifiers(item: EquipmentItem, trusted: bool) -> bool:
    """An unidentified armour piece sensed {average}: its base AC and no modifier.

    pseudo_value_check_heavy (perception/simple-perception.cpp) senses
    {average} only for an item that is no artifact or ego, not cursed or
    broken, with to_a <= 0 and to_h + to_d <= 0; the name prints its base AC
    (model._item_base_ac).  Owner 2026-11-13: an unidentified {average}
    armour piece is rated with that base AC, to_a 0 and no flags, like the
    worn {average} gear of the C screen (2026-11-04 「修正なしとして使う」) and
    the {average} light worn unidentified (2026-10-31 「並なら付けて良い」).
    n1-c life-205 follow-up: an unidentified セスタス [5] {並} rated AC 0 was
    traded for a 革グローブ [1,+3].
    """
    return item.tval in ARMOUR_TVALS and average_without_modifiers(item, trusted)


def q34_item_tagged(item: EquipmentItem) -> bool:
    """Whether the item carries the bot's in-game ``Q34`` inscription."""
    return bool(_Q34_TAG.search(item.inscription or "")
                or any(_Q34_TAG.search(block)
                       for block in re.findall(r"\{[^{}]*\}", item.name)))


def random_teleport_is_suppressed(item: EquipmentItem) -> bool:
    """Return whether the player-visible inscription contains `{.}`.

    Hengband suppresses non-cursed random teleport when any inscription block
    contains a period. The emitter currently exposes that inscription through
    the display name, so require the period inside braces rather than accepting
    an unrelated period elsewhere in the item name.
    """
    return bool(_INSCRIPTION_BLOCK.search(item.name))


def required_abilities(depth: int) -> frozenset[str]:
    return required_abilities_for_depth(depth)


def destruction_means(loadout: "Loadout", has_destruction: bool, staff_gate) -> bool:
    """The 50F+ *Destruction* means with ``loadout`` worn: one that needs no
    equipment (``has_destruction``), or an owned staff this loadout's device
    skill makes reliable (owner 2026-11-15 「装備で魔法道具使用能力を向上させて杖の
    成功率を上げることで先に進むことができる」, device_skill.StaffGate)."""
    # The absorbed power is refused in a loadout with a worn NO_MAGIC (反魔法): the ``m`` command
    # itself (me_power_success.REFUSED_FAILURE; n1-b life-411 2026-11-21 04:55 arrived wearing
    # one, its 99 absorbed *Destruction* no means).
    absorbed = has_destruction and me_power_success.TR_NO_MAGIC not in loadout.flags
    return absorbed or (staff_gate is not None and staff_gate.opens(loadout))


def divable_depth(
    loadout: "Loadout",
    *,
    intrinsic_abilities: frozenset[str] = frozenset(),
    has_destruction: bool = False,
    player_speed: int = BASE_SPEED,
    staff_gate=None,
) -> int:
    """Classify a selected loadout into its deepest authoritative depth band.

    ``staff_gate`` (device_skill.StaffGate) is an owned *Destruction* staff that
    is a means at 50F+ only in a loadout giving its reliable device skill.
    ``player_speed`` is the loadout's permanent speed (speed_valuation.loadout_speed)."""
    abilities = set(intrinsic_abilities)
    for name, flag in ABILITY_FLAG.items():
        if flag in loadout.flags:
            abilities.add(name)
    bands = (*(first_floor for first_floor, _ in DEPTH_ABILITY_REQUIREMENTS), SPEED_GATE_DEPTH)
    deepest = bands[0] - 1
    for depth, next_band in zip(bands, (*bands[1:], SPEED_GATE_DEPTH + 1)):
        if not required_abilities(depth).issubset(abilities):
            break
        if depth >= DEEP_FLOOR_DEPTH and not destruction_means(
                loadout, has_destruction, staff_gate):
            break
        if depth >= SPEED_GATE_DEPTH and not meets_speed_gate(player_speed):
            break
        deepest = next_band - 1
    return deepest


@dataclass(frozen=True)
class OwnedEquipment:
    """One physical item in the owned-equipment catalog."""

    id: str
    item: EquipmentItem
    origin: str  # equipped, pack, home, or store-simulation
    equipped_slot: str | None = None
    random_teleport_suppressed: bool = False
    # average_feeling_trusted() of the catalog's last C screen (owner Q-B).
    average_feeling_trusted: bool = False

    @property
    def flags(self) -> frozenset[int]:
        return self.item.known_flags

    @property
    def unidentified_wear_allowed(self) -> bool:
        """An unidentified item the owner allows to be worn (2026-10-31).

        「並なら付けて良い。加えてQ34習得品も付けて良い。」: a light source
        sensed {average} while no bad luck is seen (Q-B), or an item inscribed
        ``Q34`` on the Q34 floor that is not sensed cursed or broken and is
        no weapon.  Owner 2026-11-09 「Q34の武器は未鑑定で握らない」 (Q34 で手に
        入れた武器（光源以外）は未鑑定では握らない): n1-b life-349 (2026-11-08
        20:02) wielded the unidentified Q34 タルワール, cursed (-4,-4), could
        not mine with it and had no gold for Remove Curse.  Every other
        unidentified item keeps the identify-first rule.
        """
        item = self.item
        if item.known or item.pseudo_feeling in BAD_PSEUDO_FEELINGS:
            return False
        if average_light_without_modifiers(item, self.average_feeling_trusted):
            return True
        if average_armour_without_modifiers(item, self.average_feeling_trusted):
            return True
        return item.tval not in Q34_WIELD_IDENTIFY_FIRST_TVALS and q34_item_tagged(item)

    @property
    def evaluable(self) -> bool:
        if self.item.is_broken or self.item.is_cursed:
            return False
        return self.item.known or self.unidentified_wear_allowed

    @property
    def identification_incomplete(self) -> bool:
        # An average pseudo-ID is intentionally not worth an Identify charge,
        # unless the feeling says nothing (awaits_identification).
        # It remains illegal for exploration and is handled by the ordinary
        # sale/destruction path, but must not block optimization forever.
        # An item the owner allows to be worn unidentified is evaluable.
        if not self.item.known:
            return (awaits_identification(self.item)
                    and not self.unidentified_wear_allowed)
        return (
            not self.item.fully_known
            and (
                self.item.is_cursed
                or item_requires_full_identification(self.item)
            )
        )

    @property
    def exploration_legal(self) -> bool:
        if not self.evaluable or self.flags.intersection(EXPLORATION_FORBIDDEN_FLAGS):
            return False
        if (
            not self.item.fully_known
            and item_requires_full_identification(self.item)
        ):
            return self.random_teleport_suppressed
        return TR_TELEPORT not in self.flags or self.random_teleport_suppressed


def operational_equipment_candidate(
    owned: OwnedEquipment, *, oil_carried: bool = False
) -> bool:
    """Reject a carried, visibly exhausted consumable light from loadout search.

    An empty lantern stays a candidate while oil is carried: the refill
    restores it, so it is not exhausted (#85).
    """
    item = owned.item
    return not (
        owned.origin in {"pack", "equipped"}
        and isinstance(item, InventoryItem)
        and item.is_light
        and item.sval <= SV_LITE_LANTERN
        and item.known
        and item.fuel <= 0
        and not (oil_carried and item.is_lantern)
    )


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


def light_source_quality(loadout: Loadout) -> int:
    """Rank operational light quality without making fuel a volatile input."""
    light = loadout.item_at(SLOT_LIGHT)
    if light is None:
        return -1
    if light.item.sval >= SV_LITE_FEANOR:
        return 2
    if light.item.sval == SV_LITE_LANTERN:
        return 1
    return 0


def permanent_light_radius(item: OwnedEquipment | None) -> int:
    """Known light radius of a permanent (fuel-free) light; 0 for others.

    USER DECISION 2026-10-19 「照らせる範囲も比べる」: among permanent lights
    the wider radius is preferred, below every modeled combat result.
    """
    if (
        item is None
        or item.item.tval != TVAL_LITE
        or item.item.sval < SV_LITE_FEANOR
    ):
        return 0
    return flag_light_radius(item.flags)


def worn_light_radius(items: Iterable[OwnedEquipment | None]) -> int:
    """Total light radius of the worn ``items`` (the one light-radius rule).

    USER DECISION 2026-10-23 「合計で比べる」: the optimizer compares the light
    radius of the whole loadout, not of the light source alone (#101: a worn
    闇の陣笠, TR_LITE_M1, turned the lamp's radius 2 into 1).

    update_lite_radius() (src/specific-object/torch.cpp) adds
    ItemEntity::get_lite_radius() (src/system/item/item-entity.cpp) of every
    worn item: +1/+2/+3 for TR_LITE_1/2/3 unless the item has TR_DARK_SOURCE,
    -1/-2/-3 for TR_LITE_M1/M2/M3.  A permanent light adds
    permanent_light_radius() (the #86 term); every other item adds its own
    flags.  Only known flags are read (fair play): an unidentified item's
    hidden flags are not guessed.

    Not counted here: fuel (a worn torch or lantern counts as burning; the
    supply and wield owners keep it fuelled, and the optimizer never makes
    fuel a selection input), the ego LITE_SHINE bonus (no flag on the board),
    and what belongs to the player or the floor rather than the items (the
    player's own light, timed emission, mimic forms, the DARKNESS dungeon cap
    and the 0..14 clamp; the clamp is left out so that one item's own
    darkness still counts when it is compared alone).
    """
    radius = 0
    for item in items:
        if item is None:
            continue
        if item.item.tval == TVAL_LITE and item.item.sval >= SV_LITE_FEANOR:
            radius += permanent_light_radius(item)
            continue
        radius += flag_light_radius(item.flags)
    return radius


def loadout_light_radius(loadout: Loadout) -> int:
    """Total light radius of ``loadout`` (worn_light_radius of its slots)."""
    return worn_light_radius(item for _, item in loadout.slots)


@dataclass(frozen=True)
class LoadoutMetrics:
    expected_dps: float
    survival_turns: float
    combat_margin: float
    ranged_dps: float = 0.0
    speed_bonus: int = 0
    secondary_value: float = 0.0
    relevant_traits: frozenset[str] = frozenset()
    evaluation_complete: bool = True
    # equipment_utility.utility_value: the telepathy / stealth bonus already
    # folded into combat_margin, kept for the tie-breaks.
    utility_value: float = 0.0
    # me_loadout_offense: the Magic-Eater's best absorbed attack power per
    # player turn under this loadout's INT (owner 2026-11-08); 0 for every
    # other class.  Compared like ranged_dps, right after it.
    device_dps: float = 0.0
    # The player's permanent speed with this loadout worn (base without gear
    # plus the gear's speed); None reads as +0 plus speed_bonus.  Read only
    # through speed_valuation.loadout_speed (owner 2026-11-17).
    player_speed: int | None = None
    # The absorbed Rockets' success percent under this loadout's INT (me_loadout_offense
    # ``finale_power_success``, the game's cmd-magiceat.cpp rate unstunned); None for every
    # class but the Magic-Eater.  Read by ``finale_rank`` only.
    finale_power_success: int | None = None


@dataclass(frozen=True)
class EvaluatedLoadout:
    loadout: Loadout
    metrics: LoadoutMetrics


# The depth bands of the descent, deepest first; a band reads the depth requirements of its
# deepest floor (81+, 50-80, 40-49, 31-39, 26-30, 21-25, 20, <=19; owner 2026-08-10).
DEPTH_BANDS = (81, 80, 49, 39, 30, 25, 20, 19)


@dataclass(frozen=True)
class BandDecision:
    """One inspectable step in an unconstrained depth-band descent."""

    band: int
    satisfying_set_existed: bool
    melee: float | None
    melee_free: float
    refusal_reason: str | None
    ratio: float | None
    # Adopted below the half-melee limit as the destination's band (destination_band_floor).
    destination_floor: bool = False


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
    top_candidates: tuple[EvaluatedLoadout, ...] = ()
    chosen_depth: int | None = None
    band_decisions: tuple[BandDecision, ...] = ()
    chosen_decision: BandDecision | None = None
    # Every valid set of the chosen band (the whole field without a band when
    # ``depth`` is given); empty after a timeout.  The single-slot closure
    # expands around its strongest-melee sets (melee_leaders).
    chosen_band_entries: tuple[EvaluatedLoadout, ...] = ()
    # The single-slot closure stopped at its whole-search time cap and this is
    # the last completed pass's result (warrior_optimization.CLOSURE_TIME_CAP_SECONDS).
    search_capped: bool = False


def melee_leaders(
    entries: Iterable[EvaluatedLoadout], count: int,
) -> tuple[EvaluatedLoadout, ...]:
    """The ``count`` sets with the most melee per game time among ``entries``
    that clear SUFFICIENT_SURVIVAL_TURNS (the sets that can anchor the 95% cut
    of _stable_operational_best), best first; ties by item ids."""
    eligible = [
        entry for entry in entries
        if entry.metrics.survival_turns >= SUFFICIENT_SURVIVAL_TURNS
    ]
    eligible.sort(key=lambda entry: (
        -time_melee(entry.metrics), tuple(sorted(entry.loadout.item_ids)),
        entry.loadout.hand_mode))
    return tuple(eligible[:count])


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


def _ammunition_key(item: EquipmentItem) -> tuple:
    """A Home ammunition stack's identity: the catalog signature without count."""
    signature = _catalog_signature(item)
    return signature[:3] + signature[4:]


def _catalog_digest(signature: tuple) -> str:
    return sha1(repr(signature).encode("utf-8")).hexdigest()[:16]


def equipment_identity(item: EquipmentItem) -> str:
    """Stable player-visible identity across pack, equipment, and Home moves.

    Physically identical duplicates intentionally share an identity. Transaction
    confirmation counts them instead of pretending the UI exposes which copy
    moved.
    """
    return _catalog_digest(_catalog_signature(item))


def _without_player_inscription(name: str, inscription: str) -> str:
    """The display name without the player's own inscription (item_identity reading)."""
    return without_player_inscription(name, inscription)


def equipment_move_identity(item: EquipmentItem) -> str:
    """Player-visible identity that stays stable while the item moves.

    A stack count moving between Home and the pack, and the player's own
    inscription (the random-teleport suppression's '.', the Q34 tag) leave
    the physical item the same: an open transaction still finds the item it
    planned (#47 D59, n1-c life-092 deposit-missing after the inscription).
    """
    signature = _catalog_signature(item)
    stable_name = (
        _without_player_inscription(
            re.sub(r"\((?:\d+)x\s+", "(", signature[0]), getattr(item, "inscription", "") or "")
        if signature[0] else None)
    return _catalog_digest((stable_name, *signature[1:3], *signature[4:]))


def optimizer_item_projection(owned: OwnedEquipment) -> tuple:
    """Stable item fields consumed by loadout search, evaluation, or planning.

    The transport models also carry volatile UI state (pack letters, fuel-bearing
    display names, fuel, timeouts, inscriptions, and bounty markers).  None of
    that state changes an operational candidate's optimizer value, so it must
    not invalidate a completed-search memo.
    """
    item = owned.item
    return (
        owned.id,
        owned.origin,
        owned.equipped_slot,
        owned.random_teleport_suppressed,
        _catalog_signature(item),
        item.weight,
        item.weapon_proficiency,
        item.pseudo_feeling,
        item.is_equipment,
        item.ammo_tval,
        operational_equipment_candidate(owned),
        owned.unidentified_wear_allowed,
    )


class OwnedEquipmentCatalog:
    """Persistent carried gear plus the authoritative ``~9`` Home list."""

    # Class default: a restored checkpoint without the attribute is untrusted.
    average_feeling_trusted = False
    # Class default: a restored checkpoint without the attribute knows no Home
    # ammunition until its next complete scan.
    _home_ammunition: tuple[StoreItem | InventoryItem, ...] = ()

    def __init__(self) -> None:
        self._carried: dict[str, OwnedEquipment] = {}
        self._home: dict[str, OwnedEquipment] = {}
        self._home_seen_pages: set[tuple[tuple, ...]] = set()
        self._home_scan_staging: dict[int, tuple[StoreItem | InventoryItem, ...]] = {}
        self._home_scan_current_page: int | None = None
        self._home_occurrences: dict[tuple, int] = {}
        self._home_deposit_intents: set[tuple] = set()
        self._home_withdrawal_intents: set[tuple] = set()
        self.home_scan_complete = False

    def set_average_feeling_trusted(self, trusted: bool) -> None:
        """Apply the owner Q-B condition of the latest C screen to every item."""
        if trusted == self.average_feeling_trusted:
            return
        self.average_feeling_trusted = trusted
        self._carried = {
            item_id: replace(owned, average_feeling_trusted=trusted)
            for item_id, owned in self._carried.items()
        }
        self._home = {
            item_id: replace(owned, average_feeling_trusted=trusted)
            for item_id, owned in self._home.items()
        }

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
                    random_teleport_suppressed=random_teleport_is_suppressed(item),
                    average_feeling_trusted=self.average_feeling_trusted,
                )
        self._carried = carried

    def observe_home_page(
        self,
        items: Iterable[StoreItem],
        *,
        allow_wrap: bool = True,
    ) -> bool:
        """Record one page; return True after an intentional page turn wraps."""
        if self.home_scan_complete:
            return True
        all_page_items = tuple(items)
        # Page identity must include everything visible in the Home. Distinct
        # consumable-only or ammunition-only pages otherwise both collapse to
        # (), falsely completing the scan before later weapon pages are seen.
        page = tuple(_catalog_signature(item) for item in all_page_items)
        # An empty Home is unambiguous.  A merely short page is not: after a
        # deposit or withdrawal Hengband can leave the store cursor on the
        # short final page of a multi-page Home.  Treating that page as the
        # whole Home made optimization alternate between whichever weapon was
        # visible there.  Non-empty scans must prove a wrap after an intentional
        # page advance, including genuinely single-page Homes.
        if not all_page_items:
            self.home_scan_complete = True
            staged_pages = tuple(self._home_scan_staging.values())
            self._home_scan_staging.clear()
            self._home_scan_current_page = None
            self._rebuild_home(staged_pages)
            return True
        matching_page = next(
            (
                page_number
                for page_number, staged_items in self._home_scan_staging.items()
                if tuple(_catalog_signature(item) for item in staged_items) == page
            ),
            None,
        )
        if matching_page is not None:
            self._home_scan_current_page = matching_page
            if not allow_wrap:
                self._home_scan_staging[matching_page] = all_page_items
                self._rebuild_home(self._home_scan_staging.values())
                return self.home_scan_complete
            self.home_scan_complete = True
            self._rebuild_home(self._home_scan_staging.values())
            self._home_scan_staging.clear()
            self._home_scan_current_page = None
            return True
        if self._home_scan_current_page is None:
            page_number = 0
        elif not allow_wrap:
            page_number = self._home_scan_current_page
        else:
            page_number = max(self._home_scan_staging) + 1
        self._home_scan_current_page = page_number
        self._home_scan_staging[page_number] = all_page_items
        self._home_seen_pages.add(page)
        self._rebuild_home(self._home_scan_staging.values())
        return self.home_scan_complete

    def complete_home_scan(
        self, items: Iterable[StoreItem | InventoryItem]
    ) -> None:
        """Replace the Home catalog from one authoritative complete inventory."""
        complete_items = tuple(items)
        self._home_seen_pages.clear()
        self._home_scan_staging.clear()
        self._home_scan_current_page = None
        self._rebuild_home((complete_items,))
        self.home_scan_complete = True

    def _rebuild_home(
        self,
        pages: Iterable[Iterable[StoreItem | InventoryItem]],
    ) -> None:
        """Replace the Home catalog with the exact contents of staged pages."""
        self._home.clear()
        self._home_occurrences.clear()
        ammunition: list[StoreItem | InventoryItem] = []
        for item in (item for page_items in pages for item in page_items):
            if item.tval in AMMUNITION_TVALS:
                if item.count > 0:
                    ammunition.append(item)
                continue
            if not item.is_equipment:
                continue
            signature = _catalog_signature(item)
            occurrence = self._home_occurrences.get(signature, 0)
            self._home_occurrences[signature] = occurrence + 1
            item_id = f"home:{_catalog_digest(signature)}:{occurrence}"
            self._home[item_id] = OwnedEquipment(
                item_id,
                item,
                "home",
                random_teleport_suppressed=random_teleport_is_suppressed(item),
                average_feeling_trusted=self.average_feeling_trusted,
            )
        self._home_ammunition = tuple(ammunition)

    def _move_home_ammunition(
        self, item: StoreItem | InventoryItem, count: int
    ) -> None:
        """Add (or, negative, remove) ``count`` rounds of ``item``'s stack."""
        key = _ammunition_key(item)
        stacks: list[StoreItem | InventoryItem] = []
        moved = False
        for stack in self._home_ammunition:
            if not moved and _ammunition_key(stack) == key:
                moved = True
                stack = replace(stack, count=stack.count + count)
            if stack.count > 0:
                stacks.append(stack)
        if not moved and count > 0:
            stacks.append(replace(item, count=count))
        self._home_ammunition = tuple(stacks)

    @property
    def home_ammunition(self) -> tuple[StoreItem | InventoryItem, ...]:
        """The Home's ammunition stacks, kept like its equipment.

        The same content knowledge as the Home launchers in ``items``: a
        complete scan replaces it and a commanded deposit or withdrawal moves
        it, while the page-address invalidation after a Home command does not
        discard it.
        """
        return self._home_ammunition

    def _update_staged_home_item(
        self,
        item: StoreItem | InventoryItem,
        *,
        add: bool,
    ) -> None:
        """Apply one commanded mutation to the currently visible staged page."""
        if self.home_scan_complete or self._home_scan_current_page is None:
            return
        page_number = self._home_scan_current_page
        page_items = list(self._home_scan_staging[page_number])
        if add:
            page_items.append(item)
        else:
            signature = _catalog_signature(item)
            matching_index = next(
                (
                    index
                    for index, staged_item in enumerate(page_items)
                    if _catalog_signature(staged_item) == signature
                ),
                None,
            )
            if matching_index is not None:
                page_items.pop(matching_index)
        self._home_scan_staging[page_number] = tuple(page_items)
        self._rebuild_home(self._home_scan_staging.values())

    def record_home_deposit(
        self,
        item: InventoryItem,
        *,
        intent: tuple,
        quantity: int | None = None,
    ) -> None:
        """Add one commanded deposit without discarding a completed Home scan.

        ``quantity`` is the deposited part of an ammunition stack (default:
        the whole stack).
        """
        if intent in self._home_deposit_intents:
            return
        self._home_deposit_intents.add(intent)
        if item.tval in AMMUNITION_TVALS:
            if not self.home_scan_complete:
                self._update_staged_home_item(item, add=True)
            else:
                self._move_home_ammunition(
                    item, item.count if quantity is None else quantity)
            return
        if not item.is_equipment:
            return
        if not self.home_scan_complete:
            self._update_staged_home_item(item, add=True)
            return
        signature = _catalog_signature(item)
        occurrence = self._home_occurrences.get(signature, 0)
        self._home_occurrences[signature] = occurrence + 1
        item_id = f"home:{_catalog_digest(signature)}:{occurrence}"
        self._home[item_id] = OwnedEquipment(
            item_id,
            item,
            "home",
            random_teleport_suppressed=random_teleport_is_suppressed(item),
            average_feeling_trusted=self.average_feeling_trusted,
        )

    def record_home_withdrawal(
        self,
        item: StoreItem,
        *,
        intent: tuple,
        quantity: int | None = None,
    ) -> None:
        """Remove one commanded withdrawal without discarding a completed scan.

        ``quantity`` is the taken part of an ammunition stack (default: the
        whole stack).
        """
        if intent in self._home_withdrawal_intents:
            return
        self._home_withdrawal_intents.add(intent)
        if item.tval in AMMUNITION_TVALS:
            if self.home_scan_complete:
                self._move_home_ammunition(
                    item, -(item.count if quantity is None else quantity))
            return
        if not item.is_equipment:
            return
        if not self.home_scan_complete:
            self._update_staged_home_item(item, add=False)
            return
        signature = _catalog_signature(item)
        matching_ids = [
            item_id
            for item_id, owned in self._home.items()
            if _catalog_signature(owned.item) == signature
        ]
        if not matching_ids:
            return
        item_id = max(
            matching_ids,
            key=lambda matching_id: int(matching_id.rsplit(":", 1)[1]),
        )
        del self._home[item_id]
        occurrence = max(0, self._home_occurrences.get(signature, 0) - 1)
        if occurrence:
            self._home_occurrences[signature] = occurrence
        else:
            self._home_occurrences.pop(signature, None)

    def invalidate_home(self) -> None:
        """Discard Home contents when a mutation cannot be proved.

        Page-relative addresses do not live in this catalogue and must be
        invalidated by their owner.  Call this only when a content mutation
        cannot be proved and therefore must be reacquired through ``~9``.
        This is distinct from page-address invalidation after a bound command.
        """
        self._home.clear()
        self._home_ammunition = ()
        self._home_seen_pages.clear()
        self._home_scan_staging.clear()
        self._home_scan_current_page = None
        self._home_occurrences.clear()
        self._home_deposit_intents.clear()
        self._home_withdrawal_intents.clear()
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
    # TV_DIGGING (20) is reserved separately for the temporary two-hand mining
    # loadout; it remains excluded from combat-loadout optimization.
    return item.tval in {21, 22, 23}


def _is_shield(item: EquipmentItem) -> bool:
    return item.tval == 34


def _is_ring(item: EquipmentItem) -> bool:
    return item.tval == 45


def hand_configurations(
    items: Iterable[OwnedEquipment],
    pinned: Mapping[str, OwnedEquipment] | None = None,
) -> Iterator[HandConfiguration]:
    pinned = pinned or {}
    weapons = [item for item in items if _is_weapon(item.item)]
    shields = [item for item in items if _is_shield(item.item)]

    configurations = [HandConfiguration(None, None)]
    # Preserve the valid but degenerate state where a cursed weapon occupies
    # only the sub hand; otherwise pinning would make the search empty.
    if SLOT_SUB_HAND in pinned and SLOT_MAIN_HAND not in pinned:
        configurations.append(HandConfiguration(None, pinned[SLOT_SUB_HAND]))
    for weapon in weapons:
        # Hengband automatically uses both free hands for polearms and weapons
        # over 9.9 lb.  Lighter non-polearms remain genuinely one-handed.
        if weapon.item.tval == 22 or weapon.item.weight > 99:
            configurations.append(HandConfiguration(weapon, None, True))
        else:
            configurations.append(HandConfiguration(weapon, None, False))
        for shield in shields:
            configurations.append(HandConfiguration(weapon, shield))
    for main, sub in combinations(weapons, 2):
        configurations.append(HandConfiguration(main, sub))
        configurations.append(HandConfiguration(sub, main))
    for configuration in configurations:
        if (
            (SLOT_MAIN_HAND not in pinned or configuration.main == pinned[SLOT_MAIN_HAND])
            and (SLOT_SUB_HAND not in pinned or configuration.sub == pinned[SLOT_SUB_HAND])
        ):
            yield configuration


def _ring_configurations(
    items: Iterable[OwnedEquipment],
    pinned: Mapping[str, OwnedEquipment] | None = None,
) -> Iterator[tuple[OwnedEquipment | None, ...]]:
    pinned = pinned or {}
    rings = [item for item in items if _is_ring(item.item)]
    if SLOT_MAIN_RING in pinned or SLOT_SUB_RING in pinned:
        choices = (None, *rings)
        for main, sub in product(choices, repeat=2):
            if main is not None and sub is not None and main.id == sub.id:
                continue
            if SLOT_MAIN_RING in pinned and main != pinned[SLOT_MAIN_RING]:
                continue
            if SLOT_SUB_RING in pinned and sub != pinned[SLOT_SUB_RING]:
                continue
            yield (main, sub)
        return
    yield ()
    for ring in rings:
        yield (ring,)
    yield from combinations(rings, 2)


def enumerate_loadouts(
    items: Iterable[OwnedEquipment],
    pinned: Mapping[str, OwnedEquipment] | None = None,
) -> Iterator[Loadout]:
    """Enumerate every legal slot/hand assignment without quality pruning."""
    pinned = pinned or {}
    legal = [item for item in items if item.exploration_legal]
    candidates = [*legal, *(item for item in pinned.values() if item not in legal)]
    pools: list[tuple[OwnedEquipment | None, ...]] = []
    for slot in FIXED_SLOTS:
        if slot in pinned:
            pools.append((pinned[slot],))
        else:
            slot_candidates = tuple(item for item in legal if slot_for(item.item) == slot)
            pools.append((None, *slot_candidates))

    for fixed, hands, rings in product(
        product(*pools), hand_configurations(candidates, pinned),
        _ring_configurations(candidates, pinned)
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
        if rings and rings[0] is not None:
            assigned.append((SLOT_MAIN_RING, rings[0]))
        if len(rings) == 2 and rings[1] is not None:
            assigned.append((SLOT_SUB_RING, rings[1]))
        yield Loadout(tuple(assigned), hands.mode)


def _meets_requirements(
    loadout: Loadout,
    metrics: LoadoutMetrics,
    *,
    depth: int | None,
    intrinsic_abilities: frozenset[str],
    has_destruction: bool,
    require_light: bool = True,
    staff_gate=None,
) -> bool:
    if not metrics.evaluation_complete:
        return False
    if not _meets_static_requirements(
        loadout,
        depth=depth,
        intrinsic_abilities=intrinsic_abilities,
        has_destruction=has_destruction,
        require_light=require_light,
        staff_gate=staff_gate,
    ):
        return False
    if (depth is not None and depth >= SPEED_GATE_DEPTH
            and not meets_speed_gate(loadout_speed(metrics))):
        return False
    return True


def owned_armor_fill_slots(
    items: Iterable[OwnedEquipment],
    excluded_item_ids: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """Return the non-body armour slots an owned, usable piece can fill.

    Mirrors the body rule's candidate test (``exploration_legal``: known,
    uncursed, unbroken, no forbidden flag).  The catalogue holds only owned
    items (equipped, pack, Home), never store stock.
    """
    return frozenset(
        slot
        for item in items
        if item.id not in excluded_item_ids
        and item.exploration_legal
        and (slot := slot_for(item.item)) in FILL_REQUIRED_ARMOR_SLOTS
    )


def usable_light_candidate(owned: OwnedEquipment) -> bool:
    """Return whether a light can participate in an exploration loadout."""
    return (
        slot_for(owned.item) == SLOT_LIGHT
        and owned.exploration_legal
        and operational_equipment_candidate(owned)
    )


def lighting_light_candidate(owned: OwnedEquipment) -> bool:
    """A usable light that is not known to light nothing (``lights_nothing``).

    A dark light such as ★火消しライター (TR_LITE_M1 with TR_DARK_SOURCE,
    radius -1) fills the light slot but lights nothing: worn alone the
    player's radius is 0 and the game refuses reading (``no_lite``) on every
    unlit cell (n1-b life-321).  Only a light that lights makes the light
    requirement of the loadout search.
    """
    return usable_light_candidate(owned) and not lights_nothing(owned.item)


def _loadout_lights(loadout: Loadout) -> bool:
    """The loadout wears a light that lights, not darkened to 0 by the rest.

    When a light that lights is owned, the light requirement asks the whole
    loadout to light (USER DECISION 2026-10-23 「合計で比べる」): a dark
    light, or a light whose radius the other worn items cancel, is never kept
    for a stealth or score gain (n1-b life-321 wore ★火消しライター for its
    +3 stealth and read nothing in the dark).  A light whose own flags are
    not known adds no radius here and still counts as lighting.
    """
    light = loadout.item_at(SLOT_LIGHT)
    if light is None or lights_nothing(light.item):
        return False
    own = worn_light_radius((light,))
    return own <= 0 or loadout_light_radius(loadout) > 0


def _meets_static_requirements(
    loadout: Loadout,
    *,
    depth: int | None,
    intrinsic_abilities: frozenset[str],
    has_destruction: bool,
    require_light: bool = True,
    staff_gate=None,
) -> bool:
    """Reject loadouts whose failure does not depend on combat evaluation."""
    if require_light and not _loadout_lights(loadout):
        return False
    light = loadout.item_at(SLOT_LIGHT)
    launcher = loadout.item_at(SLOT_BOW)
    if not torch_release.wearable_light(launcher and launcher.item, light and light.item):
        return False
    abilities = set(intrinsic_abilities)
    for name, flag in ABILITY_FLAG.items():
        if flag in loadout.flags:
            abilities.add(name)
    if depth is not None and not required_abilities(depth).issubset(abilities):
        return False
    if (depth is not None and depth >= DEEP_FLOOR_DEPTH
            and not destruction_means(loadout, has_destruction, staff_gate)):
        return False
    return True


def _pareto_dominates(left: EvaluatedLoadout, right: EvaluatedLoadout) -> bool:
    lm = left.metrics
    rm = right.metrics
    left_traits = lm.relevant_traits
    right_traits = rm.relevant_traits
    # Damage per game time and the permanent speed (speed_valuation).
    no_worse = (
        time_melee(lm) >= time_melee(rm)
        and time_ranged(lm) >= time_ranged(rm)
        and time_device(lm) >= time_device(rm)
        and lm.survival_turns >= rm.survival_turns
        and lm.combat_margin >= rm.combat_margin
        and loadout_speed(lm) >= loadout_speed(rm)
        and lm.secondary_value >= rm.secondary_value
        and lm.utility_value >= rm.utility_value
        and left_traits.issuperset(right_traits)
    )
    strictly_better = (
        time_melee(lm) > time_melee(rm)
        or time_ranged(lm) > time_ranged(rm)
        or time_device(lm) > time_device(rm)
        or lm.survival_turns > rm.survival_turns
        or lm.combat_margin > rm.combat_margin
        or loadout_speed(lm) > loadout_speed(rm)
        or lm.secondary_value > rm.secondary_value
        or lm.utility_value > rm.utility_value
        or left_traits > right_traits
    )
    return no_worse and strictly_better


# The Light Crossbow rule (owner 2026-07-19, 2026-10-02, 2026-11-21 n1-b life-413) is
# equipment_rules' ``ordinary_launcher_yields_to_light_crossbow`` / ``launcher_is_high_grade``.


def yields_to_light_crossbow(
    launcher: OwnedEquipment,
    crossbow: OwnedEquipment,
    usable_launcher_ids: frozenset[str] = frozenset(),
) -> bool:
    """Whether the user launcher rule replaces ``launcher`` by ``crossbow``.

    ``usable_launcher_ids`` holds the launchers with obtainable ammunition
    (see ``optimize_loadout``).  The missing-bolts exception only blocks a
    swap INTO a Light Crossbow: one without obtainable bolts never displaces
    a launcher that can shoot.  An equipped Light Crossbow keeps the rule
    regardless of ammunition evidence (zero bolts or a forgotten supplier
    page after a restart never swaps it back); bolts are procured as usual.
    When neither launcher has ammunition evidence the rule applies unchanged.
    """
    return ordinary_launcher_yields_to_light_crossbow(
        launcher.item, crossbow.item
    ) and (
        crossbow.origin == "equipped"
        or crossbow.id in usable_launcher_ids
        or launcher.id not in usable_launcher_ids
    )


# The finale loadout (owner 2026-11-20, the 99F/100F directive): 「装備は加速耐性テレパシーー知力耐久力を
# 優先。ACや近接攻撃力は求めない。」 and 「呪力耐性も要求する。これはオベロンの血の呪い、サーペントの破滅の手が
# 致死的であるためである。」  TR flag numbers: src/object-enchant/tr-types.h.
TR_INT = 1
TR_CON = 4
TR_RES_CURSE = 148
# Owner 2026-11-20 Q6 「耐盲目か耐閃光を条件に入れる」: either keeps *Destruction*'s flash from
# blinding (spells-floor.cpp:416).
TR_RES_BLIND = 56
TR_RES_LITE = 54
# The resistances counted one per element: TR_RES_ACID..TR_RES_DISEN, TR_RES_TIME, TR_RES_WATER;
# an immunity (TR_IM_ACID..TR_IM_COLD, TR_IM_DARK, TR_IM_LITE) counts as its element's resistance.
FINALE_RESISTANCES = frozenset(range(48, 64)) | {143, 144}
FINALE_IMMUNITY_ELEMENT = {40: 48, 41: 49, 42: 50, 43: 51, 157: 55, 163: 54}


def _stat_bonus(loadout: Loadout, flag: int) -> int:
    return sum(item.item.pval for _, item in loadout.slots if flag in item.flags)


# Owner 2026-11-21 「過剰な加速よりもまず知力を十分上げることを優先して」 and 「成功率95%まで」: the
# powered Rockets' success the INT is raised to before any speed beyond the +25 gate.
FINALE_POWER_SUCCESS = 95


def finale_rank(entry: EvaluatedLoadout) -> tuple:
    """The 99F/100F loadout's order, compared before everything else: resist curse, resist
    blindness or light, the speed gate (+25 after the weight); then, owner 2026-11-21
    「過剰な加速よりもまず知力を十分上げることを優先して」「成功率95%まで」, the Rockets' success up to
    95% (the INT that raises it); then the permanent speed, the number of resisted elements,
    telepathy, INT, CON (owner 2026-11-20 「加速耐性テレパシー知力耐久力を優先」).  Nothing of AC or melee: those decide only between
    loadouts this rank holds equal (the ordinary comparison)."""
    flags = entry.loadout.flags
    elements = (flags & FINALE_RESISTANCES) | {
        element for immunity, element in FINALE_IMMUNITY_ELEMENT.items() if immunity in flags}
    speed = loadout_speed(entry.metrics)
    success = getattr(entry.metrics, "finale_power_success", None)
    return (TR_RES_CURSE in flags, bool(flags & {TR_RES_BLIND, TR_RES_LITE}),
            meets_speed_gate(speed),
            min(success or 0, FINALE_POWER_SUCCESS),
            speed, len(elements), TR_TELEPATHY in flags, _stat_bonus(entry.loadout, TR_INT),
            _stat_bonus(entry.loadout, TR_CON))


def _prefer(
    candidate: EvaluatedLoadout,
    incumbent: EvaluatedLoadout,
    current_item_ids: frozenset[str],
    usable_launcher_ids: frozenset[str] = frozenset(),
    finale: bool = False,
) -> bool:
    if finale:
        candidate_rank, incumbent_rank = finale_rank(candidate), finale_rank(incumbent)
        if candidate_rank != incumbent_rank:
            return candidate_rank > incumbent_rank
    cm = candidate.metrics
    im = incumbent.metrics
    candidate_bow = candidate.loadout.item_at(SLOT_BOW)
    incumbent_bow = incumbent.loadout.item_at(SLOT_BOW)
    if candidate_bow is not None and incumbent_bow is not None:
        # The grade rule precedes the obtainable-ammo damage comparison.
        if yields_to_light_crossbow(
            incumbent_bow, candidate_bow, usable_launcher_ids
        ):
            return True
        if yields_to_light_crossbow(
            candidate_bow, incumbent_bow, usable_launcher_ids
        ):
            return False
        # A launcher with nothing to shoot (no owned or seen rounds, see ``optimize_loadout``)
        # never displaces one that can shoot, whatever its plain-round damage.
        candidate_usable = candidate_bow.id in usable_launcher_ids
        if candidate_usable != (incumbent_bow.id in usable_launcher_ids):
            return candidate_usable
    # No launcher-only damage comparison precedes the whole loadout's (owner 2026-11-22
    # 「近接の増え方も入れて全体で比べる」): the launcher's shot (``ranged_dps``, the plain store
    # round, launcher_damage.plain_ammo_turn_damage) and its stat modifiers' melee, devices
    # and survival are compared below like every other slot's.
    # A permanent light is a strict operational upgrade over a lantern or
    # torch when every modeled combat result is identical. Keep this separate
    # from combat metrics so light quality cannot trade against defense or DPS.
    if cm == im:
        candidate_light = (
            light_source_quality(candidate.loadout),
            loadout_light_radius(candidate.loadout),
        )
        incumbent_light = (
            light_source_quality(incumbent.loadout),
            loadout_light_radius(incumbent.loadout),
        )
        if candidate_light != incumbent_light:
            return candidate_light > incumbent_light
    # When every defensive/utility result is identical, offense is the whole
    # comparison.  The general 1% anti-churn band used combat_margin and could
    # therefore retain an inferior wielded weapon even though a Home weapon had
    # strictly higher AC-100 damage per player turn.
    same_non_offense = (
        cm.survival_turns == im.survival_turns
        and loadout_speed(cm) == loadout_speed(im)
        and cm.secondary_value == im.secondary_value
        and cm.utility_value == im.utility_value
        and cm.relevant_traits == im.relevant_traits
    )
    if same_non_offense:
        candidate_slots = dict(candidate.loadout.slots)
        incumbent_slots = dict(incumbent.loadout.slots)
        bow_only_change = (
            candidate_slots.get(SLOT_BOW) != incumbent_slots.get(SLOT_BOW)
            and {
                slot: item.id
                for slot, item in candidate_slots.items()
                if slot != SLOT_BOW
            }
            == {
                slot: item.id
                for slot, item in incumbent_slots.items()
                if slot != SLOT_BOW
            }
        )
        if bow_only_change:
            candidate_bow = candidate_slots.get(SLOT_BOW)
            incumbent_bow = incumbent_slots.get(SLOT_BOW)
            if time_ranged(cm) != time_ranged(im):
                return time_ranged(cm) > time_ranged(im)
        if time_melee(cm) != time_melee(im):
            return time_melee(cm) > time_melee(im)
        if time_ranged(cm) != time_ranged(im):
            return time_ranged(cm) > time_ranged(im)
        if time_device(cm) != time_device(im):
            return time_device(cm) > time_device(im)
    if not isfinite(cm.combat_margin) or not isfinite(im.combat_margin):
        if cm.combat_margin != im.combat_margin:
            return cm.combat_margin > im.combat_margin
        if cm.secondary_value != im.secondary_value:
            return cm.secondary_value > im.secondary_value
        if cm.utility_value != im.utility_value:
            return cm.utility_value > im.utility_value
        if len(candidate.loadout.slots) != len(incumbent.loadout.slots):
            return len(candidate.loadout.slots) > len(incumbent.loadout.slots)
        candidate_is_current = candidate.loadout.item_ids == current_item_ids
        incumbent_is_current = incumbent.loadout.item_ids == current_item_ids
        return candidate_is_current and not incumbent_is_current
    # A modest survival loss must not hide a material damage gain. In the live
    # Might Crown regression, ten points of head AC improved modeled survival by
    # only 2.7% while dropping melee DPS by 33%. The combat margin of that time
    # (survival minus kill turns) still ranked the helmet first because the
    # survival value is measured in hundreds of turns. Compare the relative
    # trade directly before the margin.
    candidate_material_offense = time_melee(cm) > time_melee(im) * 1.05
    incumbent_material_offense = time_melee(im) > time_melee(cm) * 1.05
    candidate_preserves_survival = cm.survival_turns >= im.survival_turns * 0.95
    incumbent_preserves_survival = im.survival_turns >= cm.survival_turns * 0.95
    if candidate_material_offense and candidate_preserves_survival:
        return True
    if incumbent_material_offense and incumbent_preserves_survival:
        return False
    # combat_margin is the dimensionless ratio survival / kill turns (user
    # decision 2026-10-02).  The 1% band is relative, so it keeps its meaning
    # for the ratio: two loadouts within 1% of each other's survival-per-kill
    # are operationally equivalent.
    threshold = abs(im.combat_margin) * 0.01
    difference = cm.combat_margin - im.combat_margin
    if difference > threshold:
        return True
    if difference < -threshold:
        return False
    # Inside the existing 1% combat-margin equivalence band, preserve real
    # offensive output before consulting secondary-risk tie breakers.  A small
    # AC gain can still hide a large DPS loss inside the band (the live Might
    # Crown regression was 62.7 vs 82.3 melee DPS for only 0.9% margin when
    # the margin was a difference in turns).
    dps_threshold = abs(time_melee(im)) * 0.05
    dps_difference = time_melee(cm) - time_melee(im)
    if dps_difference > dps_threshold:
        return True
    if dps_difference < -dps_threshold:
        return False
    ranged_threshold = abs(time_ranged(im)) * 0.05
    ranged_difference = time_ranged(cm) - time_ranged(im)
    if ranged_difference > ranged_threshold:
        return True
    if ranged_difference < -ranged_threshold:
        return False
    device_threshold = abs(time_device(im)) * 0.05
    device_difference = time_device(cm) - time_device(im)
    if device_difference > device_threshold:
        return True
    if device_difference < -device_threshold:
        return False
    if cm.secondary_value != im.secondary_value:
        return cm.secondary_value > im.secondary_value
    if cm.utility_value != im.utility_value:
        return cm.utility_value > im.utility_value
    if len(candidate.loadout.slots) != len(incumbent.loadout.slots):
        return len(candidate.loadout.slots) > len(incumbent.loadout.slots)
    candidate_is_current = candidate.loadout.item_ids == current_item_ids
    incumbent_is_current = incumbent.loadout.item_ids == current_item_ids
    return candidate_is_current and not incumbent_is_current


def _selection_equivalence_key(
    entry: EvaluatedLoadout,
    current_item_ids: frozenset[str],
) -> tuple[object, ...]:
    """Keep policy-distinct representatives even when metrics are identical."""
    bow = entry.loadout.item_at(SLOT_BOW)
    if bow is None:
        bow_policy = None
    else:
        bow_policy = (bow.item.sval, launcher_is_high_grade(bow.item))
    return (
        entry.metrics,
        entry.loadout.hand_mode,
        entry.loadout.flags.intersection(ABILITY_FLAG.values()),
        bow_policy,
        light_source_quality(entry.loadout),
        len(entry.loadout.slots),
    )


# Survival-sufficiency floor (approved design 2026-07-24): once a loadout can
# absorb the representative encounter set for at least this many turns, it is
# "safe enough" and additional survival margin is not worth sacrificing melee
# offense.  Above the floor the selection is offense-first (DPS primary); below
# it (a genuinely dangerous field where nothing is comfortably safe) the
# selection falls back to survival-first. survival_turns counts player actions:
# player_hp divided by energy-adjusted incoming damage per player turn.
SUFFICIENT_SURVIVAL_TURNS = 30.0


def _dangerous_field_pool(
    pool: list[EvaluatedLoadout],
) -> list[EvaluatedLoadout]:
    """Filter a field where no loadout reaches SUFFICIENT_SURVIVAL_TURNS.

    User decision 2026-10-02 18:5x (「足切りも比に置き換える」): the
    survival-per-kill ratio decides, within the existing 1% band, not survival
    alone.  The former "survival >= 95% of the maximum" floor (2026-07-24)
    dropped the live ダメージの指輪 (+9) set (10.18 vs 11.10 turns) before its
    better ratio (2.69 vs 2.47) was consulted.  tests/recorded_loadout.py
    restores that floor for replays held on their recorded gear.

    The ratio is weighted by the speed up to +20 within the field (owner
    2026-11-17, speed_valuation.weighted_margin).
    """
    field = field_strong_speed_energy(entry.metrics for entry in pool)
    margins = [weighted_margin(entry.metrics, field) for entry in pool]
    max_margin = max(margins)
    if isfinite(max_margin):
        return [
            entry
            for entry, margin in zip(pool, margins)
            if margin >= max_margin - abs(max_margin) * 0.01
        ]
    return [entry for entry, margin in zip(pool, margins) if margin == max_margin]


def _within_half_melee(
    entries: list[EvaluatedLoadout], reference_melee: float,
) -> list[EvaluatedLoadout]:
    """The loadouts keeping at least half of ``reference_melee`` (the half-melee limit).

    A zero reference limits nothing.  The depth-band descent applies the limit
    to every set of a band against the unconstrained best melee, so whether a
    band is accepted does not depend on which of its sets the operational
    selector prefers from the worn loadout (n1-c life-105 2026-11-02: a resist
    body armour below half melee refused band 20 only while the pike was worn,
    and the pike and the war hammer were swapped forever).

    Melee is damage per game time (speed_valuation.time_melee, owner
    2026-11-17 「時間あたりの打撃」), and so is ``reference_melee``.
    """
    if reference_melee <= 0:
        return list(entries)
    return [
        entry for entry in entries
        if time_melee(entry.metrics) * 2 >= reference_melee
    ]


def _stable_operational_best(
    evaluated: Iterable[EvaluatedLoadout],
    current_item_ids: frozenset[str],
    usable_launcher_ids: frozenset[str] = frozenset(),
    *,
    launcher_power: bool = True,
) -> EvaluatedLoadout | None:
    """Select from the whole field without a non-transitive winner chain.

    ``launcher_power=False`` (me_deep_launcher, owner 2026-11-18 「射撃威力を評価値から外し、
    弓枠は追加能力や耐性のみで評価する」): the launcher's shooting power is left out, so the
    grade rule does not apply and every
    ``ranged_dps`` reads 0; the bow slot competes through its flags like any other slot.

    Pairwise "material offense if survival is within 5%" comparisons can form
    a cycle (A outdamages B, B outdamages C, C outlasts A).  A sequential
    tournament then changes winner with catalog order, which in turn changes
    whenever Home pages are rescanned after a swap.  Anchor both tolerances to
    the field maxima before applying deterministic tie breakers.
    """
    pool = list(evaluated)
    if not pool:
        return None
    # The entry chosen from the field without the launcher's power is returned as evaluated.
    original: dict[int, EvaluatedLoadout] | None = None
    if not launcher_power:
        unscored = [
            replace(entry, metrics=replace(entry.metrics, ranged_dps=0.0))
            for entry in pool
        ]
        original = {id(stripped): entry for stripped, entry in zip(unscored, pool)}
        pool = unscored

    # Preserve the explicit launcher policy: an ordinary launcher of another kind
    # does not compete with an available Light Crossbow (owner 2026-11-21). High-grade
    # ones remain in the normal comparison: the whole loadout's (owner 2026-11-22
    # 「近接の増え方も入れて全体で比べる」), no launcher-only damage filter first.
    light_crossbows = [
        bow
        for entry in pool
        if (bow := entry.loadout.item_at(SLOT_BOW)) is not None
        and bow.item.sval == LIGHT_CROSSBOW_SVAL
    ]
    if light_crossbows and launcher_power:
        pool = [
            entry
            for entry in pool
            if (bow := entry.loadout.item_at(SLOT_BOW)) is None
            or not any(
                yields_to_light_crossbow(bow, crossbow, usable_launcher_ids)
                for crossbow in light_crossbows
            )
        ]

    # A launcher with nothing to shoot never displaces one that can (``_prefer``).
    if launcher_power and any(
        (bow := entry.loadout.item_at(SLOT_BOW)) is not None and bow.id in usable_launcher_ids
        for entry in pool
    ):
        pool = [
            entry
            for entry in pool
            if (bow := entry.loadout.item_at(SLOT_BOW)) is None
            or bow.id in usable_launcher_ids
        ]

    # Apply the existing half-melee limit within the already requirement-valid
    # field before survival can reward optional resistance coverage. Otherwise
    # a low-DPS tank becomes both the winner and its own melee_free baseline.
    # Owner 2026-11-17 「装備最適化のスピードの評価を上げて。特にspeed+20までは生存に
    # 大きく寄与する」 / 「時間あたりの打撃＋+20までを強く」 (speed_valuation): every
    # damage compared below is per game time, so the half floor and the 95%
    # cut no longer discard a faster set for its lower damage per action, and
    # the survival / kill ratios are weighted by the speed up to +20.  The
    # weight is relative to this field's best speed capped at +20 (taken once
    # here; the 1% bands are relative, so the anchor only scales them).  The
    # 30-turn floor stays on the player turns survived, which already count
    # the speed once through the energy: weighting that absolute floor by a
    # field-relative factor let one slow-damage +13 set push the +10
    # damage-ring set of n1-b life-411 under it (32.4 turns -> 28.2) and chose
    # an AC ring at 306 instead of 356 damage per time.
    pool = _within_half_melee(
        pool, max(time_melee(entry.metrics) for entry in pool)
    )
    speed_field = field_strong_speed_energy(entry.metrics for entry in pool)

    # Survival-sufficiency gate.  Loadouts that survive at least
    # SUFFICIENT_SURVIVAL_TURNS are all treated as adequately safe, so the DPS
    # and margin filters below choose offense-first among them (this is why a
    # higher-DPS weapon is no longer culled merely for a few percent less
    # survival).  When NO loadout clears the floor, the survival / kill ratio
    # (combat_margin) filters first (user decision 2026-10-02).
    max_survival = max(entry.metrics.survival_turns for entry in pool)
    safe_enough = [
        entry
        for entry in pool
        if entry.metrics.survival_turns >= SUFFICIENT_SURVIVAL_TURNS
    ]
    if safe_enough:
        pool = safe_enough
    elif isfinite(max_survival):
        pool = _dangerous_field_pool(pool)
    else:
        pool = [
            entry for entry in pool
            if entry.metrics.survival_turns == max_survival
        ]

    max_dps = max(time_melee(entry.metrics) for entry in pool)
    if max_dps > 0:
        pool = [
            entry
            for entry in pool
            if time_melee(entry.metrics) >= max_dps * 0.95
        ]

    # combat_margin is the ratio survival / kill turns (user decision
    # 2026-10-02); the 1% band is relative and so unchanged by that.  The
    # ratio already counts the speed once (survival in player turns grows
    # with the energy, kill turns do not); the weight adds the +20 part.
    margins = {
        id(entry): weighted_margin(entry.metrics, speed_field) for entry in pool
    }
    max_margin = max(margins.values())
    if isfinite(max_margin):
        margin_band = abs(max_margin) * 0.01
        pool = [
            entry
            for entry in pool
            if margins[id(entry)] >= max_margin - margin_band
        ]
    else:
        pool = [
            entry for entry in pool
            if margins[id(entry)] == max_margin
        ]

    best = max(
        pool,
        key=lambda entry: (
            time_ranged(entry.metrics),
            time_device(entry.metrics),
            entry.metrics.secondary_value,
            entry.metrics.utility_value,
            loadout_speed(entry.metrics),
            light_source_quality(entry.loadout),
            loadout_light_radius(entry.loadout),
            len(entry.loadout.slots),
            entry.loadout.item_ids == current_item_ids,
            margins[id(entry)],
            entry.metrics.survival_turns,
            time_melee(entry.metrics),
            len(entry.metrics.relevant_traits),
            # The pieces themselves, not where they are: a catalogue id names the piece's
            # origin (equipped / pack / home), which the visit's own moves change.  n1-c
            # life-220 2026-11-22 07:23 (the sub_ring round trip): 耐冷の指輪 and 浮遊の指輪
            # tied on every metric; worn, 'equipped:4827..' outranked 'equipped:2ca7..', and
            # after the levitation ring went to the Home 'home:2ca7..' outranked the worn cold
            # ring, so the next search wore the levitation ring again.  The ids stay last, for
            # copies of one identity only.
            tuple(sorted(equipment_move_identity(owned.item)
                         for _slot, owned in entry.loadout.slots)),
            tuple(sorted(entry.loadout.item_ids)),
        ),
    )
    return best if original is None else original[id(best)]


def optimize_loadout(
    items: Iterable[OwnedEquipment],
    evaluator: LoadoutEvaluator,
    *,
    depth: int | None,
    intrinsic_abilities: frozenset[str] = frozenset(),
    has_destruction: bool = False,
    current_item_ids: frozenset[str] = frozenset(),
    timeout_seconds: float = 5.0,
    candidate_loadouts: Iterable[Loadout] | None = None,
    require_light: bool | None = None,
    require_body: bool | None = None,
    identification_exempt_item_ids: frozenset[str] = frozenset(),
    obtainable_ammunition: Iterable[EquipmentItem] = (),
    require_armor_slots: frozenset[str] | None = None,
    staff_gate=None,
    launcher_power_unscored: Callable[[int | None], bool] | None = None,
    finale: bool = False,
    destination_floor: int | None = None,
) -> OptimizationResult:
    """Find the best complete loadout, failing closed if exact search times out.

    ``destination_floor`` (destination_band_floor, the town's destination band; owner Q4 of the
    equipment review 2026-11-22): the depth-band descent takes the band of this depth without the
    half-melee limit when one of its sets is owned (the limit then only chooses among its sets);
    a deeper band keeps the limit, and a shallower one is never reached while that band has a set.

    ``staff_gate`` (device_skill.StaffGate): an owned *Destruction* staff is the
    50F+ means of the loadouts whose device skill makes it reliable.

    ``launcher_power_unscored(depth)`` (me_deep_launcher, owner 2026-11-18): whether the
    loadout chosen for ``depth`` (the given depth, or the descent's band) is chosen
    without the launcher's shooting power.

    ``finale`` (angband_finale ``preparing``, owner 2026-11-20): every comparison asks
    ``finale_rank`` first (resist curse, speed, resistances, telepathy, INT, CON)."""
    catalog = tuple(items)
    ammunition = tuple(obtainable_ammunition)
    # "Obtainable" is the caller's ammunition list (the policy passes carried, Home and
    # remembered plain store stock), and for a high-grade launcher the plain ammunition the
    # Weaponsmith always stocks (articles-on-sale.cpp store_regular_sale_table: two each of
    # shots, arrows and bolts): the owner's rule compares it by damage (n1-b life-413
    # 2026-11-21, ★森の狩人ロビンフッドのショート・ボウ in Home with no arrows read 0).
    def regular_stock(owned):
        return launcher_is_high_grade(owned.item) and not any(
            ammo.tval == owned.item.ammo_tval and ammo.count > 0 for ammo in ammunition)

    # The launchers' damage is the evaluator's ``ranged_dps`` with the plain store round of each
    # kind (owner 2026-11-22 「射撃武器の比較には店で買える並の矢弾を使って。」); the obtainable
    # ammunition only says which launchers can shoot (the Light Crossbow rule's exception).
    usable_launcher_ids = frozenset(
        owned.id
        for owned in catalog
        if owned.item.ammo_tval is not None
        and (regular_stock(owned) or any(
            ammo.tval == owned.item.ammo_tval and ammo.count > 0
            for ammo in ammunition
        ))
    )
    if require_light is None:
        require_light = any(lighting_light_candidate(item) for item in catalog)
    if require_body is None:
        require_body = any(
            item.exploration_legal and slot_for(item.item) == SLOT_BODY
            for item in catalog
        )
    if require_armor_slots is None:
        require_armor_slots = owned_armor_fill_slots(catalog)
    incomplete = frozenset(
        item.id
        for item in catalog
        if item.identification_incomplete
        and not item.evaluable
        and item.id not in identification_exempt_item_ids
    )

    def select(entries, band):
        if finale and entries:
            # The finale's order first (``finale_rank``); the ordinary selection only among
            # the loadouts it holds equal.
            top = max(finale_rank(entry) for entry in entries)
            entries = [entry for entry in entries if finale_rank(entry) == top]
        unscored = launcher_power_unscored is not None and launcher_power_unscored(band)
        return _stable_operational_best(
            entries, current_item_ids, usable_launcher_ids,
            launcher_power=not unscored,
        )

    started = monotonic()
    # Unevaluable items are already excluded by the loadout enumerators.  Keep
    # reporting them so callers can block transaction execution until the
    # catalogue is complete, but still score the known candidates.  Otherwise
    # one unknown Home item suppresses every valid loadout in the catalogue.
    considered = evaluated_count = invalid = 0
    # Valid loadouts are kept per armour-fill tier: the number of
    # ``require_armor_slots`` the loadout fills.  Only the highest non-empty
    # tier competes, so an owned piece for an empty outer/head/arms/feet slot is
    # worn whenever a valid loadout wearing it exists; when none is valid the
    # lower tier still yields a loadout (no new stop).  With no such owned
    # piece every loadout is tier 0 and selection is unchanged.
    evaluated_by_tier: dict[int, dict[tuple[object, ...], EvaluatedLoadout]] = {}
    evaluated_count_by_tier: dict[int, int] = {}
    timed_out = False
    body_static_valid = False
    deferred_bodyless: list[Loadout] = []

    def evaluate_candidate(loadout: Loadout) -> None:
        nonlocal evaluated_count, invalid
        metrics = evaluator(loadout)
        if not _meets_requirements(
            loadout,
            metrics,
            depth=depth,
            intrinsic_abilities=intrinsic_abilities,
            has_destruction=has_destruction,
            require_light=require_light,
            staff_gate=staff_gate,
        ):
            invalid += 1
            return
        entry = EvaluatedLoadout(loadout, metrics)
        evaluated_count += 1
        tier = sum(
            loadout.item_at(slot) is not None for slot in require_armor_slots
        )
        evaluated_count_by_tier[tier] = evaluated_count_by_tier.get(tier, 0) + 1
        evaluated_by_metrics = evaluated_by_tier.setdefault(tier, {})
        equivalence_key = _selection_equivalence_key(entry, current_item_ids)
        incumbent = evaluated_by_metrics.get(equivalence_key)
        if incumbent is None or _prefer(
            entry, incumbent, current_item_ids,
            usable_launcher_ids, finale,
        ):
            evaluated_by_metrics[equivalence_key] = entry

    if candidate_loadouts is None:
        pinned = {
            item.equipped_slot: item
            for item in catalog
            if item.id in current_item_ids
            and item.equipped_slot is not None
            and item.item.is_cursed
        }
        loadouts = enumerate_loadouts(catalog, pinned)
    else:
        loadouts = candidate_loadouts
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
            require_light=require_light,
            staff_gate=staff_gate,
        ):
            invalid += 1
            continue
        # Body armour is mandatory only when a body-filled candidate passes
        # the same static depth gates.  Defer bodyless candidates until that
        # fact is known, without paying for their combat evaluation if it is.
        if require_body and loadout.item_at(SLOT_BODY) is None:
            deferred_bodyless.append(loadout)
            continue
        if require_body:
            body_static_valid = True
        evaluate_candidate(loadout)

    if body_static_valid:
        invalid += len(deferred_bodyless)
    elif not timed_out:
        for loadout in deferred_bodyless:
            if monotonic() - started > timeout_seconds:
                timed_out = True
                break
            evaluate_candidate(loadout)

    fill_tier = max(evaluated_by_tier, default=0)
    for tier, count in evaluated_count_by_tier.items():
        if tier != fill_tier:
            # Valid but leaves an owned armour piece off: rejected like a
            # bodyless set under the body rule.
            evaluated_count -= count
            invalid += count
    evaluated = list(evaluated_by_tier.get(fill_tier, {}).values())
    operational_pool = evaluated
    chosen_depth = None
    band_decisions: list[BandDecision] = []
    chosen_decision = None
    if depth is None and evaluated and not timed_out:
        free_best = _stable_operational_best(
            evaluated, current_item_ids, usable_launcher_ids
        )
        if free_best is None:
            raise RuntimeError("evaluated loadouts have no operational best")
        # Damage per game time (speed_valuation), as _within_half_melee.
        melee_free = max(time_melee(entry.metrics) for entry in evaluated)
        floor_band = (None if destination_floor is None
                      else min((band for band in DEPTH_BANDS if band >= destination_floor),
                               default=DEPTH_BANDS[0]))
        for band in DEPTH_BANDS:
            satisfying = [
                entry
                for entry in evaluated
                if _meets_requirements(
                    entry.loadout,
                    entry.metrics,
                    depth=band,
                    intrinsic_abilities=intrinsic_abilities,
                    has_destruction=has_destruction,
                    require_light=require_light,
                    staff_gate=staff_gate,
                )
            ]
            if not satisfying:
                band_decisions.append(BandDecision(
                    band, False, None, melee_free, "no-set", None,
                ))
                continue
            # The finale asks nothing of melee (owner 2026-11-20 「ACや近接攻撃力は求めない」).
            within_melee_limit = (list(satisfying) if finale
                                  else _within_half_melee(satisfying, melee_free))
            floor_adopted = not within_melee_limit and band == floor_band
            if floor_adopted:
                within_melee_limit = list(satisfying)
            if not within_melee_limit:
                melee = max(time_melee(entry.metrics) for entry in satisfying)
                band_decisions.append(BandDecision(
                    band, True, melee, melee_free, "melee-ratio",
                    melee / melee_free,
                ))
                continue
            band_best = select(within_melee_limit, band)
            if band_best is None:
                band_decisions.append(BandDecision(
                    band, False, None, melee_free, "no-set", None,
                ))
                continue
            melee = time_melee(band_best.metrics)
            ratio = None if melee_free == 0 else melee / melee_free
            chosen_decision = BandDecision(
                band, True, melee, melee_free, None, ratio, floor_adopted,
            )
            band_decisions.append(chosen_decision)
            evaluated = satisfying
            operational_pool = within_melee_limit
            chosen_depth = band
            break
    frontier: list[EvaluatedLoadout] = []
    if not timed_out:
        for entry in evaluated:
            if any(_pareto_dominates(other, entry) for other in frontier):
                continue
            frontier = [
                other
                for other in frontier
                if not _pareto_dominates(entry, other)
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
        best = select(operational_pool, depth if depth is not None else chosen_depth)
        if depth is not None and best is not None:
            chosen_depth = divable_depth(
                best.loadout,
                intrinsic_abilities=intrinsic_abilities,
                has_destruction=has_destruction,
                player_speed=loadout_speed(best.metrics),
                staff_gate=staff_gate,
            )

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
    remaining_ranked = sorted(
        (entry for entry in evaluated if entry is not best),
        key=cmp_to_key(
            lambda left, right: (
                -1 if _prefer(
                    left, right, current_item_ids,
                    usable_launcher_ids, finale,
                )
                else 1 if _prefer(
                    right, left, current_item_ids,
                    usable_launcher_ids, finale,
                )
                else 0
            )
        ),
    )
    ranked = tuple(([best] if best is not None else []) + remaining_ranked[:2])

    # Physical Home disposal uses the capacity-aware R1 slot-local proof in
    # warrior_loadout_search.  Unknown items never reach that proof.
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
        top_candidates=ranked,
        chosen_depth=chosen_depth,
        band_decisions=tuple(band_decisions),
        chosen_decision=chosen_decision,
        chosen_band_entries=() if timed_out else tuple(evaluated),
    )
