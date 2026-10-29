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
        and policy._home_atomic_deposit_pending is None
        and policy._home_atomic_withdraw_pending is None
        and not policy._fixed_quest_prepare_return_required(snapshot)
        and not _merging_home_take(policy, snapshot)
    )


def _merging_home_take(policy, snapshot):
    """Finish a selected zero-slot merge without changing its shelf address."""
    from hengbot.town_pack_budget import incoming_slots
    signature = policy._home_pending_item
    if signature is None or not policy._home_knowledge_current:
        return False
    quantity = policy._home_pending_quantities.get(signature,
        policy._home_pending_quantity or 1)
    return any(policy._item_signature(item) == signature
               and incoming_slots(snapshot, item, quantity) == 0
               for item in policy._home_knowledge_items)


def acquisition_waits(policy, snapshot):
    """An unstarted purchase yields to observed, actionable slot recovery."""
    return bool(organizing(policy, snapshot) and eligible(policy, snapshot) and (
        policy._town_space_deposit_actionable(snapshot)
        or find_sale(policy, snapshot) is not None
        or policy._find_worthless_junk(snapshot) is not None))


def key(policy, snapshot):
    """Use beneficial supplies, preserve surplus, sell, then destroy junk."""
    from hengbot.town_pack_budget import below_floor
    if not eligible(policy, snapshot):
        return None
    if policy._home_knowledge_scan_inflight:
        # Optional work can continue beside a census, but an actual overflow
        # must await that census rather than declaring preserving relief absent.
        if below_floor(snapshot):
            return policy._town_producer_entry("_home_full_knowledge_key",
                lambda: policy._home_full_knowledge_key(snapshot, leave_foreign_store=True),
                family="home-scan", board=snapshot)
        return None
    result = _use_key(policy, snapshot)
    if result is not None:
        return result
    # The approved four-staff cap sells its weakest release before shelving.
    release = policy._find_surplus_identify_staff(snapshot)
    if release is not None:
        outlet = policy._town_organization_sale_store(snapshot, release)
        if outlet is not None:
            result = _relief_route(policy, snapshot, outlet, release)
            if result is not None:
                return result
    if (not policy._home_knowledge_current and policy._home_available(snapshot)
            and not policy._home_deposit_abandoned
            and not policy._home_knowledge_scan_inflight
            and policy._home_knowledge_scan_epoch is None
            and any(preservable(policy, snapshot, item) for item in snapshot.inventory)):
        result = policy._town_producer_entry("_home_full_knowledge_key",
            lambda: policy._home_full_knowledge_key(snapshot, leave_foreign_store=True),
            family="home-scan", board=snapshot)
        if result is not None:
            return result
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
    if snapshot.store is None:
        return policy._town_producer_entry("_worthless_junk_destroy_key",
            lambda: policy._worthless_junk_destroy_key(snapshot), family="shop-sell")
    return None


def find_deposit(policy, snapshot):
    if (not selection_enabled(policy, snapshot) or not eligible(policy, snapshot)
            or not policy._home_knowledge_current
            or policy._home_is_full(snapshot)):
        return None
    return next((item for item in snapshot.inventory
                 if preservable(policy, snapshot, item)
                 and policy._item_signature(item) not in policy._home_rejected_deposits
                 and policy._item_signature(item) not in policy._home_pending_batch
                 and item.slot not in {policy._home_pending_slot,
                                       policy._pending_disposal_slot}), None)


def find_sale(policy, snapshot):
    """File an ordinary organization sale after Home relief is unavailable."""
    if (not selection_enabled(policy, snapshot) or not eligible(policy, snapshot)
            or policy._home_knowledge_scan_inflight):
        return None
    home_open = (policy._home_available(snapshot) and not policy._home_is_full(snapshot)
                 and not policy._home_deposit_abandoned
                 and not policy._town_store_blocked_under_applicable_bound(STORE_HOME))
    return next((item for item in snapshot.inventory
                 if preservable(policy, snapshot, item)
                 and (not home_open or policy._item_signature(item)
                      in policy._home_rejected_deposits)
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


def organizing(policy, snapshot):
    """Continue only the inventory pass admitted after ordinary town errands."""
    return (snapshot.in_town and getattr(policy, "_pack_headroom_visit", None)
            == (policy._town_visit_epoch, policy._effective_town_id(snapshot)))


def selection_enabled(policy, snapshot):
    from hengbot.town_pack_budget import below_floor
    return below_floor(snapshot) or organizing(policy, snapshot) or may_begin(policy, snapshot)


def may_begin(policy, snapshot):
    """Recover blocked acquisition room without seizing a live town errand."""
    from hengbot.policy_constants import PACK_CAPACITY, MIN_TERMINAL_FREE_PACK_SLOTS
    plan = policy._town_errand_plan
    return bool(
        snapshot.in_town
        and PACK_CAPACITY - len(snapshot.inventory) == MIN_TERMINAL_FREE_PACK_SLOTS
        and policy._home_knowledge_current
        and not policy._home_knowledge_scan_inflight
        and policy._home_pending_item is None and not policy._home_pending_batch
        and policy._home_visit.request is None
        and (snapshot.store is None or snapshot.store.store_type == STORE_HOME)
        and (plan is None or plan.index >= len(plan.stops))
        and eligible(policy, snapshot)
        and any(preservable(policy, snapshot, item) for item in snapshot.inventory))


def begin_key(policy, snapshot):
    """The terminal seam starts a pass; free-slot recovery never ends it early."""
    if not eligible(policy, snapshot):
        return None
    begin(policy, snapshot)
    return key(policy, snapshot)


def begin(policy, snapshot):
    """Remember the admitted inventory pass across observed transfers."""
    policy._pack_headroom_visit = (policy._town_visit_epoch, policy._effective_town_id(snapshot))


def early_key(policy, snapshot):
    """Resume admitted cleanup, otherwise preserve the existing shortage owner."""
    if organizing(policy, snapshot):
        return key(policy, snapshot)
    if may_begin(policy, snapshot):
        return begin_key(policy, snapshot)
    if not policy._town_space_deposit_actionable(snapshot):
        return None
    from hengbot.policy_constants import PACK_CAPACITY
    if (len(snapshot.inventory) < PACK_CAPACITY
            and policy._town_order_step4_pending(snapshot)):
        return None
    policy._town_claims_active(snapshot)
    step = policy._shopping_approach_step(snapshot, requester="home-visit")
    if step is None or policy._shopping_approach_store_type != STORE_HOME:
        return None
    policy.last_reason = "shop:approach"
    return policy._town_producer_entry("_shopping_approach_key",
        lambda: policy._shopping_approach_key(snapshot, step, "shop:travel"),
        family="home-visit")
