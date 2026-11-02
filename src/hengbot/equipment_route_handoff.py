"""Return a blocked shop route to the equipment operation that owns it."""

from hengbot.model import STORE_HOME
from hengbot.policy_constants import WAIT_KEY


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


def equipment_route_key(policy, snapshot):
    session = policy._equipment_transaction_session
    # A pack equip/takeoff owns this square, and a posted action owns its
    # observation. Home work keeps its existing route/visit dispatcher.
    if (session is not None and not session.complete
            and session.required_context != "home"):
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
