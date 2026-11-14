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
its visit: the two stockout mining plans and the identification candidates.
The plans live through the run their visit started and end on the return;
the candidates end with the visit that bound them.  Slice 3-2's rest (owner
2026-11-03 「町の第3段 3-2 の残り」) moves in the in-store watches, the town
order's operation, the dominated-disposal attempts, the Home disposal and the
Home procurement probe.
"""
from __future__ import annotations

from collections.abc import Callable
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
    # quest_optional_carry filed its Home withdrawal: once a visit.
    optional_carry_filed: bool = False
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
    # The carried item bound to the identification flow, and the device bound
    # to it: each is bound by a town producer that derives it from the
    # current pack, so a candidate from an earlier visit is not this visit's
    # (da4d84b48: a candidate destroyed on the trip kept its request latched).
    identification_candidate: Signature | None = None
    device_identification_candidate: Signature | None = None
    # The in-store no-progress watches.  A watch counts unchanged attempts of
    # one transaction in a store; the next visit is another attempt with its
    # own budget, so an earlier visit's count cannot leave it early.
    # (item letter, gold) of the last buy tried and how many times it was
    # retried unchanged: a purchase that never registers.
    last_buy_sig: tuple[str, int] | None = None
    store_stuck_count: int = 0
    # Same target and shortage after a registered, money-spending buy is a
    # distinct defect from a transport failure at unchanged gold.
    last_buy_progress_sig: tuple[str, int, int] | None = None
    store_buy_no_progress_count: int = 0
    # The last sale or Home deposit attempted and its unchanged repeats.
    last_sell_sig: tuple | None = None
    store_sell_stuck_count: int = 0
    # The town order's posted operation and the observation it awaits.  Every
    # step derives it from the current pack and supplies when it runs, so a
    # step of the last visit is not this visit's: it cannot report a bounty
    # "removed" that this visit never held.
    town_order_operation: str | None = None
    town_order_expected_observation: str | None = None
    # A dominated item's disposal keeps its target across the trip (the
    # policy's _pending_disposal_item), but the attempts are this visit's: the
    # stores that refused it restock while the character is away, and the
    # destroy budget is the same per-visit retry as destroy_fail_streak.
    destroy_attempts: int = 0
    disposal_store_attempts: set[int] = field(default_factory=set)
    # The approved Home disposal in progress (identity, "sell" or "destroy").
    # An unfinished one is planned again from the shelf by the next Home pass;
    # kept, an absent "destroy" stood in for that pass for good.  What it holds
    # ends with it (_end_visit_home_disposal).
    home_disposal_pending: tuple[Signature, str] | None = None
    # A purchase is legal only after the current Home catalogue has been
    # evaluated for the same item class.  This latch names the class whose
    # scan/withdrawal owns routing before an ordinary store may compose p; the
    # purchase gate binds it again on the page that wants the class.
    home_procurement_probe: tuple[int, int] | None = None
    # The visit's stage trace (town rebuild stage 3-1, town_visit_plan):
    # [stage, first sequence, last sequence, decisions, interrupts] per run
    # of decisions in one stage.  Nothing decides from it yet.
    plan_segments: list[list] = field(default_factory=list)
    # The visit's decisions per stage (interrupts not counted), which the
    # stages' deadlines read (town rebuild stage 3-5, town_visit_plan).
    stage_decisions: dict[str, int] = field(default_factory=dict)
    # The observed work states this visit's boards showed (gold, the pack and
    # the equipment: town_visit_plan.work_state), and the stage of the
    # decision before this one: a board that shows a state the visit has not
    # seen is that stage's completed unit of work, which restarts the stage's
    # deadline count (owner 2026-11-15, town_visit_plan.note_observed_progress).
    observed_work_states: set = field(default_factory=set)
    previous_decision_stage: str | None = None
    # The progress seam's replacements this visit (town rebuild stage 3-3a):
    # [sequence, the producer's reason, the seam's reason].  Nothing decides
    # from it; stage 3-3 retires the seam and shows this list empty.  Since
    # stage 3-3e it holds only a replacement no owner's stage transition
    # (town_visit_plan.TRANSITIONS) declared.
    plan_rewrites: list[list] = field(default_factory=list)
    # The owners' stage transitions this visit (town rebuild stage 3-3e):
    # [sequence, transition name, the producer's reason, the result's reason].
    plan_transitions: list[list] = field(default_factory=list)
    # The transition declared on the decision being made; note_seam reads and
    # clears it on the same decision.
    transition_declared: str | None = None

    def begin(self, *, home_candidate_waiting: Callable[[], bool],
              run_made_again: bool = False) -> None:
        """Start a new visit: forget every fact of the previous one.

        ``home_candidate_waiting`` evaluates the arrival's Home identification
        latch.  It reads the previous visit's deferred Home items and carried
        unidentifiable signatures, as the former reset did, but not its
        identification candidates: they end first.
        ``run_made_again``: the arrival is the return of a run that is made
        again (a run ended by a ruled-out unique, owner 2026-10-31), so the
        stockout plan of that run stays with it.
        """
        plans = (self.identify_staff_mining_plan, self.recall_stockout_mining_plan)
        self.identification_candidate = None
        self.device_identification_candidate = None
        waiting = home_candidate_waiting()
        for spec in fields(self):
            if spec.default_factory is not MISSING:
                getattr(self, spec.name).clear()
            else:
                setattr(self, spec.name, spec.default)
        self.home_candidate_waiting = waiting
        if run_made_again:
            self.identify_staff_mining_plan, self.recall_stockout_mining_plan = plans

    def __setstate__(self, state: dict) -> None:
        # A visit pickled before a field existed holds that field's default.
        self.__dict__.update(_defaults())
        self.__dict__.update(state)


def is_fresh_visit(policy: Any, snapshot: Any) -> bool:
    """The board begins a new town visit (``TownVisit.begin`` runs on it):
    a town board on a floor other than the one the policy last observed."""
    return snapshot.in_town and snapshot.floor_key != policy._floor_key


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
    "_identification_candidate": "identification_candidate",
    "_device_identification_candidate": "device_identification_candidate",
    "_last_buy_sig": "last_buy_sig",
    "_store_stuck_count": "store_stuck_count",
    "_last_buy_progress_sig": "last_buy_progress_sig",
    "_store_buy_no_progress_count": "store_buy_no_progress_count",
    "_last_sell_sig": "last_sell_sig",
    "_store_sell_stuck_count": "store_sell_stuck_count",
    "_town_order_operation": "town_order_operation",
    "_town_order_expected_observation": "town_order_expected_observation",
    "_destroy_attempts": "destroy_attempts",
    "_disposal_store_attempts": "disposal_store_attempts",
    "_home_disposal_pending": "home_disposal_pending",
    "_home_procurement_probe": "home_procurement_probe",
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


# --- The hold flags, one container per clearing moment (town rebuild stage 3-2)
#
# Owner 2026-11-12 「1〜3まで一気に進める」, stage 3: the hold flags become the
# visit plan's state.  Before stage 3-2 they were policy attributes forgotten
# in several places, each with its own copy of the list, so a flag added to
# one list and not another outlived its moment.  Each container below holds
# the flags that end at one moment, and its ``release`` is the one forgetting
# (containers emptied in place, the rest back to its default, as the lists
# did).  The former attribute names forward to the containers; an old
# checkpoint's attributes move in on restore (``adopt_legacy_holds``).
#
# ``TownHolds`` (stage 3-2a) ends when the character leaves the floor it was
# on or the town changes on the surface (inn travel keeps the surface floor
# key): policy_observation's floor change with a previous floor, and its town
# change, which forgets three more by name.
# ``FloorHolds`` (stage 3-2b) ends on every board whose floor is not the one
# the policy last decided on, the first board of a process included
# (policy_observation's ``floor_key != _floor_key``).
# Neither is a ``TownVisit`` field: ``TownVisit.begin`` runs on a fresh town
# visit only.


class _Holds:
    """A dataclass mixin: ``release`` and a default-filling ``__setstate__``."""

    def release(self) -> None:
        for spec in fields(self):
            if spec.default_factory is not MISSING:
                getattr(self, spec.name).clear()
            else:
                setattr(self, spec.name, spec.default)

    def __setstate__(self, state: dict) -> None:
        # A container pickled before a field existed holds that field's default.
        self.__dict__.update({
            spec.name: (spec.default_factory() if spec.default_factory is not MISSING
                        else spec.default)
            for spec in fields(self)})
        self.__dict__.update(state)


def _signature_history() -> Any:
    from collections import deque
    from hengbot.policy_constants import TOWN_CYCLE_WINDOW
    return deque(maxlen=TOWN_CYCLE_WINDOW)


@dataclass
class TownHolds(_Holds):
    # Native surface travel's progress and its fallback goal.
    travel_state: Any = None
    travel_fallback: Any = None
    # The town monster the survival owner walks to.
    hunt_target: Any = None
    # The town-repetition detector (TOWN_CYCLE_WINDOW) and the no-progress
    # breaker (TOWN_WANDER_LIMIT).
    signature_history: Any = field(default_factory=_signature_history)
    progress_marker: tuple | None = None
    no_progress_count: int = 0
    cycle_pending: bool = False
    cycle_breaks: int = 0
    # The visit's committed departure and the departures it recorded.
    departure_committed: Any = None
    departure_recorded: set = field(default_factory=set)
    # The restock suppression and the stores its claim covers.
    restock_suppressed: bool = False
    suppression_claim_stores: set[int] = field(default_factory=set)
    # The store errand plan of this stay.
    errand_plan: Any = None
    # The town end's terminal four-slot pack certificate.
    terminal_pack_space_signature: Any = None
    # The restock wait: until when, for which stores, what was rechecked.
    restock_wait_until: int | None = None
    restock_waiting_for: tuple[int, ...] = ()
    restock_rechecked: set[int] = field(default_factory=set)
    restock_waited_turns: int = 0
    restock_last_wait_turn: int | None = None


@dataclass
class FloorHolds(_Holds):
    # The equipment optimizer timed out on this floor's visit.
    equipment_optimization_timed_out: bool = False
    # The dungeon the armed recall was read for, and the read's issue watch
    # (destination, command turn, pre-read stack count).
    pending_recall_dungeon_id: int | None = None
    recall_issue_watch: tuple[int, int, int] | None = None
    # The occupied pack slots the armed read was authorised with (stage 3-3b):
    # the canceller's pack leaf is a regression only when the pack is fuller.
    recall_read_pack_slots: int | None = None
    # This visit already cancelled a recall as unready (the read point never
    # reads again in the same visit, the read/cancel class bound).  The town
    # change forgets it too, by name.
    unready_recall_cancelled: bool = False
    # Store purchases are retained for the rest of the visit.
    purchases: set = field(default_factory=set)
    purchase_quantities: dict = field(default_factory=dict)
    # Sales are retained for the visit: buying the same tval/sval back is churn.
    sale_signatures: set = field(default_factory=set)
    # Most per-staff charges of an Identify staff sold this visit.
    sale_identify_charges: int | None = None


HOLD_LEGACY_NAMES = {
    "_town_travel_state": "travel_state",
    "_town_travel_fallback": "travel_fallback",
    "_town_hunt_target": "hunt_target",
    "_town_signature_history": "signature_history",
    "_town_progress_marker": "progress_marker",
    "_town_no_progress_count": "no_progress_count",
    "_town_cycle_pending": "cycle_pending",
    "_town_cycle_breaks": "cycle_breaks",
    "_visit_departure_committed": "departure_committed",
    "_visit_departure_recorded": "departure_recorded",
    "_town_restock_suppressed": "restock_suppressed",
    "_town_suppression_claim_stores": "suppression_claim_stores",
    "_town_errand_plan": "errand_plan",
    "_terminal_pack_space_signature": "terminal_pack_space_signature",
    "_town_restock_wait_until": "restock_wait_until",
    "_town_restock_waiting_for": "restock_waiting_for",
    "_town_restock_rechecked": "restock_rechecked",
    "_town_restock_waited_turns": "restock_waited_turns",
    "_town_restock_last_wait_turn": "restock_last_wait_turn",
}

FLOOR_HOLD_LEGACY_NAMES = {
    "_equipment_optimization_timed_out_this_visit": "equipment_optimization_timed_out",
    "_pending_recall_dungeon_id": "pending_recall_dungeon_id",
    "_town_recall_issue_watch": "recall_issue_watch",
    "_town_recall_read_pack_slots": "recall_read_pack_slots",
    "_town_visit_unready_recall_cancelled": "unready_recall_cancelled",
    "_town_visit_purchases": "purchases",
    "_town_visit_purchase_quantities": "purchase_quantities",
    "_town_visit_sale_signatures": "sale_signatures",
    "_town_visit_sale_identify_charges": "sale_identify_charges",
}

# policy attribute -> (container class, its former attribute names)
_HOLD_CONTAINERS = {
    "_town_holds": (TownHolds, HOLD_LEGACY_NAMES),
    "_floor_holds": (FloorHolds, FLOOR_HOLD_LEGACY_NAMES),
}


def _holder(policy: Any, attribute: str) -> Any:
    """The policy's container, made on first use (like ``town_visit``)."""
    holder = policy.__dict__.get(attribute)
    if holder is None:
        holder = policy.__dict__[attribute] = _HOLD_CONTAINERS[attribute][0]()
    return holder


def town_holds(policy: Any) -> TownHolds:
    return _holder(policy, "_town_holds")


def floor_holds(policy: Any) -> FloorHolds:
    return _holder(policy, "_floor_holds")


def _forward_hold(attribute: str, name: str) -> property:
    return property(
        lambda policy: getattr(_holder(policy, attribute), name),
        lambda policy, value: setattr(_holder(policy, attribute), name, value),
        doc=f"{_HOLD_CONTAINERS[attribute][0].__name__}.{name} (town rebuild stage 3-2).",
    )


for _attribute, (_cls, _names) in _HOLD_CONTAINERS.items():
    for _legacy, _name in _names.items():
        setattr(TownVisitAttributes, _legacy, _forward_hold(_attribute, _name))


def hold_bindings(state: dict) -> dict:
    """Every container's flags under the policy's former names (diagnostics),
    read from a policy's ``vars``."""
    bindings = {}
    for attribute, (_cls, names) in _HOLD_CONTAINERS.items():
        holder = state.get(attribute)
        if holder is not None:
            bindings.update({legacy: getattr(holder, name) for legacy, name in names.items()})
    return bindings


def adopt_legacy_holds(state: dict) -> None:
    """Move an old checkpoint's hold attributes into their containers.

    Checkpoints pickled before stage 3-2 hold these as policy attributes; the
    values move as they are (the same objects), so the restored containers
    decide exactly as the restored attributes did.
    """
    for attribute, (cls, names) in _HOLD_CONTAINERS.items():
        present = [legacy for legacy in names if legacy in state]
        if not present:
            continue
        holder = state.get(attribute)
        if holder is None:
            holder = state[attribute] = cls()
        for legacy in present:
            setattr(holder, names[legacy], state.pop(legacy))
