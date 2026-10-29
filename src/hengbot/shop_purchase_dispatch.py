"""Execute the live purchase choice through the shared shop admission path."""

from hengbot.purchase_rungs import PurchaseContext, PurchaseSelection


def next_purchase_key(policy, snapshot):
    previous = getattr(policy, "_shop_selection_commits", False)
    policy._shop_selection_commits = True
    try:
        item = policy._next_purchase(snapshot)
    finally:
        policy._shop_selection_commits = previous
    if item is None:
        return None
    matches = policy._matching_live_purchase_rungs(snapshot, item)
    selection = PurchaseSelection(
        matches[0] if matches else None, item, snapshot.store.store_type,
        PurchaseContext(snapshot), policy._purchase_quantity(snapshot, item),
    )
    return policy._shop_purchase_key(snapshot, selection)
