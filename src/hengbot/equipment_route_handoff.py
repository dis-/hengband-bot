"""Return a blocked shop route to the equipment operation that owns it."""

from hengbot.policy_constants import WAIT_KEY


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
