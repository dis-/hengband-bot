"""Return a blocked shop route to the equipment operation that owns it."""

from hengbot.model import STORE_HOME
from hengbot.policy_constants import WAIT_KEY
from hengbot.town_hold import CLOSED_BY_RELEASE, hold_claims


def refuses_route(policy, store_type) -> bool:
    """Whether the open equipment session refuses this shop route.

    Every route but Home's relocates the transaction.  A Home route is the
    Home work's own dispatcher, except while the session's next action is
    an equip outside Home: going in only meets equipment-transaction:
    leave-home-for-equip, and the equip waited behind each re-entry (n1-c
    life-112, 2026-11-03 00:25, owner-retired-burst after three
    leave/enter rounds with the amulet still in the pack).
    """
    if store_type != STORE_HOME:
        return True
    session = policy._equipment_transaction_session
    return (session is not None and not session.complete
            and session.required_context == "outside_home")


def withdraws_first(session) -> bool:
    """Whether the open Home session's next action is a withdraw, nothing of
    it in hand yet: the session's own Home route goes first.

    Owner 2026-11-03 「先に自宅で取り出す」 (n1-c life-112, 2026-11-02 23:43):
    the withdraw of 六尺棒 {Q34} waited while the town plan routed to the
    Armoury; every approach was refused (route-refused:2, ``5``) until
    town:blocked:owner-retired-burst.  The session re-enters Home even when
    this visit was there already, then the other errand goes on.
    """
    action = session.current_action
    return (session.required_context == "home" and session.pending_action is None
            and action is not None and action.kind == "withdraw")


def release_suspended_home_route(policy) -> None:
    """End the session's own walk to Home that survival suspended.

    The walk is the store router's claim, and a suspended errand defers every
    other family, the session included: nothing would resume the walk, as only
    the session routes to Home.  n1-c life-122 2026-11-03: a thief interrupted
    the walk with both weapons off, the session waited behind its own route
    (and the wait, with no reason of its own, reached the executor as the
    previous decision's browse: stuck-prompt periodic:magic-eater-powers).  The
    session asks for the route again.
    """
    visit = policy._store_visit
    if (visit is None or visit.owner != "equipment-transaction"
            or visit.store_type != STORE_HOME):
        return
    register = hold_claims(policy)
    for claim in register.suspended:
        declaration = claim.execution
        if (claim.owner.value == "store-router" and declaration is not None
                and declaration.work_id.startswith("route:store:")):
            register.close_suspended(claim.claim_id, CLOSED_BY_RELEASE,
                                     "equipment-session-resumes-home-route")


def equipment_route_key(policy, snapshot):
    session = policy._equipment_transaction_session
    # A pack equip/takeoff owns this square, and a posted action owns its
    # observation. Other Home work keeps its existing route/visit dispatcher.
    if (session is not None and not session.complete
            and (session.required_context != "home" or withdraws_first(session))):
        key = policy._equipment_transaction_town_key(snapshot)
        # A rejected first action leaves no physical restoration debt. Close
        # its failed ownership now, before the caller retries supplier routing.
        if (policy._equipment_transaction_session is session
                and not session.executable and not policy._equipment_transaction_owned_items):
            policy._abandon_blocked_equipment_transaction(snapshot)
        if key is not None:
            return key
    policy._offer_execution(
        WAIT_KEY, producer="store-router",
        work_id=f"route-refused:{policy._shopping_approach_store_type}",
        state="releasing", cause="equipment-transaction-owns-relocation",
        post_on_emit=False,
    )
    return WAIT_KEY
