"""Town inventory capacity: reserve expedition slots before emitting an action.

Credits are observed inventory removals, never a promise to sell later. A
zero-cost operation may repair an already over-budget pack.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from hengbot.model import STORE_HOME, TVAL_CAPTURE, TVAL_ROD, TVAL_WAND, TVAL_FOOD, TVAL_POTION, TVAL_SCROLL


_ROOM_ASSUMED = ContextVar("town_pack_room_assumed", default=False)


@contextmanager
def assuming_room():
    """Ask a purchase question as if the pack had room for it.

    Only town_pack_headroom.pack_full_no_room asks it, to tell a purchase the
    pack alone refuses from one the shelf, the price or the need refuses.
    """
    token = _ROOM_ASSUMED.set(True)
    try:
        yield
    finally:
        _ROOM_ASSUMED.reset(token)


def room_assumed() -> bool:
    return _ROOM_ASSUMED.get()


def permits(snapshot, slots: int) -> bool:
    return (not getattr(snapshot, "in_town", False) or slots <= 0
            or PACK_CAPACITY - len(snapshot.inventory) - slots
            >= MIN_TERMINAL_FREE_PACK_SLOTS)


def home_take_fits(snapshot, item, quantity: int) -> bool:
    """The Home take admission the outside composer applies (store_item_key).

    Owners that bind or hand off a Home withdrawal ask the same question, so a
    take the composer will refuse is never left pending across a Home exit.
    """
    return permits(snapshot, incoming_slots(snapshot, item, quantity))


def below_floor(snapshot) -> bool:
    """Distinguish an actual reserve deficit from a refused additional slot."""
    return (snapshot.in_town
            and PACK_CAPACITY - len(snapshot.inventory) < MIN_TERMINAL_FREE_PACK_SLOTS)


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
    return bool(snapshot is not None and below_floor(snapshot)
                and preservable(policy, snapshot, item))


def relief_key(policy, snapshot):
    """Terminal overflow delegates to the same proactive town owner."""
    from hengbot.town_pack_headroom import begin_key
    if not below_floor(snapshot):
        return None
    disposable = policy._overflow_disposal_item(snapshot)
    if disposable is not None and policy._junk_class(snapshot, disposable) is not None:
        return None  # The existing overflow destroy primitive owns its reason.
    return begin_key(policy, snapshot)
