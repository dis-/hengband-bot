"""Composite whole-loadout evaluation for a Warrior."""

from __future__ import annotations

from dataclasses import dataclass
from math import isinf

from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_encounters import melee_multiplier
from hengbot.equipment_optimizer import Loadout, LoadoutMetrics
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    WarriorRangedDefenseResult,
    evaluate_warrior_ranged_defense,
)
from hengbot.warrior_defense_evaluator import (
    TR_SPEED,
    WarriorDefenseInputs,
    WarriorDefenseResult,
    evaluate_warrior_defense,
    warrior_defense_signature,
)
from hengbot.warrior_equipment_evaluator import (
    WarriorCombatInputs,
    WarriorMeleeResult,
    evaluate_warrior_melee,
    warrior_melee_signature,
)


STATUS_RISK_WEIGHTS = {
    "paralyzed": 8.0,
    "confused": 6.0,
    "slowed": 4.0,
    "blind": 3.0,
    "hallucinating": 2.0,
    "stunned": 1.5,
    "afraid": 1.0,
    "poison": 0.25,
    "bleeding": 0.10,
}

RESOURCE_RISK_WEIGHTS = {
    "summoning": 12.0,
    "time-stop": 12.0,
    "forced-level-teleport": 10.0,
    "nexus-effect": 8.0,
    "time-effect": 8.0,
    "special-ability": 8.0,
    "buff-dispel": 6.0,
    "equipment-curse": 5.0,
    "equipment-disenchant": 5.0,
    "experience-drain": 4.0,
    "mutation-or-polymorph": 4.0,
    "mutation": 3.0,
    "forced-teleport-to": 3.0,
    "passive-teleport": 3.0,
    "trap-creation": 3.0,
    "raise-dead": 3.0,
    "map-forgetting": 2.0,
    "forced-teleport-away": 1.5,
    "monster-invulnerability": 1.5,
    "monster-heal": 1.0,
    "monster-haste": 1.0,
    "mana-drain": 1.0,
    "monster-alert": 0.5,
    "monster-reposition": 0.5,
    "monster-escape": 0.25,
    "darkness": 0.25,
    "elemental-item-damage": 0.25,
    "acid-item-damage": 0.25,
    "cold-item-damage": 0.25,
    "device-charge-drain": 0.25,
    "eat-gold": 0.25,
    "eat-item": 0.25,
    "eat-food": 0.25,
    "eat-lite": 0.25,
    "food-drain": 0.10,
    "strength-drain": 1.0,
    "intelligence-drain": 1.0,
    "wisdom-drain": 1.0,
    "dexterity-drain": 1.0,
    "constitution-drain": 1.0,
    "charisma-drain": 0.5,
    "earthquake": 1.0,
}


@dataclass(frozen=True)
class WarriorLoadoutInputs:
    combat: WarriorCombatInputs
    defense: WarriorDefenseInputs
    current_hp: int
    spell_selection: SpellSelectionContext | None = None


@dataclass(frozen=True)
class WarriorLoadoutResult:
    metrics: LoadoutMetrics
    melee: WarriorMeleeResult
    defense: WarriorDefenseResult
    ranged: WarriorRangedDefenseResult


class CachedWarriorLoadoutEvaluator:
    """Exact component cache for repeated whole-loadout evaluation."""

    def __init__(
        self,
        inputs: WarriorLoadoutInputs,
        encounters: tuple[EncounterTarget, ...],
    ) -> None:
        self.inputs = inputs
        self.encounters = encounters
        self._melee: dict[tuple[object, ...], WarriorMeleeResult] = {}
        self._defense: dict[tuple[object, ...], WarriorDefenseResult] = {}
        self._ranged: dict[frozenset[int], WarriorRangedDefenseResult] = {}
        self._weapon_multipliers: dict[str, tuple[tuple[int, float], ...]] = {}
        self._average_target_hp = sum(
            encounter.weight * encounter.knowledge.average_hp
            for encounter in encounters
        )

    @property
    def cache_sizes(self) -> tuple[int, int, int]:
        return len(self._melee), len(self._defense), len(self._ranged)

    def __call__(self, loadout: Loadout) -> WarriorLoadoutResult:
        melee_key = warrior_melee_signature(loadout)
        melee = self._melee.get(melee_key)
        if melee is None:
            for slot in ("main_hand", "sub_hand"):
                weapon = loadout.item_at(slot)
                if weapon is None or weapon.id in self._weapon_multipliers:
                    continue
                multiplier_weights: dict[int, float] = {}
                for encounter in self.encounters:
                    multiplier = melee_multiplier(
                        weapon.flags, encounter.knowledge
                    )
                    multiplier_weights[multiplier] = (
                        multiplier_weights.get(multiplier, 0.0)
                        + encounter.weight
                    )
                self._weapon_multipliers[weapon.id] = tuple(
                    multiplier_weights.items()
                )
            melee = evaluate_warrior_melee(
                loadout,
                self.inputs.combat,
                self.encounters,
                multiplier_weights_by_item=self._weapon_multipliers,
                average_target_hp=self._average_target_hp,
            )
            self._melee[melee_key] = melee

        defense_key = warrior_defense_signature(loadout, self.inputs.defense)
        defense = self._defense.get(defense_key)
        if defense is None:
            defense = evaluate_warrior_defense(
                loadout, self.inputs.defense, self.encounters
            )
            self._defense[defense_key] = defense

        flags = loadout.flags | self.inputs.defense.intrinsic_flags
        ranged = self._ranged.get(flags)
        if ranged is None:
            ranged = evaluate_warrior_ranged_defense(
                flags,
                saving_skill=self.inputs.defense.saving_skill,
                player_hp=self.inputs.current_hp,
                encounters=self.encounters,
                selection_context=self.inputs.spell_selection,
            )
            self._ranged[flags] = ranged

        return _combine_warrior_results(loadout, self.inputs, melee, defense, ranged)


def _speed_bonus(loadout: Loadout) -> int:
    return sum(
        item.item.pval
        for _, item in loadout.slots
        if TR_SPEED in item.flags
    )


def _weighted_exposure(
    exposure: tuple[tuple[str, float], ...],
    weights: dict[str, float],
) -> float:
    return sum(value * weights.get(name, 1.0) for name, value in exposure)


def secondary_risk_value(
    defense: WarriorDefenseResult,
    ranged: WarriorRangedDefenseResult,
) -> float:
    """Return a higher-is-better tie-break value for non-HP consequences."""
    risk = _weighted_exposure(defense.status_turn_exposure, STATUS_RISK_WEIGHTS)
    risk += _weighted_exposure(ranged.status_turn_exposure, STATUS_RISK_WEIGHTS)
    risk += _weighted_exposure(
        defense.resource_event_exposure, RESOURCE_RISK_WEIGHTS
    )
    risk += _weighted_exposure(
        ranged.resource_event_exposure, RESOURCE_RISK_WEIGHTS
    )
    return -risk


def evaluate_warrior_loadout(
    loadout: Loadout,
    inputs: WarriorLoadoutInputs,
    encounters: tuple[EncounterTarget, ...],
) -> WarriorLoadoutResult:
    """Combine offense and incoming damage without enabling incomplete data."""
    melee = evaluate_warrior_melee(loadout, inputs.combat, encounters)
    defense = evaluate_warrior_defense(loadout, inputs.defense, encounters)
    flags = loadout.flags | inputs.defense.intrinsic_flags
    ranged = evaluate_warrior_ranged_defense(
        flags,
        saving_skill=inputs.defense.saving_skill,
        player_hp=inputs.current_hp,
        encounters=encounters,
        selection_context=inputs.spell_selection,
    )
    return _combine_warrior_results(loadout, inputs, melee, defense, ranged)


def _combine_warrior_results(
    loadout: Loadout,
    inputs: WarriorLoadoutInputs,
    melee: WarriorMeleeResult,
    defense: WarriorDefenseResult,
    ranged: WarriorRangedDefenseResult,
) -> WarriorLoadoutResult:
    incoming = defense.expected_melee_damage + ranged.expected_ranged_damage
    survival_turns = (
        inputs.current_hp / incoming if incoming > 0 else float("inf")
    )
    kill_turns = melee.expected_kill_turns
    if isinf(kill_turns):
        combat_margin = -float("inf")
    elif isinf(survival_turns):
        combat_margin = float("inf")
    else:
        combat_margin = survival_turns - kill_turns
    complete = defense.melee_complete and ranged.ranged_complete
    secondary_value = secondary_risk_value(defense, ranged)
    metrics = LoadoutMetrics(
        expected_dps=melee.expected_dps_ac100,
        survival_turns=survival_turns,
        combat_margin=combat_margin,
        speed_bonus=_speed_bonus(loadout),
        secondary_value=secondary_value,
        evaluation_complete=complete,
    )
    return WarriorLoadoutResult(metrics, melee, defense, ranged)
