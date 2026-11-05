"""The chance to win the next arena fight (owner 2026-11-05).

Owner: 「次の対戦相手への勝率が90%以上なら挑戦する」.  No number existed, so this
module makes one.  It is a race, computed exactly, without random draws:

  chance = sum over kill times n of P(n) * P(the opponent's damage over its
           actions in n player actions stays within the character's HP)

Opponent (static race data, lib/edit/MonraceDefinitions, allowed knowledge):
  * one action: with its spell frequency a spell chosen by the game's own
    selection model (``ability_selection_probabilities``), else a melee round
    (``_melee_blow_distributions``).  Summons and TELE_LEVEL removed as
    check_mspell_arena does.  Each damage distribution is the existing
    evaluators' with this character's resistances.  Melee is counted from the
    first action, before it can have reached the character.
  * maximum dice HP; the race's speed (set_individual_speed: fixed in the arena).

Character (only what the board shows):
  * ``attack_plan``: the fight owner's attacks on a board with the arena's item rules
    (no wand, no throw).  An absorbed power counts for its displayed charges only,
    then melee; the launcher only when melee is refused, for its ammunition.
  * current HP, current speed, AC, the abilities on the board.  No potion, no
    healing power, no regeneration is counted.

Kill time: mean = HP / (damage per action * DAMAGE_MARGIN), widened by
KILL_TIME_CV * sqrt(mean) as a normal; plus APPROACH_ACTIONS for a melee plan.

Where the number errs:
  * low: melee counted while it walks up, no healing, no regeneration, no launcher
    fire on the walk up, monster HP at its maximum.
  * high: stat, experience and disenchant drains; a monster that flees from melee.
    DAMAGE_MARGIN stands against these.
  * mechanics not modelled refuse the fight (chance None): ``refusal``.  Paralysis,
    confusion, stun without the resistance, fear for a melee plan, blindness for a plan
    with no melee, and an invisible opponent without See Invisible.  Blindness for a
    melee plan counts the whole fight at BLIND_MARGIN.  Unknown means do not fight.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, exp, sqrt

import numpy as np

from hengbot import attack_expectation, me_device_attacks
from hengbot.model import MonsterState, Position
from hengbot.monrace_knowledge import SUMMON_ABILITIES
from hengbot.monster_melee_evaluator import melee_action_distribution
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    ability_selection_probabilities,
    ranged_action_distribution,
)
from hengbot.policy_constants import RESIST_FLAG_BY_ABILITY, speed_energy

WIN_CHANCE_LINE = 0.90  # owner 2026-11-05
DAMAGE_MARGIN = 0.85  # the drains and the fleeing the race does not model
BLIND_MARGIN = 0.75  # the player's blow at a monster it cannot see
KILL_TIME_CV = 0.5  # one action's damage varies by half its mean (hits and crits)
KILL_TIME_SIGMAS = 3
APPROACH_ACTIONS = 4  # generate_challenge_arena: the opponent stands 5 cells away
LONGEST_FIGHT_ACTIONS = 400  # beyond it regeneration and charges decide: not modelled
LAUNCHER_HIT_MARGIN = 0.75  # the shot's hit chance is not on the board
HEAL_PER_LEVEL = 6  # mspell heal: rlev * 6
# Actions a teleport costs a melee plan: the walk back over the arena.
LOST_ACTIONS = {"TPORT": 10, "TELE_AWAY": 10, "BLINK": 5}
# regen_monster: maxhp / 100 every 10 player turns at normal speed, doubled with REGENERATE.
REGEN_PER_ACTION = 0.001

_STUN_ABILITIES = frozenset({"BR_SOUN", "BR_PLAS", "BO_PLAS", "BR_FORC", "BR_GRAV", "ROCKET"})
_NEEDS = (
    ("paralysis", "free_action", frozenset({"HOLD"}), frozenset({"PARALYZE"})),
    ("confusion", "resist_conf", frozenset({"CONF", "BR_CONF"}), frozenset({"CONFUSE"})),
    ("stun", "resist_sound", _STUN_ABILITIES, frozenset({"STUN"})),
)


@dataclass(frozen=True)
class Odds:
    chance: float | None  # None: a mechanic not modelled, do not fight
    refusal: str | None = None
    kill_actions: float = 0.0
    monster_actions_per_action: float = 0.0
    expected_damage_per_monster_action: float = 0.0
    damage_per_action: float = 0.0
    plan: str = ""

    @property
    def accepted(self) -> bool:
        return self.chance is not None and self.chance >= WIN_CHANCE_LINE


def opponent_state(snapshot, race_id: int, knowledge) -> MonsterState:
    """The opponent at full HP, beside the character (the attack scores' question)."""
    here = snapshot.player.position
    return MonsterState(
        index=1, position=Position(here.y + 1, here.x), hp=knowledge.max_hp,
        max_hp=knowledge.max_hp, distance=1, friendly=False, pet=False, speed=knowledge.speed, race_id=race_id,
        level=knowledge.level, can_summon=False, max_melee_damage=knowledge.max_melee_damage,
        max_ranged_damage=knowledge.max_ranged_damage,
    )


def open_to_blindness(snapshot, knowledge) -> bool:
    return "resist_blind" not in snapshot.player.abilities and bool(
        "BLIND" in knowledge.abilities
        or any(blow.effect == "BLIND" for blow in knowledge.blows))


def refusal(snapshot, knowledge, melee_plan: bool) -> str | None:
    """The mechanic the race does not model and this character is open to, else None."""
    abilities = snapshot.player.abilities
    blow_effects = {blow.effect for blow in knowledge.blows}
    for name, resist, spells, effects in _NEEDS:
        if resist not in abilities and (knowledge.abilities & spells or blow_effects & effects):
            return name
    if melee_plan and "resist_fear" not in abilities and (
            "SCARE" in knowledge.abilities or "TERRIFY" in blow_effects):
        return "fear"
    if not melee_plan and open_to_blindness(snapshot, knowledge):
        return "blindness"
    if "INVISIBLE" in knowledge.flags and "see_invisible" not in abilities:
        return "invisible"
    return None


def _power_charges(policy, power) -> int:
    """The displayed uses left of the absorbed power (me_device_attacks' rows)."""
    _turn, rows = getattr(policy, "_me_device_lists", {}).get(power.kind, (0, ()))
    for row in rows:
        if me_device_attacks.row_is(power, row):
            return (max(0, row["max"] - row["charging"]) if power.kind == "rod"
                    else row["current"])
    return 0


def attack_plan(policy, arena_board, target) -> list[tuple[float, float, str]]:
    """(damage per action, uses, name), strongest first."""
    plan = []
    best = me_device_attacks.strongest(policy, arena_board, target, "2")
    if best is not None:
        plan.append((best[0], _power_charges(policy, best[1]), "power"))
    melee = attack_expectation.melee(policy, arena_board, target)
    if melee > 0:
        plan.append((melee, float("inf"), "melee"))
    else:
        ammo = policy._matching_ammo(arena_board)
        if ammo is not None:
            shot = policy._estimated_ranged_damage_per_shot(arena_board) * LAUNCHER_HIT_MARGIN
            if shot > 0:
                plan.append((shot, ammo.count, "launcher"))
    return sorted(plan, key=lambda row: -row[0])


def _kill_actions(hp: float, plan, recovery_per_action: float, margin: float) -> float | None:
    """Actions to deal ``hp`` by the plan while the opponent recovers; None: never."""
    actions = 0.0
    for damage, uses, _name in plan:
        effective = damage * margin - recovery_per_action
        if effective <= 0:
            continue
        needed = hp / effective
        if needed <= uses:
            return actions + needed
        actions += uses
        hp -= uses * effective
    return None


def _selection(knowledge) -> tuple[object, dict[str, float]]:
    """The arena's race (check_mspell_arena) and its spell selection."""
    arena_race = replace(
        knowledge, abilities=knowledge.abilities - SUMMON_ABILITIES - {"TELE_LEVEL"})
    return arena_race, ability_selection_probabilities(
        arena_race, SpellSelectionContext(distance=1, summon_possible=False))


def monster_action_distribution(policy, snapshot, knowledge, arena_race, selection) -> np.ndarray:
    """Damage of one opponent action, by damage, over every spell and the melee round."""
    flags = frozenset(flag for ability, flag in RESIST_FLAG_BY_ABILITY.items()
                      if ability in snapshot.player.abilities)
    ranged, _floor = ranged_action_distribution(
        arena_race, selection_probabilities=selection, flags=flags,
        player_hp=snapshot.player.hp, blind=False, saving_skill=snapshot.player.saving_skill)
    cast = min(1.0, knowledge.spell_frequency / 100.0 * sum(selection.values()))
    melee = melee_action_distribution(
        policy._melee_blow_distributions(snapshot, knowledge, False) if knowledge.blows else ())
    action = np.zeros(max(max(ranged, default=0) + 1, melee.size), dtype=np.float64)
    for damage, probability in ranged.items():
        action[damage] += probability
    action[0] = max(0.0, action[0] - (1.0 - cast))  # the rest of the zero entry cast nothing
    action[: melee.size] += (1.0 - cast) * melee
    return action


def alive_after(action: np.ndarray, hp: int, actions: int) -> np.ndarray:
    """P(total damage <= hp) after 0..actions opponent actions (the game dies below 0)."""
    held = np.zeros(hp + 1, dtype=np.float64)
    held[0] = 1.0
    alive = [1.0]
    for _ in range(actions):
        held = np.convolve(held, action)[: hp + 1]
        alive.append(float(held.sum()))
    return np.array(alive)


def _kill_time_weights(mean: float) -> list[tuple[int, float]]:
    deviation = max(1e-6, KILL_TIME_CV * sqrt(mean))
    low = max(1, int(mean - KILL_TIME_SIGMAS * deviation))
    high = ceil(mean + KILL_TIME_SIGMAS * deviation)
    weights = [(n, exp(-(((n - mean) / deviation) ** 2) / 2)) for n in range(low, high + 1)]
    total = sum(weight for _, weight in weights)
    return [(n, weight / total) for n, weight in weights]


def judge(policy, snapshot, race_id: int) -> Odds:
    """The chance to win against ``race_id`` from this board; a None chance refuses."""
    knowledge = policy._monrace_knowledge.get(race_id)
    if knowledge is None:
        return Odds(None, "unknown-opponent")
    arena_board = replace(snapshot, inside_arena=True)
    plan = attack_plan(policy, arena_board, opponent_state(snapshot, race_id, knowledge))
    if not plan:
        return Odds(None, "no-attack")
    shown = {"damage_per_action": plan[0][0], "plan": plan[0][2]}
    melee_plan = any(row[2] == "melee" for row in plan)
    refused = refusal(snapshot, knowledge, melee_plan)
    if refused is not None:
        return Odds(None, refused, **shown)
    arena_race, selection = _selection(knowledge)
    ratio = speed_energy(knowledge.speed) / max(1, speed_energy(snapshot.player.speed))
    cast = knowledge.spell_frequency / 100.0
    regen = knowledge.max_hp * REGEN_PER_ACTION * (2 if "REGENERATE" in knowledge.flags else 1)
    heal = selection.get("HEAL", 0.0) * cast * knowledge.level * HEAL_PER_LEVEL * ratio
    # The player's unseen blow hits at half the chance, and melee blinded strikes only a
    # remembered cell: the whole fight is counted at the blind margin when it can happen.
    margin = DAMAGE_MARGIN * (BLIND_MARGIN if open_to_blindness(snapshot, knowledge) else 1.0)
    kill = _kill_actions(knowledge.max_hp, plan, regen + heal, margin)
    if kill is None:
        return Odds(0.0, None, **shown)
    if plan[0][2] == "melee":
        lost = sum(selection.get(name, 0.0) * actions for name, actions in LOST_ACTIONS.items())
        # A moving opponent walks back too; one that never moves waits for the whole walk.
        walk_share = 1.0 if "NEVER_MOVE" in knowledge.flags else 1.0 / (1.0 + ratio)
        lost_share = cast * lost * ratio * walk_share
        if lost_share >= 1.0:
            return Odds(0.0, None, **shown)
        kill = kill / (1.0 - lost_share) + APPROACH_ACTIONS
    if kill > LONGEST_FIGHT_ACTIONS:
        return Odds(0.0, None, kill_actions=kill, **shown)
    action = monster_action_distribution(policy, snapshot, knowledge, arena_race, selection)
    weights = _kill_time_weights(kill)
    longest = ceil(weights[-1][0] * ratio)
    alive = alive_after(action, max(0, snapshot.player.hp), longest)
    chance = sum(weight * alive[ceil(n * ratio)] for n, weight in weights)
    return Odds(
        float(min(1.0, chance)), None, kill_actions=kill, monster_actions_per_action=ratio,
        expected_damage_per_monster_action=float(action @ np.arange(action.size)), **shown,
    )
