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

Per 10 game turns (owner 2026-11-19 「攻撃力の判定を1行動あたりではなく、10ゲームターンあたりの
ダメージで評価して」, scope 「攻撃力の判定すべて」): 「1ターン」 is one turn at normal speed, 10 game
turns, and the figure is the per-action one times the actions the character takes in them
(attack_expectation.per_10_game_turns: speed_energy / 10).  It must reach ``hit_points / turns``
at the speed the character will fight at:

* "full": at the permanent speed (attack_expectation.permanent_speed: a timed haste in town
  ends before the quest), so no haste is asked;
* "hasted": only at the hasted speed, where the force assures a haste -- ``haste_doses`` (Q32:
  the permanent speed + 10, ``quest_force_rows.resolve`` asks the doses, an absorbed Speed power
  with that many charges at the reliable rate stands for them, and ``speed_required_to_depart``
  carries them in; the fight doses before it engages the race, ``haste_first``) or an
  ``always_hasted`` force (Q33: attack_expectation.always_hasted_speed, its own Speed supplies
  already asked by the force);
* None otherwise.

The per-10-game-turn reading counts the haste itself, so the earlier hasted line
(``hasted_hit_points`` 135 with two doses: 「加速手段が十分なら135以上で良いとする」, 2 x 135 = 270
before the monster's next action at +10 against its +0) is the same 240 line read hasted: at a
+0 permanent speed one action of 120 is 240 per 10 game turns hasted.  The field is gone from
the schema.  Recorded 2026-11-19 (permanent speed): n1-a life-531 +4 (energy 14) melee 496.9 ->
695.6, n1-b life-411 +25 (35) 504.6 -> 1766.2, n1-c life-217 +6 (16) 231.8 -> 370.8: all three
"full" (n1-c was "hasted" per action, with two doses asked).

``tier`` is "full", "hasted" or None.  ``met`` (a tier) is the
power condition: acceptance adds the hasted row's doses; ``quest_force_rows.resolve`` asks no
kit of a character with no tier (a character that cannot take the quest spends nothing on it).
``non_urgent`` (owner 2026-11-19 「条件を満たした時だけ割り込む」): the quest keeps its place in
the fixed-quest order, but while ``met`` is false it is passed over (``holds_back``) and the
next quest is taken.

``turns`` (QUEST_33, owner 2026-11-19 「戦力は過剰に要求して良い」): the race's ``hit_points`` within
that many turns, so the figure per 10 game turns must reach ``hit_points / turns``.  1 when absent.
Q33 (クイーン・アント 1500 HP in 2 turns, ``always_hasted``): 750 per 10 game turns at the
always-hasted speed; recorded n1-a (+4) 578.3 x 1.4 = 809.7 already at its permanent speed
("full"; 1388.0 hasted), n1-b (+25, no dose at +10 or more) 415.0 x 3.5 = 1452.4 ("full"), n1-c
(+6, hasted +16) 180.6 x 2.6 = 469.5 does not (288.9 unhasted).  Its haste is the
force's own (``always_hasted`` with ten Speed doses), so no ``haste_doses``.

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
                    for name in ("haste_doses", "turns") if name in value)
            # The per-action hasted line is read per 10 game turns now (the module's docstring).
            and "hasted_hit_points" not in value)


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
    """The larger figure per player action."""
    return max(figures(policy, snapshot, force).values(), default=0.0)


def speeds(snapshot, force) -> dict[str, int | None]:
    """{"permanent": ..., "hasted": ...}: the speeds the tiers read; "hasted" is None when the
    force assures no haste."""
    required = requirement(force)
    hasted = None
    if force.get("always_hasted"):
        hasted = attack_expectation.always_hasted_speed(snapshot)
    elif required is not None and "haste_doses" in required:
        hasted = attack_expectation.hasted_speed(snapshot)
    return {"permanent": attack_expectation.permanent_speed(snapshot), "hasted": hasted}


def per_10_game_turns(policy, snapshot, force) -> dict[str, float | None]:
    """``best`` per 10 game turns at each of ``speeds``."""
    figure = best(policy, snapshot, force)
    return {name: (None if speed is None else
                   attack_expectation.per_10_game_turns(policy, snapshot, figure, speed=speed))
            for name, speed in speeds(snapshot, force).items()}


def needed(force) -> float:
    """The damage per 10 game turns asked: ``hit_points`` over ``turns``."""
    required = requirement(force)
    return int(required["hit_points"]) / int(required.get("turns", 1))


def tier(policy, snapshot, force) -> str | None:
    """"full" (the figure per 10 game turns reaches ``needed`` at the permanent speed), "hasted"
    (only at the speed the force's haste assures: the doses are asked by
    ``quest_force_rows.resolve``) or None."""
    found, line = per_10_game_turns(policy, snapshot, force), needed(force)
    if found["permanent"] >= line:
        return "full"
    if found["hasted"] is not None and found["hasted"] >= line:
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
    """The readiness telemetry's entry: the per-action figures, and the best of them per 10 game
    turns at the tiers' speeds against ``required`` (hit points over turns)."""
    required = requirement(force)
    timed = per_10_game_turns(policy, snapshot, force)
    return {"race": int(required["race"]), "hit_points": int(required["hit_points"]),
            "turns": int(required.get("turns", 1)), "required": round(needed(force), 1),
            **{name: round(value, 1) for name, value in figures(policy, snapshot, force).items()},
            "per_10_game_turns": {name: (None if value is None else round(value, 1))
                                  for name, value in timed.items()},
            "speed": speeds(snapshot, force),
            "means": means(policy, snapshot, force), "tier": tier(policy, snapshot, force)}
