"""Town inventory capacity: reserve expedition slots before emitting an action.

Credits are observed inventory removals, never a promise to sell later. A
zero-cost operation may repair an already over-budget pack.
"""

from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from hengbot.model import STORE_HOME, TVAL_CAPTURE, TVAL_ROD, TVAL_WAND, TVAL_FOOD, TVAL_POTION, TVAL_SCROLL


def permits(snapshot, slots: int) -> bool:
    return (not getattr(snapshot, "in_town", False) or slots <= 0
            or PACK_CAPACITY - len(snapshot.inventory) - slots
            >= MIN_TERMINAL_FREE_PACK_SLOTS)


def floor_step_fits(snapshot, position) -> bool:
    if not getattr(snapshot, "in_town", False):
        return True
    grid = snapshot.grids.get(position)
    return grid is None or permits(snapshot, grid.object_count)


def native_travel_fits(snapshot) -> bool:
    # Native travel can traverse several pickup tiles before the next board.
    return (not getattr(snapshot, "in_town", False)
            or permits(snapshot, sum(grid.object_count for grid in snapshot.grids.values())))


def incoming_slots(snapshot, item, quantity: int) -> int:
    """Conservative carry estimate using the shared exported similarity fields.

    Partial wand transfers can change per-stack charges. Unknown objects
    cannot prove similarity. Leave those one slot.
    """
    if not item.known or not item.aware or (
            item.tval == TVAL_WAND and quantity < item.count):
        return 1
    fields = (
        "tval", "sval", "aware", "known", "fully_known", "pval", "fuel",
        "is_ego", "is_artifact", "is_cursed", "is_broken",
        "to_h", "to_d", "to_a", "ac", "damage_dice_num", "damage_dice_sides",
        "known_flags", "inscription",
    )
    return int(not any(
        carried.count + quantity <= 99
        # Consumables have no recharge state. Home protocol-2 catalogues
        # export 0 where protocol-3 pack observations omit it (None).
        and (item.tval in {TVAL_FOOD, TVAL_POTION, TVAL_SCROLL}
             or carried.timeout == item.timeout)
        and all(getattr(carried, field, 0) == getattr(item, field, 0)
                for field in fields)
        for carried in snapshot.inventory
    ))


def pressure_deposit(policy, snapshot, item) -> bool:
    """Preserve a whole surplus consumable/device instead of declaring overflow.

    Equipment still belongs to its optimizer. Identification, mining, carry
    reservations and purpose purchases keep their existing authorities.
    """
    return bool(
        snapshot is not None and snapshot.in_town
        and PACK_CAPACITY - len(snapshot.inventory) < MIN_TERMINAL_FREE_PACK_SLOTS
        and item.known and item.aware and not item.is_equipment
        and not item.is_bounty and not item.is_cursed
        and (item.is_potion or item.is_scroll or item.is_wand_staff
             or item.tval in {TVAL_ROD, TVAL_CAPTURE})
        and policy._entire_stack_is_surplus(snapshot, item)
        and policy._item_signature(item) not in policy._town_visit_purchases
        and not policy._identification_flow_owns(item)
        and not policy._disposal_protected_by_identification(item)
        and policy._junk_class(snapshot, item) is None
    )


def find_pressure_deposit(policy, snapshot):
    if not policy._home_knowledge_current or policy._home_is_full(snapshot):
        return None
    return next((item for item in snapshot.inventory
                 if pressure_deposit(policy, snapshot, item)
                 and policy._item_signature(item) not in policy._home_rejected_deposits
                 and policy._item_signature(item) not in policy._home_pending_batch
                 and item.slot not in {policy._home_pending_slot,
                                       policy._pending_disposal_slot}), None)


def find_pressure_sale(policy, snapshot):
    """File an ordinary organization sale after Home relief is unavailable."""
    if (PACK_CAPACITY - len(snapshot.inventory) >= MIN_TERMINAL_FREE_PACK_SLOTS
            or (policy._home_available(snapshot) and not policy._home_is_full(snapshot)
                and not policy._home_deposit_abandoned)):
        return None
    return next((item for item in snapshot.inventory
                 if pressure_deposit(policy, snapshot, item)
                 and policy._town_organization_sale_store(snapshot, item) is not None), None)


def relief_key(policy, snapshot):
    """Exhaust preserving routes and useful consumption before destruction.

    Keep the normal route/operation owners, refusal latches and visit bounds.
    A deposit/sale of a partial reserved stack cannot free a slot.
    """
    if (not snapshot.in_town
            or PACK_CAPACITY - len(snapshot.inventory) >= MIN_TERMINAL_FREE_PACK_SLOTS):
        return None
    disposable = policy._overflow_disposal_item(snapshot)
    if disposable is not None and policy._junk_class(snapshot, disposable) is not None:
        return None
    if (not policy._home_knowledge_current and policy._home_available(snapshot)
            and not policy._home_deposit_abandoned
            and any(pressure_deposit(policy, snapshot, item) for item in snapshot.inventory)):
        return policy._town_producer_entry("_home_full_knowledge_key",
            lambda: policy._home_full_knowledge_key(snapshot, leave_foreign_store=True),
            family="home-scan", board=snapshot)
    deposit = policy._find_home_deposit(snapshot)
    if (deposit is not None and policy._entire_stack_is_surplus(snapshot, deposit)
            and policy._home_available(snapshot) and not policy._home_is_full(snapshot)):
        key = _relief_route(policy, snapshot, STORE_HOME, deposit)
        if key is not None:
            return key
    organization = policy._find_town_organization_surplus(snapshot)
    candidates = ([organization] if organization is not None else []) + [
        item for item in snapshot.inventory if pressure_deposit(policy, snapshot, item)]
    for item in dict.fromkeys(candidates):
        store = policy._town_organization_sale_store(snapshot, item)
        if store is not None:
            key = _relief_route(policy, snapshot, store, item)
            if key is not None:
                return key
    return _use_key(policy, snapshot)


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
