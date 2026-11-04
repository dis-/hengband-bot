"""Buying the gear a destination's depth requirement is missing.

Owner 2026-11-04, 「深さの条件に足りない耐性の装備が店にあって買える時は、
買いますか？」 「買えるなら買う」: gear with the missing resistance on a shelf
that can be bought while leaving the money for survival items is bought and
worn; the bought item is chosen by the current equipment comparison.  n1-a
life-476 2026-11-04 07:22: resist_fire missing for Angband 20F, 144025 gold and
火炎の指輪 {r火} at 30145 on the Black Market shelf.

The tables are the existing ones, so a new requirement or a new flag needs
nothing here:
 * what is missing: ``_missing_required_abilities`` at the planned landing
   (DEPTH_ABILITY_REQUIREMENTS);
 * what a shelf row closes: the flags the game displays for it (``known_flags``)
   read through RESIST_FLAG_BY_ABILITY.  A gate no worn flag answers
   (*Destruction*, speed) has no row in that table and no shelf answers it.

Only pages the bot has seen this town visit are read
(``_current_town_supplier_page``).  The budget is the survival reservation of
the required purchases (``_required_departure_supply_reserve``, the quest's
carry excluded, as me_staff_sequence and q2_tower_recharge read it); an unknown
price buys nothing.  Wearing belongs to the equipment transaction and its
comparison, which needs the calibration: nothing is bought without it.

Each row is judged once.  A bought row is never bought again, whatever became
of it.  While a bought source of an ability is still owned, whether or not the
comparison wore it, that ability buys nothing more; the town end then answers
the gap as it does without a shelf (``town_terminal``).
"""

from __future__ import annotations

from hengbot.equipment_class_profile import EQUIPMENT_CLASS_PROFILES
from hengbot.model import STORE_HOME
from hengbot.policy_constants import RESIST_FLAG_BY_ABILITY
from hengbot.town_pack_budget import room_assumed

_BOUGHT = "_ability_gear_bought"


def _identity(name: str, tval: int, sval: int) -> tuple[str, int, int]:
    from hengbot.policy_instore import shelf_item_name

    return (shelf_item_name(name), tval, sval)


def _bought(policy) -> set[tuple[str, int, int]]:
    """Rows this owner bought; restored checkpoints older than it have none."""
    return vars(policy).setdefault(_BOUGHT, set())


def note_bought(policy, snapshot, store: int, signature: tuple) -> None:
    """A confirmed purchase whose shelf row closes an open ability is judged.

    The page is the one the purchase was made from: the row is read before this
    decision's own observation replaces it, and a carried name can differ.
    """
    page = policy._town_supplier_stock.get(store)
    row = next((row for row in getattr(page, "items", ())
                if policy._item_signature(row) == signature), None)
    if (row is not None and row.is_equipment and row.known_flags
            and row.known_flags & _open_flags(policy, snapshot)):
        _bought(policy).add(_identity(*signature[:3]))


def _bought_kinds(policy) -> frozenset[tuple[int, int]]:
    return frozenset(identity[1:] for identity in _bought(policy))


def _open_flags(policy, snapshot) -> frozenset[int]:
    """The flags that would close an ability the landing is missing."""
    missing = policy._missing_required_abilities(
        snapshot, policy._equipment_departure_destination_depth(snapshot))
    flags = {RESIST_FLAG_BY_ABILITY[ability] for ability in missing
             if ability in RESIST_FLAG_BY_ABILITY}
    kinds = _bought_kinds(policy)
    if flags and kinds:
        flags -= {flag for owned in policy._equipment_catalog.items
                  if (owned.item.tval, owned.item.sval) in kinds
                  for flag in owned.flags}
    return frozenset(flags)


def _may_buy(policy, snapshot) -> bool:
    """The comparison that wears the item can run for this character."""
    return (snapshot.player.class_id in EQUIPMENT_CLASS_PROFILES
            and getattr(policy, "_character_calibration", None) is not None)


def _rows(policy, snapshot, page, flags: frozenset[int]) -> list:
    """This page's rows closing an open flag, paid above the reservation."""
    reserve = policy._required_departure_supply_reserve(snapshot, quest_carry=False)
    if reserve is None:
        return []
    bought = _bought(policy)
    return [row for row in page.items
            if row.is_equipment and row.price > 0 and row.count > 0
            and not row.is_cursed and not row.is_broken
            and row.known_flags & flags
            and snapshot.player.gold - row.price >= reserve
            and _identity(row.name, row.tval, row.sval) not in bought]


def _cheapest(policy, snapshot) -> tuple[int, object] | None:
    """(store, row) of the cheapest closing row on this visit's seen pages."""
    if not _may_buy(policy, snapshot):
        return None
    flags = _open_flags(policy, snapshot)
    if not flags:
        return None
    stores = set(policy._town_supplier_stock)
    if snapshot.store is not None:
        stores.add(snapshot.store.store_type)
    refused = policy._town_visit_ledger.nonhome_attempted_without_effect
    found = []
    for store in sorted(stores - {STORE_HOME}):
        page = policy._current_town_supplier_page(snapshot, store)
        if page is None or store in refused:
            continue
        found.extend((row.price, store, row) for row in _rows(policy, snapshot, page, flags))
    if not found:
        return None
    _price, store, row = min(found, key=lambda entry: entry[:2])
    return store, row


def purchase(policy, snapshot):
    """The open page's row to buy now, or None."""
    if snapshot.store is None:
        return None
    chosen = _cheapest(policy, snapshot)
    if chosen is None or chosen[0] != snapshot.store.store_type:
        return None
    return chosen[1]


def rung_matches(policy, snapshot, item) -> bool:
    return (item.is_equipment and bool(item.known_flags)
            and item == purchase(policy, snapshot))


def supplier_store(policy, snapshot) -> int | None:
    """The seen store worth walking to: its purchase would pass the buy order."""
    chosen = _cheapest(policy, snapshot)
    if chosen is None:
        return None
    store, row = chosen
    if room_assumed() or policy._store_purchase_fits_pack(snapshot, row):
        if snapshot.player.gold - row.price >= policy._fundraising_kit_reserve(snapshot):
            return store
    return None
