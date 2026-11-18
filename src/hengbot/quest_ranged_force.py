"""The ranged requirement of a quest row: ``required_force.ranged`` (Q25), or the launcher
and its rounds read the same way (Q2, Q22, Q31: ``launcher_devices``).

Owner 2026-11-04, Q25: 「1なら180、2なら120。魔道具術師は有効な攻撃魔法道具も考慮に入れて良い。」,
with 1発65以上・矢弾40発以上: the fire to kill the summoning イプシシマス quickly.

``ranged`` names ``shot_average``, ``ammo``, ``turn_average`` and, for the classes in
``device_classes``, the ``reference_race`` the devices are scored against.  A row may
override the last with ``ranged_turn_average``.

The launcher: the game's own figures on the ammunition's name, "(68/shot 121/turn)"
(flavor-describer.cpp describe_ammo_detail, describe_fire_energy: average damage and
shots per turn of the worn launcher), which is what the player reads.  A stack counts
when its figure per shot meets ``shot_average``.

A device, for a class in ``device_classes``: an absorbed attack power, or a carried attack
wand or rod with a charge.  Its figure is the expected damage of one use against the
reference race, success rate included (me_device_attacks.expected_damage and the game's
rate of an absorbed power, me_power_success; attack_expectation's use chance of a carried
one).  It takes one player turn, so that figure is both its per-use and its per-turn figure.
It counts when it meets ``shot_average``, and then each charge is one shot: charges and
qualifying ammunition add up towards ``ammo``.  The turn figure is the best single one of
the launcher's and the devices'; they are not added.

An absorbed power counts at its capacity, its count (the displayed ``max``: a staff's or
wand's charges, a rod's copies), not at the charges it holds now (owner 2026-11-14 「ドラゴンの
火炎の魔法棒ならもっと威力があるし成功率も担保できている。比較方法が怠惰ではないか？」): the
inn's stay refills every absorbed staff and wand and readies every rod
(cmd-building/cmd-inn.cpp charge_magic_eating_energy), and the bot stays there before it
enters such a quest (me_inn_refill).  The same stay ends a stun (back_to_health), so the
rate is the unstunned one.  n1-b life-397 (Lv45, 2026-11-14 15:56) held Dragon's Flame
(wand, 7 charges, all spent) at 200 against イプシシマス: the gate read only the charged
衰弱 at the stunned list's 75% (93.75 < 120), where the refilled flame reads 200 x 95%.

Q2, Q22 and Q31 read the same (owner 2026-11-18 「魔道具術師は魔法道具の力で読む」: 「Q2・Q22・Q31 も
Q25 と同じく、取り込んだ攻撃の力（と攻撃の魔法棒・ロッド）の成功率込みの期待値と回数で条件を満たせば
受ける。足りない分だけ弓と矢で補う。」, and earlier the same day 「魔道具術師は矢の威力ではなく魔法道具の
攻撃力で評価する。」).  Their force names a worn ``launcher`` (Q2's ``min_average_damage`` 25 over the
carried rounds, Q22's 18, Q31's none) and ``throwing_items.launcher_ammo`` 99; its
``launcher_devices`` names the ``device_classes`` and the ``reference_races`` (the monsters the
quest's shots are for).  ``ranged_requirement`` reads that as a ranged requirement: ``shot_average`` is the
launcher's per-shot average, ``ammo`` the rounds, no ``turn_average``.  A device counts when its
expected damage meets the per-shot figure against every reference race (and deals some), each
charge one shot, as Q25's.  ``settled_force`` gives the force the rest: the device charges leave
``launcher_ammo`` minus them to the launcher, whose rules (wear one, its average over those
rounds, the ammunition purchase) apply to that remainder only; no remainder drops the launcher
and its rounds from the force.  Every town reader of the launcher and the rounds reads the
settled force (policy_quest ``_quest_carry_status``, ``_quest_carry_target_for_item``,
``_quest_damage_ammo_ware``, policy ``_preferred_home_quest_launcher``, the optimizer's quest
launcher in policy_equipment, quest_force_rows.resolve).

The Magic-Eater's 50F+ rule (me_deep_launcher.ammo_unneeded, owner 2026-11-18: no ammunition
below 100 damage per turn) closes the remainder: the launcher cannot fill it, so a force left
with one asks no launcher and no rounds and is short (``ready`` False, ``SHORT``) instead of
buying rounds the 50F+ rule deposits again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hengbot import attack_expectation, me_capability, me_deep_launcher, me_device_attacks
from hengbot.item_reservation import decision_memo
from hengbot.model import TVAL_ROD, TVAL_WAND

_DISPLAY = re.compile(r"\((\d+)/shot (\d+)/turn\)")
_AMMO_CARRY = "launcher_ammo"
LAUNCHER_DEVICES = "launcher_devices"
# Fields of a settled force: the requirement it was settled against (``settled_force`` runs once), and
# a remainder the launcher cannot fill (the 50F+ rule).
SETTLED = "ranged_settled"
SHORT = "ranged_short"


@dataclass(frozen=True)
class RangedScore:
    turn: float       # the best damage per player turn that qualifies
    shots: int        # qualifying ammunition and device charges
    device_shots: int


def ranged_requirement(force) -> dict | None:
    """The force's ranged requirement: ``ranged`` (Q25), or the one its ``launcher``,
    ``launcher_ammo`` and ``launcher_devices`` make (Q2, Q22, Q31), or None."""
    if not isinstance(force, dict):
        return None
    if isinstance(force.get("ranged"), dict):
        return force["ranged"]
    if isinstance(force.get(SETTLED), dict):
        return force[SETTLED]
    devices, launcher = force.get(LAUNCHER_DEVICES), force.get("launcher")
    throwing = force.get("throwing_items", {})
    if not isinstance(devices, dict) or not isinstance(launcher, dict) or not isinstance(throwing, dict):
        return None
    return {"shot_average": float(launcher.get("min_average_damage", 0) or 0),
            "ammo": int(throwing.get(_AMMO_CARRY, 0) or 0),
            "device_classes": list(devices.get("device_classes", ())),
            "reference_races": list(devices.get("reference_races", ()))}


def _launcher(snapshot, launcher, shot_floor: float) -> tuple[float, int]:
    """(best /turn, count) of the worn launcher's stacks at the per-shot floor."""
    if launcher is None:
        return 0.0, 0
    stacks = [(item, _DISPLAY.search(item.name)) for item in snapshot.inventory
              if item.tval == launcher.ammo_tval and item.count > 0]
    good = [(item, match) for item, match in stacks
            if match is not None and int(match.group(1)) >= shot_floor]
    return (max((float(match.group(2)) for _, match in good), default=0.0),
            sum(item.count for item, _ in good))


def _reference_flags(policy, ranged) -> tuple[frozenset, ...]:
    """The known flags of each reference race (``reference_race`` or ``reference_races``)."""
    races = ranged.get("reference_races")
    if races is None:
        races = (ranged.get("reference_race"),)
    found = []
    for race in races:
        knowledge = policy._monrace_knowledge.get(race)
        found.append(knowledge.flags if knowledge is not None else frozenset())
    return tuple(found) or (frozenset(),)


def _least_damage(power, level, flag_sets) -> float:
    """One successful use's expected damage against the reference race it hurts least."""
    return min(me_device_attacks.expected_damage(power, level, flags) for flags in flag_sets)


# The stun the gate scores an absorbed power under: none, the inn's stay ends it.
GATE_STUN = 0


def _absorbed(policy, snapshot, flag_sets):
    """(expected damage per use, charges) of each absorbed attack power at its capacity."""
    level = snapshot.player.level
    for power, row in me_device_attacks.held_powers(policy):
        if not power.group_only:
            success = me_device_attacks.power_success(policy, snapshot, power, row, stun=GATE_STUN)
            yield (success * _least_damage(power, level, flag_sets),
                   me_capability.count(policy, snapshot, power.kind, power.sval))


def _counts(damage: float, floor: float) -> bool:
    """A use counts as a shot: it meets the per-shot figure and deals some damage (Q31 names
    no figure)."""
    return damage >= floor and damage > 0


def absorbed_short(policy, snapshot, ranged) -> bool:
    """An absorbed power the requirement counts (at its capacity it meets ``shot_average``)
    holds less than that capacity now: the inn's stay before entry refills it (me_inn_refill)."""
    if snapshot.player.class_id not in ranged.get("device_classes", ()):
        return False
    flag_sets = _reference_flags(policy, ranged)
    floor, level = float(ranged["shot_average"]), snapshot.player.level
    return any(
        not power.group_only and not me_device_attacks.row_full(power, row)
        and _counts(me_device_attacks.power_success(policy, snapshot, power, row, stun=GATE_STUN)
                    * _least_damage(power, level, flag_sets), floor)
        for power, row in me_device_attacks.held_powers(policy))


def _carried(snapshot, flag_sets):
    """(expected damage per use, charges) of each carried attack wand and rod."""
    player = snapshot.player
    for item in snapshot.inventory:
        if item.tval == TVAL_WAND and item.known and item.charges > 0:
            kind, chance, shots = "wand", attack_expectation.device_use_success, item.charges
        elif item.tval == TVAL_ROD and item.known and not item.charging:
            kind, chance, shots = "rod", attack_expectation.rod_use_success, item.count
        else:
            continue
        power = me_device_attacks.POWERS.get((kind, item.sval))
        if power is not None and not power.group_only:
            yield (chance(player.device_skill, power.level)
                   * _least_damage(power, player.level, flag_sets), shots)


def _devices(policy, snapshot, ranged, shot_floor: float) -> tuple[float, int]:
    if snapshot.player.class_id not in ranged.get("device_classes", ()):
        return 0.0, 0
    flag_sets = _reference_flags(policy, ranged)
    good = [(damage, charges) for damage, charges in (*_absorbed(policy, snapshot, flag_sets),
                                                      *_carried(snapshot, flag_sets))
            if _counts(damage, shot_floor) and charges > 0]
    return max((damage for damage, _ in good), default=0.0), sum(charges for _, charges in good)


def score(policy, snapshot, ranged) -> RangedScore:
    floor = float(ranged["shot_average"])
    launcher_turn, ammo = _launcher(snapshot, policy._equipped_launcher(snapshot), floor)
    device_turn, charges = _devices(policy, snapshot, ranged, floor)
    return RangedScore(max(launcher_turn, device_turn), ammo + charges, charges)


def _turn_floor(force, row) -> float:
    return float(row.get("ranged_turn_average", force["ranged"]["turn_average"]))


def turn_met(policy, snapshot, force, row) -> bool:
    """The row's damage per turn is met; ammunition can still be bought, this cannot."""
    return "ranged" not in force or score(policy, snapshot, force["ranged"]).turn >= _turn_floor(force, row)


def settled_force(policy, snapshot, force) -> dict:
    """``force`` asking only the launcher and rounds the device charges leave.

    Settled once (``SETTLED`` keeps the requirement read before), so a reader handed a force
    another reader settled reads the same remainder."""
    if not isinstance(force, dict) or SETTLED in force:
        return force
    ranged = ranged_requirement(force)
    if ranged is None:
        return force
    settled = {**force, SETTLED: ranged}
    throwing = force.get("throwing_items", {})
    if (not isinstance(throwing, dict) or _AMMO_CARRY not in throwing
            or snapshot.player.class_id not in ranged.get("device_classes", ())):
        return settled
    # Every town reader settles its force: the device count is read once a decision.
    charges = decision_memo(
        policy, "quest_ranged_force.charges", snapshot,
        (float(ranged["shot_average"]), tuple(ranged.get("device_classes", ())),
         tuple(ranged.get("reference_races") or (ranged.get("reference_race"),))),
        lambda: _devices(policy, snapshot, ranged, float(ranged["shot_average"]))[1])
    rest = max(0, int(throwing[_AMMO_CARRY]) - charges)
    closed = rest > 0 and decision_memo(
        policy, "quest_ranged_force.closed", snapshot, None,
        lambda: me_deep_launcher.ammo_unneeded(policy, snapshot))
    if closed or (rest == 0 and "ranged" not in force):
        # The devices cover the rounds, or the 50F+ rule leaves the launcher nothing to fill.
        settled.pop("launcher", None)
        settled["throwing_items"] = {name: count for name, count in throwing.items()
                                     if name != _AMMO_CARRY}
        if closed:
            settled[SHORT] = True
        return settled
    settled["throwing_items"] = {**throwing, _AMMO_CARRY: rest}
    return settled


def ready(policy, snapshot, force) -> bool:
    if force.get(SHORT):
        return False
    if "ranged" not in force:
        return True
    found = score(policy, snapshot, force["ranged"])
    return found.turn >= _turn_floor(force, force) and found.shots >= int(force["ranged"]["ammo"])


def details(policy, snapshot, force) -> dict:
    ranged = ranged_requirement(force)
    found = score(policy, snapshot, ranged)
    shots = {"measured": found.shots, "required": int(ranged["ammo"]),
             "device": found.device_shots}
    if "ranged" not in force:
        return {"shots": shots, "short": bool(force.get(SHORT))}
    return {"turn": {"measured": found.turn, "required": _turn_floor(force, force)},
            "shots": shots}
