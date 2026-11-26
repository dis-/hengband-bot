"""Can this Home take happen now: the one answer for filing and taking (MAINTAINABILITY.md rules 2, 3).

n1-a life-545 2026-11-27 03:11 (Amberite Rogue CL23, ordinary food, none carried): the fundraising
food need queued Home's 5-charge Identify staff as food (policy_town ``_town_need_candidates``), the
Home take on the entrance refused it as overweight (1445 of 1450, a staff weighs 50), released the
queue and stepped off, and the next decision queued it again: shop:approach,
home:leave-for-pending-withdraw, the step-off and policy:none-wait, about 34 times until
town:blocked:stage-deadline:home.

``refusal`` is the question both sides ask: a filer (``admit``) before it queues a take, the take
itself (policy_home ``_atomic_home_withdraw_key``) before it composes one.  A take the executor
refused is ``record``-ed with the pack weight of the refusal; it is not filed again in the same town
visit until the pack is lighter than it was then (a sale or a deposit made room).
"""
from __future__ import annotations

from typing import Any

from hengbot.policy_constants import PACK_CAPACITY

# {item signature: (town visit epoch, pack weight at the refusal)}; one town visit.
REFUSALS = "_home_take_refusals"

OVERWEIGHT = "identify-staff-overweight"
NO_PACK_SLOT = "no-pack-slot"
REFUSED_THIS_VISIT = "refused-this-visit"


def _refusals(policy: Any) -> dict:
    epoch = getattr(policy, "_town_visit_epoch", None)
    kept = {signature: entry for signature, entry
            in (getattr(policy, REFUSALS, None) or {}).items() if entry[0] == epoch}
    setattr(policy, REFUSALS, kept)
    return kept


def refusal(policy: Any, board: Any, item: Any, quantity: int | None = None) -> str | None:
    """Why a take of ``quantity`` of the Home stack ``item`` cannot happen on ``board``, or None."""
    signature = policy._item_signature(item)
    refused = _refusals(policy).get(signature)
    if refused is not None and policy._inventory_weight(board) >= refused[1]:
        return REFUSED_THIS_VISIT
    units = max(1, item.count if quantity is None else quantity)
    if policy._identify_staff_take_overloads(board, item, units):
        return OVERWEIGHT
    if (len(board.inventory) >= PACK_CAPACITY
            and not any(policy._item_signature(carried) == signature
                        for carried in board.inventory)):
        return NO_PACK_SLOT
    return None


def admit(policy: Any, board: Any, item: Any, quantity: int | None = None) -> bool:
    """Whether a filer may queue this take (``refusal`` is None)."""
    return refusal(policy, board, item, quantity) is None


def record(policy: Any, board: Any, signature: Any) -> None:
    """The executor refused the take of ``signature``: not again this visit at this weight."""
    _refusals(policy)[signature] = (getattr(policy, "_town_visit_epoch", None),
                                    policy._inventory_weight(board))
