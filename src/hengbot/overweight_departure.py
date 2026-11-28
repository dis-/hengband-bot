"""Leaving town over the weight limit when the weight relief has nothing legal left (MAINTAINABILITY.md 2).

Coordinator decision 2026-11-27 (under the owner's 2026-11-26 permission to change in-game
choices): an unmeetable "not over the weight limit" condition gives way.  n1-a life-545
(Amberite Rogue CL33) stopped in town 2026-11-27 10:28:49 under
``town:blocked:overweight-home-full-no-legal-relief`` at 164.6 lb of a 160.0 lb limit: 4.6 lb
over, which costs no speed at all in the game.

The game's facts (src of hengband):

* the limit: ``calc_weight_limit`` (player/player-status.cpp:2556-2563) is
  ``adj_str_wgt[STR] * 50`` tenths of a pound (x3/2 for the Berserker), ``_inventory_weight_limit``;
* the slowdown: ``calc_speed_bonus_by_weight`` (player-status/player-speed.cpp:43-51) is
  ``(weight - limit) / (limit / 5)`` over the limit (integer division): one speed for each fifth
  of the limit over it (32 lb at 160 lb), none for less (``angband_finale.slowdown``);
* the only other effect over the limit is drowning in deep water without levitation, swimming or
  water resistance (hpmp/hp-mp-processor.cpp:211-216), and navigation keeps off deep water
  whatever the player's state (``policy._is_avoidable_hazard_grid``: ``_damaging_terrain_ids``
  holds WATER + DEEP).

So the relief (Home deposit, then the sale or destruction of the unreserved surplus) runs first,
and when it has nothing legal left:

* a load whose slowdown is at most ``TOLERATED_SLOWDOWN`` departs (``give_way``);
* a heavier one sheds reserved quantities, the cheapest sale value per weight first, down to the
  tolerated weight (``shed_candidates``); what cannot be shed departs too (``give_way`` with
  ``force``): the excess is worn gear, which the equipment optimiser owns.

The same answer admits an equipment swap before it begins (``swap_departs``, read by
``equipment_swap_weight``): a swap whose load departs under this rule goes on, and one that would
not is dropped for the visit before anything is taken off.  n1-a life-545 2026-11-27 16:59: the
Home withdrawal of a 30.0 lb lance in place of a 25.0 lb axe was refused at 168.1 lb of a 165.0 lb
limit (no speed lost) after the axe was already deposited, and the visit re-entered Home for it
until livelock:exhausted.

The town end asks the same answer when the relief never opened (``relief_spent_key``, the last
rescue of the departure leaf ``inventory_weight_ready`` in departure_rescues).  n1-a life-545
2026-11-28 05:06: a Home withdrawal of four empty *Destruction* staffs (20.0 lb) took the pack to
181.4 lb of a 160.0 lb limit (no speed lost, the tolerated weight is 191.9 lb).  Every carried stack
was retained (the relief's route ``retained-only``), so no relief state was filed and ``give_way``
was never asked; the purchase deposit found no item held only by this visit's purchase, and the
visit stopped under town:blocked:survival:inventory_weight_ready.

The waiver holds for the rest of this town visit while the load stays within what it allowed;
``_inventory_overweight`` reads it (``limit``), so every town owner and the departure leaf
``inventory_weight_ready`` see one answer.  Every waiver is written to the overweight record
(``_overweight_surplus_record_path``) with its numbers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from hengbot.angband_finale import slowdown

# The speed the departing load may cost: none.  player-speed.cpp:43-51 takes one speed for each
# fifth of the limit over it, so this allows up to limit + limit/5 - 1 tenths of a pound
# (160.0 lb limit: up to 191.9 lb).  n1-a life-545 2026-11-27 was 4.6 lb over.
TOLERATED_SLOWDOWN = 0

# The waiver of this town visit: {"epoch", "weight", "allowed", "limit", "cause"} (state_registry).
NAME = "_overweight_departure_waiver"

# The Home route's own terminal for the weight (policy_town ``_town_claims_active``): the sale and
# the waiver answer after it, so neither is refused by it.
HOME_ROUTE_TERMINAL = "overweight-home-unreachable"


def tolerated_weight(limit: int) -> int:
    """The heaviest load whose slowdown is at most ``TOLERATED_SLOWDOWN`` (player-speed.cpp:49)."""
    return limit + (TOLERATED_SLOWDOWN + 1) * (limit // 5) - 1


# How much more slowdown than at the waiver the waived load may reach before the waiver lapses:
# none.  The waiver is a fact about the speed lost, so it holds while the load costs no more
# speed than when it was given (a ration eaten or one potion bought changes nothing the game
# counts) and lapses once it costs more (player-speed.cpp:43-51: one speed per fifth of the
# limit).  n1-a life-545 2026-11-28 09:34: the forced waiver at 198.4 lb (slowdown 1) allowed
# exactly 198.4 lb, so any later purchase would have voided it.
WAIVER_EXTRA_SLOWDOWN = 0


def waiver_weight(limit: int, weight: int) -> int:
    """The heaviest load the waiver given at ``weight`` keeps: the top of its slowdown step plus
    ``WAIVER_EXTRA_SLOWDOWN``, at least the tolerated weight."""
    step = max(TOLERATED_SLOWDOWN, slowdown(weight, limit)) + WAIVER_EXTRA_SLOWDOWN
    return limit + (step + 1) * (limit // 5) - 1


def tolerated(policy: Any, snapshot: Any) -> bool:
    """Whether the board's load costs at most ``TOLERATED_SLOWDOWN`` speed."""
    limit = policy._inventory_weight_limit(snapshot)
    return (limit is not None and limit >= 5
            and slowdown(policy._inventory_weight(snapshot), limit) <= TOLERATED_SLOWDOWN)


def waiver(policy: Any, snapshot: Any) -> dict | None:
    """This visit's waiver while the board's load stays within it, else None."""
    held = getattr(policy, NAME, None)
    if (not held or not snapshot.in_town
            or held.get("epoch") != getattr(policy, "_town_visit_epoch", None)
            or policy._inventory_weight(snapshot) > held.get("allowed", -1)):
        return None
    return held


def limit(policy: Any, snapshot: Any, current: int | None) -> int | None:
    """``current`` raised to the waiver's allowed weight (``_inventory_overweight``)."""
    held = None if current is None else waiver(policy, snapshot)
    return current if held is None else max(current, held["allowed"])


def give_way(policy: Any, snapshot: Any, cause: str, *, force: bool = False) -> bool:
    """Waive the weight for this visit when the load is tolerated (or ``force``); True if waived.

    The relief's state ends, and the Home route's terminal with it: the visit goes on to its
    ordinary departure.
    """
    raw = policy._inventory_weight_limit(snapshot)
    if raw is None or not snapshot.in_town or not (force or tolerated(policy, snapshot)):
        return False
    weight = policy._inventory_weight(snapshot)
    allowed = max(waiver_weight(raw, weight), weight)
    record = dict(time=datetime.now(timezone.utc).isoformat(),
                  reason="town:overweight-departure-waived", cause=cause, forced=force,
                  weight=weight, limit=raw, allowed=allowed,
                  slowdown=slowdown(weight, raw), visit_epoch=policy._town_visit_epoch)
    setattr(policy, NAME, {"epoch": policy._town_visit_epoch, "weight": weight,
                           "allowed": allowed, "limit": raw, "cause": cause})
    path = policy._overweight_surplus_record_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"<overweight-departure-waived> cause={cause} weight={weight} limit={raw} "
          f"allowed={allowed} forced={force}", flush=True)
    policy._overweight_surplus_disposal = None
    if policy._town_blocked_reason == HOME_ROUTE_TERMINAL:
        policy._town_blocked_reason = None
    return True


# The relief routes (policy_home ``_weight_relief_selection``) with nothing legal left for the
# weight: every carried item retained, or Home's deposits unreachable and the surplus short.
SPENT_ROUTES = frozenset({"retained-only", "home-unreachable"})
# The routes the relief's sale answers itself (it gives way inside when nothing legal is left).
SALE_ROUTES = frozenset({"sell-or-destroy"})


def relief_spent_key(policy: Any, snapshot: Any, cause: str = "town-end-relief-spent") -> str | None:
    """The weight's answer once Home and the purchase deposit gave the town nothing: the town
    end's last rescue of ``inventory_weight_ready`` (departure_rescues ``overweight-give-way``)
    and Home's spent route (town_terminal ``overweight_home_key``).

    A sellable surplus is the relief's sale (``_overweight_surplus_sale_key``, its state filed
    here when no owner filed one).  A route with nothing legal left (``SPENT_ROUTES``) gives way
    at once when the load is tolerated (``give_way``); a heavier load goes to the same sale, which
    sheds reserved quantities (``shed_candidates``) or, with nothing to shed, gives way with
    ``force``.  Another route (a deposit, Home's relief, an owner still taking items) is that
    owner's: None.  None also when the load is within the limit or the waiver was given (the
    caller reads the leaf again); else the relief's key.
    """
    if not snapshot.in_town or not policy._inventory_overweight(snapshot):
        return None
    route = policy._weight_relief_selection(snapshot).route
    if route not in SALE_ROUTES | SPENT_ROUTES:
        return None
    if route in SPENT_ROUTES and give_way(policy, snapshot, cause):
        return None
    if policy._overweight_surplus_disposal is None:
        policy._overweight_surplus_disposal = {"town": policy._effective_town_id(snapshot)}
    return policy._town_producer_entry(
        "_overweight_surplus_sale_key", lambda: policy._overweight_surplus_sale_key(snapshot),
        family="shop-sell")


def sale_uncomposed(key: str | None) -> bool:
    """Whether the relief's in-store sale composed no key (None or the empty ``""`` of
    ``_batch_sell_key``): the relief then gives way with ``force`` and leaves the page, so no
    empty key reaches the driver (n1-a life-545 2026-11-28 08:43, no-key-exhausted)."""
    return not key


def shed_candidates(policy: Any, snapshot: Any, chosen: list, *, extra: int = 0) -> list:
    """Reserved quantities to shed after ``chosen`` (the relief's surplus rows), cheapest first.

    Rows in the relief's shape (value, signature, item, count, stores).  Kept out: artifacts,
    the rows ``chosen`` already sheds, the copy of a book the character casts from
    (``realm_spell_book.retained_count``), and any count whose removal leaves a departure supply
    short (``_carried_disposal_preserves_departure``, the relief's own test).  The order is the sale
    value per tenth of a pound, cheapest first; the counts stop at the tolerated weight.
    ``extra`` is weight a planned change adds to the board's load (``swap_departs``).
    """
    from hengbot import realm_spell_book
    from hengbot.baseitem_knowledge import item_base_cost
    from hengbot.model import (STORE_ALCHEMIST, STORE_ARMOURY, STORE_BLACK, STORE_GENERAL,
                               STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON)
    from hengbot.store_sale import known_sale_value
    raw = policy._inventory_weight_limit(snapshot)
    if raw is None:
        return []
    need = (policy._inventory_weight(snapshot) + extra - tolerated_weight(raw)
            - sum(entry[2].weight * entry[3] for entry in chosen))
    taken = {entry[2].slot for entry in chosen}
    rows = []
    for item in snapshot.inventory:
        if item.slot in taken or item.weight <= 0 or item.count <= 0 or item.is_artifact:
            continue
        value = max(0, known_sale_value(item, item_base_cost(item, policy._baseitem_costs)) or 0)
        spare = item.count - realm_spell_book.retained_count(policy, snapshot, item)
        if spare > 0:
            rows.append((value / item.weight, item, value, spare))
    shed = []
    for _, item, value, spare in sorted(rows, key=lambda row: (row[0], row[1].slot)):
        if need <= 0:
            break
        count = min(spare, -(-need // item.weight))
        if not policy._carried_disposal_preserves_departure(snapshot, item, count):
            continue
        stores = tuple(store for store in (STORE_ALCHEMIST, STORE_MAGIC, STORE_WEAPON,
                       STORE_ARMOURY, STORE_GENERAL, STORE_TEMPLE, 8, STORE_BLACK)
                       if policy._store_accepts_sale(store, item)
                       and store not in policy._store_sale_refused)
        shed.append((value * count, policy._item_signature(item), item, count, stores))
        need -= item.weight * count
    return shed


def swap_departs(policy: Any, snapshot: Any, load: int, chosen: list) -> bool:
    """Whether ``load`` (this board's load after a planned change, ``chosen`` shed) departs.

    ``chosen`` holds the rows the change already leaves behind (the relief's shape); ``load`` is
    the board's weight less them plus what the change adds.  The load departs when it is within
    the tolerated weight once ``shed_candidates`` sheds what it may: the relief sheds exactly that
    after the change, and gives way at the tolerated weight (``give_way``).
    """
    raw = policy._inventory_weight_limit(snapshot)
    if raw is None:
        return True
    if load <= tolerated_weight(raw):
        return True
    remaining = policy._inventory_weight(snapshot) - sum(
        entry[2].weight * entry[3] for entry in chosen)
    shed = shed_candidates(policy, snapshot, chosen, extra=load - remaining)
    return load - sum(entry[2].weight * entry[3] for entry in shed) <= tolerated_weight(raw)
