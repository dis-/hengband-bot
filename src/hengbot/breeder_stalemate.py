"""When a breeder fight on a floor turns into flight (owner rule 2026-11-02).

Owner, verbatim: 「攻撃用の物資は制限しない。ただし、20ターンで数が減らせないなら
逃走を選択する。」  Attack supplies are not capped against breeders; once the
bot engages the breeders of a floor, the fight runs in windows of 20 player
actions.  Owner 2026-11-03: 「20回の区切りの初めの数と終わりの数を比べ、減っていれば
次の区切りへ進み、減っていなければ逃げます（Q2 などは放棄）。1体倒しても増えて元に戻る
なら逃げます。」  A completed window with fewer perceived breeders than at its start
opens the next window at the current count; any other completed window is
abandoned: the floor is latched as a breeder breakthrough
(``_breeder_breakthrough_floor``), whose owners leave it by Recall or the up
stairs.  A floor the bot cannot leave (a locked quest floor) keeps fighting
the breeders that attack it (``survival_preemption.strikes_from_adjacent``).

A "turn" is one player action: a decision board whose game turn advanced
since the previous counted board (dungeon-processor.cpp advances
``game_turn`` once per game tick; the player acts when its energy, gained
by ``speed_to_energy`` each tick, reaches the need, so the game turns per
action differ with speed while the boards between actions do not).  Only the
counts at the two ends of a window matter: boards in between neither reset
nor extend it, including boards that show no breeder at all.  A window that
ends with no breeder perceived ends the engagement instead of opening a window
at zero, which could never show a reduction; the next breeder seen opens a new
one.  An abandoned window's verdict stands until ``forget``.

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


def stalemate_standing(policy) -> bool:
    """A window has run 20 actions without a reduction."""
    return (
        policy._breeder_engagement_start_count is not None
        and policy._breeder_engagement_actions >= FLEE_AFTER_PLAYER_ACTIONS
    )


def _open_window(policy, snapshot, count: int) -> None:
    policy._breeder_engagement_start_count = count
    policy._breeder_engagement_start_turn = snapshot.turn
    policy._breeder_engagement_actions = 0
    policy._breeder_engagement_last_turn = snapshot.turn


def flee_due(policy, snapshot, breeders: list) -> bool:
    """Count this board's action; True once a window ended without a reduction."""
    count = len(breeders)
    if policy._breeder_engagement_start_count is None:
        if breeders:
            _open_window(policy, snapshot, count)
        return False
    if stalemate_standing(policy):
        return True
    last_turn = policy._breeder_engagement_last_turn
    if last_turn is not None and snapshot.turn > last_turn:
        policy._breeder_engagement_actions += 1
    policy._breeder_engagement_last_turn = snapshot.turn
    if policy._breeder_engagement_actions < FLEE_AFTER_PLAYER_ACTIONS:
        return False
    if count >= policy._breeder_engagement_start_count:
        return True
    if breeders:
        _open_window(policy, snapshot, count)
    else:
        forget(policy)
    return False
