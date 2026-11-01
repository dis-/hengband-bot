"""When a breeder fight on a floor turns into flight (owner rule 2026-11-02).

Owner, verbatim: 「攻撃用の物資は制限しない。ただし、20ターンで数が減らせないなら
逃走を選択する。」  Attack supplies are not capped against breeders; once the
bot engages the breeders of a floor, a fight that does not bring the
perceived breeder count below the count at engagement within 20 turns is
abandoned: the floor is latched as a breeder breakthrough
(``_breeder_breakthrough_floor``), whose owners leave it by Recall or the up
stairs.  A floor the bot cannot leave (a locked quest floor) keeps fighting
the breeders that attack it (``survival_preemption.strikes_from_adjacent``).

A "turn" is one player action: a decision board whose game turn advanced
since the previous counted board (dungeon-processor.cpp advances
``game_turn`` once per game tick; the player acts when its energy, gained
by ``speed_to_energy`` each tick, reaches the need, so the game turns per
action differ with speed while the boards between actions do not).  Every
board that shows fewer breeders than at engagement opens a new window.

This replaces the earlier flight triggers (five kills with more breeders
than at engagement; 3,000 game turns without a reduction).
"""
from __future__ import annotations


FLEE_AFTER_PLAYER_ACTIONS = 20


def forget(policy) -> None:
    """A new floor visit: no breeder engagement yet."""
    policy._breeder_engagement_start_count = None
    policy._breeder_engagement_start_turn = None
    policy._breeder_engagement_actions = 0
    policy._breeder_engagement_last_turn = None


def flee_due(policy, snapshot, breeders: list) -> bool:
    """Count this board's action; True once 20 actions brought no reduction."""
    count = len(breeders)
    if policy._breeder_engagement_start_count is None:
        if not breeders:
            return False
        policy._breeder_engagement_start_count = count
        policy._breeder_engagement_start_turn = snapshot.turn
        policy._breeder_engagement_actions = 0
        policy._breeder_engagement_last_turn = snapshot.turn
        return False
    last_turn = policy._breeder_engagement_last_turn
    if count < policy._breeder_engagement_start_count:
        policy._breeder_engagement_start_turn = snapshot.turn
        policy._breeder_engagement_actions = 0
    elif last_turn is not None and snapshot.turn > last_turn:
        policy._breeder_engagement_actions += 1
    policy._breeder_engagement_last_turn = snapshot.turn
    return policy._breeder_engagement_actions >= FLEE_AFTER_PLAYER_ACTIONS
