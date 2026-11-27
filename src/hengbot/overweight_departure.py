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
    allowed = max(tolerated_weight(raw), weight)
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
    policy._overweight_surplus_disposal = None
    if policy._town_blocked_reason == HOME_ROUTE_TERMINAL:
        policy._town_blocked_reason = None
    return True


def shed_candidates(policy: Any, snapshot: Any, chosen: list) -> list:
    """Reserved quantities to shed after ``chosen`` (the relief's surplus rows), cheapest first.

    Rows in the relief's shape (value, signature, item, count, stores).  Kept out: artifacts,
    the rows ``chosen`` already sheds, the copy of a book the character casts from
    (``realm_spell_book.retained_count``), and any count whose removal leaves a departure supply
    short (``_carried_disposal_preserves_departure``, the relief's own test).  The order is the sale
    value per tenth of a pound, cheapest first; the counts stop at the tolerated weight.
    """
    from hengbot import realm_spell_book
    from hengbot.baseitem_knowledge import item_base_cost
    from hengbot.model import (STORE_ALCHEMIST, STORE_ARMOURY, STORE_BLACK, STORE_GENERAL,
                               STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON)
    from hengbot.store_sale import known_sale_value
    raw = policy._inventory_weight_limit(snapshot)
    if raw is None:
        return []
    need = (policy._inventory_weight(snapshot) - tolerated_weight(raw)
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
