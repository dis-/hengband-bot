"""The arena's fight as a chain: the opponent's HP and the distance (owner 2026-11-05).

Owner: 「直す」 to dropping the cut that rated a blinker 0: count the character's ranged damage
while the opponent is away, and rate low only when its ranged force does not reach.
Owner, the Magic-Eater's plan: 「加速し、敵を倒すまでの手数が最短になる動きを取る。近接攻撃によほど
優れていなければ遠距離攻撃が評価の中心になる。」

The state is (the opponent's HP in small bands, the distance in cells), with its probability;
no random draws.  The result is the chance of the kill at each action.

Game facts (the arena is one open lit room, 29 x 9, floor-generator.cpp build_arena):
  * An action: with the race's frequency a spell attempt (cast_spell), else a step, or a
    melee round when adjacent.  A spell attempt with nothing to cast is a step too.
  * The spell (choose_attack_spell, source_selection_probabilities): BLINK comes first at
    75% within 3 cells, with an attack spell on the race's list; from 4 cells away attacks
    come first at 85%.  Below 1/3 HP HEAL then an escape come first at 50% each; below 3/4
    HP HEAL comes late at 25%; at full HP HEAL and TPORT are not chosen at all.
  * BLINK lands 5-10 cells from where it stood (teleport_away(10)).  TPORT asks 22+ cells,
    which the room rarely has, then 11+ (teleport_away(45)).  TELE_AWAY puts the player in
    the farther half of the room (teleport_player_aux).  TELE_TO brings the player beside it.
  * A step goes toward the player, except beyond 5 cells for a race the character outranks:
    player level + 4 x its HP share > race level + 25 + 4 x the race's HP share (mon_will_run).
    NEVER_MOVE stays.  HEAL gives level x 6 (spell_RF6_HEAL).

The character's plans (arena._attack_key does the same):
  * STRIKE_OR_FIRE: adjacent melee; away the strongest ranged attack with uses left, else a step.
  * FEWEST_ACTIONS: the means of ``melee_is_fewest``, in every state.

Where it errs:
  * low: spell failure (25 - (level + 3) / 4 percent) is not taken off the teleports and the
    heals; rods recharge, which is not counted.
  * high: a power's uses are spent as their expected value over the states; the character's
    damage per action is its mean (the caller's KILL_TIME_CV stands for that); the monster's
    fear, which runs from melee in the open room, is not modelled (DAMAGE_MARGIN stands
    against it).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from hengbot.monster_ranged_evaluator import SpellSelectionContext, source_selection_probabilities

AWAY_ABILITIES = frozenset({"BLINK", "TPORT", "TELE_AWAY"})
# The abilities the chain is for: without any of them a plain fight stays adjacent.
CHAIN_ABILITIES = AWAY_ABILITIES | {"TELE_TO", "HEAL"}
STRIKE_OR_FIRE, FEWEST_ACTIONS = "strike-or-fire", "fewest-actions"
START_CELLS = 5  # generate_challenge_arena
BLINK_CELLS = 8  # 5-10 from where it stood, beside the character
TELEPORT_CELLS = 14  # the far part of a 29 x 9 room
FARTHEST_CELLS = 16
NEAR_CELLS = 3  # choose_attack_spell: distance < 4 chooses the tactic first
HOLDS_OFF_BEYOND = 5  # mon_will_run: monster.cdis <= 5 never runs
HOLD_OFF_LEVEL = 25
HEAL_PER_LEVEL = 6
HP_STEPS = 60  # the chain's bands of the opponent's HP
UNRESOLVED_BELOW = 1e-4  # the chain stops when this little is still fighting
# The HP share above the selection's band floor, and the share the selection reads for it.
HP_BANDS = ((0.75, 1.0), (1 / 3, 0.5), (0.0, 0.2))
ADJACENT, NEAR, FAR = range(3)
PLACES = (ADJACENT, NEAR, FAR)
_EVERY_CELL = range(1, FARTHEST_CELLS + 1)


@dataclass(frozen=True)
class Fight:
    kill_at: np.ndarray  # kill_at[n]: the chance the kill lands on the character's action n
    # (band index, place) -> the opponent's actions spent there.
    actions_at: dict[tuple[int, int], float]

    @property
    def kill_actions(self) -> float:
        """The mean, a fight not ended counted at its longest."""
        actions = np.arange(self.kill_at.size)
        return float(actions @ self.kill_at + (self.kill_at.size - 1) * (1.0 - self.kill_at.sum()))


def applies(race) -> bool:
    """The race's spells part the two or undo the damage: the walk alone does not decide."""
    return bool(race.abilities & CHAIN_ABILITIES)


def actions_by_ranged(hp, ranged, melee: float, walk: int):
    """Actions to deal ``hp`` by the rows in order, then by melee after the walk; inf: never."""
    left = np.asarray(hp, dtype=np.float64)
    actions = np.zeros_like(left)
    for damage, uses, _name in ranged:
        fired = np.minimum(left / damage, max(0.0, uses))
        actions = actions + fired
        left = left - fired * damage
    if melee > 0:
        return actions + (left > 1e-9) * (walk + left / melee)
    return actions + np.where(left > 1e-9, np.inf, 0.0)


def melee_is_fewest(hp, ranged, melee: float, walk: int):
    """Melee only when it is plainly fewer: the walk to reach it is in the same count."""
    hp = np.asarray(hp, dtype=np.float64)
    if melee <= 0:
        return np.zeros_like(hp, dtype=bool)
    return walk + hp / melee < actions_by_ranged(hp, ranged, melee, walk)


def place_of(cell: int) -> int:
    return ADJACENT if cell == 1 else NEAR if cell <= NEAR_CELLS else FAR


def selection_at(race, place: int, band: int) -> dict[str, float]:
    distance = 1 if place != FAR else NEAR_CELLS + 1
    return source_selection_probabilities(race, SpellSelectionContext(
        distance=distance, summon_possible=False, monster_hp_fraction=HP_BANDS[band][1]))


def _band_of(hp_share: float) -> int:
    return next(index for index, (floor, _share) in enumerate(HP_BANDS) if hp_share >= floor)


def _step(race, cell: int, band: int, player_level: int) -> int:
    if "NEVER_MOVE" in race.flags or cell == 1:
        return cell
    if (cell > HOLDS_OFF_BEYOND
            and player_level + 4 > race.level + HOLD_OFF_LEVEL + 4 * HP_BANDS[band][1]):
        return min(FARTHEST_CELLS, cell + 1)
    return cell - 1


def _action_row(race, cell: int, band: int, player_level: int, selection: dict[str, float]) -> np.ndarray:
    """Where the opponent's one action takes the distance from ``cell``."""
    row = np.zeros(FARTHEST_CELLS)
    cast = race.spell_frequency / 100.0
    spells = min(1.0, cast * sum(selection.values()))
    row[_step(race, cell, band, player_level) - 1] += 1.0 - spells
    moved = {"BLINK": BLINK_CELLS, "TPORT": TELEPORT_CELLS, "TELE_AWAY": TELEPORT_CELLS, "TELE_TO": 1}
    for ability, to_cell in moved.items():
        row[to_cell - 1] += cast * selection.get(ability, 0.0)
        spells -= cast * selection.get(ability, 0.0)
    row[cell - 1] += max(0.0, spells)
    return row


def _per_player_action(one_action: np.ndarray, ratio: float) -> np.ndarray:
    """``ratio`` actions: the whole ones, and the part as a chance of one more."""
    whole = int(ratio)
    part = ratio - whole
    return ((1.0 - part) * np.linalg.matrix_power(one_action, whole)
            + part * np.linalg.matrix_power(one_action, whole + 1))


def _hit(column: np.ndarray, steps: float) -> tuple[np.ndarray, float]:
    """``column`` by HP step after ``steps`` of damage, and what that killed."""
    whole = int(steps)
    part = steps - whole
    after = np.zeros_like(column)
    for shift, share in ((whole, 1.0 - part), (whole + 1, part)):
        if shift < column.size:
            after[: column.size - shift] += share * column[shift:]
    return after, float(column.sum() - after.sum())


def _raised(state: np.ndarray, steps: float) -> np.ndarray:
    """``state`` after ``steps`` of healing, for the whole state, capped at full HP."""
    whole = int(steps)
    part = steps - whole
    size = state.shape[0]
    after = np.zeros_like(state)
    for shift, share in ((whole, 1.0 - part), (whole + 1, part)):
        shift = min(shift, size - 1)
        after[shift:] += share * state[: size - shift]
        after[-1] += share * state[size - shift:].sum(axis=0)
    return after


class _Uses:
    """The ranged rows' uses, spent as their expected value."""

    def __init__(self, ranged):
        self.rows = [[damage, float(uses)] for damage, uses, _name in ranged]

    def left(self) -> list[tuple[float, float, str]]:
        return [(damage, uses, "") for damage, uses in self.rows if uses > 0]

    def spend(self, share: float) -> None:
        for row in self.rows:
            used = min(share, row[1])
            row[1] -= used
            share -= used
            if share <= 0:
                return


def _fires(plan: str, cell: int, hp: np.ndarray, left, melee: float) -> np.ndarray:
    """By HP step: whether the character fires from ``cell``; else it strikes or steps."""
    if not left:
        return np.zeros_like(hp, dtype=bool)
    if plan == FEWEST_ACTIONS:
        return ~melee_is_fewest(hp, left, melee, cell - 1)
    return np.full_like(hp, cell > 1 or melee <= 0, dtype=bool)


def _character_acts(state, plan, uses, melee, steps_per_damage, hp):
    """The character's action on the state: (the state after it, the kill)."""
    alive = max(float(state.sum()), 1e-12)
    left = uses.left()
    top = left[0][0] * steps_per_damage if left else 0.0
    fired = killed = 0.0
    after = np.zeros_like(state)
    for cell in _EVERY_CELL:
        column = state[:, cell - 1]
        firing = column * _fires(plan, cell, hp, left, melee)
        other = column - firing
        fired += float(firing.sum())
        moved, dead = _hit(firing, top)
        after[:, cell - 1] += moved
        killed += dead
        if cell == 1:
            moved, dead = _hit(other, melee * steps_per_damage)
            after[:, 0] += moved
            killed += dead
        else:
            after[:, cell - 2] += other
    uses.spend(fired / alive)
    return after, killed


def run(race, *, melee: float, ranged, ratio: float, player_level: int, margin: float,
        recovery_per_action: float, longest: int, plan: str = STRIKE_OR_FIRE,
        recast_every: int = 0) -> Fight:
    """``ranged`` is (damage per action, uses, name), strongest first.  ``recast_every``: the
    character spends the first action and every such action on its haste."""
    unit = race.max_hp / HP_STEPS
    hp = np.arange(1, HP_STEPS + 1) * unit
    bands = [_band_of(share) for share in (np.arange(HP_STEPS) + 0.5) / HP_STEPS]
    moves, heal_chance = [], []
    for band in range(len(HP_BANDS)):
        selections = [selection_at(race, place_of(cell), band) for cell in _EVERY_CELL]
        one_action = np.array([_action_row(race, cell, band, player_level, selections[cell - 1])
                               for cell in _EVERY_CELL])
        moves.append(_per_player_action(one_action, ratio))
        heal_chance.append(np.array([
            min(1.0, race.spell_frequency / 100.0 * selection.get("HEAL", 0.0) * ratio)
            for selection in selections]))
    places = np.array([place_of(cell) for cell in _EVERY_CELL])
    uses = _Uses(ranged)
    state = np.zeros((HP_STEPS, FARTHEST_CELLS))
    state[HP_STEPS - 1, START_CELLS - 1] = 1.0
    kill_at = np.zeros(longest + 1)
    actions_at = {(band, place): 0.0 for band in range(len(HP_BANDS)) for place in PLACES}
    for action in range(1, longest + 1):
        if not (recast_every and (action - 1) % recast_every == 0):
            state, kill_at[action] = _character_acts(state, plan, uses, melee, margin / unit, hp)
        if float(state.sum()) < UNRESOLVED_BELOW:
            break
        moved, healed = np.zeros_like(state), np.zeros_like(state)
        for index, band in enumerate(bands):
            row = state[index]
            for place in PLACES:
                actions_at[band, place] += float(row[places == place].sum()) * ratio
            healing = row * heal_chance[band]
            healed[index] = healing @ moves[band]
            moved[index] = (row - healing) @ moves[band]
        state = _raised(moved + _raised(healed, race.level * HEAL_PER_LEVEL / unit), recovery_per_action / unit)
    return Fight(kill_at, actions_at)
