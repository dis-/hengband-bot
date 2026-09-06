from __future__ import annotations

from collections import deque

from hengbot.model import (
    DUNGEON_YEEK_CAVE,
    STORE_GENERAL,
    STORE_MAGIC,
    STORE_TEMPLE,
    SV_SCROLL_STAR_REMOVE_CURSE,
    TVAL_SCROLL,
    InventoryItem,
    MonsterState,
    Position,
    Snapshot,
    StoreItem,
)
from hengbot.policy_constants import (
    BARREN_FLOOR_SKIP_THRESHOLD,
    DIGGER_WIELD_LIMIT,
    EAT_KEY,
    ExplorationPathOutcome,
    FOOD_TYPE_MANA,
    FUNDRAISING_DETECTION_BASE_PRICE,
    FUNDRAISING_DIGGER_BASE_PRICE,
    FUNDRAISING_GOLD_TARGET,
    FUNDRAISING_KIT_MARGIN,
    MINING_COMBAT_CONTACT_LIMIT,
    MINING_DETECTION_RADIUS,
    MINING_NAVIGATION_REVISIT_LIMIT,
    MINING_OSCILLATION_RETARGET_LIMIT,
    MINING_ROUTE_REVISIT_LIMIT,
    MINING_STALL_LIMIT,
    MINING_SWEEP_HARD_LIMIT,
    MINING_SWEEP_NO_PROGRESS_LIMIT,
    MINING_THREAT_FREE_LIMIT,
    NEIGHBOR_OFFSETS,
    PACK_CAPACITY,
    RECALL_MIN_DEPTH,
    REFILL_KEY,
    SEARCH_KEY,
    SEARCH_LIMIT,
    STUCK_ESCAPE_LIMIT,
    TUNNEL_KEY,
    UP_STAIRS_KEY,
    WAIT_KEY,
)


class FundraisingMixin:

    def _fundraising_kit_secured(self, snapshot: Snapshot) -> bool:
        """Whether the minimum mining kit is physically in the pack/equipment."""
        return (
            self._has_digging_tool(snapshot)
            and self._count_treasure_detection_scrolls(snapshot) > 0
        )

    def _fundraising_kit_reserve(self, snapshot: Snapshot) -> int:
        """Gold to retain for whichever minimum mining-kit pieces are missing."""
        if (
            self._has_withdrawable_digging_tool(snapshot)
            and self._has_withdrawable_treasure_detection(snapshot)
        ):
            return 0
        digger_price = FUNDRAISING_DIGGER_BASE_PRICE
        detection_price = FUNDRAISING_DETECTION_BASE_PRICE
        if snapshot.store is not None:
            observed_diggers = [
                it.price for it in snapshot.store.items if it.is_digging_tool
            ]
            observed_detection = [
                it.price
                for it in snapshot.store.items
                if it.is_treasure_detection_scroll
            ]
            if observed_diggers:
                digger_price = min(observed_diggers)
            if observed_detection:
                detection_price = min(observed_detection)
        needed = FUNDRAISING_KIT_MARGIN
        if not self._has_withdrawable_digging_tool(snapshot):
            needed += digger_price
        if not self._has_withdrawable_treasure_detection(snapshot):
            needed += detection_price
        return needed

    def _fundraising_food_ready(self, snapshot: Snapshot) -> bool:
        """Allow a shallow cash run when town cannot sell the preferred reserve."""
        if self._food_ready(snapshot):
            return True
        food_store = (
            STORE_MAGIC
            if snapshot.player.food_type == FOOD_TYPE_MANA
            else STORE_GENERAL
        )
        return (
            food_store in self._town_store_attempted
            and not snapshot.player.hungry
        )

    def _fundraising_supplies_ready(self, snapshot: Snapshot) -> bool:
        scrolls_needed = self._mining_detection_scroll_target(snapshot)
        return (
            self._fundraising_food_ready(snapshot)
            and self._count_treasure_detection_scrolls(snapshot)
            >= scrolls_needed
            and self._has_digging_tool(snapshot)
        )

    def _mining_detection_scroll_target(self, snapshot: Snapshot) -> int:
        remaining_runs = max(
            0,
            self._effective_mining_run_target() - self._mining_runs_completed,
        )
        return remaining_runs

    def _fundraising_light_ready(self, snapshot: Snapshot) -> bool:
        """Whether level-one fundraising can start with a working light."""
        if self._expedition_light_ready(snapshot):
            return True
        return self._fundraising_wieldable_light(snapshot) is not None

    def _fundraising_wieldable_light(
        self, snapshot: Snapshot
    ) -> InventoryItem | None:
        """Return a carried light that can satisfy expedition readiness."""
        candidate = self._find_light(snapshot)
        if candidate is None:
            return None
        if candidate.known:
            return candidate if self._is_usable_light(candidate) else None
        if (
            candidate.is_lantern
            and not self._oil_below_departure_target(snapshot)
        ):
            return candidate
        return None

    def _fundraising_mining_requirements(
        self, snapshot: Snapshot
    ) -> tuple[int, int] | None:
        """Share the mining-only requirement targets with procurement."""
        if self._fundraising_mode not in {"prepare", "mine", "scavenge"}:
            return None
        return self._mining_detection_scroll_target(snapshot), 2

    def _affordable_star_remove_curse(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_TEMPLE:
            return None
        ware = next(
            (
                item for item in store.items
                if item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_STAR_REMOVE_CURSE
                and item.price <= snapshot.player.gold
            ),
            None,
        )
        if ware is not None:
            self._star_remove_curse_shelf_seen = True
        if (
            ware is None
            or self._star_remove_curse_reserve_buy_inflight is not None
            or (
                not self._has_unremovable_curse_target(snapshot)
                and not self._star_remove_curse_reserve_purchase_needed(snapshot)
            )
            or (
                self._has_unremovable_curse_target(snapshot)
                and bool(self._home_star_remove_curse_count)
            )
        ):
            return None
        return ware

    def _fundraising_departure_ready(self, snapshot: Snapshot) -> bool:
        player = snapshot.player
        base_ready = (
            self._fundraising_food_ready(snapshot)
            and self._fundraising_light_ready(snapshot)
            and player.hp >= player.max_hp
            and player.mp >= player.max_mp
            and self._temporary_status_clear(snapshot)
        )
        if not base_ready:
            return False
        if self._fundraising_mode == "mine":
            return self._fundraising_supplies_ready(snapshot)
        return True

    def _fundraising_combat_equipment_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if (
            self._fundraising_mode not in {"mine", "scavenge"}
            or snapshot.floor_key[0] != DUNGEON_YEEK_CAVE
            or snapshot.dungeon_level != 1
        ):
            return None
        active_adjacent = [
            monster for monster in hostiles
            if monster.distance <= 1 and not monster.asleep
        ]
        if self._equipped_digging_tool(snapshot) is not None:
            ranged = self._ranged_attack_key(snapshot, hostiles, active_adjacent)
            if ranged is not None:
                return ranged
        if (
            not active_adjacent
            or self._mining_combat_contact_streak < MINING_COMBAT_CONTACT_LIMIT
        ):
            return None
        restore = self._restore_mining_combat_hand_key(
            snapshot, "melee:restore-weapon"
        )
        if restore is not None:
            return restore
        return None

    def _update_mining_combat_streaks(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> None:
        """Advance mining re-arm hysteresis exactly once per decision."""
        mining = (
            self._fundraising_mode in {"mine", "scavenge"}
            and snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and snapshot.dungeon_level == 1
        )
        if not mining:
            self._mining_combat_contact_streak = 0
            self._mining_threat_free_streak = 0
            return
        if any(not monster.asleep for monster in adjacent):
            self._mining_combat_contact_streak += 1
            self._mining_threat_free_streak = 0
        elif not hostiles:
            self._mining_combat_contact_streak = 0
            self._mining_threat_free_streak += 1
        else:
            self._mining_combat_contact_streak = 0
            self._mining_threat_free_streak = 0

    def _leave_fundraising_floor(
        self, snapshot: Snapshot, *, allow_recall: bool = True
    ) -> str:
        player = snapshot.player
        if allow_recall and snapshot.dungeon_level >= RECALL_MIN_DEPTH:
            if player.recalling:
                self.last_reason = "fundraise:wait-recall"
                return WAIT_KEY
            recall = self._find_recall_scroll(snapshot)
            if (
                recall is not None
                and not player.blind
                and not player.confused
                and self._can_read_scrolls(snapshot)
            ):
                self.last_reason = "fundraise:recall"
                return self._read_key(snapshot, recall)
        here = snapshot.grid_at(player.position)
        if here is not None and self._is_upstairs_target(here):
            self.last_reason = "fundraise:ascend"
            return UP_STAIRS_KEY
        # The remembered route to a distant staircase can change as mining
        # reveals terrain, making BFS alternate between two equally short first
        # steps at a junction.  Break that confined cycle before asking BFS for
        # the same step again; the next decision resumes the staircase route.
        oscillation_cells = set(self._recent) if self._is_oscillating() else set()
        if oscillation_cells:
            step = self._least_visited_neighbor(snapshot)
            if step is not None and step not in oscillation_cells:
                self.last_reason = "fundraise:seek-upstairs"
                return self._step_toward(snapshot, step)
        step = self._nearest_goal_step(snapshot, self._is_upstairs_target)
        if step is not None:
            self.last_reason = "fundraise:seek-upstairs"
            return self._step_toward(snapshot, step)
        blocker = self._blocking_escape_melee_key(
            snapshot, self._physical_hostiles(snapshot), self._is_upstairs_target
        )
        if blocker is not None:
            self.last_reason = "fundraise:clear-escape-path"
            return blocker
        upstairs_search_expired = self._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
        if upstairs_search_expired and allow_recall:
            recall = self._find_recall_scroll(snapshot)
            if (
                recall is not None
                and not player.blind
                and not player.confused
                and self._can_read_scrolls(snapshot)
            ):
                self._stuck_escape_streak = 0
                self._returning_to_town = True
                self.last_reason = "fundraise:recall-stuck"
                return self._read_key(snapshot, recall)
        else:
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "fundraise:seek-upstairs-explore"
                return self._step_toward(snapshot, step)
            if self._is_oscillating():
                step = self._probe_unknown_step(snapshot)
                if step is not None:
                    self.last_reason = "fundraise:probe"
                    return self._step_toward(snapshot, step)
                here_key = (snapshot.player.position.y, snapshot.player.position.x)
                if self._search_counts[here_key] < SEARCH_LIMIT:
                    self._search_counts[here_key] += 1
                    self.last_reason = "fundraise:search"
                    return SEARCH_KEY
            step = self._least_visited_neighbor(snapshot)
            if step is not None and (
                not oscillation_cells or step not in oscillation_cells
            ):
                self.last_reason = "fundraise:seek-upstairs-wander"
                return self._step_toward(snapshot, step)
        # Terminal: no reachable up-stairs, nothing to explore, and no walkable
        # neighbour that escapes a confined cycle (a mining tunnel can wall us into a
        # pocket). A miner DIGS out rather
        # than spending a scarce Teleport/Recall scroll — tunnel toward the nearest known
        # up-stairs, or failing that toward the nearest remembered floor (back the way we
        # dug in). Survival escapes are handled upstream, before fundraising.
        if not player.blind and not player.confused:
            goal = self._nearest_upstairs(snapshot)
            if goal is None:
                goal = self._nearest_remembered_floor(snapshot)
            if goal is not None:
                dig = self._tunnel_step_toward(snapshot, goal)
                if dig is not None:
                    self.last_reason = "fundraise:tunnel-out"
                    return dig
        self.last_reason = "fundraise:upstairs-not-found"
        return WAIT_KEY

    def _tunnel_step_toward(self, snapshot: Snapshot, target: Position) -> str | None:
        """Tunnel one step toward ``target`` through an adjacent diggable wall/vein.

        A miner reaches a walled-off vein by digging, not by relocating — so when
        the walk pathfinder is bouncing (oscillating) we dig straight at the vein
        instead of burning a scarce Teleport scroll. Prefer the direct (diagonal)
        approach, then its cardinal components, taking the first diggable neighbour
        that heads toward the target. Returns None when no adjacent cell in a useful
        direction can be dug (the caller then gives up and ascends)."""
        pos = snapshot.player.position
        dy = max(-1, min(1, target.y - pos.y))
        dx = max(-1, min(1, target.x - pos.x))
        candidates: list[tuple[int, int]] = []
        if dy or dx:
            candidates.append((dy, dx))
        if dx:
            candidates.append((0, dx))
        if dy:
            candidates.append((dy, 0))
        for cy, cx in candidates:
            cell = snapshot.grids.get(Position(pos.y + cy, pos.x + cx))
            if (
                cell is not None
                and cell.can_dig
                and cell.position not in self._mining_unmarkable_grids
            ):
                return self._mining_tunnel_key(snapshot, cell.position)
        return None

    def _mining_tunnel_key(
        self,
        snapshot: Snapshot,
        grid_position: Position,
        *,
        vein: Position | None = None,
    ) -> str | None:
        """Mark an adjacent mining wall before issuing Hengband's tunnel key."""
        if grid_position in self._mining_unmarkable_grids:
            return None
        grid = snapshot.grids.get(grid_position)
        if grid is None or not grid.tunnel or grid.enterable:
            return None
        direction = self._direction_key(snapshot.player.position, grid_position)
        if grid.marked:
            self._mining_mark_bumps.pop(grid_position, None)
            return TUNNEL_KEY + direction

        self._mining_mark_bumps[grid_position] += 1
        if self._mining_mark_bumps[grid_position] >= DIGGER_WIELD_LIMIT:
            self._mining_mark_bumps.pop(grid_position, None)
            self._mining_unmarkable_grids.add(grid_position)
            if vein is not None:
                self._drop_mining_vein(vein)
            return None
        self.last_reason = "fundraise:dig-mark-bump"
        return direction

    def _dig_to_known_downstairs_key(self, snapshot: Snapshot) -> str | None:
        """Route toward a known descent, allowing only known diggable terrain."""
        origin = snapshot.player.position
        targets = set(self._remembered_downstairs)
        targets.update(
            grid.position for grid in snapshot.grids.values() if grid.has_down_stairs
        )
        targets.discard(origin)
        if not targets:
            return None

        # Walking always wins.  This breakout is solely for stairs whose known
        # approach requires at least one vein to be tunnelled.
        if self._nearest_goal_step(snapshot, lambda grid: grid.position in targets):
            return None

        seen = {origin}
        queue: deque[tuple[Position, Position | None]] = deque([(origin, None)])
        while queue:
            position, first = queue.popleft()
            if position in targets and position != origin:
                assert first is not None
                first_grid = snapshot.grids.get(first)
                if first_grid is not None and first_grid.can_dig:
                    return self._tunnel_step_toward(snapshot, first)
                return self._step_toward(snapshot, first)
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if (
                    neighbor in seen
                    or neighbor in self._mining_unmarkable_grids
                    # Avoided cells carry lethal-danger weight in every
                    # routing BFS; a dig-breakout route walking one would
                    # repeat _step_toward's refusal forever on this static
                    # floor.
                    or neighbor in self._engagement_avoid_cells
                ):
                    continue
                grid = snapshot.grids.get(neighbor)
                if grid is None or not grid.known or grid.has_monster:
                    continue
                walkable = neighbor in self._walkable_neighbors(snapshot, position)
                # Match the mining tunneller's terrain authority.  Digging is
                # permitted diagonally when the emitter marks that tile can_dig.
                if not walkable and not grid.can_dig:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, neighbor if first is None else first))
        return None

    def _dig_reachable_goal_and_step(
        self, snapshot: Snapshot, goals: set[Position]
    ) -> tuple[Position, Position] | None:
        """Return the nearest goal and first step through floor, tunnels, or fog.

        Detection bounds the optimistic unseen search: cells outside every
        detection radius cannot contain one of this mining pass's targets and
        must not provide an infinite route around known permanent rock.
        """
        if not goals:
            return None
        start = snapshot.player.position
        centers = self._mining_detection_centers or [start]
        seen = {start}
        queue: deque[tuple[Position, Position | None, int]] = deque(
            [(start, None, 0)]
        )
        while queue:
            position, first, distance = queue.popleft()
            if position in goals and position != start:
                assert first is not None
                self._mining_target_distance = distance
                return position, first
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if (
                    neighbor in seen
                    or neighbor in self._engagement_avoid_cells
                    or neighbor in self._mining_unmarkable_grids
                    or not snapshot.in_bounds(neighbor)
                    or all(
                        neighbor.distance_to(center)
                        > MINING_DETECTION_RADIUS
                        for center in centers
                    )
                ):
                    continue
                grid = snapshot.grids.get(neighbor)
                if grid is None and (snapshot.width <= 0 or snapshot.height <= 0):
                    # Legacy/synthetic snapshots without map dimensions cannot
                    # bound an optimistic fog search. Treat absent cells as
                    # outside their represented map.
                    continue
                if grid is not None and grid.known:
                    if grid.permanent or grid.has_monster:
                        continue
                    if not (grid.enterable or grid.tunnel):
                        continue
                seen.add(neighbor)
                queue.append(
                    (
                        neighbor,
                        neighbor if first is None else first,
                        distance + 1,
                    )
                )
        return None

    def _mining_closure_key(self, snapshot: Snapshot) -> str:
        """Collect or permanently drop every detected target on this floor."""
        if self._mining_sweep_steps >= MINING_SWEEP_HARD_LIMIT:
            result = self._finish_mining_floor(snapshot)
            self.last_reason = "fundraise:mining-hard-limit"
            return result

        centers = self._mining_detection_centers
        targets = {
            target
            for target in self._known_treasure - self._mining_dropped_veins
            if not centers
            or any(
                target.distance_to(center) <= MINING_DETECTION_RADIUS
                for center in centers
            )
        }
        while targets:
            previous_distance = self._mining_target_distance
            route = self._dig_reachable_goal_and_step(snapshot, targets)
            if route is None:
                for target in targets:
                    self._drop_mining_vein(target)
                self._treasure_target = None
                self._mining_stall_turns = 0
                return self._finish_mining_floor(snapshot)
            target, step = route
            distance = self._mining_target_distance
            step_grid = snapshot.grids.get(step)
            step_is_dig = (
                step_grid is not None
                and step_grid.known
                and step_grid.tunnel
                and not step_grid.enterable
            )
            if target != self._treasure_target:
                self._treasure_target = target
                self._mining_stall_turns = 0
                self._mining_target_revealed_grids = len(snapshot.grids)
                self._mining_target_collected = self._mining_veins_collected
                previous_distance = None
            # Actively tunnelling a hard but reachable tile is forward progress
            # even though position, revealed grids, and collection are unchanged;
            # only a non-digging navigation stall may burn the per-target leash.
            # The global MINING_SWEEP_HARD_LIMIT backstop still bounds a tile that
            # never breaks through.
            progressed = (
                step_is_dig
                or previous_distance is None
                or (distance is not None and distance < previous_distance)
                or len(snapshot.grids) > self._mining_target_revealed_grids
                or self._mining_veins_collected > self._mining_target_collected
            )
            if progressed:
                self._mining_stall_turns = 0
            else:
                self._mining_stall_turns += 1
            self._mining_target_revealed_grids = max(
                self._mining_target_revealed_grids, len(snapshot.grids)
            )
            self._mining_target_collected = self._mining_veins_collected
            if self._mining_stall_turns >= MINING_STALL_LIMIT:
                self._drop_mining_vein(target)
                self._treasure_target = None
                self._mining_target_distance = None
                self._mining_stall_turns = 0
                targets.discard(target)
                continue

            self._mining_sweep_steps += 1
            if step_is_dig:
                self.last_reason = "fundraise:dig-to-treasure"
                key = self._mining_tunnel_key(snapshot, step, vein=target)
                if key is not None:
                    return key
                self._treasure_target = None
                self._mining_target_distance = None
                targets.discard(target)
                continue
            self.last_reason = "fundraise:seek-treasure"
            return self._step_toward(snapshot, step)

        return self._finish_mining_floor(snapshot)

    def _mining_sweep_step(self, snapshot: Snapshot) -> Position | None:
        """One exploration step inside the detected area (phase 1 of the user's
        mining design): mapping the area first gives every cheap vein a known
        walkable approach, so the collection walk can actually reach it. None
        means that no in-radius frontier remains; transient oscillation is a
        caller-managed pause, not completion."""
        centers = self._mining_detection_centers
        if not centers:
            return None
        result = self._nearest_goal_and_step(
            snapshot,
            lambda grid: grid.position not in self._mining_swept_dead_targets
            and self._is_frontier(snapshot, grid)
            and any(
                grid.position.distance_to(center)
                <= MINING_DETECTION_RADIUS
                for center in centers
            ),
        )
        if result is None:
            self._mining_sweep_goal = None
            self._mining_sweep_goal_distance = None
            return None
        goal, step = result
        if goal != self._mining_sweep_goal:
            self._mining_sweep_goal_distance = None
        self._mining_sweep_goal = goal
        return step

    def _record_mining_sweep_step(self, snapshot: Snapshot) -> None:
        """Account for one sweep move without spending the collection leash."""
        self._mining_sweep_steps += 1
        revealed = len(snapshot.grids)
        goal = self._mining_sweep_goal
        distance = (
            snapshot.player.position.distance_to(goal) if goal is not None else None
        )
        approached_goal = (
            goal is not None
            and self._mining_sweep_goal_distance is not None
            and distance < self._mining_sweep_goal_distance
        )
        if revealed > self._mining_sweep_revealed_grids or approached_goal:
            self._mining_sweep_no_progress = 0
        else:
            self._mining_sweep_no_progress += 1
        self._mining_sweep_goal_distance = distance
        self._mining_sweep_revealed_grids = max(
            self._mining_sweep_revealed_grids, revealed
        )
        if (
            self._mining_sweep_no_progress >= MINING_SWEEP_NO_PROGRESS_LIMIT
            or self._mining_sweep_steps >= MINING_SWEEP_HARD_LIMIT
        ):
            self._mining_sweep_done = True
            self._mining_grids_at_sweep_done = max(
                len(snapshot.grids), self._mining_sweep_revealed_grids
            )

    def _mining_tapped_out_key(self, snapshot: Snapshot) -> str:
        """No distance-1 vein is reachable right now. Mining opens new floor, so
        first resume the sweep if fresh in-radius frontiers appeared (a dug vein
        chain can unseal a whole pocket); once neither a vein nor a frontier
        remains, the cheap treasure really is collected and the floor is done."""
        was_done = self._mining_sweep_done
        self._mining_sweep_revealed_grids = max(
            self._mining_sweep_revealed_grids, len(snapshot.grids)
        )
        if self._is_oscillating():
            # Waiting cannot drain _recent: choose_key appends our unchanged
            # position on every decision, so a stationary pause would keep the
            # oscillation predicate true forever.  Drop the stale combat jitter
            # and let the resumed sweep make a real move below.
            self._recent.clear()
        sweep = self._mining_sweep_step(snapshot)
        if sweep is not None:
            if (
                was_done
                and self._mining_grids_at_sweep_done > 0
                and self._mining_sweep_revealed_grids
                <= self._mining_grids_at_sweep_done
            ):
                # The sweep finished and NOTHING has been exposed since (no
                # vein was dug, no new floor revealed): resuming would re-run
                # the exact sweep that just dead-ended — the observed
                # done→resume macro-cycle that bounced a junction until the
                # loop guard stopped the bot. The cheap treasure here is
                # done; leave for a fresh floor instead.
                self._mining_stall_turns = MINING_STALL_LIMIT
                return self._finish_mining_floor(snapshot)
            self._mining_sweep_done = False
            if was_done:
                self._reset_mining_sweep_progress(snapshot)
                # The reset clears the freshly selected goal; select it again.
                sweep = self._mining_sweep_step(snapshot)
                assert sweep is not None
            self._record_mining_sweep_step(snapshot)
            self.last_reason = "fundraise:sweep-explore"
            return self._step_toward(snapshot, sweep)
        self._mining_stall_turns = MINING_STALL_LIMIT
        return self._finish_mining_floor(snapshot)

    def _fundraising_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if self._fundraising_mode not in {"mine", "scavenge"}:
            return None
        if snapshot.in_town and self._calibration_active():
            # The unequipped calibration phase owns the town while it runs.
            # Fundraising town work (kit purchases, departure) would feed the
            # calibration deposit loop its own purchases; it resumes untouched
            # once the phase releases the town.
            return None
        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and snapshot.dungeon_level != 1
        ):
            self._returning_to_town = True
            return self._return_to_town_key(snapshot, hostiles)
        if (
            snapshot.floor_key[0] != DUNGEON_YEEK_CAVE
            or snapshot.dungeon_level != 1
        ):
            return None
        mining_hostiles = self._physical_hostiles(snapshot)
        combat_equip = self._fundraising_combat_equipment_key(
            snapshot, mining_hostiles
        )
        if combat_equip is not None:
            return combat_equip
        if self._breeder_breakthrough_floor == snapshot.floor_key:
            return self._finish_mining_floor(snapshot)
        if (
            self._returning_to_town
            or self._should_start_town_return(snapshot)
        ):
            # Fundraising normally owns dungeon movement before the generic
            # town-return router.  Once an emergency latches a return, or normal
            # supply accounting says the expedition is exhausted, continuing a
            # remembered multiplier pursuit shadows that router: the bot walks
            # back into the same swarm after every teleport.  Drop the stale
            # combat destination and let the fundraising floor-exit procedure
            # carry out the return.
            self._returning_to_town = True
            return self._leave_fundraising_floor(snapshot)
        if (
            snapshot.player.gold >= FUNDRAISING_GOLD_TARGET
            and (
                self._fundraising_mode == "scavenge"
                or not self._known_treasure
            )
        ):
            self._returning_to_town = True
            return self._leave_fundraising_floor(snapshot)

        no_food_left = self._find_edible(snapshot) is None and snapshot.player.food_state not in {
            "full",
            "gorged",
        }
        if no_food_left:
            return self._leave_fundraising_floor(snapshot)
        if not self._expedition_light_ready(snapshot):
            light = self._fundraising_wieldable_light(snapshot)
            if light is None:
                return self._leave_fundraising_floor(snapshot)
            self.last_reason = "fundraise:wield-light"
            return self._equipment_wield(
                snapshot, "light-loadout", light, "light"
            )

        if snapshot.player.hungry:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "fundraise:eat"
                return EAT_KEY + food.slot

        refill = self._light_refill_item(snapshot)
        if refill is not None:
            self.last_reason = "fundraise:refill-light"
            return REFILL_KEY + refill.slot

        if self._escape_state.owner == "disengage":
            # A declared walk-out owns movement until EscapeState releases it.
            # Adjacent combat has already run in _decide, so yielding here still
            # permits bump-attacking a blocker while preventing multiplier,
            # loot, mining, and exploration routes from pulling against the
            # disengage direction.
            return None
        multipliers = [monster for monster in hostiles if monster.can_multiply]
        if multipliers:
            target = min(multipliers, key=lambda monster: monster.distance)
            self._multiplier_target = target.position
            self._multiplier_target_grace = 10
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.position.distance_to(target.position) <= 1,
            )
            if step is not None:
                self.last_reason = "fundraise:eliminate-multiplier"
                return self._step_toward(snapshot, step)
        elif self._multiplier_target is not None and self._multiplier_target_grace:
            self._multiplier_target_grace -= 1
            if snapshot.player.position == self._multiplier_target:
                self._multiplier_target = None
                self._multiplier_target_grace = 0
            else:
                step = self._nearest_goal_step(
                    snapshot,
                    lambda grid: grid.position == self._multiplier_target,
                )
                if step is not None:
                    self.last_reason = "fundraise:eliminate-multiplier-last-seen"
                    return self._step_toward(snapshot, step)
        # Do not chase distant weak monsters during a fundraising run. Global
        # survival handling already escaped dangerous threats and normal melee
        # already attacked adjacent ones; hunting here makes the bot alternate
        # between a flickering monster and its treasure target.

        current_loot = self._current_floor_item_key(
            snapshot,
            pickup_reason="fundraise:pickup",
            trigger_reason="fundraise:trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot

        visible_loot_step = None
        if len(snapshot.inventory) < PACK_CAPACITY:
            # Mined gold piles inherit Hengband's `unsafe` cave flag even when no
            # monster is visible. Survival and adjacent combat have already run,
            # so do not leave those drops behind merely because of that flag.
            visible_loot_step = self._loot_step(snapshot, include_unsafe=True)

        # A floor item is already realised value. Collect the nearest reachable
        # one before detecting, mining, or exploring for another vein.
        if visible_loot_step is not None:
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_navigation_visits.clear()
            self._mining_oscillation_retargets = 0
            self.last_reason = "fundraise:seek-loot"
            return self._step_toward(snapshot, visible_loot_step)

        if self._fundraising_mode == "scavenge":
            if len(snapshot.inventory) >= PACK_CAPACITY:
                return self._leave_fundraising_floor(snapshot)
            if (
                not self._has_digging_tool(snapshot)
                and self._count_treasure_detection_scrolls(snapshot) > 0
                and bool(self._known_treasure)
            ):
                # This is a recoverable mining run with its tool left in town,
                # not a loot-only poverty run. Return and let the town plan
                # withdraw/buy the tool instead of walking past known veins.
                self._returning_to_town = True
                return self._leave_fundraising_floor(snapshot)
            if self._is_oscillating():
                # Loot-only exploration can exhaust the useful frontier while
                # a stale committed path keeps circling a small open pocket.
                # Mining has its own oscillation recovery, but scavenging used
                # to continue until the broader CLI loop guard stopped the bot.
                # Treat the floor as spent and hand the still-populated recent
                # cycle to the exit router, which prefers a known staircase or
                # a least-visited step outside the cycle.
                self._returning_to_town = True
                self._clear_explore_path(ExplorationPathOutcome.ABANDON)
                return self._leave_fundraising_floor(snapshot)
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "fundraise:scavenge"
                return self._step_toward(snapshot, step)
            return self._leave_fundraising_floor(snapshot)

        desired_diggers = min(2, self._digging_tool_count(snapshot))
        equipped_diggers = sum(
            1 for item in snapshot.equipment if item.is_digging_tool
        )
        if equipped_diggers < desired_diggers:
            # Do not oscillate weapon<->digger around a wandering monster.
            # Re-enter the mining loadout only after the same bounded quiet
            # streak used by the wield transaction has elapsed.
            if self._mining_threat_free_streak < MINING_THREAT_FREE_LIMIT:
                return None
            if not self._has_digging_tool(snapshot):
                self._town_blocked_reason = "digging-tool-lost"
                self.last_reason = "fundraise:digging-tool-lost"
                return WAIT_KEY
            # Backstop: the wield below normally takes on the first try (answering the
            # hand prompt when needed). If it still keeps not taking — a genuinely stuck
            # or cursed main weapon that cannot be removed — mining is impossible, so
            # abandon the run and leave rather than re-issuing the wield until the loop
            # guard stops the bot.
            wield = self._wield_digging_tool_key(
                snapshot, "fundraise:wield-digging-tool"
            )
            if wield is None:
                report = self._equipment_mutation_result.report
                if report is not None:
                    # Supersession keeps mining on the current loadout.  An
                    # unobserved post retries this same ladder without taking
                    # ownership away from unrelated town/floor work.
                    self.last_reason = report
                    if (
                        report != "goal-already-superseded"
                        and self._digger_wield_attempts >= DIGGER_WIELD_LIMIT
                    ):
                        self._digger_wield_attempts = 0
                        self._fundraising_mode = None
                        leave = self._leave_fundraising_floor(snapshot)
                        self.last_reason = "fundraise:abandon-unwieldable-digger"
                        return leave
                    return None
                self._fundraising_mode = None
                return self._leave_fundraising_floor(snapshot)
            return wield
        self._digger_wield_attempts = 0

        needs_initial_detection = self._mining_scroll_used_floor != snapshot.floor_key
        if needs_initial_detection:
            scroll = self._first_item(
                snapshot, lambda it: it.is_treasure_detection_scroll
            )
            if scroll is None:
                # Out of treasure-detection scrolls: return to town to restock
                # rather than WAIT on the mining floor forever (the loop detector
                # then stops the bot). Leaving clears any town block on the floor
                # change, and the town purchase logic re-buys the scrolls before
                # the next mining run.
                if needs_initial_detection:
                    return self._leave_fundraising_floor(snapshot)
            else:
                self._mining_scroll_used_floor = snapshot.floor_key
                self._mining_detection_centers.append(snapshot.player.position)
                # Fresh detection = a fresh sweep of the (extended) area and a
                # fresh chance for veins whose walk failed before.
                self._mining_sweep_done = False
                if needs_initial_detection:
                    self._mining_viability_pending_floor = snapshot.floor_key
                self._reset_mining_sweep_progress(snapshot)
                self._mining_swept_dead_targets.clear()
                self._mining_grids_at_sweep_done = 0
                self._mining_dropped_veins.clear()
                self._mining_mark_bumps.clear()
                self._mining_unmarkable_grids.clear()
                self.last_reason = "fundraise:detect-treasure"
                return self._read_key(snapshot, scroll)

        # The detection command's snapshot does not contain its effect yet.  Assess
        # exactly once on the following decision, after _observe has incorporated
        # the revealed veins, and reroll a clear dry outlier before paying for the
        # thorough radius sweep.  Dropped veins are excluded for consistency with
        # the phase-2 yield accounting (normally this set is empty after detection).
        if self._mining_viability_pending_floor == snapshot.floor_key:
            self._mining_viability_pending_floor = None
            detected_total = len(self._known_treasure - self._mining_dropped_veins)
            has_spare_detection_scroll = (
                self._count_treasure_detection_scrolls(snapshot)
                > self._mining_detection_scroll_target(snapshot)
            )
            if detected_total == 0:
                self._mining_stall_turns = MINING_STALL_LIMIT
                return self._finish_mining_floor(snapshot)
            if (
                detected_total <= BARREN_FLOOR_SKIP_THRESHOLD
                and has_spare_detection_scroll
            ):
                self._mining_stall_turns = MINING_STALL_LIMIT
                key = self._finish_mining_floor(snapshot)
                self.last_reason = "fundraise:skip-barren-floor"
                return key

        # Loot, equipment, detection, and combat remain handled above. Consume
        # the detected set itself as one dig-aware reachable-treasure closure.
        return self._mining_closure_key(snapshot)

        adjacent_gold = min(
            (
                grid
                for grid in snapshot.grids.values()
                if grid.has_gold
                and snapshot.player.position.distance_to(grid.position) == 1
            ),
            key=lambda grid: (
                abs(snapshot.player.position.y - grid.position.y)
                + abs(snapshot.player.position.x - grid.position.x)
                != 1,
                grid.position.y,
                grid.position.x,
            ),
            default=None,
        )
        if self._mining_sweep_done:
            self._mining_sweep_revealed_grids = max(
                self._mining_sweep_revealed_grids, len(snapshot.grids)
            )
        # Floor loot is handled above before chasing
        # veins — it is walkable gold we would otherwise leave behind.
        # Productivity leash: MINING_STALL_LIMIT turns with no gold collected means the
        # remaining veins are effectively out of reach — leave for a fresh floor. Not reset
        # here, so once tripped we keep heading out (still grabbing any adjacent gold / loot
        # above on the way) until we collect again or change floor.
        if (
            self._mining_stall_turns >= MINING_STALL_LIMIT
            and adjacent_gold is None
        ):
            return self._finish_mining_floor(snapshot)
        # Phase 1 (user design): SWEEP the detected area before collecting — map
        # the terrain so every cheap vein gains a known walkable approach
        # (upstream steps already killed monsters and grabbed loot on the way).
        # The old routine skipped this and burned its leash tunneling toward one
        # deep vein, leaving most of the detection uncollected.
        if not self._mining_sweep_done:
            oscillating = self._is_oscillating()
            sweep = self._mining_sweep_step(snapshot)
            if oscillating and self._mining_sweep_goal is not None:
                goal = self._mining_sweep_goal
                position = snapshot.player.position
                oscillation_cells = set(self._recent)
                self._mining_sweep_escape_pairs.append((position, goal))
                escape_goals = {
                    escape_goal
                    for _, escape_goal in self._mining_sweep_escape_pairs
                }
                # A frontier that retargets to a cell in the stationary output
                # cycle (especially the adjacent tile just left) is view flicker,
                # not exploration. The three-escape fallback also catches an
                # alternating pair just outside the sampled position set.
                flickering = goal in oscillation_cells
                repeated_small_set = (
                    len(self._mining_sweep_escape_pairs) == 3
                    and len(escape_goals) <= 2
                )
                if flickering or repeated_small_set:
                    self._mining_swept_dead_targets.update(escape_goals)
                    sweep = self._mining_sweep_step(snapshot)
                # Keep the evidence while the replacement route still takes
                # us through the same output cycle.  Clearing it here made
                # each bad frontier consume another full STUCK_WINDOW; the
                # CLI's broader 40-decision guard could stop the bot before
                # phase 1 blacklisted enough flickering goals to escape.
                if sweep is None or sweep not in oscillation_cells:
                    self._recent.clear()
            if sweep is not None:
                self._record_mining_sweep_step(snapshot)
                self.last_reason = "fundraise:sweep-explore"
                return self._step_toward(snapshot, sweep)
            self._mining_sweep_done = True
            self._mining_grids_at_sweep_done = self._mining_sweep_revealed_grids
        # Phase 2: collect distance-1 veins (walk to a floor tile beside the
        # vein, dig it directly) until none qualify. A dug vein becomes floor,
        # which can expose the vein behind it — the walk picks that up next
        # iteration, peeling whole clusters without ever digging blank rock.
        if adjacent_gold is not None:
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_navigation_visits.clear()
            self._mining_oscillation_retargets = 0
            self.last_reason = "fundraise:mine-treasure"
            key = self._mining_tunnel_key(
                snapshot, adjacent_gold.position, vein=adjacent_gold.position
            )
            if key is not None:
                return key
        osc = self._is_oscillating()
        if osc and self._treasure_target is not None:
            self._mining_oscillation_retargets += 1
            self._drop_mining_vein(self._treasure_target)
            self._treasure_target = None
            self._mining_route_visits.clear()
            if (
                self._mining_oscillation_retargets
                >= MINING_OSCILLATION_RETARGET_LIMIT
            ):
                self._mining_stall_turns = MINING_STALL_LIMIT
                return self._finish_mining_floor(snapshot)
            self._recent.clear()
            osc = False
        if not osc:
            step = self._treasure_step(snapshot)
            if step is not None:
                if self._mining_navigation_stalled(snapshot):
                    return self._finish_mining_floor(snapshot)
                self._mining_route_visits[snapshot.player.position] += 1
                if (
                    self._mining_route_visits[snapshot.player.position]
                    >= MINING_ROUTE_REVISIT_LIMIT
                ):
                    failed_target = self._treasure_target
                    if failed_target is not None:
                        self._drop_mining_vein(failed_target)
                    self._treasure_target = None
                    self._mining_route_visits.clear()
                    step = self._treasure_step(snapshot)
                    if step is not None:
                        self.last_reason = "fundraise:seek-treasure"
                        return self._step_toward(snapshot, step)
                    return self._mining_tapped_out_key(snapshot)
                self._mining_stall_turns += 1
                self.last_reason = "fundraise:seek-treasure"
                return self._step_toward(snapshot, step)
        # No distance-1 vein is walkable-reachable. Never tunnel through blank
        # rock toward a far vein — the user's design trades those few for
        # reliably collecting every cheap one before leaving.
        return self._mining_tapped_out_key(snapshot)

    def _mining_navigation_stalled(self, snapshot: Snapshot) -> bool:
        position = snapshot.player.position
        self._mining_navigation_visits[position] += 1
        if (
            self._mining_navigation_visits[position]
            < MINING_NAVIGATION_REVISIT_LIMIT
        ):
            return False
        self._mining_stall_turns = MINING_STALL_LIMIT
        return True

    def _secret_wall_search_step(self, snapshot: Snapshot) -> Position | None:
        candidates = {
            Position(y, x)
            for y, x in self._remembered_floor_t
            if self._undersearched_walls(Position(y, x))
        }
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None, int]] = deque(
            [(start, None, 0)]
        )
        best: tuple[tuple[int, int, int, int], Position] | None = None
        while queue:
            pos, first_step, distance = queue.popleft()
            if pos != start and pos in candidates and first_step is not None:
                # Secret exits are most likely at corridor ends. Prefer fewer
                # walkable neighbors before path distance so large room
                # perimeters do not consume the no-progress budget first.
                score = (
                    len(self._walkable_neighbors(snapshot, pos)),
                    distance,
                    pos.y,
                    pos.x,
                )
                if best is None or score < best[0]:
                    best = (score, first_step)
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
        return best[1] if best is not None else None
