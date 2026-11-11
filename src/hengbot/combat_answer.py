"""The answer beside a hostile, in one order.

Every rung that may hit an adjacent hostile asks ``adjacent_attack``; a rung
holding a target of its own asks ``strike_key``.  ``_MELEE_OPEN`` is the order
of answers while the game allows a blow: a new answer before melee is one row
there.  While the game refuses the blow, a carried Potion of Heroism answers a
refusing fear first (heroism_potion.afraid_key, owner 2026-11-11); else
``me_ranged_first.melee_refused_key`` owns the answer (fear and a NO_MELEE
dungeon refuse melee only), as it does
beside hostiles no worn weapon can hurt (attack_expectation.blows_cannot_hurt).

A rung declares only what differs: the reason of its blow, how the blow is sent
(a town producer entry or a walking step instead of ``direct_blow``) and what an
engagement completes.  The rung's own survival order stays in the rung: what it
asks before this answer is its ladder, not part of the answer.

``unseen_attacker_key`` is the same idea for the attacker the player cannot see.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from hengbot import attack_expectation, blind_strike, heroism_potion, me_ranged_first


class Answer(NamedTuple):
    """The rung's answer.  ``key`` None is still an answer: a town hold refused
    the blow, and the rung returns that None instead of going on down its ladder."""

    key: str | None


class _Strike(NamedTuple):
    policy: object
    snapshot: object
    target: object
    reason: str
    blow: Callable | None


def direct_blow(policy, snapshot, target) -> str:
    """The melee blow at an adjacent ``target``; the caller holds the gates."""
    return policy._direction_key(snapshot.player.position, target.position)


def _ranged_first(strike: _Strike) -> Answer | None:
    key = me_ranged_first.attack_key(strike.policy, strike.snapshot, strike.target)
    return None if key is None else Answer(key)


def _melee(strike: _Strike) -> Answer:
    strike.policy.last_reason = strike.reason
    if strike.blow is not None:
        return Answer(strike.blow(strike.target))
    return Answer(direct_blow(strike.policy, strike.snapshot, strike.target))


# The answers in their order while the game allows a blow; melee always answers.
_MELEE_OPEN = (_ranged_first, _melee)


def strike_key(policy, snapshot, target, reason: str, blow: Callable | None = None) -> str | None:
    """``target``'s answer in the fixed order; the caller holds the gates."""
    strike = _Strike(policy, snapshot, target, reason, blow)
    return next(answer.key for provider in _MELEE_OPEN
                if (answer := provider(strike)) is not None)


def adjacent_attack(policy, snapshot, adjacent, reason: str, *,
                    blow: Callable | None = None,
                    on_engage: Callable[[], object] | None = None) -> Answer | None:
    """The answer to the weakest of ``adjacent``; None leaves the board to the rung.

    ``blow`` takes the target and sends the melee blow, ``on_engage`` runs before
    the first answer of a fight the game allows."""
    if not adjacent:
        return None
    if attack_expectation.melee_answers_none_of(policy, snapshot, adjacent):
        # Owner 2026-11-11 「恐怖になって殴れなくなった時に飲む」: the Potion of Heroism ends the
        # fear that refuses the blow, before any other answer.
        key = heroism_potion.afraid_key(policy, snapshot, adjacent)
        if key is not None:
            return Answer(key)
        key = me_ranged_first.melee_refused_key(policy, snapshot, adjacent)
        return None if key is None else Answer(key)
    if on_engage is not None:
        on_engage()
    hurtable = [monster for monster in adjacent
                if not attack_expectation.blows_cannot_hurt(policy, snapshot, monster)]
    return Answer(strike_key(policy, snapshot, policy._weakest(hurtable), reason, blow))


def unseen_attacker_key(policy, snapshot, speed: Callable, last: Callable[[], str | None]) -> str | None:
    """A survival ladder's answer to an attacker it cannot see: the rung's Speed
    dose, the blind strike at the remembered cell, then the rung's last answer."""
    key = speed(policy, snapshot)
    if key is None:
        key = blind_strike.emergency_key(policy, snapshot)
    return last() if key is None else key
