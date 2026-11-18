"""A quest taken only once one player turn kills its named monster: ``required_force.one_turn_kill``.

QUEST_32 (ダークエルフの王), owner 2026-11-19: 「Q32の戦略を作って。受注を急がないクエストなので
閾に棲む者を一撃で倒せる程度の強さを要求する。」, and on what 「一撃」 means: 「閾に棲む者の召喚魔法を
受ける回数を最小化するのが目的なので、1ターンで倒せれば良い」.  So the figure is one player action's
expected damage (all the blows of one melee turn, or one use of an attack device), and it must
reach the monster's largest hit points.

``one_turn_kill`` names ``race`` (263, 閾に棲む者), ``hit_points`` and ``device_classes``.

The game's side (C:/hengband/src):

* hit points: a monster without FORCE_MAXHP rolls its dice at placement
  (monster-floor/one-monster-placer.cpp: ``hit_dice.roll()``, ``maxroll()`` only with
  FORCE_MAXHP; the quest map places it the same way).  閾に棲む者 is 30d8 without FORCE_MAXHP,
  so 30..240 (135 on average); ``hit_points`` is the largest roll, 240, so the figure answers
  every roll the floor can hold.
* melee (``attack_expectation.melee_against``): both hands' blows x hit chance at the race's
  armour (AC 30) x the dice with the weapon's slay against its flags (EVIL x2, DEMON x3: the
  race is EVIL and DEMON; its IM_FIRE/IM_COLD/IM_POIS cancel those brands), plus to_d; no
  criticals (they only add).  One player turn, 100 energy, whatever the blows.
* a device (``attack_expectation.devices_against``), for the classes of ``device_classes``:
  the best absorbed attack power or carried attack wand or rod with a charge now, success
  rate x its damage after the race's immunities (fire, cold and poison leave a ninth,
  scored 0; drain life does nothing to a DEMON).  One use is one player turn.
* no launcher: the strategy carries none (its force names no ``launcher``, and the quest
  executor shoots a launcher only for a force that names one).  n1-a life-531's (warrior Lv42)
  bow reads 138 a turn against it, its melee 497.

The figure is expected damage (hit chance and success rate in it) against the largest roll:
the conservative reading of 「1ターンで倒せれば良い」.

The hasted tier, owner 2026-11-19 「加速手段が十分なら135以上で良いとする」: a figure of at least
``hasted_hit_points`` (135, the 30d8 average) is enough with ``haste_doses`` haste means carried.
Hasted (+10) the player takes two actions to the monster's one (energy 20 against 10 at speed +0),
so 2 x 135 = 270 lands before its next action, the summons it gets as at the 240 line.  The doses
are counted by the existing reader of haste supplies: ``quest_force_rows.resolve`` asks the
hasted row's ``speed_potions`` (an absorbed Speed power with that many charges at the reliable
rate stands for them, ``_speed_cost``) and sets ``speed_required_to_depart``, so they are bought,
checked at acceptance and carried in.  The fight doses before it engages the race (policy_quest,
``haste_first``).

``tier`` is "full" (the 240 line), "hasted" (the 135 line) or None.  ``met`` (a tier) is the
power condition: acceptance adds the hasted row's doses; ``quest_force_rows.resolve`` asks no
kit of a character with no tier (a character that cannot take the quest spends nothing on it).
``non_urgent`` (owner 2026-11-19 「条件を満たした時だけ割り込む」): the quest keeps its place in
the fixed-quest order, but while ``met`` is false it is passed over (``holds_back``) and the
next quest is taken.

``means`` is the attack the fight uses on the race (quest executor): the one with the larger
figure, melee on a tie.
"""

from __future__ import annotations

from hengbot import attack_expectation
from hengbot.item_reservation import decision_memo

FIELD = "one_turn_kill"


def requirement(force) -> dict | None:
    """The force's ``one_turn_kill``, or None."""
    if not isinstance(force, dict):
        return None
    value = force.get(FIELD)
    return value if isinstance(value, dict) else None


def valid(value) -> bool:
    """The schema of ``one_turn_kill`` (quest_strategies reads it at load)."""
    def integer(item) -> bool:
        return isinstance(item, int) and not isinstance(item, bool)

    return (isinstance(value, dict)
            and integer(value.get("race")) and value["race"] > 0
            and integer(value.get("hit_points")) and value["hit_points"] > 0
            and isinstance(value.get("device_classes", []), list)
            and all(integer(item) for item in value.get("device_classes", []))
            and all(integer(value[name]) and 0 < value[name]
                    for name in ("hasted_hit_points", "haste_doses") if name in value)
            and ("hasted_hit_points" in value) == ("haste_doses" in value))


def figures(policy, snapshot, force) -> dict[str, float]:
    """{"melee": ..., "device": ...}: one player turn's expected damage to the race."""
    required = requirement(force)
    if required is None:
        return {}
    race = int(required["race"])
    devices = tuple(required.get("device_classes", ()))

    def compute() -> dict[str, float]:
        found = {"melee": attack_expectation.melee_against(policy, snapshot, race)}
        found["device"] = (attack_expectation.devices_against(policy, snapshot, race)
                           if snapshot.player.class_id in devices else 0.0)
        return found

    return decision_memo(policy, "quest_one_turn_kill.figures", snapshot,
                         (race, devices), compute)


def best(policy, snapshot, force) -> float:
    return max(figures(policy, snapshot, force).values(), default=0.0)


def tier(policy, snapshot, force) -> str | None:
    """"full" (the figure reaches ``hit_points``), "hasted" (it reaches ``hasted_hit_points``:
    the haste doses are asked by ``quest_force_rows.resolve``) or None."""
    required = requirement(force)
    figure = best(policy, snapshot, force)
    if figure >= int(required["hit_points"]):
        return "full"
    if "hasted_hit_points" in required and figure >= int(required["hasted_hit_points"]):
        return "hasted"
    return None


def met(policy, snapshot, force) -> bool:
    """No requirement, or one player turn's figure reaches a tier."""
    return requirement(force) is None or tier(policy, snapshot, force) is not None


def haste_doses(force) -> int:
    return int(requirement(force)["haste_doses"])


def holds_back(policy, snapshot, quest_id: int) -> bool:
    """A ``non_urgent`` approved quest whose power condition is not met: the fixed-quest order
    passes over it (owner 2026-11-19 「条件を満たした時だけ割り込む」)."""
    force = getattr(policy.approved_quest_strategy(quest_id), "required_force", None)
    if not isinstance(force, dict) or not force.get("non_urgent"):
        return False
    return not met(policy, snapshot, force)


def haste_first(policy, snapshot, force) -> bool:
    """The hasted tier fights its race hasted: dose before engaging it while the haste is off."""
    from hengbot import haste_read
    return (requirement(force) is not None and tier(policy, snapshot, force) == "hasted"
            and not haste_read.hasted(policy, snapshot))


def means(policy, snapshot, force) -> str | None:
    """"melee" or "device": the attack the fight uses on the race; None without a requirement."""
    found = figures(policy, snapshot, force)
    if not found:
        return None
    return "device" if found["device"] > found["melee"] else "melee"


def race(force) -> int | None:
    required = requirement(force)
    return int(required["race"]) if required is not None else None


def details(policy, snapshot, force) -> dict:
    """The readiness telemetry's entry."""
    required = requirement(force)
    return {"race": int(required["race"]), "required": int(required["hit_points"]),
            **{name: round(value, 1) for name, value in figures(policy, snapshot, force).items()},
            "means": means(policy, snapshot, force), "tier": tier(policy, snapshot, force)}
