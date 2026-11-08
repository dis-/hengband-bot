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

``note``: the decision that posts the THREAT occasion's teleport-away key remembers its target
when that monster is T1 -- the engagement it stands in reads T1, or it does alone
(threat_tiers.cannot_win, the owner's 11-08 「勝てないと分かれば離脱」) -- on a floor outside any
quest (``floor_key[2] == 0``).  ``observe``: the next board of the same floor that prints the
target's 「…が消え去った！」 starts the town return (trigger ``TRIGGER``); a resisted or failed use
(no such message), a floor change or a later turn without it forgets the target.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import me_powers, threat_tiers


MEMORY = "_sent_away_t1"
TRIGGER = "teleported-away-t1"
THREAT_REASON = "me-power:unbeatable-in-range:teleport-away"
VANISHED = ("が消え去った！", " disappears!")   # effect/effect-monster.cpp:546


@dataclass(frozen=True)
class SentAway:
    floor: tuple
    turn: int
    index: int
    name: str


def _t1(policy, snapshot, monster) -> bool:
    hp = snapshot.player.hp
    engaged = threat_tiers.engagement(policy, snapshot)
    if any(other.index == monster.index for other in engaged) and threat_tiers.cannot_win(
            threat_tiers.tiered(policy, snapshot, engaged), hp):
        return True
    return threat_tiers.cannot_win(threat_tiers.tiered(policy, snapshot, [monster]), hp)


def note(policy, snapshot) -> None:
    """The THREAT occasion's key was decided: remember a T1 target of its teleport-away."""
    setattr(policy, MEMORY, None)
    memory = getattr(policy, me_powers.MEMORY, None)
    pending = None if memory is None else memory.pending
    target = None if pending is None else pending.target
    if (policy.last_reason != THREAT_REASON or target is None or snapshot.floor_key[2] != 0
            or not threat_tiers.acts_here(policy, snapshot)):
        return
    monster = next((each for each in snapshot.visible_monsters
                    if each.hostile and each.position == target), None)
    if monster is None or not _t1(policy, snapshot, monster):
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
    vanished = any(message.endswith(VANISHED) and sent.name in message
                   for message in snapshot.messages)
    if not vanished or any(each.index == sent.index for each in snapshot.visible_monsters):
        return
    policy._note_return_start(TRIGGER)
    policy._returning_to_town = True
    policy._last_return_trigger = TRIGGER
