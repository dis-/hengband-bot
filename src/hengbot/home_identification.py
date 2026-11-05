"""Which catalogued Home equipment this town visit can take out and identify.

Owner 2026-10-31 「鑑定の手段がある時に、預けた未鑑定の装備を空きに収まる分
ずつ取り出して鑑定」.  One rule answers it for every owner: the catalogue
take's binder (policy_home._bind_catalogued_home_identification_withdrawal),
the release of a filed take that can no longer be done, and the town end's
identification wait (identification_wait.visit_can_identify).  An item is
doable when the current Home catalogue observed it, the visit has not
deferred it, a reliable carried source of the needed tier identifies it
(a known item that needs *Identify* takes a full-tier source), and its take
fits the pack reserve.

n1-a life-472 (2026-11-03 12:05): the cloak's take was filed while an
Identify scroll was carried; the scroll was then shelved, the take stayed
filed and unposted, and the armour the carried *Identify* could identify
was never filed: the visit stopped under
town:blocked:unmet:home_candidate_resolved (the fourth such stop).
"""

from __future__ import annotations

from typing import Any

from hengbot.model import item_requires_full_identification
from hengbot.town_pack_budget import home_take_fits

# The Home errand purpose of a catalogue identification take.
CATALOGUE_PURPOSE = "identification-catalog"


def source(policy: Any, board: Any, item: Any):
    """The reliable carried source that identifies the Home ``item`` now."""
    full = bool(item.known and item_requires_full_identification(item)
                and not item.fully_known)
    return policy._find_identification_source(
        board, full=full, reliable_only=True,
        reservation_target=policy._item_signature(item))


def _observed(policy: Any) -> set:
    if not policy._home_knowledge_current:
        return set()
    return {policy._item_signature(item) for item in
            policy._home_knowledge_items[:policy._home_knowledge_valid_before]}


def doable(policy: Any, board: Any, item: Any, observed: set | None = None) -> bool:
    """Whether this visit can take the Home ``item`` out and identify it."""
    signature = policy._item_signature(item)
    return (signature in (_observed(policy) if observed is None else observed)
            and signature not in policy._deferred_home_items
            and source(policy, board, item) is not None
            and home_take_fits(board, item, 1))


def candidates(policy: Any, board: Any) -> list:
    """The incomplete catalogued Home equipment this visit can identify."""
    observed = _observed(policy)
    return [owned.item for owned in policy._equipment_catalog.items
            if owned.origin == "home" and owned.identification_incomplete
            and doable(policy, board, owned.item, observed)]


def release_stale_take(policy: Any, board: Any) -> None:
    """An unposted catalogue take that can no longer be done gives way.

    It gives way only to another candidate this visit can identify, so a
    take waiting for its source to be bought keeps its slot.
    """
    errand = policy._home_errand
    request = errand.request
    if (not errand.active or request is None or request.purpose != CATALOGUE_PURPOSE
            or policy._home_atomic_withdraw_pending is not None):
        return
    target = next((owned.item for owned in policy._equipment_catalog.items
                   if owned.origin == "home"
                   and policy._item_signature(owned.item) == request.signature), None)
    if target is not None and doable(policy, board, target):
        return
    if any(policy._item_signature(item) != request.signature
           for item in candidates(policy, board)):
        errand.cancel_unposted()


def filed_take_route_key(policy: Any, board: Any) -> str | None:
    """Route Home for a filed catalogue take this visit can do.

    The town end is reached with the take filed but Home already tried this
    visit (its pass did another operation and was charged).  Home is re-armed
    within its pass bound (``_rearm_town_store_for_new_work``) and the router
    walks there, as ``overweight_home_key`` does for an overload; with the
    bound used up nothing is returned and the named stop stands.
    """
    from hengbot.model import STORE_HOME
    errand = policy._home_errand
    request = errand.request
    if (not errand.active or request is None or request.purpose != CATALOGUE_PURPOSE
            or STORE_HOME not in policy._town_store_attempted
            or not any(policy._item_signature(item) == request.signature
                       for item in candidates(policy, board))):
        return None
    if policy._home_store_block_owner == (policy._town_visit_epoch, "equipment-work"):
        # The bound closed Home to the deposit a full Home refused; the take
        # deposits nothing and frees a shelf (n1-a life-487 19:30, 20:08: the
        # deposit closed Home on the pass the take was filed for, and the town
        # end stopped under town:blocked:unmet:home_candidate_resolved).
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
    return rearmed_home_route_key(policy, board)


def rearmed_home_route_key(policy: Any, board: Any) -> str | None:
    """Re-arm a tried Home within its pass bound and route there, or None."""
    from hengbot.model import STORE_HOME
    policy._rearm_town_store_for_new_work(STORE_HOME)
    if STORE_HOME in policy._town_store_attempted:
        return None
    step = policy._shopping_approach_step(board, router_plan_stop=True)
    if step is None:
        return None
    key = policy._shopping_approach_key(board, step, "shop:travel")
    if key is not None:
        policy._record_shop_selector_diagnostics(board, key)
    return key
