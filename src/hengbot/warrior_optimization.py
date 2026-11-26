"""Prepare a fail-closed Warrior loadout optimization and transaction plan."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from time import monotonic
from math import isfinite
from pathlib import Path
from typing import Callable, Iterable, Mapping

from hengbot import ability_sources
from hengbot.equipment_encounters import (
    normal_encounters, ordinary_encounters, representative_encounters,
)
from hengbot.policy_constants import SPEED_GATE_MINIMA
from hengbot.speed_valuation import permanent_player_speed
from hengbot.equipment_optimizer import (
    ABILITY_FLAG,
    DEPTH_BANDS,
    _meets_static_requirements,
    Loadout,
    OptimizationResult,
    OwnedEquipment,
    SLOT_BODY,
    SLOT_LIGHT,
    current_loadout,
    equipment_identity,
    optimizer_item_projection,
    optimize_loadout,
    required_abilities,
    slot_for,
    owned_armor_fill_slots,
    lighting_light_candidate,
    melee_leaders,
)
from hengbot.equipment_transaction_planner import (
    EquipmentTransactionPlan,
    plan_equipment_transactions,
)
from hengbot.equipment_class_profile import EQUIPMENT_CLASS_PROFILES
from hengbot.equipment_utility import with_destruction_means
from hengbot import angband_cap, equipment_rules
from hengbot.me_loadout_offense import (
    finale_power_success, offense_inputs as magic_eater_offense_inputs,
)
from hengbot.model import STAT_NAMES, InventoryItem, Snapshot, StoreItem
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.monster_ranged_evaluator import SpellSelectionContext
from hengbot.protocol import skill_exp_known
from hengbot.saving_throw import saving_base
from hengbot.warrior_defense_evaluator import (
    TR_SPEED,
    WarriorDefenseInputs,
    loadout_armor_class,
)
from hengbot.warrior_equipment_evaluator import (
    WarriorCombatInputs,
    evaluate_warrior_melee,
)
from hengbot.warrior_loadout_evaluator import (
    CachedWarriorLoadoutEvaluator,
    WarriorLoadoutInputs,
    constitution_hp_bonus,
    constitution_with_bonus,
    intelligence_with_bonus,
    max_hp_with_con_bonus,
)
from hengbot.warrior_loadout_search import (
    FinaleFigures,
    enumerate_single_slot_variants,
    enumerate_warrior_loadouts,
    finale_exhaustive_search,
    speed_gates,
)


PLAYER_ABILITY_FLAGS = {
    "free_action": 46,
    "hold_exp": 47,
    "resist_acid": 48,
    "resist_elec": 49,
    "resist_fire": 50,
    "resist_cold": 51,
    "resist_pois": 52,
    "resist_fear": 53,
    "resist_lite": 54,
    "resist_dark": 55,
    "resist_blind": 56,
    "resist_conf": 57,
    "resist_sound": 58,
    "resist_shard": 59,
    "resist_neth": 60,
    "resist_nexus": 61,
    "resist_chaos": 62,
    "resist_disen": 63,
    "levitation": 76,
    # The board's permanent see invisible (a Zombie's, race-info-table.cpp) reaches the
    # intrinsic flags here too, not only through the C screen's calibration: the utility of
    # a worn source is for a character without it (equipment_utility.SEE_INVISIBLE_BONUS).
    "see_invisible": 78,
    "telepathy": 79,
}

REPRESENTATIVE_CATALOG_THRESHOLD = 48
# Catalog size alone has a sharp blind spot: the live 40-item catalog at 18F
# evaluated every loadout against 403 monsters and hit the 25-second timeout
# after 12,288 loadouts.  Keep the existing terminal-scale guards, but also
# bound the item/encounter workload before combinatorial loadout expansion.
REPRESENTATIVE_EVALUATION_WORKLOAD_THRESHOLD = 12_000
# Beyond this owned-catalog size the full combinatorial loadout search explodes:
# a live 51-item catalog at a shallow mining depth (few required abilities to
# prune candidates) produced ~51,000 candidates, timed out the 25 s search, and
# then blew the bot's 90 s decision watchdog inside the evaluator.  At or above
# this size, hill-climb from the confirmed current loadout one slot at a time
# instead (enumerate_single_slot_variants).  Below it, keep the exact search so
# small catalogs still find the global combinatorial optimum.
INCREMENTAL_SEARCH_CATALOG_THRESHOLD = 44
FREE_ACTION_PRESERVE_DEPTH = 10
TR_FREE_ACT = 46
# The strongest-melee sets of the chosen band whose neighbourhoods the
# single-slot closure also expands (owner 2026-11-20, n1-b life-411).
CLOSURE_MELEE_LEADERS = 3
# The whole single-slot closure, every pass and every flag set of one search
# (owner 2026-11-20).  Each pass has the search's 25 s budget, but n1-c
# life-214 needed nine passes and 41.7 s in all; the town decision watchdog is
# 90 s and the same decision also builds the catalog, plans the transaction
# and decides the town step (n1-c 214: about 3 s besides the search on this
# PC, the viewing server is slower).  30 s keeps a third of the watchdog for
# that and for a slower host; a capped search returns its last completed
# pass (``OptimizationResult.search_capped``).
CLOSURE_TIME_CAP_SECONDS = 30.0
# The finale's exhaustive search (finale_seed_loadouts), out of the same cap: n1-c life-221's
# 175-item catalog (2026-11-24) took 0.74 s on this PC; a search stopped here hands on the best
# sets it found.
FINALE_SEARCH_SECONDS = 8.0


def _loadout_key(loadout: Loadout) -> tuple[frozenset[str], str]:
    return loadout.item_ids, loadout.hand_mode


def optimize_single_slot_closure(
    current: Loadout,
    neighbours: Callable[[Loadout], Iterable[Loadout]],
    optimize: Callable[[tuple[Loadout, ...]], OptimizationResult],
    extra_seeds: Iterable[Loadout] = (),
) -> OptimizationResult:
    """Choose over the single-slot neighbourhoods until the choice's own is included.

    The selection is relative to its field (the 95% of the best melee, the
    survival floor, the 1% margin band), so the one-swap neighbourhood of the
    worn loadout alone can choose a set whose own neighbourhood chooses the
    worn one back.  n1-c life-205 2026-11-13 20:06-20:14: with the Gauntlets of
    Slaying worn the Cestus set won (a Gauntlets neighbour at 397.8 melee fell
    under the 30-turn survival floor, so the 95% cut stayed low); with the
    Cestus worn its neighbour at 389.8 melee stayed above the floor, the cut
    rose past the Cestus set, and the Gauntlets won - swapped through Home
    forever.  The field here is the union of the neighbourhoods of every
    chosen set, grown until the chosen set's neighbourhood is in it, so a set
    is moved to only when it is also the choice from its own position: both
    boards above choose over the same union and keep one glove.  The loop ends
    because every pass expands a loadout not expanded before, from a finite
    catalog.  Each pass is one optimization under the search's own time
    budget; the evaluator cache keeps the loadouts already scored.  ``optimize``
    gives each pass what is left of CLOSURE_TIME_CAP_SECONDS; a pass that runs
    out returns the previous pass's result marked ``search_capped``.

    ``extra_seeds`` join the field from the first pass: the finale's exhaustive
    search (warrior_loadout_search.finale_exhaustive_search) puts the sets first
    in its order there, however many slots they change; a chosen one's own
    neighbourhood is expanded in the next pass as any chosen set's.

    The field also holds the neighbourhoods of the CLOSURE_MELEE_LEADERS sets
    with the most melee per game time among the chosen band's sets that clear
    the 30-turn survival floor (owner 2026-11-20 「案A：打撃の上位3つの周りも
    探す」).  The best of them anchors the 95% melee cut, so a set the chosen
    one never neighbours can still decide the choice.  n1-b life-411
    (2026-11-20 06:01, 81F band): with ★運命のオーブ worn the one-swap field
    chose the worn set (1926.7 melee per time, ratio 133.55); its neighbour
    ★飛行石 (1980.2, 130.66) lost inside the 1% ratio band.  The 飛行石 set's
    own neighbour ★炎の鉄ゲタ (2067.4; the boots alone fall to +23 speed,
    under the 81F +25 gate) lifts the cut to 1964 and the 飛行石 set wins -
    and from the 飛行石 set the closure stays.  Both were fixed points of the
    winner-only closure, so the worn one stayed.
    """
    candidates: dict[tuple[frozenset[str], str], Loadout] = {}
    expanded: set[tuple[frozenset[str], str]] = set()
    seeds = [current]
    for seed in extra_seeds:
        candidates.setdefault(_loadout_key(seed), seed)
    previous: OptimizationResult | None = None
    while True:
        for seed in seeds:
            expanded.add(_loadout_key(seed))
            for loadout in neighbours(seed):
                candidates.setdefault(_loadout_key(loadout), loadout)
        result = optimize(tuple(candidates.values()))
        if result.timed_out and previous is not None:
            # The whole-search cap (CLOSURE_TIME_CAP_SECONDS) ran out in this
            # pass: the last completed pass's choice stands.
            return replace(previous, search_capped=True)
        best = result.best
        if best is None or result.timed_out:
            return result
        previous = result
        seeds = []
        for entry in (best, *melee_leaders(
                result.chosen_band_entries, CLOSURE_MELEE_LEADERS)):
            key = _loadout_key(entry.loadout)
            if key not in expanded and all(_loadout_key(seed) != key for seed in seeds):
                seeds.append(entry.loadout)
        if not seeds:
            return result


def finale_seed_loadouts(
    items, inputs: WarriorLoadoutInputs, defense: WarriorDefenseInputs,
    intrinsic_flags: frozenset[int], *, current: Loadout, pinned, excluded_item_ids,
    require_light: bool, require_body: bool, required_flags: frozenset[int],
    depth: int | None, intrinsic_abilities: frozenset[str], has_destruction: bool,
    staff_gate, deadline: float,
) -> tuple[Loadout, ...]:
    """The sets first in the finale's order over every combination of the owned gear
    (warrior_loadout_search.finale_exhaustive_search), from the evaluator's own figures: the
    search's key of a set is its equipment_optimizer ``finale_rank``.  The static requirements
    are the given depth's, else the deepest band's (the finale's 99F/100F)."""
    figures = FinaleFigures(
        base_speed=defense.base_speed,
        intrinsic_flags=intrinsic_flags,
        intelligence=lambda bonus: intelligence_with_bonus(inputs, bonus),
        constitution=lambda bonus: constitution_with_bonus(inputs, bonus),
        max_hp=lambda bonus: max_hp_with_con_bonus(inputs, bonus),
        power_success=lambda bonus, flags: finale_power_success(
            getattr(inputs, "magic_eater", None), bonus, flags),
    )
    band = depth if depth is not None else DEPTH_BANDS[0]
    # The band's abilities the gear must supply (the static requirements' own test), required of
    # every branch so that none is searched without them.
    band_flags = frozenset(ABILITY_FLAG[ability] for ability in required_abilities(band)
                           if ability not in intrinsic_abilities)
    found = finale_exhaustive_search(
        items, figures, current_item_ids=current.item_ids, pinned=pinned,
        excluded_item_ids=excluded_item_ids, require_light=require_light,
        require_body=require_body,
        fill_slots=owned_armor_fill_slots(items, excluded_item_ids),
        required_flags=required_flags | band_flags,
        valid=lambda loadout: _meets_static_requirements(
            loadout, depth=band, intrinsic_abilities=intrinsic_abilities,
            has_destruction=has_destruction, require_light=require_light,
            staff_gate=staff_gate),
        deadline=deadline)
    return found.loadouts


def destination_encounter_depth(snapshot, knowledge, *, cap_lifted: bool = False) -> int:
    """The floor whose monsters an unconstrained search scores against.

    Owner 2026-11-20 (「吸血も評価に入れて直す」, with the population by depth):
    the destination, not the deepest known monster.  n1-b life-411 searched
    against every race up to level 127 although it explores Angband 95F, and
    the 64-race sample held 26% dragons (13% on 95F, 3% of what it met), so
    ★アイシングデス's dragon slaying outscored ★スレイヤー.  The destination is
    the deepest floor reached in any dungeon (each within its cap: angband_cap,
    95F) and the deepest known monster; the deepest known monster when the
    board names no depth.  Not the recall dungeon's own depth: that is often a
    shallow side dungeon (n1-c life-205 recalled to 23F with 80F reached in
    Angband, n1-a life-525 to 13F with 50F reached).

    ``cap_lifted`` (angband_finale ``lifted``, owner 2026-11-20): the 95F cap no longer holds
    for this character, so Angband's depth is read as reached.
    """
    deepest_known = max((monster.level for monster in knowledge.values()), default=1)
    reached = [
        depth if cap_lifted or (cap := angband_cap.cap(dungeon_id)) is None else min(depth, cap)
        for dungeon_id, depth in getattr(snapshot, "dungeon_recall_depths", {}).items()
        if depth
    ]
    landing = max(reached, default=getattr(snapshot, "recall_depth", 0))
    if not landing:
        return deepest_known
    return max(1, min(landing, deepest_known))


def blocker_leaves_no_target(blocker: str) -> bool:
    """The optimizer was skipped or gave up, so no target exists: the worn kit stays.

    Calibration and search time control optimization, never ordinary movement: this
    is no Home work and no stop.  n1-a life-480 2026-11-04 21:07: the exact search of
    a 43-item catalog (83,968 loadouts) ran out of its 25 seconds with no other
    departure leaf unmet, and three retired visits ended the life.
    """
    return (blocker in {"calibration-required", "optimization-timeout"}
            or blocker.startswith("calibration-stale:"))


def free_action_wearable(
    items,
    required_flags: frozenset[int],
    intrinsic_abilities: frozenset[str],
    search_excluded_item_ids: frozenset[str],
) -> bool:
    """Whether the search must keep an owned Free Action item on at any depth.

    Owner 2026-11-09 (n1-a life-501, a Lv17 warrior without Free Action chain-
    paralysed on 13F), verbatim: 「浅い階で要求しても達成できないので要求階層は
    今のまま。…耐麻痺装備をたまたま浅い階から拾っていたら装備することを確認
    する。」  The depth requirement (DEPTH_ABILITY_REQUIREMENTS) asks for Free
    Action from 20F; above it the evaluator values the flag only as the paralysis
    exposure of its encounters (warrior_defense_evaluator), a tie-break the DPS
    and margin bands come before, so Gloves or Boots of Free Action lost to a
    pair with more AC.  An owned Free Action item the search may wear is
    therefore required as the depth requirement requires it from 20F."""
    if "free_action" in intrinsic_abilities or TR_FREE_ACT in required_flags:
        return False
    return any(
        TR_FREE_ACT in item.flags
        and item.exploration_legal
        and item.id not in search_excluded_item_ids
        for item in items
    )


def optimization_encounters(
    encounters: tuple,
    *,
    catalog_size: int,
) -> tuple:
    """Bound encounter cost once owned equipment makes the search large."""
    if (
        len(encounters) > 512
        or catalog_size >= REPRESENTATIVE_CATALOG_THRESHOLD
        or catalog_size * len(encounters)
        >= REPRESENTATIVE_EVALUATION_WORKLOAD_THRESHOLD
    ):
        return representative_encounters(encounters)
    return encounters


@dataclass(frozen=True)
class CharacterCalibration:
    """Worn-independent constants from an equipped visible C-sheet (schema 2).

    Schema 1 is retained for historical comparison and diagnostic unit tests;
    the live policy accepts only session-correlated schema-2 observations.
    """

    race_id: int
    class_id: int
    personality_id: int
    level: int
    stat_cur: tuple[int, ...]
    base_stats: tuple[int, ...]
    base_hp: int
    base_ac_bonus: int
    intrinsic_abilities: frozenset[str]
    pinned_identities: tuple[tuple[str, str], ...] = ()
    observed_turn: int = 0
    # Sorted mutation ids from the equipped `C` character snapshot at capture
    # time (the periodic status dump refreshes the live observation); None
    # when no mutation observation was available yet.
    mutation_signature: tuple[int, ...] | None = None
    # Permanent TR flag ids read off the `C` character snapshot's
    # characteristics table (player/immunity/vulnerability columns).  These
    # carry what the 19-boolean abilities set cannot express — permanent
    # elemental vulnerabilities and immunities, sustains, TR_RES_TIME and the
    # rest — and become worn-independent search input.
    intrinsic_tr_flags: frozenset[int] = frozenset()

    schema_version: int = 1
    source: str = "legacy-strip"
    natural_stats: tuple[int, ...] = ()
    intrinsic_adjustments: tuple[int, ...] = ()
    hp_floor: int = 1
    evidence_hash: str = ""
    response_sequence: int | str | None = None
    protocol_version: int = 0
    stat_key_kind: str = "legacy"
    visible_stat_key: tuple[int, ...] = ()
    session_id: str = ""
    intrinsic_capabilities: frozenset[str] = frozenset()

    def stale_reason(
        self,
        player,
        pinned_identities: tuple[tuple[str, str], ...],
        *,
        mutation_signature: tuple[int, ...] | None = None,
    ) -> str | None:
        """First reason the cached constants no longer describe this character.

        The invalidation triggers are exactly the approved list: character
        identity, level change, ``stat_cur`` change (augmentation / drain),
        mutation gain or loss (observed through the `C` character snapshots —
        the periodic status dump the bot already posts), and a change in the pinned (cursed worn) set.  Pass
        ``mutation_signature=None`` when no mutation observation exists yet;
        an observed signature that differs from the recorded one — including
        a capture made before any observation — invalidates the cache.
        """
        if (
            player.race_id != self.race_id
            or player.class_id != self.class_id
            or player.personality_id != self.personality_id
        ):
            return "character-identity"
        if player.level != self.level:
            return "level"
        if self.schema_version == 2:
            if player.mimic_form:
                return "unsupported-active-form"
            if player.printed_stat_cur_key != self.visible_stat_key:
                return "visible-stat-key"
        elif player.stat_cur is not None:
            if tuple(player.stat_cur) != self.stat_cur:
                return "stat_cur"
        elif player.printed_stat_cur_key != self.stat_cur:
            # Protocol 3 prints no raw stat_cur; compare the printed key
            # (max, negated when drained).  A protocol-2 calibration's
            # stat_cur matches it exactly when the natural stats are the
            # recorded ones and undrained.
            return "stat_cur"
        if tuple(pinned_identities) != self.pinned_identities:
            return "pinned-set"
        if (
            mutation_signature is not None
            and mutation_signature != self.mutation_signature
        ):
            return "mutations"
        return None


def loadout_natural_stats(calibration: CharacterCalibration, player) -> tuple[int, ...]:
    """The calibration's natural stats with each drained stat at its printed maximum.

    A drain lowers ``stat_cur`` below ``stat_max`` until a restore puts it back
    (base-status.cpp res_stat: ``stat_cur = stat_max``), and the town visit drinks the
    restore (policy_shop ``_stat_restore_quaff_key``).  The loadout is the character's,
    so the selector reads the maximum the board prints (bot-json-output.cpp ``max``) for a
    drained stat, never the drained value: n1-b life-413 2026-11-22 (Q25 done, STR drained
    84 -> 74) took off 腕力の指輪 (+5) for 殺戮の指輪 (+13,+7) at the drained STR, drank
    腕力復活の薬 in the same visit, and the search on the restored STR put the strength ring
    back (decision 373, ``town:blocked:equipment-slot-flipflop:main_ring``).  A legacy
    calibration without natural stats keeps its base stats (another scale).
    """
    if not calibration.natural_stats:
        return calibration.base_stats
    drained = frozenset(player.drained_stats)
    maxima = tuple(player.stat_max)
    return tuple(
        max(value, maxima[index])
        if index < len(maxima) and index < len(STAT_NAMES) and STAT_NAMES[index] in drained
        else value
        for index, value in enumerate(calibration.natural_stats)
    )


@dataclass(frozen=True)
class ConfirmedLoadoutRecord:
    """A live worn set recorded only after optimization genuinely completes."""

    item_ids: frozenset[str]
    optimizer_input_key: str


def confirmed_loadout_record(
    item_ids: frozenset[str],
    optimizer_input_key: str,
) -> ConfirmedLoadoutRecord:
    return ConfirmedLoadoutRecord(
        item_ids=frozenset(item_ids),
        optimizer_input_key=optimizer_input_key,
    )


def save_confirmed_loadout(path: Path, record: ConfirmedLoadoutRecord) -> bool:
    data = asdict(record)
    data["item_ids"] = sorted(record.item_ids)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except OSError:
        return False


def load_confirmed_loadout(path: Path) -> ConfirmedLoadoutRecord | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        item_ids = frozenset(str(value) for value in data["item_ids"])
        optimizer_input_key = data["optimizer_input_key"]
        if (
            not item_ids
            or not isinstance(optimizer_input_key, str)
            or len(optimizer_input_key) != 64
            or any(
                character not in "0123456789abcdef"
                for character in optimizer_input_key
            )
        ):
            return None
        return ConfirmedLoadoutRecord(
            item_ids=item_ids,
            optimizer_input_key=optimizer_input_key,
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _canonical_optimizer_input(value):
    """Return a JSON-safe, ordering-stable representation of optimizer input."""
    if hasattr(value, "__dataclass_fields__"):
        return {
            field: _canonical_optimizer_input(getattr(value, field))
            for field in value.__dataclass_fields__
        }
    if isinstance(value, Mapping):
        return [
            (_canonical_optimizer_input(key), _canonical_optimizer_input(item))
            for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
        ]
    if isinstance(value, (set, frozenset)):
        members = [_canonical_optimizer_input(item) for item in value]
        return sorted(members, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (tuple, list)):
        return [_canonical_optimizer_input(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported optimizer input type: {type(value).__qualname__}")


def warrior_optimizer_knowledge_key(
    knowledge: Mapping[int, MonraceKnowledge],
) -> str:
    """Digest immutable monster knowledge once for reuse by per-state keys."""
    encoded = json.dumps(
        _canonical_optimizer_input(knowledge),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def warrior_optimizer_input_key(
    snapshot: Snapshot,
    items: tuple[OwnedEquipment, ...],
    knowledge: Mapping[int, MonraceKnowledge],
    *,
    depth: int | None,
    home_scan_complete: bool,
    has_destruction: bool,
    preserve_pack_item_ids: frozenset[str],
    search_excluded_item_ids: frozenset[str],
    calibration: CharacterCalibration | None,
    identification_exempt_item_ids: frozenset[str] = frozenset(),
    knowledge_key: str | None = None,
    curse_pinned_item_ids: frozenset[str] = frozenset(),
    magic_eater_powers: tuple[tuple[str, int], ...] = (),
    staff_gate=None,
    finale: bool = False,
    cap_lifted: bool = False,
    destination_floor: int | None = None,
) -> str:
    """Digest every semantic input consumed by preparation and planning."""
    player = snapshot.player
    inputs = {
        # The owner's equipment rules (equipment_rules.RULES_VERSION, a digest of that table):
        # changing a rule makes a confirmation or cache of an earlier search stale.
        "schema": equipment_rules.RULES_VERSION,
        "items": tuple(sorted(
            (optimizer_item_projection(item) for item in items),
            key=lambda projection: projection[0],
        )),
        "knowledge_key": knowledge_key or warrior_optimizer_knowledge_key(knowledge),
        "depth": depth,
        "home_scan_complete": home_scan_complete,
        "has_destruction": has_destruction,
        "preserve_pack_item_ids": preserve_pack_item_ids,
        "search_excluded_item_ids": search_excluded_item_ids,
        "identification_exempt_item_ids": identification_exempt_item_ids,
        "calibration": calibration,
        "current_pack_items": len(snapshot.inventory),
        "player": {
            "race_id": player.race_id,
            "class_id": player.class_id,
            "personality_id": player.personality_id,
            "level": player.level,
            "stat_cur": (
                player.stat_cur
                if player.stat_cur is not None
                else player.printed_stat_cur_key
            ),
            "speed": player.speed,
            "melee_skill": player.melee_skill,
            "shooting_skill": getattr(player, "shooting_skill", player.melee_skill),
            "saving_skill": player.saving_skill,
            "two_weapon_skill": player.two_weapon_skill,
            "shield_skill": player.shield_skill,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        },
    }
    if curse_pinned_item_ids:
        # Only present when set, so every key without a pin stays as it was.
        inputs["curse_pinned_item_ids"] = curse_pinned_item_ids
    if destination_floor is not None:
        # Only present when set (destination_band_floor), as the pin above.
        inputs["destination_floor"] = destination_floor
    if magic_eater_powers and player.class_id == 16:
        # Class 16 scores its held powers (me_loadout_offense); only
        # present then, so every other key stays as it was.
        inputs["magic_eater_powers"] = tuple(magic_eater_powers)
    if staff_gate is not None:
        # Only present with an owned *Destruction* staff, so every other key
        # stays as it was.
        inputs["staff_gate"] = staff_gate.key()
    if finale or cap_lifted:
        # The 99F/100F loadout (angband_finale): only present then.
        inputs["angband_finale"] = (finale, cap_lifted)
    encoded = json.dumps(
        _canonical_optimizer_input(inputs),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def character_intrinsic_flags(characteristics) -> frozenset[int]:
    """Permanent player columns; resistance-keyed immune/vulnerable rows map to TRs."""
    flags: set[int] = set()
    for row in characteristics or ():
        if not isinstance(row, dict):
            continue
        try:
            flag_id = int(row.get("flag_id"))
        except (TypeError, ValueError):
            continue
        if bool(row.get("player")):
            flags.add(flag_id)
        if bool(row.get("immunity")):
            immunity = {48: 40, 49: 41, 50: 42, 51: 43}.get(flag_id)
            if immunity is not None:
                flags.add(immunity)
        if bool(row.get("vulnerability")):
            vulnerability = {48: 152, 49: 154, 50: 155, 51: 153}.get(flag_id)
            if vulnerability is not None:
                flags.add(vulnerability)
    return frozenset(flags)


def calibrate_character_constants(
    snapshot: Snapshot,
    *,
    mutation_signature: tuple[int, ...] | None = None,
    intrinsic_tr_flags: frozenset[int] = frozenset(),
) -> CharacterCalibration | None:
    """Historical schema-1 diagnostic; never called by the live policy.

    Returns None unless every worn item is unremovable (cursed): a removable
    item still worn means the strip phase has not finished and the observation
    would be contaminated.  The caller (execution layer) owns every other
    precondition: town, temporary statuses clear, no visible hostiles, HP full.
    """
    player = snapshot.player
    if not skill_exp_known(player, ("shield_skill",)):
        # Protocol 3 before the ~f skill list was read: not observable yet.
        return None
    removable = [
        item
        for item in snapshot.equipment
        if item.is_equipment and not item.is_cursed
    ]
    if removable:
        return None
    natural = player.stat_cur if player.stat_cur is not None else player.stat_max
    if len(natural) < 6 or len(player.stat_use) < 6:
        return None
    if player.stat_use[0] <= 0 or player.stat_use[3] <= 0 or player.stat_use[4] <= 0:
        return None
    base_stats = tuple(player.stat_use)
    naked = current_loadout(())
    naked_defense = WarriorDefenseInputs(
        level=player.level,
        natural_dex=base_stats[3],
        shield_skill=player.shield_skill,
        base_speed=player.speed,
        saving_skill=player.saving_skill,
    )
    base_ac_bonus = player.ac - loadout_armor_class(naked, naked_defense)
    base_hp = max(
        1,
        player.max_hp - constitution_hp_bonus(base_stats[4], player.level),
    )
    pinned_identities = tuple(
        sorted(
            (item.slot, equipment_identity(item))
            for item in snapshot.equipment
            if item.is_equipment and item.is_cursed
        )
    )
    return CharacterCalibration(
        race_id=player.race_id,
        class_id=player.class_id,
        personality_id=player.personality_id,
        level=player.level,
        # Protocol 3 prints no raw stat_cur: record the printed key instead
        # (the max, negated when drained), which stale_reason compares.
        stat_cur=(
            tuple(player.stat_cur)
            if player.stat_cur is not None
            else player.printed_stat_cur_key
        ),
        base_stats=base_stats,
        base_hp=base_hp,
        base_ac_bonus=base_ac_bonus,
        intrinsic_abilities=_effective_intrinsic_abilities(
            player, frozenset(ability_sources.held_abilities(player))
        ),
        pinned_identities=pinned_identities,
        observed_turn=getattr(snapshot, "turn", 0),
        mutation_signature=mutation_signature,
        intrinsic_tr_flags=frozenset(intrinsic_tr_flags),
    )


def save_character_calibration(path: Path, calibration: CharacterCalibration) -> None:
    data = asdict(calibration)
    data["intrinsic_abilities"] = sorted(calibration.intrinsic_abilities)
    data["pinned_identities"] = [list(pair) for pair in calibration.pinned_identities]
    data["intrinsic_tr_flags"] = sorted(calibration.intrinsic_tr_flags)
    data["intrinsic_capabilities"] = sorted(calibration.intrinsic_capabilities)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Never erase an old physical obligation while publishing observations.
        # Startup refuses such a file; this guard only keeps a file restored
        # later intact, and never raises into response dispatch.
        from hengbot.policy_calibration import legacy_calibration_file_debt
        if legacy_calibration_file_debt(path):
            return
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        temporary.replace(path)
    except OSError:
        # Persistence is an optimization; the in-memory calibration stays valid.
        return


def load_character_calibration(path: Path) -> CharacterCalibration | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        calibration = CharacterCalibration(
            race_id=int(data["race_id"]),
            class_id=int(data["class_id"]),
            personality_id=int(data["personality_id"]),
            level=int(data["level"]),
            stat_cur=tuple(int(v) for v in data["stat_cur"]),
            base_stats=tuple(int(v) for v in data["base_stats"]),
            base_hp=int(data["base_hp"]),
            base_ac_bonus=int(data["base_ac_bonus"]),
            intrinsic_abilities=frozenset(
                str(v) for v in data["intrinsic_abilities"]
            ),
            pinned_identities=tuple(
                (str(slot), str(identity))
                for slot, identity in data.get("pinned_identities", [])
            ),
            observed_turn=int(data.get("observed_turn", 0)),
            mutation_signature=(
                tuple(int(v) for v in data["mutation_signature"])
                if data.get("mutation_signature") is not None
                else None
            ),
            intrinsic_tr_flags=frozenset(
                int(v) for v in data.get("intrinsic_tr_flags", [])
            ),
            schema_version=int(data.get("schema_version", 1)),
            source=str(data.get("source", "legacy-strip")),
            natural_stats=tuple(int(v) for v in data.get("natural_stats", ())),
            intrinsic_adjustments=tuple(int(v) for v in data.get("intrinsic_adjustments", ())),
            hp_floor=int(data.get("hp_floor", 1)),
            evidence_hash=str(data.get("evidence_hash", "")),
            response_sequence=data.get("response_sequence"),
            protocol_version=int(data.get("protocol_version", 0)),
            stat_key_kind=str(data.get("stat_key_kind", "legacy")),
            visible_stat_key=tuple(int(v) for v in data.get("visible_stat_key", ())),
            session_id=str(data.get("session_id", "")),
            intrinsic_capabilities=frozenset(str(v) for v in data.get("intrinsic_capabilities", [])),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if calibration.schema_version == 2 and (
        calibration.source != "equipped-c-screen"
        or any(len(values) != 6 for values in (
            calibration.natural_stats, calibration.intrinsic_adjustments,
            calibration.base_stats, calibration.visible_stat_key))
        or not calibration.session_id
    ):
        return None
    return calibration


@dataclass(frozen=True)
class WarriorOptimizationPreparation:
    current: Loadout
    result: OptimizationResult | None
    transaction: EquipmentTransactionPlan | None
    blockers: tuple[str, ...]
    encounters_total: int = 0
    encounters_evaluated: int = 0

    @property
    def ready(self) -> bool:
        return not self.blockers and self.transaction is not None


@dataclass
class WarriorEvaluatorCache:
    """Reuse exact component evaluations while the combat context is stable."""

    context: tuple[object, ...] | None = None
    evaluator: CachedWarriorLoadoutEvaluator | None = None

    def get(
        self,
        inputs: WarriorLoadoutInputs,
        encounters: tuple,
        offense_encounters: tuple | None = None,
    ) -> CachedWarriorLoadoutEvaluator:
        normalized_inputs = (
            replace(inputs, current_hp=0)
            if inputs.base_hp is not None
            else inputs
        )
        context = (normalized_inputs, encounters, offense_encounters)
        if self.context != context or self.evaluator is None:
            self.context = context
            self.evaluator = CachedWarriorLoadoutEvaluator(
                inputs, encounters, offense_encounters)
        return self.evaluator

def weapon_expected_dps(
    snapshot: Snapshot,
    weapon,
    reference_ac: int,
    calibration: CharacterCalibration | None,
    *,
    current_proficiency: bool = False,
) -> float | None:
    """Score both wielded hands against a visible, non-immune neutral target.

    Use the same single-application stat inputs as the loadout selector.
    Without a calibration the expected score is unavailable.
    The worn slot layout itself is a legitimate physical input here: the
    question asked is "this weapon in MY current off-hand configuration".
    """
    if calibration is None or not skill_exp_known(snapshot.player, ("two_weapon_skill",)):
        # Unknown two-weapon skill_exp (protocol 3 before ~f) is as
        # unknowable as a missing calibration: fail closed.
        return None
    equipped = tuple(
        OwnedEquipment(
            f"equipped:{index}", item, "equipped", equipped_slot=item.slot
        )
        for index, item in enumerate(snapshot.equipment)
        if item.is_equipment
    )
    current = current_loadout(equipped)
    natural = loadout_natural_stats(calibration, snapshot.player)
    inputs = WarriorCombatInputs(
        level=snapshot.player.level,
        class_id=snapshot.player.class_id,
        natural_str=natural[0],
        natural_dex=natural[3],
        intrinsic_str=calibration.intrinsic_adjustments[0] if calibration.natural_stats else 0,
        intrinsic_dex=calibration.intrinsic_adjustments[3] if calibration.natural_stats else 0,
        melee_skill=snapshot.player.melee_skill,
        two_weapon_skill=snapshot.player.two_weapon_skill,
    )
    replacement = OwnedEquipment("sale-candidate", weapon, "pack")
    slots = tuple(
        (slot, owned) for slot, owned in current.slots if slot != "main_hand"
    ) + (("main_hand", replacement),)
    sub = current.item_at("sub_hand")
    hand_mode = (
        current.hand_mode
        if sub is not None
        else "two_handed" if weapon.tval == 22 or weapon.weight > 99 else "one_handed"
    )
    melee = evaluate_warrior_melee(
        Loadout(tuple(sorted(slots)), hand_mode),
        inputs,
        target_ac=reference_ac,
        neutral_target_brands=True,
        current_proficiency=current_proficiency,
    )
    return sum(hand.expected_damage_per_round for hand in melee.hands)


def _intrinsic_flags(abilities: frozenset[str]) -> frozenset[int]:
    return frozenset(
        flag for name, flag in PLAYER_ABILITY_FLAGS.items() if name in abilities
    )


def _equipment_speed(loadout: Loadout) -> int:
    # Deliberately the only worn de-gearing left in this module: it is linear
    # and exact (roadmap P1 requirement 4).  The stat de-gearing helpers
    # (_base_stat_without_current_gear, _conservative_intrinsic_abilities)
    # were deleted with the legacy derivation: every stat/ability constant now
    # comes from the calibration observation, and no per-call
    # modify_stat_value inversion exists anywhere in production.
    return sum(
        item.item.pval for _, item in loadout.slots if TR_SPEED in item.flags
    )


def _effective_intrinsic_abilities(
    player: object, stored: frozenset[str]
) -> frozenset[str]:
    """Prefer permanent source flags; fall back only for flat snapshots."""
    sources_by_ability = ability_sources.ability_source_map(player)
    if sources_by_ability:
        return frozenset(
            ability
            for ability, sources in sources_by_ability.items()
            if "permanent" in sources
        )
    return stored


def optimization_blockers(
    snapshot: Snapshot,
    items: tuple[OwnedEquipment, ...],
    knowledge: Mapping[int, MonraceKnowledge],
    *,
    home_scan_complete: bool,
    calibration: CharacterCalibration | None,
) -> tuple[str, ...]:
    """Why the loadout search cannot run on this board (``()``: it can).

    ``prepare_warrior_optimization`` returns these as its blockers before it searches; the
    visit's fixed target (policy_equipment, equipment review E3) reads the same ones, so a
    board the search would refuse is refused with the target held, too.
    """
    blockers: list[str] = []
    player = snapshot.player
    if player.class_id not in EQUIPMENT_CLASS_PROFILES:
        blockers.append("unsupported-class")
    # Protocol 3 prints no raw stat_cur; the printed natural max stands in.
    natural = player.stat_cur if player.stat_cur is not None else player.stat_max
    if len(natural) < 4 or natural[0] <= 0 or natural[3] <= 0:
        blockers.append("missing-natural-stats")
    if not skill_exp_known(player):
        # Protocol 3: the ~f skill list has not been read yet.
        blockers.append("skill-exp-unknown")
    if not knowledge:
        blockers.append("missing-monrace-knowledge")
    if not home_scan_complete:
        blockers.append("home-scan-incomplete")
    if calibration is None:
        # P1: the worn-independent constants are a MANDATORY input of the
        # selector.  There is deliberately no fallback derivation from the
        # geared snapshot — that reconstruction (per-call modify_stat_value
        # inversion, ADJ_DEX_TO_AC subtraction of the worn set) is the measured
        # impurity this stage removes, so its absence fails closed here at the
        # selector boundary, not just in the policy wrapper.
        blockers.append("calibration-required")
    else:
        pinned_identities = tuple(
            sorted(
                (item.equipped_slot or "", equipment_identity(item.item))
                for item in items
                if item.origin == "equipped" and item.item.is_cursed
            )
        )
        stale = calibration.stale_reason(player, pinned_identities)
        if stale is not None:
            blockers.append(f"calibration-stale:{stale}")
    return tuple(blockers)


def prepare_warrior_optimization(
    snapshot: Snapshot,
    items: tuple[OwnedEquipment, ...],
    knowledge: Mapping[int, MonraceKnowledge],
    *,
    depth: int | None,
    home_scan_complete: bool,
    has_destruction: bool = False,
    preserve_pack_item_ids: frozenset[str] = frozenset(),
    search_excluded_item_ids: frozenset[str] = frozenset(),
    identification_exempt_item_ids: frozenset[str] = frozenset(),
    timeout_seconds: float = 25.0,
    loadout_report_path: Path | None = None,
    evaluator_cache: WarriorEvaluatorCache | None = None,
    calibration: CharacterCalibration | None = None,
    obtainable_ammunition: tuple[InventoryItem | StoreItem, ...] | None = None,
    curse_pinned_item_ids: frozenset[str] = frozenset(),
    magic_eater_powers: tuple[tuple[str, int], ...] = (),
    staff_gate=None,
    finale: bool = False,
    cap_lifted: bool = False,
    destination_floor: int | None = None,
) -> WarriorOptimizationPreparation:
    """Evaluate and plan without emitting any game command.

    ``destination_floor`` (destination_band_floor): the depth-band descent's floor, passed to
    ``optimize_loadout``.

    ``staff_gate`` (device_skill.StaffGate): an owned *Destruction* staff that is
    the 50F+ means of a loadout whose device skill makes it reliable; the search
    then also builds the sets that reach that skill (WarriorSingleSlotSearch's
    device-skill completions).

    ``magic_eater_powers`` are the (kind, sval) of the held absorbed attack
    and survival powers (me_loadout_offense.held_magic_eater_powers); class 16
    scores their INT-dependent fail rate as ``device_dps`` and on the survival
    side, with the escape reliability lost to blindness (owner 2026-11-08).

    ``curse_pinned_item_ids`` are worn items the player saw cursed although
    the board does not say ``is_cursed`` (an unidentified item: a cursed
    pseudo feeling, or the game refused its takeoff); they stay in their slot
    like a known cursed item.

    ``finale`` (angband_finale ``preparing``, owner 2026-11-20): the 99F/100F loadout's order
    (equipment_optimizer ``finale_rank``) decides; ``cap_lifted``: the 95F cap is lifted, so
    the destination's monsters are read past it.
    """
    current = current_loadout(items)
    player = snapshot.player
    blockers = optimization_blockers(
        snapshot, items, knowledge, home_scan_complete=home_scan_complete,
        calibration=calibration)
    # The banned pieces (equipment_rules.LOADOUT_BANNED_FLAGS: owner 2026-11-21 「99F 100Fでも
    # 宵闇のローブは禁止」) are in no loadout, ordinary or the finale's, at any depth; out of the
    # search, a worn one is taken off by the next town's swap (n1-b life-411 2026-11-21 wore one
    # on 95F).
    search_excluded_item_ids = search_excluded_item_ids | equipment_rules.loadout_banned_item_ids(items)
    if blockers:
        return WarriorOptimizationPreparation(current, None, None, blockers)

    encounter_depth = (
        depth if depth is not None
        else destination_encounter_depth(snapshot, knowledge, cap_lifted=cap_lifted)
    )
    all_encounters = normal_encounters(knowledge, encounter_depth)
    if not all_encounters:
        return WarriorOptimizationPreparation(
            current, None, None, ("empty-encounter-set",)
        )
    encounters = optimization_encounters(
        all_encounters,
        catalog_size=len(items),
    )
    # The melee side reads the whole ordinary pool when the defense reads a
    # sample (CachedWarriorLoadoutEvaluator.offense_encounters).
    offense_encounters = (
        None if encounters is all_encounters else ordinary_encounters(all_encounters))

    # P1: every character constant comes from the unequipped calibration
    # observation, never from de-gearing the currently worn snapshot.  The
    # worn partition of the owned multiset can no longer move the answer
    # through ADJ_DEX_TO_AC steps (base_ac_bonus), the non-injective
    # modify_stat_value scale (base stats / base_hp), or ability shadowing
    # (intrinsic set).  There is no legacy derivation here by design.
    # The live per-source format is more authoritative than a calibration
    # written by the former dict-as-true parser.  Preserve the stored numeric,
    # identity, and TR-flag constants, but never let its contaminated ability
    # list reach selection after source detail is available.
    intrinsic_abilities = _effective_intrinsic_abilities(
        player, calibration.intrinsic_abilities
    )
    # A drained stat at its maximum (loadout_natural_stats): the visit restores it.
    stats = loadout_natural_stats(calibration, player)
    adjustments = calibration.intrinsic_adjustments or (0,) * 6
    base_str = stats[0]
    base_dex = stats[3]
    base_con = stats[4]
    base_hp = calibration.base_hp
    base_ac_bonus = calibration.base_ac_bonus
    # Source-separated characteristics enrich the intrinsic flag set with
    # what the abilities booleans cannot express.  Consumed today by the
    # defense model: TR_IM_* (zero elemental damage), TR_VUL_* (+1/3 damage),
    # TR_SUST_* (drain exposure) and TR_RES_TIME; telepathy and the ESP kinds
    # by equipment_utility (an intrinsic one levels every loadout); every
    # other recorded flag (slays, brands, ...) has no evaluator consumer yet
    # and is deliberately carried without invented scoring.
    intrinsic_flags = (
        _intrinsic_flags(intrinsic_abilities) | calibration.intrinsic_tr_flags
    )
    # Speed is deliberately NOT calibrated: its de-gearing is linear and exact,
    # and a stripped observation would fold the changed carried weight into the
    # base (roadmap P1 requirement 4).
    defense = WarriorDefenseInputs(
        level=player.level,
        natural_dex=base_dex,
        intrinsic_dex=adjustments[3],
        shield_skill=player.shield_skill,
        base_ac_bonus=base_ac_bonus,
        # The permanent speed (speed_valuation): a haste or slowness at the
        # board is not the loadout's.
        base_speed=permanent_player_speed(snapshot) - _equipment_speed(current),
        saving_skill=player.saving_skill,
        intrinsic_flags=intrinsic_flags,
    )
    inputs = WarriorLoadoutInputs(
        combat=WarriorCombatInputs(
            level=player.level,
            class_id=player.class_id,
            natural_str=base_str,
            natural_dex=base_dex,
            intrinsic_str=adjustments[0],
            intrinsic_dex=adjustments[3],
            melee_skill=player.melee_skill,
            shooting_skill=getattr(player, "shooting_skill", player.melee_skill),
            two_weapon_skill=player.two_weapon_skill,
        ),
        defense=defense,
        current_hp=max(1, player.max_hp),
        # This represents an ordinary neutral encounter, not live hidden state.
        spell_selection=SpellSelectionContext(
            player_has_mana=player.max_mp > 0,
        ),
        natural_con=base_con,
        intrinsic_con=adjustments[4],
        hp_floor=calibration.hp_floor,
        base_hp=base_hp,
        magic_eater=magic_eater_offense_inputs(
            player.class_id, player.level, stats[1], adjustments[1],
            calibration.personality_id, magic_eater_powers),
        # The saving throw per loadout (saving_throw): the board's value is the
        # worn loadout's, so its gear terms are taken out once here.
        saving_base=saving_base(
            player.saving_skill, current, level=player.level,
            natural_wis=stats[2], intrinsic_wis=adjustments[2],
            intrinsic_flags=intrinsic_flags),
        natural_wis=stats[2],
        intrinsic_wis=adjustments[2],
    )
    evaluator = (
        evaluator_cache.get(inputs, encounters, offense_encounters)
        if evaluator_cache is not None
        else CachedWarriorLoadoutEvaluator(inputs, encounters, offense_encounters)
    )
    pinned = {
        item.equipped_slot: item
        for item in items
        if item.id in current.item_ids
        and item.equipped_slot is not None
        and (item.item.is_cursed or item.id in curse_pinned_item_ids)
    }
    required_candidate_flags = {
        ABILITY_FLAG[ability]
        for ability in (required_abilities(depth) if depth is not None else ())
        if ability not in intrinsic_abilities
    }
    # Once paralysis is a live dungeon risk, an optimizer transaction must not
    # discard free action that the current loadout already owns merely because
    # a mundane armor piece gains a few points of AC. Another slot may replace
    # the flag, but the resulting complete loadout must retain it.
    if (
        depth is not None
        and depth >= FREE_ACTION_PRESERVE_DEPTH
        and TR_FREE_ACT in current.flags
    ):
        required_candidate_flags.add(TR_FREE_ACT)
    search_factory = (
        enumerate_single_slot_variants
        if len(items) >= INCREMENTAL_SEARCH_CATALOG_THRESHOLD
        else enumerate_warrior_loadouts
    )
    require_light = any(
        item.id not in search_excluded_item_ids
        and lighting_light_candidate(item)
        for item in items
    )
    require_body = any(
        item.id not in search_excluded_item_ids
        and item.exploration_legal
        and slot_for(item.item) == SLOT_BODY
        for item in items
    )
    required_flags = frozenset(required_candidate_flags)
    # The depth abilities the items must supply: a set that adds one of them
    # (the next band's) while another slot keeps every one worn is searched
    # as a pair (WarriorSingleSlotSearch's requirement repairs).
    repair_flags = frozenset(
        flag for ability, flag in ABILITY_FLAG.items()
        if ability not in intrinsic_abilities
    )
    flag_sets = [required_flags]
    if free_action_wearable(
        items, required_flags, intrinsic_abilities, search_excluded_item_ids
    ):
        # Free Action first; when no complete loadout can wear it (a cursed
        # piece pinned in its slot, say), the search without it stands.
        flag_sets.insert(0, required_flags | {TR_FREE_ACT})
    closure_deadline = monotonic() + CLOSURE_TIME_CAP_SECONDS
    for flags in flag_sets:
        def optimize(candidates):
            budget = timeout_seconds
            if search_factory is enumerate_single_slot_variants:
                budget = max(0.0, min(timeout_seconds, closure_deadline - monotonic()))
            return optimize_loadout(
                items,
                # Owner 2026-11-15 「深さに関係なく持っていく」: a set that makes an owned
                # *Destruction* staff reliable earns its utility at every depth.
                lambda loadout: with_destruction_means(
                    evaluator(loadout).metrics, loadout, staff_gate),
                depth=depth,
                intrinsic_abilities=intrinsic_abilities.intersection(ABILITY_FLAG),
                has_destruction=has_destruction,
                current_item_ids=current.item_ids,
                timeout_seconds=budget,
                candidate_loadouts=candidates,
                require_light=require_light,
                require_body=require_body,
                require_armor_slots=owned_armor_fill_slots(
                    items, search_excluded_item_ids
                ),
                identification_exempt_item_ids=identification_exempt_item_ids,
                finale=finale,
                obtainable_ammunition=(
                    tuple(snapshot.inventory)
                    if obtainable_ammunition is None
                    else obtainable_ammunition
                ),
                staff_gate=staff_gate,
                # Owner 2026-11-18 「魔道具術師については射撃威力を評価値から外し、弓枠は
                # 追加能力や耐性のみで評価する」 (50F+).
                launcher_power_unscored=lambda band: equipment_rules.launcher_power_unscored(
                    player.class_id, band),
                destination_floor=destination_floor,
            )

        def search(seed=None, flags=flags):
            return search_factory(
                items,
                current_item_ids=current.item_ids,
                pinned=pinned,
                excluded_item_ids=search_excluded_item_ids,
                require_light=require_light,
                required_flags=flags,
                **({} if seed is None else {"seed": seed}),
                # The depth gates' speeds (SPEED_GATE_MINIMA): a set that reaches one only
                # by two swaps or more is searched as a whole (_gate_completions).
                **({"repair_flags": repair_flags, "staff_gate": staff_gate,
                    "speed_gates": speed_gates(defense.base_speed, SPEED_GATE_MINIMA)}
                   if search_factory is enumerate_single_slot_variants else {}),
            )

        # The finale's order (owner 2026-11-24): its exhaustive search over the owned gear
        # puts the sets first in that order among the candidates, whatever the slot count.
        finale_seeds = (
            finale_seed_loadouts(
                items, inputs, defense, intrinsic_flags, current=current, pinned=pinned,
                excluded_item_ids=search_excluded_item_ids, require_light=require_light,
                require_body=require_body, required_flags=flags, depth=depth,
                intrinsic_abilities=intrinsic_abilities.intersection(ABILITY_FLAG),
                has_destruction=has_destruction, staff_gate=staff_gate,
                deadline=min(closure_deadline, monotonic() + FINALE_SEARCH_SECONDS))
            if finale else ())
        if search_factory is enumerate_single_slot_variants:
            result = optimize_single_slot_closure(
                current, lambda seed: search(seed), optimize,
                **({"extra_seeds": finale_seeds} if finale_seeds else {}),
            )
        else:
            result = optimize((*search(), *finale_seeds))
        if result.best is not None or result.timed_out:
            break
    if loadout_report_path is not None:
        _append_loadout_report(
            loadout_report_path, encounter_depth, result, evaluator, defense
        )
    if result.timed_out:
        return WarriorOptimizationPreparation(
            current,
            result,
            None,
            ("optimization-timeout",),
            len(all_encounters),
            len(encounters),
        )
    if result.incomplete_item_ids:
        return WarriorOptimizationPreparation(
            current,
            result,
            None,
            ("incomplete-equipment-catalog",),
            len(all_encounters),
            len(encounters),
        )
    if result.best is None:
        return WarriorOptimizationPreparation(
            current,
            result,
            None,
            ("no-valid-loadout",),
            len(all_encounters),
            len(encounters),
        )
    transaction = plan_equipment_transactions(
        items,
        current,
        result.best.loadout,
        current_pack_items=len(snapshot.inventory),
        home_scan_complete=home_scan_complete,
        preserve_pack_item_ids=preserve_pack_item_ids,
        preserve_worn_light=any(
            item.id in search_excluded_item_ids
            and item.equipped_slot == SLOT_LIGHT
            for item in items
        ),
        curse_pinned_item_ids=curse_pinned_item_ids,
    )
    return WarriorOptimizationPreparation(
        current, result, transaction,
        transaction.blockers,
        len(all_encounters),
        len(encounters),
    )


def _append_loadout_report(
    path: Path,
    depth: int,
    result: OptimizationResult,
    evaluator: CachedWarriorLoadoutEvaluator,
    defense_inputs: WarriorDefenseInputs,
) -> None:
    """Append one inspectable record for every completed loadout search."""
    candidates = []
    for rank, entry in enumerate(result.top_candidates, 1):
        detailed = evaluator(entry.loadout)
        resistances = sorted(
            name for name, flag in ABILITY_FLAG.items()
            if name.startswith("resist_") and flag in entry.loadout.flags
        )
        candidates.append({
            "rank": rank,
            "slots": {
                slot: {
                    "id": owned.id,
                    "name": owned.item.name,
                    "origin": owned.origin,
                }
                for slot, owned in entry.loadout.slots
            },
            "score": {
                "melee_output": entry.metrics.expected_dps,
                "device_output": entry.metrics.device_dps,
                "ac": loadout_armor_class(entry.loadout, defense_inputs),
                "resist_coverage": resistances,
                "resist_coverage_count": len(resistances),
                "speed": entry.metrics.speed_bonus,
                "total": entry.metrics.combat_margin if isfinite(entry.metrics.combat_margin) else None,
                "survival_turns": entry.metrics.survival_turns if isfinite(entry.metrics.survival_turns) else None,
                "secondary_value": entry.metrics.secondary_value,
            },
            "melee_hands": [
                {"blows": hand.blows, "hit_chance_ac100": hand.hit_chance_ac100,
                 "to_hit": hand.to_hit, "to_damage": hand.to_damage,
                 "hit_reliability": hand.hit_reliability,
                 "damage_per_hit": hand.expected_damage_per_hit,
                 "damage_per_turn": hand.expected_damage_per_round}
                for hand in detailed.melee.hands
            ],
        })
    record = {
        "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "depth": depth,
        "combat_inputs": asdict(evaluator.inputs.combat),
        "timed_out": result.timed_out,
        "search_truncated": result.search_truncated,
        "search_capped": getattr(result, "search_capped", False),
        "considered": result.combinations_considered,
        "evaluated": result.combinations_evaluated,
        "band_descent": [asdict(decision) for decision in result.band_decisions],
        "chosen_band": result.chosen_depth,
        "chosen_ratio": (
            result.chosen_decision.ratio if result.chosen_decision else None
        ),
        "candidates": candidates,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False, allow_nan=False)
            file.write("\n")
    except (OSError, ValueError):
        # Diagnostics must never turn a safe fail-closed optimizer into a crash.
        return
