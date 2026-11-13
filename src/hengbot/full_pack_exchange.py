"""With the pack full, a floor item worth more than the cheapest spare carried item is taken.

Owner 2026-11-13 (answer 「価値の低い品を捨てて拾う」, its option verbatim: 「床の品の方が価値が
高ければ、持ち物の一番価値の低い品（予備の魔法書の重複・余った矢など、必需品以外）を壊して空きを作り
拾う。必需品（帰還・テレポート・回復・食料・光源）は捨てない。」).  n1-c life-205 (Angband 62F, quest
46, 2026-11-13 01:03-01:08) explored 449 boards with 23 of 23 slots and every floor item
blocked as ``pack-full``.

The value is the base kind's cost (k_info, ``baseitem_knowledge``), the one value the player can
know of an aware kind on the floor (grid_map ``found_item_ids`` carry the sval of an aware kind
only).  The carried item is the cheapest whose whole stack is surplus to the retention plan
(policy ``_cheapest_exchange_item``: not a Recall scroll, a dear spellbook or a protected
digger), and never a necessity: no potion, scroll of Teleportation, food, light source, flask
of oil or magic device; nor an ego, an artifact or an unknown item, whose worth its base kind's
cost does not measure.  Only a pile of one item is exchanged, so one freed slot takes it.  The
walk goes to the pile first and destroys the carried item standing on it, so nothing is
destroyed for an item that is never reached; the ordinary pickup takes it on the next board.

Where it is asked (n1-c life-205, Orc cave 23F, 2026-11-13 09:22-12:52): the full pack's own
rung of the objectives layer (``ladder_objectives``, beside ``_full_pack_destroy_key``), ahead of
the return a full pack starts (``_should_start_town_return``, trigger ``pack-full``).  Asked only
from the loot owner, below that return, the exchange ran on quest floors alone (where the return
is locked): seven of seven ordinary full packs read Recall on the board the pack filled, with a
dearer single item known on the floor each time (a 25000-gold songbook for a 2-gold bolt stack).

テレポート (the owner's necessity) is every relocation scroll the escapes read (policy
``RELOCATION_SCROLL_SVALS``: Phase Door, Teleportation, Teleport Level); the live exchange
chose the one Phase Door carried as its spare.
"""

from __future__ import annotations

from hengbot.model import TVAL_FLASK, TVAL_FOOD, TVAL_LITE, TVAL_POTION, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND
from hengbot.policy_constants import PACK_CAPACITY

SEEK_REASON = "seek-loot:exchange"
DESTROY_REASON = "inventory:exchange-for-floor-loot"
NECESSITY_TVALS = frozenset({TVAL_POTION, TVAL_FOOD, TVAL_LITE, TVAL_FLASK,
                             TVAL_STAFF, TVAL_WAND, TVAL_ROD})


def _relocation_scroll(item) -> bool:
    from hengbot.policy import RELOCATION_SCROLL_SVALS
    return item.tval == TVAL_SCROLL and item.sval in RELOCATION_SCROLL_SVALS


def _necessity(item) -> bool:
    return (item.tval in NECESSITY_TVALS or item.is_recall_scroll or _relocation_scroll(item)
            or item.is_food or item.is_light or item.is_oil)


def _worth_more_than_its_kind(item) -> bool:
    """An ego, an artifact or an unknown item: its base kind's cost is no measure of it."""
    return item.is_ego or item.is_artifact or not item.known


def spare(policy, snapshot):
    """The cheapest carried item the exchange may destroy, or None.

    Only an item the destroy itself accepts: ``_verified_destroy_dispatch_key`` refuses an item
    that is the best of its comparable gear (``_destroy_would_discard_superior_item``), and the
    exchange's finder is bound to the one item chosen here.  n1-c life-205 (Orc cave 23F,
    2026-11-13 15:44:20 and 12:34:28): the cheapest spare was an amulet of resist lightning
    (base 300), the walk reached a metal scale mail pile (1100), the destroy refused the amulet
    on the pile, and the full pack's return read Recall there.
    """
    narrowed = [item for item in snapshot.inventory
                if not _necessity(item) and not _worth_more_than_its_kind(item)
                and not policy._destroy_would_discard_superior_item(snapshot, item)]
    if not narrowed:
        return None
    # Surplus is judged on the whole pack: a pack narrowed to the candidates hid the other
    # stacks of the same ammunition, and the one left was no longer surplus.
    return policy._cheapest_exchange_item(snapshot, narrowed)


def pile_value(policy, snapshot, position) -> int | None:
    """The base cost of the single aware item found on the cell, else None."""
    row = next((row for row in snapshot.found_items or ()
                if (row[0], row[1]) == (position.y, position.x)), None)
    ids = (snapshot.found_item_ids or {}).get(position)
    if row is None or row[2] != 1 or not ids or ids[0] is None:
        return None
    sval = ids[0].get("sval")
    if not isinstance(sval, int) or sval < 0:
        return None
    return policy._baseitem_costs.get((row[3], sval))


def key(policy, snapshot, hostiles) -> str | None:
    if snapshot.in_town or len(snapshot.inventory) < PACK_CAPACITY:
        return None
    if policy._loot_block_reason(snapshot, hostiles, ignore_pack=True) is not None:
        return None
    carried = spare(policy, snapshot)
    if carried is None:
        return None
    carried_cost = policy._baseitem_costs.get((carried.tval, carried.sval))
    if carried_cost is None:
        return None
    worth = {position for position in policy._loot_candidates(snapshot)
             if (value := pile_value(policy, snapshot, position)) is not None
             and value > carried_cost}
    if not worth:
        return None
    if snapshot.player.position in worth:
        return policy._verified_destroy_key(
            snapshot,
            lambda current, selected=carried: (
                selected
                if policy._item_signature(selected) not in policy._undestroyable_sigs
                and policy._entire_stack_is_surplus(current, selected)
                else None),
            DESTROY_REASON)
    policy._claim_target_capture = []
    try:
        step = policy._nearest_position_step(snapshot, worth)
    finally:
        target = policy._take_claim_target()
    if step is None:
        return None
    policy.last_reason = SEEK_REASON
    policy._declare_reach(target)
    return policy._step_toward(snapshot, step)
