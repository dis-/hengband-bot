"""How many Potions of Restore Mana a Magic-Eater collects (owner 2026-11-20).

Owner, verbatim: 「詳細は別途指示するが、99Fと100Fでは強力発動ロケットをダメージソースとして戦う。
魔力復活1服あたり回復するロケットの量から与えられるダメージ量を出し、99Fと100Fのターゲットの
HP総量の1.5倍を目標値として魔力復活の薬を集める必要がある。」 and 「専用の装備を組ませるので、
ロケットの成功率は90%で試算して良い」.

    target = ceil(TARGET_HP_SHARE x total HP of the 99F and 100F targets
                  / (uses restored per potion x ROCKET_SUCCESS x powerful rocket damage))

* The targets: the fixed quests of Angband 99F and 100F (lib/edit/quests/008_Oberon.jsonc,
  KILL_LEVEL 99, monster 860 アンバーの王『オベロン』; 009_SerpentOfChaos.jsonc, level 100,
  monster 862 『混沌のサーペント』).  Both are FORCE_MAXHP, so their HP is the dice maximum
  (MonraceDefinitions: 99d111 and 200d150), read from the race knowledge (``max_hp``).
* The rocket: the Wand of Rockets (sv-wand-types.h SV_WAND_ROCKETS 29; cmd-zapwand.cpp
  fire_rocket ROCKET, 250 + lev * 3) through Powerful Activation (the level doubled:
  me_device_attacks ``powered``), after each target's resistance (effect-monster-resist-hurt.cpp
  effect_monster_rocket: RESIST_SHARDS halves; me_device_attacks ``expected_damage``).
* Uses restored per potion: spells-status.cpp restore_mana(magic_eater=true): a wand power gains
  3 uses below 10 absorbed, else count / 3 uses, never past the count.  The CURRENT rocket count
  (me_capability.count), so the target shrinks as more rockets are absorbed.

Record and purchase only: no battle rule reads it (the owner instructs the 99F/100F tactics
separately).
"""
from __future__ import annotations

import math
from typing import Any

from hengbot import me_capability
from hengbot.model import SV_POTION_RESTORE_MANA, TVAL_POTION

# Owner 2026-11-20 「専用の装備を組ませるので、ロケットの成功率は90%で試算して良い」.
ROCKET_SUCCESS = 0.9
# Owner 2026-11-20 「99Fと100FのターゲットのHP総量の1.5倍を目標値として」.
TARGET_HP_SHARE = 1.5
# lib/edit/quests 008_Oberon (99F) and 009_SerpentOfChaos (100F).
TARGET_RACES = (860, 862)
ROCKET = ("wand", 29)
# spells-status.cpp restore_mana: below this count a wand power gains a fixed 3 uses.
FIXED_REFILL_BELOW = 10
FIXED_REFILL_USES = 3


def uses_per_potion(count: int) -> float:
    """The rocket uses one potion restores to an empty power of ``count`` absorbed."""
    if count <= 0:
        return 0.0
    restored = FIXED_REFILL_USES if count < FIXED_REFILL_BELOW else count / 3
    return min(float(count), float(restored))


def rocket_damage(policy: Any, snapshot: Any, race_id: int) -> float:
    """One successful Powerful Activation rocket against the race, after its resistance."""
    from hengbot.me_device_attacks import POWERS, expected_damage, powered
    race = policy._monrace_knowledge.get(race_id)
    flags = race.flags if race is not None else frozenset()
    return expected_damage(powered(POWERS[ROCKET]), snapshot.player.level, flags)


def plan(policy: Any, snapshot: Any) -> dict | None:
    """The collection target and its figures for a Magic-Eater, else None."""
    if snapshot.player.class_id != me_capability.PLAYER_CLASS_MAGIC_EATER:
        return None
    count = me_capability.count(policy, snapshot, *ROCKET)
    hp = {race_id: getattr(policy._monrace_knowledge.get(race_id), "max_hp", 0)
          for race_id in TARGET_RACES}
    needed = TARGET_HP_SHARE * sum(hp.values())
    uses = uses_per_potion(count)
    # The weaker of the two targets' damage per rocket decides (both take full ROCKET today).
    damage = min(rocket_damage(policy, snapshot, race_id) for race_id in TARGET_RACES)
    per_potion = uses * ROCKET_SUCCESS * damage
    target = math.ceil(needed / per_potion) if per_potion > 0 else None
    return {"rockets": count, "target_hp": hp, "needed_damage": needed,
            "rocket_damage": damage, "uses_per_potion": uses,
            "damage_per_potion": per_potion, "target": target,
            "held": held(policy, snapshot)}


def held(policy: Any, snapshot: Any) -> int:
    """The Potions of Restore Mana carried and on the last Home census."""
    def mana(item):
        return item.tval == TVAL_POTION and item.sval == SV_POTION_RESTORE_MANA
    return (sum(item.count for item in snapshot.inventory if mana(item))
            + sum(item.count for item in policy._home_knowledge_items if mana(item)))


def wanted(policy: Any, snapshot: Any) -> bool:
    """A Magic-Eater still short of its target (an unknown target: absorb a rocket first,
    then the target is known; until then the potions are still collected)."""
    figures = plan(policy, snapshot)
    if figures is None:
        return False
    return figures["target"] is None or figures["held"] < figures["target"]
