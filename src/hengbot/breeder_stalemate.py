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

Floors with a quest plan (owner 2026-11-05 「攻撃を始めてから数える」): the bot
walks those floors in the plan's order past breeders it does not fight yet, and
what comes into view is not growth.  n1-a life-478 was abandoned at full HP on
one gremlin at the window's start and one blue icky thing at its end; life-482
on one Undead mass glimpsed at the start and eleven in view at the end.  There a
window opens on the board that shows the first attack landed on a breeder (a
visible breeder of the last board hurt, or gone with the player's experience
up: the key's own target differs per attack owner, the result does not) and
counts only that race, from its count before the attack.  A shot that misses
opens nothing yet.  The comparison and the abandonment are the same.
"""
from __future__ import annotations

from typing import NamedTuple


FLEE_AFTER_PLAYER_ACTIONS = 20


class _LastBoard(NamedTuple):
    """What the next board's attack reading compares with."""
    floor: tuple
    exp: int
    sighted: dict       # visible breeder's index -> (race, estimated HP)
    counts: dict        # race -> perceived breeders


def forget(policy) -> None:
    """A new floor visit: no breeder engagement yet."""
    policy._breeder_engagement_start_count = None
    policy._breeder_engagement_start_turn = None
    policy._breeder_engagement_actions = 0
    policy._breeder_engagement_last_turn = None
    policy._breeder_engagement_race = None


def stalemate_standing(policy) -> bool:
    """A window has run 20 actions without a reduction."""
    return (
        policy._breeder_engagement_start_count is not None
        and policy._breeder_engagement_actions >= FLEE_AFTER_PLAYER_ACTIONS
    )


def _counts_from_first_attack(policy, snapshot) -> bool:
    """This floor is the TAKEN quest's with a plan."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    return quest_id is not None and policy.approved_quest_strategy(quest_id) is not None


def _attacked_race(policy, snapshot, breeders: list) -> tuple[int, int] | None:
    """(race, its count on the last board) of a breeder the last action hit."""
    last = policy._breeder_last_board
    sighted = {monster.index: monster for monster in snapshot.visible_monsters
               if monster.hostile and monster.can_multiply}
    counts: dict[int, int] = {}
    for monster in breeders:
        counts[monster.race_id] = counts.get(monster.race_id, 0) + 1
    policy._breeder_last_board = _LastBoard(
        snapshot.floor_key, snapshot.player.exp,
        {index: (monster.race_id, monster.hp) for index, monster in sighted.items()},
        counts)
    if last is None or last.floor != snapshot.floor_key:
        return None
    for index, (race, hp) in last.sighted.items():
        now = sighted.get(index)
        hurt = now is not None and now.race_id == race and now.hp < hp
        killed = now is None and snapshot.player.exp > last.exp
        if hurt or killed:
            return race, last.counts.get(race, 1)
    return None


def _open_window(policy, snapshot, count: int, race: int | None = None) -> None:
    policy._breeder_engagement_race = race
    policy._breeder_engagement_start_count = count
    policy._breeder_engagement_start_turn = snapshot.turn
    policy._breeder_engagement_actions = 0
    policy._breeder_engagement_last_turn = snapshot.turn


def flee_due(policy, snapshot, breeders: list) -> bool:
    """Count this board's action; True once a window ended without a reduction."""
    attacked = _attacked_race(policy, snapshot, breeders)
    if policy._breeder_engagement_start_count is None:
        if _counts_from_first_attack(policy, snapshot):
            if attacked is not None:
                _open_window(policy, snapshot, attacked[1], attacked[0])
        elif breeders:
            _open_window(policy, snapshot, len(breeders))
        return False
    race = policy._breeder_engagement_race
    if race is not None:
        breeders = [monster for monster in breeders if monster.race_id == race]
    count = len(breeders)
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
        _open_window(policy, snapshot, count, race)
    else:
        forget(policy)
    return False
