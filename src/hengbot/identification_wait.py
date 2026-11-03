"""Identification the town visit cannot finish does not hold its departure.

Owner decisions: 2026-09-02 「鑑定不能品を除外して装備を選定する。鑑定不能品
があっても出発は許可する。次回以降帰還時鑑定を試みる。」; 2026-09-13 「鑑定待ち
でも止めない」; 2026-10-31 「鑑定待ちの装備は預ける　極力持ち歩かない」 and
「鑑定できない訪問では取り出さない」.

The town end (town_terminal.town_end_key) is reached only on a board no owner
answered, so identification work still latched there (the identification
need, the Home candidate latch, the *Identify* expedition's Home targets) is
work this visit does not perform.  It is released for this visit: the
candidates join the visit's deferred Home items, which every fresh town
visit clears, so the next return tries again.  A Home transfer in flight is
left to its owner, and a visit that can still identify a candidate (a
carried source for a carried one; for a Home one also a take that fits the
pack reserve, owner 10-31 「空きに収まる分ずつ取り出して鑑定」) keeps its
named stop: that is an owner's defect, not a wait (owner 2026-11-03).

n1-b life-300 (2026-11-03 01:56 and 02:23, the Outpost): the Home armour
waiting for *Identify* held the visit after every stop of the plan was done,
and the visit stopped under town:blocked:unmet:home_candidate_resolved.

n1-b life-306 (2026-11-03 21:33): the same stop with a carried whip and two
Identify staffs of a 71% device skill.  The staff is no source below
STAFF_IDENTIFY_MIN_SUCCESS (identify-carried refused no-identification-source),
but this wait counted it, so the wait was held for a command never composed.
"""

from __future__ import annotations

from typing import Any

from hengbot import home_identification

# The departure leaves an identification wait holds.
WAIT_LEAVES = frozenset({
    "home_candidate_resolved",
    "identification_need_clear",
    "departure_identification_need_clear",
})
DEFER_SITE = "identification-wait-town-end"


def holds(unmet) -> bool:
    """Whether an identification wait is among the unmet departure leaves."""
    return bool(WAIT_LEAVES.intersection(unmet))


def visit_can_identify(policy: Any, board: Any) -> bool:
    """Whether this visit still holds the means to identify a candidate."""
    candidate = policy._identification_candidate
    if candidate is not None and policy._identification_need is not None and any(
            policy._item_signature(item) == candidate for item in board.inventory):
        if policy._carried_identification_source(
                board, full=policy._identification_need == "full") is not None:
            return True
    return bool(home_identification.candidates(policy, board))


def release(policy: Any, board: Any, unmet) -> bool:
    """Release this visit's identification wait; True when it was released."""
    if (not holds(unmet)
            or policy._home_pending_item is not None
            or policy._home_atomic_withdraw_pending is not None
            or visit_can_identify(policy, board)):
        return False
    expedition = policy._morivant_full_identify
    if (expedition is not None and expedition.phase == "prepare-home"
            and not expedition.temporary_deposits):
        policy._finish_morivant_full_identify()
    policy._defer_identification_for_conquest(board)
    for owned in policy._equipment_catalog.items:
        if owned.origin == "home" and owned.identification_incomplete:
            policy._defer_home_item(policy._item_signature(owned.item), DEFER_SITE)
    policy._release_stale_home_candidate_waiting(board)
    return True
