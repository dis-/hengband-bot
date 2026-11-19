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

``teleport_scrolls_without_absorbed`` (QUEST_33, owner 2026-11-19 「Q33では離脱に取り込んだテレポート
の杖の使用を許可する。ない場合はテレポートの巻物を40巻用意すること。」): a character with no absorbed
Teleportation (me_capability ``has``) is asked that many Scrolls of Teleportation in
``required_scrolls.teleport``'s place; one that has absorbed it keeps the row's count.  The resolved
force carries it to acceptance, purchase, the Home withdrawal and departure alike.

``resolve`` answers with one force for this character, so acceptance, purchase, the
town route and the fight all read the same counts through
``_strategy_force_for_snapshot``.  A row counts when the character's maximum HP,
measured damage and (where the force names one) ranged damage per turn meet its floors
(quest_ranged_force); of those, the one that asks for the fewest Speed potions.

The damage floors are per 10 game turns (owner 2026-11-19 「攻撃力の判定を1行動あたりではなく、
10ゲームターンあたりのダメージで評価して」, ``row_damage``): the measured per-action figure at the
permanent speed, or at the hasted speed for an ``always_hasted`` row.  A floor derived per action
at +0 keeps its number; the always-hasted rows whose floor was halved per action for the haste
(QUEST_18 row 2: 75, QUEST_25 row 2: 100 and ranged 120) read twice that per 10 game turns, the
same per-action line at a +0 permanent speed.  With no such row the floors of the first row refuse the quest and no potion
is asked for: a character that cannot take the quest yet spends nothing on it.
"""

from __future__ import annotations

from hengbot import attack_expectation, haste_read, me_capability, quest_one_turn_kill, quest_ranged_force
from hengbot.model import SV_POTION_SPEED, SV_STAFF_TELEPORTATION

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


TELEPORT_SCROLLS_WITHOUT_ABSORBED = "teleport_scrolls_without_absorbed"


def valid_teleport_scrolls(force: dict) -> bool:
    """The schema (quest_strategies reads it at load)."""
    value = force.get(TELEPORT_SCROLLS_WITHOUT_ABSORBED, 0)
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _teleport_scrolls(policy, snapshot, force: dict) -> dict:
    """``required_scrolls.teleport`` raised to ``teleport_scrolls_without_absorbed`` for a character
    with no absorbed Teleportation (module docstring)."""
    floor = int(force.get(TELEPORT_SCROLLS_WITHOUT_ABSORBED, 0))
    scrolls = force.get("required_scrolls")
    if (not floor or not isinstance(scrolls, dict) or "teleport" not in scrolls
            or me_capability.has(policy, snapshot, "staff", SV_STAFF_TELEPORTATION)):
        return force
    return {**force, "required_scrolls": {**scrolls, "teleport": max(int(scrolls["teleport"]), floor)}}


def resolve(policy, snapshot, force: dict) -> dict:
    """``force`` with the row that serves this character merged in."""
    return _teleport_scrolls(policy, snapshot, _resolve_row(policy, snapshot, force))


def _resolve_row(policy, snapshot, force: dict) -> dict:
    one_turn = quest_one_turn_kill.tier(policy, snapshot, force) if quest_one_turn_kill.requirement(
        force) is not None else "full"
    if one_turn is None:
        # QUEST_32: no row serves a character one turn does not kill the summoner with.
        return {**force, "heal_potions": 0, "speed_potions": 0, **_NO_KIT, "required_scrolls": {}}
    if one_turn == "hasted" and "haste_doses" in quest_one_turn_kill.requirement(force):
        # QUEST_32's hasted row (owner 2026-11-19 「加速手段が十分なら135以上で良いとする」, read per
        # 10 game turns at the hasted speed since 「10ゲームターンあたり」): its haste doses, Speed
        # potions or an absorbed Speed power holding that many charges, asked at acceptance and
        # at departure.  An ``always_hasted`` force (QUEST_33) asks its own Speed supplies.
        doses = quest_one_turn_kill.haste_doses(force)
        row = {"speed_potions": max(doses, int(force.get("speed_potions", 0))),
               "speed_alternatives": {"absorbed_charges": doses}}
        cost = _speed_cost(policy, snapshot, row)
        force = {**force, **row, DEPART_FLAG: True}
        if cost == _WAITING_FOR_CHARGES:
            force[ABSORBED_SHORT] = True
        else:
            force["speed_potions"] = cost
    alternatives = force.get(ALTERNATIVES)
    if not alternatives:
        # The launcher and rounds the device charges leave (quest_ranged_force: Q2, Q22, Q31).
        return quest_ranged_force.settled_force(policy, snapshot, force)
    rows = [{name: force[name] for name in ROW_FIELDS if name in force}, *alternatives]
    max_hp = snapshot.player.max_hp
    damage = policy._strategy_measured_dps(snapshot, force)
    capable = [
        (_speed_cost(policy, snapshot, row), index) for index, row in enumerate(rows)
        if max_hp >= int(row["min_hp"])
        and row_damage(policy, snapshot, force, row, damage) >= float(row["min_expected_dps"])
        and quest_ranged_force.turn_met(policy, snapshot, force, row)
    ]
    if not capable:
        return {**force, "heal_potions": 0, "speed_potions": 0, **_NO_KIT}
    cost, index = min(capable)
    resolved = quest_ranged_force.settled_force(policy, snapshot, {**force, **rows[index]})
    if cost == _WAITING_FOR_CHARGES:
        resolved[ABSORBED_SHORT] = True
    else:
        resolved["speed_potions"] = cost
    return resolved


def row_damage(policy, snapshot, force, row, per_action: float) -> float:
    """``per_action`` (the measured melee) per 10 game turns at the speed ``row`` fights at.

    Owner 2026-11-19 「攻撃力の判定を1行動あたりではなく、10ゲームターンあたりのダメージで評価して」:
    ``min_expected_dps`` is damage per 10 game turns, read at the permanent speed, or for an
    ``always_hasted`` row at the speed its haste assures (attack_expectation.force_speed)."""
    speed = attack_expectation.force_speed(snapshot, attack_expectation.row_always_hasted(force, row))
    return attack_expectation.per_10_game_turns(policy, snapshot, per_action, speed=speed)


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
    if profile is None:
        return False
    # The resolved force: QUEST_32's hasted row sets the flag for this character only.
    force = policy._strategy_force_for_snapshot(snapshot, profile)
    return bool(force.get(DEPART_FLAG)) and speed_short(policy, snapshot, force)
