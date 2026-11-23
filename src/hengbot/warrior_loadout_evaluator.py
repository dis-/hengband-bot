"""Composite whole-loadout evaluation for a Warrior."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, isinf

from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_encounters import melee_multiplier
from hengbot.equipment_optimizer import Loadout, LoadoutMetrics, SLOT_BOW
from hengbot.equipment_utility import utility_value
from hengbot.launcher_damage import LAUNCHER_PROPERTIES, plain_ammo_turn_damage
from hengbot.me_loadout_offense import (
    TR_INT,
    MagicEaterOffenseInputs,
    finale_power_success,
    magic_eater_device_dps,
    survival_factor,
)
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    WarriorRangedDefenseResult,
    evaluate_warrior_ranged_defense,
)
from hengbot.policy_constants import speed_energy
from hengbot.saving_throw import loadout_saving
from hengbot.warrior_defense_evaluator import (
    TR_SPEED,
    WarriorDefenseInputs,
    WarriorDefenseResult,
    evaluate_warrior_defense,
    warrior_defense_signature,
)
from hengbot.warrior_equipment_evaluator import (
    ADJ_DEX_TO_H,
    ADJ_STR_HOLD,
    ADJ_STR_TO_D,
    ADJ_STR_TO_H,
    TR_DEX,
    TR_STR,
    WarriorCombatInputs,
    WarriorMeleeResult,
    evaluate_warrior_melee,
    modify_stat_value,
    stat_index,
    trunc_div,
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

TR_XTRA_MIGHT = 82
TR_XTRA_SHOTS = 83
TR_CON = 4
ADJ_CON_HP = (
    -8, -6, -4, -2, -1, 0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 4,
    5, 6, 7, 8, 9, 10, 11, 12, 14, 17, 20, 23, 26, 29, 32, 35,
    38, 40, 42, 44, 46, 48,
)


@dataclass(frozen=True)
class WarriorLoadoutInputs:
    combat: WarriorCombatInputs
    defense: WarriorDefenseInputs
    current_hp: int
    spell_selection: SpellSelectionContext | None = None
    natural_con: int = 3
    base_hp: int | None = None
    intrinsic_con: int = 0
    hp_floor: int = 1
    # Class 16 only (me_loadout_offense, owner 2026-11-08): the held absorbed
    # attack powers whose INT-dependent fail rate scores ``device_dps``.
    magic_eater: MagicEaterOffenseInputs | None = None
    # The board's saving throw without the worn gear's terms (saving_throw):
    # each loadout adds its own resist / vulnerability to curse, WIS index and
    # anti-magic floor.  None scores every loadout at defense.saving_skill.
    saving_base: int | None = None
    natural_wis: int = 3
    intrinsic_wis: int = 0


@dataclass(frozen=True)
class WarriorLoadoutResult:
    metrics: LoadoutMetrics
    melee: WarriorMeleeResult
    defense: WarriorDefenseResult
    ranged: WarriorRangedDefenseResult
    ranged_offense_dps: float = 0.0
    device_dps: float = 0.0


def _pval_total(loadout: Loadout, flag: int) -> int:
    return sum(item.item.pval for _, item in loadout.slots if flag in item.flags)


def constitution_hp_bonus(constitution: int, level: int) -> int:
    return trunc_div(ADJ_CON_HP[stat_index(constitution)] * level, 4)


TR_VAMPIRIC = 15
# MAX_VAMPIRIC_DRAIN (src/player-attack/player-attack.cpp): the HP one hand's
# blows of one player turn can drain.
MAX_VAMPIRIC_DRAIN = 50
# A drain needs more than 5 damage (blood-sucking-processor.cpp drain_result).
VAMPIRIC_MIN_DRAIN = 5
NON_LIVING_KINDS = frozenset({"DEMON", "UNDEAD", "NONLIVING"})


def living_encounters(
    encounters: tuple[EncounterTarget, ...],
) -> tuple[tuple[EncounterTarget, ...], float]:
    """The living encounters (has_living_flag) renormalized, and their share."""
    living = [encounter for encounter in encounters
              if not encounter.knowledge.flags & NON_LIVING_KINDS]
    share = sum(encounter.weight for encounter in living)
    if share <= 0:
        return (), 0.0
    return tuple(EncounterTarget(encounter.race_id, encounter.weight / share,
                                 encounter.knowledge) for encounter in living), share


def vampiric_heal_per_turn(
    loadout: Loadout, melee: WarriorMeleeResult | None, living_share: float,
) -> float:
    """HP a vampiric weapon drains per player turn, over the encounter mix.

    Owner 2026-11-20 「吸血も評価に入れて直す」 (★首切りソード『スレイヤー』).  A
    hit with TR_VAMPIRIC (src/player-attack/blood-sucking-processor.cpp) on a
    living monster (has_living_flag: not DEMON, UNDEAD or NONLIVING) whose
    damage - after slays and criticals, plus the weapon's and the hand's to_d -
    is above 5 heals 2d(damage/6), on average damage/6 + 1 with the division
    truncated (taken as damage/6 + 7/12); one hand drains at most
    MAX_VAMPIRIC_DRAIN = 50 in a player turn.  ``melee`` is this loadout's
    melee against the living encounters only, ``living_share`` their weight.
    Not modelled: the killing blow drains nothing and a hit drains at most the
    monster's remaining HP.
    """
    if melee is None or living_share <= 0:
        return 0.0
    weapons = [weapon for slot in ("main_hand", "sub_hand")
               if (weapon := loadout.item_at(slot)) is not None
               and weapon.item.tval in {20, 21, 22, 23}]
    heal = 0.0
    for weapon, hand in zip(weapons, melee.hands):
        if TR_VAMPIRIC not in weapon.flags:
            continue
        damage = hand.expected_damage_per_hit
        per_hit = damage / 6 + 7 / 12 if damage > VAMPIRIC_MIN_DRAIN else 0.0
        heal += min(float(MAX_VAMPIRIC_DRAIN),
                    hand.blows * hand.hit_chance_ac100 * per_hit)
    return heal * living_share


def drains(loadout: Loadout) -> bool:
    return any((weapon := loadout.item_at(slot)) is not None and TR_VAMPIRIC in weapon.flags
               for slot in ("main_hand", "sub_hand"))


def loadout_defense_inputs(
    loadout: Loadout, inputs: WarriorLoadoutInputs,
) -> WarriorDefenseInputs:
    """``inputs.defense`` with ``loadout``'s own saving throw (saving_throw)."""
    if inputs.saving_base is None:
        return inputs.defense
    saving = loadout_saving(
        inputs.saving_base, loadout, level=inputs.combat.level,
        natural_wis=inputs.natural_wis, intrinsic_wis=inputs.intrinsic_wis,
        intrinsic_flags=inputs.defense.intrinsic_flags)
    if saving == inputs.defense.saving_skill:
        return inputs.defense
    return replace(inputs.defense, saving_skill=saving)


def loadout_max_hp(loadout: Loadout, inputs: WarriorLoadoutInputs) -> int:
    """Apply Hengband's Warrior CON hit-point adjustment to this loadout."""
    if inputs.base_hp is None:
        return inputs.current_hp
    constitution = modify_stat_value(
        inputs.natural_con, inputs.intrinsic_con + _pval_total(loadout, TR_CON)
    )
    return max(
        inputs.hp_floor,
        inputs.base_hp
        + constitution_hp_bonus(constitution, inputs.combat.level),
    )


def _shooting_misc_to_hit(loadout: Loadout) -> int:
    return sum(
        item.item.to_h
        for slot, item in loadout.slots
        if slot not in {"main_hand", "sub_hand", SLOT_BOW}
    )


def warrior_ranged_offense_dps(
    loadout: Loadout, inputs: WarriorCombatInputs, target_ac: int = 100
) -> float:
    """The worn launcher's shot with the plain store round of its kind, per player turn.

    Owner 2026-11-22 「射撃武器の比較には店で買える並の矢弾を使って。」: the shared figure
    (launcher_damage.plain_ammo_turn_damage), with this loadout's shooter: calc_to_hit_bow's
    to_h_b from its STR/DEX and the other gear's to_h (a heavy launcher's penalty), the STR
    term of the multiplier, the other gear's extra shots and extra might and the Warrior's
    shots.  So a launcher's stat modifiers count here and in the melee (owner 2026-11-22
    「近接の増え方も入れて全体で比べる」) through the ordinary comparison."""
    launcher = loadout.item_at(SLOT_BOW)
    if launcher is None or launcher.item.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    strength = modify_stat_value(inputs.natural_str, inputs.intrinsic_str + _pval_total(loadout, TR_STR))
    dexterity = modify_stat_value(inputs.natural_dex, inputs.intrinsic_dex + _pval_total(loadout, TR_DEX))
    str_idx = stat_index(strength)
    dex_idx = stat_index(dexterity)
    hold = ADJ_STR_HOLD[str_idx]
    heavy = hold < launcher.item.weight // 10
    others = [item for slot, item in loadout.slots if slot != SLOT_BOW]
    to_h_b = ADJ_DEX_TO_H[dex_idx] + ADJ_STR_TO_H[str_idx] + _shooting_misc_to_hit(loadout)
    if heavy:
        to_h_b += 2 * (hold - launcher.item.weight // 10)
    return plain_ammo_turn_damage(
        launcher.item,
        skill_thb=inputs.shooting_skill,
        to_h_b=to_h_b,
        str_td=ADJ_STR_TO_D[str_idx],
        extra_shots=(sum(1 for _, item in loadout.slots if TR_XTRA_SHOTS in item.flags)
                     - (TR_XTRA_SHOTS in launcher.item.known_flags)),
        shots_bonus=inputs.level * 2 if not heavy and inputs.class_id == 0 else 0,
        xtra_might=(any(TR_XTRA_MIGHT in item.flags for item in others)
                    or TR_XTRA_MIGHT in launcher.flags),
        target_ac=target_ac,
        lazy=inputs.lazy_personality,
    )


class CachedWarriorLoadoutEvaluator:
    """Exact component cache for repeated whole-loadout evaluation."""

    def __init__(
        self,
        inputs: WarriorLoadoutInputs,
        encounters: tuple[EncounterTarget, ...],
        offense_encounters: tuple[EncounterTarget, ...] | None = None,
    ) -> None:
        self.inputs = inputs
        self.encounters = encounters
        # The whole ordinary pool the melee slays and kill turns are read
        # against when ``encounters`` is a sample (owner 2026-11-20): the
        # weapon's multipliers are per weapon and cheap, and a 64-race sample
        # tilted them (n1-b life-411: 26-30% dragons against 12.5%).
        self.offense_encounters = offense_encounters or encounters
        self._living, self._living_share = living_encounters(self.offense_encounters)
        self._living_melee: dict[tuple[object, ...], WarriorMeleeResult] = {}
        self._melee: dict[tuple[object, ...], WarriorMeleeResult] = {}
        self._defense: dict[tuple[object, ...], WarriorDefenseResult] = {}
        self._ranged: dict[
            tuple[frozenset[int], int], WarriorRangedDefenseResult
        ] = {}
        self._weapon_multipliers: dict[str, tuple[tuple[int, float], ...]] = {}
        self._device: dict[tuple[int, frozenset[int]], tuple[float, float]] = {}
        self._average_target_hp = sum(
            encounter.weight * encounter.knowledge.average_hp
            for encounter in self.offense_encounters
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
                for encounter in self.offense_encounters:
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
                self.offense_encounters,
                multiplier_weights_by_item=self._weapon_multipliers,
                average_target_hp=self._average_target_hp,
            )
            self._melee[melee_key] = melee

        defense_inputs = loadout_defense_inputs(loadout, self.inputs)
        defense_key = (warrior_defense_signature(loadout, defense_inputs),
                       defense_inputs.saving_skill)
        defense = self._defense.get(defense_key)
        if defense is None:
            defense = evaluate_warrior_defense(
                loadout, defense_inputs, self.encounters
            )
            self._defense[defense_key] = defense

        flags = loadout.flags | self.inputs.defense.intrinsic_flags
        player_hp = loadout_max_hp(loadout, self.inputs)
        ranged_key = (flags, player_hp, defense_inputs.saving_skill)
        ranged = self._ranged.get(ranged_key)
        if ranged is None:
            ranged = evaluate_warrior_ranged_defense(
                flags,
                saving_skill=defense_inputs.saving_skill,
                player_hp=player_hp,
                encounters=self.encounters,
                selection_context=self.inputs.spell_selection,
            )
            self._ranged[ranged_key] = ranged

        device_key = (_pval_total(loadout, TR_INT), flags)
        # setdefault: an evaluator restored from a checkpoint pickled before
        # this cache existed has no ``_device``.
        device_cache = self.__dict__.setdefault("_device", {})
        cached = device_cache.get(device_key)
        if not isinstance(cached, tuple):
            magic_eater = getattr(self.inputs, "magic_eater", None)
            cached = (
                magic_eater_device_dps(magic_eater, device_key[0], flags, self.encounters),
                survival_factor(magic_eater, device_key[0], flags, self.encounters),
            )
            device_cache[device_key] = cached

        heal = 0.0
        if drains(loadout):
            # setdefault: an evaluator restored from an older checkpoint.
            if "_living" not in self.__dict__:
                self._living, self._living_share = living_encounters(self.offense_encounters)
            living_cache = self.__dict__.setdefault("_living_melee", {})
            living_melee = living_cache.get(melee_key)
            if living_melee is None:
                living_melee = evaluate_warrior_melee(
                    loadout, self.inputs.combat, self._living)
                living_cache[melee_key] = living_melee
            heal = vampiric_heal_per_turn(loadout, living_melee, self._living_share)
        return _combine_warrior_results(
            loadout, self.inputs, melee, defense, ranged, *cached, heal)


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
    defense_inputs = loadout_defense_inputs(loadout, inputs)
    defense = evaluate_warrior_defense(loadout, defense_inputs, encounters)
    flags = loadout.flags | inputs.defense.intrinsic_flags
    player_hp = loadout_max_hp(loadout, inputs)
    ranged = evaluate_warrior_ranged_defense(
        flags,
        saving_skill=defense_inputs.saving_skill,
        player_hp=player_hp,
        encounters=encounters,
        selection_context=inputs.spell_selection,
    )
    int_pval = _pval_total(loadout, TR_INT)
    device = magic_eater_device_dps(inputs.magic_eater, int_pval, flags, encounters)
    factor = survival_factor(inputs.magic_eater, int_pval, flags, encounters)
    heal = 0.0
    if drains(loadout):
        living, share = living_encounters(encounters)
        heal = vampiric_heal_per_turn(
            loadout, evaluate_warrior_melee(loadout, inputs.combat, living), share)
    return _combine_warrior_results(
        loadout, inputs, melee, defense, ranged, device, factor, heal)


def _combine_warrior_results(
    loadout: Loadout,
    inputs: WarriorLoadoutInputs,
    melee: WarriorMeleeResult,
    defense: WarriorDefenseResult,
    ranged: WarriorRangedDefenseResult,
    device_dps: float = 0.0,
    me_survival_factor: float = 1.0,
    vampiric_heal: float = 0.0,
) -> WarriorLoadoutResult:
    player_speed = inputs.defense.base_speed + _speed_bonus(loadout)
    player_energy = speed_energy(player_speed)
    incoming = (
        defense.energy_weighted_melee_damage
        + ranged.energy_weighted_ranged_damage
    ) / player_energy
    player_hp = loadout_max_hp(loadout, inputs)
    survival_turns = (
        player_hp / incoming if incoming > 0 else float("inf")
    )
    # The vampiric drain (vampiric_heal_per_turn, owner 2026-11-20): what it
    # restores in one engagement - kill_turns of melee, and no more than the
    # damage taken meanwhile - in turns of incoming damage.  The engagement
    # bounds it: over the whole survival horizon an average drain above the
    # (mix-averaged) incoming damage would read as immortality.
    kill_turns = melee.expected_kill_turns
    if vampiric_heal > 0 and incoming > 0 and isfinite(kill_turns):
        survival_turns += kill_turns * min(vampiric_heal, incoming) / incoming
    # Class 16 (me_loadout_offense.survival_factor, owner 2026-11-08): the
    # absorbed powers' success under this loadout's INT and the escape
    # reliability lost to blindness scale the survival side; 1.0 otherwise.
    survival_turns *= me_survival_factor
    # User decision 2026-10-02 (verbatim: 「指輪で優先度が低いのはどう見ても守りの
    # 指輪。ACの評価が高すぎる。」 -> 「生存÷撃破の比で比べる」): the combat
    # margin is the ratio survival / kill, not the difference.  A difference
    # in turns let a few turns of AC survival outweigh a 16% faster kill.
    # expected_kill_turns is either inf or strictly positive.
    if isinf(kill_turns):
        combat_margin = -float("inf")
    elif isinf(survival_turns):
        combat_margin = float("inf")
    else:
        combat_margin = survival_turns / kill_turns
    # Owner 2026-11-02 (equipment_utility): telepathy highly, stealth somewhat,
    # as a relative bonus on the ratio.
    utility = utility_value(
        (item for _, item in loadout.slots), inputs.defense.intrinsic_flags
    )
    if isfinite(combat_margin):
        combat_margin *= 1.0 + utility
    complete = defense.melee_complete and ranged.ranged_complete
    secondary_value = secondary_risk_value(defense, ranged)
    ranged_offense_dps = warrior_ranged_offense_dps(loadout, inputs.combat)
    metrics = LoadoutMetrics(
        expected_dps=melee.expected_dps_ac100,
        ranged_dps=ranged_offense_dps,
        survival_turns=survival_turns,
        combat_margin=combat_margin,
        speed_bonus=_speed_bonus(loadout),
        secondary_value=secondary_value,
        utility_value=utility,
        evaluation_complete=complete,
        device_dps=device_dps,
        player_speed=player_speed,
        finale_power_success=finale_power_success(
            getattr(inputs, "magic_eater", None), _pval_total(loadout, TR_INT),
            loadout.flags | inputs.defense.intrinsic_flags),
    )
    return WarriorLoadoutResult(
        metrics, melee, defense, ranged, ranged_offense_dps, device_dps)
