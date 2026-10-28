"""Free every safely releasable town stack before acquiring more inventory.

The slot budget remains a floor. Selection uses the existing retention,
identification, Home and store executors, including their refusal bounds.
"""

from hengbot.model import STORE_HOME, TVAL_CAPTURE, TVAL_ROD


def preservable(policy, snapshot, item):
    """A whole unneeded consumable/device, independent of current free slots."""
    return bool(
        snapshot is not None and snapshot.in_town
        and item.known and item.aware and not item.is_equipment
        and not item.is_bounty and not item.is_cursed
        and (item.is_potion or item.is_scroll or item.is_wand_staff
             or item.tval in {TVAL_ROD, TVAL_CAPTURE})
        and policy._entire_stack_is_surplus(snapshot, item)
        and policy._carried_disposal_preserves_departure(snapshot, item, item.count)
        and policy._item_signature(item) not in policy._town_visit_purchases
        and not policy._identification_flow_owns(item)
        and not policy._disposal_protected_by_identification(item)
        and policy._junk_class(snapshot, item) is None
    )


def eligible(policy, snapshot):
    """Never interrupt a survival departure, equipment mutation or quest return."""
    return bool(
        snapshot.in_town and not snapshot.player.recalling
        and not (snapshot.player.hungry and policy._find_edible(snapshot) is None)
        and policy._equipment_mutation.state.name == "IDLE"
        and policy._equipment_transaction_session is None
        and not policy._fixed_quest_prepare_return_required(snapshot)
    )


def acquisition_waits(policy, snapshot):
    """An unstarted purchase yields to observed, actionable slot recovery."""
    return bool(eligible(policy, snapshot) and (
        policy._town_space_deposit_actionable(snapshot)
        or find_sale(policy, snapshot) is not None
        or policy._find_worthless_junk(snapshot) is not None))


def key(policy, snapshot):
    """Preserve first, sell next, use beneficial supplies, then destroy junk."""
    if not eligible(policy, snapshot):
        return None
    if (not policy._home_knowledge_current and policy._home_available(snapshot)
            and not policy._home_deposit_abandoned
            and any(preservable(policy, snapshot, item) for item in snapshot.inventory)):
        return policy._town_producer_entry("_home_full_knowledge_key",
            lambda: policy._home_full_knowledge_key(snapshot, leave_foreign_store=True),
            family="home-scan", board=snapshot)
    deposit = policy._find_home_deposit(snapshot)
    if (deposit is not None and policy._home_available(snapshot)
            and not policy._home_is_full(snapshot)):
        result = _relief_route(policy, snapshot, STORE_HOME, deposit)
        if result is not None:
            return result
    sale = policy._find_town_organization_surplus(snapshot)
    if sale is not None:
        store = policy._town_organization_sale_store(snapshot, sale)
        if store is not None:
            result = _relief_route(policy, snapshot, store, sale)
            if result is not None:
                return result
    result = _use_key(policy, snapshot)
    if result is not None:
        return result
    if snapshot.store is None:
        return policy._town_producer_entry("_worthless_junk_destroy_key",
            lambda: policy._worthless_junk_destroy_key(snapshot), family="shop-sell")
    return None


def find_deposit(policy, snapshot):
    if not policy._home_knowledge_current or policy._home_is_full(snapshot):
        return None
    return next((item for item in snapshot.inventory
                 if preservable(policy, snapshot, item)
                 and policy._item_signature(item) not in policy._home_rejected_deposits
                 and policy._item_signature(item) not in policy._home_pending_batch
                 and item.slot not in {policy._home_pending_slot,
                                       policy._pending_disposal_slot}), None)


def find_sale(policy, snapshot):
    """File an ordinary organization sale after Home relief is unavailable."""
    if (policy._home_available(snapshot) and not policy._home_is_full(snapshot)
            and not policy._home_deposit_abandoned):
        return None
    return next((item for item in snapshot.inventory
                 if preservable(policy, snapshot, item)
                 and policy._town_organization_sale_store(snapshot, item) is not None), None)


def _use_key(policy, snapshot):
    if snapshot.store is not None:
        return None
    hostiles = policy._physical_hostiles(snapshot)
    for consume in (
            lambda: policy._town_producer_entry("_stat_restore_quaff_key",
                lambda: policy._stat_restore_quaff_key(snapshot, hostiles), board=snapshot),
            lambda: policy._town_producer_entry("_experience_potion_quaff_key",
                lambda: policy._experience_potion_quaff_key(snapshot, hostiles), board=snapshot),
            lambda: policy._town_producer_entry("_stat_gain_quaff_key",
                lambda: policy._stat_gain_quaff_key(snapshot, hostiles), board=snapshot)):
        key = consume()
        if key is not None:
            return key
    return None


def _relief_route(policy, snapshot, store, item):
    family = "home-visit" if store == STORE_HOME else "shop-sell"
    if snapshot.store is not None:
        if snapshot.store.store_type != store:
            return None
        if store == STORE_HOME:
            return policy._town_producer_entry("_open_home_deposit_key",
                lambda: policy._open_home_deposit_key(snapshot), family=family, board=snapshot)
        return policy._store_sale_entry_key(snapshot, item, "shop:batch-sell")
    if policy._town_store_blocked_under_applicable_bound(store):
        return None
    step = policy._shopping_approach_step(snapshot, store, requester=family)
    if step is None:
        return None
    return policy._town_producer_entry(
        "_shopping_approach_key",
        lambda: policy._shopping_approach_key(snapshot, step, "shop:travel"),
        family=family)
