"""Keep out of the line of fire of a never-moving breeder that blinds and confuses.

Owner 2026-11-22, the question 「耐閃光（耐盲目）も耐混乱も無い時、盲目と混乱を起こす増える敵
（百目口：動かない・増える・閃光のブレスと混乱の呪文）が射線にいたらどうしますか？」 answered
「撃たずに射線の外へ離れる」 (撃たずに射線の外へ歩いて離れ、その階ではもう近寄りません。動かない敵
なので歩くだけで離れられます。).  It overrides, for this case only, the 11-08 rule that a breeder
in the line of fire is shot.

n1-a life-533 (2026-11-22 15:14:41, オークの洞窟19階, Warrior Lv22, neither resistance): the first
百目口 (race 253: NEVER_MOVE, MULTIPLY, BR_LITE, CONF, SCARE) was seen five cells away and shot
(``ranged:fire-target``, #16767); its breaths and spells, and its children's, kept the player
blind and confused until the cures ran out and it died there at 15:15.

The race is read from its abilities, not its id (MonraceDefinitions.jsonc): it multiplies, never
moves, blinds from range (BR_LITE: effect_player_lite blinds without resist_lite and
resist_blind; BR_DARK: effect_player_dark without resist_dark and resist_blind; the BLIND spell
without resist_blind) and confuses from range (CONF, BR_CONF without resist_conf).  Today that is
the 百目口 and the カオス・タイル (458).  The ベトベト (252, BLIND and CONF) moves: walking out of its
line does not keep it away (the owner's 「動かない敵なので」), and it stays as today (Q2's own rules).

The avoidance is the never-moving summoner's (policy_combat ``_immobile_summoner_key``, owner
2026-10-27 「近づかずに避ける」): the monster is remembered for the floor visit, the cells in its
line of fire leave every walk, a player inside them steps out (``STEP_OUT_REASON``) ahead of every
shooting rung, and the floor is left once nothing outside is left to explore.  Not on a floor
whose exit is locked (no retreat exists: the fight is as today), nor the hunted quest target.
"""

from __future__ import annotations

from hengbot import ability_sources, hunt_target

# The abilities that blind from range, each with the resistance that also stops it
# (effect-player-resist-hurt.cpp effect_player_lite / effect_player_dark; mspell BLIND), and
# the ones that confuse from range (mspell CONF; effect_player_confusion).
BLINDING = {"BR_LITE": "resist_lite", "BR_DARK": "resist_dark", "BLIND": None}
CONFUSING = frozenset({"CONF", "BR_CONF"})
STEP_OUT_REASON = "status-breeder:step-out"


def race_kept_away(policy, snapshot, race_id: int) -> bool:
    """The race multiplies, never moves, and blinds and confuses this unresisting player."""
    knowledge = policy._monrace_knowledge.get(race_id)
    if (knowledge is None or not knowledge.can_multiply or "NEVER_MOVE" not in knowledge.flags
            or not knowledge.abilities & CONFUSING):
        return False
    player = snapshot.player
    if (ability_sources.has_ability(player, "resist_blind")
            or ability_sources.has_ability(player, "resist_conf")):
        return False
    return any(ability in knowledge.abilities
               and (resist is None or not ability_sources.has_ability(player, resist))
               for ability, resist in BLINDING.items())


def kept_away(policy, snapshot, monster) -> bool:
    """``race_kept_away``, on a dungeon floor that can be left, not the hunted target."""
    return (race_kept_away(policy, snapshot, monster.race_id)
            and not snapshot.in_town and snapshot.dungeon_level > 0
            and not policy._floor_navigation_exit_locked(snapshot)
            and monster.race_id != hunt_target.target_race(policy, snapshot))
