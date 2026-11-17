"""A T1 monster sent away by Teleport Away leaves the floor dangerous: return to town.

Owner 2026-11-09 (question E of the n1-b deaths, life-346), verbatim: 「テレポート・アウェイで
飛ばした T1 の敵がいる階は、クエストの外なら帰還する。」  n1-b life-346 (鉄獄19階, 2026-11-08
12:06): the absorbed Teleport Away (me_powers THREAT, ``unbeatable-in-range``, owner 2026-11-01
「勝てない敵が射程内にいればいつでも使って良い」) sent a クトーニアン (KILL_WALL, HOLD,
BRAIN_SMASH) away while the engagement read T1; the floor went on and the player died paralysed.

Game (C:/hengband/src): the rod and the wand fire a beam of AWAY_ALL (me_powers, the
teleport-away row); a monster it moves prints 「<name>が消え去った！」
(effect/effect-monster.cpp:546 effect_damage_makes_teleport), one that resists prints
「には耐性がある！」 or 「には効果がなかった。」 (effect/effect-monster-evil.cpp:7-30) and stays.
The monster lives on the same floor (teleport_away), so it can come back.

Owner 2026-11-16 (n1-c life-216 recalled about 75 times in 16:41-19:21 on 城64階 and around),
on 「T1 の敵」 of that rule: 「飛ばした敵が単独で T1 の時だけ」.  The monster sent away is read on its
own -- ``threat_tiers.assess`` of it alone, the raw reading, without the decided side the
engagement holds (``held_tier``, 「境に余裕を持たせる」) -- and only that reading counts: standing in
an engagement that reads T1 (17:02:02 土の鬼 beside a グレーター・バルログ), or being held at T1 after
the engagement's T1 has gone (18:47:44 見習レンジャー, 19:09:14 ダークエルフ・ワーロック), no longer does.
``_t1`` is the one reader, for the THREAT occasion's Teleport Away and for teleport_follower's.

``note``: the decision that posts the THREAT occasion's teleport-away key remembers its target
when that monster is T1 on its own (threat_tiers.cannot_win, the owner's 11-08 「勝てないと分かれば
離脱」) on a floor outside any quest (``floor_key[2] == 0``).  ``observe``: the next board of the
same floor that prints the target's own 「<name>が消え去った！」 (" disappears!", the game's
``str_upcase_first`` of ``monster_desc``: "The <name> disappears!") starts the town return (trigger
``TRIGGER``); the line names exactly the target, so 「白狼が消え去った！」 is not a 狼's.  A resisted
or failed use (no such message), a floor change or a later turn without it forgets the target.
Recalls by this rule are not counted as over-extension (owner 2026-11-16).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hengbot import me_powers, threat_tiers


MEMORY = "_sent_away_t1"
TRIGGER = "teleported-away-t1"
THREAT_REASON = "me-power:unbeatable-in-range:teleport-away"
VANISHED = ("が消え去った！", " disappears!")   # effect/effect-monster.cpp:546
_REPEAT_RE = re.compile(r" <x[1-9]\d*>$")
_ARTICLE_RE = re.compile(r"^the ", re.IGNORECASE)


@dataclass(frozen=True)
class SentAway:
    floor: tuple
    turn: int
    index: int
    name: str


def _t1(policy, snapshot, monster) -> bool:
    """``monster`` reads T1 on its own (owner 2026-11-16 「飛ばした敵が単独で T1 の時だけ」): the raw
    reading of it alone, never the engagement's nor a held side."""
    return threat_tiers.alone_t1(policy, snapshot, monster, raw=True)


def vanished(message: str, name: str) -> bool:
    """``message`` is the game's line for ``name`` sent away (effect-monster.cpp:546, printed as
    ``str_upcase_first(m_name) + note``), the ``<xN>`` repeat counter aside."""
    text = _REPEAT_RE.sub("", message)
    if text == name + VANISHED[0]:
        return True
    if not text.endswith(VANISHED[1]):
        return False
    said = _ARTICLE_RE.sub("", text[:-len(VANISHED[1])]).casefold()
    return said == _ARTICLE_RE.sub("", name).casefold()


def note(policy, snapshot) -> None:
    """The THREAT occasion's key was decided: remember a T1 target of its teleport-away."""
    setattr(policy, MEMORY, None)
    memory = getattr(policy, me_powers.MEMORY, None)
    pending = None if memory is None else memory.pending
    target = None if pending is None else pending.target
    if policy.last_reason != THREAT_REASON or target is None:
        return
    monster = next((each for each in snapshot.visible_monsters
                    if each.hostile and each.position == target), None)
    if monster is not None:
        remember(policy, snapshot, monster)


def remember(policy, snapshot, monster) -> None:
    """A Teleport Away was aimed at ``monster``: remember it when it is T1 on its own, outside any
    quest.

    Also the emergency ladder's Teleport Other at a monster that follows the player's teleport
    (teleport_follower, owner 2026-11-09 「*破壊*>テレポートアウェイ>戦闘」)."""
    setattr(policy, MEMORY, None)
    if (snapshot.floor_key[2] != 0 or not threat_tiers.acts_here(policy, snapshot)
            or not _t1(policy, snapshot, monster)):
        return
    setattr(policy, MEMORY, SentAway(snapshot.floor_key, snapshot.turn, monster.index, monster.name))


def observe(policy, snapshot) -> None:
    """Every decision: the board after the use settles it."""
    sent = getattr(policy, MEMORY, None)
    if sent is None or snapshot.turn <= sent.turn:
        return
    setattr(policy, MEMORY, None)
    if snapshot.floor_key != sent.floor or snapshot.in_town:
        return
    gone = any(vanished(message, sent.name) for message in snapshot.messages)
    if not gone or any(each.index == sent.index for each in snapshot.visible_monsters):
        return
    policy._note_return_start(TRIGGER)
    policy._returning_to_town = True
    policy._last_return_trigger = TRIGGER


def forget_destroyed(policy, keys) -> None:
    """The monsters a *Destruction* deleted (``keys``: (index, race)) leave this memory
    (owner 2026-11-15, maintainability review Q6 「全部から消す」; monster_memory
    ``DESTRUCTION_FORGETS``)."""
    sent = getattr(policy, MEMORY, None)
    if sent is not None and sent.index in {index for index, _race in keys}:
        setattr(policy, MEMORY, None)
