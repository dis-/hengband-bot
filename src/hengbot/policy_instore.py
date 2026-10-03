"""In-store shop operations and shelf evidence.

SOL-DESIGN-store-reentry-20261003 (revision 2), user decisions 2026-10-03:
「入り直しの仕組みも含めて見直す」 / final spec 「承認・自宅も段階2で変える」.

Part A (IST, section 3.1): on an ordinary shop's observed page the bot buys,
sells or inscribes right there, one operation per barrier board, instead of
observing, leaving and composing a one-shot outside.  Every operation is
selected from the board the executor observed now: the letter is that board's
emitted row, the executor's slot-by-slot screen check passed for that board,
and the page is page one.  Anything else falls back to the existing
observe-and-leave path unchanged.

Part B (section 3.3): an ordinary shop's shelf, observed while the game cannot
have restocked it, proves a planned stop fruitless; the stop is not added.

Phase 0 (section 3.6) runs both parts as a log-only shadow with pure
selectors (section 3.0); Phase 1 acts behind ``--in-store-shop-ops``.
Home (Phase 2) is not part of this module.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import re
import time

from hengbot.model import Snapshot, StoreState, TVAL_WAND
from hengbot.policy_constants import (
    BUY_KEY,
    IN_STORE_BREAKER_REASON_PREFIX,
    IN_STORE_BUY_REASON,
    IN_STORE_DONE_REASON,
    IN_STORE_INSCRIBE_REASON,
    IN_STORE_OPERATION_REASONS,
    IN_STORE_SELL_REASON,
    LEAVE_STORE_KEY,
    SELL_KEY,
    STORE_HOME,
    STORE_MAINTENANCE_INTERVAL_TURNS,
    STORE_RETRY_TURNS,
    STORE_STUCK_LIMIT,
)
from hengbot.policy_types import ProcurementHomeGate, StoreVisitPhase


_INSCRIPTION = re.compile(r"\s*\{[^{}]*\}")


def shelf_item_name(name: str) -> str:
    """The emitted name without inscriptions (owner change: {売出中}, discounts)."""
    return _INSCRIPTION.sub("", name).strip()


def shelf_signature(store: StoreState) -> tuple[tuple[str, int, int, int], ...]:
    """Design 3.3.1: page-one stock without price and inscription."""
    return tuple(sorted(
        (shelf_item_name(item.name), item.tval, item.sval, item.count)
        for item in store.items
    ))


def _row_identity(item) -> tuple:
    return (item.name, item.tval, item.sval, item.count, item.price,
            getattr(item, "charges", 0))


def expected_buy_confirmation(price: int, quantity: int, *, wand_stack: bool) -> str | None:
    """purchase-order.cpp prompt_to_buy: price x amount; None for a wand stack."""
    if wand_stack:
        return None
    return f"買値 ${price * quantity} で買いますか？[Y/n]"


class InStoreMixin:
    """Section 3 of SOL-DESIGN-store-reentry-20261003 (Phase 0 and Phase 1)."""

    # ------------------------------------------------------------ switches
    def observe_store_screen(self, verified: bool | None) -> None:
        """CLI: whether the executor's screen shows this board's page slot by slot.

        ``input_executor._store_page_is_on_screen`` on the ready screen and the
        ready board's store record (design 3.1 condition 3); ``None`` when the
        decision board did not come from the executor's barrier.
        """
        self._in_store_screen_verified = verified

    def _in_store_ops_active(self) -> bool:
        return bool(getattr(self, "_in_store_ops_enabled", False)) and (
            getattr(self, "_in_store_breaker", None) is None
        )

    def load_in_store_breaker(self, path: Path | None) -> dict | None:
        """CLI start: a tripped breaker stays off until a human removes the file."""
        self._in_store_breaker_path = path
        if path is None or not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = {"cause": "unreadable-breaker-file"}
        if not isinstance(record, dict):
            record = {"cause": "unreadable-breaker-file"}
        self._in_store_breaker = (
            str(record.get("cause", "unknown")),
            record.get("decision_sequence"),
        )
        return record

    def trip_in_store_breaker(self, cause: str) -> dict:
        """Disable IST for this process and every restart (design 3.1, Q4/Q5)."""
        record = {
            "cause": cause,
            "decision_sequence": self._decision_sequence,
            "time": datetime.now().astimezone().isoformat(),
            "reason": IN_STORE_BREAKER_REASON_PREFIX + cause,
        }
        self._in_store_breaker = (cause, self._decision_sequence)
        path = getattr(self, "_in_store_breaker_path", None)
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(record, ensure_ascii=False) + "\n",
                                encoding="utf-8")
            except OSError as error:
                record["write_error"] = str(error)
        self._in_store_note("breaker", record)
        return record

    def _in_store_attribute(self, name: str) -> dict:
        """A dict attribute a restored older checkpoint may lack (design 3.2)."""
        return self.__dict__.setdefault(name, {})

    # ------------------------------------------------------------ telemetry
    def _in_store_note(self, name: str, value) -> None:
        telemetry = getattr(self, "_in_store_telemetry", None)
        if not isinstance(telemetry, dict) or telemetry.get(
                "decision_sequence") != self._decision_sequence:
            telemetry = {"decision_sequence": self._decision_sequence}
            self._in_store_telemetry = telemetry
        telemetry[name] = value

    # ------------------------------------------------------------ purity
    @contextmanager
    def _in_store_pure_scope(self):
        """Design 3.0: selectors run here leave no attribute rebound behind.

        ``_next_purchase`` and the sale finders are the pure selectors the
        design names; they still write diagnostics (and, in the mana-food
        branch, a Home request).  Every rebinding and the diagnostics dict
        are put back so the shadow cannot change a later decision.
        """
        before = dict(self.__dict__)
        diagnostics = dict(getattr(self, "_shop_selector_diagnostics", {}) or {})
        try:
            yield
        finally:
            for name in tuple(self.__dict__):
                if name not in before:
                    del self.__dict__[name]
            for name, value in before.items():
                if self.__dict__.get(name, value) is not value or name not in self.__dict__:
                    self.__dict__[name] = value
            current = self.__dict__.get("_shop_selector_diagnostics")
            if isinstance(current, dict):
                current.clear()
                current.update(diagnostics)

    def _in_store_selection(self, snapshot: Snapshot) -> dict | None:
        """The pure answer to "is there an operation on this page" (design 3.0).

        Mirrors ``_shop_core``'s order: a pending disposal, then sales, then
        the next purchase.  Returns the would-be key; it never calls ``_shop``.
        """
        store = snapshot.store
        if store is None or store.store_type == STORE_HOME:
            return None
        with self._in_store_pure_scope():
            if snapshot.player.hungry and self._find_edible(snapshot) is None:
                return {"op": "survival", "would_key": None}
            if (getattr(self, "_pending_disposal_item", None) is not None
                    or getattr(self, "_home_disposal_pending", None) is not None):
                return {"op": "disposal", "would_key": None}
            pending = self._batch_sell_pending
            if (pending is not None and pending.get("store_type") == store.store_type
                    and pending.get("phase") == "await-inscription"):
                # Re-address the inscribed item on this post-op pack. The
                # stateful batch seller will validate the same row once.
                entries = pending["entries"]
                if len(entries) != 1:
                    return None
                entry = entries[0]
                sale = next((item for item in snapshot.inventory
                             if self._sale_item_identity(item) == entry["signature"]
                             and self._item_has_sale_tag(item, str(entry["tag"]))), None)
                if sale is None or not self._sale_tag_is_unique(snapshot, sale, str(entry["tag"])):
                    return None
                surplus = self._retention_surplus(snapshot, sale)
                quantity = sale.count if surplus <= 0 else min(sale.count, surplus)
                return {"op": "sell", "pending_sale": True,
                        "would_key": SELL_KEY + str(entry["tag"])
                        + (f"{quantity}\r" if sale.count > 1 else "") + "y"}
            sales = (self._current_store_sale_candidates(snapshot)
                     if self._batch_sell_pending is None else [])
            if sales:
                sale = sales[0]
                digit = self._unique_sale_tag(snapshot, sale)
                target = {"slot": sale.slot, "name": sale.name,
                          "count": sale.count, "tval": sale.tval,
                          "sval": sale.sval}
                if digit is None:
                    return {"op": "sell", "would_key": None, "target": target}
                if self._item_has_sale_tag(sale, digit):
                    surplus = self._retention_surplus(snapshot, sale)
                    quantity = sale.count if surplus <= 0 else min(sale.count, surplus)
                    key = (SELL_KEY + digit
                           + (f"{quantity}\r" if sale.count > 1 else "") + "y")
                    return {"op": "sell", "would_key": key, "target": target}
                return {"op": "inscribe",
                        "would_key": "{" + sale.slot + "@" + digit + "\r",
                        "target": target}
            item = self._next_purchase(snapshot)
            if item is None:
                return None
            # Use the existing pure Home gate, never its stateful wrapper.
            # Running _shop's Home rearm here would change the outside
            # fallback's owner before the original composition boundary.
            home_gate = self._evaluate_purchase_home_gate(snapshot, item)
            home_first = ("home-first-purchase", store.store_type,
                          *self._item_signature(item))
            if (home_gate is ProcurementHomeGate.BLOCKED
                    or (home_gate is ProcurementHomeGate.HOME_FIRST
                        and home_first not in self._town_visit_ledger.rearmed_work_signatures)):
                return {"op": "home-first", "would_key": None}
            quantity = self._purchase_quantity(snapshot, item)
            suffix = f"{quantity}\r\r" if item.count > 1 else "\r"
            wand_stack = item.tval == TVAL_WAND and item.count > 1
            return {
                "op": "buy",
                "would_key": BUY_KEY + item.letter + suffix,
                "letter": item.letter,
                "identity": _row_identity(item),
                "target": {"letter": item.letter, "name": item.name,
                           "price": item.price, "count": item.count},
                "quantity": quantity,
                "expected_confirm": expected_buy_confirmation(
                    item.price, quantity, wand_stack=wand_stack),
            }

    def _in_store_preconditions(self, snapshot: Snapshot, selection: dict | None,
                                *, continuing: bool = False) -> dict:
        """Design 3.1 trigger and letter/page conditions, each by name.

        ``continuing``: a later page of an entry that already emitted IST
        operations; its own inscribed sale awaiting this page is not an
        old-path operation.
        """
        store = snapshot.store
        visit = self._store_visit
        sale_pending = self._batch_sell_pending
        own_inscription = bool(
            continuing and sale_pending is not None
            and sale_pending.get("store_type") == store.store_type
            and sale_pending.get("phase") == "await-inscription"
        )
        row_ok = True
        if selection is not None and selection.get("op") == "buy":
            row = next((item for item in store.items
                        if item.letter == selection["letter"]), None)
            row_ok = row is not None and _row_identity(row) == selection["identity"]
        return {
            "flag": bool(getattr(self, "_in_store_ops_enabled", False)),
            "breaker_clear": getattr(self, "_in_store_breaker", None) is None,
            "visit_ready": bool(
                visit is not None and visit.store_type == store.store_type
                and visit.phase != StoreVisitPhase.CLOSED),
            "no_old_path_operation": bool(
                self._store_buy_inflight is None
                and (sale_pending is None or own_inscription)
                and not (visit is not None and visit.operation_posted)),
            "page_one": store.page_top == 0,
            "identity": row_ok,
            "screen_on_page": getattr(self, "_in_store_screen_verified", None) is True,
        }

    # ------------------------------------------------------------ Phase 0
    def _in_store_shadow(self, snapshot: Snapshot) -> None:
        """Log what IST would do on this observe-and-leave page (no effect)."""
        started = time.perf_counter()
        selection = self._in_store_selection(snapshot)
        conditions = self._in_store_preconditions(snapshot, selection)
        shadow = {
            "store": snapshot.store.store_type,
            "op": None if selection is None else selection.get("op"),
            "would_key": None if selection is None else selection.get("would_key"),
            "target": None if selection is None else selection.get("target"),
            "expected_confirm": (
                None if selection is None else selection.get("expected_confirm")),
            "preconditions": conditions,
        }
        shadow["ms"] = round((time.perf_counter() - started) * 1000, 3)
        self._in_store_note("shadow", shadow)
        if selection is not None and selection.get("would_key"):
            self._in_store_attribute("_in_store_shadow_last")[snapshot.store.store_type] = {
                "sequence": self._decision_sequence,
                "would_key": selection["would_key"],
                "target": selection.get("target"),
            }
        else:
            self._in_store_attribute("_in_store_shadow_last").pop(snapshot.store.store_type, None)

    def _in_store_shadow_agreement(self, snapshot: Snapshot, released: str) -> None:
        """Phase 0: compare a stage-2 release with the shadow of its page."""
        shadow = self._in_store_attribute("_in_store_shadow_last").pop(snapshot.store.store_type, None)
        if shadow is None:
            return
        body = released[:-1] if released.endswith(LEAVE_STORE_KEY) else released
        same_identity = None
        target = shadow.get("target") or {}
        if body.startswith(BUY_KEY) and len(body) > 1:
            row = next((item for item in snapshot.store.items
                        if item.letter == body[1]), None)
            same_identity = row is not None and (
                row.name, row.price, row.count) == (
                target.get("name"), target.get("price"), target.get("count"))
        self._in_store_note("agreement", {
            "store": snapshot.store.store_type,
            "shadow_sequence": shadow["sequence"],
            "shadow_key": shadow["would_key"],
            "released_key": released,
            "same_body": shadow["would_key"] == body,
            "same_identity": same_identity,
        })

    # ------------------------------------------------------------ Phase 1
    def _in_store_try_start(self, snapshot: Snapshot) -> str | None:
        """The observe-and-leave page: start an IST entry, or fall back (None)."""
        if not self._in_store_ops_active():
            return None
        selection = self._in_store_selection(snapshot)
        if selection is None or not selection.get("would_key"):
            return None
        conditions = self._in_store_preconditions(snapshot, selection)
        self._in_store_note("start", {"op": selection["op"], "preconditions": conditions})
        if not all(conditions.values()):
            return None
        visit = self._store_visit
        self._in_store_entry_ledger = {
            "store": snapshot.store.store_type,
            "opened_sequence": visit.opened_sequence,
            "ops": 0,
            "pending": None,
            "ended": False,
        }
        key = self._in_store_emit(snapshot, selection, first=True)
        if key is None:
            self._in_store_entry_ledger = None
        return key

    def _in_store_entry_key(self, snapshot: Snapshot) -> str | None:
        """An entry that emitted an IST operation continues IST or leaves."""
        ledger = getattr(self, "_in_store_entry_ledger", None)
        if ledger is None:
            return None
        visit = self._store_visit
        if (
            snapshot.store.store_type != ledger["store"]
            or visit is None
            or visit.opened_sequence != ledger["opened_sequence"]
            or visit.store_type != ledger["store"]
        ):
            self._in_store_entry_ledger = None
            return None
        breaker = getattr(self, "_in_store_breaker", None)
        if breaker is not None:
            return self._in_store_leave(
                snapshot, IN_STORE_BREAKER_REASON_PREFIX + str(breaker[0]))
        pending = ledger["pending"]
        if pending is not None and self._decision_sequence > pending["sequence"]:
            if pending["kind"] == "inscribe" and self._in_store_inscription_observed(snapshot):
                self._in_store_effect_confirmed(snapshot)
            else:
                # Buy/sell confirmation ran on this board already
                # (policy.py one-shot confirmation); still pending means the
                # state-bound post-operation board shows no effect: no
                # in-store retry, the entry ends (design 3.1).
                ledger["ended"] = True
        if ledger["ended"] or ledger["ops"] >= STORE_STUCK_LIMIT:
            return self._in_store_leave(snapshot, IN_STORE_DONE_REASON)
        selection = self._in_store_selection(snapshot)
        if selection is None or not selection.get("would_key"):
            # Pure end-of-visit selection: _shop is reserved for an actual
            # operation, not run again merely to compute a leave command.
            return self._in_store_leave(snapshot, IN_STORE_DONE_REASON)
        conditions = self._in_store_preconditions(snapshot, selection, continuing=True)
        self._in_store_note("continue", {
            "op": None if selection is None else selection.get("op"),
            "ops": ledger["ops"], "preconditions": conditions,
        })
        if not all(conditions.values()):
            return self._in_store_leave(snapshot, IN_STORE_DONE_REASON)
        key = self._in_store_emit(snapshot, selection, first=False)
        if key is None:
            return self._in_store_leave(snapshot, IN_STORE_DONE_REASON)
        return key

    def _in_store_emit(self, snapshot: Snapshot, selection: dict | None, *,
                       first: bool) -> str | None:
        """Call ``_shop`` once for this page; emit only p/d/{ (design 3.1).

        A first page whose ``_shop`` result is anything else falls back to
        observe-and-leave; its result is kept for the outside composition so
        ``_shop`` is not run twice for the same page (design 3.0).
        """
        store = snapshot.store
        key = self._shop(snapshot)
        if not key or not key.startswith((BUY_KEY, SELL_KEY, "{")):
            if first:
                self._in_store_shop_fallback = {
                    "store": store.store_type,
                    "generation": self._decision_sequence,
                    "key": key,
                    "reason": self.last_reason,
                }
            self._in_store_note("fallback", {"shop_key": key, "shop_reason": self.last_reason})
            return None
        if key.startswith(BUY_KEY) and (
                selection is None or selection.get("op") != "buy"
                or key[1:2] != selection.get("letter")):
            # Selection and ``_shop`` disagree on the row: never post it in
            # the store.  A first page hands ``_shop``'s own result to the
            # outside composition (today's path); a later page ends the entry.
            self._store_buy_inflight = None
            self._in_store_note("fallback", {"shop_key": key, "identity": False})
            if first:
                self._in_store_shop_fallback = {
                    "store": store.store_type,
                    "generation": self._decision_sequence,
                    "key": key,
                    "reason": self.last_reason,
                }
            return None
        reason = (
            IN_STORE_BUY_REASON if key.startswith(BUY_KEY)
            else IN_STORE_SELL_REASON if key.startswith(SELL_KEY)
            else IN_STORE_INSCRIBE_REASON
        )
        family = "shop-buy" if key.startswith(BUY_KEY) else "shop-sell"
        visit = self._store_visit
        visit.transition(StoreVisitPhase.OPERATING)
        visit.operation_posted = True
        visit.operation_released = True
        visit.operation_effect_observed = False
        visit.operation_producer_family = family
        visit.operation_key = key
        visit.claim_operation_identity = (store.store_type, visit.opened_sequence, key)
        visit.posted_sequence = self._decision_sequence
        visit.posted_turn = snapshot.turn
        self._open_execution_delegation(
            family, family,
            ("shop-operation", visit.opened_sequence, store.store_type, key),
            ("plan-stop-operation", store.store_type,
             tuple(sorted(getattr(visit, "requester_families", ())))),
            "inventory/gold-effect", "shop-one-shot-existing-budget",
        )
        ledger = self._in_store_entry_ledger
        ledger["pending"] = {
            "kind": ("buy" if key.startswith(BUY_KEY)
                     else "sell" if key.startswith(SELL_KEY) else "inscribe"),
            "key": key,
            "sequence": self._decision_sequence,
            "turn": snapshot.turn,
        }
        # Observation ownership (design 3.1, review change 2): a page IST
        # acted on never leaves a composable observation behind.
        if (self._shop_observation is not None
                and self._shop_observation[0].store_type == store.store_type):
            self._shop_observation = None
        self._in_store_shop_fallback = None
        self.last_reason = reason
        self._record_shop_selector_diagnostics(snapshot, key)
        self._in_store_note("operation", {"key": key, "reason": reason,
                                          "ops": ledger["ops"]})
        return key

    def _in_store_leave(self, snapshot: Snapshot, reason: str) -> str:
        """End an IST entry with the operation's own exit (no observation)."""
        ledger = self._in_store_entry_ledger
        if ledger is not None:
            ledger["ended"] = True
        visit = self._store_visit
        if visit is not None:
            # The executor has completed this input operation, including
            # when its fresh board shows no business effect. Its remaining
            # buy/sell watch belongs to the outside confirmation budget;
            # it must not advertise an input tail still owning this exit.
            visit.operation_posted = False
        self.last_reason = reason
        self._offer_execution(
            LEAVE_STORE_KEY,
            producer="shop-buy" if reason == IN_STORE_DONE_REASON else "store-router",
            work_id="shop:in-store-leave",
            next_step="store.leave.send",
            arguments=(snapshot.store.store_type,),
            expected_effect="outside-store",
        )
        self._in_store_note("leave", {"reason": reason})
        return LEAVE_STORE_KEY

    def _in_store_post_op_board(self, snapshot: Snapshot) -> bool:
        """The state-bound STORE board after this entry's posted buy/sell."""
        ledger = getattr(self, "_in_store_entry_ledger", None)
        if ledger is None or snapshot.store is None:
            return False
        pending = ledger.get("pending")
        return bool(
            pending is not None
            and pending["kind"] in {"buy", "sell"}
            and snapshot.store.store_type == ledger["store"]
            and self._decision_sequence > pending["sequence"]
        )

    def _in_store_inscription_observed(self, snapshot: Snapshot) -> bool:
        pending = self._batch_sell_pending
        if pending is None or pending.get("phase") != "await-inscription":
            return False
        return all(
            any(
                self._sale_item_identity(current) == entry["signature"]
                and self._item_has_sale_tag(current, str(entry["tag"]))
                for current in snapshot.inventory
            )
            for entry in pending["entries"]
        )

    def _in_store_effect_confirmed(self, snapshot: Snapshot) -> None:
        """Design 3.2: effect seen on the open page; the visit keeps operating."""
        ledger = self._in_store_entry_ledger
        ledger["ops"] += 1
        ledger["pending"] = None
        visit = self._store_visit
        if visit is not None:
            visit.transition(StoreVisitPhase.OPERATING)
            visit.operation_posted = False
            visit.operation_released = False
            visit.operation_effect_observed = False
            visit.operation_key = None
            visit.claim_operation_identity = None

    def _in_store_reconcile(self, owner: str, business_outcome: str | None) -> None:
        """Executor-proven results of an IST operation (design 3.1 refusals)."""
        if owner not in IN_STORE_OPERATION_REASONS or business_outcome is None:
            return
        ledger = getattr(self, "_in_store_entry_ledger", None)
        if owner == IN_STORE_BUY_REASON and business_outcome == "failed:purchase-refused":
            self._store_buy_inflight = None
            self._in_store_entry_ledger = None
            self._close_store_visit("in-store-buy-refused")
            return
        cause = {
            "failed:price-mismatch": "price-mismatch",
            "refused:store-command": "store-command-refused",
            "failed:unowned-screen": "unowned-screen",
            "failed:terminal": "terminal",
        }.get(business_outcome)
        if cause is None:
            return
        # The operation did not happen: its watches end with it.
        if owner == IN_STORE_BUY_REASON:
            self._store_buy_inflight = None
        elif self._batch_sell_pending is not None:
            self._batch_sell_pending = None
        if ledger is not None:
            ledger["pending"] = None
        visit = self._store_visit
        if visit is not None and visit.operation_posted:
            visit.operation_posted = False
            visit.operation_released = False
            visit.operation_key = None
            visit.claim_operation_identity = None
        self.trip_in_store_breaker(cause)

    def _in_store_cached_shop(self, observation) -> tuple[bool, str | None]:
        """The in-store ``_shop`` result of this observed page, if IST ran it."""
        cached = getattr(self, "_in_store_shop_fallback", None)
        self._in_store_shop_fallback = None
        if (
            cached is None
            or observation is None
            or cached["store"] != observation[0].store_type
            or cached["generation"] != observation[1]
        ):
            return False, None
        self.last_reason = cached["reason"]
        return True, cached["key"]

    # ------------------------------------------------------------ Part B
    def _observe_shelf_evidence(self, snapshot: Snapshot) -> None:
        """Design 3.3.2: record page one and what is known about last_visit."""
        started = time.perf_counter()
        store = snapshot.store
        if store is None or store.store_type == STORE_HOME or store.page_top != 0:
            return
        town = self._effective_town_id(snapshot)
        pages = self._in_store_attribute("_shelf_evidence").setdefault("pages", {})
        key = (town, store.store_type)
        signature = shelf_signature(store)
        previous = pages.get(key)
        restock = None
        window = None
        opened = getattr(getattr(self, "_store_visit", None), "opened_sequence", None)
        entering = previous is not None and opened != previous.get("opened_sequence")
        if previous is not None:
            if entering and snapshot.turn - previous["turn"] >= STORE_MAINTENANCE_INTERVAL_TURNS:
                restock = "elapsed"
            elif entering and self._shelf_changed_beyond_trades(previous, signature):
                restock = "changed"
            if restock is not None:
                window = snapshot.turn
            elif (previous["window"] is not None
                  and snapshot.turn < previous["window"] + STORE_MAINTENANCE_INTERVAL_TURNS):
                window = previous["window"]
        # Dry runs are keyed by the shelf signature; a new observation of any
        # shelf starts a fresh cache so it never outgrows one town stay.
        self._in_store_attribute("_shelf_evidence_cache").clear()
        pages[key] = {
            "opened_sequence": opened,
            "turn": snapshot.turn,
            "signature": signature,
            "page": store,
            "stock_num": store.stock_num,
            "page_size": store.page_size,
            "window": window,
            "restock": restock,
            "trades": [],
        }
        # A no-operation verdict is conservative for every ordinary-shop
        # category: if any purchase or sale is possible, keep every stop.
        # Populate the category ledger on every observed board, including
        # categories whose needs will only be armed after a later purchase.
        with self._in_store_pure_scope():
            absent = self._shelf_dry_run_absent(snapshot, store)
            categories = {spec.category for spec in self._town_need_registry()
                          if spec.ordering_class not in {"home-first", "post-alchemist-home"}}
        ledger = self._in_store_attribute("_shelf_evidence").setdefault("ledger", {})
        for category in categories:
            ledger[(town, store.store_type, category)] = (snapshot.turn, signature, absent)
        outcome = self._in_store_attribute("_plan_shadow_pending").pop(key, None)
        if outcome is not None:
            self._in_store_attribute("_plan_shadow_visits")[key] = {
                **outcome, "visited_turn": snapshot.turn, "productive": False}
        self._in_store_note("shelf_observe_ms", round((time.perf_counter() - started) * 1000, 3))

    def _in_store_shadow_visit_outcome(self, snapshot: Snapshot) -> None:
        """Audit would-skip visits after their actual confirmed trades/exit."""
        if snapshot.store is not None:
            return
        audits = self._in_store_attribute("_plan_shadow_visits")
        if audits:
            self._in_store_note("plan_shadow_outcomes", [
                {**entry, "exited_turn": snapshot.turn,
                 "fruitless": not entry["productive"]} for entry in audits.values()])
            audits.clear()

    @staticmethod
    def _shelf_changed_beyond_trades(previous: dict, signature) -> bool:
        """Rule (a): a change the bot's own trades since then cannot explain.

        Only (tval, sval) groups the bot did not trade are compared: a bought
        stack's display name can change with its count.  A sale, or a
        purchase on a multi-page shelf (rows shift between pages), leaves (a)
        unestablished.
        """
        trades = previous["trades"]
        if any(trade[0] == "sell" for trade in trades):
            return False
        multi_page = (
            isinstance(previous.get("stock_num"), int)
            and isinstance(previous.get("page_size"), int)
            and previous["stock_num"] > previous["page_size"]
        )
        if trades and multi_page:
            return False
        traded = {(trade[2], trade[3]) for trade in trades}

        def groups(rows) -> Counter:
            counts: Counter = Counter()
            for name, tval, sval, count in rows:
                if (tval, sval) not in traded:
                    counts[(name, tval, sval)] += count
            return counts

        return groups(previous["signature"]) != groups(signature)

    def _note_shelf_trade(self, snapshot: Snapshot, store_type: int, kind: str,
                          signature: tuple, quantity: int, gold_spent: int = 0) -> None:
        """A confirmed own trade with this shelf since its last observation.

        A purchase confirmed by gold alone (the carried name differs from the
        shelf name) counts the units its gold paid for at the observed price.
        """
        record = self._in_store_attribute("_shelf_evidence").get("pages", {}).get(
            (self._effective_town_id(snapshot), store_type))
        if record is None:
            return
        name, tval, sval = signature[:3]
        name = shelf_item_name(str(name))
        if kind == "buy" and quantity <= 0:
            row = next((item for item in record["page"].items
                        if (shelf_item_name(item.name), item.tval, item.sval)
                        == (name, tval, sval)), None)
            quantity = (
                max(1, gold_spent // row.price)
                if row is not None and row.price > 0 and gold_spent > 0 else 1
            )
        record["trades"].append((kind, name, tval, sval, quantity))
        audit = self._in_store_attribute("_plan_shadow_visits").get(
            (self._effective_town_id(snapshot), store_type))
        if audit is not None:
            audit["productive"] = True

    @staticmethod
    def _shelf_page_after_trades(record: dict) -> StoreState:
        """The observed page minus what the bot bought from it since then.

        Without a restock the shelf changes only by the player's own trades
        (design 3.3.2); a one-shot buy happens after its page was observed, so
        the bought units are taken off that page.  A sold item's shelf row
        cannot be predicted and is not added.
        """
        page = record["page"]
        bought: Counter = Counter()
        for kind, name, tval, sval, quantity in record["trades"]:
            if kind == "buy":
                bought[(name, tval, sval)] += quantity
        if not bought:
            return page
        items = []
        for item in page.items:
            identity = (shelf_item_name(item.name), item.tval, item.sval)
            taken = min(bought[identity], item.count)
            bought[identity] -= taken
            if item.count - taken > 0:
                items.append(replace(item, count=item.count - taken) if taken else item)
        return replace(page, items=items)

    @staticmethod
    def _shelf_evidence_valid(record: dict, turn: int) -> bool:
        """Hard window [E, E+10000) when last_visit is known, else the 5000 rule."""
        if record["window"] is not None:
            return turn < record["window"] + STORE_MAINTENANCE_INTERVAL_TURNS
        return turn - record["turn"] < STORE_RETRY_TURNS

    def _shelf_dry_run_absent(self, snapshot: Snapshot, page: StoreState) -> bool:
        """Pure dry run (design 3.0): would this remembered page give no operation?"""
        view = replace(snapshot, store=page)
        with self._in_store_pure_scope():
            if snapshot.player.hungry and self._find_edible(snapshot) is None:
                return False
            if (getattr(self, "_pending_disposal_item", None) is not None
                    or getattr(self, "_home_disposal_pending", None) is not None):
                return False
            pending = self._batch_sell_pending
            if pending is not None and pending.get("store_type") == page.store_type:
                return False
            if self._next_purchase(view) is not None:
                return False
            return not self._current_store_sale_candidates(view)

    def _shelf_evidence_entry(self, snapshot: Snapshot, store_type: int,
                              category: str) -> dict | None:
        """The (town, store, category) ledger entry for a planned stop."""
        started = time.perf_counter()
        town = self._effective_town_id(snapshot)
        record = self._in_store_attribute("_shelf_evidence").get("pages", {}).get((town, store_type))
        if record is None or not self._shelf_evidence_valid(record, snapshot.turn):
            return None
        pack = (
            snapshot.player.gold,
            tuple(repr(item) for item in snapshot.inventory),
            tuple(repr(item) for item in snapshot.equipment),
            snapshot.player.food_type, self._planned_depth(),
            getattr(self, "_identification_need", None),
            getattr(self, "_fundraising_mode", None),
            getattr(self, "_home_knowledge_scan_epoch", None),
            getattr(self, "_home_knowledge_current", False),
            repr(getattr(self, "_equipment_transaction_owned_items", ())),
            repr(getattr(self, "_unsellable_items", ())),
            repr(getattr(self, "_deferred_device_items", ())),
        )
        cache_key = (town, store_type, record["signature"], tuple(record["trades"]),
                     pack, category)
        absent = self._in_store_attribute("_shelf_evidence_cache").get(cache_key)
        if absent is None:
            absent = self._shelf_dry_run_absent(
                snapshot, self._shelf_page_after_trades(record))
            self._in_store_attribute("_shelf_evidence_cache")[cache_key] = absent
        # Include cache hits and key construction, not only selector time.
        telemetry = getattr(self, "_in_store_telemetry", None)
        spent = (time.perf_counter() - started) * 1000
        if isinstance(telemetry, dict) and telemetry.get(
                "decision_sequence") == self._decision_sequence:
            spent += float(telemetry.get("dry_run_ms", 0.0))
        self._in_store_note("dry_run_ms", round(spent, 3))
        ledger = self._in_store_attribute("_shelf_evidence").setdefault("ledger", {})
        ledger[(town, store_type, category)] = (record["turn"], record["signature"], absent)
        return {
            "store": store_type,
            "category": category,
            "observed_turn": record["turn"],
            "window": record["window"],
            "restock": record["restock"],
            "absent": absent,
        }

    def _shelf_evidence_skips_need(self, snapshot: Snapshot, store_type: int,
                                   category: str) -> bool:
        """Design 3.3.3: skip ``add(store, category)`` on valid absence evidence."""
        if store_type == STORE_HOME:
            return False
        entry = self._shelf_evidence_entry(snapshot, store_type, category)
        if entry is None or not entry["absent"]:
            # The shadow audits only a would-be skip that still stands.
            self._in_store_attribute("_plan_shadow_pending").pop(
                (self._effective_town_id(snapshot), store_type), None)
            return False
        if getattr(self, "_in_store_ops_enabled", False):
            skips = self._in_store_decision_list("shelf_evidence_skips")
            if entry not in skips:
                skips.append(entry)
            return True
        # Phase 0: record the would-be skip and audit the next visit.  A
        # planner run on the shop's own page belongs to the visit in progress.
        would = self._in_store_decision_list("plan_shadow_would_skip")
        if entry not in would:
            would.append(entry)
        if snapshot.store is None:
            self._in_store_attribute("_plan_shadow_pending").setdefault(
                (self._effective_town_id(snapshot), store_type),
                {"store": store_type, "category": category,
                 "would_skip_sequence": self._decision_sequence,
                 "observed_turn": entry["observed_turn"]},
            )
        return False

    def _in_store_decision_list(self, name: str) -> list:
        telemetry = getattr(self, "_in_store_telemetry", None)
        if not isinstance(telemetry, dict) or telemetry.get(
                "decision_sequence") != self._decision_sequence:
            self._in_store_note(name, [])
            telemetry = self._in_store_telemetry
        return telemetry.setdefault(name, [])

    def in_store_decision_telemetry(self) -> dict | None:
        """CLI: this decision's IST/shelf-evidence record, if any."""
        telemetry = getattr(self, "_in_store_telemetry", None)
        if not isinstance(telemetry, dict) or telemetry.get(
                "decision_sequence") != self._decision_sequence:
            return None
        return telemetry
