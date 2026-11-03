"""The town visit: the state that one arrival in town owns (structure stage 3).

Structure stage 3 (plans/DESIGN-structure-1028.md) moves state into the
object that owns it, and that object decides when the state ends.  The first
owner is the town visit: everything here is per-arrival bookkeeping that the
policy forgot together at one place, the fresh-visit reset in
``policy_observation`` (the first town board after a floor change).  That
reset is now ``TownVisit.begin``; it keeps exactly the old semantics:
containers are emptied in place (a holder of a container keeps the same
object), the rest is set back to its default.

The policy keeps one ``_town_visit``.  Its former attribute names stay as
thin forwarding properties (``TownVisitAttributes``) so callers and tests read
and write the same names; ``LEGACY_NAMES`` maps them to the fields.  Slice 3-1
does not change which state survives an arrival: several fields are also
written or cleared elsewhere, as before.

Slice 3-2 (owner 2026-11-03 「3つから始める」) moves in state that outlived
its visit: the two stockout mining plans live through the run their visit
started and end on the return.
"""
from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hengbot.model import StoreState

# An item identity: (name, tval, sval) as ``_item_signature`` makes it.
Signature = tuple[str, int, int]


@dataclass
class TownVisit:
    # Full-pack disposal verification: signatures of items the game would not
    # destroy (so we stop re-selecting them and forever looping), plus a watch
    # on the last attempt to detect that the pack did not change afterwards.
    # Destruction failures are scoped to one expedition; keeping the watch
    # during the visit lets unchanged attempts reach their retry limit
    # instead of being resent forever.
    undestroyable_sigs: set[Signature] = field(default_factory=set)
    destroy_watch: tuple[Signature, int, int] | None = None
    destroy_fail_streak: int = 0
    # The posted abnormal departure stays visible on the landing board; its
    # diagnostic retires at the next fresh town visit.
    equipment_optional_failure_departure: dict[str, object] | None = None
    # Set once we visit the General Store but cannot buy a lantern (can't
    # afford it / not stocked), so we stop walking back to it forever.  A
    # fresh town visit retries the stores: an earlier give-up must not block
    # buying the rations this return trip is for.  The in-store bail-outs
    # re-bound any retry.
    shopping_abandoned: bool = False
    # store_type -> the game turn it was latched at (see STORE_RETRY_TURNS),
    # except that Home's terminal claim verdict retains its named reason.
    store_attempted: dict[int, int | str] = field(default_factory=dict)
    # A6a: Home remains the preferred source for the two-tool mining kit.
    # The count remains useful as terminal-failure evidence, but no longer
    # authorizes buying around stock that Home still records.
    digger_home_withdraw_failures: int = 0
    digger_fallback_bought: bool = False
    home_procurement_withdraw_failure: dict[str, object] | None = None
    # Rejections are only authoritative for the current town visit.  A full
    # store can reject an otherwise sellable item, so retry it after the next
    # dungeon trip instead of blacklisting it for the whole bot session.
    unsellable_items: set[Signature] = field(default_factory=set)
    # Store types that refused a sale this town visit because they are FULL
    # (no room), not because of the item type. While a store is latched here
    # the bot must stop routing spare weapons to it and stop pulling more from
    # Home to sell there; otherwise it churns futile trips to the full store.
    store_sale_refused: set[int] = field(default_factory=set)
    # Item signature, last observed count, and consecutive attempts. Unlike
    # _last_sell_sig, this survives turn changes and store exit/re-entry so
    # an unanswered prompt cannot evade rejection by advancing the turn.
    store_sell_attempt: tuple[Signature, int, int] | None = None
    # Every store sale is a tag-bound transaction.  The pending record
    # spans inscription observation, sale, and post-sale verification.
    batch_sell_pending: dict[str, object] | None = None
    home_candidate_waiting: bool = False
    deferred_home_items: set[Signature] = field(default_factory=set)
    retried_deferred_home_items: set[Signature] = field(default_factory=set)
    deferred_home_item_sites: dict[Signature, str] = field(default_factory=dict)
    home_pending_quantities: dict[Signature, int] = field(default_factory=dict)
    home_procurement_batch_active: bool = False
    # Carried equipment whose identification sources were exhausted is
    # skipped only for the current town visit.  Unlike the dungeon-facing
    # failure set, this must survive every in-town observation.
    unidentifiable_carried_sigs: set[Signature] = field(default_factory=set)
    # Shelves turn over while the character is away: a page from an earlier
    # visit is no evidence for this one, so its supplier is visited again
    # before a stockout is concluded (n1-c life-109 2026-11-02 21:11 stopped
    # on the remembered Temple/Alchemist pages right after its mining run).
    supplier_stock: dict[int, StoreState] = field(default_factory=dict)
    # Provenance for general-store shelf snapshots.  Shelf contents are kept
    # in the mapping above for its existing consumers, while decisions that
    # require negative stock evidence must prove that the page was observed
    # during this town visit and in this town.
    supplier_stock_observations: dict[int, tuple[int, int]] = field(
        default_factory=dict
    )
    deferred_device_items: set[Signature] = field(default_factory=set)
    retried_home_identification_items: set[Signature] = field(default_factory=set)
    # Home errand purposes filed since the last Home pass report
    # (home_pass_charge): the work that pass attempted.
    home_pass_errand_purposes: set[str] = field(default_factory=set)
    # The stockout time-pass plans ("one Yeek Cave 1F mining run, then retry
    # the suppliers"): the Identify staff's (_identify_staff_stockout_key)
    # and Word of Recall's (_recall_restock_key and
    # _start_unobtainable_recall_stockout_mining).  A plan is set in town and
    # read on the run (policy_fundraising._restock_time_pass_run), so it
    # lives through the trip out; the return is a new visit, whose shelves
    # decide again whether another run is due.  Before slice 3-2 a set ended
    # without clearing it (the conquest supersession, the poverty exit) left
    # the plan to later visits, where it kept the next stockout run from
    # being installed.
    identify_staff_mining_plan: bool = False
    recall_stockout_mining_plan: bool = False

    def begin(self, *, home_candidate_waiting: bool,
              run_made_again: bool = False) -> None:
        """Start a new visit: forget every fact of the previous one.

        ``home_candidate_waiting`` is the arrival's Home identification
        latch, which the caller evaluates before the reset (as the former
        reset did: against the previous visit's deferred Home items and
        carried unidentifiable signatures).
        ``run_made_again``: the arrival is the return of a run that is made
        again (a run ended by a ruled-out unique, owner 2026-10-31), so the
        stockout plan of that run stays with it.
        """
        plans = (self.identify_staff_mining_plan, self.recall_stockout_mining_plan)
        for spec in fields(self):
            if spec.default_factory is not MISSING:
                getattr(self, spec.name).clear()
            else:
                setattr(self, spec.name, spec.default)
        self.home_candidate_waiting = home_candidate_waiting
        if run_made_again:
            self.identify_staff_mining_plan, self.recall_stockout_mining_plan = plans

    def __setstate__(self, state: dict) -> None:
        # A visit pickled before a field existed holds that field's default.
        self.__dict__.update(_defaults())
        self.__dict__.update(state)


def _defaults() -> dict:
    return {
        spec.name: (spec.default_factory() if spec.default_factory is not MISSING
                    else spec.default)
        for spec in fields(TownVisit)
    }


# The policy's former attribute names, kept as forwarding properties.
LEGACY_NAMES = {
    "_undestroyable_sigs": "undestroyable_sigs",
    "_destroy_watch": "destroy_watch",
    "_destroy_fail_streak": "destroy_fail_streak",
    "_equipment_optional_failure_departure": "equipment_optional_failure_departure",
    "_shopping_abandoned": "shopping_abandoned",
    "_town_store_attempted": "store_attempted",
    "_digger_home_withdraw_failures": "digger_home_withdraw_failures",
    "_digger_fallback_bought_this_visit": "digger_fallback_bought",
    "_home_procurement_withdraw_failure": "home_procurement_withdraw_failure",
    "_unsellable_items": "unsellable_items",
    "_store_sale_refused": "store_sale_refused",
    "_store_sell_attempt": "store_sell_attempt",
    "_batch_sell_pending": "batch_sell_pending",
    "_home_candidate_waiting": "home_candidate_waiting",
    "_deferred_home_items": "deferred_home_items",
    "_retried_deferred_home_items": "retried_deferred_home_items",
    "_deferred_home_item_sites": "deferred_home_item_sites",
    "_home_pending_quantities": "home_pending_quantities",
    "_home_procurement_batch_active": "home_procurement_batch_active",
    "_town_unidentifiable_carried_sigs": "unidentifiable_carried_sigs",
    "_town_supplier_stock": "supplier_stock",
    "_town_supplier_stock_observations": "supplier_stock_observations",
    "_deferred_device_items": "deferred_device_items",
    "_retried_home_identification_items": "retried_home_identification_items",
    "_identify_staff_mining_plan": "identify_staff_mining_plan",
    "_recall_stockout_mining_plan": "recall_stockout_mining_plan",
}


def town_visit(policy: Any) -> TownVisit:
    """The policy's visit, made on first use (a policy built without
    ``__init__``, as test doubles and checkpoint restores are)."""
    visit = policy.__dict__.get("_town_visit")
    if visit is None:
        visit = policy.__dict__["_town_visit"] = TownVisit()
    return visit


def _forward(name: str) -> property:
    return property(
        lambda policy: getattr(town_visit(policy), name),
        lambda policy, value: setattr(town_visit(policy), name, value),
        doc=f"TownVisit.{name} (structure stage 3).",
    )


class TownVisitAttributes:
    """Mixin: the former policy attribute names, forwarding to the visit."""


for _legacy, _name in LEGACY_NAMES.items():
    setattr(TownVisitAttributes, _legacy, _forward(_name))


def legacy_bindings(visit: TownVisit) -> dict:
    """The visit's fields under the policy's former names (diagnostics)."""
    return {legacy: getattr(visit, name) for legacy, name in LEGACY_NAMES.items()}


def adopt_legacy_attributes(state: dict) -> None:
    """Move an old checkpoint's per-visit attributes into its town visit.

    Checkpoints pickled before slice 3-1 hold these as policy attributes;
    the values move as they are, so the restored visit decides exactly as
    the restored attributes did.  A name the checkpoint lacks keeps the
    field's default (what the old upgrade's ``setdefault`` wrote).
    """
    present = [legacy for legacy in LEGACY_NAMES if legacy in state]
    if not present:
        return
    visit = state.get("_town_visit")
    if visit is None:
        visit = state["_town_visit"] = TownVisit()
    for legacy in present:
        setattr(visit, LEGACY_NAMES[legacy], state.pop(legacy))
