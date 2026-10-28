"""Town inventory capacity: reserve expedition slots before emitting an action.

Credits are observed inventory removals, never a promise to sell later. A
zero-cost operation may repair an already over-budget pack.
"""

from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from hengbot.model import TVAL_WAND, TVAL_FOOD, TVAL_POTION, TVAL_SCROLL


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
    from hengbot.town_pack_headroom import preservable
    return bool(snapshot is not None and snapshot.in_town
                and PACK_CAPACITY - len(snapshot.inventory) < MIN_TERMINAL_FREE_PACK_SLOTS
                and preservable(policy, snapshot, item))


def relief_key(policy, snapshot):
    """Terminal overflow delegates to the same proactive town owner."""
    from hengbot.town_pack_headroom import key
    if (not snapshot.in_town
            or PACK_CAPACITY - len(snapshot.inventory) >= MIN_TERMINAL_FREE_PACK_SLOTS):
        return None
    disposable = policy._overflow_disposal_item(snapshot)
    if disposable is not None and policy._junk_class(snapshot, disposable) is not None:
        return None  # The existing overflow destroy primitive owns its reason.
    return key(policy, snapshot)
