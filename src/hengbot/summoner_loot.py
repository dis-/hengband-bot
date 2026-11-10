"""A summoner in the open on a T3 board: *Destruction* only when it destroys nothing of value.

Owner 2026-11-10 (the n1-b life-367 report's P6, question 「50階以降で、召喚する敵が見えただけ
（HP満タン・段T3）の時も *破壊* を使いますか？」, verbatim): 「ドロップに価値がないなら*破壊*、価値が
あるT3なら穴熊を試みて地形が悪ければやはり*破壊*する。」  The example board (Mountain 50F,
2026-11-10 20:54:42, HP 611/629): the bot's own lit room woke a summoner (ナイトウィング) and
three others, the emergency ladder took *Destruction* (policy_combat ``summoner_open``), and
three of the deleted monsters were reward races.

The scene (``applies``): the emergency ladder's ``summoner_open`` alone (not lethal, not 即死,
not the guardian reposition), HP at least FULL_HP_SHARE of the maximum (「HP満タン」, read with
the margin of the report's own example, 611/629), the engagement T3 (threat_tiers ``tier_of``),
and the *Destruction* the ladder would use usable now (destruction_use ``usable`` with the
ladder's own ``leaving``, the engagement): the choice is between that use and the pocket,
nothing else changes.

「ドロップに価値がある」 (``valuable``), from the static race data (lib/edit/MonraceDefinitions,
fair play) of every hostile, seen or detected, within destruction_use.WORST_RADIUS (what the
use may delete, spell-kind/spells-floor.cpp destroy_area: no drop, no experience):

- DROP_GOOD or DROP_GREAT (monster-floor/monster-death.cpp decide_drop_quality: the drops are
  made with AM_GOOD / AM_GREAT; monster-death-util.cpp: such a race always drops items);
- the expected drop count at least threat_tiers.MANY_DROPS (3), counted as the threat tiers'
  reward reading counts it (DROP_COUNTS, decide_drop_numbers: DROP_60/90/1D2/2D2/3D2/4D2;
  owner OQ-8);
- UNIQUE: a unique's fixed artifact drops (MonraceDefinitions ``artifacts``) are not in the
  race knowledge the bot loads, and every unique carries some drop flag; this stands for them.

Not valuable: a race that multiplies (as threat_tiers.reward_reasons), a pet, a monster with
none of the above.  Experience is no drop (the owner's word is ドロップ), unlike the tiers'
reward reading.

The pocket is anaguma's (``anaguma.key``, its own pack and terrain rules unchanged): when it
answers, its key; when it does not (no pack it plans for, no rock, no charge, a wall passer:
「地形が悪ければ」), the ladder's *Destruction* as before.
"""

from __future__ import annotations

from hengbot import anaguma, destruction_use, threat_tiers
from hengbot.model import game_distance

FULL_HP_SHARE = 0.9


def valuable(policy, monster) -> bool:
    """The race's drops are worth keeping (the module docstring)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is None or monster.pet or monster.can_multiply or "MULTIPLY" in knowledge.flags:
        return False
    flags = knowledge.flags
    if "DROP_GOOD" in flags or "DROP_GREAT" in flags or "UNIQUE" in flags:
        return True
    return sum(threat_tiers.DROP_COUNTS.get(flag, 0.0) for flag in flags) >= threat_tiers.MANY_DROPS


def deleted(snapshot) -> list:
    """The hostiles, seen or detected, a use here may delete (destruction_use.WORST_RADIUS)."""
    here = snapshot.player.position
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile and game_distance(here, monster.position) <= destruction_use.WORST_RADIUS]


def applies(policy, snapshot, hostiles) -> bool:
    player = snapshot.player
    return (player.hp >= FULL_HP_SHARE * player.max_hp
            and threat_tiers.tier_of(policy, snapshot, hostiles) == threat_tiers.T3
            and destruction_use.usable(policy, snapshot, leaving=threat_tiers.engagement(policy, snapshot)))


def pocket_key(policy, snapshot, hostiles) -> str | None:
    """The pocket in place of the summoner's *Destruction*, else None (the ladder as before)."""
    if not applies(policy, snapshot, hostiles):
        return None
    if not any(valuable(policy, monster) for monster in deleted(snapshot)):
        return None
    return anaguma.key(policy, snapshot, hostiles)
