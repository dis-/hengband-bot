"""The ranged requirement of a quest row: ``required_force.ranged``.

Owner 2026-11-04, Q25: 「1なら180、2なら120。魔道具術師は有効な攻撃魔法道具も考慮に入れて良い。」,
with 1発65以上・矢弾40発以上: the fire to kill the summoning イプシシマス quickly.

``ranged`` names ``shot_average``, ``ammo``, ``turn_average`` and, for the classes in
``device_classes``, the ``reference_race`` the devices are scored against.  A row may
override the last with ``ranged_turn_average``.

The launcher: the game's own figures on the ammunition's name, "(68/shot 121/turn)"
(flavor-describer.cpp describe_ammo_detail, describe_fire_energy: average damage and
shots per turn of the worn launcher), which is what the player reads.  A stack counts
when its figure per shot meets ``shot_average``.

A device, for a class in ``device_classes``: an absorbed attack power with a charge, or
a carried attack wand or rod.  Its figure is the expected damage of one use against the
reference race, success rate included (me_device_attacks.expected_damage and the game's
rate of an absorbed power, me_power_success; attack_expectation's use chance of a carried
one).  It takes one player turn, so that figure is both its per-use and its per-turn figure.
It counts when it meets ``shot_average``, and then each charge (a rod's ready count) is one
shot: charges and qualifying ammunition add up towards ``ammo``.  The turn figure is the
best single one of the launcher's and the devices'; they are not added.

An absorbed power's rate is the unstunned one (owner 2026-11-14 「95%じゃないのか」): a stun
ends before the quest is entered (the inn's stay ends it, cmd-building/cmd-inn.cpp
back_to_health), so the stun of the list's board or of this one does not lower the gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hengbot import attack_expectation, me_capability, me_device_attacks
from hengbot.model import TVAL_ROD, TVAL_WAND

_DISPLAY = re.compile(r"\((\d+)/shot (\d+)/turn\)")
_AMMO_CARRY = "launcher_ammo"


@dataclass(frozen=True)
class RangedScore:
    turn: float       # the best damage per player turn that qualifies
    shots: int        # qualifying ammunition and device charges
    device_shots: int


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


def _reference_flags(policy, ranged) -> frozenset:
    knowledge = policy._monrace_knowledge.get(ranged.get("reference_race"))
    return knowledge.flags if knowledge is not None else frozenset()


# The stun the gate scores an absorbed power under: none, the inn's stay ends it.
GATE_STUN = 0


def _absorbed(policy, snapshot, flags):
    """(expected damage per use, charges) of each absorbed attack power with a charge."""
    level = snapshot.player.level
    for power, row in me_device_attacks.held_powers(policy):
        if not power.group_only and me_device_attacks._available(power, row):
            success = me_device_attacks.power_success(policy, snapshot, power, row, stun=GATE_STUN)
            yield (success * me_device_attacks.expected_damage(power, level, flags),
                   me_capability.charges(policy, snapshot, power.kind, power.sval))


def _carried(snapshot, flags):
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
                   * me_device_attacks.expected_damage(power, player.level, flags), shots)


def _devices(policy, snapshot, ranged, shot_floor: float) -> tuple[float, int]:
    if snapshot.player.class_id not in ranged.get("device_classes", ()):
        return 0.0, 0
    flags = _reference_flags(policy, ranged)
    good = [(damage, charges) for damage, charges in (*_absorbed(policy, snapshot, flags),
                                                      *_carried(snapshot, flags))
            if damage >= shot_floor and charges > 0]
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


def settle_ammo(policy, snapshot, force) -> dict:
    """``force`` asking only the ammunition the device charges leave to carry."""
    ranged = force.get("ranged")
    throwing = force.get("throwing_items", {})
    if ranged is None or _AMMO_CARRY not in throwing:
        return force
    charges = score(policy, snapshot, ranged).device_shots
    return {**force, "throwing_items": {
        **throwing, _AMMO_CARRY: max(0, int(throwing[_AMMO_CARRY]) - charges)}}


def ready(policy, snapshot, force) -> bool:
    if "ranged" not in force:
        return True
    found = score(policy, snapshot, force["ranged"])
    return found.turn >= _turn_floor(force, force) and found.shots >= int(force["ranged"]["ammo"])


def details(policy, snapshot, force) -> dict:
    found = score(policy, snapshot, force["ranged"])
    return {"turn": {"measured": found.turn, "required": _turn_floor(force, force)},
            "shots": {"measured": found.shots, "required": int(force["ranged"]["ammo"]),
                      "device": found.device_shots}}
