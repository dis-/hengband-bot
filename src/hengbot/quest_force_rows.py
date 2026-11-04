"""Alternative acceptance rows of a quest's ``required_force``.

``required_force`` itself is the first row; ``force_alternatives`` lists the others
(QUEST_18: owner 2026-11-04 「条件1はそれで良い。加速が潤沢にあり、常時加速できる場合の条件を
別途求めて。」).  A row names its ``min_hp``, ``min_expected_dps``, ``heal_potions``
and ``speed_potions``, and may name

 * ``speed_alternatives``: what stands for its Speed potions, ``gear_speed_bonus``
   (the permanent speed the character shows unhasted) and ``absorbed_charges`` (the
   charges an absorbed Speed power at the reliable success rate must hold);
 * ``always_hasted``: the row's fight stays hasted (the arithmetic of its floors
   assumes it), so a scene doses whenever the haste is off.

``resolve`` answers with one force for this character, so acceptance, purchase, the
town route and the fight all read the same counts through
``_strategy_force_for_snapshot``.  A row counts when the character's maximum HP and
measured damage meet its floors; of those, the one that asks for the fewest Speed
potions.  With no such row the floors of the first row refuse the quest and no potion
is asked for: a character that cannot take the quest yet spends nothing on it.
"""

from __future__ import annotations

from hengbot import me_capability

ALTERNATIVES = "force_alternatives"
ROW_FIELDS = ("min_hp", "min_expected_dps", "heal_potions", "speed_potions")
# Field of the resolved force: an absorbed power at the reliable rate waives the Speed
# potions (me_capability.force_count), but holds too few charges for this row yet.
ABSORBED_SHORT = "absorbed_speed_short"
_WAITING_FOR_CHARGES = 1 << 16
_SPEED_POTION = me_capability.FORCE_KINDS["speed_potions"]
_NORMAL_SPEED = 110
_POTION_SPEED_BONUS = 10


def _unhasted_speed(policy, snapshot) -> int:
    hasted = policy._player_hasted(snapshot)
    return snapshot.player.speed - (_POTION_SPEED_BONUS if hasted else 0)


def _speed_cost(policy, snapshot, row: dict) -> int:
    """The Speed potions this row asks of this character."""
    alternatives = row.get("speed_alternatives", {})
    gear = alternatives.get("gear_speed_bonus")
    if gear is not None and _unhasted_speed(policy, snapshot) >= _NORMAL_SPEED + int(gear):
        return 0
    if me_capability.replaced_by_absorbed(policy, snapshot, _SPEED_POTION):
        needed = int(alternatives.get("absorbed_charges", 0))
        power = me_capability.replacing_power(_SPEED_POTION)
        held = me_capability.charges(policy, snapshot, *power)
        return 0 if held >= needed else _WAITING_FOR_CHARGES
    return int(row.get("speed_potions", 0))


def resolve(policy, snapshot, force: dict) -> dict:
    """``force`` with the row that serves this character merged in."""
    alternatives = force.get(ALTERNATIVES)
    if not alternatives:
        return force
    rows = [{name: force[name] for name in ROW_FIELDS if name in force}, *alternatives]
    max_hp = snapshot.player.max_hp
    damage = policy._strategy_measured_dps(snapshot, force)
    capable = [
        (_speed_cost(policy, snapshot, row), index) for index, row in enumerate(rows)
        if max_hp >= int(row["min_hp"]) and damage >= float(row["min_expected_dps"])
    ]
    if not capable:
        return {**force, "heal_potions": 0, "speed_potions": 0}
    cost, index = min(capable)
    resolved = {**force, **rows[index]}
    if cost == _WAITING_FOR_CHARGES:
        resolved[ABSORBED_SHORT] = True
    else:
        resolved["speed_potions"] = cost
    return resolved
