"""Keep equipment plan admission consistent with the town mutation budget."""

from hengbot.equipment_transaction_planner import plan_equipment_transactions as _plan
from hengbot import town_pack_budget as budget


def plan_equipment_transactions(*args, **kwargs):
    """Reserve expedition slots before admitting a physical equipment plan."""
    plan = _plan(*args, **kwargs)
    if not any(action.kind in {'takeoff', 'withdraw'} for action in plan.actions):
        # Empty plans and capacity relief remain legal above the budget.
        return plan
    return _plan(*args, pack_capacity=budget.PACK_CAPACITY - budget.MIN_TERMINAL_FREE_PACK_SLOTS,
                 **kwargs)


def release_unaffordable_session(policy, snapshot):
    """Replan an unposted takeoff after inventory outgrows its admission.

    No item failed and no movement failed. Keep restoration debt and posted
    operations with their existing owner; only debt-free work can yield here.
    """
    session = policy._equipment_transaction_session
    if (not snapshot.in_town or session is None or not session.executable
            or session.pending_action is not None
            or policy._equipment_transaction_owned_items):
        return
    action = session.current_action
    if action is None or action.kind != "takeoff":
        return
    item = next((item for item in snapshot.equipment
                 if item.slot == action.target_slot), None)
    if item is None or budget.permits(snapshot, budget.incoming_slots(snapshot, item, item.count)):
        return
    policy._release_claim_goal('equipment-capacity-replan', owners=('equipment-txn',))
    if (policy._store_visit is not None
            and policy._store_visit.owner == 'equipment-transaction'):
        policy._close_store_visit('equipment-capacity-replan')
    policy._set_equipment_transaction_session(None)
    policy._equipment_optimization_signature = None
