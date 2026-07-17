"""Prepare a fail-closed Warrior loadout optimization and transaction plan."""

from __future__ import annotations

from dataclasses import dataclass
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
    optimize_loadout,
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
    TR_DEX,
    TR_STR,
    WarriorCombatInputs,
    evaluate_warrior_melee,
    modify_stat_value,
)
from hengbot.warrior_loadout_evaluator import (
    CachedWarriorLoadoutEvaluator,
    WarriorLoadoutInputs,
)
from hengbot.warrior_loadout_search import enumerate_warrior_loadouts


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


def weapon_expected_dps(snapshot: Snapshot, weapon, reference_ac: int) -> float | None:
    """Score both wielded hands against a visible, non-immune neutral target."""
    equipped = tuple(
        OwnedEquipment(
            f"equipped:{index}", item, "equipped", equipped_slot=item.slot
        )
        for index, item in enumerate(snapshot.equipment)
        if item.is_equipment
    )
    current = current_loadout(equipped)
    if len(snapshot.player.stat_cur) < 4 and len(snapshot.player.stat_use) < 4:
        return None
    displayed_stats = (
        snapshot.player.stat_use
        if len(snapshot.player.stat_use) >= 4
        and snapshot.player.stat_use[0] > 0
        and snapshot.player.stat_use[3] > 0
        else snapshot.player.stat_cur
    )
    inputs = WarriorCombatInputs(
        level=snapshot.player.level,
        natural_str=_base_stat_without_current_gear(displayed_stats[0], current, TR_STR),
        natural_dex=_base_stat_without_current_gear(displayed_stats[3], current, TR_DEX),
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


def _conservative_intrinsic_abilities(
    abilities: frozenset[str], current: Loadout
) -> frozenset[str]:
    """Remove every ability that the current equipment could be supplying.

    The snapshot exposes only the combined player result. If race and equipment
    both grant the same resistance this deliberately underestimates the intrinsic
    set; retaining an equipment resistance after removing its item would be the
    dangerous error.
    """
    equipment_abilities = {
        name
        for name, flag in PLAYER_ABILITY_FLAGS.items()
        if flag in current.flags
    }
    return abilities.difference(equipment_abilities)


def _equipment_speed(loadout: Loadout) -> int:
    return sum(
        item.item.pval for _, item in loadout.slots if TR_SPEED in item.flags
    )


def _base_stat_without_current_gear(
    displayed_value: int, current: Loadout, flag: int
) -> int:
    """Remove current equipment pval from Hengband's displayed stat value.

    ``stat_use`` already includes race, class, personality, mutations, and other
    player-visible modifiers. Only the current loadout's pval must be removed
    before candidate loadouts apply their own pval during evaluation.
    """
    equipment_bonus = sum(
        item.item.pval for _, item in current.slots if flag in item.flags
    )
    return modify_stat_value(displayed_value, -equipment_bonus)


def prepare_warrior_optimization(
    snapshot: Snapshot,
    items: tuple[OwnedEquipment, ...],
    knowledge: Mapping[int, MonraceKnowledge],
    *,
    depth: int,
    home_scan_complete: bool,
    has_destruction: bool = False,
    preserve_pack_item_ids: frozenset[str] = frozenset(),
    timeout_seconds: float = 60.0,
    loadout_report_path: Path | None = None,
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
    if blockers:
        return WarriorOptimizationPreparation(current, None, None, tuple(blockers))

    all_encounters = normal_encounters(knowledge, depth)
    if not all_encounters:
        return WarriorOptimizationPreparation(
            current, None, None, ("empty-encounter-set",)
        )
    encounters = (
        representative_encounters(all_encounters)
        if len(all_encounters) > 512
        else all_encounters
    )

    intrinsic_abilities = _conservative_intrinsic_abilities(
        player.abilities, current
    )
    intrinsic_flags = _intrinsic_flags(intrinsic_abilities)
    displayed_stats = (
        player.stat_use
        if len(getattr(player, "stat_use", ())) >= 4
        and player.stat_use[0] > 0
        and player.stat_use[3] > 0
        else player.stat_cur
    )
    base_str = _base_stat_without_current_gear(
        displayed_stats[0], current, TR_STR
    )
    base_dex = _base_stat_without_current_gear(
        displayed_stats[3], current, TR_DEX
    )
    provisional_defense = WarriorDefenseInputs(
        level=player.level,
        natural_dex=base_dex,
        shield_skill=player.shield_skill,
        base_speed=player.speed - _equipment_speed(current),
        saving_skill=player.saving_skill,
        intrinsic_flags=intrinsic_flags,
    )
    base_ac_bonus = player.ac - loadout_armor_class(current, provisional_defense)
    defense = WarriorDefenseInputs(
        level=provisional_defense.level,
        natural_dex=provisional_defense.natural_dex,
        shield_skill=provisional_defense.shield_skill,
        base_ac_bonus=base_ac_bonus,
        base_speed=provisional_defense.base_speed,
        saving_skill=provisional_defense.saving_skill,
        intrinsic_flags=intrinsic_flags,
    )
    inputs = WarriorLoadoutInputs(
        combat=WarriorCombatInputs(
            level=player.level,
            natural_str=base_str,
            natural_dex=base_dex,
            melee_skill=player.melee_skill,
            two_weapon_skill=player.two_weapon_skill,
        ),
        defense=defense,
        current_hp=max(1, player.max_hp),
        # This represents an ordinary neutral encounter, not live hidden state.
        spell_selection=SpellSelectionContext(
            player_has_mana=player.max_mp > 0,
        ),
    )
    evaluator = CachedWarriorLoadoutEvaluator(inputs, encounters)
    pinned = {
        item.equipped_slot: item
        for item in items
        if item.id in current.item_ids
        and item.equipped_slot is not None
        and item.item.is_cursed
    }
    candidate_loadouts = enumerate_warrior_loadouts(
        items, current_item_ids=current.item_ids, pinned=pinned
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
