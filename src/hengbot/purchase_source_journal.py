"""Which selector answered each shop purchase: the rungs table or the legacy order (record only).

Whole-bot maintainability review 2026-11-23 (b)-6: the shop's ordinary order
(``policy_shop._legacy_next_purchase_unreserved``, 524 lines) and the purchase rungs table
(``purchase_rungs`` / ``policy_shop._purchase_rungs``, equipment review E6) answer the same
question twice.  Owner 2026-11-23 (verbatim) 「数を見てから一本化する」: before either is
removed, count which one actually decides the buys.  This module adds no rule and changes no
key; it writes one row per composed shop purchase to a small rotation-bounded jsonl beside the
decision log (``purchase-source.jsonl``), and ``scripts/legacy_purchase_report.py`` sums the
rows of the server's bots.

A row's ``source`` says who chose the ware:

- ``rungs``: the departure's required buy on the page (``_departure_blocking_page_purchase``),
  chosen by walking the rungs table;
- ``legacy``: the ordinary order (``_next_purchase`` -> ``_legacy_next_purchase_unreserved``,
  with its short-money tier pass);
- ``bm-priority`` / ``opening-q1`` / ``zul-trip`` / ``me-staff``: ``_next_purchase``'s errands
  that own their page before the ordinary order (each has one rung of the table too);
- ``survival``: the hungry character's food buy (``_shop_core``'s survival branch).

With it: the rungs the ware closes (``rungs``, as ``_matching_live_purchase_rungs`` reads them, and
``rungs_unfiltered``, before its absorbed-power and surplus filter; both empty = no rung of the
table wants it, a buy only the legacy order makes), the first one's category and tier, and for
every source but ``rungs`` what the table alone would have bought on the same page (``table``:
each rung's first affordable ware that fits the pack, then the short-money tier rule, as the
departure's required buy picks, without its town-need filter) and whether it is the same ware
(``table_agrees``).  An errand's ware the absorbed powers keep from the ordinary candidates
(the Magic-Eater staff sequence) has no table answer.

The table's answer is read inside the in-store pure scope (every policy attribute rebinding is
put back), and any failure of the record is printed, never raised: the key is the one the
selector composed either way.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from hengbot.flight_recorder import jsonable, rotate_log
from hengbot.purchase_rungs import PurchaseContext, purchase_rung_tier, short_money_choice

# The branch ``_next_purchase`` answered from (the last call's; read by ``_shop_purchase_key``).
STATE = "_purchase_source_branch"
PATH = "_purchase_source_journal_path"
FILE_NAME = "purchase-source.jsonl"
ROTATE_BYTES = 8 * 1024 ** 2
GENERATIONS = 3

RUNGS = "rungs"
LEGACY = "legacy"
BM_PRIORITY = "bm-priority"
OPENING_Q1 = "opening-q1"
ZUL_TRIP = "zul-trip"
ME_STAFF = "me-staff"
SURVIVAL = "survival"
SOURCES = (RUNGS, LEGACY, BM_PRIORITY, OPENING_Q1, ZUL_TRIP, ME_STAFF, SURVIVAL)


def note_branch(policy: Any, branch: str) -> None:
    """``_next_purchase`` is answering from ``branch`` (one of ``SOURCES``)."""
    setattr(policy, STATE, branch)


def _ware(item: Any) -> dict | None:
    if item is None:
        return None
    return {"letter": getattr(item, "letter", None), "name": getattr(item, "name", None),
            "tval": getattr(item, "tval", None), "sval": getattr(item, "sval", None),
            "price": getattr(item, "price", None), "count": getattr(item, "count", None)}


def _same_ware(left: Any, right: Any) -> bool:
    return (left is not None and right is not None
            and (left.letter, left.tval, left.sval, left.name)
            == (right.letter, right.tval, right.sval, right.name))


def table_pick(policy: Any, snapshot: Any):
    """(ware, rung id, tier) the rungs table alone buys on this page, or None.

    Each rung's first ware it matches that is not a sell-rebuy, that the absorbed powers do not
    refuse, whose quantity the shelf holds, that the gold pays and the pack takes; then the
    short-money tier rule over those firsts (``_departure_blocking_page_purchase_pure`` without
    its town-need filter, its errand deferral and its Home gate)."""
    store = snapshot.store
    if store is None:
        return None
    context = PurchaseContext(snapshot)
    firsts = []
    for rung in policy._purchase_rungs(context):
        for item in store.items:
            if rung.match(context, item) is None:
                continue
            if (policy._purchase_churn_rejected(store.store_type, item)
                    or policy._absorbed_power_refuses_purchase(snapshot, item)):
                continue
            quantity = policy._purchase_quantity(snapshot, item)
            if quantity < 1 or quantity > item.count:
                continue
            if item.price * quantity > snapshot.player.gold:
                continue
            if not policy._store_purchase_fits_pack(snapshot, item):
                continue
            firsts.append(((item, rung.rung_id, rung.tier), item.price * quantity, rung.tier))
            break
    return short_money_choice(firsts, snapshot.player.gold)


def _row(policy: Any, snapshot: Any, item: Any, match: Any, source: str,
         quantity: int | None, key: str) -> dict:
    with policy._in_store_pure_scope():
        matches = policy._matching_live_purchase_rungs(snapshot, item)
        context = PurchaseContext(snapshot)
        unfiltered = [rung.rung_id for rung in policy._purchase_rungs(context)
                      if rung.match(context, item) is not None]
        table = None if source == RUNGS else table_pick(policy, snapshot)
        depth = policy._planned_depth()
    first = match if match is not None else (matches[0] if matches else None)
    rung_id = getattr(first, "rung_id", None)
    player = snapshot.player
    row = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "decision": getattr(policy, "_decision_sequence", None),
        "epoch": getattr(policy, "_town_visit_epoch", None),
        "turn": getattr(snapshot, "turn", None),
        "store": snapshot.store.store_type if snapshot.store is not None else None,
        "gold": getattr(player, "gold", None),
        "class_id": getattr(player, "class_id", None),
        "level": getattr(player, "level", None),
        "planned_depth": depth,
        "source": source,
        "key": key,
        "ware": _ware(item),
        "quantity": quantity,
        "rung": rung_id,
        "category": getattr(first, "category", None),
        "tier": purchase_rung_tier(rung_id) if rung_id is not None else None,
        "rungs": [m.rung_id for m in matches],
        # Before the absorbed-power and surplus filter of _matching_live_purchase_rungs.
        "rungs_unfiltered": unfiltered,
    }
    if source != RUNGS:
        row["table"] = None if table is None else {
            **_ware(table[0]), "rung": table[1], "tier": table[2]}
        row["table_agrees"] = table is not None and _same_ware(table[0], item)
    return jsonable(row)


def _write(policy: Any, row: dict) -> None:
    path = getattr(policy, PATH, None)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rotate_log(path, ROTATE_BYTES, GENERATIONS)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"purchase-source-journal write failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)


def record(policy: Any, snapshot: Any, item: Any, key: str | None, *, source: str | None = None,
           match: Any = None, quantity: int | None = None) -> None:
    """One row for the composed buy ``key`` of ``item`` (no row without the journal's path).

    ``source`` None: the branch ``_next_purchase`` last answered from (``STATE``)."""
    if not key or item is None or getattr(policy, PATH, None) is None:
        return
    try:
        if source is None:
            source = getattr(policy, STATE, None) or LEGACY
        row = _row(policy, snapshot, item, match, source, quantity, key)
    except Exception as exc:  # record only: the composed key stands
        print(f"purchase-source-journal row failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return
    _write(policy, row)
