"""Town inventory capacity: reserve expedition slots before emitting an action.

Credits are observed inventory removals, never a promise to sell later. A
zero-cost operation may repair an already over-budget pack.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from hengbot.model import Position, STORE_HOME, SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE, TVAL_CAPTURE, TVAL_GOLD, TVAL_ROD, TVAL_WAND, TVAL_FOOD, TVAL_POTION, TVAL_SCROLL


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


_EXPLICIT_PICKUP_CELLS: ContextVar[frozenset] = ContextVar(
    "town_explicit_pickup_cells", default=frozenset())


@contextmanager
def explicit_pickup_cells(cells):
    """Let a walk end on cells whose objects the caller picks up on purpose.

    The floor-step budget is for implicit pickups (walking over a pile in
    town picks it up); a mandatory pickup's own cell is not one.  Only
    town_quest_reward asks it, for its allowlisted reward cells.
    """
    token = _EXPLICIT_PICKUP_CELLS.set(frozenset(cells))
    try:
        yield
    finally:
        _EXPLICIT_PICKUP_CELLS.reset(token)


# Home takes that are used at once, so one slot of the reserve may hold
# them (owner 2026-11-03 「取り置きを使ってよい」: the *Remove Curse* read on
# the next board; nothing is sold or shelved to make room for it).
USED_AT_ONCE_TAKES = frozenset({
    (TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE),
    (TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE),
})


def used_at_once(item) -> bool:
    """Whether a Home take of ``item`` is used at once (``USED_AT_ONCE_TAKES``)."""
    return (item.tval, item.sval) in USED_AT_ONCE_TAKES


_RESERVE_SWAP: ContextVar[frozenset] = ContextVar("town_reserve_swap_items", default=frozenset())


def note_reserve_swap(session) -> None:
    """Remember what the open session's reserve swap may hold in the reserve.

    Owner 2026-11-04 「自宅の中だけ割ってよい」: the item taken off and the item
    taken out of one planned swap (equipment_transaction_planner), nothing else.
    """
    plan = getattr(session, "plan", None)
    _RESERVE_SWAP.set(frozenset(
        action.item_identity for action in plan.actions
        if action.kind in {"takeoff", "withdraw"}
    ) if getattr(plan, "reserve_swap", False) else frozenset())


def reserve_swap_slot(item) -> int:
    """One slot of the reserve for an item of the open reserve swap, else none."""
    swap = _RESERVE_SWAP.get()
    if not swap or not hasattr(item, "tval"):
        return 0
    from hengbot.equipment_optimizer import equipment_identity
    return int(equipment_identity(item) in swap)


def permits(snapshot, slots: int, *, reserve_used: int = 0) -> bool:
    return (not getattr(snapshot, "in_town", False) or slots <= 0
            or PACK_CAPACITY - len(snapshot.inventory) - slots
            >= MIN_TERMINAL_FREE_PACK_SLOTS - reserve_used)


def home_take_fits(snapshot, item, quantity: int) -> bool:
    """The Home take admission the outside composer applies (store_item_key).

    Owners that bind or hand off a Home withdrawal ask the same question, so a
    take the composer will refuse is never left pending across a Home exit.
    """
    return permits(snapshot, incoming_slots(snapshot, item, quantity),
                   reserve_used=max(int(used_at_once(item)), reserve_swap_slot(item)))


def below_floor(snapshot) -> bool:
    """Distinguish an actual reserve deficit from a refused additional slot."""
    return (snapshot.in_town
            and PACK_CAPACITY - len(snapshot.inventory) < MIN_TERMINAL_FREE_PACK_SLOTS)


def pile_slots(grid, snapshot=None) -> int:
    """Pack slots a walk over ``grid`` can fill: gold goes to the purse.

    With ``snapshot``, an object that joins a carried stack fills none
    (``stacking_pile_objects``).
    """
    slots = max(0, grid.object_count - sum(tval == TVAL_GOLD for tval in grid.object_tvals))
    if snapshot is None or slots == 0:
        return slots
    return max(0, slots - stacking_pile_objects(snapshot, grid))


def stacking_pile_objects(snapshot, grid) -> int:
    """Objects of ``grid``'s pile that a pickup puts on a carried stack.

    An object whose look name is a known carried stack's own inventory name
    is that stack's kind with the same visible state (a light's fuel, an
    inscription, known bonuses), so the game stacks it there and the pickup
    fills no slot.  An unknown or unaware carried item proves nothing
    (``incoming_slots``).  n1-b life-364 2026-11-10 10:18: the torch the
    character threw at a scruffy dog in the Outpost's one-cell east gate lay there
    as 松明(1700ターンの寿命) {明, @v0=g}, the name of the two carried, and
    19 carried items made the one-slot estimate refuse the gate: the walk to
    the Magic shop went round the outside of the town wall until
    owner-retired-burst.
    """
    names = (getattr(snapshot, "found_item_names", None) or {}).get(grid.position)
    if not names:
        return 0
    room = {item.name: 99 - item.count for item in snapshot.inventory
            if item.known and item.aware}
    stacking = 0
    for name in names:
        if name is not None and room.get(name, 0) > 0:
            room[name] -= 1
            stacking += 1
    return stacking


def floor_step_fits(snapshot, position) -> bool:
    if pile_fits(snapshot, position):
        return True
    return position in sealed_pile_exits(snapshot)


def pile_fits(snapshot, position) -> bool:
    """The budget alone: a walk onto ``position`` keeps the terminal reserve."""
    if not getattr(snapshot, "in_town", False) or position in _EXPLICIT_PICKUP_CELLS.get():
        return True
    grid = snapshot.grids.get(position)
    return grid is None or permits(snapshot, pile_slots(grid, snapshot))


_SEALED_CACHE: list = [None, frozenset()]


def sealed_pile_exits(snapshot) -> frozenset:
    """Refused piles that are the only way out of the player's cell or into an entrance.

    The budget keeps a walk off a pile whose pickup would eat the terminal
    reserve; it must not wall the player or a shop in.  n1-b life-370
    (2026-11-12 02:19, Outpost Home): with 19 of 23 slots used, the town
    chest pass dropped a carried chest on the Home entrance (an entrance
    holds no object, so it landed on the cell beside it) and opened it
    there; its two items scattered onto the entrance's other two approach
    cells.  Every way out of the Home pocket now carried a refused pile: the
    entrance step-off had no step (no-key-exhausted) and, after the restart,
    the inn route had no path (quest:blocked:me-staff
    travel-morivant-unavailable).  Where every passable non-entrance
    neighbour of the player's cell, or of a town entrance, is such a pile,
    those piles are walkable: the pickup is the cost, and the town's own
    disposal and deposit flows restore the reserve afterwards.
    """
    if not getattr(snapshot, "in_town", False):
        return frozenset()
    cached_board, cached = _SEALED_CACHE
    if cached_board is snapshot:
        return cached
    grids = snapshot.grids
    refused = {grid.position for grid in grids.values()
               if grid.object_count > 0 and not pile_fits(snapshot, grid.position)}
    exits: set = set()
    if refused:
        centres = {snapshot.player.position}
        for position in refused:
            for dy, dx in _OFFSETS:
                around = grids.get(Position(position.y + dy, position.x + dx))
                if around is not None and _entrance(around):
                    centres.add(around.position)
        for centre in centres:
            ways = []
            for dy, dx in _OFFSETS:
                cell = grids.get(Position(centre.y + dy, centre.x + dx))
                if (cell is None or not (cell.passable or cell.is_door)
                        or _entrance(cell)):
                    continue
                ways.append(cell.position)
            if ways and all(way in refused for way in ways):
                exits.update(ways)
    result = frozenset(exits)
    _SEALED_CACHE[0], _SEALED_CACHE[1] = snapshot, result
    return result


_OFFSETS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)


def _entrance(grid) -> bool:
    """A cell whose step enters a shop, building or dungeon rather than leading on."""
    return grid.store_number >= 0 or grid.building_special >= 0 or grid.has_entrance


def native_travel_fits(snapshot) -> bool:
    # Native travel can traverse several pickup tiles before the next board.
    return (not getattr(snapshot, "in_town", False)
            or permits(snapshot, sum(pile_slots(grid, snapshot)
                                     for grid in snapshot.grids.values())))


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
