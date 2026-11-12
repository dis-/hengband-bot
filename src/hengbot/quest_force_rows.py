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
``_strategy_force_for_snapshot``.  A row counts when the character's maximum HP,
measured damage and (where the force names one) ranged damage per turn meet its floors
(quest_ranged_force); of those, the one that asks for the fewest Speed potions.  With no such row the floors of the first row refuse the quest and no potion
is asked for: a character that cannot take the quest yet spends nothing on it.
"""

from __future__ import annotations

from hengbot import haste_read, me_capability, quest_ranged_force
from hengbot.model import SV_POTION_SPEED

ALTERNATIVES = "force_alternatives"
ROW_FIELDS = ("min_hp", "min_expected_dps", "heal_potions", "speed_potions")
# Field of the resolved force: an absorbed power at the reliable rate waives the Speed
# potions (me_capability.force_count), but holds too few charges for this row yet.
ABSORBED_SHORT = "absorbed_speed_short"
_WAITING_FOR_CHARGES = 1 << 16
_SPEED_POTION = me_capability.FORCE_KINDS["speed_potions"]
_NORMAL_SPEED = 110
_POTION_SPEED_BONUS = 10
# A character no row serves buys nothing for the quest (only QUEST_25 names these).
_NO_KIT = {"throwing_items": {}, "required_potions": {}}


def _unhasted_speed(policy, snapshot) -> int:
    return snapshot.player.speed - (_POTION_SPEED_BONUS if haste_read.adds_speed(snapshot) else 0)


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
        and quest_ranged_force.turn_met(policy, snapshot, force, row)
    ]
    if not capable:
        return {**force, "heal_potions": 0, "speed_potions": 0, **_NO_KIT}
    cost, index = min(capable)
    resolved = quest_ranged_force.settle_ammo(policy, snapshot, {**force, **rows[index]})
    if cost == _WAITING_FOR_CHARGES:
        resolved[ABSORBED_SHORT] = True
    else:
        resolved["speed_potions"] = cost
    return resolved


DEPART_FLAG = "speed_required_to_depart"


def speed_short(policy, snapshot, force: dict) -> bool:
    """``force`` (resolved) asks for more Speed doses than the character carries: fewer Speed
    potions than its row's count (0 for permanent speed or an absorbed power at the reliable
    rate), or an absorbed power holding too few charges for its row."""
    if force.get(ABSORBED_SHORT):
        return True
    required = me_capability.force_count(policy, snapshot, force, "speed_potions")
    return policy._exact_potion_count(snapshot, SV_POTION_SPEED) < required


def departure_speed_short(policy, snapshot, quest_id: int) -> bool:
    """A strategy whose ``required_force`` names ``speed_required_to_depart`` (QUEST_18, owner
    2026-11-12 「加速手段を十分数確保することを必須にする。」) is entered only with its row's
    Speed doses, as it is accepted only with them: a quest taken earlier, or doses spent since,
    sends the character back to the shops (the quest's carry rung buys them) instead of in."""
    profile = policy.approved_quest_strategy(quest_id)
    if profile is None or not profile.required_force.get(DEPART_FLAG):
        return False
    return speed_short(policy, snapshot, policy._strategy_force_for_snapshot(snapshot, profile))
