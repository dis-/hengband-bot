from __future__ import annotations

from collections import deque

from hengbot.baseitem_knowledge import item_base_cost
from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    SV_ROD_IDENTIFY,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_STAR_IDENTIFY,
    SV_STAFF_IDENTIFY,
    TVAL_CHEST,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_STAFF,
    InventoryItem,
    MonsterState,
    Position,
    Snapshot,
    StoreItem,
    item_requires_full_identification,
)
from hengbot.policy_constants import (
    CARDINAL_OFFSETS,
    CHEST_COLLECT_BUDGET,
    CHEST_DISARM_BUDGET,
    CHEST_DISARM_KEY,
    CHEST_DROP_KEY,
    CHEST_OPEN_BUDGET,
    CHEST_OPEN_KEY,
    CHEST_SEARCH_BUDGET,
    CHEST_SEARCH_KEY,
    FULL_IDENTIFY_DISMISS_SUFFIX,
    FUNDRAISING_GOLD_TARGET,
    IDENTIFY_FAIL_LIMIT,
    IDENTIFY_PRESSURE_FREE_SLOTS,
    LOOT_DEFER_BLOCKERS,
    LOOT_THREAT_DAMAGE_RATIO,
    NEIGHBOR_OFFSETS,
    PACK_CAPACITY,
    PROBE_LIMIT,
    RANGED_MAX_DISTANCE,
    READ_KEY,
    STAFF_IDENTIFY_MIN_SUCCESS,
    STORE_RESTOCK_WAIT_TURNS,
    USE_STAFF_KEY,
    WAIT_KEY,
    ZAP_ROD_KEY,
)
from hengbot.quest_navigator import PICKUP_KEY


class IdentificationMixin:
    def _chest_processing_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        allowed_positions: set[Position] | None = None,
    ) -> str | None:
        """User-specified chest pipeline: drop → step beside → s ×N → D ×N → o ×N.

        The trap-discovered message is invisible to snapshots, so each phase
        spends a fixed key budget instead of observing: search() reveals an
        adjacent trapped chest at skill_srh% per press, disarm can fail, and a
        locked chest takes several picks. Budget exhaustion abandons the chest
        (whatever spilled is normal loot)."""
        player = snapshot.player
        if hostiles or player.blind or player.confused:
            return None
        floor_chests = [
            candidate.position
            for candidate in snapshot.grids.values()
            if candidate.known
            and candidate.object_count > 0
            and (
                TVAL_CHEST in candidate.object_tvals
                or (
                    allowed_positions is not None
                    and candidate.position in allowed_positions
                )
            )
            and candidate.position not in self._processed_chest_positions
            and (
                allowed_positions is None
                or candidate.position in allowed_positions
            )
        ]
        if self._chest_drop_origin is not None:
            nearby = [
                position
                for position in floor_chests
                if position.distance_to(self._chest_drop_origin) <= 3
            ]
            if nearby:
                self._chest_position = min(
                    nearby,
                    key=lambda position: (
                        player.position.distance_to(position), position.y, position.x
                    ),
                )
                self._chest_phase_counts = {}
                self._chest_drop_origin = None
                self._chest_preopen_objects = None
            elif any(
                self._is_processable_chest(item) for item in snapshot.inventory
            ):
                # The drop command has not yet reached the next stable snapshot.
                # Keep ownership so town errands cannot carry the chest away.
                self.last_reason = "chest:await-drop"
                return WAIT_KEY
            else:
                origin = self._chest_drop_origin
                origin_grid = snapshot.grids.get(origin)
                if player.position == origin or (
                    origin_grid is not None and origin_grid.object_count > 0
                ):
                    # Objects under the player are omitted from the visible
                    # tval list. Preserve the legacy underfoot fallback only
                    # when no displaced chest was actually observed.
                    self._chest_position = origin
                    self._chest_phase_counts = {}
                    self._chest_preopen_objects = None
                self._chest_drop_origin = None
        if self._chest_position is not None:
            chest_pos = self._chest_position
            distance = player.position.distance_to(chest_pos)
            grid = snapshot.grids.get(chest_pos)
            counts = self._chest_phase_counts
            if counts.get("open", 0) > 0:
                # Chest::open() calls drop_near() for every generated item.
                # Contents can therefore land anywhere within radius three,
                # not just on the original chest square (live Q34: three cells).
                contents = set()
                for candidate in snapshot.grids.values():
                    if (
                        not candidate.known
                        or candidate.object_count <= 0
                        or candidate.position.distance_to(chest_pos) > 3
                    ):
                        continue
                    non_chests = sum(
                        tval != TVAL_CHEST for tval in candidate.object_tvals
                    )
                    if self._chest_preopen_objects is None:
                        # Resume compatibility for an already-opened chest whose
                        # pre-open snapshot was owned by the previous process.
                        is_new_content = (
                            candidate.position != chest_pos
                            or candidate.object_count > 1
                            or non_chests > 0
                        )
                    else:
                        before_count, before_non_chests = (
                            self._chest_preopen_objects.get(
                                candidate.position, (0, 0)
                            )
                        )
                        is_new_content = (
                            candidate.object_count > before_count
                            or non_chests > before_non_chests
                        )
                    if is_new_content:
                        contents.add(candidate.position)
                if contents:
                    self._chest_collecting = True
                    if counts.get("collect", 0) >= CHEST_COLLECT_BUDGET:
                        contents.clear()
                    else:
                        counts["collect"] = counts.get("collect", 0) + 1
                if contents:
                    here = snapshot.grids.get(player.position)
                    if player.position in contents and here is not None:
                        self.last_reason = "chest:collect-contents"
                        if here.object_count > 1:
                            return PICKUP_KEY + ("a" * here.object_count)
                        return PICKUP_KEY
                    step = self._nearest_goal_step(
                        snapshot, lambda candidate: candidate.position in contents
                    )
                    if step is not None:
                        self.last_reason = "chest:collect-contents"
                        return self._step_toward(snapshot, step)
                if self._chest_collecting:
                    self._processed_chest_positions.add(chest_pos)
                    self._chest_position = None
                    self._chest_phase_counts = {}
                    self._chest_collecting = False
                    self._chest_preopen_objects = None
                    return None
            if distance > 0 and grid is not None and grid.object_count == 0:
                # Opened and fully looted, or destroyed by its own trap.
                self._processed_chest_positions.add(chest_pos)
                self._chest_position = None
                self._chest_phase_counts = {}
                self._chest_collecting = False
                self._chest_preopen_objects = None
                return None
            if distance == 0:
                # An avoided step-off pick would re-run _step_toward's refusal
                # every decision from this same tile; abandon the chest (the
                # no-neighbour exit) rather than repeat it.
                neighbors = [
                    neighbor
                    for neighbor in self._walkable_neighbors(
                        snapshot, player.position
                    )
                    if neighbor not in self._engagement_avoid_cells
                ]
                if not neighbors:
                    self._chest_position = None
                    self._chest_phase_counts = {}
                    self._chest_preopen_objects = None
                    return None
                self.last_reason = "chest:step-off"
                return self._step_toward(snapshot, neighbors[0])
            if distance > 1:
                step = self._nearest_goal_step(
                    snapshot,
                    lambda g: g.position != chest_pos
                    and g.position.distance_to(chest_pos) == 1,
                )
                if step is None:
                    self._chest_position = None
                    self._chest_phase_counts = {}
                    self._chest_preopen_objects = None
                    return None
                self.last_reason = "chest:approach"
                return self._step_toward(snapshot, step)
            if counts.get("search", 0) < CHEST_SEARCH_BUDGET:
                counts["search"] = counts.get("search", 0) + 1
                self.last_reason = "chest:search"
                return CHEST_SEARCH_KEY
            direction = self._direction_key(player.position, chest_pos)
            if counts.get("disarm", 0) < CHEST_DISARM_BUDGET:
                counts["disarm"] = counts.get("disarm", 0) + 1
                self.last_reason = "chest:disarm"
                return CHEST_DISARM_KEY + direction
            if counts.get("open", 0) < CHEST_OPEN_BUDGET:
                if counts.get("open", 0) == 0:
                    self._chest_preopen_objects = {
                        candidate.position: (
                            candidate.object_count,
                            sum(
                                tval != TVAL_CHEST
                                for tval in candidate.object_tvals
                            ),
                        )
                        for candidate in snapshot.grids.values()
                        if candidate.known
                        and candidate.object_count > 0
                        and candidate.position.distance_to(chest_pos) <= 3
                    }
                counts["open"] = counts.get("open", 0) + 1
                self.last_reason = "chest:open"
                return CHEST_OPEN_KEY + direction
            self._chest_position = None
            self._chest_phase_counts = {}
            self._chest_collecting = False
            self._chest_preopen_objects = None
            self._processed_chest_positions.add(chest_pos)
            return None
        if floor_chests:
            if player.hp < player.max_hp * 0.8:
                self.last_reason = "chest:wait-health"
                return WAIT_KEY
            self._chest_position = min(
                floor_chests,
                key=lambda position: (
                    player.position.distance_to(position), position.y, position.x
                ),
            )
            self._chest_phase_counts = {}
            self._chest_preopen_objects = None
            return self._chest_processing_key(
                snapshot, hostiles, allowed_positions=allowed_positions
            )
        chest = next(
            (it for it in snapshot.inventory if self._is_processable_chest(it)),
            None,
        )
        if chest is None:
            return None
        if player.hp < player.max_hp * 0.8:
            # A chest trap can hurt; open on a healthy bar.
            return None
        if allowed_positions is not None and player.position not in allowed_positions:
            target = min(
                allowed_positions,
                key=lambda position: (
                    player.position.distance_to(position), position.y, position.x
                ),
            )
            profile = self.approved_quest_strategy(snapshot.floor_key[2])
            step = (
                self._quest_strategy_route_step(snapshot, profile, target)
                if profile is not None
                else None
            )
            if step is None:
                # A completed quest can be resumed with no in-memory record of
                # cleared fixed targets.  Its reviewed route may then reject
                # every path back to the chest's reserved square.  Waiting here
                # can never change that routing evidence, so process the carried
                # chest at the current safe, hostile-free position instead.
                self._chest_drop_origin = player.position
                self._chest_phase_counts = {}
                self._chest_collecting = False
                self._chest_preopen_objects = None
                self.last_reason = "chest:drop-unreachable-reserved"
                return CHEST_DROP_KEY + chest.slot
            self.last_reason = "chest:return-reserved-position"
            return self._step_toward(snapshot, step)
        self._chest_drop_origin = player.position
        self._chest_phase_counts = {}
        self._chest_collecting = False
        self._chest_preopen_objects = None
        self.last_reason = "chest:drop"
        return CHEST_DROP_KEY + chest.slot

    def _pack_pressure_identify_key(self, snapshot: Snapshot) -> str | None:
        """Identify an unknown while the pack is filling, so the disposal/sale
        logic can judge it before it crowds out real loot.

        Dungeon-only (town has its own identify errands); mushrooms are shed, not
        identified. Uses the carried Staff of Identify / Rod / scroll on the first
        unaware, non-food item — command + source slot + target slot.
        """
        if snapshot.in_town:
            return None
        if PACK_CAPACITY - len(snapshot.inventory) > IDENTIFY_PRESSURE_FREE_SLOTS:
            return None
        source = self._find_identification_source(snapshot, full=False)
        if source is None:
            return None
        command, src = source
        target = self._first_item(
            snapshot,
            # `aware` only means the base kind is recognized. Equipment can be
            # aware while this specific item is still unidentified (`known=False`),
            # as with the Leather Gloves that filled the live pack and triggered
            # Recall before their "average" pseudo-ID became disposable.
            lambda it: not it.known
            and not it.is_food
            and not self._is_ammunition(it)
            and it.slot != src.slot
            and self._item_signature(it) not in self._unidentifiable_sigs,
        )
        if target is None:
            return None
        # Verify the previous attempt landed: if the pack's unknown count is
        # unchanged when the same target comes up again, the device use did not
        # take (a stalled prompt), so after a few tries abandon this target rather
        # than looping on it forever.
        unknown_count = sum(
            1 for it in snapshot.inventory if not it.known and not it.is_food
        )
        watch = (self._item_signature(target), unknown_count)
        if watch == self._identify_watch:
            self._identify_fail_streak += 1
            if self._identify_fail_streak >= IDENTIFY_FAIL_LIMIT:
                self._unidentifiable_sigs.add(self._item_signature(target))
                self._identify_watch = None
                self._identify_fail_streak = 0
                return None
        else:
            self._identify_watch = watch
            self._identify_fail_streak = 0
        self.last_reason = "identify:pack-pressure"
        if command == READ_KEY:
            return self._read_key(snapshot, src, target.slot)
        return command + src.slot + target.slot

    def _full_pack_destroy_key(self, snapshot: Snapshot) -> str | None:
        """Destroy one disposable item to free a pack slot, verifying progress.

        The previous attempt is watched: if the pack is unchanged when the same
        item comes up for destruction again, the destroy did not take (the game
        refused it, or the keys stalled), so after DESTROY_FAIL_LIMIT tries the
        item is marked undestroyable and skipped. When nothing destroyable is
        left we return None and let the caller fall through to the return-to-town
        path (a full pack already triggers _should_start_town_return), which
        stops the bot collecting more loot it cannot carry.
        """
        return self._verified_destroy_key(
            snapshot,
            self._find_disposable_item,
            "inventory:destroy-disposable-item",
        )

    def _full_pack_loot_triage_key(self, snapshot: Snapshot) -> str | None:
        """Identify and exchange valuable guardian loot before permitting return."""
        destroy = self._full_pack_destroy_key(snapshot)
        if destroy is not None:
            return destroy
        identify = self._pack_pressure_identify_key(snapshot)
        if identify is not None:
            return identify

        if self._look_floor_key != snapshot.floor_key:
            self._look_floor_items.clear()
            self._look_floor_object_counts.clear()
            self._look_probe_inflight = False
        loot_positions = {
            grid.position
            for grid in snapshot.grids.values()
            if grid.object_count > 0 and grid.position not in self._deferred_loot
        }
        if not loot_positions:
            return None
        if self._look_probe_inflight:
            self._look_probe_inflight = False
        if self._look_floor_key != snapshot.floor_key:
            return self._look_probe_key(snapshot)
        live_counts = {
            position: snapshot.grids[position].object_count
            for position in loot_positions
        }
        cached_counts = {
            position: self._look_floor_object_counts.get(position, live_counts[position])
            for position in loot_positions
        }
        if live_counts != cached_counts:
            # A pickup can leave a non-empty pile whose old identities still
            # look usable. Invalidate all identities and make one fresh probe;
            # the recorded counts prevent a missing response from re-probing.
            return self._look_probe_key(snapshot)

        for position in sorted(
            loot_positions,
            key=lambda candidate: snapshot.player.position.distance_to(candidate),
        ):
            for floor_item in self._look_floor_items.get(position, ()):
                if item_base_cost(floor_item, self._baseitem_costs) is None:
                    if position == snapshot.player.position:
                        identify = self._floor_item_identify_key(snapshot, floor_item)
                        if identify is not None:
                            return identify
                    else:
                        step = self._nearest_goal_step(
                            snapshot, lambda grid, target=position: grid.position == target
                        )
                        if step is not None:
                            self.last_reason = "loot:seek-unidentified-floor-item"
                            return self._step_toward(snapshot, step)

        carried = self._cheapest_exchange_item(snapshot)
        if carried is None:
            return None
        carried_cost = item_base_cost(carried, self._baseitem_costs)
        floor_costs = [
            item_base_cost(item, self._baseitem_costs)
            for position in loot_positions
            for item in self._look_floor_items.get(position, ())
        ]
        if carried_cost is None or not any(
            cost is not None and cost > carried_cost for cost in floor_costs
        ):
            return None
        return self._verified_destroy_key(
            snapshot,
            lambda current, selected=carried: (
                selected
                if self._item_signature(selected) not in self._undestroyable_sigs
                and self._entire_stack_is_surplus(current, selected)
                else None
            ),
            "inventory:exchange-cheapest-surplus",
        )

    def _identification_need_unsatisfiable(self, snapshot: Snapshot) -> bool:
        """Whether a pending identify errand cannot advance this town visit.

        Mirrors the store-needs logic (which adds no store in exactly this case):
        no identify source is carried or buyable because the Alchemist was
        already tried and holds none. A pending withdrawal of the identification
        target is not a source: until a usable source is carried, that withdrawal
        cannot execute and must not keep the incomplete-catalog escape valve shut.
        When an item needs *Identify* the town cannot supply, the need would
        otherwise stay set forever and keep the escape valve shut.
        """
        if self._identification_need is None:
            return False
        source = self._find_identification_source(
            snapshot,
            full=self._identification_need == "full",
            reliable_only=self._identification_requires_reliable_source(snapshot),
        )
        if source is not None:
            return False
        if (
            self._identification_need != "full"
            and STORE_ALCHEMIST not in self._town_store_attempted
        ):
            return False
        return True

    def _identification_need_actionable(self, snapshot: Snapshot) -> bool:
        """Return whether the current visit can compose the identify errand."""
        if self._identification_need is None:
            return False
        source = self._find_identification_source(
            snapshot,
            full=self._identification_need == "full",
            reliable_only=self._identification_requires_reliable_source(snapshot),
        )
        if source is not None:
            return True
        refusal = self._shop_selector_diagnostics.get("composition_refusal")
        refusal_sequence = self._shop_selector_diagnostics.get(
            "composition_refusal_sequence"
        )
        if refusal is not None and refusal_sequence == self._decision_sequence:
            return False
        return (
            self._identification_need != "full"
            and STORE_ALCHEMIST not in self._town_store_attempted
        )

    @staticmethod
    def _identification_flow_candidate(
        item: InventoryItem | StoreItem,
    ) -> bool:
        """Return whether the town identification scan should own an item."""
        return (
            item.is_equipment
            and (
                (
                    item.known
                    and not item.fully_known
                    and (
                        item.is_cursed
                        or item_requires_full_identification(item)
                    )
                )
                or (not item.known and item.pseudo_feeling != "average")
            )
        )

    def _identification_flow_owns(
        self, item: InventoryItem | StoreItem
    ) -> bool:
        signature = self._item_signature(item)
        return (
            self._identification_flow_candidate(item)
            or signature == self._home_pending_item
            or signature in self._home_pending_batch
        )

    def _find_identification_source(
        self,
        snapshot: Snapshot,
        *,
        full: bool,
        reliable_only: bool = False,
        reservation_target: tuple[str, int, int] | None = None,
    ) -> tuple[str, InventoryItem] | None:
        self._bind_identification_source_reservation(snapshot)

        def available(item: InventoryItem) -> bool:
            reservation = self._identification_source_reservation
            if reservation is None or reservation.get("state") == "awaiting-source":
                return True
            if reservation_target == reservation.get("target"):
                return True
            source = reservation.get("source")
            if not isinstance(source, dict):
                return True
            if tuple(source.get("signature", ())) != self._item_signature(item):
                return True
            return self._identification_source_units(item) > 1

        if not full:
            if not reliable_only:
                staff = self._first_item(
                    snapshot,
                    lambda it: it.tval == TVAL_STAFF
                    and it.aware
                    and it.sval == SV_STAFF_IDENTIFY
                    and it.known
                    and it.charges > 0
                    and available(it),
                )
                if staff is not None:
                    return USE_STAFF_KEY, staff
                rod = self._first_item(
                    snapshot,
                    lambda it: it.tval == TVAL_ROD
                    and it.aware
                    and it.sval == SV_ROD_IDENTIFY
                    and it.known
                    and it.timeout == 0
                    and available(it),
                )
                if rod is not None:
                    return ZAP_ROD_KEY, rod
            scroll = self._first_item(
                snapshot,
                lambda it: it.is_scroll
                and it.aware
                and it.sval == SV_SCROLL_IDENTIFY
                and available(it),
            )
            if scroll is not None:
                return READ_KEY, scroll
            return None

        scroll = self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval == SV_SCROLL_STAR_IDENTIFY
            and available(it),
        )
        if scroll is not None:
            return READ_KEY, scroll
        return None

    @staticmethod
    def _identification_source_units(item: InventoryItem) -> int:
        if item.tval == TVAL_STAFF:
            return item.charges
        return item.count

    def _identification_source_items(
        self, snapshot: Snapshot, *, full: bool
    ) -> list[InventoryItem]:
        if full:
            return [
                item
                for item in snapshot.inventory
                if item.is_scroll
                and item.aware
                and item.sval == SV_SCROLL_STAR_IDENTIFY
            ]
        return [
            item
            for item in snapshot.inventory
            if item.is_scroll
            and item.aware
            and item.sval == SV_SCROLL_IDENTIFY
        ]

    def _bind_identification_source_reservation(self, snapshot: Snapshot) -> None:
        reservation = self._identification_source_reservation
        if reservation is None or reservation.get("state") != "awaiting-source":
            return
        full = reservation.get("kind") == "full"
        baseline = reservation.get("baseline")
        if not isinstance(baseline, dict):
            baseline = {}
        current: dict[tuple[str, int, int], int] = {}
        items = self._identification_source_items(snapshot, full=full)
        for item in items:
            signature = self._item_signature(item)
            current[signature] = (
                current.get(signature, 0) + self._identification_source_units(item)
            )
        acquired = next(
            (
                item
                for item in items
                if current[self._item_signature(item)]
                > baseline.get(self._item_signature(item), 0)
            ),
            None,
        )
        if acquired is None:
            return
        reservation["source"] = {
            "signature": self._item_signature(acquired),
            "slot": acquired.slot,
        }
        reservation["state"] = "acquired"

    def _identification_requires_reliable_source(self, snapshot: Snapshot) -> bool:
        """Whether the pending target is worn and therefore needs a scroll.

        Device-use commands can fail before Hengband asks for an item target.
        Appending the equipment selector to a staff/rod command then feeds those
        remaining keys to the town map, which can enter the shop underfoot and
        create an identify/leave loop.  Scroll reading has no device-skill
        failure, so worn targets deliberately procure and use a scroll.
        """
        return (
            self._identification_candidate is not None
            or self._device_identification_candidate is not None
            or self._home_pending_item is not None
            or self._home_disposal_pending is not None
        )

    def _identification_source_obtainability(
        self, snapshot: Snapshot, *, full: bool
    ) -> str:
        """Return ``available``, ``unavailable``, or ``unknown`` for this visit.

        A carried usable source is authoritative.  Negative shelf evidence is
        usable only when the Alchemist page was observed in the current town
        visit, for the current town, and no later than this snapshot.  Older
        checkpoints and pages retained across travel are therefore unknown.
        """
        if self._find_identification_source(
            snapshot,
            full=full,
            reliable_only=self._identification_requires_reliable_source(snapshot),
        ) is not None:
            return "available"
        observation = self._town_supplier_stock_observations.get(STORE_ALCHEMIST)
        page = self._town_supplier_stock.get(STORE_ALCHEMIST)
        if (
            observation is None
            or page is None
            or observation[0] != self._effective_town_id(snapshot)
            or observation[1] > snapshot.turn
            or snapshot.turn - observation[1] >= STORE_RESTOCK_WAIT_TURNS
        ):
            return "unknown"
        wanted_sval = SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY
        return (
            "available"
            if any(
                item.tval == TVAL_SCROLL
                and item.sval == wanted_sval
                and item.price <= snapshot.player.gold
                for item in page.items
            )
            else "unavailable"
        )

    def _carried_identify_command(
        self,
        snapshot: Snapshot,
        target: InventoryItem,
        *,
        full: bool,
        reservation_target: tuple[str, int, int] | None = None,
    ) -> str | None:
        """Key that identifies a non-worn carried item, or None if none is usable.

        The carried Staff of Identify is only allowed when its modelled success
        rate clears STAFF_IDENTIFY_MIN_SUCCESS; below that a town staff misfire
        would leak the target selector onto the town map, so only a scroll is
        accepted.  A full *Identify* always needs a scroll regardless.  A device
        that repeatedly fails to land (unknown count unchanged) is abandoned via
        _unidentifiable_sigs so it cannot loop.
        """
        reliable_only = (
            self._identify_staff_success_rate(snapshot) < STAFF_IDENTIFY_MIN_SUCCESS
        )
        source = self._find_identification_source(
            snapshot,
            full=full,
            reliable_only=reliable_only,
            reservation_target=reservation_target,
        )
        if source is None:
            return None
        command, source_item = source
        if command in (USE_STAFF_KEY, ZAP_ROD_KEY):
            unknown_count = sum(
                1 for it in snapshot.inventory if not it.known and not it.is_food
            )
            watch = (self._item_signature(target), unknown_count)
            if watch == self._identify_watch:
                self._identify_fail_streak += 1
                if self._identify_fail_streak >= IDENTIFY_FAIL_LIMIT:
                    self._unidentifiable_sigs.add(self._item_signature(target))
                    self._identify_watch = None
                    self._identify_fail_streak = 0
                    return None
            else:
                self._identify_watch = watch
                self._identify_fail_streak = 0
        return (
            command
            + source_item.slot
            + target.slot
            + (FULL_IDENTIFY_DISMISS_SUFFIX if full else "")
        )

    def _identification_deadlock_recoverable(self, snapshot: Snapshot) -> bool:
        """A pure Home-identification deadlock that only a mining retry re-arms.

        The equipment optimizer is blocked by incomplete gear, yet every blocking
        item is a Home item already burned into _processed_home_items — so
        _find_home_candidate and _has_actionable_incomplete_home_item both skip it
        and no ordinary town errand can make progress. Clearing that skip-cache is
        exactly what the mining-return retry boundary does, so a single
        fundraising run resolves it. An equipped/pack unidentified item (or any
        non-Home blocker) is deliberately NOT treated as recoverable: mining does
        not re-arm it, so fundraising there would loop without ever clearing the
        block. That distinct gap (e.g. an unidentified worn weapon with no town
        identify errand) is left to its own owner rather than papered over with an
        endless mining cycle here.
        """
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR or not snapshot.in_town:
            return False
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            return False
        # An identification errand is already in flight (a scroll is being bought
        # or applied, or a withdrawn Home candidate is waiting): let it finish
        # rather than diverting into a mining trip.
        if self._identification_need is not None or self._home_candidate_waiting:
            return False
        # Fundraising self-cancels once gold reaches the target, so entering it
        # above the target is a no-op (and would recurse); gold is not the
        # constraint for this deadlock in any case.
        if snapshot.player.gold >= FUNDRAISING_GOLD_TARGET:
            return False
        preparation = self._prepare_equipment_optimization(snapshot)
        if (
            preparation is None
            or preparation.result is None
            or "incomplete-equipment-catalog" not in preparation.blockers
        ):
            return False
        incomplete_ids = preparation.result.incomplete_item_ids
        if not incomplete_ids:
            return False
        catalog = {owned.id: owned for owned in self._equipment_catalog.items}
        for item_id in incomplete_ids:
            owned = catalog.get(item_id)
            if owned is None or owned.origin != "home":
                return False
            if self._item_signature(owned.item) not in self._processed_home_items:
                return False
        return True

    def _outstanding_identification_count(self, snapshot: Snapshot, *, full: bool) -> int:
        """How many items still need this identification tier right now.

        full=True counts *Identify* targets (known ego/artifact/dragon-armour
        gear still missing its full traits); full=False counts plain Identify
        targets (an unknown item whose pseudo-sense is not "average"). Used to
        size a single scroll purchase over the whole outstanding tier instead
        of one scroll per store trip -- discovering each further need only
        after a fresh Home round trip measurably wasted most of a town stay
        (4 separate Alchemist visits for one Home identification batch).

        Mirrors the two mechanisms that actually consume these scrolls: the
        pack scan in prime() that seeds _home_pending_batch (all equipment,
        including lights and diggers that can otherwise block optimization) plus the
        actionable Home gear _has_actionable_incomplete_home_item finds via
        the duplicate-aware equipment catalog (same deferred/processed skip).
        """
        count = sum(
            1
            for item in (*snapshot.inventory, *snapshot.equipment)
            if (
                item.is_equipment
                and item.known
                and item_requires_full_identification(item)
                and not item.fully_known
                if full
                else self._normal_identification_flow_candidate(item)
            )
        )
        for owned in self._equipment_catalog.items:
            if owned.origin != "home" or not owned.identification_incomplete:
                continue
            if owned.item.known != full:
                continue
            signature = self._item_signature(owned.item)
            if signature in self._deferred_home_items:
                continue
            if owned.item.known and signature in self._processed_home_items:
                continue
            count += 1
        return count

    def _loot_step(
        self,
        snapshot: Snapshot,
        *,
        include_unsafe: bool = False,
        max_path_distance: int | None = None,
    ) -> Position | None:
        avoided_loot = self._known_loot & self._engagement_avoid_cells
        if avoided_loot:
            self._deferred_loot.update(avoided_loot)
            if avoided_loot & self._paralyzer_avoid_cells:
                self._loot_defer_blocker = "paralyzer-ring"
        candidates = self._known_loot - self._deferred_loot
        if include_unsafe:
            candidates |= {
                grid.position
                for grid in snapshot.grids.values()
                if grid.object_count > 0 and grid.passable
            }
        candidates -= self._deferred_loot
        candidates -= self._engagement_avoid_cells
        if not candidates:
            self._loot_target = None
            return None
        target = self._loot_target
        if (
            max_path_distance is None
            and target is not None
            and target in candidates
        ):
            step = self._position_target_step(snapshot, target)
            if step is not None:
                return step

        self._loot_target = None
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None, int]] = deque(
            [(start, None, 0)]
        )
        while queue:
            pos, first_step, distance = queue.popleft()
            if pos != start and pos in candidates:
                self._loot_target = pos
                return first_step
            if max_path_distance is not None and distance >= max_path_distance:
                continue
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen or neighbor in self._engagement_avoid_cells:
                    continue
                seen.add(neighbor)
                queue.append(
                    (
                        neighbor,
                        neighbor if first_step is None else first_step,
                        distance + 1,
                    )
                )
        return None

    def _normal_loot_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        *,
        max_path_distance: int | None = None,
        seek_reason: str = "seek-loot",
    ) -> str | None:
        """Collect visible drops before shopping or ordinary exploration.

        Adjacent combat and survival have already had priority. Distant weak
        monsters do not erase realised floor value. Trap-undetected grids are
        eligible because ordinary exploration already traverses them.
        """
        guarded = self._guarded_paralyzers(snapshot, hostiles)
        if guarded:
            ranged = self._ranged_attack_key(snapshot, guarded, [])
            if ranged is not None:
                return ranged
            target = min(
                guarded,
                key=lambda monster: snapshot.player.position.distance_to(
                    monster.position
                ),
            )
            if (
                self._has_usable_ranged_option(snapshot)
                and
                snapshot.player.position.distance_to(target.position)
                > RANGED_MAX_DISTANCE
            ):
                step = self._nearest_goal_step(
                    snapshot,
                    lambda grid: (
                        grid.position not in self._paralyzer_avoid_cells
                        and grid.position.distance_to(target.position)
                        <= RANGED_MAX_DISTANCE
                    ),
                )
                if step is not None:
                    self.last_reason = "paralyzer-guard:approach-range"
                    return self._step_toward(snapshot, step)
        blocker = self._loot_block_reason(snapshot, hostiles)
        if blocker is not None:
            if blocker == "paralyzer-ring":
                guarded_loot = (
                    self._known_loot - self._deferred_loot
                ) & self._paralyzer_avoid_cells
                self._deferred_loot.update(guarded_loot)
                self._loot_defer_blocker = "paralyzer-ring"
            if blocker in LOOT_DEFER_BLOCKERS and self._loot_target is not None:
                self._deferred_loot.add(self._loot_target)
                self._loot_target = None
            return None
        current_loot = self._current_floor_item_key(
            snapshot,
            pickup_reason="pickup",
            trigger_reason="trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot
        step = self._loot_step(
            snapshot, max_path_distance=max_path_distance
        )
        if step is None:
            return None
        self.last_reason = seek_reason
        return self._step_toward(snapshot, step)

    def _loot_block_reason(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if len(snapshot.inventory) >= PACK_CAPACITY:
            return "pack-full"
        if self._physical_adjacent_hostiles(snapshot):
            return "adjacent-hostile"
        if any(monster.can_summon for monster in hostiles):
            return "summoner-visible"
        if any(monster.can_multiply for monster in hostiles):
            return "multiplier-visible"
        if hostiles and self._predicted_damage(snapshot, hostiles, turns=3) >= (
            snapshot.player.hp * LOOT_THREAT_DAMAGE_RATIO
        ):
            return "material-threat"
        if (self._known_loot - self._deferred_loot) & self._paralyzer_avoid_cells:
            return "paralyzer-ring"
        return None

    def _probe_unknown_step(self, snapshot: Snapshot) -> Position | None:
        """Step into an adjacent unknown (absent, in-bounds) tile to reveal it.

        Prefer orthogonal probes, then try diagonals. A tile that keeps blocking
        the move (a wall) is abandoned after PROBE_LIMIT tries so we do not bump
        it forever.
        """
        origin = snapshot.player.position
        marked = self._marked_t
        blocked = self._blocked_unknown
        occupied = {
            (position.y, position.x)
            for position, count in self._visit_counts.items()
            if count > 0
        }
        blocked.difference_update(occupied)
        best: Position | None = None
        best_score: tuple[int, int] | None = None
        stairs = (
            min(
                self._remembered_upstairs,
                key=lambda pos: max(abs(pos.y - origin.y), abs(pos.x - origin.x)),
                default=None,
            )
            or min(
                self._remembered_downstairs,
                key=lambda pos: max(abs(pos.y - origin.y), abs(pos.x - origin.x)),
                default=None,
            )
        )
        probe_offsets = ((-1, 0), (1, 0), (0, -1), (0, 1)) + tuple(
            offset for offset in NEIGHBOR_OFFSETS if offset not in CARDINAL_OFFSETS
        )
        for dy, dx in probe_offsets:
            ny = origin.y + dy
            nx = origin.x + dx
            key = (ny, nx)
            if key in marked or key in blocked or key in occupied:
                continue
            if not snapshot.in_bounds(Position(ny, nx)):
                continue
            count = self._probe_counts[key]
            if count >= PROBE_LIMIT:
                continue
            distance = (
                max(abs(ny - stairs.y), abs(nx - stairs.x))
                if self._is_dark(snapshot) and stairs is not None
                else 0
            )
            score = (count, distance)
            if best_score is None or score < best_score:
                best_score = score
                best = Position(ny, nx)
        if best is None:
            self._probed_frontiers.add(origin)
            return None
        yx = (best.y, best.x)
        self._probe_counts[yx] += 1
        if self._probe_counts[yx] >= PROBE_LIMIT and yx not in occupied:
            # Bumped to the limit without ever stepping in → it is a wall we can't
            # see. Record it so the floor tile beside it stops reading as a
            # frontier (otherwise we are drawn back to that tile forever).
            self._blocked_unknown.add(yx)
        return best
