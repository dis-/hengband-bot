from __future__ import annotations

from hengbot.policy_constants import AMMO_CARRY_TARGET, CALIBRATION_HOME_VISIT_LIMIT, FUNDRAISING_START_GOLD, TORCH_THROW_MAX_DEPTH, STAFF_IDENTIFY_MIN_CHARGES, BUY_KEY, CHARACTER_DUMP_MACRO, DIRECTION_KEYS, DOWN_STAIRS_KEY, ENTER_DUNGEON_MACRO, ExplorationPathOutcome, FOOD_MIN_SVAL, FOOD_TYPE_MANA, INN_BUILDING_TYPE, INSCRIBE_KEY, FULL_IDENTIFY_DISMISS_SUFFIX, FUNDRAISING_GOLD_TARGET, IDENTIFY_FAIL_LIMIT, LEAVE_STORE_KEY, LANTERN_MIN_GOLD, MINING_RUNS_PER_SET, MIN_TERMINAL_FREE_PACK_SLOTS, NEIGHBOR_OFFSETS, PACK_CAPACITY, READ_KEY, RECALL_ISSUE_CONFIRM_TURNS, RECALL_MIN_DEPTH, SEARCH_KEY, SELL_KEY, STORE_STUCK_LIMIT, RESTOCK_WAIT_MACRO, RUMOR_COST, RUMOR_GOLD_RESERVE, RUMOR_READ_KEY, RUMOR_READS_PER_VISIT, TORCH_THROW_TARGET, TOWN_TRAVEL_STORE_SYMBOLS, TOWN_CLAIM_ADVANCING_MOVE_REASONS, TOWN_CYCLE_MAX_DISTINCT, TOWN_CYCLE_WINDOW, TOWN_FAST_TRAVEL_MAX_POSITIONS, TOWN_FAST_TRAVEL_MIN_ROWS, TOWN_FAST_TRAVEL_WINDOW, TOWN_STOP_PASS_LIMIT, TOWN_TELEPORT_BUILDING_TYPES, TOWN_TRAVEL_MIN_DISTANCE, TOWN_CYCLE_BREAK_LIMIT, UP_STAIRS_KEY, WAIT_KEY, WALK_OUT_MAX_DEPTH
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, PLAYER_CLASS_WARRIOR, STORE_ALCHEMIST, STORE_ARMOURY, STORE_BLACK, STORE_GENERAL, STORE_HOME, STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON, SV_LITE_LANTERN, SV_LITE_TORCH, SV_POTION_SPEED, SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, RESTORE_POTION_SVAL_BY_STAT, SV_SCROLL_IDENTIFY, SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE, SV_STAFF_IDENTIFY, TVAL_FOOD, TVAL_LITE, TVAL_POTION, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, InventoryItem, MonsterState, Position, Snapshot, StoreItem
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY, MIN_FREE_PACK_SLOTS, REST_MACRO, TOWN_TELEPORT_COST
from hengbot.policy_types import TownTravelProgress, TownNeed, NeedSpec, TownErrandPlan
from collections import deque
from hengbot.equipment_optimizer import equipment_identity
from dataclasses import replace

class TownMixin:
    def _refresh_town_facts(self, snapshot: Snapshot) -> None:
        """Incrementally retain store/building facts for this floor visit."""
        if snapshot is self._town_fact_snapshot:
            return
        self._town_fact_snapshot = snapshot
        in_town = getattr(snapshot, "in_town", False)
        if not in_town:
            self._town_visit_entrances.clear()
        region = self._grid_region(snapshot)
        if self._town_fact_region != region:
            self._town_fact_region = region
            self._town_store_positions = {}
            self._town_emitted_entrances = set()
            self._town_entrance_cache = None
            emitted = getattr(snapshot, "grids", {}).items()
        else:
            grids = getattr(snapshot, "grids", {})
            emitted = (
                (Position(y, x), grids[Position(y, x)])
                for y, x in self._emitted_t
                if Position(y, x) in grids
            )
        changed = False
        for position, grid in emitted:
            for positions in self._town_store_positions.values():
                if position in positions:
                    positions.discard(position)
                    changed = True
            if grid.store_number >= 0:
                self._town_store_positions.setdefault(grid.store_number, set()).add(position)
                changed = True
            was_entrance = position in self._town_emitted_entrances
            # Preserve 4f41982 exactly: older/synthetic GridState producers may
            # use None for a non-store even though current parsed snapshots use
            # -1. Entrance-cache work must not alter that routing predicate.
            is_entrance = grid.store_number is not None or grid.building_special >= 0
            if is_entrance:
                self._town_emitted_entrances.add(position)
            else:
                self._town_emitted_entrances.discard(position)
            if in_town and (
                grid.store_number >= 0
                or grid.building_special >= 0
                or grid.has_quest_enter
                or grid.has_quest_exit
            ):
                self._town_visit_entrances.add(position)
            changed = changed or was_entrance != is_entrance
        if changed:
            self._town_entrance_cache = None

    def _town_arbiter_terminal_result(self, key: str) -> bool:
        """Classify visible stops without treating their emission as progress."""
        reason = self.last_reason or ""
        return key == WAIT_KEY and (
            reason.startswith("town:blocked:")
            or "terminal" in reason
            or reason.endswith(":unsatisfiable")
            or reason in {"policy:no-action", "stuck:wander"}
        )

    def _town_arbiter_progress_vector(
        self, snapshot: Snapshot, reason: str | None = None
    ) -> tuple[object, ...]:
        """Read durable facts plus the registered locomotion owner's distance."""
        departure = getattr(self, "_departure_block", {}) or {}
        core = self._owner_progress_core(snapshot)
        durable_core = replace(
            core,
            position=Position(0, 0),
            turn=0,
            decision_sequence=0,
        )
        home_blocked = (
            STORE_HOME in self._town_visit_ledger.blocked_stores
            or STORE_HOME in self._town_visit_ledger.nonhome_attempted_without_effect
            or self._store_entry_failed_owner == STORE_HOME
        )
        durable = (
            durable_core,
            self._town_progress_fingerprint(snapshot),
            tuple(sorted((str(key), repr(value)) for key, value in departure.items())),
            bool(self._home_knowledge_current),
            bool(home_blocked),
            getattr(self, "_town_blocked_reason", None),
            getattr(self, "_descent_refusal_reason", None),
            bool(getattr(self, "_descent_blocked", False)),
        )
        arbiter = getattr(self, "_town_turn_arbiter", None)
        owner = (
            arbiter.owner_for_reason(reason or self.last_reason)
            if arbiter is not None
            else "unregistered"
        )
        goal: Position | None = None
        if owner == "store-router" or (
            owner == "equipment-txn"
            and (reason or self.last_reason) == "equipment-transaction:approach-home"
        ):
            goal = self._shopping_approach_goal
        elif owner == "departure":
            goal = self._descent_target_goal
            if goal is None:
                upward = (reason or self.last_reason or "").startswith(
                    ("return:", "recall", "town:recall")
                )
                candidates = (
                    self._remembered_upstairs if upward
                    else self._remembered_downstairs
                )
                if candidates:
                    goal = min(
                        candidates,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
                elif snapshot.in_town and self._town_map_active(snapshot):
                    goal = self._town_map_descent_entrance(snapshot)
        elif owner == "quest-request" and "approach" in (reason or self.last_reason or ""):
            quest_id = self._fixed_quest_target(snapshot)
            if quest_id is not None:
                positions = self._fixed_quest_entrance_positions(snapshot, quest_id)
                if not positions:
                    positions = self._fixed_quest_building_positions(snapshot, quest_id)
                if positions:
                    goal = min(
                        positions,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
            if goal is None and self._town_map_active(snapshot):
                positions = tuple(
                    position
                    for entries in self._town_map.quest_entrances.values()
                    for position in entries
                )
                if positions:
                    goal = min(
                        positions,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
        elif owner == "misc" and (reason or self.last_reason or "").startswith("explore"):
            # Deliberate G1 explorer position-as-progress exception: the restored open-town explorer pin requires it.
            path = getattr(self, "_explore_path", None)
            if path:
                goal = path[-1]
            else:
                identity = getattr(self, "_explore_goal_identity", None)
                if identity is not None:
                    goal = identity.position
                else:
                    pending = getattr(self, "_pending_one_step_explore", None)
                    if pending is not None:
                        goal = pending[1]
        if goal is None:
            return durable
        if owner == "misc":
            return durable + (
                ("locomotion", owner, snapshot.floor_key, snapshot.player.position),
            )
        distance = (
            abs(snapshot.player.position.y - goal.y)
            + abs(snapshot.player.position.x - goal.x)
        )
        return durable + (("locomotion", owner, snapshot.floor_key, distance),)

    def _town_result_makes_progress(self, snapshot: Snapshot, key: str) -> bool:
        """Positively classify a town result by its effect, never its label."""
        if (
            key == LEAVE_STORE_KEY
            and (self.last_reason or "").startswith("home-errand:filed:")
        ):
            return True
        if (
            key == LEAVE_STORE_KEY
            and snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._home_entry_operation_posted
        ):
            return True
        if (
            self._home_entry_operation_posted
            and key not in {"", WAIT_KEY, LEAVE_STORE_KEY}
        ):
            return True
        if (
            self._store_visit is not None
            and self._store_visit.operation_posted
            and (self.last_reason or "").startswith("shop:one-shot-")
        ):
            # Outside composition intentionally returns WAIT while the bound
            # purchase tail waits for the re-entered store page.  The posted
            # operation, not the transport key, is the progress effect.
            return True
        if key in {"", WAIT_KEY, LEAVE_STORE_KEY}:
            if key == WAIT_KEY and (self.last_reason or "").startswith(
                "equipment-transaction:"
            ):
                fingerprint = self._town_progress_fingerprint(snapshot)
                if fingerprint in self._town_progress_history():
                    self._town_progress_invariant_defect = {
                        "marker": "TOWN_OSCILLATION_DEFECT",
                        "winning_rung": self.last_reason or "",
                        "repeated_fingerprint": repr(fingerprint),
                        "gold": snapshot.player.gold,
                    }
                    self._record_shop_selector_diagnostics(snapshot, key)
            return False
        if key and key.startswith((BUY_KEY, SELL_KEY, "{")):
            # Store purchase/sale and inscription producers have closed command
            # prefixes and directly mutate gold or inventory.
            return True
        if key and key.startswith("~") and (self.last_reason or "").startswith(
            "home:request-knowledge-scan"
        ):
            return True
        direction = next(
            (delta for delta, direction_key in DIRECTION_KEYS.items()
             if direction_key == key),
            None,
        )
        if direction is not None and (self.last_reason or "").endswith("home:scan-step-off") and not self._equipment_catalog.home_scan_complete:
            return True
        goal = self._shopping_approach_goal
        if direction is not None:
            if goal is not None:
                before = snapshot.player.position.distance_to(goal)
                after = Position(
                    snapshot.player.position.y + direction[0],
                    snapshot.player.position.x + direction[1],
                ).distance_to(goal)
                if after < before:
                    return True
            fingerprint = self._town_progress_fingerprint(snapshot)
            if fingerprint in self._town_progress_history():
                # Movement without a closer claim goal revisits the same town
                # goal state even when it reaches a fresh map position.
                return False
            # Town movement is not goal progress.  Only an approach with a
            # measured supplier/landmark goal or an established reachable
            # movement owner can advance a live claim.  Wander and breakout
            # labels are deliberately absent from this town-only contract.
            reason = self.last_reason or ""
            return (
                reason in TOWN_CLAIM_ADVANCING_MOVE_REASONS
                or "step-off" in reason
                or reason.startswith("shop:")
                or reason.startswith(
                    "town-progress-invariant:boxed-breakout-travel"
                )
            )
        # Keep this positive and closed.  Native store travel and dungeon entry
        # have explicit contracts that advance position/depth; an unknown macro
        # is not progress merely because it contains command characters.
        store_type = self._shopping_approach_store_type
        if (
            goal is not None
            and store_type is not None
            and 0 <= store_type < len(TOWN_TRAVEL_STORE_SYMBOLS)
            and key == f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[store_type]}."
        ):
            return True
        if key in {DOWN_STAIRS_KEY, ENTER_DUNGEON_MACRO}:
            return True
        if key not in {RESTOCK_WAIT_MACRO, "l", "s", "\x1b\x1b"}:
            # At this point direction, WAIT, leave, and the closed noop-macro
            # axis have all been rejected.  Remaining policy command macros
            # are inventory/equipment/Home actions that mutate goal state.
            # Their command shape alone is not evidence of progress: a
            # completed takeoff/restore cycle returns to the same measured
            # state even though every individual macro looked mutating.
            fingerprint = self._town_progress_fingerprint(snapshot)
            if fingerprint in self._town_progress_history():
                self._town_progress_invariant_defect = {
                    "marker": "TOWN_OSCILLATION_DEFECT",
                    "winning_rung": self.last_reason or "",
                    "repeated_fingerprint": repr(fingerprint),
                    "gold": snapshot.player.gold,
                }
                self._record_shop_selector_diagnostics(snapshot, key)
                return False
            return True
        return False

    def _town_progress_fingerprint(self, snapshot: Snapshot) -> tuple[object, ...]:
        """Measured town progress fields used by the result arbitration seam."""
        return (
            snapshot.floor_key,
            snapshot.player.gold,
            snapshot.player.food_state,
            snapshot.player.food_type,
            snapshot.player.exp,
            snapshot.dungeon_level,
            tuple(sorted(
                (self._town_progress_item_state(item) for item in snapshot.inventory),
                key=repr,
            )),
            tuple(sorted(
                (self._town_progress_item_state(item) for item in snapshot.equipment),
                key=repr,
            )),
            tuple(getattr(self._town_errand_plan, "completed_this_visit", ()) or ()),
            tuple(getattr(self._town_errand_plan, "blocked_this_visit", ()) or ()),
            self._equipment_catalog.home_scan_complete,
            self._home_knowledge_current,
            self._home_pending_item,
            tuple(self._home_pending_batch),
            self._home_atomic_withdraw_pending,
            self._home_atomic_deposit_pending,
            tuple(getattr(self._equipment_optimization_preparation, "blockers", ())),
            self._equipment_transaction_session is not None,
            tuple(sorted(self._equipment_transaction_failed_items)),
        )

    def _town_progress_history(self) -> deque[tuple[object, ...]]:
        """Return the window, lazily upgrading restored pre-R6 policies."""
        history = getattr(self, "_town_progress_fingerprint_history", None)
        if history is None:
            history = deque(maxlen=TOWN_CYCLE_WINDOW)
            self._town_progress_fingerprint_history = history
        return history

    def _town_begin_progress_decision(self, snapshot: Snapshot) -> None:
        """Move the prior decision into the window, leaving current state fresh."""
        history = self._town_progress_history()
        if not snapshot.in_town:
            history.clear()
            self._town_progress_last_fingerprint = None
            return
        previous = getattr(self, "_town_progress_last_fingerprint", None)
        if previous is not None:
            history.append(previous)
        self._town_progress_last_fingerprint = self._town_progress_fingerprint(snapshot)

    def _town_progress_allow_members(self, snapshot: Snapshot) -> frozenset[str]:
        """Return only members of the reviewed procurement preemptor set."""
        reason = self.last_reason or ""
        allowed: set[str] = set()
        if reason.startswith(("emergency:", "unseen-recall:", "guardian:")):
            allowed.add("emergency-lethal-danger")
        if reason in {
            "survival:mana-absorb", "town:eat-before-travel", "survival:eat"
        } and snapshot.player.food_state in {"weak", "fainting"}:
            allowed.add("weak-fainting-survival-absorb")
        if reason.startswith(("town:repetition-depart", "recall-entry:")):
            allowed.add("recall-entry-invariant")
        if any(
            monster.distance <= 4
            for monster in getattr(snapshot, "visible_monsters", ())
        ):
            allowed.add("nearby-threat-defer")

        observation = self._shop_observation
        if observation is not None:
            observed = replace(snapshot, store=observation[0])
            wanted = self._next_purchase_unreserved(observed)
            if wanted is not None:
                quantity = self._purchase_quantity(observed, wanted)
                reserve = self._fundraising_kit_reserve(observed)
                if (
                    reserve > 0
                    and snapshot.player.gold - wanted.price * quantity < reserve
                ):
                    allowed.add("reserve-already-satisfied")
        assert allowed <= self.TOWN_PROGRESS_ALLOW_SET
        return frozenset(allowed)

    def _town_procurement_progress_key(
        self, snapshot: Snapshot
    ) -> tuple[str, str] | None:
        """Compose the next step of an available approach->enter->buy route."""
        home_scan_pending = (
            not self._equipment_catalog.home_scan_complete
            and self._home_available_for_probe(snapshot)
            and (
                "home-scan-incomplete" in getattr(
                    self._equipment_optimization_preparation, "blockers", ()
                )
                or (snapshot.player.food_type == FOOD_TYPE_MANA and snapshot.player.hungry)
            )
        )
        here = snapshot.grid_at(snapshot.player.position)
        if (
            home_scan_pending
            and snapshot.store is None
            and here is not None
            and here.store_number >= 0
            and self._store_leave_inflight is None
            and self._store_entry_posted_owner is None
            and self._store_entry_wait_owner is None
        ):
            reason = "home:scan-step-off"
            key = self._town_entrance_step_off_key(snapshot, reason)
            return key, self.last_reason or reason

        # An observed ordinary-shop shelf is paired with current gold at this
        # boundary.  It is the strongest counterfactual and composes first.
        transaction = self._atomic_shop_transaction_key(snapshot)
        if transaction is not None:
            return transaction, self.last_reason

        # A21 remains Home-first.  Calling its established producer here makes
        # the A26 generic-food route unable to preempt a MANA acquisition.
        if snapshot.player.food_type == FOOD_TYPE_MANA and snapshot.player.hungry:
            mana = self._mana_food_survival_override_key(snapshot)
            if mana is not None and self._town_result_makes_progress(snapshot, mana):
                return mana, self.last_reason

        # A27 bookkeeping belongs to candidate availability: stale terminal
        # ownership and an inert visit cannot make a released supplier appear
        # unreachable.  Posted operations remain authoritative.
        if self._town_blocked_reason in {
            "restock-store-unreachable",
        }:
            self._town_blocked_reason = None
            visit = self._store_visit
            if visit is not None and not visit.operation_posted:
                self._close_store_visit("town-progress-invariant-reroute")

        supplier = None
        for store_type, known_stock in getattr(
            self, "_town_supplier_stock", {}
        ).items():
            if store_type == STORE_HOME:
                continue
            stock_snapshot = replace(snapshot, store=known_stock)
            wanted = self._next_purchase_unreserved(stock_snapshot)
            if (
                wanted is None
                or not self._town_blocked_purchase_is_composable(stock_snapshot)
            ):
                continue
            quantity = self._purchase_quantity(stock_snapshot, wanted)
            reserve = self._fundraising_kit_reserve(stock_snapshot)
            if snapshot.player.gold - wanted.price * quantity >= reserve:
                supplier = store_type
                break
        if supplier is None:
            return None
        step = self._shopping_approach_step(snapshot, supplier)
        if step is None:
            return None
        reason = "town-progress-invariant:approach"
        key = self._shopping_approach_key(snapshot, step, reason)
        return key, self.last_reason or reason

    def _town_observed_purchase_is_composable(self, snapshot: Snapshot) -> bool:
        """Whether this ordinary-store page can fund a wanted purchase now."""
        if snapshot.store is None or snapshot.store.store_type == STORE_HOME:
            return False
        wanted = self._next_purchase_unreserved(snapshot)
        if wanted is None:
            return False
        quantity = self._purchase_quantity(snapshot, wanted)
        reserve = self._fundraising_kit_reserve(snapshot)
        return snapshot.player.gold - wanted.price * quantity >= reserve

    def _town_blocked_purchase_is_composable(self, snapshot: Snapshot) -> bool:
        """Whether the blocked store handler will stage its selected purchase."""
        store = snapshot.store
        if store is None or store.store_type == STORE_HOME:
            return False
        attempted_at = self._town_store_attempted.pop(store.store_type, None)
        try:
            departure_families = {
                need.category.split(":", 1)[0]
                for need in self._departure_blocking_town_needs(snapshot)
                if need.store_type == store.store_type
            }
        finally:
            if attempted_at is not None:
                self._set_town_store_attempted(store.store_type, attempted_at, "shop-exit-attempt")
        purchase = self._next_purchase(snapshot)
        purchase_families = {
            category.split(":", 1)[0]
            for category in (
                self._cross_town_item_categories(purchase)
                if purchase is not None
                else ()
            )
        }
        family_aliases = {
            "fundraising-oil": "oil",
            "fundraising-light": "light",
            "mining-digger": "digger",
        }
        departure_families = {
            family_aliases.get(family, family) for family in departure_families
        }
        purchase_families = {
            family_aliases.get(family, family) for family in purchase_families
        }
        if departure_families:
            return bool(departure_families.intersection(purchase_families))
        return purchase is not None and purchase.tval in {TVAL_WAND, TVAL_STAFF}

    def _town_procurement_decision(
        self, snapshot: Snapshot, key: str, *, enforce: bool = True
    ) -> str:
        """Enforce composable progress at the one downstream town-result seam."""
        proposed_reason = self.last_reason or ""
        self._town_begin_progress_decision(snapshot)
        result_makes_progress = self._town_result_makes_progress(snapshot, key)
        if not snapshot.in_town or result_makes_progress:
            return key
        claims_active = self._town_claims_active(snapshot)
        movement_key = key in DIRECTION_KEYS.values()
        allow_members = self._town_progress_allow_members(snapshot)
        if allow_members:
            return key

        # Durable session ownership survives reason relabelling and blockers.
        if self._equipment_transaction_owns_town_relocation(snapshot):
            return key

        # The outside half of an already-posted Home take owns the decision
        # until inventory confirms it or its existing confirmation bound
        # expires.  A posted shop visit must not relabel that await as a buy.
        if (
            proposed_reason == "home:atomic-withdraw-await-confirmation"
            and self._home_atomic_withdraw_pending is not None
        ):
            return key
        if proposed_reason == "breakout:least-visited":
            self._boxed_town_breakout_key(snapshot)
            committed = self._commit_boxed_town_breakout_key(snapshot)
            if committed is not None:
                self.last_reason = "town-progress-invariant:boxed-breakout-travel"
                return committed

        # Observing a wanted, affordable shelf is the entry phase of the
        # existing atomic contract.  Leaving is only its transport step: it is
        # a defect until the saved page is composed on the adjacent outside
        # snapshot.  A non-supplier store may still be left normally so the
        # router can advance toward another supplier.
        if proposed_reason == "shop:observe-and-leave":
            if not self._town_observed_purchase_is_composable(snapshot):
                return key
            self.last_reason = "town-progress-invariant:continue-observed-shop"
            self._town_progress_invariant_defect = {
                "marker": "TOWN_PROGRESS_INVARIANT_DEFECT",
                "winning_rung": proposed_reason,
                "progress_action": self.last_reason,
                "gold": snapshot.player.gold,
                "allow_set": (),
            }
            self._record_shop_selector_diagnostics(snapshot, key)
            return key

        visit = self._store_visit
        if visit is not None and visit.operation_posted:
            if visit.store_type == STORE_HOME:
                return key
            progress_reason = "shop:one-shot-buy"
            self._town_progress_invariant_defect = {
                "marker": "TOWN_PROGRESS_INVARIANT_DEFECT",
                "winning_rung": proposed_reason,
                "progress_action": progress_reason,
                "gold": snapshot.player.gold,
                "allow_set": (),
            }
            if enforce:
                self.last_reason = (
                    "town-progress-invariant:defect:"
                    f"{proposed_reason}=>{progress_reason}"
                )
            return key

        progress = self._town_procurement_progress_key(snapshot)
        if progress is None:
            liveness_candidate = (
                proposed_reason == "stuck:wander"
                or proposed_reason.startswith("novel:")
            )
            if enforce and movement_key and liveness_candidate and (
                claims_active or getattr(self, "_town_liveness_claim_retired", False)
            ):
                blocked_reason = (
                    "retired-equipment-transaction-failed"
                    if getattr(self, "_town_liveness_claim_retired", False)
                    else "no-actionable-claim-owner"
                )
                self.last_reason = f"town:blocked:{blocked_reason}"
                self._town_liveness_invariant_defect = {
                    "marker": "TOWN_LIVENESS_INVARIANT_DEFECT",
                    "winning_rung": proposed_reason,
                    "resolution": self.last_reason,
                    "claim_retired": getattr(
                        self, "_town_liveness_claim_retired", False
                    ),
                }
                self._town_progress_invariant_defect = dict(
                    self._town_liveness_invariant_defect
                )
                self._record_shop_selector_diagnostics(snapshot, WAIT_KEY)
                return WAIT_KEY
            self.last_reason = proposed_reason
            return key
        progress_key, progress_reason = progress
        if progress_key == key and progress_reason == proposed_reason:
            self.last_reason = proposed_reason
            return key
        if not self._town_result_makes_progress(snapshot, progress_key):
            self.last_reason = proposed_reason
            return key
        self._town_progress_invariant_defect = {
            "marker": "TOWN_PROGRESS_INVARIANT_DEFECT",
            "winning_rung": proposed_reason,
            "progress_action": progress_reason,
            "gold": snapshot.player.gold,
            "allow_set": (),
        }
        if not enforce:
            self.last_reason = proposed_reason
            return key
        self.last_reason = (
            f"town-progress-invariant:defect:{proposed_reason}=>{progress_reason}"
        )
        self._record_shop_selector_diagnostics(snapshot, progress_key)
        return progress_key

    def _boxed_town_breakout_key(self, snapshot: Snapshot) -> str | None:
        """Probe a distinct-landmark escape without opening a store visit."""
        route = self._boxed_town_breakout_route(snapshot)
        if route is None:
            here = snapshot.grid_at(snapshot.player.position)
            return WAIT_KEY if here is not None and here.store_number >= 0 else None
        store_type, goal, step = route
        if (
            self._has_light_equipped(snapshot)
            and goal in snapshot.grids
            and snapshot.player.position.distance_to(goal) >= TOWN_TRAVEL_MIN_DISTANCE
            and self._town_travel_fallback != goal
        ):
            return f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[store_type]}."
        return self._direction_key(snapshot.player.position, step)

    def _boxed_town_breakout_route(
        self, snapshot: Snapshot
    ) -> tuple[int, Position, Position] | None:
        """Return the first visible alternate-store route using derived map facts only."""
        here = snapshot.grid_at(snapshot.player.position)
        current_store = here.store_number if here is not None else -1
        for store_type in (STORE_HOME, STORE_MAGIC, STORE_ALCHEMIST, STORE_GENERAL):
            if store_type == current_store:
                continue
            route = self._nearest_goal_and_step(
                snapshot, lambda grid, wanted=store_type: grid.store_number == wanted
            )
            if route is None and self._town_map_active(snapshot):
                goal = self._town_map.store_position(store_type)
                step = self._town_map_goal_step(snapshot, goal)
                route = (goal, step) if step is not None else None
            if route is None:
                visible_goals = [
                    grid.position
                    for grid in snapshot.grids.values()
                    if grid.store_number == store_type
                ]
                if visible_goals:
                    goal = min(
                        visible_goals,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
                    if (
                        snapshot.player.position.distance_to(goal)
                        >= TOWN_TRAVEL_MIN_DISTANCE
                    ):
                        route = (goal, goal)
            if route is None:
                continue
            goal, step = route
            if step != snapshot.player.position:
                return store_type, goal, step
        return None

    def _commit_boxed_town_breakout_key(self, snapshot: Snapshot) -> str | None:
        """Open and compose the store visit only after the breakout probe wins."""
        here = snapshot.grid_at(snapshot.player.position)
        current_store = here.store_number if here is not None else -1
        for store_type in (STORE_HOME, STORE_MAGIC, STORE_ALCHEMIST, STORE_GENERAL):
            if store_type == current_store:
                continue
            step = self._shopping_approach_step(snapshot, store_type)
            if step is None:
                continue
            key = self._shopping_approach_key(
                snapshot, step, "town-progress-invariant:boxed-breakout-travel"
            )
            if key not in {"", WAIT_KEY}:
                return key
        return None

    def _town_entrance_step_off_key(
        self, snapshot: Snapshot, prior_reason: str | None
    ) -> str:
        """Select the established safe, least-visited exit from an entrance."""
        origin = snapshot.player.position
        candidates: list[Position] = []
        for dy, dx in NEIGHBOR_OFFSETS:
            candidate = Position(origin.y + dy, origin.x + dx)
            grid = snapshot.grids.get(candidate)
            if (
                grid is None
                or not grid.passable
                or grid.has_monster
                or grid.is_door
                or grid.has_entrance
                or grid.store_number >= 0
                or grid.building_special >= 0
                or grid.has_quest_enter
                or grid.has_quest_exit
                or candidate in self._warning_refused_cells
                or candidate in self._engagement_owned_avoid_cells
                or self._is_avoidable_hazard_grid(grid)
                or self._on_town_border(snapshot, candidate)
            ):
                continue
            candidates.append(candidate)
        if not candidates:
            if prior_reason == "equipment-transaction:abandon-blocked":
                # Escape is inert at the outside command loop and, unlike stay,
                # cannot enter the store beneath the player.  Preserve the
                # restoration owner's durable progress marker for harness/CLI
                # visibility when the emitter discloses no safe step-off cell.
                return LEAVE_STORE_KEY
            self.last_reason = "livelock:exhausted"
            return WAIT_KEY
        step = min(candidates, key=lambda position: self._visit_counts[position])
        key = self._step_toward(snapshot, step)
        if not (
            (prior_reason or "").startswith("town:blocked:")
            or prior_reason == "equipment-transaction:abandon-blocked"
        ):
            self.last_reason = f"town:entrance-step-off:{prior_reason or 'wait'}"
        return key

    def _release_stale_town_block(self, snapshot: Snapshot) -> None:
        """Release snapshot-local verdicts; declared drive terminals persist."""
        del snapshot
        latch = self._cross_decision_latches["_town_blocked_reason"]
        reason = self._town_blocked_reason
        if (
            reason not in {*latch.permanent_values, *latch.retained_values}
            and not any(
                (reason or "").startswith(prefix)
                for prefix in latch.retained_prefixes
            )
        ):
            self._town_blocked_reason = None

    def _town_departure_ready(
        self, snapshot: Snapshot, ignore_free_slots: bool = False
    ) -> bool:
        if snapshot.player.class_id < 0:
            return True
        return all(
            self._town_departure_conjuncts(
                snapshot, ignore_free_slots=ignore_free_slots
            ).values()
        )

    def _town_departure_conjuncts(
        self, snapshot: Snapshot, *, ignore_free_slots: bool = False
    ) -> dict[str, bool]:
        """Evaluate and name every leaf of the ordinary town departure gate."""
        player = snapshot.player
        free_slots_ok = (
            ignore_free_slots
            or self._town_pack_space_ready(snapshot)
        )

        home_required = self._home_available(snapshot)
        return {
            "recall_departure_ready": self._recall_departure_ready(snapshot),
            # A calibration-stripped character must be re-dressed (by the
            # restore session or a completed optimizer transaction) before ANY
            # departure path — including every pre-existing escape valve
            # deeper in this conjunction — can open.
            "calibration_loadout_restored": not self._calibration_stripped_unrestored,
            "food_ready": (
                self._fundraising_food_ready(snapshot)
                if self._fundraising_mode in {"prepare", "mine", "scavenge"}
                else self._food_ready(snapshot)
            ),
            "light_ready": self._light_ready(snapshot),
            "quest_carry_ready": (
                self._fundraising_mode in {"mine", "scavenge"}
                or (strategy := self._carry_procurement_strategy(snapshot)) is None
                or all(
                    bool(status["ready"])
                    or name in self._abandoned_quest_carry_requirements
                    for name, status in self._quest_carry_status(
                        snapshot, strategy.required_force
                    ).items()
                )
            ),
            "teleport_ready": self._teleport_ready(snapshot),
            "cure_critical_ready": self._cure_critical_ready(snapshot),
            "identify_staff_ready": self._identify_staff_ready(snapshot),
            "teleport_items_safe": not any(
                self._blocks_teleport(item)
                for item in (*snapshot.inventory, *snapshot.equipment)
            ),
            "free_pack_slots_ready": free_slots_ok,
            "inventory_weight_ready": not self._inventory_overweight(snapshot),
            "hp_full": player.hp >= player.max_hp,
            "mp_full": player.mp >= player.max_mp,
            "temporary_status_clear": self._temporary_status_clear(snapshot),
            "organization_complete": (
                self._find_town_organization_surplus(snapshot) is None
            ),
            "equipment_departure_ready": self._equipment_departure_ready(snapshot),
            "home_candidate_resolved": (
                not home_required or not self._home_candidate_waiting
            ),
            # A bounded Home pass can end with the page catalog still
            # incomplete. Once Home is blocked, defer unroutable catalog work.
            "home_catalog_ready": not home_required or (
                self._equipment_catalog.home_scan_complete
                or not self._home_catalog_routable(snapshot)
            ),
            "home_pending_item_clear": (
                not home_required or self._home_pending_item is None
            ),
            "home_pending_batch_clear": (
                not home_required or not self._home_pending_batch
            ),
            "home_batch_review_clear": (
                not home_required or not self._home_batch_review_items
            ),
            "home_atomic_withdraw_clear": (
                self._home_atomic_withdraw_pending is None
            ),
            "digger_withdrawal_resolved": (
                not self._home_digger_withdraw_pending
                or self._digger_fallback_bought_this_visit
            ),
            "identification_need_clear": (
                not home_required or self._identification_need is None
            ),
            # Never depart mid-calibration or with its supplies still at Home.
            "calibration_phase_complete": (
                not home_required or not self._calibration_active()
            ),
            "calibration_restore_complete": (
                not home_required or not self._calibration_restore_signatures
            ),
        }

    def _town_pack_space_ready(self, snapshot: Snapshot) -> bool:
        """Accept four slots only after the town pipeline exhausted this pack."""
        free_slots = PACK_CAPACITY - len(snapshot.inventory)
        if free_slots >= MIN_FREE_PACK_SLOTS:
            return True
        if not snapshot.in_town or free_slots < MIN_TERMINAL_FREE_PACK_SLOTS:
            return False
        return self._terminal_pack_space_signature == self._town_pack_space_signature(
            snapshot
        )

    def _recall_town_departure_conjuncts(self, snapshot: Snapshot) -> dict[str, bool]:
        """Return the complete leaf set consumed by a town recall decision."""
        values = self._town_departure_conjuncts(snapshot)
        values.update(
            {
                "combat_weapon_ready": self._combat_weapon_ready(snapshot),
                "departure_home_pending_item_clear": self._home_pending_item is None,
                "departure_home_pending_batch_clear": not self._home_pending_batch,
                "departure_home_batch_review_clear": not self._home_batch_review_items,
                "departure_home_atomic_withdraw_clear": (
                    self._home_atomic_withdraw_pending is None
                ),
                "departure_identification_need_clear": (
                    self._identification_need is None
                ),
            }
        )
        return values

    @staticmethod
    def _town_pack_space_signature(
        snapshot: Snapshot,
    ) -> tuple[tuple[object, ...], ...]:
        """Return the exact inventory state certified by the terminal fallback."""
        return tuple(
            (item.slot, item.name, item.tval, item.sval, item.count)
            for item in snapshot.inventory
        )

    def _town_overflow_destroy_key(self, snapshot: Snapshot) -> str | None:
        """Free town pack space without creating floor-item pickup loops."""
        return self._verified_destroy_key(
            snapshot,
            self._overflow_disposal_item,
            "town:destroy-overflow",
        )

    def _town_device_processing_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town:
            return None
        target = self._first_item(
            snapshot,
            lambda item: self._normal_identification_flow_candidate(item)
            and not item.is_equipment
            and self._item_signature(item) not in self._deferred_device_items,
        )
        if target is None:
            return None
        source = self._find_identification_source(
            snapshot, full=False, reliable_only=True
        )
        if source is None:
            self._request_identification("normal")
            self._device_identification_candidate = self._item_signature(target)
            return None
        # Verify the identify lands: if the same device is still unknown and the
        # unknown-device count has not moved, the staff/scroll use did not take
        # (a stalled prompt) — defer it after a few tries rather than looping.
        unknown_devices = sum(
            1
            for it in snapshot.inventory
            if self._normal_identification_flow_candidate(it)
            and not it.is_equipment
        )
        watch = (self._item_signature(target), unknown_devices)
        if watch == self._device_identify_watch:
            self._device_identify_fail_streak += 1
            if self._device_identify_fail_streak >= IDENTIFY_FAIL_LIMIT:
                self._deferred_device_items.add(self._item_signature(target))
                self._device_identify_watch = None
                self._device_identify_fail_streak = 0
                return None
        else:
            self._device_identify_watch = watch
            self._device_identify_fail_streak = 0
        command, item = source
        self._identification_need = None
        self._device_identification_candidate = None
        self.last_reason = "identify:device"
        if command == READ_KEY:
            return self._read_key(snapshot, item, target.slot)
        return command + item.slot + target.slot

    def _town_item_processing_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town:
            return None
        self._activate_home_batch_item()
        if self._home_pending_item is None:
            target = self._first_item(
                snapshot,
                # The optimizer catalogs every carried equipment item, not only
                # jewellery. Select from that same domain dynamically: prime()'s
                # startup batch cannot see an ego weapon acquired later in the
                # run, which caused the 2026-07-20 incomplete-catalog deadlock.
                lambda item: item.is_equipment
                and self._item_signature(item) not in self._deferred_home_items
                and self._item_signature(item) not in self._unidentifiable_sigs
                and self._item_signature(item)
                not in self._town_unidentifiable_carried_sigs
                and self._identification_flow_candidate(item),
            )
            if target is None:
                return None
            full = target.known
            key = self._carried_identify_command(snapshot, target, full=full)
            if key is None:
                if (
                    self._item_signature(target) in self._unidentifiable_sigs
                    or self._item_signature(target)
                    in self._town_unidentifiable_carried_sigs
                ):
                    return None
                signature = self._item_signature(target)
                if full and STORE_ALCHEMIST in self._town_store_attempted:
                    self._defer_full_identification(signature)
                else:
                    self._identification_candidate = signature
                    self._request_identification("full" if full else "normal")
                return None
            self._identification_need = None
            self._identification_candidate = None
            self.last_reason = "identify:full" if full else "identify:normal"
            return key
        if self._home_withdrawal_queued:
            # The in-store chooser has selected a Home identity, but the atomic
            # composer has not withdrawn it yet.  Surface item processing runs
            # before the Home approach owner, and an already-carried stack may
            # have the same name/tval/sval signature as the stored stack.  Do
            # not mistake that pre-existing stack for withdrawal success.  A
            # posted atomic command clears this queued state before the newly
            # observed inventory may be processed.
            return None
        target = self._pending_inventory_item(snapshot)
        if target is None:
            # The Home command can be rejected (for example by a prompt timing
            # mismatch). Do not alternate forever between leaving and re-entering
            # the store: defer this candidate for the current town visit and let
            # higher-priority resupply/fundraising continue.
            self._defer_home_item(
                self._home_pending_item, "town-item-processing-missing-pending"
            )
            self._release_identification_source_reservation(self._home_pending_item)
            self._home_pending_item = None
            self._home_pending_slot = None
            self._home_active_from_batch = False
            self._identification_need = None
            self._identification_candidate = None
            self._home_candidate_waiting = not self._home_pending_batch
            self._town_blocked_reason = None
            self.last_reason = "home:withdraw-failed-deferred"
            if self._home_pending_batch:
                return self._town_item_processing_key(snapshot)
            return None
        if (
            self._home_atomic_withdraw_pending is not None
            and self._home_atomic_withdraw_pending[0] == self._home_pending_item
        ):
            self._home_atomic_withdraw_pending = None

        if not target.known and target.pseudo_feeling != "average":
            key = self._carried_identify_command(
                snapshot,
                target,
                full=False,
                reservation_target=self._home_pending_item,
            )
            if key is None:
                self._request_identification("normal")
                return None
            self._identification_need = None
            if self._identification_source_reservation is not None:
                self._identification_source_reservation["state"] = "identifying"
            self.last_reason = "identify:normal"
            return key

        if target.known and self._identification_flow_candidate(target):
            source = self._find_identification_source(
                snapshot,
                full=True,
                reservation_target=self._home_pending_item,
            )
            if source is None:
                signature = self._item_signature(target)
                if STORE_ALCHEMIST in self._town_store_attempted:
                    self._defer_full_identification(signature)
                else:
                    self._request_identification("full")
                return None
            command, item = source
            self._identification_need = None
            if self._identification_source_reservation is not None:
                self._identification_source_reservation["state"] = "identifying"
            self.last_reason = "identify:full"
            if command == READ_KEY:
                return self._read_key(
                    snapshot, item, target.slot + FULL_IDENTIFY_DISMISS_SUFFIX
                )
            return command + item.slot + target.slot + FULL_IDENTIFY_DISMISS_SUFFIX

        target_signature = self._item_signature(target)
        self._release_identification_source_reservation(self._home_pending_item)
        self._processed_home_items.add(target_signature)
        if self._home_active_from_batch:
            self._home_pending_item = None
            self._home_pending_slot = None
            self._home_active_from_batch = False
            self._identification_need = None
            self._identification_candidate = None
            self._home_candidate_waiting = False
            if self._home_pending_batch:
                return self._town_item_processing_key(snapshot)
            self.last_reason = "identify:batch-complete"
            return None

        self._home_pending_item = None
        self._home_pending_slot = None
        self._home_active_from_batch = False
        self._identification_need = None
        self._identification_candidate = None
        self._home_candidate_waiting = not self._home_pending_batch
        if self._home_pending_batch:
            self.last_reason = "home:process-next-batch-item"
            return WAIT_KEY
        self.last_reason = "identify:complete"
        return None

    def _town_destroy_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or not self._destroy_pending:
            return None
        target = self._pending_disposal(snapshot)
        if target is None:
            self._clear_pending_disposal()
            self.last_reason = "equipment:destroy-complete"
            return None
        if self._destroy_attempts >= STORE_STUCK_LIMIT:
            self._town_blocked_reason = "dominated-item-destroy-failed"
            self.last_reason = "town:blocked:dominated-item-destroy-failed"
            return WAIT_KEY
        self._destroy_attempts += 1
        self.last_reason = "equipment:destroy-unsellable-dominated"
        return self._destroy_item_key(target)

    def _town_need_candidates(self, snapshot: Snapshot) -> list[TownNeed]:
        """Mechanically evaluate the predicates backing the town need registry."""
        needs: list[TownNeed] = []
        fundraising_active = (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and snapshot.player.gold < FUNDRAISING_GOLD_TARGET
            and not self._opening_q34_active(snapshot)
        )
        star_reserve_surplus = (
            snapshot.player.gold >= FUNDRAISING_GOLD_TARGET
            and not self._recall_departure_shortage(snapshot)
        )

        def add(store_type: int, category: str, ordering_class: str = "normal") -> None:
            needs.append(TownNeed(store_type, category, ordering_class))

        if self._calibration_active():
            # The unequipped calibration phase owns the town while it runs.
            # The only legitimate errand is Home: deposits going in, the pack
            # restore coming out.  Every other need is suppressed — in
            # particular a supply purchase would feed the deposit loop its own
            # replacements (deposit -> shortage -> buy -> deposit ...).
            if (
                self._calibration_phase in {"deposit", "restore-supplies"}
                and self._home_available(snapshot)
                and STORE_HOME not in self._town_store_attempted
            ):
                add(
                    STORE_HOME,
                    "calibration-restore"
                    if self._calibration_phase == "restore-supplies"
                    else "deposit",
                    "home-first",
                )
            return needs

        if (
            self._home_disposal_pass
            and snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
        ):
            # An opportunistic scan may share an already-owned Home visit, but
            # it is not executable Home work and must never create a visit by
            # itself.  With no surface need, the errand plan advances to real
            # work/departure instead of entering, scanning, and leaving.
            add(STORE_HOME, "idle-consumable-scan", "home-first")
        if self._home_disposal_pending is not None:
            signature, decision = self._home_disposal_pending
            target = self._home_disposal_inventory_item(snapshot)
            if decision == "sell" and target is not None:
                if not target.known and self._find_identification_source(
                    snapshot, full=False, reliable_only=True
                ) is None:
                    add(STORE_ALCHEMIST, "home-disposal-identify")
                else:
                    add(self._home_disposal_store(signature), "home-disposal-sale")

        if snapshot.player.class_id < 0:
            if not self._shopping_abandoned and snapshot.player.gold >= LANTERN_MIN_GOLD:
                if not self._owns_lantern(snapshot):
                    add(STORE_GENERAL, "birth-supplies")
                if self._needs_food_restock(snapshot):
                    add(
                        STORE_MAGIC
                        if snapshot.player.food_type == FOOD_TYPE_MANA
                        else STORE_GENERAL,
                        "birth-supplies",
                    )
            return needs

        # The approved fresh-character route is intentionally tiny: acquire
        # Q34's complete throwing-torch stock, then let _fixed_quest_key accept
        # it on the next decision.  In particular, do not let low-gold
        # fundraising turn its own missing digger/detection kit into an earlier
        # Home or Alchemist stop; that created a circular readiness lock where
        # Q34 waited for torches while fundraising hid their procurement need.
        if self._opening_q34_active(snapshot):
            equipped_weapon = next(
                (item for item in snapshot.equipment if item.slot == "main_hand"),
                None,
            )
            if (
                equipped_weapon is None
                and not self._pack_has_safe_melee_weapon(snapshot)
            ):
                add(STORE_HOME, "combat-weapon", "home-first")
                return needs
        if self._opening_q34_torch_shortage(snapshot) > 0:
            add(STORE_GENERAL, "quest-throwing-items", "opening-quest")
            return needs

        self._begin_pack_dominated_launcher_disposal(snapshot)
        if (
            self._pending_disposal_item is not None
            and (target := self._pending_disposal(snapshot)) is not None
        ):
            disposal_store = self._dominated_disposal_store(target)
            if disposal_store is not None and disposal_store not in self._disposal_store_attempts:
                add(disposal_store, "disposal")
        if self._pending_disposal_item is not None:
            return needs

        equipped_weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        blocked_weapon_in_pack = any(
            item.is_melee_weapon and self._blocks_teleport(item)
            for item in snapshot.inventory
        )
        safe_weapon_equipped = (
            equipped_weapon is not None
            and equipped_weapon.is_melee_weapon
            and not self._blocks_teleport(equipped_weapon)
        )
        if (
            (
                self._no_teleport_rearm_pending
                or (equipped_weapon is not None and self._blocks_teleport(equipped_weapon))
                or (blocked_weapon_in_pack and not safe_weapon_equipped)
            )
            and not self._pack_has_safe_melee_weapon(snapshot)
        ):
            add(STORE_HOME, "safe-weapon", "home-first")
        if (
            self._equipped_digging_tool(snapshot) is not None
            and not self._pack_has_safe_melee_weapon(snapshot)
            and not self._combat_weapon_ready(snapshot)
        ):
            add(STORE_HOME, "combat-weapon", "home-first")
        book_sale = self._find_book_sale(snapshot)
        if book_sale is not None:
            add(self._book_sale_store_type(book_sale), "book-sale")
        organization = self._find_town_organization_surplus(snapshot)
        organization_store = (
            self._town_organization_sale_store(snapshot, organization)
            if organization is not None
            else None
        )
        if organization_store is not None:
            add(organization_store, "organization-sale")
        elif (
            organization is not None
            and self._identification_need is None
            and self._town_organization_home_routable(snapshot, organization)
        ):
            # Required organization remains routable during fundraising; this
            # is the existing Home deposit need and deposit machinery.
            add(STORE_HOME, "deposit", "home-first")
        if (
            self._home_available(snapshot)
            and self._inventory_overweight(snapshot)
            and self._find_home_deposit(snapshot) is not None
        ):
            add(STORE_HOME, "weight-overload", "home-first")
        elif (
            self._identification_need is None
            and self._home_available(snapshot)
            and STORE_HOME not in self._town_store_attempted
            and not fundraising_active
            and self._find_home_deposit(snapshot) is not None
        ):
            add(STORE_HOME, "deposit", "home-first")
        procurement_probe = getattr(self, "_home_procurement_probe", None)
        if procurement_probe is not None and (
            (
                procurement_probe[0] == TVAL_FOOD
                and procurement_probe[1] >= FOOD_MIN_SVAL
                and self._food_ready(snapshot)
            )
            or (
                procurement_probe[0] in {TVAL_WAND, TVAL_STAFF}
                and self._count_mana_food_devices(snapshot) > 0
            )
            or any(
                self._procurement_class_matches(item, procurement_probe)
                for item in snapshot.inventory
            )
        ):
            self._home_procurement_probe = None
            procurement_probe = None
        if (
            procurement_probe is not None
            and self._home_available(snapshot)
            and STORE_HOME not in self._town_store_attempted
        ):
            add(STORE_HOME, "procurement-home-first", "home-first")
        if self._needs_stat_restore(snapshot) and STORE_ALCHEMIST not in self._town_store_attempted:
            add(STORE_ALCHEMIST, "stat-restore")
        low_level_sale = self._find_low_level_sale(snapshot)
        if low_level_sale is not None:
            add(STORE_ALCHEMIST, "low-level-sale")
        elif (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and self._first_item(
                snapshot,
                lambda item: item.tval == TVAL_FOOD
                and self._retention_surplus(snapshot, item) > 0
                and self._item_signature(item) not in self._unsellable_items,
            )
            is not None
        ):
            add(STORE_GENERAL, "mana-food-sale")
        unknown_device = self._first_item(
            snapshot,
            lambda item: item.tval in {TVAL_WAND, TVAL_STAFF}
            and not item.known
            and self._item_signature(item) not in self._deferred_device_items,
        )
        device_processing_actionable = (
            unknown_device is not None
            and self._find_identification_source(
                snapshot, full=False, reliable_only=True
            ) is not None
        )
        if (
            not device_processing_actionable
            and self._find_device_sale(snapshot) is not None
            and STORE_MAGIC not in self._town_store_attempted
        ):
            add(STORE_MAGIC, "device-sale")
        if self._find_weapon_sale(snapshot) is not None and STORE_WEAPON not in self._town_store_attempted:
            add(STORE_WEAPON, "weapon-sale")
        if self._find_light_sale(snapshot) is not None and STORE_GENERAL not in self._town_store_attempted:
            add(STORE_GENERAL, "light-sale")

        if fundraising_active:
            if (
                self._digger_buy_fallback_available(snapshot)
                and STORE_GENERAL not in self._town_store_attempted
            ):
                add(STORE_GENERAL, "fundraising-digger")
            if not self._fundraising_kit_secured(snapshot):
                if STORE_HOME not in self._town_store_attempted:
                    add(STORE_HOME, "fundraising-kit", "home-first")
                if (
                    not self._has_withdrawable_digging_tool(snapshot)
                    or self._digger_buy_fallback_available(snapshot)
                ):
                    if STORE_GENERAL not in self._town_store_attempted:
                        add(STORE_GENERAL, "fundraising-digger")
                if not self._has_withdrawable_treasure_detection(snapshot):
                    if STORE_ALCHEMIST not in self._town_store_attempted:
                        add(STORE_ALCHEMIST, "fundraising-detection")
            if not self._fundraising_food_ready(snapshot):
                food_store = STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL
                if food_store not in self._town_store_attempted:
                    add(food_store, "fundraising-food")
            if self._planned_mining_runs is None:
                remaining_cap = max(0, MINING_RUNS_PER_SET - self._mining_runs_completed)
                additional_runs = min(
                    remaining_cap,
                    self._count_treasure_detection_scrolls(snapshot),
                )
                planned_runs = self._mining_runs_completed + max(0, additional_runs)
            else:
                planned_runs = self._planned_mining_runs
            scrolls_needed = max(0, planned_runs - self._mining_runs_completed)
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                if STORE_HOME not in self._town_store_attempted:
                    add(STORE_HOME, "stored-detection", "home-first")
                if STORE_ALCHEMIST not in self._town_store_attempted:
                    add(STORE_ALCHEMIST, "mining-detection")
            if (
                self._fundraising_mode != "scavenge"
                and self._digging_tool_count(snapshot) < 2
                and self._count_treasure_detection_scrolls(snapshot) > 0
            ):
                if (
                    STORE_HOME not in self._town_store_attempted
                    and any(
                        owned.origin == "home" and owned.item.is_digging_tool
                        for owned in self._equipment_catalog.items
                    )
                ):
                    add(STORE_HOME, "stored-digger", "home-first")
                if (
                    STORE_GENERAL not in self._town_store_attempted
                    and (
                        self._withdrawable_digging_tool_count(snapshot) < 2
                        or self._digger_buy_fallback_available(snapshot)
                    )
                ):
                    add(STORE_GENERAL, "mining-digger")
            if not self._fundraising_light_ready(snapshot):
                if STORE_GENERAL not in self._town_store_attempted:
                    add(STORE_GENERAL, "fundraising-light")
            if (
                self._owns_lantern(snapshot)
                and self._oil_below_departure_target(snapshot)
                and STORE_GENERAL not in self._town_store_attempted
            ):
                add(STORE_GENERAL, "fundraising-oil")
            mandatory_supplies_ready = (
                self._fundraising_kit_secured(snapshot)
                and self._count_treasure_detection_scrolls(snapshot) >= scrolls_needed
                and self._fundraising_food_ready(snapshot)
                and self._fundraising_light_ready(snapshot)
                and not (
                    self._owns_lantern(snapshot)
                    and self._oil_below_departure_target(snapshot)
                )
            )
            if mandatory_supplies_ready:
                if (
                    self._equipped_launcher(snapshot) is not None
                    and self._count_matching_ammo(snapshot) < AMMO_CARRY_TARGET
                    and STORE_WEAPON not in self._town_store_attempted
                ):
                    add(STORE_WEAPON, "ammo")
                if (
                    self._fundraising_mode in {"prepare", "mine", "scavenge"}
                    and self._planned_depth() <= TORCH_THROW_MAX_DEPTH
                    and self._matching_ammo(snapshot) is None
                    and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
                    and STORE_GENERAL not in self._town_store_attempted
                ):
                    add(STORE_GENERAL, "throwing-torches")
            return needs

        bindable_home_identification = any(
            owned.origin == "home"
            and owned.identification_incomplete
            and self._item_signature(owned.item) not in self._deferred_home_items
            for owned in self._equipment_catalog.items
        )
        home_identification_unsatisfiable = (
            self._equipment_catalog.home_scan_complete
            and self._home_knowledge_current
            and self._identification_candidate is None
            and not bindable_home_identification
        )
        home_identification_claim = (
            self._home_errand.active
            or (
                self._identification_candidate is None
                and not home_identification_unsatisfiable
            )
            or any(
                owned.origin == "home"
                and self._item_signature(owned.item)
                == self._identification_candidate
                and self._item_signature(owned.item)
                not in self._deferred_home_items
                for owned in self._equipment_catalog.items
            )
        )
        if self._identification_need is not None:
            source = self._find_identification_source(
                snapshot,
                full=self._identification_need == "full",
                reliable_only=self._identification_requires_reliable_source(snapshot),
            )
            if source is None and STORE_ALCHEMIST not in self._town_store_attempted:
                add(STORE_ALCHEMIST, "identification-source", "before-withdrawal")
            elif (
                self._home_candidate_waiting
                and home_identification_claim
                and self._home_available(snapshot)
            ):
                add(
                    STORE_HOME,
                    "identification-withdrawal",
                    "post-alchemist-home",
                )
        elif (
            self._home_candidate_waiting
            and home_identification_claim
            and self._home_available(snapshot)
        ):
            add(
                STORE_HOME,
                "identification-withdrawal",
                "post-alchemist-home",
            )

        supply_categories = {
            "recall": "recall", "food": "food", "oil": "oil",
            "teleport": "teleport", "cure": "cure-critical",
        }
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        for status in self._ledger_departure_shortages(ledger):
            for store_type in status.stores:
                remembered = self._town_supplier_stock.get(store_type)
                remembered_affordable = bool(
                    remembered is not None
                    and any(
                        item.price <= snapshot.player.gold
                        and self._store_item_is_supply(item, status.kind)
                        for item in remembered.items
                    )
                )
                if (
                    store_type not in self._town_store_attempted
                    or store_type == STORE_HOME
                    or remembered_affordable
                ):
                    add(store_type, supply_categories[status.kind])
        if self._identification_need is not None:
            # Identification remains primary, while the supply ledger retains
            # its independent departure claims.
            return needs
        quest_strategy = self._carry_procurement_strategy(snapshot)
        if quest_strategy is not None:
            force = quest_strategy.required_force
            carry_status = self._quest_carry_status(snapshot, force)
            missing_carries = {
                name for name, status in carry_status.items()
                if (
                    not bool(status["ready"])
                    and name not in self._abandoned_quest_carry_requirements
                )
            }
            if "throwing_items.lit_torch" in missing_carries:
                home_torch = self._home_procurement_candidate(
                    (TVAL_LITE, SV_LITE_TORCH)
                )
                if home_torch is not None:
                    if self._home_pending_item is None:
                        self._home_pending_item = self._item_signature(home_torch)
                        torch_status = carry_status["throwing_items.lit_torch"]
                        self._home_pending_quantity = max(
                            1,
                            int(torch_status["required"]) - int(torch_status["measured"]),
                        )
                    add(STORE_HOME, "quest-throwing-items", "home-first")
                if (
                    STORE_GENERAL not in self._town_store_attempted
                    or self._quest_carry_remembered_affordable(
                        snapshot,
                        quest_strategy,
                        "throwing_items.lit_torch",
                        STORE_GENERAL,
                    )
                ):
                    add(STORE_GENERAL, "quest-throwing-items")
            self._abandon_unobtainable_quest_carries(snapshot, quest_strategy)
            home_launcher = self._preferred_home_quest_launcher(
                snapshot, quest_strategy
            )
            if "launcher" in missing_carries and home_launcher is not None:
                add(STORE_HOME, "quest-launcher", "home-first")
            if missing_carries & {
                "throwing_items.shot",
                "throwing_items.arrow",
                "throwing_items.bolt",
                "throwing_items.launcher_ammo",
            } or ("launcher" in missing_carries and home_launcher is None):
                remembered_affordable = any(
                    self._quest_carry_remembered_affordable(
                        snapshot, quest_strategy, name, STORE_WEAPON
                    )
                    for name in missing_carries
                    if STORE_WEAPON in self._quest_carry_suppliers(name)
                )
                if (
                    STORE_WEAPON not in self._town_store_attempted
                    or remembered_affordable
                ):
                    add(STORE_WEAPON, "quest-ranged-kit")
            if any(name.startswith("required_scrolls.") for name in missing_carries):
                if (
                    STORE_ALCHEMIST not in self._town_store_attempted
                    or any(
                        self._quest_carry_remembered_affordable(
                            snapshot, quest_strategy, name, STORE_ALCHEMIST
                        )
                        for name in missing_carries
                        if name.startswith("required_scrolls.")
                    )
                ):
                    add(STORE_ALCHEMIST, "quest-scrolls")
            if "utility_tools.wall_breach" in missing_carries:
                # Stone-to-Mud is not in the normal Magic-shop table.  It can
                # appear in the Black Market's random stock, so inspect that
                # store once before checking the General Store for an eligible
                # +3 digger.  Neither random stock is waited on indefinitely.
                if (
                    STORE_BLACK not in self._town_store_attempted
                    or self._quest_carry_remembered_affordable(
                        snapshot,
                        quest_strategy,
                        "utility_tools.wall_breach",
                        STORE_BLACK,
                    )
                ):
                    add(STORE_BLACK, "quest-wall-breach")
                elif (
                    STORE_GENERAL not in self._town_store_attempted
                    or self._quest_carry_remembered_affordable(
                        snapshot,
                        quest_strategy,
                        "utility_tools.wall_breach",
                        STORE_GENERAL,
                    )
                ):
                    add(STORE_GENERAL, "quest-wall-breach")
            if (
                self._exact_potion_count(snapshot, SV_POTION_SPEED)
                < int(force.get("speed_potions", 0))
                and STORE_BLACK not in self._town_store_attempted
            ):
                add(STORE_BLACK, "quest-speed")
            healing = self._exact_potion_count(snapshot, SV_POTION_HEALING)
            if healing < int(force.get("heal_potions", 0)):
                if STORE_TEMPLE not in self._town_store_attempted:
                    add(STORE_TEMPLE, "quest-healing")
                if STORE_BLACK not in self._town_store_attempted:
                    add(STORE_BLACK, "quest-healing")
        if not self._light_ready(snapshot):
            if STORE_GENERAL in self._town_store_attempted:
                return needs
            add(STORE_GENERAL, "light")
        if not self._identify_staff_ready(snapshot):
            if STORE_MAGIC in self._town_store_attempted:
                return needs
            add(STORE_MAGIC, "identify-staff")
        # Ammo is an optional supply: restock when low, but never block the
        # visit on it (the Weapon Smith always stocks SHOT/ARROW/BOLT).
        if (
            self._equipped_launcher(snapshot) is not None
            and self._count_matching_ammo(snapshot) < AMMO_CARRY_TARGET
            and STORE_WEAPON not in self._town_store_attempted
        ):
            add(STORE_WEAPON, "ammo")
        # Throwing torches for the early floors (user directive). Routed only
        # for fundraising trips (the shallow 1-10F fighting happens there);
        # ordinary visits still buy torches opportunistically when the General
        # Store is entered for another errand. Never blocks the visit.
        if (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and self._planned_depth() <= TORCH_THROW_MAX_DEPTH
            and self._matching_ammo(snapshot) is None
            and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
            and STORE_GENERAL not in self._town_store_attempted
        ):
            add(STORE_GENERAL, "throwing-torches")
        if (
            self._has_normal_remove_curse_target(snapshot)
            and self._find_remove_curse_scroll(snapshot) is None
        ):
            if STORE_TEMPLE in self._town_store_attempted:
                return needs
            add(STORE_TEMPLE, "remove-curse")
        carried_star_reserve = self._carried_star_remove_curse_count(snapshot) > 0
        if (
            self._has_unremovable_curse_target(snapshot)
            # A fresh policy must inspect Home before considering a new shop
            # purchase; otherwise it can buy while the reserve already sits on
            # an unobserved Home page.
            and self._home_star_remove_curse_count != 0
            and not carried_star_reserve
            and not self._recall_departure_shortage(snapshot)
        ):
            add(STORE_HOME, "home-star-remove-curse-use", "home-first")
        if (
            star_reserve_surplus
            and self._star_remove_curse_shelf_seen
            and self._home_star_remove_curse_count is None
            and not carried_star_reserve
        ):
            add(STORE_HOME, "home-star-remove-curse-check", "home-first")
        if (
            star_reserve_surplus
            and self._star_remove_curse_shelf_seen
            and self._home_star_remove_curse_count == 0
            and not carried_star_reserve
            and not self._star_remove_curse_reserve_deposit_pending
        ):
            add(STORE_TEMPLE, "home-star-remove-curse-stock")
        # A latched heavy curse never creates a speculative Temple trip.  Keep
        # the stop only when the live shelf proves that an affordable *Remove
        # Curse* is available; this makes the attempt opportunistic and gives
        # neither departure nor the restock waiter a missing-stock obligation.
        if self._affordable_star_remove_curse(snapshot) is not None:
            add(STORE_TEMPLE, "star-remove-curse")
        if (
            getattr(
                self, "_town_need_evaluation_include_launcher_enchant", True
            )
            and self._launcher_enchant_needed_svals(snapshot)
            and snapshot.player.gold > FUNDRAISING_START_GOLD
            and self._launcher_enchant_registration_actionable(snapshot)
        ):
            add(STORE_ALCHEMIST, "launcher-enchant")
        if (
            snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and not (
                self._home_knowledge_current
                and self._home_scan_item_count == 0
            )
            and (
                (
                    not self._equipment_catalog.home_scan_complete
                    and self._home_catalog_routable(snapshot)
                )
                or self._has_actionable_incomplete_home_item(snapshot)
                or self._has_selected_home_random_teleport_suppression(snapshot)
            )
        ):
            add(STORE_HOME, "equipment-catalog", "home-first")
        if STORE_BLACK not in self._town_store_attempted:
            add(STORE_BLACK, "black-market")
        return needs

    def _town_need_registry(self) -> tuple[NeedSpec, ...]:
        """Build the single ordered producer/satisfaction registry once."""
        cached = getattr(self, "_town_need_specs", None)
        if cached is not None:
            return cached
        entries = (
            ("idle-consumable-scan", "home-first", 1, False),  # Idle Home scans are opportunistic.
            ("home-disposal-identify", "normal", 1, False),  # Disposal identification is opportunistic.
            ("home-disposal-sale", "normal", 1, False),  # Disposal sales are opportunistic.
            ("birth-supplies", "normal", 2, True),  # Birth supplies are required before the opening departure.
            ("quest-throwing-items", "opening-quest", 1, True),  # Opening Q34 stock gates quest acceptance.
            ("quest-throwing-items", "home-first", 1, True),  # Stored required throwing stock gates departure.
            ("disposal", "normal", 1, False),  # Dominated-item disposal is opportunistic.
            ("safe-weapon", "home-first", 1, True),  # A teleport-safe weapon is a departure safety gate.
            ("combat-weapon", "home-first", 1, True),  # Combat weapon readiness gates departure.
            ("book-sale", "normal", 1, False),  # Book sales are opportunistic.
            ("organization-sale", "normal", 1, True),  # Recognized surplus gates departure.
            ("weight-overload", "home-first", 1, True),  # Overweight inventory blocks departure.
            ("deposit", "home-first", 1, False),  # Non-mandatory Home deposits are convenience work.
            ("stat-restore", "normal", 1, True),  # Drained stats make departure unsafe.
            ("low-level-sale", "normal", 1, False),  # Low-level sales are opportunistic.
            ("mana-food-sale", "normal", 1, False),  # Surplus food sales are opportunistic.
            ("device-sale", "normal", 1, False),  # Device sales are opportunistic.
            ("weapon-sale", "normal", 1, False),  # Inferior weapon sales are opportunistic.
            ("light-sale", "normal", 1, False),  # Surplus light sales are opportunistic.
            ("fundraising-kit", "home-first", 1, True),  # The mining kit gates a fundraising run.
            ("fundraising-digger", "normal", 1, True),  # A digger gates a fundraising run.
            ("fundraising-detection", "normal", 1, True),  # Detection gates a fundraising run.
            ("fundraising-food", "normal", 1, True),  # Food gates a fundraising run.
            ("stored-detection", "home-first", 1, True),  # Stored detection gates a fundraising run.
            ("mining-detection", "normal", 1, True),  # Purchased detection gates a fundraising run.
            ("stored-digger", "home-first", 1, True),  # A stored digger gates a fundraising run.
            ("mining-digger", "normal", 1, True),  # A purchased digger gates a fundraising run.
            ("fundraising-light", "normal", 1, True),  # Light gates a fundraising run.
            ("fundraising-oil", "normal", 1, True),  # Oil gates a fundraising run.
            ("identification-source", "before-withdrawal", 1, True),  # Identification is consumed by departure readiness.
            ("identification-withdrawal", "post-alchemist-home", 1, True),  # The identification handoff gates departure.
            ("recall", "normal", 2, True),  # Recall supply feeds the departure ledger.
            ("teleport", "normal", 1, True),  # Teleport supply feeds the departure ledger.
            ("cure-critical", "normal", 2, True),  # Critical cures feed the departure ledger.
            ("oil", "normal", 1, True),  # Oil supply feeds the departure ledger.
            ("food", "normal", 2, True),  # Food supply feeds the departure ledger.
            ("quest-throwing-items", "normal", 1, True),  # Required throwing stock gates the quest departure.
            ("quest-launcher", "home-first", 1, True),  # A required launcher gates the quest departure.
            ("quest-ranged-kit", "normal", 1, True),  # Required ranged gear gates the quest departure.
            ("quest-scrolls", "normal", 1, True),  # Required scrolls gate the quest departure.
            ("quest-wall-breach", "normal", 1, True),  # Required wall breach gates the quest departure.
            ("quest-speed", "normal", 1, True),  # Required speed potions gate the quest departure.
            ("quest-healing", "normal", 2, True),  # Required healing potions gate the quest departure.
            ("light", "normal", 1, True),  # Expedition light gates departure.
            ("identify-staff", "normal", 1, True),  # Identification capacity gates departure.
            ("ammo", "normal", 1, False),  # Ordinary ammo restocking is optional.
            ("throwing-torches", "normal", 1, False),  # Non-quest throwing torches are optional.
            ("remove-curse", "normal", 1, True),  # An actionable carried curse makes departure unsafe.
            ("home-star-remove-curse-use", "home-first", 1, True),
            ("home-star-remove-curse-check", "home-first", 1, False),
            ("home-star-remove-curse-stock", "normal", 1, False),
            ("star-remove-curse", "normal", 1, False),  # Shelf-proven heavy-curse service is opportunistic.
            ("launcher-enchant", "normal", 1, False),  # Launcher enchanting is an optimization.
            ("equipment-catalog", "home-first", 1, False),  # Catalog completion yields to a ready departure.
            ("equipment-work", "home-first", 1, True),
            ("equipment-transaction", "home-first", 1, True),
            ("calibration-restore", "home-first", 1, True),
            ("black-market", "normal", 1, False),  # Black Market browsing is opportunistic.
        )
        specs: list[NeedSpec] = []
        for category, ordering_class, count, departure_blocking in entries:
            for occurrence in range(count):
                lookup = (
                    lambda snapshot, category=category,
                    ordering_class=ordering_class, occurrence=occurrence:
                    self._candidate_need(
                        snapshot, category, ordering_class, occurrence
                    )
                )
                produces = lambda snapshot, lookup=lookup: lookup(snapshot) is not None
                specs.append(
                    NeedSpec(
                        category=category,
                        store_type=lambda snapshot, lookup=lookup: (
                            lookup(snapshot).store_type  # type: ignore[union-attr]
                        ),
                        ordering_class=ordering_class,
                        produces=produces,
                        satisfied=lambda snapshot, produces=produces: not produces(snapshot),
                        departure_blocking=departure_blocking,
                    )
                )
        self._town_need_specs = tuple(specs)
        return self._town_need_specs

    def _town_claims_active(self, snapshot: Snapshot) -> bool:
        """Record live route owners from the same registry used by projection."""
        self._retire_actionless_equipment_failure(snapshot)
        self._refresh_nonhome_effect_refusals(snapshot)
        claims: list[str] = []
        departure_ready: bool | None = None
        specs = {spec.category: spec for spec in self._town_need_registry()}
        for need in self._enumerate_live_store_claims(snapshot):
            spec = specs.get(need.category)
            equipment_owner = need.category in {
                "equipment-work", "equipment-transaction"
            }
            home_visit_budget_exhausted = (
                need.store_type == STORE_HOME
                and getattr(self, "_home_visit", None) is not None
                and self._home_visit.attempts_used
                >= self._home_visit.attempt_limit
            )
            if (
                need.store_type
                in self._town_visit_ledger.nonhome_attempted_without_effect
                or (
                    need.store_type == STORE_HOME
                    and (
                        home_visit_budget_exhausted
                        or self._town_store_blocked_under_applicable_bound(
                            need.store_type
                        )
                        or self._town_visit_ledger.approach_fails[need.store_type]
                        >= self._town_store_visit_limit(need.store_type)
                        or (
                            spec is not None
                            and self._town_visit_ledger.need_attempts.get(
                                need.category, 0
                            ) >= spec.budget
                            and not equipment_owner
                            and not self._outstanding_equipment_work()
                        )
                    )
                )
            ):
                if (
                    need.store_type == STORE_HOME
                    and need.category == "weight-overload"
                    and self._inventory_overweight(snapshot)
                    and self._town_visit_ledger.approach_fails[STORE_HOME]
                    >= self._town_store_visit_limit(STORE_HOME)
                ):
                    # Claim retirement is still the town-liveness outcome, but
                    # an overweight character has no alternate supplier.  Hand
                    # the exhausted route directly to a diagnostic terminal.
                    self._town_blocked_reason = "overweight-home-unreachable"
                if (
                    home_visit_budget_exhausted
                    and need.category == "calibration-restore"
                ):
                    self._town_liveness_claim_retired = True
                continue
            if spec is not None and not spec.departure_blocking:
                if departure_ready is None:
                    departure_ready = self._town_departure_ready(snapshot)
                if departure_ready:
                    continue
            if need.category not in claims:
                claims.append(need.category)
        self._town_claim_categories = claims
        return bool(claims)

    def _enumerate_town_needs(self, snapshot: Snapshot) -> list[TownNeed]:
        """Return every currently true town errand from the shared registry."""
        needs: list[TownNeed] = []
        previous_snapshot = getattr(self, "_town_need_evaluation_snapshot", None)
        previous_candidates = getattr(
            self, "_town_need_evaluation_candidates", None
        )
        self._town_need_evaluation_snapshot = snapshot
        self._town_need_evaluation_candidates = self._town_need_candidates(snapshot)
        try:
            for spec in self._town_need_registry():
                if spec.produces(snapshot):
                    needs.append(
                        TownNeed(
                            spec.resolve_store_type(snapshot),
                            spec.category,
                            spec.ordering_class,
                        )
                    )
        finally:
            self._town_need_evaluation_snapshot = previous_snapshot
            self._town_need_evaluation_candidates = previous_candidates
        if (
            self._home_knowledge_current
            and self._home_scan_item_count == 0
            and not self._calibration_active()
            and self._equipment_transaction_session is None
        ):
            needs = [
                need
                for need in needs
                if need.store_type != STORE_HOME
                or need.category in {"deposit", "weight-overload"}
            ]
        return needs

    def _departure_blocking_town_needs(self, snapshot: Snapshot) -> list[TownNeed]:
        """Return live errands whose NeedSpec says they gate departure."""
        needs: list[TownNeed] = []
        previous_snapshot = getattr(self, "_town_need_evaluation_snapshot", None)
        previous_candidates = getattr(
            self, "_town_need_evaluation_candidates", None
        )
        self._town_need_evaluation_snapshot = snapshot
        self._town_need_evaluation_candidates = self._town_need_candidates(snapshot)
        try:
            for spec in self._town_need_registry():
                if spec.departure_blocking and spec.produces(snapshot):
                    needs.append(
                        TownNeed(
                            spec.resolve_store_type(snapshot),
                            spec.category,
                            spec.ordering_class,
                        )
                    )
        finally:
            self._town_need_evaluation_snapshot = previous_snapshot
            self._town_need_evaluation_candidates = previous_candidates
        if self._calibration_phase == "deposit" and self._home_available(snapshot):
            needs.append(TownNeed(
                STORE_HOME, "calibration-deposit", "home-first"
            ))
        return needs

    def _town_need_supplier_reachable(
        self, snapshot: Snapshot, need: TownNeed
    ) -> bool:
        """Whether a need's supplier has a live or remembered town route."""
        store = getattr(snapshot, "store", None)
        if store is not None and store.store_type == need.store_type:
            return True
        if any(
            grid.store_number == need.store_type
            for grid in getattr(snapshot, "grids", {}).values()
        ):
            return True
        if not hasattr(snapshot, "town_id"):
            return False
        store_position = getattr(self._town_map, "store_position", None)
        return bool(
            self._town_map_active(snapshot)
            and callable(store_position)
            and store_position(need.store_type) is not None
        )

    def _departure_supplier_counterfactual(
        self, snapshot: Snapshot
    ) -> int | None:
        """Return a reachable, obtainable supplier for a failing town gate."""
        supplier, _ = self._departure_supplier_core(snapshot)
        if supplier is not None:
            self._rearm_town_store_for_new_work(
                supplier, release_visit_bound=True
            )
        return supplier

    def _actionable_departure_supplier(self, snapshot: Snapshot) -> int | None:
        """Purely find a reachable supplier that owns a failing departure gate."""
        supplier, _ = self._departure_supplier_core(snapshot)
        return supplier

    def _launcher_enchant_registration_actionable(self, snapshot: Snapshot) -> bool:
        """Allow optional work only while the durable town plan is still live."""
        supplier, exhausted = self._departure_supplier_core(snapshot)
        return not exhausted and (
            self._town_departure_ready(snapshot) or supplier is not None
        )

    def _departure_supplier_core(
        self, snapshot: Snapshot
    ) -> tuple[int | None, bool]:
        """Purely find a supplier and report durable owner exhaustion."""
        previous_include_launcher_enchant = getattr(
            self, "_town_need_evaluation_include_launcher_enchant", True
        )
        self._town_need_evaluation_include_launcher_enchant = False
        try:
            candidates = self._departure_blocking_town_needs(snapshot)
        finally:
            self._town_need_evaluation_include_launcher_enchant = (
                previous_include_launcher_enchant
            )
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        supply_categories = {
            "recall": "recall", "food": "food", "oil": "oil",
            "teleport": "teleport", "cure": "cure-critical",
        }
        for status in self._ledger_departure_shortages(ledger):
            if status.obtainable:
                candidates.extend(
                    TownNeed(store, supply_categories[status.kind], "normal")
                    for store in status.stores
                )
        if self._equipment_retired_worn_item_ids or (
            self._equipment_failure_unexecutable_this_visit(
                snapshot,
                self._equipment_optimization_preparation,
                require_confirmed=False,
                include_launcher_enchant=False,
            )
        ):
            return None, True
        retired = set(getattr(self._town_turn_arbiter, "_retired", ()))
        for need in candidates:
            if not self._town_need_supplier_reachable(snapshot, need):
                continue
            if need.category in {"equipment-work", "equipment-transaction"} and (
                self._equipment_retired_worn_item_ids
                or "equipment-opt" in retired
                or "equipment-txn" in retired
            ):
                continue
            page = self._town_supplier_stock.get(need.store_type)
            remembered_affordable = bool(
                page is not None
                and any(item.price <= snapshot.player.gold for item in page.items)
            )
            if (
                need.store_type not in self._town_store_attempted
                or need.store_type == STORE_HOME
                or remembered_affordable
            ):
                return need.store_type, False
        return None, False

    def _order_town_stops(
        self, snapshot: Snapshot, stores: list[int], start: Position | None = None
    ) -> list[int]:
        """Nearest-neighbour order; numeric store order is the mapless fallback."""
        remaining = list(dict.fromkeys(stores))
        ordered: list[int] = []
        position = start or snapshot.player.position
        while remaining:
            if self._town_map_active(snapshot):
                store_type = min(
                    remaining,
                    key=lambda value: (
                        position.distance_to(self._town_map.store_position(value))
                        if self._town_map.store_position(value) is not None
                        else 10**9,
                        value,
                    ),
                )
                target = self._town_map.store_position(store_type)
                if target is not None:
                    position = target
            else:
                # Stable mapless circuit, chosen to retain the historical
                # high-value/service ordering while still batching by building.
                canonical = (
                    STORE_ARMOURY,
                    STORE_MAGIC,
                    STORE_WEAPON,
                    STORE_TEMPLE,
                    STORE_GENERAL,
                    STORE_ALCHEMIST,
                    STORE_BLACK,
                    STORE_HOME,
                )
                rank = {value: index for index, value in enumerate(canonical)}
                store_type = min(remaining, key=lambda value: (rank.get(value, 99), value))
            remaining.remove(store_type)
            ordered.append(store_type)
        return ordered

    @staticmethod
    def _town_need_phase(need: TownNeed) -> int:
        """Order mandatory town work before convenience and speculative buys."""
        if need.category in {
            "black-market",
            "ammo",
            "throwing-torches",
            "launcher-enchant",
        }:
            return 2
        return 0

    def _town_need_effective_phase(
        self, snapshot: Snapshot, need: TownNeed
    ) -> int:
        """Put concretely affordable curse service ahead of ordinary errands."""
        if (
            need.category == "remove-curse"
            and self._normal_remove_curse_actionable_this_visit(snapshot)
        ):
            return -1
        if need.category == "identification-source":
            return -1
        if (
            need.category == "oil"
            and self._identification_need is not None
            and self._owns_lantern(snapshot)
        ):
            return -2
        return self._town_need_phase(need)

    def _order_town_needs(
        self,
        snapshot: Snapshot,
        needs: list[TownNeed],
        stores: list[int],
        start: Position,
    ) -> list[int]:
        """Order stores by need phase, then minimize travel inside each phase."""
        needed_store_types = {need.store_type for need in needs}
        unique_stores = [
            store_type
            for store_type in dict.fromkeys(stores)
            if store_type in needed_store_types
        ]
        phase_by_store = {
            store_type: min(
                self._town_need_effective_phase(snapshot, need)
                for need in needs
                if need.store_type == store_type
            )
            for store_type in unique_stores
        }
        ordered: list[int] = []
        current = start
        for phase in sorted(set(phase_by_store.values())):
            phase_order = self._order_town_stops(
                snapshot,
                [
                    store_type
                    for store_type in unique_stores
                    if phase_by_store[store_type] == phase
                ],
                current,
            )
            ordered.extend(phase_order)
            if phase_order and self._town_map_active(snapshot):
                current = self._town_map.store_position(phase_order[-1]) or current
        return ordered

    def _build_town_errand_plan(
        self, snapshot: Snapshot, needs: list[TownNeed]
    ) -> TownErrandPlan | None:
        leading_home = any(
            need.store_type == STORE_HOME and need.ordering_class != "post-alchemist-home"
            for need in needs
        )
        post_home = any(need.ordering_class == "post-alchemist-home" for need in needs)
        stores = {need.store_type for need in needs if need.store_type != STORE_HOME}
        stops: list[int] = [STORE_HOME] if leading_home else []
        start = self._town_map.store_position(STORE_HOME) if leading_home and self._town_map_active(snapshot) else snapshot.player.position
        ordered = self._order_town_needs(snapshot, needs, list(stores), start)
        if post_home and STORE_ALCHEMIST in ordered:
            alchemist_index = ordered.index(STORE_ALCHEMIST)
            ordered.insert(alchemist_index + 1, STORE_HOME)
        elif post_home:
            ordered.append(STORE_HOME)
        stops.extend(ordered)
        return (
            TownErrandPlan(
                stops,
                need_categories={
                    store_type: tuple(
                        need.category
                        for need in needs
                        if need.store_type == store_type
                    )
                    for store_type in dict.fromkeys(stops)
                },
            )
            if stops
            else None
        )

    @staticmethod
    def _town_workflow_progress_state(snapshot: Snapshot) -> tuple[object, ...]:
        """Project state changes that demonstrate town-workflow progress."""
        def item_state(item: object) -> tuple[object, ...]:
            return tuple(
                getattr(item, field, None)
                for field in (
                    "slot", "tval", "sval", "name", "count", "charges",
                    "inscription", "known", "fully_known", "is_equipment",
                )
            )

        store = snapshot.store
        store_state = None if store is None else (
            store.store_type,
            getattr(store, "stock_num", None),
            getattr(store, "page_top", None),
            tuple(item_state(item) for item in store.items),
        )
        return (
            store_state,
            tuple(item_state(item) for item in snapshot.inventory),
            tuple(item_state(item) for item in snapshot.equipment),
            snapshot.player.gold,
        )

    def _report_town_stop_pass(
        self,
        snapshot: Snapshot,
        store_type: int,
        *,
        goal_satisfied: bool,
        operation_completed: bool = False,
    ) -> None:
        """Report one handler pass to the plan that owns this town objective."""
        self._town_visit_ledger.store_visits[store_type] += 1
        store_needs = [
            need
            for need in self._enumerate_town_needs(snapshot)
            if need.store_type == store_type
        ]
        plan = self._town_errand_plan
        owned_categories = (
            plan.need_categories.get(store_type, ())
            if plan is not None
            else tuple(need.category for need in store_needs)
        )
        if (
            store_type == STORE_HOME
            and self._home_knowledge_current
            and self._home_scan_item_count == 0
            and not self._calibration_active()
            and self._equipment_transaction_session is None
        ):
            # Reconcile a plan built before the knowledge response.  Categories
            # whose only fulfillment was an empty-Home withdrawal no longer own
            # this stop; live deposit categories remain visible in store_needs.
            owned_categories = tuple(need.category for need in store_needs)
            if plan is not None and STORE_HOME not in plan.blocked_this_visit:
                plan.blocked_this_visit.append(STORE_HOME)
            self._town_blocked_reason = "home-known-empty-withdrawal"
        if not owned_categories:
            owned_categories = tuple(need.category for need in store_needs)
        registry_satisfied = True
        if owned_categories:
            previous_snapshot = getattr(
                self, "_town_need_evaluation_snapshot", None
            )
            previous_candidates = getattr(
                self, "_town_need_evaluation_candidates", None
            )
            self._town_need_evaluation_snapshot = snapshot
            self._town_need_evaluation_candidates = self._town_need_candidates(
                snapshot
            )
            try:
                registry_satisfied = all(
                    spec.satisfied(snapshot)
                    for spec in self._town_need_registry()
                    if spec.category in set(owned_categories)
                    and (
                        not spec.produces(snapshot)
                        or spec.resolve_store_type(snapshot) == store_type
                    )
                )
            finally:
                self._town_need_evaluation_snapshot = previous_snapshot
                self._town_need_evaluation_candidates = previous_candidates
        goal_satisfied = goal_satisfied and registry_satisfied
        for category in owned_categories:
            self._town_visit_ledger.need_attempts[category] = (
                self._town_visit_ledger.need_attempts.get(category, 0) + 1
            )
        if goal_satisfied:
            self._town_visit_ledger.satisfied_needs.update(
                (store_type, category) for category in owned_categories
            )
        if (
            plan is None
            or plan.index >= len(plan.stops)
            or plan.stops[plan.index] != store_type
        ):
            return
        if goal_satisfied:
            plan.completed_this_visit.append(store_type)
            plan.current_stop_passes = 0
            plan.index += 1
            return
        if store_type != STORE_HOME:
            if self._wanted_purchase_is_home_first_refused(snapshot, store_type):
                return
            if operation_completed:
                plan.current_stop_passes = 0
                return
            self._town_visit_ledger.pending_nonhome_effect_observation.add(
                store_type
            )
            plan.blocked_this_visit.append(store_type)
            plan.current_stop_passes = 0
            plan.index += 1
            self._set_town_store_attempted(store_type, snapshot.turn, "plan-stop-satisfied")
            return
        limit = self._town_store_visit_limit(store_type)
        # During calibration, one completed Home entry is the unit of work:
        # an atomic deposit/withdrawal still consumes an entry when its owner
        # remains live.  The same ledger counter therefore enforces the user's
        # visit ceiling without weakening the existing blocked-store terminal.
        plan.current_stop_passes += 1
        self._town_visit_ledger.unsatisfied_passes[store_type] += 1
        self._observe_withdrawal_unsatisfied_pass(snapshot)
        if (
            self._town_visit_ledger.unsatisfied_passes[store_type]
            < limit
        ):
            if operation_completed:
                plan.current_stop_passes = 0
            return
        plan.blocked_this_visit.append(store_type)
        self._town_visit_ledger.blocked_stores.add(store_type)
        # A ledger block's authority is the bound that installed it.  Passes
        # remain cumulative, but a later owner with a different applicable
        # bound is denied only when its own bound is exhausted.
        self._town_visit_ledger.blocked_store_limits[store_type] = limit
        self._release_blocked_store_latches(store_type)
        plan.current_stop_passes = 0
        plan.index += 1
        self._set_town_store_attempted(store_type, snapshot.turn, "plan-stop-advanced")
        if (
            store_type == STORE_HOME
            and self._equipment_transaction_session is not None
            and self._equipment_transaction_session.required_context == "home"
        ):
            self._abandon_blocked_equipment_transaction(snapshot)

    def _town_store_visit_limit(self, store_type: int) -> int:
        """Return the user-authorised visit-local terminal ceiling for Home.

        The authorised 300 Home visits cover outstanding equipment work,
        including applying an optimizer result after the optimizer succeeds.
        Mixed Home work within that interval is part of completing the work;
        Later Home work retains the ordinary hard terminal. Non-Home routing is
        state-based and must never ask for a visit limit.
        """
        if store_type != STORE_HOME:
            raise ValueError("non-Home stores have no visit-count limit")
        if store_type == STORE_HOME and self._outstanding_equipment_work():
            return CALIBRATION_HOME_VISIT_LIMIT
        return TOWN_STOP_PASS_LIMIT

    def _town_store_blocked_under_applicable_bound(self, store_type: int) -> bool:
        """Return whether the recorded block has authority over current work."""
        if store_type != STORE_HOME:
            return False
        if store_type not in self._town_visit_ledger.blocked_stores:
            return False
        authority = self._town_visit_ledger.blocked_store_limits.get(store_type)
        return authority is None or authority == self._town_store_visit_limit(store_type)

    @staticmethod
    def _cross_town_item_categories(item: StoreItem) -> tuple[str, ...]:
        """Return expedition shortage categories concretely supplied by a ware."""
        categories: list[str] = []
        if item.is_recall_scroll:
            categories.append("recall")
        if item.is_teleport_scroll:
            categories.append("teleport")
        if item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            categories.append("cure-critical")
        if item.is_oil:
            categories.append("oil")
        if item.tval == TVAL_FOOD and item.sval >= FOOD_MIN_SVAL:
            categories.append("food")
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
            categories.append("identification-source:normal")
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
            categories.append("identification-source:full")
        if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY:
            categories.append("identify-staff")
        if item.tval == TVAL_LITE and item.sval in {
            SV_LITE_TORCH,
            SV_LITE_LANTERN,
        }:
            categories.append("light")
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_REMOVE_CURSE:
            categories.append("remove-curse")
        for stat, sval in RESTORE_POTION_SVAL_BY_STAT.items():
            if item.tval == TVAL_POTION and item.sval == sval:
                categories.append(f"stat-restore:{stat}")
        return tuple(categories)

    def _observe_cross_town_shelf(self, snapshot: Snapshot) -> None:
        """Record positive or negative shelf facts for live local suppliers."""
        store = snapshot.store
        if store is None:
            return
        offered: dict[str, list[tuple[int, int]]] = {}
        for item in store.items:
            for category in self._cross_town_item_categories(item):
                offered.setdefault(category, []).append(
                    (
                        item.price,
                        max(1, item.pval)
                        if category == "identify-staff"
                        else max(1, item.count),
                    )
                )
        observed_categories = set(offered)
        observed_categories.update(
            category
            for category in (
                "recall",
                "teleport",
                "cure-critical",
                "oil",
                "food",
                "identification-source:normal",
                "identification-source:full",
                "identify-staff",
                "light",
                "remove-curse",
                *(f"stat-restore:{stat}" for stat in RESTORE_POTION_SVAL_BY_STAT),
            )
            if store.store_type in self._cross_town_supplier_types(snapshot, category)
        )
        for category in observed_categories:
            self._town_visit_ledger.shelf_observations[
                (store.store_type, category)
            ] = tuple(offered.get(category, ()))

    def _cross_town_supplier_types(
        self, snapshot: Snapshot, category: str
    ) -> tuple[int, ...]:
        """Return every local store eligible to supply an expedition shortage."""
        supply_kind = {
            "recall": "recall",
            "teleport": "teleport",
            "cure-critical": "cure",
            "oil": "oil",
            "food": "food",
        }.get(category)
        if supply_kind is not None:
            ledger = self._supply_ledger(snapshot, self._planned_depth())
            return tuple(
                dict.fromkeys(
                    store_type
                    for status in ledger.values()
                    if status.kind == supply_kind
                    for store_type in status.stores
                )
            )
        if category.startswith("identification-source:"):
            return (STORE_ALCHEMIST,)
        if category == "identify-staff":
            return (STORE_MAGIC,)
        if category == "light":
            return (STORE_GENERAL,)
        if category == "remove-curse":
            return (STORE_TEMPLE,)
        if category.startswith("stat-restore:"):
            return (STORE_ALCHEMIST,)
        return ()

    def _cross_town_shortages(
        self, snapshot: Snapshot
    ) -> list[tuple[str, int]]:
        """Return shop-purchasable departure shortages, including latched ones."""
        shortages: list[tuple[str, int]] = []
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        category = {
            "recall": "recall",
            "teleport": "teleport",
            "cure": "cure-critical",
            "oil": "oil",
            "food": "food",
        }
        for status in ledger.values():
            missing = max(0, status.required_departure - status.count)
            if missing:
                shortages.append((category[status.kind], missing))
        if self._identification_need is not None:
            shortages.append(
                (
                    "identification-source:full"
                    if self._identification_need == "full"
                    else "identification-source:normal",
                    1,
                )
            )
        identify_charges = sum(
            item.charges
            for item in snapshot.inventory
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
        )
        if not self._identify_staff_ready(snapshot):
            shortages.append(
                ("identify-staff", max(1, STAFF_IDENTIFY_MIN_CHARGES - identify_charges))
            )
        if not self._light_ready(snapshot):
            shortages.append(("light", 1))
        if self._has_normal_remove_curse_target(snapshot) and self._find_remove_curse_scroll(snapshot) is None:
            shortages.append(("remove-curse", 1))
        for stat in snapshot.player.drained_stats:
            if self._carried_restore_potion(snapshot, stat) is None:
                shortages.append((f"stat-restore:{stat}", 1))
        return shortages

    def _cross_town_unobtainable_categories(
        self, snapshot: Snapshot, shortages: list[tuple[str, int]]
    ) -> tuple[str, ...]:
        """Require shelf evidence from every local supplier before escalation."""
        unobtainable: list[str] = []
        for category, _quantity in shortages:
            suppliers = set(self._cross_town_supplier_types(snapshot, category))
            evidence = [
                self._town_visit_ledger.shelf_observations.get(
                    (store_type, category)
                )
                for store_type in suppliers
            ]
            if suppliers and all(observation is not None for observation in evidence):
                # An empty tuple proves an observed stock-out. Non-empty
                # evidence proves local failure only when every matching ware
                # costs more than the player's current gold. In particular, an
                # affordable visible ware vetoes attempts, drift and latches.
                if all(
                    not observation
                    or all(price > snapshot.player.gold for price, _units in observation)
                    for observation in evidence
                ):
                    unobtainable.append(category)
        return tuple(dict.fromkeys(unobtainable))

    def _cross_town_candidate_order(self, snapshot: Snapshot) -> tuple[int, ...]:
        current = self._effective_town_id(snapshot)
        if snapshot.visited_town_ids is None:
            return ()
        return tuple(
            town_id
            for town_id in sorted(set(snapshot.visited_town_ids))
            if town_id != current and town_id in TOWN_TELEPORT_BUILDING_TYPES
        )

    def _town_terminal_transitions(self, snapshot: Snapshot) -> None:
        """Apply ordered state changes only after the plan walk is exhausted."""
        if self._town_restock_suppressed or snapshot.player.class_id < 0:
            return
        if self._fundraising_mode in {"prepare", "mine", "scavenge"} and snapshot.player.gold >= FUNDRAISING_GOLD_TARGET:
            self._fundraising_mode = None
            self._planned_mining_runs = None
            self._town_store_attempted.clear()
        if self._pending_disposal_item is not None:
            target = self._pending_disposal(snapshot)
            if target is None:
                self._clear_pending_disposal()
            else:
                store_type = self._dominated_disposal_store(target)
                if store_type is None or store_type in self._disposal_store_attempts:
                    self._destroy_pending = True
            return
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if not self._fundraising_food_ready(snapshot):
                store_type = STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL
                if store_type in self._town_store_attempted:
                    self._fundraising_mode = "scavenge"
                    self._scavenge_entry_gold = snapshot.player.gold
                    self._town_blocked_reason = None
                    return
            if self._planned_mining_runs is None:
                self._activate_partial_mining_plan(snapshot)
            detection_low = self._count_treasure_detection_scrolls(snapshot) < self._mining_detection_scroll_target(snapshot)
            if detection_low and STORE_HOME in self._town_store_attempted and STORE_ALCHEMIST in self._town_store_attempted:
                if self._activate_partial_mining_plan(snapshot) or self._try_normal_expedition_after_detection_stockout(snapshot):
                    return
                self._fundraising_mode = "scavenge"
                self._scavenge_entry_gold = snapshot.player.gold
            if self._fundraising_mode != "scavenge" and not self._has_digging_tool(snapshot) and STORE_HOME in self._town_store_attempted and STORE_GENERAL in self._town_store_attempted:
                self._fundraising_mode = "scavenge"
                self._scavenge_entry_gold = snapshot.player.gold
            if not self._fundraising_light_ready(snapshot) and STORE_GENERAL in self._town_store_attempted:
                self._retry_after_store_restock(snapshot, (STORE_GENERAL,))
            return
        if self._identification_need is not None:
            plan = self._town_errand_plan
            exhausted = set(plan.completed_this_visit) | set(plan.blocked_this_visit) if plan is not None else set()
            if STORE_ALCHEMIST not in self._town_store_attempted and STORE_ALCHEMIST not in exhausted:
                return
            source_obtainability = self._identification_source_obtainability(
                snapshot, full=self._identification_need == "full"
            )
            if source_obtainability != "unavailable":
                if self._find_identification_source(
                    snapshot,
                    full=self._identification_need == "full",
                    reliable_only=self._identification_requires_reliable_source(snapshot),
                ) is None:
                    self._retain_identification_source_owner()
                return
            if self._identification_need == "full":
                if self._conquest_target(snapshot) is not None:
                    self._defer_identification_for_conquest(snapshot)
                    if snapshot.player.gold < FUNDRAISING_START_GOLD:
                        self._start_fundraising(snapshot)
                    return
                if self._start_fundraising(snapshot):
                    return
                if STORE_ALCHEMIST in self._town_restock_rechecked:
                    self._defer_identification_for_conquest(snapshot)
                    self._town_restock_wait_until = None
                    self._town_restock_waiting_for = ()
                    return
                self._retry_after_store_restock(snapshot, (STORE_ALCHEMIST,))
                return
            pending = self._pending_inventory_item(snapshot)
            candidate = (
                self._item_signature(pending)
                if pending is not None
                else self._identification_candidate
            )
            candidate_origins = {
                owned.origin
                for owned in self._equipment_catalog.items
                if candidate is not None
                and self._item_signature(owned.item) == candidate
            }
            if candidate is not None and candidate_origins & {"pack", "equipped"}:
                self._town_unidentifiable_carried_sigs.add(candidate)
                self._equipment_optimization_signature = None
                self._equipment_optimization_preparation = None
            elif candidate is not None and "home" in candidate_origins:
                self._defer_home_item(candidate, "full-identify-expedition-capacity")
            elif self._device_identification_candidate is not None:
                self._deferred_device_items.add(self._device_identification_candidate)
            self._home_pending_item = None
            self._home_pending_slot = None
            self._identification_need = None
            self._identification_candidate = None
            self._device_identification_candidate = None
            self._home_candidate_waiting = True
            if self._home_available(snapshot) and not self._equipment_catalog.home_scan_complete:
                self._rearm_town_store_for_new_work(STORE_HOME)
            return
        recall = self._supply_ledger(snapshot, self._planned_depth())["recall"]
        recall_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
        if (not self._recall_ready(snapshot) or not self._recall_departure_ready(snapshot)) and all(store in self._town_store_attempted for store in recall_stores):
            if recall.count == 0:
                if (
                    self._town_restock_wait_until is None
                    and all(
                        store in self._town_restock_rechecked
                        for store in recall_stores
                    )
                ):
                    if not self._food_ready(snapshot):
                        food_store = (
                            STORE_MAGIC
                            if snapshot.player.food_type == FOOD_TYPE_MANA
                            else STORE_GENERAL
                        )
                        self._town_store_attempted.pop(food_store, None)
                    else:
                        self._town_blocked_reason = (
                            "restocked-recall-unavailable"
                        )
                    return
                self._retry_after_store_restock(snapshot, recall_stores)
                return
            if not self._recall_departure_ready(snapshot):
                if self._start_fundraising(snapshot):
                    return
                self._retry_after_store_restock(snapshot, recall_stores)
                return
        shortages = (
            (not self._food_ready(snapshot), STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL),
            (not self._light_ready(snapshot), STORE_GENERAL),
            (not self._teleport_ready(snapshot), STORE_ALCHEMIST),
            (not self._identify_staff_ready(snapshot), STORE_MAGIC),
        )
        for missing, store_type in shortages:
            if missing and store_type in self._town_store_attempted:
                if not self._start_fundraising(snapshot):
                    self._retry_after_store_restock(snapshot, (store_type,))
                return
        cure_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
        if not self._cure_critical_ready(snapshot) and all(store in self._town_store_attempted for store in cure_stores):
            if not self._start_fundraising(snapshot):
                self._retry_after_store_restock(snapshot, cure_stores)
            return
        if self._retry_processed_home_identification(snapshot) or self._start_identification_fundraising(snapshot):
            return
        self._town_restock_wait_until = None

    def _find_town_organization_surplus(
        self, snapshot: Snapshot
    ) -> InventoryItem | None:
        """Return surplus recognized by the existing sale/deposit authorities."""
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and not self._equipment_catalog.home_scan_complete
        ):
            # Complete the already-owned Home catalog/transaction pass before
            # organization changes pack letters or consumes its reserved slots.
            return None
        finder_candidates = (
            self._find_book_sale(snapshot),
            self._find_low_level_sale(snapshot),
            self._find_device_sale(snapshot),
            self._find_weapon_sale(snapshot),
            self._find_light_sale(snapshot),
        )
        candidates = [candidate for candidate in finder_candidates if candidate is not None]
        candidates.extend(
            item
            for item in snapshot.inventory
            if (
                self._home_deposit_candidate(item, snapshot)
                and not item.is_ammo
                and not item.is_torch
                # Ordinary convenience deposits keep their established
                # fundraising suppression. Organization owns this Home-only
                # case once every sale outlet has actually refused the item.
                and (
                    self._item_signature(item) in self._unsellable_items
                    or self._town_organization_sale_store(snapshot, item) is not None
                )
            )
            or self._is_surplus_digging_tool(snapshot, item)
        )
        return self._first_item(
            replace(snapshot, inventory=list(dict.fromkeys(candidates))),
            lambda item: not item.is_recall_scroll
            and self._entire_stack_is_surplus(snapshot, item)
            and not item.is_bounty
            and self._item_signature(item) not in self._home_rejected_deposits
            and (
                self._town_organization_sale_store(snapshot, item) is not None
                or self._town_organization_home_routable(snapshot, item)
            ),
        )

    def _town_organization_home_routable(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> bool:
        """Whether the existing Home deposit route can still take this surplus."""
        at_home = snapshot.store is not None and snapshot.store.store_type == STORE_HOME
        return (
            self._home_available(snapshot)
            and not self._home_deposit_abandoned
            and self._item_signature(item) not in self._home_rejected_deposits
            and (
                at_home
                or (
                    STORE_HOME not in self._town_store_attempted
                    and STORE_HOME not in self._town_visit_ledger.blocked_stores
                )
            )
        )

    def _town_organization_sale_store(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> int | None:
        if (
            self._item_signature(item) in self._unsellable_items
            or self._sale_retains_digging_tool(snapshot, item)
        ):
            return None
        for store_type in (
            STORE_WEAPON,
            STORE_ARMOURY,
            STORE_MAGIC,
            STORE_GENERAL,
            STORE_TEMPLE,
        ):
            if (
                self._store_accepts_sale(store_type, item)
                and self._town_need_supplier_reachable(
                    snapshot, TownNeed(store_type, "organization-sale", "")
                )
                and store_type not in self._store_sale_refused
                and store_type not in self._town_store_attempted
            ):
                return store_type
        return None

    def _town_travel_key(
        self, snapshot: Snapshot, goal: Position, macro: str, reason: str
    ) -> str | None:
        """Progress-based gate shared by every native-travel leg (stores, Home,
        the dungeon entrance). Travel is re-issued after an interruption (a
        monster, a nudge Escape) as long as it got CLOSER to the goal since the
        last issue; TOWN_TRAVEL_STALL_LIMIT issues with no progress latch a
        fallback to BFS walking for that goal (the game rejects travel over an
        unknown approach). The latch clears when the goal changes or the floor
        does. Near goals just walk — a travel round-trip costs more than the
        last couple of steps."""
        if goal not in snapshot.grids:
            # An undisclosed goal cannot support native travel.  The emitted
            # grid set is not, however, an authoritative projection of
            # point_target's live candidate vector; a disclosed goal may still
            # be rejected.  That failure is handled after the recovery nudge.
            return None
        position = snapshot.player.position
        distance = position.distance_to(goal)
        if distance < TOWN_TRAVEL_MIN_DISTANCE:
            return None
        if self._town_travel_fallback is not None:
            if self._town_travel_fallback == goal:
                return None
            self._town_travel_fallback = None
        state = self._town_travel_state
        if state is not None and state.goal == goal:
            if state.record(distance, snapshot.turn) == "fallback":
                self._town_travel_fallback = goal
                self._town_travel_state = None
                return None
        else:
            self._town_travel_state = TownTravelProgress(
                goal, distance, 0, 0, snapshot.turn
            )
        self.last_reason = reason
        return macro

    def _town_clear_traveler_key(
        self, snapshot: Snapshot, goal: Position | None = None
    ) -> str | None:
        """Compatibility hook for travel callers; town combat is global now."""
        return self._town_kill_mob_key(snapshot)

    def _town_kill_mob_key(self, snapshot: Snapshot) -> str | None:
        """Approach and kill every visible town monster except the player's pets.

        A direction key merely swaps places with a friendly in Hengband's
        ``exe_movement``.  The alter command instead reaches ``do_cmd_attack``
        through ``exe_alter``; a normal Warrior then receives the friendly-fire
        confirmation, answered inline by the trailing ``y``.
        """
        if not snapshot.in_town or snapshot.dungeon_level != 0:
            self._town_hunt_target = None
            return None
        player = snapshot.player
        targets = sorted(
            (monster for monster in snapshot.visible_monsters if not monster.pet),
            key=lambda monster: monster.distance,
        )
        for target in targets:
            self._town_hunt_target = target.position
            if player.position.distance_to(target.position) <= 1:
                if target.friendly:
                    self.last_reason = "town:kill-mob-friendly"
                    return "+" + self._direction_key(player.position, target.position) + "y"
                # Preserve the ordinary adjacent-hostile melee path and reason.
                return None
            step = self._nearest_goal_step(
                snapshot,
                lambda grid, target=target: grid.position.distance_to(target.position) <= 1,
            )
            if step is not None:
                self.last_reason = "town:kill-mob-approach"
                return self._step_toward(snapshot, step)
        if self._town_hunt_target is not None:
            if player.position.distance_to(self._town_hunt_target) <= 1:
                self._town_hunt_target = None
                return None
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.position.distance_to(
                    self._town_hunt_target
                ) <= 1,
            )
            if step is not None:
                self.last_reason = "town:kill-mob-approach"
                return self._step_toward(snapshot, step)
            self._town_hunt_target = None
        return None

    def _town_cancel_unsafe_recall_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or not snapshot.player.recalling:
            return None
        pending_destination = (
            self._pending_recall_dungeon_id
            if self._pending_recall_dungeon_id is not None
            else snapshot.recall_dungeon_id
        )
        active_destination = self._active_dungeon_target()
        destination_changed = (
            pending_destination != active_destination
            and self._recall_selection_key(snapshot, active_destination) is not None
            and self._recall_destination_safe(snapshot, active_destination)
        )
        blocks_teleport = any(
            self._blocks_teleport(item)
            for item in (*snapshot.inventory, *snapshot.equipment)
        )
        unready_blockers = self._recall_unready_blockers(
            snapshot, pending_destination
        )
        if (
            self._startup_town_recall
            and not destination_changed
            and not blocks_teleport
        ):
            # On attach, catalog/deposit/pack readiness is reconstructed over
            # subsequent observations and is not grounds to cancel a recall
            # that Hengband already owns.  Wrong destination and NO_TELE are
            # observable hard hazards, so they retain normal cancellation.
            return None
        if (
            self._emergency_recall_sanctioned
            and not destination_changed
            and not blocks_teleport
        ):
            return None
        if not destination_changed and not blocks_teleport and not unready_blockers:
            return None
        recall = self._find_recall_scroll(snapshot)
        if recall is None:
            return None
        if destination_changed or blocks_teleport:
            self._emergency_recall_sanctioned = False
        if destination_changed:
            self._pending_recall_dungeon_id = None
            self.last_reason = "town:cancel-wrong-recall-destination"
        else:
            self.last_reason = (
                "town:cancel-unsafe-recall"
                if blocks_teleport
                else "town:cancel-unready-recall"
            )
        return self._read_key(snapshot, recall)

    def _town_remove_curse_key(self, snapshot: Snapshot) -> str | None:
        """Read a Remove Curse scroll during town prep when a cursed item is worn,
        so it can be swapped/upgraded and its penalties lifted before diving."""
        if not snapshot.in_town or not self._has_cursed_equipment(snapshot):
            return None
        player = snapshot.player
        if player.blind or player.confused:
            return None
        cursed = next(
            (
                item for item in snapshot.equipment
                if item.is_cursed
                and not self._curse_unremovable(item)
            ),
            None,
        )
        star = self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval == SV_SCROLL_STAR_REMOVE_CURSE,
        )
        scroll = star or self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval == SV_SCROLL_REMOVE_CURSE,
        )
        if scroll is None:
            return None
        if cursed is None and scroll.sval != SV_SCROLL_STAR_REMOVE_CURSE:
            return None
        if cursed is None:
            cursed = next((item for item in snapshot.equipment if item.is_cursed), None)
        if cursed is None:
            return None
        self._remove_curse_watch = (
            self._item_signature(cursed),
            scroll.sval,
            sum(
                item.count for item in snapshot.inventory
                if item.is_scroll and item.aware and item.sval == scroll.sval
            ),
        )
        if scroll.sval == SV_SCROLL_STAR_REMOVE_CURSE:
            self._star_remove_curse_reserve_withdraw_pending = False
        self.last_reason = "town:remove-curse"
        return self._read_key(snapshot, scroll)

    def _town_random_teleport_suppression_key(
        self, snapshot: Snapshot
    ) -> str | None:
        """Suppress visible or still-hidden random teleport before equipping."""
        if not snapshot.in_town:
            return None

        # choose_key normally performs this synchronization before dispatch,
        # but keeping the action self-contained ensures its catalog predicate
        # is evaluated against this exact observation.
        self._refresh_carried_equipment_catalog(snapshot)
        preparation = self._prepare_equipment_optimization(snapshot)
        selected_ids = self._equipment_preparation_selected_ids(preparation)
        pending = tuple(
            owned
            for owned in self._equipment_catalog.items
            if self._needs_random_teleport_suppression(owned, selected_ids)
        )
        pack_owned = next(
            (owned for owned in pending if owned.origin == "pack"), None
        )
        equipped_owned = next(
            (owned for owned in pending if owned.origin == "equipped"), None
        )
        if pack_owned is not None or equipped_owned is not None:
            if snapshot.store is not None:
                self.last_reason = "equipment:leave-store-to-suppress-random-teleport"
                return LEAVE_STORE_KEY
            if pack_owned is not None:
                self.last_reason = "equipment:suppress-random-teleport"
                return INSCRIBE_KEY + pack_owned.item.slot + ".\r"
            slot_key = EQUIPMENT_SLOT_KEY.get(equipped_owned.equipped_slot)
            if slot_key is not None:
                self.last_reason = "equipment:suppress-equipped-random-teleport"
                return INSCRIBE_KEY + "/" + slot_key + ".\r"

        home_owned = next(
            (owned for owned in pending if owned.origin == "home"), None
        )
        if (
            home_owned is not None
            and snapshot.store is None
            and self._home_pending_item is None
            and self._item_signature(home_owned.item)
            not in self._deferred_home_items
            and self._town_pack_space_ready(snapshot)
        ):
            # The completed ~9 catalogue owns the identity and shelf ordinal.
            # Arm the ordinary derived-address withdrawal only outside; its
            # entrance path owns visit bounds, posting, page arithmetic, the
            # take command, and the exit.
            self._home_pending_item = self._item_signature(home_owned.item)
            self._home_random_teleport_withdrawal = self._home_pending_item
        return None

    def _town_cycle_detected(self) -> bool:
        """A full window of town decisions collapsing to a handful of distinct
        (reason, position) signatures with no progress is a repetition cycle,
        whatever subsystem drives it."""
        history = self._town_signature_history
        recent = list(history)[-TOWN_FAST_TRAVEL_WINDOW:]
        travel_rows = [row for row in recent if "travel" in row[0]]
        if (
            len(recent) == TOWN_FAST_TRAVEL_WINDOW
            and len(travel_rows) >= TOWN_FAST_TRAVEL_MIN_ROWS
            and len({(row[1], row[2]) for row in travel_rows})
            <= TOWN_FAST_TRAVEL_MAX_POSITIONS
        ):
            # A failed native-travel command is not repaired by clearing generic
            # shopping state.  Escalate this first observed fast cycle directly
            # to the existing visible town stop instead of waiting for a second
            # 48-decision cycle.
            self._town_cycle_breaks = max(
                self._town_cycle_breaks, TOWN_CYCLE_BREAK_LIMIT - 1
            )
            return True
        if len(history) < TOWN_CYCLE_WINDOW:
            return False
        return len(set(history)) <= TOWN_CYCLE_MAX_DISTINCT

    def _break_town_cycle(self, snapshot: Snapshot) -> None:
        """Cut every fuel line the known cycle shapes run on. Latching all the
        stores sends the errand router to its no-store path (the departure
        gates take over); the session/disposal/travel resets kill the other
        observed drivers. The latches expire on the normal STORE_RETRY_TURNS
        schedule, so a later town visit shops normally again."""
        # This repair starts a fresh observation epoch.  In particular, a
        # wander-limit detection may leave the generic no-progress count at 60;
        # carrying that debt forward makes 36 legitimate entrance-walk steps
        # look like a second cycle and stops the bot before it can depart.
        self._town_signature_history.clear()
        self._town_no_progress_count = 0
        self._town_wander_streak = 0
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        shortages = (
            self._ledger_departure_shortages(ledger)
            if self._last_return_trigger in {
                "recall-low",
                "teleport-low",
                "cure-low",
                "next-depth-kit",
                "escape-kit-empty",
            }
            else []
        )
        preserved_stores = {
            store
            for status in shortages
            if status.obtainable
            for store in status.stores
        }
        attempted_stores = dict(self._town_store_attempted)
        self._town_store_attempted.clear()
        try:
            departure_needs = [
                need
                for need in self._departure_blocking_town_needs(snapshot)
                if self._town_need_supplier_reachable(snapshot, need)
            ]
        finally:
            self._town_store_attempted.update(attempted_stores)
        preserved_stores.update(need.store_type for need in departure_needs)
        for store_type in range(len(TOWN_TRAVEL_STORE_SYMBOLS) + 1):
            if store_type in preserved_stores:
                self._town_store_attempted.pop(store_type, None)
            else:
                self._set_town_store_attempted(
                    store_type,
                    snapshot.turn,
                    "repetition-preserve-exhausted-store",
                    if_absent=True,
                )
        self._abandon_blocked_equipment_transaction(snapshot)
        self._clear_pending_disposal()
        self._close_store_visit("abandoned-with-restore")
        self._shopping_stuck = True
        self._town_travel_state = None
        self._town_travel_fallback = None
        # A cycle can begin only after the ordinary departure route has already
        # spent/expired its navigation-ledger budget.  The repair is a fresh
        # observation epoch, so re-arm the entrance as well as clearing the
        # store/native-travel state; otherwise the forced repetition owner has
        # no selectable goal and can only WAIT forever.
        self._nav_ledger.reset()
        self._town_restock_wait_until = None
        # The ordinary fundraising router changes prepare -> scavenge after
        # the required shops are exhausted.  Suppression returns before that
        # router can run, so preserve the same transition here; otherwise the
        # departure gates keep hiding the entrance and the bot merely wanders.
        if (
            self._fundraising_mode is None
            and snapshot.player.gold < FUNDRAISING_START_GOLD
        ):
            self._fundraising_mode = "scavenge"
            self._scavenge_entry_gold = snapshot.player.gold
        elif self._fundraising_mode == "prepare" or (
            self._fundraising_mode == "mine"
            and not self._fundraising_departure_ready(snapshot)
        ):
            self._fundraising_mode = "scavenge"
            self._scavenge_entry_gold = snapshot.player.gold
        # After a cycle the goal is DEPARTURE, not errands: without this, a
        # restock-retry path starts a fresh in-town wait, un-latches the very
        # stores above when it expires, and the cycle resumes.
        self._town_restock_suppressed = not preserved_stores
        self._town_suppression_claim_stores.update(preserved_stores)
        self._town_errand_plan = (
            self._build_town_errand_plan(snapshot, departure_needs)
            if departure_needs
            else (
                TownErrandPlan(sorted(preserved_stores))
                if preserved_stores
                else None
            )
        )

    def _town_blocked_store_context(self, snapshot: Snapshot) -> bool:
        here = snapshot.grid_at(snapshot.player.position)
        return snapshot.store is not None or (
            self._last_snapshot_was_store
            and here is not None
            and here.is_store
        )

    def _town_blocked_entrance_has_composable_operation(
        self, snapshot: Snapshot
    ) -> bool:
        """Yield a blocked entrance when its owner can compose a Home take."""
        if snapshot.store is not None or not self._home_knowledge_current:
            return False
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.store_number != STORE_HOME or not self._home_page_size:
            return False
        if (
            self._shopping_approach_store_type != STORE_HOME
            or self._home_atomic_withdraw_pending is not None
        ):
            return False
        addressable = tuple(
            item
            for index, item in enumerate(self._home_knowledge_items)
            if index < self._home_knowledge_valid_before
        )
        session = self._equipment_transaction_session
        action = session.current_action if session is not None else None
        if action is not None and action.kind == "withdraw":
            return any(
                item.is_equipment
                and equipment_identity(item) == action.item_identity
                for item in addressable
            )
        requested = {
            *self._calibration_restore_signatures,
            *self._home_pending_batch,
            *(
                (self._home_pending_item,)
                if self._home_pending_item is not None
                else ()
            ),
            *(
                (self._home_errand.request.signature,)
                if self._home_errand.active and self._home_errand.request is not None
                else ()
            ),
        }
        return any(self._item_signature(item) in requested for item in addressable)

    def _town_blocked_key(self, snapshot: Snapshot) -> str | None:
        """Leave an open/interleaved store UI before handling a town block.

        A repeated town cycle is recoverable once its shopping fuel lines have
        been cut: own the route to the dungeon entrance until the character is
        out of town.  Treating that case like an unrecoverable block used to
        issue WAIT forever outside a store, so the CLI could only stop the bot.
        Other blocked reasons remain visible terminal waits.
        """
        self.last_reason = f"town:blocked:{self._town_blocked_reason}"
        if self._town_blocked_reason == "repetition" and snapshot.store is not None:
            store = snapshot.store
            if self._town_blocked_purchase_is_composable(snapshot):
                # Keep the ordinary two-visit one-shot contract: this page only
                # records the shelf, then the outside entrance page binds the
                # exact purchase before re-entry releases its command tail.
                self._shop_observation = (store, self._decision_sequence)
                self.last_reason = "shop:observe-and-leave"
            else:
                self._close_store_visit("repetition-block-abandoned")
            return LEAVE_STORE_KEY
        if (
            self._town_blocked_reason is not None
            and self._town_blocked_reason.startswith("equipment-transaction:")
        ):
            blocked_reason = self._town_blocked_reason
            blocked_owner = f"town:blocked:{blocked_reason}"
            if not self._owner_may_select(snapshot, blocked_owner):
                self._town_blocked_reason = None
                return None
            unobserved_withdrawal = blocked_reason.startswith(
                "equipment-transaction:withdraw-item-unobserved:"
            )
            self._abandon_blocked_equipment_transaction(snapshot)
            # Abandoning releases the failed executable plan, but this caller
            # is the terminal owner.  Preserve the cause so the next outside
            # snapshot cannot rebuild the same Home need and enter unowned.
            if unobserved_withdrawal:
                self._town_blocked_reason = blocked_reason
            if snapshot.store is not None:
                self._post_owner_expectation(
                    snapshot, blocked_owner, "store_type", "inventory", "equipment"
                )
                return LEAVE_STORE_KEY
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.is_store:
                neighbors = self._walkable_neighbors(
                    snapshot, snapshot.player.position
                )
                if neighbors:
                    self._post_owner_expectation(
                        snapshot, blocked_owner, "position", "inventory", "equipment"
                    )
                    return self._step_toward(snapshot, neighbors[0])
                self._post_owner_expectation(
                    snapshot, blocked_owner, "position", "inventory", "equipment"
                )
                return "2"
            self._post_owner_expectation(
                snapshot, blocked_owner, "inventory", "equipment", "gold"
            )
            return WAIT_KEY if unobserved_withdrawal else None
        if snapshot.store is None:
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.is_store:
                neighbors = self._walkable_neighbors(
                    snapshot, snapshot.player.position
                )
                if neighbors:
                    return self._step_toward(snapshot, neighbors[0])
                # Interleaved main-loop snapshots can omit surrounding town
                # cells immediately after leaving a store. Still step off the
                # door instead of sending another ESC into the town command loop.
                return "2"
        if self._town_blocked_store_context(snapshot):
            return LEAVE_STORE_KEY
        if self._town_blocked_reason == "repetition":
            clear_traveler = self._town_kill_mob_key(snapshot)
            if clear_traveler is not None:
                return clear_traveler
            required_store = self._next_required_store_type(snapshot)
            if (
                self._store_visit is not None
                and not self._store_visit.operation_posted
                and required_store is not None
                and self._store_visit.store_type != required_store
            ):
                # A captured outside snapshot can resume after the store-page
                # eject above.  Release the abandoned owner before asking the
                # approach router to bind the store that is required now.
                self._close_store_visit("repetition-block-abandoned")
            shopping_step = self._shopping_approach_step(snapshot)
            if shopping_step is not None:
                self.last_reason = "town:repetition-required-shopping"
                return self._shopping_approach_key(
                    snapshot,
                    shopping_step,
                    "town:repetition-required-shopping",
                )
            here = snapshot.grid_at(snapshot.player.position)
            if (
                here is not None
                and self._is_active_dungeon_entrance(here)
                and not self._descent_is_blocked(snapshot)
                and self._dungeon_entry_allowed(
                    snapshot,
                    via_recall=False,
                    destination_depth=self._dungeon_entry_depth(
                        snapshot, self._active_dungeon_target(), via_recall=False
                    ),
                )
            ):
                self.last_reason = "town:repetition-depart:enter"
                return ENTER_DUNGEON_MACRO
            step = self._descent_step(snapshot)
            if step is not None:
                travel = self._entrance_travel_key(
                    snapshot, self._descent_target_goal
                )
                # Every departure rung must yield when it cannot advance.
                # In particular, a rejected native-travel command or a
                # degenerate BFS step must not hide the recall rung below.
                if travel not in (None, WAIT_KEY):
                    return travel
                walk = self._step_toward(snapshot, step)
                if walk != WAIT_KEY:
                    self.last_reason = "town:repetition-depart"
                    return walk
            if not snapshot.player.recalling:
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    selection = ""
                    if snapshot.in_town:
                        recall_dest, recall_dungeon_id = (
                            self._town_recall_destination(snapshot)
                        )
                        if recall_dest is None:
                            return WAIT_KEY
                        if not self._dungeon_entry_allowed(
                            snapshot,
                            via_recall=True,
                            destination_depth=self._dungeon_entry_depth(
                                snapshot, recall_dungeon_id, via_recall=True
                            ),
                        ):
                            return WAIT_KEY
                        selection = self._recall_selection_key(
                            snapshot, recall_dungeon_id
                        )
                        if selection is None:
                            return WAIT_KEY
                    self.last_reason = "town:repetition-depart:recall"
                    self._emergency_recall_sanctioned = True
                    return self._read_key(snapshot, recall, selection)
        return WAIT_KEY

    def _town_recall_destination(
        self, snapshot: Snapshot
    ) -> tuple[str | None, int]:
        """Choose the voluntary town-recall destination without issuing it."""
        recall_dest = None
        recall_dungeon_id = self._target_dungeon_id
        if (
            self._target_dungeon_id == DUNGEON_ANGBAND
            and snapshot.angband_recall_unlocked
            and self._recall_destination_safe(snapshot, DUNGEON_ANGBAND)
        ):
            recall_dest = "angband"
        elif (
            self._target_dungeon_id not in (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE)
            and self._target_dungeon_id in snapshot.entered_dungeon_ids
            and self._recall_destination_safe(snapshot, self._target_dungeon_id)
        ):
            recall_dest = "alt-dungeon"
        elif (
            self._target_dungeon_id == DUNGEON_YEEK_CAVE
            and self._fundraising_mode not in {"mine", "scavenge"}
            and not self._taken_kill_quest_requires_walk_in(snapshot)
            and self._deepest_level >= RECALL_MIN_DEPTH
            and self._recall_destination_safe(snapshot, DUNGEON_YEEK_CAVE)
        ):
            recall_dest = "yeek-cave"
        return recall_dest, recall_dungeon_id

    def _town_special_key(self, snapshot: Snapshot) -> str | None:
        full_identify_trip = self._morivant_full_identify_key(snapshot)
        if full_identify_trip is not None:
            return full_identify_trip
        if not snapshot.in_town or snapshot.player.class_id < 0:
            return None
        if self._town_cycle_pending:
            # _observe caught a repetition cycle (see _town_cycle_detected).
            # First offense: cut every fuel line the known cycle shapes run on
            # (errand router latches, transaction session, disposal target,
            # travel state) and carry on. A second cycle in the same town
            # visit means the repair did not hold — stop visibly instead of
            # burning supplies for hours.
            self._town_cycle_pending = False
            self._town_cycle_breaks += 1
            if self._town_cycle_breaks >= TOWN_CYCLE_BREAK_LIMIT:
                # Re-apply the repair before the forced departure.  A second
                # detector can be raised by a different errand subsystem after
                # the first pass, so this closes any state it reopened.
                self._break_town_cycle(snapshot)
                self._town_blocked_reason = "repetition"
                return self._town_blocked_key(snapshot)
            self._break_town_cycle(snapshot)
            if (
                self._fundraising_mode in {"mine", "scavenge"}
                and not self._fundraising_light_ready(snapshot)
            ):
                self._town_blocked_reason = "departure-no-light"
                return self._town_blocked_key(snapshot)
            # Once ordinary town work has been suppressed there is no useful
            # router left to own the walk to an entrance. Leaving this unset
            # handed the next turn back to generic navigation, where a large
            # town could accumulate another full wander window before the
            # second detector finally forced departure. Preserve the visible
            # one-turn cycle-break marker, then let _town_blocked_key own every
            # following turn until the character leaves town. Fundraising is
            # deliberately excluded: its scavenge/mine mode owns a different
            # shallow-dungeon departure route.
            if self._town_restock_suppressed and self._fundraising_mode is None:
                self._town_blocked_reason = "repetition"
            self.last_reason = "town:cycle-break"
            return WAIT_KEY
        if self._town_blocked_reason is not None:
            return self._town_blocked_key(snapshot)

        if (
            self._fundraising_mode in {"prepare", "scavenge"}
            and self._fundraising_supplies_ready(snapshot)
        ):
            # Store-route suppression prevents another futile shopping cycle;
            # it must not freeze the activity mode after the complete mining
            # kit is already in the pack. Promotion itself neither clears nor
            # revisits a store latch, so it is safe while suppression remains.
            self._fundraising_mode = "mine"
            self._mining_runs_completed = 0
            # Promotion changes the dungeon activity, not the stock that was
            # just observed in town.  Clearing every visit latch here made the
            # current errand plan revisit the same empty/unaffordable shop
            # immediately, producing Alchemist -> entrance -> Alchemist trips.
            # Genuine stock turnover is re-armed by _retry_after_store_restock.

        if (
            not self._town_restock_suppressed
            and self._town_restock_wait_until is not None
            and snapshot.turn < self._town_restock_wait_until
        ):
            self.last_reason = self._restock_wait_reason(snapshot)
            return RESTOCK_WAIT_MACRO

        if (
            self._fundraising_mode == "mine"
            and self._mining_runs_completed >= self._effective_mining_run_target()
        ):
            self._fundraising_mode = None
            self._mining_runs_completed = 0
            self._planned_mining_runs = None
            self._town_store_attempted.clear()
            self._town_restock_suppressed = False
            self._town_errand_plan = None
            return None

        # A resumed bot does not retain the in-memory partial batch selected
        # after shop stock ran out. Reconstruct it from supplies already carried
        # before applying the departure gate.
        if self._fundraising_mode == "mine" and self._planned_mining_runs is None:
            self._activate_partial_mining_plan(snapshot)
        player = snapshot.player
        if (
            player.hp < player.max_hp
            or player.mp < player.max_mp
            or not self._temporary_status_clear(snapshot)
        ) and player.food_state in {"normal", "full", "gorged"}:
            self.last_reason = "town:recover"
            return REST_MACRO

        if self._fundraising_mode in {"mine", "scavenge"}:
            if not self._fundraising_departure_ready(snapshot):
                # Do not let this early fundraising wait starve the ordinary
                # town pack-pressure pipeline below.  Descent deliberately
                # rejects a completely full pack, so waiting here can only
                # become a cycle; falling through lets identification, safe
                # destruction, and the terminal overflow fallback free a slot.
                if len(snapshot.inventory) >= PACK_CAPACITY:
                    return None
                plan = self._town_errand_plan
                if plan is not None and plan.index >= len(plan.stops):
                    # Every planned shop owner has already run, so another wait
                    # cannot improve the departure kit.  Apply the same bounded
                    # fallback as the generic town-cycle detector immediately;
                    # waiting for its 30-decision window produced a visible
                    # departure-blocked loop outside the final shop.
                    self._break_town_cycle(snapshot)
                    self.last_reason = "fundraise:fallback-exhausted-plan"
                    return None
                # Once every store route has been abandoned, preferred food is
                # optional for a shallow scavenge dive.  A working light was
                # checked when the cycle was broken and remains a hard gate.
                if (
                    self._town_restock_suppressed
                    and self._fundraising_mode == "scavenge"
                    and self._fundraising_light_ready(snapshot)
                ):
                    return None
                here = snapshot.grid_at(snapshot.player.position)
                if here is not None and here.is_store:
                    neighbors = self._walkable_neighbors(
                        snapshot, snapshot.player.position
                    )
                    if neighbors:
                        self.last_reason = "fundraise:departure-blocked-step-off"
                        return self._step_toward(snapshot, neighbors[0])
                self.last_reason = "fundraise:departure-blocked"
                self.prompt_owner_handoff = "town:blocked:departure-no-light"
                return WAIT_KEY
            return None

        rumor_needed = (
            self._rumor_unlock_pending and not snapshot.angband_recall_unlocked
        ) or self._town_travel_rumor_pending is not None
        if rumor_needed:
            # Revealing a destination is a town prerequisite, not an expedition.
            # Do not require a complete dive loadout before reading the rumors
            # needed to make the inn's travel destination selectable.
            if (
                self._town_travel_rumor_pending is None
                and not self._town_departure_ready(snapshot)
            ):
                self.last_reason = "town:rumor-wait-supplies"
                return WAIT_KEY
            if player.gold < RUMOR_GOLD_RESERVE + RUMOR_COST:
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                self.last_reason = "town:rumor-needs-funds"
                return WAIT_KEY
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.building_type == INN_BUILDING_TYPE
            )
            if step is None and self._town_map_active(snapshot):
                # At night / far off, the inn is unlit and absent from the emitted
                # grids; route to its remembered position from the static town map
                # (unless we are already standing on it, where a path-to-self is
                # empty). Mirrors the store / Hunter's Office approach.
                inn_pos = self._town_map.building_position(INN_BUILDING_TYPE)
                if inn_pos is not None and player.position != inn_pos:
                    step = self._town_map_goal_step(snapshot, inn_pos)
            if step is not None:
                self.last_reason = "town:rumor"
                # _nearest_goal_step returns only the FIRST step of the path. The
                # rumor keys must ride along ONLY when that step lands on the inn
                # (walking onto it opens the building menu, which then consumes
                # them); while still approaching, send the bare move — otherwise
                # 'u'+exit leak into the town command loop and the inn is never
                # entered, so Angband recall never unlocks.
                target = snapshot.grids.get(step)
                if target is not None and target.building_type == INN_BUILDING_TYPE:
                    # Read a whole batch of rumors this one visit (menu stays open
                    # between reads), capped by what we can afford above the
                    # reserve, then leave. The next snapshot shows whether the
                    # Angband-unlock rumor came up (angband_recall_unlocked).
                    reads = min(
                        RUMOR_READS_PER_VISIT,
                        max(1, (player.gold - RUMOR_GOLD_RESERVE) // RUMOR_COST),
                    )
                    self.last_reason = "town:rumor-batch"
                    return self._step_toward(
                        snapshot,
                        step,
                        tail=RUMOR_READ_KEY * reads + LEAVE_STORE_KEY,
                    )
                return self._step_toward(snapshot, step)
            # Inn unreachable, or we are already standing on it. Do NOT latch a
            # sticky WAIT block — that froze the bot on the inn tile forever
            # (town "5-loop"). Fall through to the recall logic below so the run
            # continues (dive again) instead of waiting on an unreachable rumor.

        # Return to the dungeon by Word of Recall once we have depth to justify it:
        # to Angband once its recall is unlocked (Yeek Cave conquered), otherwise
        # back into a deep Yeek Cave run (recall lands at the deepest level, far
        # faster than re-walking from the entrance). Fundraising deliberately mines
        # level 1, so it keeps walking to the entrance instead.
        recall_dest, recall_dungeon_id = self._town_recall_destination(snapshot)
        # A completed scan with no pending Home or identification owner cannot
        # legitimately defer departure.  This also repairs old visit state
        # created before disposal completion released the latch at its source.
        self._release_stale_home_candidate_waiting(snapshot)
        # A consumed/moved item can leave the old in-memory pointer behind even
        # though there is no longer an errand capable of clearing it.  Do this
        # immediately before the departure gate so an inert latch cannot turn a
        # ready recall into generic town wandering.
        if (
            self._home_pending_item is not None
            and self._home_atomic_withdraw_pending is None
            and self._pending_inventory_item(snapshot) is None
            and not self._home_candidate_waiting
        ):
            self._home_pending_item = None
            self._home_pending_slot = None
            self._identification_candidate = None
            self._identification_need = None
        if (
            self._identification_need is not None
            and self._home_pending_item is None
            and not self._home_pending_batch
            and not self._home_batch_review_items
            and not self._home_candidate_waiting
        ):
            self._identification_need = None
            self._identification_candidate = None
        # Free pack space is a hard departure requirement. A full Home or an
        # unreachable shop must not become permission to Recall over-packed.
        # Combat readiness remains an independent hard gate as well.
        departure_conjuncts = self._recall_town_departure_conjuncts(snapshot)
        departure_ok = all(departure_conjuncts.values())
        if recall_dest is not None and not departure_ok:
            self._departure_block = self._departure_block_state(
                snapshot, departure_conjuncts
            )
        else:
            self._departure_block = {}
        self._departure_block_sequence = self._decision_sequence
        if (
            recall_dest is not None
            and not snapshot.player.recalling
            and self._find_recall_scroll(snapshot) is None
        ):
            # A zero-scroll visit cannot execute this recall objective.
            # Suppliers may both be latched after genuine stock failure;
            # wait for turnover instead of falling through to dungeon-style
            # town exploration while carrying an unreachable objective.
            return self._recall_restock_key(snapshot)
        if recall_dest is not None and departure_ok:
            self._cross_town_shopping = None
            recall_count = sum(
                item.count for item in snapshot.inventory if item.is_recall_scroll
            )
            issue_watch = self._town_recall_issue_watch
            if not snapshot.player.recalling and issue_watch is not None:
                watched_destination, issue_turn, pre_read_count = issue_watch
                if watched_destination != recall_dungeon_id:
                    self._town_recall_issue_watch = None
                    self._pending_recall_dungeon_id = None
                elif recall_count < pre_read_count or snapshot.turn <= issue_turn:
                    # A reduced stack proves that the read succeeded even when a
                    # stale/interleaved snapshot temporarily reports recalling
                    # as false.  An unchanged snapshot at the command turn is
                    # likewise not evidence of rejection.  Wait for the engine's
                    # next authoritative state instead of spending another scroll.
                    self.last_reason = "town:await-recall-confirmation"
                    return WAIT_KEY
                else:
                    # The turn advanced without consuming the scroll: the read
                    # was genuinely rejected, so allow one ordinary retry.
                    self._town_recall_issue_watch = None
                    self._pending_recall_dungeon_id = None
            if snapshot.player.recalling:
                here = snapshot.grid_at(snapshot.player.position)
                if here is not None and here.is_store:
                    neighbors = self._walkable_neighbors(
                        snapshot, snapshot.player.position
                    )
                    if neighbors:
                        self.last_reason = "town:wait-recall-step-off"
                        return self._step_toward(snapshot, neighbors[0])
                self.last_reason = "town:wait-recall"
                return WAIT_KEY
            if (
                not self._char_dump_done_this_visit
                and not snapshot.player.blind
                and not snapshot.player.confused
            ):
                # Snapshot the full character sheet just before committing to the
                # dive, so the human can review stats/resistances/equipment per dive.
                self._char_dump_done_this_visit = True
                self.last_reason = "town:character-dump"
                return CHARACTER_DUMP_MACRO
            if not snapshot.player.blind and not snapshot.player.confused:
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    destination_depth = self._dungeon_entry_depth(
                        snapshot, recall_dungeon_id, via_recall=True
                    )
                    if not self._dungeon_entry_allowed(
                        snapshot,
                        via_recall=True,
                        destination_depth=destination_depth,
                    ):
                        return WAIT_KEY
                    selection = self._recall_selection_key(
                        snapshot, recall_dungeon_id
                    )
                    if selection is None:
                        return None
                    self._pending_recall_dungeon_id = recall_dungeon_id
                    self._town_recall_issue_watch = (
                        recall_dungeon_id,
                        snapshot.turn,
                        recall_count,
                    )
                    self.last_reason = f"town:recall-to-{recall_dest}"
                    return self._read_key(snapshot, recall, selection)

        if recall_dest is not None and not departure_ok:
            blocker = self._terminal_equipment_blocker(snapshot)
            if blocker is not None:
                self._town_blocked_reason = blocker
                return self._town_blocked_key(snapshot)
            # The errand registry and its bounded store passes have no remaining
            # owner, yet some departure prerequisite is still false.  Expose
            # that otherwise-unclassified gate through the existing visible
            # terminal instead of handing town back to generic stuck:wander.
            if not self._town_claims_active(snapshot):
                expedition = self._cross_town_shopping_key(snapshot)
                if expedition is not None:
                    return expedition
                supplier = self._departure_supplier_counterfactual(snapshot)
                if supplier is not None:
                    self._town_blocked_reason = None
                    return None
                self._town_blocked_reason = "departure-unsatisfiable"
                return self._town_blocked_key(snapshot)
        # Destination safety is a departure assertion, not an errand-router
        # precondition.  Run it only after every town owner above has had the
        # opportunity to act; otherwise an unsafe deep recall can starve a live
        # supply plan before its next shop stop.  With no town claim left, make
        # the genuine no-destination state a visible terminal instead of an
        # unlatched WAIT that is reconsidered forever.
        if (
            self._target_dungeon_id == DUNGEON_ANGBAND
            and snapshot.angband_recall_unlocked
            and not self._recall_destination_safe(snapshot, DUNGEON_ANGBAND)
        ):
            if self._activate_safe_recall_fallback(snapshot) is not None:
                self.last_reason = "town:unsafe-recall-fallback"
                return WAIT_KEY
            if self._town_claims_active(snapshot):
                return None
            # Outstanding equipment work suppresses this departure terminal
            # only while its bounded Home route remains available. Once Home
            # is blocked or its ceiling is consumed, expose the exhausted work
            # as its own named terminal instead of falling through to a cycle.
            if self._equipment_work_home_route_available():
                return None
            if self._outstanding_equipment_work():
                self._town_blocked_reason = "equipment-work-home-route-exhausted"
                return self._town_blocked_key(snapshot)
            destination_depth = self._dungeon_entry_depth(
                snapshot, DUNGEON_ANGBAND, via_recall=True
            )
            if not self._destination_depth_allowed(snapshot, destination_depth):
                self._town_blocked_reason = self.last_reason
                return self._town_blocked_key(snapshot)
            self._town_blocked_reason = "no-safe-recall-destination"
            return self._town_blocked_key(snapshot)
        return None

    def _departure_block_state(
        self, snapshot: Snapshot, conjuncts: dict[str, bool] | None = None
    ) -> dict[str, object]:
        """Expose the exact enumeration consumed by the departure decision."""
        town_ledger = {
            "store_visits": dict(self._town_visit_ledger.store_visits),
            "need_attempts": dict(self._town_visit_ledger.need_attempts),
            "approach_fails": dict(self._town_visit_ledger.approach_fails),
            "unsatisfied_passes": dict(
                self._town_visit_ledger.unsatisfied_passes
            ),
            "blocked_stores": sorted(self._town_visit_ledger.blocked_stores),
            "passes_since_progress": self._town_visit_ledger.passes_since_progress,
            "drift_warnings": list(self._town_visit_ledger.drift_warnings),
        }
        town_claims = list(getattr(self, "_town_claim_categories", ()))
        values = dict(conjuncts or self._recall_town_departure_conjuncts(snapshot))
        selected_gate = "town_departure_ready"
        failures = [name for name, value in values.items() if not value]
        return {
            "failed": failures,
            "values": values,
            "gate": selected_gate,
            "ready": not failures,
            "diagnostics": {
                "free_pack_slots": PACK_CAPACITY - len(snapshot.inventory),
                "minimum_free_pack_slots": MIN_FREE_PACK_SLOTS,
            },
            "town_claims": town_claims,
            "town_ledger": town_ledger,
        }

    def _town_teleport_key(
        self, snapshot: Snapshot, destination_town_id: int
    ) -> str | None:
        current_town_id = self._effective_town_id(snapshot)
        required_gold = (
            TOWN_TELEPORT_COST
            if destination_town_id == 0
            else 2 * TOWN_TELEPORT_COST
        )
        if snapshot.player.gold < required_gold:
            self.town_teleport_refusal = {
                "current_town_id": current_town_id,
                "destination_town_id": destination_town_id,
                "gold": snapshot.player.gold,
                "required_gold": required_gold,
            }
            self.last_reason = "town:teleport-refused-fare"
            return None
        inn_type = TOWN_TELEPORT_BUILDING_TYPES.get(
            current_town_id
        )
        if inn_type is None:
            return None
        positions = frozenset(
            grid.position for grid in snapshot.grids.values()
            if grid.building_type == inn_type
        )
        if not positions and self._town_map_active(snapshot):
            position = self._town_map.building_position(inn_type)
            positions = frozenset({position}) if position is not None else frozenset()
        if snapshot.player.position in positions:
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self.last_reason = "town:teleport-step-off"
                return self._step_toward(snapshot, neighbors[0])
            return None
        step = min(
            (candidate for candidate in (
                self._town_map_goal_step(snapshot, position) for position in positions
            ) if candidate is not None),
            key=lambda pos: snapshot.player.position.distance_to(pos),
            default=None,
        )
        if step is None:
            return None
        self.last_reason = "town:teleport"
        suffix = "m" + chr(ord("a") + destination_town_id) if step in positions else ""
        return self._step_toward(snapshot, step, tail=suffix)

    def _read_dungeon_recall_scroll_key(
        self, snapshot: Snapshot, recall: InventoryItem
    ) -> str:
        recall_count = sum(
            item.count for item in snapshot.inventory if item.is_recall_scroll
        )
        self._dungeon_recall_issue_watch = (
            snapshot.floor_key,
            snapshot.turn,
            recall_count,
        )
        self._post_owner_expectation(
            snapshot, "return:recall", "inventory", "recalling", "floor"
        )
        return self._read_key(snapshot, recall)

    def _dungeon_recall_confirmation_key(
        self, snapshot: Snapshot
    ) -> str | None:
        """Share the pending dungeon-recall read guard between all issuers."""
        issue_watch = self._dungeon_recall_issue_watch
        if snapshot.player.recalling or issue_watch is None:
            return None
        if not self._owner_may_select(
            snapshot, "return:await-recall-confirmation"
        ):
            self._dungeon_recall_issue_watch = None
            return None
        watched_floor, issue_turn, pre_read_count = issue_watch
        if watched_floor != snapshot.floor_key:
            self._dungeon_recall_issue_watch = None
            return None
        recall_count = sum(
            item.count for item in snapshot.inventory if item.is_recall_scroll
        )
        if snapshot.turn <= issue_turn or (
            recall_count < pre_read_count
            and snapshot.turn <= issue_turn + RECALL_ISSUE_CONFIRM_TURNS
        ):
            # Treat both the unchanged command-turn redraw and a consumed
            # scroll within the confirmation window as pending states. The
            # exported recalling flag can lag behind either, so reading again
            # can consume a second scroll.
            self.last_reason = "return:await-recall-confirmation"
            self._post_owner_expectation(
                snapshot,
                self.last_reason,
                "inventory",
                "recalling",
                "floor",
            )
            return WAIT_KEY
        # The turn advanced without consuming the scroll: the command was
        # genuinely rejected, so one ordinary retry is safe.
        self._dungeon_recall_issue_watch = None
        self._owner_expectations.release("return:recall")
        return None

    def _should_start_town_return(self, snapshot: Snapshot) -> bool:
        # Records WHICH condition ends the run in self._last_return_trigger, so the
        # decision log shows why every dive returned (see the depth_safety telemetry).
        if snapshot.in_town:
            return False
        if self._guardian_descent_blocked(snapshot):
            self._last_return_trigger = "guardian-kit-insufficient"
            return True
        if len(snapshot.inventory) >= PACK_CAPACITY:
            self._last_return_trigger = "pack-full"
            return True
        # Hungry with nothing edible left ends ANY run — including mining and
        # scavenge dives, which the suppression below otherwise exempts from
        # every supply threshold. A fundraising character starved to death
        # behind that exemption (2026-07-17): income policy owns its economics,
        # never the character's survival.
        if snapshot.player.hungry and self._find_edible(snapshot) is None:
            self._last_return_trigger = "food-hungry"
            return True
        # Income dives own their completion/return policy in _fundraising_key.
        # Ordinary expedition supply thresholds must not bounce a freshly
        # launched scavenge or mining run straight back to town.
        if self._fundraising_mode in {"mine", "scavenge"}:
            return False
        ledger = self._supply_ledger(snapshot, snapshot.dungeon_level)
        if snapshot.player.class_id >= 0:
            if (
                self._deepest_floor_escape_kit_empty(snapshot)
                and (
                    ledger["teleport"].obtainable
                    or snapshot.dungeon_level > WALK_OUT_MAX_DEPTH
                )
            ):
                self._last_return_trigger = "escape-kit-empty"
                return True
            # A resistance gap at the CURRENT floor -- not the next one, which
            # _is_descent_target already gates before a descent is taken -- means
            # the character is standing somewhere its present gear no longer
            # covers: Word of Recall can land at the save-backed deepest floor
            # after a resistance-granting item was swapped/stashed, or an amulet
            # swap mid-dive can drop a required resistance. Nothing previously
            # caught an EXISTING gap, only a prospective one on the next stairs.
            # Leaving the depth (the return itself) clears this, so it cannot
            # flap. DEPTH_ABILITY_REQUIREMENTS only starts at 20F, so shallow
            # (and Yeek Cave mining, capped at 13F) floors never trigger it.
            if self._missing_required_abilities(snapshot, snapshot.dungeon_level):
                self._last_return_trigger = "resist-gap"
                return True
            ledger_shortages = self._ledger_return_shortages(
                ledger,
                snapshot.dungeon_level,
            )
            ledger_shortages = [
                status for status in ledger_shortages
                if status.kind in {"recall", "teleport", "cure"}
            ]
            if ledger_shortages:
                self._last_return_trigger = {
                    "recall": "recall-low",
                    "teleport": "teleport-low",
                    "cure": "cure-low",
                }[ledger_shortages[0].kind]
                return True
            if snapshot.dungeon_level >= 1:
                if not self._expedition_light_ready(snapshot):
                    self._last_return_trigger = "light-low"
                    return True
            equipped_light = next(
                (it for it in snapshot.equipment if it.is_light), None
            )
            if equipped_light is None:
                self._last_return_trigger = "no-light"
                return True
            if (
                equipped_light.known
                and equipped_light.sval <= SV_LITE_LANTERN
                and equipped_light.fuel <= 0
                and self._light_refill_item(snapshot) is None
            ):
                self._last_return_trigger = "light-empty"
                return True
            knows_downstairs = bool(self._remembered_downstairs) or any(
                grid.known and grid.has_down_stairs
                for grid in snapshot.grids.values()
            )
            if knows_downstairs and self._next_depth_supply_shortage(snapshot):
                self._last_return_trigger = "next-depth-kit"
                return True
        # Hunger-without-food already returned True above (it runs before the
        # fundraising exemption); with something edible carried, the survival
        # gate eats instead of ending the run. Note the trigger fires only at
        # the ACTUAL hungry bands (hungry/weak/fainting), not below Full —
        # "normal" is a wide band with ample margin to reach town, and bailing
        # there abandoned deep dives far too eagerly.
        return False

    def _return_to_town_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        *,
        allow_recall: bool = True,
    ) -> str | None:
        player = snapshot.player
        if snapshot.in_town:
            self._dungeon_recall_issue_watch = None
            return None
        active_fixed = self._active_fixed_quest_id(snapshot)
        if (
            self._quest_floor_exit_locked(snapshot)
            or active_fixed is not None and self._fixed_quest_is_once(active_fixed)
        ):
            # A quest exit is represented as up-stairs, but ordinary pack/light/
            # supply returns must never fail a one-shot quest. Survival escapes
            # run earlier and remain intentionally permitted.
            self._returning_to_town = False
            self._last_return_trigger = None
            return None
        if self._should_start_town_return(snapshot) or player.recalling:
            self._returning_to_town = True
        if not self._returning_to_town:
            return None

        here = snapshot.grid_at(player.position)
        if here is not None and self._is_upstairs_target(here):
            self.last_reason = "return:ascend"
            return UP_STAIRS_KEY

        pending_recall = self._dungeon_recall_confirmation_key(snapshot)
        if pending_recall is not None:
            return pending_recall

        if player.recalling:
            self.last_reason = "return:wait-recall"
            return WAIT_KEY

        # A previously latched return bypasses the ordinary light-upkeep block
        # later in _decide.  Refill here before trying to read Word of Recall:
        # Hengband rejects reading in darkness without consuming a turn, which
        # otherwise repeats READ_KEY + slot until the loop watchdog stops us.
        if not player.confused:
            darkness_recovery = self._darkness_recovery_key(snapshot)
            if darkness_recovery is not None:
                return darkness_recovery
        dark_locomotion = self._dark_locomotion_key(snapshot)
        if dark_locomotion is not None:
            return dark_locomotion

        recall = self._find_recall_scroll(snapshot)
        if (
            allow_recall
            and snapshot.dungeon_level > WALK_OUT_MAX_DEPTH
            and recall is not None
            and not player.blind
            and not player.confused
            and self._can_read_scrolls(snapshot)
            and self._owner_may_select(snapshot, "return:recall")
        ):
            self.last_reason = "return:recall"
            return self._read_dungeon_recall_scroll_key(snapshot, recall)

        upstairs_step = self._escape_state.read_once(
            snapshot,
            "return:upstairs-step",
            lambda: self._nearest_goal_step(snapshot, self._is_upstairs_target),
        )
        assert upstairs_step is None or isinstance(upstairs_step, Position)
        wall_owner = (
            self._escape_state.owner == "return"
            and self._escape_state.rung == "return:seek-secret-wall"
        )
        if wall_owner:
            if upstairs_step is None:
                self._escape_state.stable_decisions = 0
            else:
                self._escape_state.stable_decisions += 1
                if self._escape_state.stable_decisions >= 2:
                    self._escape_state.release()
                    self.last_reason = "return:seek-upstairs"
                    if self._escape_state.owner != "disengage":
                        self._escape_state.enter("return", self.last_reason)
                    return self._step_toward(snapshot, upstairs_step)

            # A temporary occupant can split a one-tile corridor in the
            # remembered movement graph for one decision. Once that hands the
            # exit search to the wall owner, keep consuming its existing search
            # budgets instead of letting a single clear redraw reverse course.
            if (
                not self._is_forgetting_maze(snapshot)
                and not player.blind
                and not player.confused
            ):
                if self._undersearched_walls(player.position):
                    self._record_wall_search(player.position)
                    self.last_reason = "return:search-upstairs"
                    return SEARCH_KEY
                step = self._secret_wall_search_step(snapshot)
                if step is not None:
                    self.last_reason = "return:seek-secret-wall"
                    return self._step_toward(snapshot, step)

            # No wall-search budget remains reachable. Release ownership so the
            # normal return rungs (including a currently valid stair path) can
            # make progress.
            self._escape_state.release()

        if upstairs_step is not None:
            self.last_reason = "return:seek-upstairs"
            if self._escape_state.owner != "disengage":
                self._escape_state.enter("return", self.last_reason)
            return self._step_toward(snapshot, upstairs_step)

        if self._is_oscillating():
            # The ordinary exploration owner has an oscillation breakout below,
            # but a latched return exits through this method first. Give walking
            # returns the same unknown probe/search escape instead of repeating
            # a four-cell frontier cycle forever.
            step = self._probe_unknown_step(snapshot)
            if step is not None:
                self._clear_explore_path(ExplorationPathOutcome.PAUSE)
                self.last_reason = "return:probe"
                return self._step_toward(snapshot, step)
            if (
                not self._is_forgetting_maze(snapshot)
                and not player.blind
                and not player.confused
                and self._undersearched_walls(player.position)
            ):
                self._record_wall_search(player.position)
                self._clear_explore_path(ExplorationPathOutcome.PAUSE)
                self.last_reason = "return:search-upstairs"
                return SEARCH_KEY
        else:
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "return:explore"
                return self._step_toward(snapshot, step)

        # Returning without a recall scroll requires an up-stair, which may be
        # hidden behind a secret door. This cannot use the ordinary secret-wall
        # sweep below: the return owner exits earlier, and that sweep is disabled
        # whenever any down-stair is known. Search likely wall exits after all
        # reachable floor/frontier exploration is exhausted.
        if (
            not self._is_forgetting_maze(snapshot)
            and not player.blind
            and not player.confused
        ):
            if self._undersearched_walls(player.position):
                self._record_wall_search(player.position)
                self.last_reason = "return:search-upstairs"
                return SEARCH_KEY
            step = self._secret_wall_search_step(snapshot)
            if step is not None:
                self.last_reason = "return:seek-secret-wall"
                if self._escape_state.owner != "disengage":
                    self._escape_state.enter("return", self.last_reason)
                return self._step_toward(snapshot, step)

        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "return:wander"
            return self._step_toward(snapshot, step)

        self.last_reason = "return:wait"
        return WAIT_KEY

    def _town_entrance_cells(self, snapshot: Snapshot) -> set[Position]:
        """Known modal store/building cells that routes should avoid crossing."""
        if not snapshot.in_town:
            return set()
        self._refresh_town_facts(snapshot)
        if self._town_entrance_cache is not None:
            return set(self._town_entrance_cache)
        # _town_emitted_entrances preserves a legacy ``store_number is not None``
        # predicate and therefore includes ordinary parsed grids whose sentinel
        # is -1.  The visit set uses the real modal-cell predicates and retains
        # observed entrances after they leave the emitted window.
        entrances = set(self._town_visit_entrances)
        if self._town_map_active(snapshot):
            entrances.update(self._town_map.stores.values())
            entrances.update(self._town_map.buildings.values())
            for positions in self._town_map.quest_buildings.values():
                entrances.update(positions)
            for positions in self._town_map.quest_entrances.values():
                entrances.update(positions)
        self._town_entrance_cache = frozenset(entrances)
        return set(self._town_entrance_cache)

    def _town_map_goal_step(
        self,
        snapshot: Snapshot,
        target: Position | None,
        *,
        blocked: set[Position] | None = None,
        allow_entrance_fallback: bool = True,
    ) -> Position | None:
        """BFS to a specific static-town-map tile (store or dungeon entrance).

        Unlike _nearest_goal_step, the goal is matched by POSITION rather than by
        an emitted grid flag, so it still works at night: an unlit store/entrance
        tile is absent from snapshot.grids, yet the town map remembers where it
        is and merged it into the walkable set. Returns the first step, or None if
        already there / unreachable across the remembered walkable tiles.
        """
        if target is None:
            return None
        start = snapshot.player.position
        if start == target:
            return None
        blocked = blocked or set()
        entrance_cells = self._town_entrance_cells(snapshot)
        entrance_cells.discard(start)
        entrance_cells.discard(target)
        route_attempts = (blocked | entrance_cells, blocked)
        if not allow_entrance_fallback:
            route_attempts = route_attempts[:1]
        for route_blocked in route_attempts:
            seen = {start}
            queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
            while queue:
                pos, first_step = queue.popleft()
                if pos == target:
                    return first_step
                for neighbor in self._walkable_neighbors(snapshot, pos):
                    if neighbor in seen or neighbor in route_blocked:
                        continue
                    seen.add(neighbor)
                    queue.append(
                        (neighbor, neighbor if first_step is None else first_step)
                    )
        return None

    def _town_map_descent_entrance(self, snapshot: Snapshot) -> Position | None:
        """The town map's '>' entrance, but only when the bot would descend on
        foot: fundraising mines level 1, and a shallow run (deepest below the
        recall threshold) walks in. A deep run returns by Word of Recall from
        anywhere in town (see _town_special_key), so it needs no entrance route.
        """
        if not self._town_map_active(snapshot):
            return None
        if self._town_map.entrance is None:
            return None
        entrance = snapshot.grids.get(self._town_map.entrance)
        remembered_suppressed_entrance = (
            entrance is None
            and self._town_restock_suppressed
        )
        if not remembered_suppressed_entrance and (
            entrance is None or not self._is_active_dungeon_entrance(entrance)
        ):
            return None
        if self._town_restock_suppressed:
            # A deep character with no recall scroll loses its saved depth here,
            # but an L1 walk-in is the only remaining departure; do not turn it
            # into an unsupplied deep recall. This departure-only bypass also
            # skips _fundraising_departure_ready's kit/light/HP gate; light is
            # checked by _descent_is_blocked, and DESCEND_MIN_HP_RATIO remains
            # the final HP backstop before the entrance command is emitted.
            return self._town_map.entrance
        if (
            self._fundraising_mode in {"mine", "scavenge"}
            or self._deepest_level < RECALL_MIN_DEPTH
        ):
            return self._town_map.entrance
        return None

    def _effective_town_id(self, snapshot: Snapshot) -> int:
        """Recover a missing town id from exported, player-known landmarks."""
        if snapshot.town_id >= 0:
            return snapshot.town_id
        observed_buildings = {
            grid.building_type: grid.position
            for grid in snapshot.grids.values()
            if grid.known and grid.building_type >= 0
        }
        if not observed_buildings:
            # Preserve synthetic/legacy snapshots that predate town metadata.
            return 0 if 0 in self._town_maps else -1
        scored: list[tuple[int, int]] = []
        for town_id, town_map in self._town_maps.items():
            matches = sum(
                town_map.building_position(building_type) == position
                for building_type, position in observed_buildings.items()
            )
            if matches:
                scored.append((matches, town_id))
        if not scored:
            return 0 if 0 in self._town_maps else -1
        best_score = max(score for score, _town_id in scored)
        winners = [town_id for score, town_id in scored if score == best_score]
        return winners[0] if len(winners) == 1 else -1

    def _town_map_active(self, snapshot: Snapshot) -> bool:
        # The static Outpost layout is loaded AND matches this surface floor,
        # so the whole fixed town is effectively known (walls included).
        # Legacy/synthetic snapshots use -1 for an unknown town id; preserve
        # the historical single-map Outpost behavior for them.  Real new
        # snapshots select strictly by the emitter's town id.
        town_id = self._effective_town_id(snapshot)
        selected = self._town_maps.get(town_id)
        if selected is not None:
            self._town_map = selected
        return (
            selected is not None
            and snapshot.in_town
            and (snapshot.width or max((p.x for p in snapshot.grids), default=-1) + 1)
            == selected.width
            and (snapshot.height or max((p.y for p in snapshot.grids), default=-1) + 1)
            == selected.height
        )

    def _on_town_border(self, snapshot: Snapshot, pos: Position) -> bool:
        # A town is a fixed walled map; its passable border tiles are the roads
        # that lead OFF this tile into the adjacent open wilderness. Stepping onto
        # one leaves the safe town (a clvl-4 bot wandered out this way and a
        # Cyclops killed it), so town wandering must shun the outer ring.
        if not snapshot.in_town:
            return False
        if snapshot is self._map_predicate_snapshot:
            if pos in self._town_border_cache:
                return self._town_border_cache[pos]
        result = bool(
            snapshot.width > 0
            and snapshot.height > 0
            and (
            pos.y == 0
            or pos.x == 0
            or pos.y == snapshot.height - 1
            or pos.x == snapshot.width - 1
            )
        )
        if snapshot is self._map_predicate_snapshot:
            self._town_border_cache[pos] = result
        return result
