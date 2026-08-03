"""Prepare a fail-closed Warrior loadout optimization and transaction plan."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
from typing import Mapping

from hengbot.equipment_encounters import normal_encounters, representative_encounters
from hengbot.equipment_optimizer import (
    ABILITY_FLAG,
    Loadout,
    OptimizationResult,
    OwnedEquipment,
    current_loadout,
    equipment_identity,
    optimize_loadout,
    required_abilities,
)
from hengbot.equipment_transaction_planner import (
    EquipmentTransactionPlan,
    plan_equipment_transactions,
)
from hengbot.model import PLAYER_CLASS_WARRIOR, Snapshot
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.monster_ranged_evaluator import SpellSelectionContext
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
)
from hengbot.warrior_loadout_search import (
    enumerate_single_slot_variants,
    enumerate_warrior_loadouts,
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
    """Worn-independent character constants observed with nothing removable worn.

    Produced by the execution-layer unequipped calibration phase (the user's
    sanctioned method): the pack is deposited at Home, every removable item is
    taken off, and the naked snapshot IS the constants — no inversion of
    ``modify_stat_value`` and no ``ADJ_DEX_TO_AC`` subtraction of a worn set
    ever happens.  Cursed (unremovable) items stay worn during the observation,
    so their contribution is folded into the constants; ``pinned_identities``
    records that folded set so a curse change invalidates the calibration.
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
    # Sorted mutation ids from the naked `C` character snapshot at capture
    # time (the periodic status dump refreshes the live observation); None
    # when no mutation observation was available yet.
    mutation_signature: tuple[int, ...] | None = None
    # Permanent TR flag ids read off the naked `C` character snapshot's
    # characteristics table (player/immunity/vulnerability columns).  These
    # carry what the 19-boolean abilities set cannot express — permanent
    # elemental vulnerabilities and immunities, sustains, TR_RES_TIME and the
    # rest — and become worn-independent search input.
    intrinsic_tr_flags: frozenset[int] = frozenset()

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
        the capture phase's naked dump and the periodic status dump the bot
        already posts), and a change in the pinned (cursed worn) set.  Pass
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
        if tuple(player.stat_cur) != self.stat_cur:
            return "stat_cur"
        if tuple(pinned_identities) != self.pinned_identities:
            return "pinned-set"
        if (
            mutation_signature is not None
            and mutation_signature != self.mutation_signature
        ):
            return "mutations"
        return None


def character_intrinsic_flags(characteristics) -> frozenset[int]:
    """Permanent TR flag ids from a NAKED `C` snapshot's characteristics.

    Rows are the emitter's make_flag_table_json shape.  With nothing worn the
    player/immunity/vulnerability columns are exactly the character's own
    permanent flags (race, class, mutations); the temporary columns are
    deliberately excluded — the calibration preconditions forbid temporary
    effects, and folding one in would contaminate the constants.
    """
    flags: set[int] = set()
    for row in characteristics or ():
        if not isinstance(row, dict):
            continue
        try:
            flag_id = int(row.get("flag_id"))
        except (TypeError, ValueError):
            continue
        if bool(row.get("player")) or bool(row.get("immunity")) or bool(
            row.get("vulnerability")
        ):
            flags.add(flag_id)
    return frozenset(flags)


def calibrate_character_constants(
    snapshot: Snapshot,
    *,
    mutation_signature: tuple[int, ...] | None = None,
    intrinsic_tr_flags: frozenset[int] = frozenset(),
) -> CharacterCalibration | None:
    """Read the constants off a naked observation. Purely observational.

    Returns None unless every worn item is unremovable (cursed): a removable
    item still worn means the strip phase has not finished and the observation
    would be contaminated.  The caller (execution layer) owns every other
    precondition: town, temporary statuses clear, no visible hostiles, HP full.
    """
    player = snapshot.player
    removable = [
        item
        for item in snapshot.equipment
        if item.is_equipment and not item.is_cursed
    ]
    if removable:
        return None
    if len(player.stat_cur) < 6 or len(player.stat_use) < 6:
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
        stat_cur=tuple(player.stat_cur),
        base_stats=base_stats,
        base_hp=base_hp,
        base_ac_bonus=base_ac_bonus,
        intrinsic_abilities=frozenset(player.abilities),
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
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError:
        # Persistence is an optimization; the in-memory calibration stays valid.
        return


def load_character_calibration(path: Path) -> CharacterCalibration | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return CharacterCalibration(
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
        )
    except (KeyError, TypeError, ValueError):
        return None


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
    ) -> CachedWarriorLoadoutEvaluator:
        normalized_inputs = (
            replace(inputs, current_hp=0)
            if inputs.base_hp is not None
            else inputs
        )
        context = (normalized_inputs, encounters)
        if self.context != context or self.evaluator is None:
            self.context = context
            self.evaluator = CachedWarriorLoadoutEvaluator(inputs, encounters)
        return self.evaluator

def weapon_expected_dps(
    snapshot: Snapshot,
    weapon,
    reference_ac: int,
    calibration: CharacterCalibration | None,
) -> float | None:
    """Score both wielded hands against a visible, non-immune neutral target.

    P1: the natural stats come from the unequipped calibration observation —
    the same mandatory input the loadout selector uses — never from inverting
    the geared ``stat_use``.  Without a calibration the score is unknowable
    and the caller must fail closed (defer the sale / readiness decision).
    The worn slot layout itself is a legitimate physical input here: the
    question asked is "this weapon in MY current off-hand configuration".
    """
    if calibration is None:
        return None
    equipped = tuple(
        OwnedEquipment(
            f"equipped:{index}", item, "equipped", equipped_slot=item.slot
        )
        for index, item in enumerate(snapshot.equipment)
        if item.is_equipment
    )
    current = current_loadout(equipped)
    inputs = WarriorCombatInputs(
        level=snapshot.player.level,
        natural_str=calibration.base_stats[0],
        natural_dex=calibration.base_stats[3],
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


def prepare_warrior_optimization(
    snapshot: Snapshot,
    items: tuple[OwnedEquipment, ...],
    knowledge: Mapping[int, MonraceKnowledge],
    *,
    depth: int,
    home_scan_complete: bool,
    has_destruction: bool = False,
    preserve_pack_item_ids: frozenset[str] = frozenset(),
    search_excluded_item_ids: frozenset[str] = frozenset(),
    timeout_seconds: float = 25.0,
    loadout_report_path: Path | None = None,
    evaluator_cache: WarriorEvaluatorCache | None = None,
    calibration: CharacterCalibration | None = None,
) -> WarriorOptimizationPreparation:
    """Evaluate and plan without emitting any game command."""
    current = current_loadout(items)
    blockers: list[str] = []
    player = snapshot.player
    if player.class_id != PLAYER_CLASS_WARRIOR:
        blockers.append("unsupported-class")
    if len(player.stat_cur) < 4 or player.stat_cur[0] <= 0 or player.stat_cur[3] <= 0:
        blockers.append("missing-natural-stats")
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
    if blockers:
        return WarriorOptimizationPreparation(current, None, None, tuple(blockers))

    all_encounters = normal_encounters(knowledge, depth)
    if not all_encounters:
        return WarriorOptimizationPreparation(
            current, None, None, ("empty-encounter-set",)
        )
    encounters = optimization_encounters(
        all_encounters,
        catalog_size=len(items),
    )

    # P1: every character constant comes from the unequipped calibration
    # observation, never from de-gearing the currently worn snapshot.  The
    # worn partition of the owned multiset can no longer move the answer
    # through ADJ_DEX_TO_AC steps (base_ac_bonus), the non-injective
    # modify_stat_value scale (base stats / base_hp), or ability shadowing
    # (intrinsic set).  There is no legacy derivation here by design.
    intrinsic_abilities = calibration.intrinsic_abilities
    base_str = calibration.base_stats[0]
    base_dex = calibration.base_stats[3]
    base_con = calibration.base_stats[4]
    base_hp = calibration.base_hp
    base_ac_bonus = calibration.base_ac_bonus
    # The naked characteristics enrich the evaluator's intrinsic flag set with
    # what the abilities booleans cannot express.  Consumed today by the
    # defense model: TR_IM_* (zero elemental damage), TR_VUL_* (+1/3 damage),
    # TR_SUST_* (drain exposure) and TR_RES_TIME; every other recorded flag
    # (slays, brands, ESP, ...) has no evaluator consumer yet and is
    # deliberately carried without invented scoring.
    intrinsic_flags = (
        _intrinsic_flags(intrinsic_abilities) | calibration.intrinsic_tr_flags
    )
    # Speed is deliberately NOT calibrated: its de-gearing is linear and exact,
    # and a stripped observation would fold the changed carried weight into the
    # base (roadmap P1 requirement 4).
    defense = WarriorDefenseInputs(
        level=player.level,
        natural_dex=base_dex,
        shield_skill=player.shield_skill,
        base_ac_bonus=base_ac_bonus,
        base_speed=player.speed - _equipment_speed(current),
        saving_skill=player.saving_skill,
        intrinsic_flags=intrinsic_flags,
    )
    inputs = WarriorLoadoutInputs(
        combat=WarriorCombatInputs(
            level=player.level,
            natural_str=base_str,
            natural_dex=base_dex,
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
        base_hp=base_hp,
    )
    evaluator = (
        evaluator_cache.get(inputs, encounters)
        if evaluator_cache is not None
        else CachedWarriorLoadoutEvaluator(inputs, encounters)
    )
    pinned = {
        item.equipped_slot: item
        for item in items
        if item.id in current.item_ids
        and item.equipped_slot is not None
        and item.item.is_cursed
    }
    required_candidate_flags = {
        ABILITY_FLAG[ability]
        for ability in required_abilities(depth)
        if ability not in intrinsic_abilities
    }
    # Once paralysis is a live dungeon risk, an optimizer transaction must not
    # discard free action that the current loadout already owns merely because
    # a mundane armor piece gains a few points of AC. Another slot may replace
    # the flag, but the resulting complete loadout must retain it.
    if depth >= FREE_ACTION_PRESERVE_DEPTH and TR_FREE_ACT in current.flags:
        required_candidate_flags.add(TR_FREE_ACT)
    search_factory = (
        enumerate_single_slot_variants
        if len(items) >= INCREMENTAL_SEARCH_CATALOG_THRESHOLD
        else enumerate_warrior_loadouts
    )
    candidate_loadouts = search_factory(
        items,
        current_item_ids=current.item_ids,
        pinned=pinned,
        excluded_item_ids=search_excluded_item_ids,
        require_light=True,
        required_flags=frozenset(required_candidate_flags),
    )
    result = optimize_loadout(
        items,
        lambda loadout: evaluator(loadout).metrics,
        depth=depth,
        intrinsic_abilities=intrinsic_abilities.intersection(ABILITY_FLAG),
        has_destruction=has_destruction,
        current_item_ids=current.item_ids,
        timeout_seconds=timeout_seconds,
        candidate_loadouts=candidate_loadouts,
    )
    if loadout_report_path is not None:
        _append_loadout_report(loadout_report_path, depth, result, evaluator, defense)
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
                 "damage_per_hit": hand.expected_damage_per_hit,
                 "damage_per_turn": hand.expected_damage_per_round}
                for hand in detailed.melee.hands
            ],
        })
    record = {
        "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "depth": depth,
        "timed_out": result.timed_out,
        "search_truncated": result.search_truncated,
        "considered": result.combinations_considered,
        "evaluated": result.combinations_evaluated,
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
