"""Required resistances another means stands in for, for every class and quest (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「魔道具術師でテレパシーがあるなら盲目でも戦闘に支障はない。また、恐怖
攻撃はヒーローの薬で対処する決まりが既にある。」 (n1-c life-217, Magic-Eater Lv44 with telepathy and
neither resistance, was refused QUEST_33 for ``blindness`` and ``fear`` and QUEST_32 for ``fear``.)

* Blindness: a Magic-Eater (class 16) with telepathy fights blind.  Its attacks are absorbed
  powers, which the game refuses only while confused (cmd-item/cmd-magiceat.cpp:463
  ``cmd_limit_confused``; no blindness check), and telepathy marks the monsters seen while blind
  (monster/monster-update.cpp ``decide_sight_invisible_monster``: ``update_telepathy_sight`` runs
  before the blindness return).  Any other class still needs the resistance: a blind character
  reads no scroll, and a melee or launcher class gains nothing from this rule.
* Fear: the heroism rule (heroism_potion, owner 2026-11-11 「恐怖耐性が無い時はヒーローの薬を15服
  持ち…」) answers it.  Without a lasting fear resistance the requirement is that rule's carry
  (``heroism_potion.carry_target`` potions carried, ``heroism_potion.carried``), a shortage of
  which is a carry the town buys (the ``tail:heroism`` rung and the Temple errand), never a
  missing resistance.

This is one rule in code, not a ``resist_alternatives`` row in every QUEST_*.jsonc: it depends on
the character (class, telepathy, the carried potions), which the per-quest rows (an ability for an
ability, QUEST_25's See Invisible) cannot say, and it holds for every quest that names either
resistance.  The depth table (DEPTH_ABILITY_REQUIREMENTS) names neither.
"""

from __future__ import annotations

from hengbot import heroism_potion
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.quest_strategies import has_ability_or_alternative

BLIND = "resist_blind"
FEAR = "resist_fear"
HEROISM_CARRY = "heroism_potions"


def blind_covered_by_telepathy(snapshot) -> bool:
    """A Magic-Eater with telepathy: blindness does not stop its fight."""
    player = snapshot.player
    return player.class_id == PLAYER_CLASS_MAGIC_EATER and "telepathy" in player.abilities


def fear_by_heroism(snapshot) -> bool:
    """No lasting fear resistance: the heroism rule's carry answers fear."""
    return not heroism_potion.lasting_fear_resistance(snapshot)


def resist_met(force: dict, name: str, snapshot) -> bool:
    """The required ability ``name`` (resolved) is had, or a means stands in for it.

    Fear is always met here: by a lasting resistance, else by the heroism carry, which
    ``carry_status`` asks as a carry."""
    if name == FEAR:
        return True
    if has_ability_or_alternative(force, name, snapshot.player.abilities, snapshot.equipment):
        return True
    return name == BLIND and blind_covered_by_telepathy(snapshot)


def carry_status(force: dict, resolve, snapshot) -> dict:
    """The heroism carry standing in for a required fear resistance ({} when none is asked).

    ``resolve`` maps a profile's resistance name to the ability name."""
    if not any(resolve(str(name)) == FEAR for name in force.get("resists", ())):
        return {}
    if not fear_by_heroism(snapshot):
        return {}
    carried, required = heroism_potion.carried(snapshot), heroism_potion.carry_target(snapshot)
    return {HEROISM_CARRY: {"measured": carried, "required": required, "ready": carried >= required}}
