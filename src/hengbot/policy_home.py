from __future__ import annotations

from hengbot.policy_constants import ADJ_STR_WEIGHT_LIMIT, AMMO_CARRY_TARGET, CALIBRATION_HOME_VISIT_LIMIT, FUNDRAISING_START_GOLD, TOWN_IDS_WITH_HOME, ZUL_TOWN_ID, SUPPLY_STORES, BUY_KEY, DESTROY_COMMAND, EMERGENCY_POTION_CARRY_TARGET, FOOD_MIN_SVAL, FOOD_TYPE_MANA, LEAVE_STORE_KEY, PACK_CAPACITY, PLAYER_CLASS_BERSERKER, READ_KEY, SELL_KEY, STORE_STUCK_LIMIT, TORCH_THROW_TARGET, UNUSED_DIVE_LIMIT, WAIT_KEY
from hengbot.home_disposal import HomeDisposalCandidate
from hengbot.home_errand import HomeErrandRequest
from hengbot.home_visit import HomeVisitExecutor, HomeVisitKind, HomeVisitRequest as PhysicalHomeVisitRequest, HomeVisitState
from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL, STORE_HOME, STORE_MAGIC, STORE_WEAPON, SV_POTION_SPEED, SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, SV_SCROLL_PHASE_DOOR, RESTORE_POTION_SVAL_BY_STAT, STAT_GAIN_POTION_SVALS, SV_SCROLL_IDENTIFY, SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_STAR_REMOVE_CURSE, TVAL_FOOD, TVAL_POTION, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, InventoryItem, Position, Snapshot, StoreItem, item_requires_full_identification
from hengbot.policy_types import StoreVisit, ProcurementHomeGate
from hengbot.latch_onset_capture import assignment_provenance
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_session import observe_equipment_transactions
from dataclasses import replace

class HomeMixin:
    @staticmethod
    def _home_page_letter(page_pos: int) -> str:
        """Map one zero-based Home page position to Hengband's selector."""
        return (
            chr(ord("a") + page_pos)
            if page_pos < 26
            else chr(ord("A") + page_pos - 26)
        )

    def _file_home_errand(
        self,
        snapshot: Snapshot,
        request: HomeErrandRequest,
        *,
        knowledge_current: bool,
    ) -> bool:
        """File migrated Home work and register its observation expectation."""
        filed = self._home_errand.file(
            request, knowledge_current=knowledge_current
        )
        if filed:
            self._post_owner_expectation(
                snapshot, f"home-errand:{request.purpose}",
                "inventory", "equipment",
            )
        return filed

    def _home_visit_keep_set(self, snapshot: Snapshot) -> frozenset[tuple]:
        """Snapshot retention inputs before a visit is allowed to approach."""
        return self._home_visit_retention(snapshot)[0]

    def _home_visit_retention(
        self, snapshot: Snapshot
    ) -> tuple[frozenset[tuple], frozenset[str]]:
        """Return the one retention authority in UI and equipment key spaces."""
        retained = tuple(
            item
            for item in snapshot.inventory
            if self._retention_reservation(snapshot, item) > 0
        )
        return (
            frozenset(self._item_signature(item) for item in retained),
            frozenset(
                equipment_identity(item) for item in retained if item.is_equipment
            ),
        )

    def _ensure_home_visit_request(self, snapshot: Snapshot) -> bool:
        """File before approach; reports are consumed explicitly, never waited."""
        if getattr(self, "_home_visit", None) is None:
            # Checkpoint/restored policies created before this structural field
            # visibly re-file from the current observation.
            self._home_visit = HomeVisitExecutor(CALIBRATION_HOME_VISIT_LIMIT)
        if not hasattr(self, "_pending_home_visit_report"):
            self._pending_home_visit_report = None
        report = self._home_visit.consume_report()
        if report is not None:
            marker = report.defect or report.outcome
            self._pending_home_visit_report = (
                f"home-visit:{report.request.requester}:{marker}"
            )
        request = self._derived_home_visit_request(snapshot)
        if request is None:
            self._home_route_refusal = self._record_home_route_refusal(
                derived=None,
                filing=None,
                rejection=None,
                begin_approach=None,
            )
            self._home_route_refusal_sequence = self._decision_sequence
            return False
        filing = self._home_visit.file(request)
        if filing == "rejected" or self._home_visit.request is None:
            rejection = None
            report = self._home_visit.consume_report()
            if report is not None:
                marker = report.defect or report.outcome
                rejection = marker
                self._pending_home_visit_report = (
                    f"home-visit:{report.request.requester}:{marker}"
                )
            self._home_route_refusal = self._record_home_route_refusal(
                derived=f"{request.kind.value}:{request.requester}",
                filing=filing,
                rejection=rejection,
                begin_approach=None,
            )
            self._home_route_refusal_sequence = self._decision_sequence
            return False
        began = self._home_visit.begin_approach(self._decision_sequence)
        if not began:
            self._home_route_refusal = self._record_home_route_refusal(
                derived=f"{request.kind.value}:{request.requester}",
                filing=filing,
                rejection=None,
                begin_approach=False,
            )
            self._home_route_refusal_sequence = self._decision_sequence
        return began

    def _record_home_route_refusal(
        self,
        *,
        derived: str | None,
        filing: str | None,
        rejection: str | None,
        begin_approach: bool | None,
    ) -> dict[str, object]:
        """Describe an observed Home-route refusal without changing its executor."""
        visit = self._home_visit
        return {
            "derived": derived,
            "filing": filing,
            "rejection": rejection,
            "begin_approach": begin_approach,
            "executor_state": visit.state.name,
            "attempts_used": visit.attempts_used,
            "queued": len(visit.queued),
        }

    def home_route_refusal_state(self) -> dict[str, object] | None:
        """Return only a refusal observed during the current decision."""
        if (
            getattr(self, "_home_route_refusal_sequence", None)
            != self._decision_sequence
        ):
            return None
        return getattr(self, "_home_route_refusal", None)

    def _prepare_home_visit_operation(
        self, action: str, identity: tuple, evidence: tuple
    ) -> bool:
        """Authorize exactly one Home operation from fresh address evidence."""
        rebuilt = getattr(self, "_home_visit", None) is None
        if rebuilt:
            # Checkpoint/restored policies created before this structural field
            # visibly re-file from the current observation.
            self._home_visit = HomeVisitExecutor(CALIBRATION_HOME_VISIT_LIMIT)
        if not hasattr(self, "_pending_home_visit_report"):
            self._pending_home_visit_report = None
        if rebuilt:
            self._pending_home_visit_report = (
                "home-visit:atomic-home-composer:restart-refile-required"
            )
            return False
        visit = self._home_visit
        if visit.state in {HomeVisitState.REPORTED, HomeVisitState.DEFECT}:
            report = visit.consume_report()
            if report is not None:
                marker = report.defect or report.outcome
                self._pending_home_visit_report = (
                    f"home-visit:{report.request.requester}:{marker}"
                )
        if (
            visit.state == HomeVisitState.EXIT_PENDING
            and self._home_atomic_withdraw_pending is None
            and self._home_atomic_deposit_pending is None
        ):
            # Compatibility for direct composer callers: production consumes
            # the outside delta in _choose_key before reaching this method.
            visit.observe_outside(effect_observed=True)
            report = visit.consume_report()
            if report is not None:
                self._pending_home_visit_report = (
                    f"home-visit:{report.request.requester}:{report.outcome}"
                )
        request = visit.request
        if visit.entry_pending:
            return False
        while (
            request is not None
            and request.item_identity != identity
            and visit.report_unoperated("superseded-before-operation")
        ):
            report = visit.consume_report()
            if report is not None:
                self._pending_home_visit_report = (
                    f"home-visit:{report.request.requester}:{report.outcome}"
                )
            # consume_report() may promote a queued request.  Reconcile that
            # value too; otherwise the desired request is queued behind the
            # promoted stale request and authorization uses the wrong identity.
            request = visit.request
        if request is None:
            kind = (
                HomeVisitKind.WITHDRAW if action == "take"
                else HomeVisitKind.DEPOSIT
            )
            try:
                visit.file(PhysicalHomeVisitRequest(
                    kind,
                    "atomic-home-composer",
                    identity,
                    address=identity if action == "take" else None,
                ))
            except ValueError:
                return False
            if visit.request is None or not visit.begin_approach(
                self._decision_sequence
            ):
                report = visit.consume_report()
                if report is not None:
                    marker = report.defect or report.outcome
                    self._pending_home_visit_report = (
                        f"home-visit:{report.request.requester}:{marker}"
                    )
                return False
            request = visit.request
        expected = request.item_identity
        compatible = expected == identity or (
            request.kind == HomeVisitKind.EQUIPMENT_MUTATION
            and str(expected).startswith("equipment")
        )
        if not compatible:
            return False
        visit.observe_outside_ready(evidence, self._decision_sequence)
        if not visit.record_operation(action, identity, self._decision_sequence):
            return False
        return visit.post_exit()

    def consume_home_knowledge(self, items: tuple[InventoryItem, ...]) -> bool:
        """Consume the complete Home list returned by the emitter's ``~9``."""
        self._home_knowledge_items = tuple(items)
        self._home_knowledge_valid_before = len(items)
        self._home_knowledge_current = True
        self._home_knowledge_invalidated = False
        self._equipment_catalog.complete_home_scan(items)
        self._home_star_remove_curse_count = sum(
            item.count
            for item in items
            if item.tval == TVAL_SCROLL
            and item.sval == SV_SCROLL_STAR_REMOVE_CURSE
        )
        self._home_knowledge_scan_inflight = False
        self._home_scan_source = "~9"
        self._home_scan_item_count = len(items)
        self._home_errand.observe_knowledge(True)
        return True

    @staticmethod
    def _open_home_page_is_complete(snapshot: Snapshot) -> bool:
        """Whether the displayed page proves it contains the whole Home."""
        store = snapshot.store
        return bool(
            store is not None
            and store.store_type == STORE_HOME
            and store.page_top == 0
            and store.page_size is not None
            and store.page_size > 0
            and store.stock_num is not None
            and store.stock_num <= store.page_size
            and len(store.items) == store.stock_num
        )

    def _record_digger_home_withdraw_failure(
        self, signature: tuple[str, int, int] | None
    ) -> None:
        if signature is not None and any(
            owned.origin == "home"
            and owned.item.is_digging_tool
            and self._item_signature(owned.item) == signature
            for owned in self._equipment_catalog.items
        ):
            self._digger_home_withdraw_failures += 1

    def _has_withdrawable_digging_tool(self, snapshot: Snapshot) -> bool:
        return self._has_digging_tool(snapshot) or any(
            owned.origin == "home" and owned.item.is_digging_tool
            for owned in self._equipment_catalog.items
        )

    def _has_withdrawable_treasure_detection(self, snapshot: Snapshot) -> bool:
        if self._count_treasure_detection_scrolls(snapshot) > 0:
            return True
        return bool(
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and any(it.is_treasure_detection_scroll for it in snapshot.store.items)
        )

    def consume_pending_home_visit_report(self) -> str | None:
        """Return the terminal Home visit report for this decision, once."""
        report = self._pending_home_visit_report
        self._pending_home_visit_report = None
        return report

    def consume_pending_home_procurement_fallthrough_report(
        self,
    ) -> dict[str, str] | None:
        """Return a legal Home-procurement fallthrough once, then clear it."""
        case = self._home_procurement_fallthrough
        equivalence = self._home_procurement_fallthrough_equivalence
        self._home_procurement_fallthrough = None
        self._home_procurement_fallthrough_equivalence = None
        if case is None:
            return None
        return {
            "case": case,
            "classification": (
                "legal-static-no-home"
                if case == "town-without-home"
                else "legal-fresh-catalogue-absence"
            ),
            "need_equivalence": equivalence or "item:exact-tval-sval",
        }

    def _home_available(self, snapshot: Snapshot) -> bool:
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            return True
        self._refresh_town_facts(snapshot)
        return bool(self._town_store_positions.get(STORE_HOME))

    def _home_available_for_probe(self, snapshot: Snapshot) -> bool:
        """Read Home availability without warming incremental town-fact state."""
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            return True
        if self._town_store_positions.get(STORE_HOME):
            return True
        return any(
            grid.store_number == STORE_HOME for grid in snapshot.grids.values()
        )

    def _current_town_has_home(self, snapshot: Snapshot) -> bool:
        """Static Home classification; unknown towns fail closed."""
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            return True
        if snapshot.town_id in TOWN_IDS_WITH_HOME:
            return True
        if snapshot.town_id == ZUL_TOWN_ID:
            return False
        if snapshot.town_id in {None, -1}:
            # Legacy/map-shaped fixtures omit the emitter field entirely;
            # observed topology remains authoritative for that absence case.
            self._refresh_town_facts(snapshot)
            return bool(self._town_store_positions.get(STORE_HOME))
        # A present but unrecognised emitter ID must not authorize a purchase.
        return True

    def _home_catalog_routable(self, snapshot: Snapshot) -> bool:
        """Whether this visit can still advance the Home catalog."""
        return (
            self._home_available(snapshot)
            and STORE_HOME not in self._town_store_attempted
            and STORE_HOME not in self._town_visit_ledger.blocked_stores
        )

    def _retention_reservation(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> int:
        """The single authority for how much of a pack stack must remain.

        Every stash, sale, and destruction path asks this view.  Quantities are
        allocated in pack order so duplicate stacks share one aggregate target.
        """
        return self._retention_reservation_detail(snapshot, item)[0]

    def _retention_reservation_detail(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> tuple[int, str | None]:
        """Return retention plus the narrow weakest-ammo fallback."""
        baseline = self._retention_reservation_baseline_detail(snapshot, item)
        launcher = self._equipped_launcher(snapshot)
        retired_town_owners = set(
            getattr(
                getattr(self, "_town_turn_arbiter", None), "_retired", ()
            )
        )
        preparation = getattr(self, "_equipment_optimization_preparation", None)
        failed_home_route = (
            tuple(getattr(preparation, "blockers", ()))
            == ("equipment-transaction-failed",)
            and self._equipment_transaction_session is None
            and (
                STORE_HOME in self._town_store_attempted
                or self._town_visit_ledger.unsatisfied_passes[STORE_HOME] > 0
                or self._town_visit_ledger.approach_fails[STORE_HOME] > 0
            )
        )
        if (
            launcher is None
            or not item.is_ammo
            or item.tval != launcher.ammo_tval
            or self._equipment_retired_worn_item_ids
            or "equipment-opt" in retired_town_owners
            or "equipment-txn" in retired_town_owners
            or failed_home_route
        ):
            return baseline

        matching = [
            candidate for candidate in snapshot.inventory
            if candidate.tval == launcher.ammo_tval and candidate.count > 0
        ]
        def ammo_damage(candidate: InventoryItem) -> float:
            average = (
                candidate.damage_dice_num * (candidate.damage_dice_sides + 1) / 2
                if candidate.damage_dice_num > 0 and candidate.damage_dice_sides > 0
                else 0.0
            )
            return average + candidate.to_d

        ranked = sorted(
            matching,
            key=lambda candidate: (ammo_damage(candidate), candidate.slot),
        )
        if not ranked or ammo_damage(ranked[0]) >= ammo_damage(ranked[-1]):
            return baseline
        return (
            (0, None)
            if ranked[0] is item
            else (item.count, "ammo:retained-better")
        )

    def _retention_reservation_baseline_detail(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> tuple[int, str | None]:
        """Return the existing reservation together with its observed branch."""
        signature = self._item_signature(item)
        obsolete_oil = item.is_oil and self._owns_usable_permanent_light(snapshot)
        capped_emergency_potion = (
            item.tval == TVAL_POTION
            and item.sval in {SV_POTION_SPEED, SV_POTION_HEALING}
        )
        if (
            signature in self._town_visit_purchases
            and not capped_emergency_potion
            and not obsolete_oil
        ):
            return item.count, "visit-purchase"

        target = 0
        branch = None
        matches = lambda candidate: False
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        strategy = (
            self._carry_procurement_strategy(snapshot)
            or self._quest_strategy_for_errand_or_floor(snapshot)
        )
        mining_planned = self._fundraising_mode in {"prepare", "mine", "scavenge"} or (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.gold < FUNDRAISING_START_GOLD
        )
        if item.is_recall_scroll:
            target = max(
                ledger["recall"].required_departure,
                self._recall_required_target(snapshot),
            )
            matches = lambda candidate: candidate.is_recall_scroll
            branch = "supply-ledger:recall"
        elif item.is_teleport_scroll:
            target = ledger["teleport"].required_departure
            matches = lambda candidate: candidate.is_teleport_scroll
            branch = "supply-ledger:teleport"
        elif item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            target = ledger["cure"].required_departure
            matches = lambda candidate: (
                candidate.tval == TVAL_POTION
                and candidate.sval == SV_POTION_CURE_CRITICAL
            )
            branch = "supply-ledger:cure"
        elif item.is_oil:
            target = ledger["oil"].required_departure
            matches = lambda candidate: candidate.is_oil
            branch = "supply-ledger:oil"
        elif (
            item.is_food
            and item.aware
            and item.sval >= FOOD_MIN_SVAL
            and snapshot.player.food_type != FOOD_TYPE_MANA
        ):
            target = ledger["food"].required_departure
            matches = lambda candidate: (
                candidate.is_food and candidate.aware and candidate.sval >= FOOD_MIN_SVAL
            )
            branch = "supply-ledger:food"
        elif item.is_torch:
            if self._matching_ammo(snapshot) is not None:
                return 0, None
            if not item.known or item.fuel <= 0:
                return 0, None
            target = TORCH_THROW_TARGET
            matches = lambda candidate: (
                candidate.is_torch and candidate.known and candidate.fuel > 0
            )
            branch = "torch-throw"
        elif item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED:
            target = EMERGENCY_POTION_CARRY_TARGET
            matches = lambda candidate: (
                candidate.tval == TVAL_POTION
                and candidate.sval == SV_POTION_SPEED
            )
            branch = "emergency-potion:speed"
        elif item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING:
            target = EMERGENCY_POTION_CARRY_TARGET
            matches = lambda candidate: (
                candidate.tval == TVAL_POTION
                and candidate.sval == SV_POTION_HEALING
            )
            branch = "emergency-potion:healing"
        elif item.is_ammo:
            launcher = self._equipped_launcher(snapshot)
            quest_target = (
                self._quest_carry_target_for_item(
                    snapshot, item, strategy.required_force
                )
                if strategy is not None
                else None
            )
            if (
                launcher is not None
                and item.tval != launcher.ammo_tval
                and quest_target is None
            ):
                # Carry one ranged system.  Quest force requirements follow the
                # selected launcher.  A fixed-quest reservation takes precedence:
                # town preparation may intentionally carry bolts while a sling is
                # still equipped, before the quest crossbow is wielded.
                return 0, None
            if launcher is not None and item.tval == launcher.ammo_tval:
                retained_slots = self._retained_ammo_slots(
                    snapshot, launcher.ammo_tval
                )
                if item.slot not in retained_slots:
                    # The two-slot ceiling is stronger than a quest's aggregate
                    # ammo target.  Otherwise the force reservation below simply
                    # re-reserves every tiny enchanted stack we rejected here.
                    return 0, None
                target = AMMO_CARRY_TARGET
                matches = lambda candidate: (
                    candidate.tval == launcher.ammo_tval
                    and candidate.slot in retained_slots
                )
                branch = "retained-ammo"
        elif item.is_launcher:
            launcher = self._equipped_launcher(snapshot)
            quest_target = (
                self._quest_carry_target_for_item(
                    snapshot, item, strategy.required_force
                )
                if strategy is not None
                else None
            )
            if (
                launcher is not None
                and item.ammo_tval is not None
                and item.ammo_tval != launcher.ammo_tval
                and quest_target is None
            ):
                return 0, None
        # Keep this predicate identical to _next_required_store_type's town-cycle
        # trigger.  That router can activate fundraising later in the same visit,
        # after Home has already asked this retention authority what may be stashed.
        elif item.is_treasure_detection_scroll and mining_planned:
            target = self._mining_detection_scroll_target(snapshot)
            matches = lambda candidate: candidate.is_treasure_detection_scroll
            branch = "mining:detection"
        elif item.is_digging_tool and mining_planned:
            pack_diggers = [it for it in snapshot.inventory if it.is_digging_tool]
            equipped_count = sum(
                1 for equipped in snapshot.equipment if equipped.is_digging_tool
            )
            keep_slots = {
                candidate.slot
                for candidate in sorted(
                    pack_diggers,
                    key=lambda it: (
                        it.pval,
                        int(it.is_artifact),
                        int(it.is_ego),
                        it.sval,
                    ),
                    reverse=True,
                )[: max(0, 2 - equipped_count)]
            }
            return (
                (item.count, "mining:digging-tool")
                if item.slot in keep_slots
                else (0, None)
            )
        elif snapshot.player.food_type == FOOD_TYPE_MANA and item.is_wand_staff:
            # Charged devices are MANA food; Identify charges below the casting
            # floor are reserved for identification rather than edible surplus.
            if (
                item.known
                and item.charges > 0
                and item.slot == self._device_food_reserve_slot(snapshot)
            ):
                return item.count, "mana-device"

        if strategy is not None:
            force = strategy.required_force
            carry_target = self._quest_carry_target_for_item(snapshot, item, force)
            if carry_target is not None:
                carry_name, _, required = carry_target
                matches = lambda candidate: (
                    (candidate_target := self._quest_carry_target_for_item(
                        snapshot, candidate, force
                    )) is not None
                    and candidate_target[0] == carry_name
                )
                equipped = sum(
                    candidate.count
                    for candidate in snapshot.equipment
                    if item.is_launcher and matches(candidate)
                )
                target = max(target, required - equipped)
                branch = f"carry-strategy:{carry_name}"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED:
                target = min(
                    EMERGENCY_POTION_CARRY_TARGET,
                    max(target, int(force.get("speed_potions", 0))),
                )
                matches = lambda candidate: (
                    candidate.tval == TVAL_POTION and candidate.sval == SV_POTION_SPEED
                )
                branch = "carry-strategy:speed-potions"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING:
                target = min(
                    EMERGENCY_POTION_CARRY_TARGET,
                    max(target, int(force.get("heal_potions", 0))),
                )
                matches = lambda candidate: (
                    candidate.tval == TVAL_POTION
                    and candidate.sval == SV_POTION_HEALING
                )
                branch = "carry-strategy:heal-potions"
        if target <= 0:
            return 0, None
        before = 0
        for candidate in snapshot.inventory:
            if candidate.slot == item.slot:
                break
            if matches(candidate):
                before += candidate.count
        reservation = min(item.count, max(0, target - before))
        return reservation, (branch or "unlabelled") if reservation > 0 else None

    def retention_reservation_state(self, snapshot: Snapshot) -> dict[str, object]:
        """Describe pack retention and an active deposit collision, read-only."""
        reservations = []
        by_signature = {}
        for item in snapshot.inventory:
            reservation, branch = self._retention_reservation_detail(snapshot, item)
            if reservation <= 0:
                continue
            signature = self._item_signature(item)
            by_signature[signature] = branch
            reservations.append({
                "signature": signature,
                "tval": item.tval,
                "sval": item.sval,
                "count": item.count,
                "reservation": reservation,
                "branch": branch,
            })

        conflict = None
        session = self._equipment_transaction_session
        action = session.current_action if session is not None else None
        if action is not None and action.kind == "deposit":
            current = next((
                item for item in snapshot.inventory
                if item.is_equipment
                and equipment_identity(item) == action.item_identity
            ), None)
            signature = self._item_signature(current) if current is not None else None
            conflict = {
                "session_deposit_identity": action.item_identity,
                "in_keep_set": signature in by_signature if signature is not None else False,
                "reserving_branch": by_signature.get(signature),
            }
        return {
            "retention_reservations": reservations,
            "deposit_keep_conflict": conflict,
        }

    def _retention_surplus(self, snapshot: Snapshot, item: InventoryItem) -> int:
        if self._equipment_transaction_owns_item(item):
            return 0
        return max(0, item.count - self._retention_reservation(snapshot, item))

    def _entire_stack_is_surplus(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        """Return whether a whole-stack operation may consume this item."""
        return item.count > 0 and self._retention_surplus(snapshot, item) == item.count

    @staticmethod
    def _inventory_weight_limit(snapshot: Snapshot) -> int | None:
        if not snapshot.player.stat_index:
            return None
        strength_index = max(
            0, min(snapshot.player.stat_index[0], len(ADJ_STR_WEIGHT_LIMIT) - 1)
        )
        limit = ADJ_STR_WEIGHT_LIMIT[strength_index] * 50
        if snapshot.player.class_id == PLAYER_CLASS_BERSERKER:
            limit = limit * 3 // 2
        return limit

    def _inventory_overweight(self, snapshot: Snapshot) -> bool:
        limit = self._inventory_weight_limit(snapshot)
        return limit is not None and self._inventory_weight(snapshot) > limit

    def _can_add_item_without_overweight(
        self, snapshot: Snapshot, item: InventoryItem | StoreItem,
        *, quantity: int | None = None,
    ) -> bool:
        limit = self._inventory_weight_limit(snapshot)
        if limit is None:
            return True
        current_weight = self._inventory_weight(snapshot)
        if current_weight > limit:
            # This purchase cannot create an overload which already exists.
            # The town shedding owner, not an unrelated shop, owns recovery.
            return True
        added_weight = max(0, item.weight) * max(
            1, item.count if quantity is None else quantity
        )
        return current_weight + added_weight <= limit

    def _overweight_home_deposit(
        self, snapshot: Snapshot
    ) -> InventoryItem | None:
        if not self._inventory_overweight(snapshot):
            return None

        blocking_categories = {
            spec.category
            for spec in self._town_need_registry()
            if spec.departure_blocking
        }

        def required_supply(item: InventoryItem) -> bool:
            categories = set(self._cross_town_item_categories(item))
            categories.update(
                category.split(":", 1)[0]
                for category in tuple(categories)
                if category.startswith(("identification-source:", "stat-restore:"))
            )
            strategy = (
                self._carry_procurement_strategy(snapshot)
                or self._quest_strategy_for_errand_or_floor(snapshot)
            )
            if (
                strategy is not None
                and self._quest_carry_target_for_item(
                    snapshot, item, strategy.required_force
                ) is not None
            ):
                categories.update(
                    category
                    for category in blocking_categories
                    if category.startswith("quest-")
                )
            mining_planned = self._fundraising_mode in {
                "prepare", "mine", "scavenge"
            } or (
                snapshot.in_town
                and snapshot.player.class_id >= 0
                and snapshot.player.gold < FUNDRAISING_START_GOLD
            )
            if mining_planned:
                if item.is_treasure_detection_scroll:
                    categories.add("fundraising-detection")
                if item.is_digging_tool:
                    categories.add("fundraising-digger")
                if item.is_light:
                    categories.add("fundraising-light")
            return bool(categories & blocking_categories)

        def unreserved_required_supply(item: InventoryItem) -> bool:
            return (
                required_supply(item)
                and self._retention_reservation(snapshot, item) == 0
            )

        def priority(item: InventoryItem) -> tuple[int, int, str]:
            noncombat_bulk = not (
                item.is_equipment
                or item.is_ammo
                or item.is_potion
                or item.is_scroll
                or item.is_wand_staff
                or item.is_food
                or item.is_oil
                or item.is_light
                or item.is_digging_tool
                or item.is_bounty
                or self._is_high_value_book(item)
            )
            category = (
                0
                if noncombat_bulk
                else 1
                if item.is_ammo
                else 2
                if item.is_equipment
                else 3
            )
            removable_weight = item.weight * self._retention_surplus(snapshot, item)
            return category, -removable_weight, item.slot

        candidates = [
            item
            for item in snapshot.inventory
            if item.weight > 0
            and self._retention_surplus(snapshot, item) > 0
            # A blocking supply without a retention target is not surplus merely
            # because the retention table does not yet quantify its need.
            and not unreserved_required_supply(item)
            and not item.is_bounty
            and not self._is_wanted_jewelry(snapshot, item)
            and self._item_signature(item) not in self._home_rejected_deposits
            and self._item_signature(item) not in self._home_pending_batch
            and item.slot != self._home_pending_slot
            and item.slot != self._pending_disposal_slot
        ]
        required = [item for item in candidates if required_supply(item)]
        if required:
            excess = (
                self._inventory_weight(snapshot)
                - (self._inventory_weight_limit(snapshot) or 0)
            )
            # A Home put ends the visit.  First prefer a surplus which clears the
            # excess by itself; otherwise take the largest removable weight so
            # the greedy sequence uses the fewest such full visits it can.
            return min(
                required,
                key=lambda item: (
                    item.weight * self._retention_surplus(snapshot, item) < excess,
                    -item.weight * self._retention_surplus(snapshot, item),
                    item.slot,
                ),
            )
        return min(candidates, key=priority, default=None)

    def _home_deposit_candidate(
        self, item: InventoryItem, snapshot: Snapshot | None = None
    ) -> bool:
        if (
            item.tval == TVAL_SCROLL
            and item.sval == SV_SCROLL_STAR_REMOVE_CURSE
            and self._star_remove_curse_reserve_deposit_pending
            and self._star_remove_curse_reserve_deposit_inflight is None
            and not self._star_remove_curse_reserve_withdraw_pending
        ):
            return True
        if snapshot is not None and self._retention_surplus(snapshot, item) <= 0:
            return False
        # A GOOD melee weapon — identified ego/artifact or one with real +to-hit/+to-dam/
        # +pval — is protected from Home-shelving ONLY while it might still be needed
        # for re-arm: mining swaps the digger into the main hand, displacing the real
        # combat weapon to the pack, and stashing THAT strands the character fighting
        # on a pickaxe (the bug the user hit — the Lucerne Hammer (2d5)(+16,+9) et al.
        # ended up in the Home while a Pick stayed wielded). That risk exists only
        # while no real (non-digger) melee weapon is wielded — a digger wielded, or
        # the main hand empty. Once a real weapon IS wielded, a spare good weapon is
        # no longer needed there: it becomes ordinary spare_equipment below, shelved
        # like any other duplicate, and _home_rearm_key can withdraw it again if a
        # later mining run needs it. No snapshot (a handful of item-only call sites)
        # falls back to the old, conservative always-protect behaviour. Unidentified
        # or mundane spare weapons still shelve/sell regardless.
        good_weapon = item.is_melee_weapon and item.known and (
            item.is_ego
            or item.is_artifact
            or item.to_h > 0
            or item.to_d > 0
            or item.pval > 0
        )
        # Spare wearable gear (armour, rings, amulets, junk weapons) is shelved at Home —
        # the equipment optimiser wields the best and this stashes the rest.
        equipment_deposit_shape = self._spare_equipment_deposit_shape(item)
        spare_equipment = (
            equipment_deposit_shape
            and not item.is_digging_tool
            and not good_weapon
            and self._target_loadout_known()
        )
        protected_unknown_consumable = (
            self._deepest_level >= 20
            and (item.is_potion or item.is_scroll)
            and not item.aware
        )
        # Treasure Detection scrolls and digging tools are mining gear: carried only
        # while fundraising (mining level 1). On a normal diving run they are dead
        # weight, so stash them at home instead of hauling them down.
        mining_gear_off_duty = (
            item.is_treasure_detection_scroll or item.is_digging_tool
        ) and self._fundraising_mode not in {"prepare", "mine", "scavenge"}
        # Dead weight: an identified non-consumable, non-device item carried through
        # several whole dives without ever being used (see _track_idle_items). Stash
        # it at Home to free pack space and cut full-pack returns.
        idle_dead_weight = (
            self._item_idle_dives.get(self._item_signature(item), 0) >= UNUSED_DIVE_LIMIT
            and not self._idle_deposit_protected(item)
        )
        # A wand/staff drained to 0 charges is pure junk — no utility, and no MANA
        # charge-food left in it — so stash it at once (do not wait out the idle
        # counter). The magic-missile wand (0 回分) the user flagged is exactly this.
        depleted_device = item.is_wand_staff and item.known and item.charges <= 0
        reserved_stack_surplus = (
            snapshot is not None
            and self._retention_surplus(snapshot, item) > 0
            and (
                item.is_ammo
                or (
                    (
                        item.is_torch
                        or (
                            item.tval == TVAL_POTION
                            and item.sval in {SV_POTION_SPEED, SV_POTION_HEALING}
                        )
                    )
                    and self._retention_reservation(snapshot, item) > 0
                )
            )
        )
        throwing_torches_replaced = (
            snapshot is not None
            and item.is_torch
            and self._matching_ammo(snapshot) is not None
        )
        obsolete_oil = (
            snapshot is not None
            and item.is_oil
            and self._owns_usable_permanent_light(snapshot)
        )
        incompatible_ammo = (
            snapshot is not None
            and item.is_ammo
            and (launcher := self._equipped_launcher(snapshot)) is not None
            and item.tval != launcher.ammo_tval
        )
        return (
            spare_equipment
            or protected_unknown_consumable
            or mining_gear_off_duty
            or idle_dead_weight
            or depleted_device
            or reserved_stack_surplus
            or throwing_torches_replaced
            or obsolete_oil
            or incompatible_ammo
        )

    def _spare_equipment_deposit_shape(self, item: InventoryItem) -> bool:
        """Item shape used by Home's spare-equipment disposal branch."""
        return item.is_equipment and not item.is_light

    def _idle_deposit_protected(self, item: InventoryItem) -> bool:
        # Keep only what the bot genuinely relies on; everything else that has gone
        # unused for UNUSED_DIVE_LIMIT dives is low-use dead weight the idle rule may
        # stash. Protected: the survival kit (recall/teleport/cure-critical/food/
        # light/oil/digging) and the secondary Phase-Door escape; a CHARGED device
        # (MANA charge-food / identify staff / utility wand — a DEPLETED 0-charge one
        # is NOT); stat gain/restore potions (drunk when able); spare equipment (the
        # equipment rule stashes that itself); and unidentified items (identify
        # routine owns those). What is now idle-stashable that was NOT before: resist
        # potions, redundant identify scrolls, enchant scrolls, depleted wands, and
        # other identified low-use consumables — the items the user flagged.
        if not item.aware or item.is_equipment or self._is_high_value_book(item):
            return True
        if self._survival_essential(item):
            return True
        if item.is_scroll and item.sval == SV_SCROLL_PHASE_DOOR:
            return True
        if item.is_wand_staff and item.charges > 0:
            return True
        if item.is_potion and (
            item.sval in STAT_GAIN_POTION_SVALS
            or item.sval in RESTORE_POTION_SVAL_BY_STAT.values()
        ):
            return True
        return False

    def _home_deposit_key(
        self,
        snapshot: Snapshot,
        deposit: InventoryItem,
        *,
        forced_count: int | None = None,
    ) -> str:
        sig = (
            deposit.slot,
            self._item_signature(deposit),
            deposit.count,
            deposit.charges,
            len(snapshot.inventory),
            snapshot.player.gold,
        )
        if sig == self._last_sell_sig:
            self._store_sell_stuck_count += 1
        else:
            self._last_sell_sig = sig
            self._store_sell_stuck_count = 0
        if self._store_sell_stuck_count >= STORE_STUCK_LIMIT:
            # Stop this visit's deposit errand without claiming the Home is full;
            # otherwise every eligible pack item consumes the same retry budget.
            self._home_rejected_deposits.add(self._item_signature(deposit))
            self._home_deposit_abandoned = True
            self._store_sell_stuck_count = 0
            self._last_sell_sig = None
            self.last_reason = "home:deposit-rejected"
            return LEAVE_STORE_KEY
        self.last_reason = "home:deposit"
        deposit_count = (
            forced_count
            if forced_count is not None
            else deposit.count
            if self._calibration_phase == "deposit"
            else self._retention_surplus(snapshot, deposit)
        )
        if self._calibration_phase == "deposit":
            signature = self._item_signature(deposit)
            if signature not in self._calibration_restore_signatures:
                self._calibration_restore_signatures.append(signature)
        if (
            deposit.tval == TVAL_SCROLL
            and deposit.sval == SV_SCROLL_STAR_REMOVE_CURSE
            and self._star_remove_curse_reserve_deposit_pending
        ):
            signature = self._item_signature(deposit)
            self._star_remove_curse_reserve_deposit_inflight = (
                signature,
                self._inventory_signature_count(snapshot, signature),
            )
        quantity = f"{deposit_count}\r" if deposit_count > 1 else ""
        return SELL_KEY + deposit.slot + quantity

    def _atomic_home_withdraw_key(
        self, snapshot: Snapshot, step: Position
    ) -> str | None:
        """Bind one catalogued Home take to fresh entry, operation, and exit."""
        if (
            snapshot.store is not None
            or self._shopping_approach_store_type != STORE_HOME
            or self._home_atomic_withdraw_pending is not None
            or (
                getattr(self, "_store_entrance_step_off", None) is not None
                and self._store_entrance_step_off[0] != self._decision_sequence
            )
        ):
            return None
        entrance = snapshot.grid_at(snapshot.player.position)
        if entrance is None or entrance.store_number != STORE_HOME:
            return None
        session = self._equipment_transaction_session
        action = session.current_action if session is not None else None
        withdrawal_requested = bool(
            self._calibration_restore_signatures
            or self._home_errand.active
            or self._home_pending_item is not None
            or self._home_pending_batch
            or (action is not None and action.kind == "withdraw")
        )
        if not withdrawal_requested:
            return None
        if not self._home_knowledge_current:
            self.last_reason = (
                self._home_errand.reason("await-fresh-knowledge")
                if self._home_errand.active
                else "home:await-fresh-knowledge"
            )
            return None
        if not self._home_page_size:
            self.last_reason = "home:await-page-size"
            return None

        signature: tuple[str, int, int] | None = None
        restore_owner_signature: tuple[str, int, int] | None = None
        transaction_identity: tuple | None = None
        quantity: int | None = None
        reason = "home:atomic-withdraw"
        address_slots = tuple(
            (index, item)
            for index, item in enumerate(self._home_knowledge_items)
            if index < self._home_knowledge_valid_before
        )
        observed_signatures = {self._item_signature(item) for _, item in address_slots}
        if self._home_errand.active and self._home_errand.request is not None:
            signature = self._home_errand.request.signature
            quantity = self._home_errand.request.quantity
            reason = self._home_errand.reason("atomic-withdraw")
        # A specifically queued Home item is the current town stop's operation.
        # In particular, the fundraising kit must not sit behind the calibration
        # restore list: every successful restore invalidates later addresses until
        # the next ~9 response, so prioritising restore here starved later diggers
        # forever in the captured 34-item Home.
        if signature is None and self._home_pending_item in observed_signatures:
            signature = self._home_pending_item
        if signature is None and self._calibration_worn_before:
            redress_identities = {
                identity for _slot, identity in self._calibration_worn_before
            }
            redress_matches = [
                item for _, item in address_slots
                if item.is_equipment
                and equipment_identity(item) in redress_identities
            ]
            if len(redress_matches) == 1:
                signature = self._item_signature(redress_matches[0])
                restore_owner_signature = next(
                    (
                        owner for owner in self._calibration_restore_signatures
                        if owner == signature
                        or owner[1:] == signature[1:]
                    ),
                    None,
                )
                reason = "calibration:atomic-restore-withdraw"
        if signature is None:
            for restore_signature in self._calibration_restore_signatures:
                if restore_signature in observed_signatures:
                    signature = restore_signature
                    restore_owner_signature = restore_signature
                    reason = "calibration:atomic-restore-withdraw"
                    break
        if signature is None and self._home_pending_batch:
            batch_signature = self._home_pending_batch[0]
            if batch_signature in observed_signatures:
                signature = batch_signature
        if signature is None and action is not None and action.kind == "withdraw":
            transaction_slot = next(
                (
                    (index, item)
                    for index, item in address_slots
                    if item.is_equipment
                    and equipment_identity(item) == action.item_identity
                ),
                None,
            )
            if transaction_slot is not None:
                signature = self._item_signature(transaction_slot[1])
                transaction_identity = action.item_identity
                reason = "equipment-transaction:atomic-withdraw"
        if signature is None:
            unaddressable_signatures = {
                candidate
                for candidate in (
                    self._home_pending_item,
                    *self._calibration_restore_signatures,
                    *self._home_pending_batch,
                    (
                        self._home_errand.request.signature
                        if self._home_errand.active
                        and self._home_errand.request is not None
                        else None
                    ),
                )
                if candidate is not None
            }
            complete_open_page_match = (
                self._home_scan_source == "observed-home-page"
                and any(
                    self._item_signature(item) in unaddressable_signatures
                    or (
                        action is not None
                        and action.kind == "withdraw"
                        and item.is_equipment
                        and equipment_identity(item) == action.item_identity
                    )
                    for index, item in enumerate(self._home_knowledge_items)
                    if index >= self._home_knowledge_valid_before
                )
            )
            if complete_open_page_match:
                self._invalidate_home_observation()
                self.last_reason = "home:await-fresh-knowledge"
                return None
            self.last_reason = "home:atomic-withdraw-target-unobserved"
            deferred = self._defer_unobserved_home_withdrawal()
            self._record_digger_home_withdraw_failure(deferred)
            plan = self._town_errand_plan
            categories = (
                plan.need_categories.get(STORE_HOME, ())
                if plan is not None else ()
            )
            for category in categories:
                if category in {"identification-withdrawal", "equipment-work"}:
                    self._post_owner_expectation(
                        snapshot, f"home-withdrawal:{category}",
                        "inventory", "equipment",
                    )
            # We are already outside on the Home entrance.  Escape is a no-op
            # there and identical repost recovery only turns it into ESC/look
            # churn.  Make the failed visit observable by stepping off; normal
            # routing may then re-enter once, or use the two-failure fallback.
            return self._town_entrance_step_off_key(
                snapshot, "home:atomic-withdraw-target-unobserved"
            )
        if signature not in observed_signatures and self._home_errand.active:
            self._home_errand.observe_unaddressed_entry(
                self._town_store_visit_limit(STORE_HOME), "target-unobserved"
            )
            self.last_reason = self._home_errand.reason("target-unobserved")
            self._record_digger_home_withdraw_failure(signature)
            self._defer_unobserved_home_withdrawal(signature)
            return LEAVE_STORE_KEY
        if self._calibration_phase == "restore-supplies":
            for restore_signature in self._calibration_restore_signatures:
                if (
                    restore_signature != self._home_pending_item
                    and restore_signature not in self._home_pending_batch
                ):
                    self._home_pending_batch.append(restore_signature)
            self._home_procurement_batch_active = bool(self._home_pending_batch)
        selected = next(
            (
                (index, item)
                for index, item in reversed(address_slots)
                if self._item_signature(item) == signature
                and (
                    transaction_identity is None
                    or equipment_identity(item) == transaction_identity
                )
            ),
            None,
        )
        if selected is None:
            if self._home_errand.active:
                self._home_errand.observe_unaddressed_entry(
                    self._town_store_visit_limit(STORE_HOME), "slot-unobserved"
                )
                self.last_reason = self._home_errand.reason("slot-unobserved")
                self._record_digger_home_withdraw_failure(signature)
                self._defer_unobserved_home_withdrawal(signature)
            else:
                self.last_reason = "home:atomic-withdraw-slot-unobserved"
                deferred = self._defer_unobserved_home_withdrawal(signature)
                self._record_digger_home_withdraw_failure(deferred)
            return LEAVE_STORE_KEY
        index, item = selected
        page, page_pos = divmod(index, self._home_page_size)
        letter = self._home_page_letter(page_pos)
        if restore_owner_signature is not None:
            quantity = item.count
        if not letter or len(letter) != 1:
            if self._home_errand.active:
                self._home_errand.observe_unaddressed_entry(
                    self._town_store_visit_limit(STORE_HOME), "address-invalid"
                )
                self.last_reason = self._home_errand.reason("address-invalid")
                self._record_digger_home_withdraw_failure(signature)
                self._defer_unobserved_home_withdrawal(signature)
            else:
                self.last_reason = "home:atomic-withdraw-address-invalid"
                deferred = self._defer_unobserved_home_withdrawal(signature)
                self._record_digger_home_withdraw_failure(deferred)
            return LEAVE_STORE_KEY
        requested_quantity = (
            quantity
            if quantity is not None
            else getattr(self, "_home_pending_quantities", {}).get(signature)
            if signature in getattr(self, "_home_pending_quantities", {})
            else self._home_pending_quantity
            if self._home_pending_quantity is not None
            else 1
        )
        take_count = max(1, min(item.count, requested_quantity))
        # The completed address scan binds the shelf letter and stack count to
        # this one-shot entry.  A multi-item stack therefore proves that the
        # quantity prompt will consume this response before the leave key.
        quantity_suffix = f"{take_count}\r" if item.count > 1 else ""
        operation_key = (
            (" " * page)
            + BUY_KEY
            + letter
            + quantity_suffix
            + LEAVE_STORE_KEY
        )
        batch_entries = ()
        if (
            restore_owner_signature is not None
            and restore_owner_signature == signature
        ):
            free_slots = max(1, PACK_CAPACITY - len(snapshot.inventory))
            page_candidates = []
            for owner_signature in self._calibration_restore_signatures:
                match = next(
                    (
                        (owner_index, owner_item)
                        for owner_index, owner_item in reversed(address_slots)
                        if self._item_signature(owner_item) == owner_signature
                        and owner_index // self._home_page_size == page
                    ),
                    None,
                )
                if match is not None:
                    page_candidates.append((owner_signature, *match))
            page_candidates.sort(key=lambda entry: entry[1], reverse=True)
            page_candidates = page_candidates[:free_slots]
            if not any(
                owner_signature == restore_owner_signature
                for owner_signature, _owner_index, _owner_item in page_candidates
            ):
                page_candidates[-1:] = [
                    (restore_owner_signature, index, item)
                ]
                page_candidates.sort(key=lambda entry: entry[1], reverse=True)
            if len(page_candidates) > 1:
                batch_entries = tuple(
                    (
                        owner_signature,
                        self._inventory_signature_count(snapshot, owner_signature),
                        owner_item,
                        owner_item.count,
                        owner_index,
                    )
                    for owner_signature, owner_index, owner_item in page_candidates
                )
                commands = []
                for _owner_signature, owner_index, owner_item in page_candidates:
                    page_pos = owner_index % self._home_page_size
                    owner_letter = self._home_page_letter(page_pos)
                    owner_quantity = (
                        f"{owner_item.count}\r" if owner_item.count > 1 else ""
                    )
                    commands.append(BUY_KEY + owner_letter + owner_quantity)
                operation_key = (
                    (" " * page) + "".join(commands) + LEAVE_STORE_KEY
                )
        key = WAIT_KEY
        if session is not None and action is not None and action.kind == "withdraw":
            observation = replace(
                observe_equipment_transactions(snapshot), in_home=True
            )
            if not self._prepare_equipment_transaction_command(
                session,
                action,
                observation,
                key,
                (
                    "home-entrance",
                    getattr(snapshot, "turn", 0),
                    page,
                    letter,
                    action.item_identity,
                ),
            ):
                self.last_reason = "equipment-transaction:atomic-withdraw-refused"
                return LEAVE_STORE_KEY
        visit_identity = transaction_identity or signature
        if not self._prepare_home_visit_operation(
            "take",
            visit_identity,
            (
                tuple(self._item_signature(candidate) for candidate in self._home_knowledge_items),
                self._home_knowledge_valid_before,
                self._home_page_size,
            ),
        ):
            self.last_reason = "home-visit:withdraw-not-authorized"
            return None
        self._home_atomic_withdraw_pending = (
            signature,
            self._inventory_signature_count(snapshot, signature),
            item,
            take_count,
            batch_entries,
        ) if batch_entries else (
            signature,
            self._inventory_signature_count(snapshot, signature),
            item,
            take_count,
        )
        procurement_probe = getattr(self, "_home_procurement_probe", None)
        self._home_atomic_withdraw_procurement_class = (
            procurement_probe
            if (
                procurement_probe is not None
                and self._home_pending_item == signature
                and self._procurement_class_matches(item, procurement_probe)
            )
            else None
        )
        if session is not None and action is not None and action.kind == "withdraw":
            self._equipment_atomic_withdraw_leave_count = 0
        tracked = getattr(self, "_withdrawal_unsatisfied_for", None)
        if tracked is None or tracked[0] != signature:
            self._withdrawal_unsatisfied_for = (
                signature,
                self._inventory_signature_count(snapshot, signature),
                0,
                False,
            )
        self._home_atomic_withdraw_index = index
        self._home_atomic_withdraw_posted_turn = snapshot.turn
        if (
            self._home_errand.active
            and self._home_errand.request is not None
            and self._home_errand.request.signature == signature
        ):
            self._home_errand.post(
                self._inventory_signature_count(snapshot, signature)
            )
        if restore_owner_signature is not None and not batch_entries:
            self._calibration_restore_signatures.remove(restore_owner_signature)
        self._home_pending_quantity = None
        getattr(self, "_home_pending_quantities", {}).pop(signature, None)
        self._home_candidate_waiting = False
        self._home_withdrawal_queued = False
        self._home_entry_operation_posted = True
        self._home_history_inflight = None if batch_entries else (
            "withdraw",
            signature,
            len(snapshot.inventory),
            self._inventory_signature_count(snapshot, signature),
        )
        self._stage_home_operation(snapshot, operation_key)
        self.last_reason = reason
        return key

    def _observe_calibration_restore_batch(
        self, snapshot: Snapshot, pending: tuple
    ) -> None:
        """Reconcile one same-page calibration restore macro outside Home."""
        succeeded = []
        failed = []
        for entry in pending[4]:
            signature, before_count, _withdrawn, quantity, _index = entry
            after_count = self._inventory_signature_count(snapshot, signature)
            (succeeded if after_count >= before_count + quantity else failed).append(
                entry
            )
        if getattr(self, "_home_visit", None) is not None:
            self._home_visit.observe_outside(
                effect_observed=bool(succeeded) and not failed
            )
        self._home_atomic_withdraw_pending = None
        self._home_atomic_withdraw_procurement_class = None
        self._home_atomic_withdraw_posted_turn = None
        self._home_atomic_withdraw_index = None
        self._home_entry_operation_posted = False
        for signature, before_count, withdrawn, quantity, _index in succeeded:
            if signature in self._calibration_restore_signatures:
                self._calibration_restore_signatures.remove(signature)
            if signature in self._home_pending_batch:
                self._home_pending_batch.remove(signature)
            self._home_pending_quantities.pop(signature, None)
            self._equipment_catalog.record_home_withdrawal(
                withdrawn,
                intent=(snapshot.turn, signature, before_count, quantity),
            )
            self._home_disposal.record("withdraw", signature, snapshot.turn)
        self._home_procurement_batch_active = bool(self._home_pending_batch)
        self._invalidate_home_observation()
        if succeeded:
            self._refresh_carried_equipment_catalog(snapshot)
        if self._calibration_restore_signatures:
            self._rearm_town_store_for_new_work(
                STORE_HOME, release_visit_bound=True
            )
            self.last_reason = "home:process-next-batch-item"
        elif failed:
            self.last_reason = "home:atomic-withdraw-failed"

    def _confirm_home_withdrawal_address(
        self, signature: tuple[str, int, int], posted_index: int | None
    ) -> None:
        """Apply shelf-slot movement only after a Home take is observed."""
        index = posted_index
        if index is None:
            index = next(
                (
                    candidate_index
                    for candidate_index, item in reversed(tuple(enumerate(
                        self._home_knowledge_items
                    )))
                    if candidate_index < self._home_knowledge_valid_before
                    and self._item_signature(item) == signature
                ),
                None,
            )
        if index is None:
            self._invalidate_home_observation()
            return
        # Removing index i shifts only later slots. Earlier indices remain
        # addressable; owners at or beyond i require a fresh complete scan.
        self._home_knowledge_valid_before = index
        owner_signatures = {
            candidate
            for candidate in (
                self._home_pending_item,
                *self._calibration_restore_signatures,
                *self._home_pending_batch,
                (
                    self._home_errand.request.signature
                    if self._home_errand.active
                    and self._home_errand.request is not None
                    else None
                ),
            )
            if candidate is not None
        }
        owner_signatures.discard(signature)
        owner_indices = [
            owner_index
            for owner_index, owner_item in enumerate(self._home_knowledge_items)
            if self._item_signature(owner_item) in owner_signatures
        ]
        session = self._equipment_transaction_session
        action = session.current_action if session is not None else None
        if action is not None and action.kind == "withdraw":
            owner_indices.extend(
                owner_index
                for owner_index, owner_item in enumerate(self._home_knowledge_items)
                if owner_item.is_equipment
                and equipment_identity(owner_item) == action.item_identity
            )
        if owner_indices and index <= min(owner_indices):
            self._invalidate_home_observation()

    def _bind_catalogued_home_identification_withdrawal(
        self, snapshot: Snapshot
    ) -> None:
        """Promote a known Home identification target before entering Home.

        Home's ``~9`` knowledge is deliberately addressable only from the
        entrance.  Once an identification source has been acquired, retaining
        only ``_home_candidate_waiting`` leaves no operation for the atomic
        entry composer to post; opening Home cannot repair that omission.
        """
        if (
            not self._home_candidate_waiting
            or self._home_errand.active
            or self._home_pending_batch
        ):
            return
        observed = (
            {
                self._item_signature(item)
                for index, item in enumerate(self._home_knowledge_items)
                if index < self._home_knowledge_valid_before
            }
            if self._home_knowledge_current else set()
        )
        for owned in self._equipment_catalog.items:
            if owned.origin != "home" or not owned.identification_incomplete:
                continue
            signature = self._item_signature(owned.item)
            if signature not in observed or signature in self._deferred_home_items:
                continue
            full = bool(
                owned.item.known
                and item_requires_full_identification(owned.item)
                and not owned.item.fully_known
            )
            source = self._find_identification_source(
                snapshot, full=full, reliable_only=True,
                reservation_target=signature,
            )
            if source is None:
                continue
            self._file_home_errand(
                snapshot,
                HomeErrandRequest(
                    signature, 1, "home-catalog", "identification-catalog"
                ),
                knowledge_current=self._home_knowledge_current,
            )
            return
        if (
            self._identification_candidate is not None
            and self._identification_candidate in observed
        ):
            self._file_home_errand(
                snapshot,
                HomeErrandRequest(
                    self._identification_candidate,
                    1,
                    "identification-candidate",
                    "identification",
                ),
                knowledge_current=self._home_knowledge_current,
            )

    def _defer_unobserved_home_withdrawal(
        self, signature: tuple[str, int, int] | None = None
    ) -> tuple[str, int, int] | None:
        """End an unaddressable claim visibly instead of re-entering Home."""
        if signature is None:
            if self._home_pending_item is not None:
                signature = self._home_pending_item
            elif self._calibration_restore_signatures:
                signature = self._calibration_restore_signatures[0]
            elif self._home_pending_batch:
                signature = self._home_pending_batch[0]
        if self._home_random_teleport_withdrawal == signature:
            self._home_random_teleport_withdrawal = None
        session = self._equipment_transaction_session
        action = session.current_action if session is not None else None
        if signature is None and action is not None and action.kind == "withdraw":
            self._block_equipment_transaction(
                f"withdraw-item-unobserved:{action.item_id}"
            )
        if signature is not None:
            self._defer_home_item(signature, "unobserved-home-withdrawal")
            if signature in self._home_pending_batch:
                self._home_pending_batch.remove(signature)
            if signature in self._calibration_restore_signatures:
                self._calibration_restore_signatures.remove(signature)
        if self._home_pending_item == signature:
            self._home_pending_item = None
            self._home_pending_slot = None
        self._home_pending_quantity = None
        return signature

    def _invalidate_home_observation(self) -> None:
        """Discard every page-relative address fact after a Home mutation.

        The catalogue is separate content knowledge.  A commanded deposit is
        added when posted and a withdrawal is removed when its inventory gain
        is observed; neither operation makes all other Home contents unknown.
        If a content change cannot be proved, its owner must explicitly call
        ``invalidate_home`` so the next outside-town decision reacquires it
        through ``~9``.  No address survives this method.
        """
        self._home_knowledge_items = ()
        self._home_knowledge_valid_before = 0
        self._home_knowledge_current = False
        self._home_knowledge_invalidated = True
        self._home_processing_seen_pages.clear()
        self._home_star_remove_curse_count = None
        self._home_knowledge_scan_requested = False
        self._home_knowledge_scan_inflight = False
        self._home_scan_source = None
        self._home_scan_item_count = None
        self._home_errand.observe_knowledge(False)

    def _atomic_home_deposit_key(
        self, snapshot: Snapshot, step: Position
    ) -> str | None:
        """Bind one Home deposit to its stay-entry and exit."""
        if (
            snapshot.store is not None
            or self._shopping_approach_store_type != STORE_HOME
            or self._home_atomic_deposit_pending is not None
            or (
                getattr(self, "_store_entrance_step_off", None) is not None
                and self._store_entrance_step_off[0] != self._decision_sequence
            )
        ):
            return None
        entrance = snapshot.grid_at(snapshot.player.position)
        if entrance is None or entrance.store_number != STORE_HOME:
            return None
        session = self._equipment_transaction_session
        if session is not None:
            action = session.current_action
            if action is None or action.kind != "deposit":
                return None
            current = next(
                (
                    item
                    for item in snapshot.inventory
                    if item.is_equipment
                    and equipment_identity(item) == action.item_identity
                ),
                None,
            )
            if current is None:
                return None
            if self._retention_reservation(snapshot, current) > 0:
                return None
            if self._identification_flow_owns(current):
                return None
            if current.is_digging_tool and not self._is_surplus_digging_tool(
                snapshot, current
            ):
                self._abandon_blocked_equipment_transaction(snapshot)
                self.last_reason = "equipment-transaction:retain-digging-tool"
                return None
            if not self._prepare_home_visit_operation(
                "put",
                self._item_signature(current),
                (self._item_signature(current), current.slot, snapshot.turn),
            ):
                self.last_reason = "home-visit:deposit-not-authorized"
                return None
            # The one-shot transaction observation binds both the pack letter
            # and count used by the operation at this owned Home entry.
            quantity = f"{current.count}\r" if current.count > 1 else ""
            operation_key = SELL_KEY + current.slot + quantity + LEAVE_STORE_KEY
            key = WAIT_KEY
            observation = replace(
                observe_equipment_transactions(snapshot), in_home=True
            )
            if not self._prepare_equipment_transaction_command(
                session,
                action,
                observation,
                key,
                (
                    "home-entrance",
                    getattr(snapshot, "turn", 0),
                    current.slot,
                    action.item_identity,
                ),
            ):
                return None
            self._equipment_transaction_prepared_catalog_update = (
                "deposit",
                current,
                (
                    snapshot.turn,
                    current.slot,
                    self._item_signature(current),
                    current.count,
                    current.charges,
                    len(snapshot.inventory),
                ),
            )
            self._home_entry_operation_posted = True
            self._home_atomic_deposit_pending = (
                self._item_signature(current),
                self._inventory_signature_count(
                    snapshot, self._item_signature(current)
                ),
                snapshot.turn,
                0,
            )
            self._stage_home_operation(snapshot, operation_key)
            self.last_reason = "equipment-transaction:atomic-deposit"
            return key
        plan = self._town_errand_plan
        if (
            plan is not None
            and plan.index < len(plan.stops)
            and plan.stops[plan.index] == STORE_HOME
            and STORE_HOME not in plan.completed_this_visit
            and STORE_HOME not in plan.blocked_this_visit
            and STORE_HOME not in self._town_visit_ledger.blocked_stores
            and any(
                category not in {"deposit", "weight-overload", "equipment-work"}
                and (STORE_HOME, category)
                not in self._town_visit_ledger.satisfied_needs
                for category in plan.need_categories.get(STORE_HOME, ())
            )
        ):
            return None
        deposit = self._find_home_deposit(snapshot)
        if deposit is None:
            self.last_reason = ""
            return None
        current = next(
            (
                item for item in snapshot.inventory
                if item.slot == deposit.slot
                and self._item_signature(item) == self._item_signature(deposit)
            ),
            None,
        )
        if current is None:
            return None
        operation = self._home_deposit_key(snapshot, current)
        if operation == LEAVE_STORE_KEY:
            return None
        if not self._prepare_home_visit_operation(
            "put",
            self._item_signature(current),
            (self._item_signature(current), current.slot, snapshot.turn),
        ):
            self.last_reason = "home-visit:deposit-not-authorized"
            return None
        self._home_entry_operation_posted = True
        self._home_atomic_deposit_pending = (
            self._item_signature(current),
            self._inventory_signature_count(snapshot, self._item_signature(current)),
            snapshot.turn,
            0,
        )
        self._equipment_catalog.record_home_deposit(
            current,
            intent=(
                snapshot.turn,
                current.slot,
                self._item_signature(current),
                current.count,
                current.charges,
                len(snapshot.inventory),
            ),
        )
        self._stage_home_operation(snapshot, operation + LEAVE_STORE_KEY)
        self.last_reason = "home:atomic-deposit"
        return WAIT_KEY

    def _stage_home_operation(self, snapshot: Snapshot, operation_key: str) -> None:
        """Post Home entry now and release its bound tail on the fresh page."""
        if self._store_visit is None:
            self._store_visit = StoreVisit(
                owner=(
                    "equipment-transaction"
                    if self._equipment_transaction_session is not None
                    else "town-errand"
                ),
                purpose=(
                    "equipment-work"
                    if self._equipment_transaction_session is not None
                    else "shopping"
                ),
                store_type=STORE_HOME,
                visit_origin="home-operation-staging",
                opened_sequence=self._decision_sequence,
            )
        visit = self._store_visit
        visit.operation_posted = True
        visit.operation_key = operation_key
        visit.operation_released = False
        visit.composed_key = WAIT_KEY
        visit.posted_sequence = self._decision_sequence
        visit.posted_turn = snapshot.turn
        self._store_entry_wait_owner = STORE_HOME
        self._store_entry_wait_key = WAIT_KEY

    def _find_home_deposit(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._home_deposit_abandoned:
            return None
        if self._calibration_phase == "deposit":
            # The unequipped calibration phase deposits the whole pack (the
            # user-approved order: pack first, then every removable worn item),
            # through the unchanged atomic-deposit / one-operation-per-entry
            # machinery.  Only items Home already refused are skipped.
            return self._first_item(
                snapshot,
                lambda item: self._item_signature(item)
                not in self._home_rejected_deposits
                and self._item_signature(item)
                not in self._calibration_restore_signatures
                and item.slot != self._home_pending_slot
                and item.slot != self._pending_disposal_slot,
            )
        overweight = self._overweight_home_deposit(snapshot)
        if overweight is not None:
            return overweight
        # Inferior weapons may be sold by the sale path, but enhanced weapons stay
        # carried until the complete loadout optimizer has compared them.
        high_grade = self._equipped_weapon_high_grade(snapshot)
        deposit = self._first_item(
            snapshot,
            lambda item: (
                self._home_deposit_candidate(item, snapshot)
                or self._is_surplus_digging_tool(snapshot, item)
            )
            and not (
                item.is_digging_tool
                and not self._is_surplus_digging_tool(snapshot, item)
            )
            and not self._is_wanted_jewelry(snapshot, item)
            and self._item_signature(item) not in self._home_rejected_deposits
            and not (
                high_grade
                and self._weapon_is_inferior(item)
                # An inferior spare is carried for sale only while the Weapon Smith
                # can still take it: keep it out of the deposit pass only if it is
                # neither individually refused (unsellable) NOR blocked by a full
                # smith this visit. Once the smith refuses/fills, let leftovers
                # shelve back so a pack of unsellable spares cannot stall departure.
                and (item.name, item.tval, item.sval) not in self._unsellable_items
                and STORE_WEAPON not in self._store_sale_refused
            )
            and self._item_signature(item) not in self._home_pending_batch
            and (
                self._home_atomic_withdraw_pending is None
                or self._item_signature(item) != self._home_atomic_withdraw_pending[0]
            )
            and item.slot != self._home_pending_slot
            and item.slot != self._pending_disposal_slot,
        )
        if deposit is not None:
            return deposit
        organization = self._find_town_organization_surplus(snapshot)
        if (
            organization is not None
            and not self._home_deposit_candidate(organization, snapshot)
            and not self._is_surplus_digging_tool(snapshot, organization)
            and self._town_organization_sale_store(snapshot, organization) is None
            and self._item_signature(organization) not in self._home_rejected_deposits
        ):
            return organization
        return None

    def _observe_home_history(self, snapshot: Snapshot) -> None:
        """Persist only a Home command whose inventory delta confirms success."""
        if self._home_history_inflight is None:
            return
        action, signature, before_length, before_count = self._home_history_inflight
        after_count = self._inventory_signature_count(snapshot, signature)
        succeeded = (
            after_count > before_count or len(snapshot.inventory) > before_length
            if action == "withdraw"
            else after_count < before_count or len(snapshot.inventory) < before_length
        )
        if succeeded:
            self._home_disposal.record(action, signature, snapshot.turn)
            self._home_history_inflight = None
        elif snapshot.store is None or snapshot.store.store_type != STORE_HOME:
            self._home_history_inflight = None

    def _capture_home_history_intent(self, snapshot: Snapshot, key: str) -> None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME or not key:
            return
        if key.startswith(SELL_KEY) and len(key) > 1:
            target = next((item for item in snapshot.inventory if item.slot == key[1]), None)
            action = "deposit"
        else:
            return
        if target is None:
            return
        signature = self._item_signature(target)
        self._home_history_inflight = (
            action,
            signature,
            len(snapshot.inventory),
            self._inventory_signature_count(snapshot, signature),
        )

    @staticmethod
    def _home_disposal_store(signature: tuple[str, int, int]) -> int:
        if signature[1] in {TVAL_WAND, TVAL_STAFF, TVAL_ROD}:
            return STORE_MAGIC
        if signature[1] == TVAL_FOOD:
            return STORE_GENERAL
        return STORE_ALCHEMIST

    def _home_disposal_inventory_item(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._home_disposal_pending is None:
            return None
        signature, decision = self._home_disposal_pending
        exact = self._first_item(snapshot, lambda item: self._item_signature(item) == signature)
        if exact is not None:
            return exact
        if decision != "sell":
            return None
        # Identify changes the displayed name (and therefore the signature) while
        # preserving the visible base kind.  Keep the approved item attached to
        # its sale pipeline across that rename; the pending pipeline owns only one
        # Home signature at a time, so this fallback cannot consume two decisions.
        return self._first_item(
            snapshot, lambda item: (item.tval, item.sval) == signature[1:]
        )

    def _home_disposal_home_key(self, snapshot: Snapshot) -> str | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None
        if self._home_disposal_pending is not None:
            if self._home_disposal_inventory_item(snapshot) is not None:
                self.last_reason = "home-disposal:leave-with-approved-item"
                return LEAVE_STORE_KEY
            if self._home_disposal_pending[1] == "destroy":
                return None
            self._home_disposal_pending = None
        if not self._home_disposal_pass:
            return None

        page = tuple((item.letter, item.name, item.tval, item.sval) for item in store.items)
        for item in store.items:
            signature = self._item_signature(item)
            if item.tval not in {TVAL_POTION, TVAL_SCROLL, TVAL_WAND, TVAL_STAFF, TVAL_ROD, TVAL_FOOD}:
                continue
            self._home_disposal_candidates.setdefault(
                signature,
                HomeDisposalCandidate(
                    signature, item.name, item.tval, item.sval, item.count,
                    item.aware, item.known,
                ),
            )
            if not self._home_disposal.is_idle(signature):
                continue
            decision = self._home_disposal.decision(signature)
            if decision in {"sell", "destroy"}:
                self._home_disposal_pending = (signature, decision)
                self._home_pending_item = signature
                self.last_reason = f"home-disposal:queue-withdraw-{decision}"
                return LEAVE_STORE_KEY

        if page not in self._home_disposal_seen_pages:
            self._home_disposal_seen_pages.add(page)
            self.last_reason = "home-disposal:seek-page"
            return " "

        self._home_disposal.emit_queue(self._home_disposal_candidates.values(), snapshot.turn)
        self._home_disposal_pass = False
        self._home_disposal_seen_pages.clear()
        self._home_disposal_candidates.clear()
        self.last_reason = "home-disposal:scan-complete"
        return LEAVE_STORE_KEY

    def _home_disposal_processing_key(self, snapshot: Snapshot) -> str | None:
        if self._home_disposal_pending is None or not snapshot.in_town or snapshot.store is not None:
            return None
        signature, decision = self._home_disposal_pending
        target = self._home_disposal_inventory_item(snapshot)
        if target is None:
            if decision == "destroy":
                return None
            self._home_disposal_pending = None
            return None
        if decision == "destroy":
            self.last_reason = "home-disposal:destroy-approved"
            self._home_disposal_pending = None
            return self._destroy_item_key(target)
        if not target.known:
            source = self._find_identification_source(
                snapshot, full=False, reliable_only=True
            )
            if source is None:
                self._request_identification("normal")
                return None
            command, source_item = source
            self._identification_need = None
            self.last_reason = "home-disposal:identify-before-sale"
            if command == READ_KEY:
                return self._read_key(snapshot, source_item, target.slot)
            return command + source_item.slot + target.slot
        return None

    def _find_home_candidate(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None
        queued = set(self._home_pending_batch)
        if self._home_atomic_withdraw_pending is not None:
            queued.add(self._home_atomic_withdraw_pending[0])
        full_identify_available = (
            self._find_identification_source(snapshot, full=True) is not None
        )
        for item in store.items:
            if self._is_ammunition(item):
                continue
            signature = self._item_signature(item)
            # Identical objects cannot be distinguished reliably after Identify
            # consumes a scroll and shifts pack letters. Take at most one copy of
            # a signature per batch; a later Home pass can process another copy.
            if signature in queued:
                continue
            if item.is_equipment and item.pseudo_feeling == "average":
                group = self._equipment_slot_group(item)
                slot_occupied = group is None or any(
                    self._equipment_slot_group(equipped) == group
                    and (group != "weapon" or equipped.slot == "main_hand")
                    for equipped in snapshot.equipment
                )
                if slot_occupied:
                    self._processed_home_items.add(signature)
                    continue
            if (
                signature in self._deferred_home_items
                and not (
                    signature in self._unbuyable_full_identify_sigs
                    and full_identify_available
                )
            ):
                continue
            if (
                signature in self._unbuyable_full_identify_sigs
                and not full_identify_available
            ):
                continue
            # The (name, tval, sval) signature cannot tell two duplicate
            # UNIDENTIFIED equipment items apart, so a processed twin must not
            # skip an unidentified one — otherwise a duplicate is stranded
            # unprocessed in the Home. Identifying it changes its signature (so
            # this cannot loop), and an unidentifiable item is caught by the
            # _deferred set above. Already-identified items still skip by
            # signature as before.
            needs_identification = item.is_equipment and not item.known
            if not needs_identification and signature in self._processed_home_items:
                continue
            if item.is_equipment:
                needs_normal_identification = (
                    not item.known and item.pseudo_feeling != "average"
                )
                needs_full_identification = (
                    item.known
                    and self._identification_flow_candidate(item)
                )
                if (
                    needs_normal_identification
                    and self._find_identification_source(
                        snapshot,
                        full=False,
                        reliable_only=True,
                        reservation_target=signature,
                    )
                    is None
                    and STORE_ALCHEMIST in self._town_store_attempted
                ):
                    self._defer_home_item(signature, "home-disposal-uncomposable")
                    continue
                if needs_normal_identification or needs_full_identification:
                    return item
                self._processed_home_items.add(signature)
                continue
            if (
                self._deepest_level >= 20
                and (item.tval == TVAL_POTION or item.tval == TVAL_SCROLL)
                and not item.aware
            ):
                return item
        return None

    def _queue_home_identification_source(self, snapshot: Snapshot) -> bool:
        """Bind a catalogued Home scroll that can satisfy the active ID need."""
        if (
            self._identification_need is None
            or self._home_pending_item is not None
            or self._find_identification_source(
                snapshot,
                full=self._identification_need == "full",
                reliable_only=self._identification_requires_reliable_source(snapshot),
            )
            is not None
            or not self._home_knowledge_current
        ):
            return False
        wanted_sval = (
            SV_SCROLL_STAR_IDENTIFY
            if self._identification_need == "full"
            else SV_SCROLL_IDENTIFY
        )
        source = next(
            (
                item
                for item in self._home_knowledge_items[
                    : self._home_knowledge_valid_before
                ]
                if item.tval == TVAL_SCROLL and item.sval == wanted_sval
            ),
            None,
        )
        if source is None:
            return False
        self._file_home_errand(
            snapshot,
            HomeErrandRequest(
                self._item_signature(source), 1, "home-catalog", "identification"
            ),
            knowledge_current=self._home_knowledge_current,
        )
        self._home_candidate_waiting = True
        return True

    def _retain_identification_source_owner(self) -> None:
        """Re-open the Alchemist owner without discarding its route progress.

        Keeping the plan is defensive state preservation.  Recorded transition
        experiments show the unknown branch resolves on the same observed pass
        with or without it; the shelf observation, not plan identity, is the
        behavioural authority.
        """
        self._rearm_town_store_for_new_work(STORE_ALCHEMIST)

    def _activate_home_batch_item(self) -> None:
        if self._home_pending_item is None and self._home_pending_batch:
            self._home_pending_item = self._home_pending_batch.pop(0)
            self._home_pending_slot = None
            self._home_active_from_batch = True
            self._home_candidate_waiting = False
        elif self._home_pending_item is None:
            self._home_procurement_batch_active = False

    def _defer_home_item(
        self, signature: tuple[str, int, int], site: str
    ) -> None:
        """Defer one Home identity and retain the decision site's provenance."""
        self._deferred_home_items.add(signature)
        if not hasattr(self, "_deferred_home_item_sites"):
            self._deferred_home_item_sites = {}
        self._deferred_home_item_sites[signature] = site

    def _has_actionable_incomplete_home_item(self, snapshot: Snapshot) -> bool:
        """Whether the catalog contains incomplete Home gear usable this visit."""
        full_identify_available = (
            self._find_identification_source(snapshot, full=True) is not None
        )
        for owned in self._equipment_catalog.items:
            if owned.origin != "home" or not owned.identification_incomplete:
                continue
            signature = self._item_signature(owned.item)
            if (
                signature in self._deferred_home_items
                and not (
                    signature in self._unbuyable_full_identify_sigs
                    and full_identify_available
                )
            ):
                continue
            if (
                signature in self._unbuyable_full_identify_sigs
                and not full_identify_available
            ):
                continue
            needs_normal_identification = (
                not owned.item.known
                and owned.item.pseudo_feeling != "average"
            )
            if (
                needs_normal_identification
                and self._find_identification_source(
                    snapshot, full=False, reliable_only=True
                )
                is None
                and STORE_ALCHEMIST in self._town_store_attempted
            ):
                self._defer_home_item(signature, "home-processing-unidentifiable")
                continue
            # Mirror _find_home_candidate's processed-skip EXACTLY: it re-offers a
            # still-UNIDENTIFIED processed twin (a duplicate signature, known via
            # a different physical copy) but permanently skips a *known* item that
            # only needs full identification once it is in the processed cache.
            # Only that second class is genuinely non-actionable this visit, so
            # only it must be dropped here — otherwise home:processing-complete is
            # reported while the router still insists on the Home, looping the
            # visit. The mining-return retry boundary clears _processed_home_items
            # to give such gear a fresh attempt.
            if owned.item.known and signature in self._processed_home_items:
                continue
            return True
        return False

    def _home_dominated_disposal_key(self, snapshot: Snapshot) -> str | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None

        if self._pending_disposal_item is not None:
            target = self._pending_disposal(snapshot)
            if target is not None:
                self.last_reason = "home:leave-with-dominated"
                return LEAVE_STORE_KEY

            # A Home withdrawal cannot create a new pack stack when all 23
            # slots are occupied.  Retrying that impossible command used to
            # bounce out of and back into Home until STORE_STUCK_LIMIT.  Drop
            # the failed transaction so the normal deposit pass below can free
            # space immediately; the candidate remains eligible on a later
            # Home snapshot.
            if len(snapshot.inventory) >= PACK_CAPACITY:
                self._clear_pending_disposal()
                return None

        if not self._home_disposal_pass:
            return None

        # Do not start a withdrawal that the full pack cannot accept.  Returning
        # None lets the ordinary Home deposit policy run in this same decision.
        if len(snapshot.inventory) >= PACK_CAPACITY:
            return None

        candidate = next(
            (
                item
                for item in store.items
                if self._item_signature(item) not in self._deferred_home_items
                and self._is_disposable_dominated_armour(snapshot, item)
            ),
            None,
        )
        if candidate is None:
            return None

        signature = self._item_signature(candidate)
        self._pending_disposal_slot = None
        self._pending_disposal_item = signature
        self._disposal_store_attempts.clear()
        self._home_pending_item = signature
        self.last_reason = "home:queue-dominated-withdraw"
        return LEAVE_STORE_KEY

    @staticmethod
    def _destroy_item_key(item: InventoryItem) -> str:
        """Force-destroy a whole item stack with no stray keys.

        ``0<count>`` primes command_arg, so the original-keyset destroy command
        runs in force mode (no confirmation prompt) and input_quantity
        consumes the same arg (no quantity prompt); the item letter then selects
        the stack. Every key is swallowed by the command, so nothing leaks.
        """
        return f"0{item.count}{DESTROY_COMMAND}{item.slot}"

    def _observe_withdrawal_unsatisfied_pass(self, snapshot: Snapshot) -> None:
        """Flag one requested Home item that repeatedly fails to reach the pack."""
        pending = self._home_atomic_withdraw_pending
        signature = pending[0] if pending is not None else self._home_pending_item
        if signature is None:
            return
        current_count = self._inventory_signature_count(snapshot, signature)
        tracked = getattr(self, "_withdrawal_unsatisfied_for", None)
        if tracked is None or tracked[0] != signature:
            tracked = (signature, current_count, 0, False)
        target, before_count, passes, forced = tracked
        if current_count > before_count:
            self._withdrawal_unsatisfied_for = None
            return
        passes += 1
        # Six completed unsatisfied visits exceed any one-shot/page confirmation
        # chain (which completes before another stop pass is reported).  Keep
        # this diagnostic threshold independent of the looser calibration budget.
        threshold = 6
        if passes >= threshold and not forced:
            defect = {
                "marker": "WITHDRAWAL_UNFULFILLED_DEFECT",
                "item": target,
                "reason": self.last_reason or "",
                "unsatisfied_passes": passes,
            }
            self._withdrawal_unfulfilled_defect = defect
            self._town_progress_invariant_defect = dict(defect)
            self._invalidate_home_observation()
            forced = True
            if getattr(self, "_latch_capture_path", None) is not None:
                try:
                    self._latch_capture_assignment = assignment_provenance()
                except Exception:
                    self._latch_capture_assignment = {
                        "assigning_file": None,
                        "assigning_line": None,
                        "caller_chain": [],
                        "capture_error": "assignment-provenance-failed",
                    }
        self._withdrawal_unsatisfied_for = (
            target, before_count, passes, forced
        )

    def _home_owner_goal_pending(self, snapshot: Snapshot) -> bool:
        session = self._equipment_transaction_session
        if session is not None and session.executable and session.required_context is not None:
            return True
        directly_owned = bool(
            self._home_pending_item is not None
            or self._home_pending_batch
            or self._home_atomic_withdraw_pending is not None
            or self._home_atomic_deposit_pending is not None
            or self._calibration_restore_signatures
        )
        if (
            self._home_knowledge_current
            and self._home_scan_item_count == 0
            and self._home_atomic_deposit_pending is None
            and not self._calibration_active()
            and self._equipment_transaction_session is None
        ):
            # Empty Home knowledge is a state terminal for withdrawal-only
            # work.  It is process-independent, so a restart cannot resurrect
            # the visit-count-bounded route.
            return False
        home_categories = {
            need.category
            for need in self._enumerate_town_needs(snapshot)
            if need.store_type == STORE_HOME
        }
        return (
            directly_owned
            or "equipment-catalog" in home_categories
            or bool(
                self._calibration_active()
                and home_categories.intersection(
                    {"calibration-restore", "deposit"}
                )
            )
        )

    def _home_full_identify_targets(self) -> list[InventoryItem]:
        return [
            owned.item
            for owned in self._equipment_catalog.items
            if owned.origin == "home"
            and owned.item.known
            and item_requires_full_identification(owned.item)
            and not owned.item.fully_known
        ]

    def _home_procurement_candidate(
        self, item_class: tuple[int, int]
    ) -> InventoryItem | None:
        if not self._home_knowledge_current:
            return None
        return next(
            (
                item for item in self._home_knowledge_items
                if self._item_signature(item) not in self._deferred_home_items
                and self._procurement_class_matches(item, item_class)
                and item.count > 0
                and (not item.is_torch or item.fuel > 0)
            ),
            None,
        )

    def _home_procurement_viable_class_matches(
        self, item_class: tuple[int, int]
    ) -> int:
        """Count usable class stock, including items deferred after a failure."""
        return sum(
            self._procurement_class_matches(item, item_class)
            and item.count > 0
            and (not item.is_torch or item.fuel > 0)
            for item in self._home_knowledge_items
        )

    def _home_procurement_viable_item(
        self, item_class: tuple[int, int]
    ) -> InventoryItem | None:
        """Return usable class stock whether or not withdrawal was deferred."""
        return next(
            (
                item
                for item in self._home_knowledge_items
                if self._procurement_class_matches(item, item_class)
                and item.count > 0
                and (not item.is_torch or item.fuel > 0)
            ),
            None,
        )

    def _queue_home_procurement_batch(
        self, snapshot: Snapshot, primary: StoreItem
    ) -> None:
        """Retain all presently unmet, viable Home supply classes under Home ownership."""
        strategy = self._carry_procurement_strategy(snapshot)
        quest_target = self._quest_carry_target_for_item(
            snapshot, primary, strategy.required_force if strategy is not None else {}
        )
        primary_is_supply = any(
            self._store_item_is_supply(primary, kind) for kind in SUPPLY_STORES
        )
        if (
            quest_target is None
            and not primary_is_supply
            and not primary.is_treasure_detection_scroll
            and not primary.is_digging_tool
        ):
            return
        primary_missing = self._procurement_missing_amount(snapshot, primary)
        if primary_missing <= 0:
            return
        wanted_classes = {self._procurement_class(primary)}
        for known in self._home_knowledge_items:
            if self._procurement_missing_amount(snapshot, known) > 0:
                wanted_classes.add(self._procurement_class(known))
        for item_class in wanted_classes:
            candidate = self._home_procurement_candidate(item_class)
            if candidate is None:
                continue
            signature = self._item_signature(candidate)
            if not hasattr(self, "_home_pending_quantities"):
                self._home_pending_quantities = {}
            quantity = min(
                candidate.count, self._procurement_missing_amount(snapshot, candidate)
            )
            if quantity <= 0:
                continue
            self._home_pending_quantities.setdefault(signature, quantity)
            if (
                signature != self._home_pending_item
                and signature not in self._home_pending_batch
            ):
                self._home_pending_batch.append(signature)
                self._home_procurement_batch_active = True

    def _record_home_gate(
        self,
        snapshot: Snapshot,
        item: StoreItem,
        result: ProcurementHomeGate,
        branch: str,
        *,
        wrapper_fallthrough: str | None = None,
    ) -> ProcurementHomeGate:
        """Record a gate return without participating in its decision."""
        previous = self._home_gate_telemetry
        if (
            branch.startswith("evaluate-")
            and previous.get("decision_sequence") == self._decision_sequence
            and str(previous.get("branch", "")).startswith("wrapper-")
        ):
            return result
        item_class = self._procurement_class(item)
        matches = [
            known for known in self._home_knowledge_items
            if self._procurement_class_matches(known, item_class)
        ]
        candidate = self._home_procurement_candidate(item_class)
        fails = self._town_visit_ledger.approach_fails[STORE_HOME]
        limit = self._town_store_visit_limit(STORE_HOME)
        attempted = STORE_HOME in self._town_store_attempted
        viable_signatures = {
            self._item_signature(known)
            for known in matches
            if known.count > 0 and (not known.is_torch or known.fuel > 0)
        }
        all_viable_deferred = bool(viable_signatures) and viable_signatures.issubset(
            self._deferred_home_items
        )
        retried_deferred = getattr(
            self, "_retried_deferred_home_items", set()
        )
        retried_signatures = viable_signatures.intersection(retried_deferred)
        fresh_retry_failed = bool(
            branch == "wrapper-withdraw-failed-stock-present"
            and all_viable_deferred
            and viable_signatures.issubset(retried_deferred)
        )
        if not attempted:
            self._home_latch_active = None
        self._home_gate_telemetry = {
            "result": (
                "allow" if result is ProcurementHomeGate.ALLOW_PURCHASE
                else result.value
            ),
            "branch": branch,
            "item": {
                "tval": item.tval, "sval": item.sval, "letter": item.letter,
                "price": item.price,
                "category": self._purchase_diagnostic_category(item),
            },
            "candidate": (
                {"identity": self._item_signature(candidate)}
                if candidate is not None else None
            ),
            "candidate_absence_census": {
                "class_matches": len(matches),
                "excluded_as_deferred": sum(
                    self._item_signature(known) in self._deferred_home_items
                    for known in matches
                ),
                "zero_count": sum(known.count <= 0 for known in matches),
                "torch_no_fuel": sum(
                    known.is_torch and known.fuel <= 0 for known in matches
                ),
            } if candidate is None else None,
            "deferred_matches": [
                {
                    "identity": self._item_signature(known),
                    "site": getattr(self, "_deferred_home_item_sites", {}).get(
                        self._item_signature(known), "legacy-unattributed"
                    ),
                }
                for known in matches
                if self._item_signature(known) in self._deferred_home_items
                and known.count > 0
                and (not known.is_torch or known.fuel > 0)
            ],
            "deferred_retry": {
                "attempted_signatures": [
                    list(signature) for signature in sorted(retried_signatures)
                ],
                "fresh_attempt_made": fresh_retry_failed,
                "fresh_attempt_failed": fresh_retry_failed,
            },
            "inputs": {
                "knowledge_current": self._home_knowledge_current,
                "knowledge_invalidated": self._home_knowledge_invalidated,
                "attempted": attempted,
                "blocked_store": STORE_HOME in self._town_visit_ledger.blocked_stores,
                "fails_at_limit": fails >= limit,
                "approach_fails": fails,
                "unsatisfied_passes": self._town_visit_ledger.unsatisfied_passes[STORE_HOME],
                "visit_limit": limit,
            },
            "wrapper_fallthrough": wrapper_fallthrough,
            "home_latch": {
                "active": self._home_latch_active,
                "history": list(self._home_latch_history),
            },
            "withdraw_failure": (
                dict(getattr(self, "_home_procurement_withdraw_failure", None))
                if getattr(self, "_home_procurement_withdraw_failure", None)
                is not None else None
            ),
            "decision_sequence": self._decision_sequence,
            "turn": snapshot.turn,
        }
        return result

    def _home_quest_launcher_key(self, snapshot: Snapshot) -> str | None:
        store = snapshot.store
        profile = self._carry_procurement_strategy(snapshot)
        if store is None or store.store_type != STORE_HOME or profile is None:
            self._home_quest_launcher_seen_pages.clear()
            return None
        preferred = self._preferred_home_quest_launcher(snapshot, profile)
        if preferred is None:
            self._home_quest_launcher_seen_pages.clear()
            return None
        signature = self._item_signature(preferred)
        candidate = next(
            (
                item for item in store.items
                if self._item_signature(item) == signature
            ),
            None,
        )
        if candidate is not None:
            self._home_quest_launcher_seen_pages.clear()
            self._home_pending_item = signature
            self._home_pending_slot = None
            self._home_candidate_waiting = False
            self.last_reason = "home:queue-quest-launcher-withdraw"
            return LEAVE_STORE_KEY
        page = tuple(
            (item.letter, item.name, item.tval, item.sval)
            for item in store.items
        )
        if page not in self._home_quest_launcher_seen_pages:
            self._home_quest_launcher_seen_pages.add(page)
            self.last_reason = "home:seek-quest-launcher-page"
            return " "
        self._home_quest_launcher_seen_pages.clear()
        return None

    def _home_mana_food_candidate(self) -> InventoryItem | None:
        """Cheapest edible Home device, including unidentified devices."""
        if not self._home_knowledge_current:
            return None
        candidates = [
            item
            for item in self._home_knowledge_items
            if item.is_wand_staff and (not item.known or item.charges > 0)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                self._is_useful_device(item),
                self._stack_charges(item),
                self._item_signature(item),
            ),
        )
