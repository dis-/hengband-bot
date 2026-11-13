"""The rescue registry of the departure leaves (town rebuild stage 2, owner 2026-11-12).

Owner 2026-11-12 「1〜3まで一気に進める」, stage 2 「落ちた葉には必ず救済の手」:
every leaf of the departure gates -- the ordinary gate
(``_town_departure_conjuncts``), the recall gate on top of it
(``_recall_town_departure_conjuncts``), the forced departure's minimum
(``_departure_minimum``) and the repetition remedy's blocked recall
(``town_terminal.gather_blocked_recall``) -- has one row here: the rescue
actions that may still answer it at the town end, in order, and the named stop
the visit ends under when none does.

Before this table the town end (``town_terminal.town_end_key``) answered a
failed leaf only when it was a purchase gap (one mining cycle) and otherwise
named the stop: a leaf no owner served there stopped the town even when a
rescue the owner rules allow was still open (n1-c life-203/205: Recall short,
the Temple never asked; n1-c life-202: the pack overweight with a sellable
surplus; n1-a life-512: Identify staff charges with another supplier
unvisited, a Home withdrawal never settled).

The rescues are the owner rules' remedies, each an existing owner's own key:

``supplier-visit``   ask a supplier of the leaf's short supply that this visit has
                     not tried (Home first when it holds the supply, then the
                     stores the readiness table names) -- the store router's
                     approach, as ``overweight_home_key`` re-arms Home;
``cross-town``       buy it in another town (``_cross_town_shopping_key``);
``stockout-mining``  one mining run when no supplier serves it
                     (``_supply_stockout_mining_key``, at most three);
``overweight-sale``  sell the overweight surplus (``_overweight_surplus_sale_key``);
``home-settle``      walk back to Home to settle a pending Home transfer;
``rest``             rest off HP, mana and a temporary status.

Each action starts at most ``ATTEMPTS_PER_VISIT`` times per leaf in a visit
(an attempt runs on consecutive decisions, ``STEPS_PER_ATTEMPT`` at most), so
a rescue that does not help still ends at the named stop.  A purchase gap
keeps its own answer (the town end's mining cycle) before any of these.

scripts/departure_rescue_lint.py reads every leaf the gates can return and
fails on one this table does not know, on an unknown action, and on a row with
neither an action nor a stop reason (0 gaps).
"""
from __future__ import annotations

from typing import Any, Callable, NamedTuple

from hengbot.model import SV_STAFF_IDENTIFY, STORE_BLACK, STORE_HOME, STORE_MAGIC, TVAL_STAFF

ATTEMPTS_PER_VISIT = 2
# Decisions one attempt may run on consecutive boards (a walk across town).
STEPS_PER_ATTEMPT = 200


class Rescue(NamedTuple):
    """A departure leaf's rescue actions (in order) and its named stop."""

    actions: tuple[str, ...]
    # Why the leaf has no action (a stop-only row); "" when it has actions.
    stop_only: str = ""


_SUPPLY = Rescue(("supplier-visit", "cross-town", "stockout-mining"))
_HOME_SETTLE = Rescue(("home-settle",))
_REST = Rescue(("rest",))

RESCUES: dict[str, Rescue] = {
    # Supplies (departure_readiness): another supplier, another town, mining.
    "recall_departure_ready": _SUPPLY,
    "food_ready": _SUPPLY,
    "light_ready": _SUPPLY,
    "teleport_ready": _SUPPLY,
    "cure_critical_ready": _SUPPLY,
    "remove_curse_ready": _SUPPLY,
    "identify_staff_ready": Rescue(("supplier-visit", "cross-town")),
    # Weight: Home's deposit answers first (overweight_home_key); then the sale.
    "inventory_weight_ready": Rescue(("overweight-sale",)),
    # A pending Home withdrawal: walk back to Home while Home was not tried
    # this visit (its executor settles it there).
    "home_atomic_withdraw_clear": _HOME_SETTLE,
    "departure_home_atomic_withdraw_clear": _HOME_SETTLE,
    "home_pending_item_clear": _HOME_SETTLE,
    "departure_home_pending_item_clear": _HOME_SETTLE,
    "home_pending_batch_clear": _HOME_SETTLE,
    "departure_home_pending_batch_clear": _HOME_SETTLE,
    "home_batch_review_clear": Rescue((), "the Home batch review settles on the Home page; a review that outlives the visit is the town plan's (stage 3)"),
    "departure_home_batch_review_clear": Rescue((), "the Home batch review settles on the Home page; a review that outlives the visit is the town plan's (stage 3)"),
    "home_candidate_resolved": Rescue((), "identification_wait.release answers it before the stop (owner 2026-11-03: depart with the worn gear when this visit cannot identify)"),
    "digger_withdrawal_resolved": Rescue((), "the digger's Home take is bounded by its own fallback buy (_digger_buy_fallback_available)"),
    # Survival: rest in town.
    "hp_full": _REST,
    "mp_full": _REST,
    "temporary_status_clear": _REST,
    # Named stops: the owner that serves the leaf has already answered before
    # the town end, or the leaf is a defect no town action repairs.
    "free_pack_slots_ready": Rescue((), "the space owners (Home deposit, sale, destroy) answer before the town end"),
    "organization_complete": Rescue((), "the organization sale answers before the town end"),
    "spare_gear_stowed": Rescue((), "never stops a visit (gather_town_end drops it)"),
    "quest_carry_ready": Rescue((), "always ready: the quest-entry contract owns quest carry"),
    # Owner 2026-11-13 「足さない」: a stop-only leaf whose owner did not answer
    # (n1-c life-205 06:49, the Home catalogue check left in flight) gets no
    # re-sent check as a rescue; it keeps its named stop until stage 3 rebuilds
    # the owners' flow.
    "equipment_departure_ready": Rescue((), "the equipment transaction owns it; its exhaustion is a named stop"),
    "combat_weapon_ready": Rescue((), "the equipment transaction owns it; its exhaustion is a named stop"),
    "teleport_items_safe": Rescue((), "the equipment transaction owns it; its exhaustion is a named stop"),
    "home_catalog_ready": Rescue((), "the Home scan owns it; an unroutable Home defers it"),
    "identification_need_clear": Rescue((), "the identification owner answers before the town end"),
    "departure_identification_need_clear": Rescue((), "the identification owner answers before the town end"),
    "depth_abilities": Rescue((), "the no-safe-destination fundraising answers it (owner 2026-10-19)"),
    "equipment_observed": Rescue((), "a board defect: the equipment channel was not observed"),
    "store_transfer_clear": Rescue((), "an in-flight store transfer settles on its own board"),
    "equipment_transfer_clear": Rescue((), "an in-flight equipment transfer settles on its own board"),
}

SUPPLY_LEAVES_STORES = {"identify_staff_ready": (STORE_MAGIC, STORE_BLACK)}


def _attempted(policy: Any, leaf: str, action: str) -> bool:
    """Charge ``action`` for ``leaf`` this visit; True when its budget is spent.

    A rescue answered on the previous decision continues (an approach takes
    one step per decision) and costs no new attempt, up to
    ``STEPS_PER_ATTEMPT`` decisions; any other call starts a new attempt.
    """
    epoch = getattr(policy, "_town_visit_epoch", None)
    attempts = {key: value for key, value
                in (getattr(policy, "_departure_rescue_attempts", None) or {}).items()
                if key[0] == epoch}
    key = (epoch, leaf, action)
    sequence = getattr(policy, "_decision_sequence", 0)
    starts, last, steps = attempts.get(key, (0, None, 0))
    if last is not None and sequence - last <= 1 and steps < STEPS_PER_ATTEMPT:
        attempts[key] = (starts, sequence, steps + 1)
    elif starts >= ATTEMPTS_PER_VISIT:
        policy._departure_rescue_attempts = attempts
        return True
    else:
        attempts[key] = (starts + 1, sequence, 1)
    policy._departure_rescue_attempts = attempts
    return False


def _unanswered(policy: Any, leaf: str, action: str) -> None:
    """An action that gave no key is no running rescue: the next call starts anew."""
    epoch = getattr(policy, "_town_visit_epoch", None)
    attempts = getattr(policy, "_departure_rescue_attempts", None) or {}
    key = (epoch, leaf, action)
    if key in attempts:
        starts, _last, steps = attempts[key]
        attempts[key] = (starts, None, steps)


def _approach(policy: Any, board: Any, store: int) -> str | None:
    """Re-arm ``store`` and take the store router's approach step toward it."""
    policy._rearm_town_store_for_new_work(store, release_visit_bound=True)
    if store in policy._town_store_attempted:
        return None
    step = policy._shopping_approach_step(board, store, router_plan_stop=True)
    if step is None:
        return None
    key = policy._shopping_approach_key(board, step, "shop:travel")
    if key is not None:
        # The router's own reason (shop:travel) keeps its progress class.
        if not policy.last_reason:
            policy.last_reason = "shop:travel"
        policy._record_shop_selector_diagnostics(board, key)
    return key


def _supplier_stores(policy: Any, board: Any, leaf: str) -> list[int]:
    """The suppliers of ``leaf``'s short supply this visit has not tried."""
    from hengbot.departure_readiness import readiness_table
    from hengbot.town_terminal import SUPPLY_KIND_BY_CATEGORY
    if leaf in SUPPLY_LEAVES_STORES:
        stores = list(SUPPLY_LEAVES_STORES[leaf])
        categories = {store: "identify-staff" for store in stores}
        kinds: dict[int, str | None] = {store: None for store in stores}
    else:
        ledger = policy._supply_ledger(board, policy._planned_depth())
        stores, categories, kinds = [], {}, {}
        for kind in readiness_table(policy, board).leaf_kinds(leaf):
            status = ledger.get(kind)
            if status is None or status.count >= status.required_departure:
                continue
            if policy._supply_purchase_gap(board, kind):
                # Priced above the gold or out of stock everywhere: the town
                # end's mining cycle answers it, not another walk.
                continue
            category = next((each for each, value in SUPPLY_KIND_BY_CATEGORY.items()
                             if value == kind), kind)
            for store in status.stores:
                if store not in stores:
                    stores.append(store)
                    categories[store] = category
                    kinds[store] = kind
    return [store for store in stores
            if not policy._shelf_stop_tried(board, store, categories[store])
            and _store_may_supply(policy, board, leaf, store, kinds.get(store))]


def _store_may_supply(policy: Any, board: Any, leaf: str, store: int, kind: str | None) -> bool:
    """The ledger's own obtainability of one store: unseen, or a seen page
    that offers the ware within the gold (``_supply_store_obtainable``)."""
    if store == STORE_HOME:
        return True
    if kind is None:  # an Identify staff store: a seen shelf with an affordable staff
        pages = {page.store_type: page for page in policy._identify_staff_offer_pages(board)}
        page = pages.get(store)
        return page is None or any(
            item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
            and item.price <= board.player.gold for item in page.items)
    return policy._supply_store_obtainable(board, kind, (store,))


def _supplier_visit(policy: Any, board: Any, leaf: str) -> str | None:
    for store in _supplier_stores(policy, board, leaf):
        key = _approach(policy, board, store)
        if key is not None:
            return key
    return None


def _cross_town(policy: Any, board: Any, leaf: str) -> str | None:
    return policy._cross_town_shopping_key(board)


def _stockout_mining(policy: Any, board: Any, leaf: str) -> str | None:
    return policy._supply_stockout_mining_key(board)


def _overweight_sale(policy: Any, board: Any, leaf: str) -> str | None:
    if not policy._inventory_overweight(board):
        return None
    return policy._overweight_surplus_sale_key(board)


def _home_settle(policy: Any, board: Any, leaf: str) -> str | None:
    if not policy._home_available(board) or STORE_HOME in policy._town_store_attempted:
        return None
    return _approach(policy, board, STORE_HOME)


def _rest(policy: Any, board: Any, leaf: str) -> str | None:
    from hengbot.policy_constants import REST_MACRO
    player = board.player
    if player.food_state not in {"normal", "full", "gorged"}:
        return None
    policy.last_reason = "town:recover"
    policy._offer_execution(
        REST_MACRO, producer="survival", work_id="town:recover",
        next_step="player.rest", expected_effect="hp/mp/status-recovered")
    return REST_MACRO


ACTIONS: dict[str, Callable[[Any, Any, str], str | None]] = {
    "supplier-visit": _supplier_visit,
    "cross-town": _cross_town,
    "stockout-mining": _stockout_mining,
    "overweight-sale": _overweight_sale,
    "home-settle": _home_settle,
    "rest": _rest,
}


def rescue_key(policy: Any, board: Any, leaves: tuple[str, ...]) -> str | None:
    """The first rescue that answers one of the failed ``leaves``, or None.

    Read where the town end would name its stop: each leaf's actions in the
    registry's order, each at most ``ATTEMPTS_PER_VISIT`` times in a visit.
    """
    if board.store is not None or board.player.recalling:
        return None
    for leaf in leaves:
        for action in RESCUES.get(leaf, Rescue(())).actions:
            if _attempted(policy, leaf, action):
                continue
            key = ACTIONS[action](policy, board, leaf)
            if key is not None:
                policy._departure_rescue_last = (leaf, action)
                print(f"<departure-rescue> leaf={leaf} action={action} reason={policy.last_reason}",
                      flush=True)
                return key
            _unanswered(policy, leaf, action)
    return None
