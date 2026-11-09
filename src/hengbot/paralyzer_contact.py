"""D55: a paralyzer is in contact when its blow can land before our next action.

Recorded n1-a life-450 (Labyrinth 16F, 2026-10-31 14:47): the Lv24 warrior
without Free Action waited on Word of Recall carrying 12 Teleportation
scrolls.  An アイス・コボルド stepped beside it and a ランゴスタ (race 1252,
speed +10, STING/CRUSH PARALYZE) stood two cells away.  The paralyzer rung
(``_paralyzer_prevention_key``, which reads an escape scroll before a
paralyzer's blow lands) looked at adjacency only and saw none; the
status-threat rung below it then kept the fight already in contact.  The bot
meleed the kobold; the locust, with two actions per player action, closed and
stung, and the player died paralyzed at HP 213/419 (playrecord
「麻痺状態でランゴスタに殺された」).

Only the paralyzer rung reads contact.  When it has neither a scroll nor a
retreat step, the status-threat rung's "finish the fight already in contact"
still melees the adjacent enemy, which beats a status-threat wait.

Contact is the game's energy arithmetic, not a new margin: each game tick
the player and every monster lose ``speed_to_energy(speed)`` of their energy
need (core/player-processor.cpp:133, monster/monster-processor.cpp:677) and
every action costs ``ENERGY_NEED()`` = randnor(100, 25)
(core/speed-table.h:6), so between two player actions a monster takes on
average ``monster_energy // player_energy`` actions; one ``path`` steps away
needs ``path - 1`` moves and one blow.
"""

from __future__ import annotations

from hengbot.policy_constants import MONSTER_SPELL_MAX_RANGE


# Owner 2026-11-09 (question E of n1-b life-346, 鉄獄19階: クトーニアン, 1_IN_5 HOLD and
# BRAIN_SMASH, killed the player paralysed): 「麻痺知らずが無い時、HOLD・脳攻撃を持つ敵も麻痺
# させる敵に数え、視線が通れば 09-18 の決まりで離れる。」  Game: spell_RF5_HOLD paralyses
# unless free action or the saving throw (mspell/mspell-status.cpp:423-445, mod_paralysis
# 4-7); effect_player_brain_smash paralyses past the saving throw unless free action
# (effect/effect-player-spirit.cpp:103-136).  A monster casts only within the maximum range
# (mspell/mspell-attack.cpp:320, MAX_RANGE) and a projectable line (:326
# decide_lite_projection, mspell/mspell-lite.cpp:209-212); arena_odds._NEEDS reads the same
# two spells.
SPELL_PARALYSIS = frozenset({"HOLD", "BRAIN_SMASH"})


def paralyses_by_spell(knowledge) -> bool:
    """A race that casts one of the paralysing spells."""
    return (knowledge is not None and knowledge.spell_frequency > 0
            and bool(knowledge.abilities & SPELL_PARALYSIS))


def spell_contact(policy, snapshot, monster) -> bool:
    """Whether an awake spell paralyser has the player in sight: in range and a clear line
    (the 09-18 leave's contact for a paralyser that needs no blow)."""
    if monster.asleep or not paralyses_by_spell(policy._monrace_knowledge.get(monster.race_id)):
        return False
    return (monster.distance <= MONSTER_SPELL_MAX_RANGE
            and policy._has_line_of_fire(snapshot, monster.position, snapshot.player.position))


def in_contact(policy, snapshot, monster) -> bool:
    """Whether ``monster``'s melee can reach the player before its next action."""
    if monster.distance <= 1:
        return True
    if monster.asleep:
        return False
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is not None and "NEVER_MOVE" in knowledge.flags:
        return False
    path = policy._monster_path_distance(snapshot, monster.position)
    if path is None:
        return False
    actions = policy._speed_energy(monster.speed) // policy._speed_energy(
        snapshot.player.speed
    )
    return actions >= path


def follows_walk(policy, snapshot, monster) -> bool:
    """Whether a walking retreat cannot leave ``monster`` behind: awake, it
    moves and gains at least one action per player step.

    n1-a life-470 (イークの洞穴13階, 2026-11-03 09:50): without Free Action
    the Lv15 warrior walked away (``status-threat:retreat``) from an awake
    ゲイザー (race 218, speed +0, GAZE:PARALYZE, HOLD) two cells away carrying
    14 Teleportation scrolls; the gazer kept pace, the player was paralyzed
    and the yeeks around it killed it from HP 234/310.  Owner 2026-11-03
    「階段が隣などとても近くにある場合を除き徒歩での逃走は絶対に間に合わ
    ない。」  A stationary monster (Floating Eye) or a slower one is still
    walked away from."""
    if monster.asleep:
        return False
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is not None and "NEVER_MOVE" in knowledge.flags:
        return False
    return policy._speed_energy(monster.speed) >= policy._speed_energy(
        snapshot.player.speed
    )
