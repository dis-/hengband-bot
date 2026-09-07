from __future__ import annotations

from collections import Counter, deque
from heapq import heappop, heappush
from itertools import count
from hengbot.loop_detection import LOOP_MAX_DISTINCT
from hengbot.policy_constants import (
    BARREN_FLOOR_SKIP_THRESHOLD,
    BREEDER_CONTAINMENT_WINDOW,
    CURE_CRITICAL_REQUIRED_DEPTH,
    FOOD_STOCK_TARGET,
    IDENTIFY_CHARGE_FLOOR,
    LANTERN_REFILL_FUEL,
    MANA_FOOD_DEVICE_TARGET,
    OIL_TARGET,
    QUEST_STATUS_UNTAKEN,
    STAFF_IDENTIFY_MAX_COUNT,
    STAFF_IDENTIFY_MIN_CHARGES,
    STAFF_IDENTIFY_MIN_DEPTH,
    SUMMONER_CHOKE_NEIGHBORS,
    SUPPLY_STORES,
    TELEPORT_REQUIRED_DEPTH,
    TORCH_REFILL_FUEL,
    BUY_KEY,
    CARDINAL_OFFSETS,
    CHARACTER_DUMP_MACRO,
    CHEST_COLLECT_BUDGET,
    CHEST_DISARM_BUDGET,
    CHEST_DISARM_KEY,
    CHEST_DROP_KEY,
    CHEST_OPEN_BUDGET,
    CHEST_OPEN_KEY,
    CHEST_SEARCH_BUDGET,
    CHEST_SEARCH_KEY,
    DIRECTION_KEYS,
    DOWN_STAIRS_KEY,
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    EQUIPMENT_TRANSACTION_FINAL_STOP_REASONS,
    EAT_KEY,
    ExplorationPathOutcome,
    FOOD_MIN_SVAL,
    FOOD_TYPE_MANA,
    FULL_IDENTIFY_DISMISS_SUFFIX,
    FUNDRAISING_GOLD_TARGET,
    FUNDRAISING_DETECTION_BASE_PRICE,
    FUNDRAISING_DIGGER_BASE_PRICE,
    FUNDRAISING_KIT_MARGIN,
    FUNDRAISING_KIT_RESERVE,
    IDENTIFY_FAIL_LIMIT,
    IDENTIFY_PRESSURE_FREE_SLOTS,
    LEAVE_STORE_KEY,
    LOOT_DEFER_BLOCKERS,
    LOOT_THREAT_DAMAGE_RATIO,
    DIGGER_WIELD_LIMIT,
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
    PROBE_LIMIT,
    RANGED_MAX_DISTANCE,
    READ_KEY,
    RECALL_MIN_DEPTH,
    REFILL_KEY,
    SEARCH_KEY,
    SEARCH_LIMIT,
    SELL_KEY,
    STAFF_IDENTIFY_MIN_SUCCESS,
    STORE_RESTOCK_WAIT_TURNS,
    STORE_STUCK_LIMIT,
    STUCK_ESCAPE_LIMIT,
    TERMINAL_NUDGE_LIMIT,
    TOWN_TRAVEL_STORE_SYMBOLS,
    TOWN_STOP_PASS_LIMIT,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    TUNNEL_KEY,
    UP_STAIRS_KEY,
    USE_STAFF_KEY,
    WAIT_KEY,
    ZAP_ROD_KEY,
)
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_CHAMELEON_CAVE,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    STORE_WEAPON,
    SV_LITE_LANTERN,
    SV_LITE_FEANOR,
    SV_LITE_TORCH,
    SV_POTION_SLEEP,
    SV_POTION_SPEED,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_RESIST_COLD,
    SV_SCROLL_PHASE_DOOR,
    SV_SCROLL_TELEPORT,
    RESTORE_POTION_SVAL_BY_STAT,
    STAT_GAIN_POTION_SVALS,
    SV_ROD_IDENTIFY,
    SV_ROD_LITE,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_DETECT_INVISIBLE,
    SV_SCROLL_DETECT_TRAP,
    SV_SCROLL_DETECT_ITEM,
    SV_SCROLL_DETECT_DOOR,
    SV_SCROLL_LIGHT,
    SV_SCROLL_BLESSING,
    SV_SCROLL_HOLY_CHANT,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    SV_SCROLL_STAR_REMOVE_CURSE,
    SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
    SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
    SV_SCROLL_STAR_DESTRUCTION,
    SV_SCROLL_WORD_OF_RECALL,
    SV_STAFF_DESTRUCTION,
    SV_STAFF_IDENTIFY,
    SV_WAND_STONE_TO_MUD,
    SV_WAND_TELEPORT_AWAY,
    SV_HAFTED_WIZSTAFF,
    SPELLBOOK_TVALS,
    TVAL_AMULET,
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_BOW,
    TVAL_BOOTS,
    TVAL_CROWN,
    TVAL_CLOAK,
    TVAL_SOFT_ARMOR,
    TVAL_HARD_ARMOR,
    TVAL_DRAG_ARMOR,
    TVAL_GLOVES,
    TVAL_HELM,
    TVAL_SHIELD,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_LIFE_BOOK,
    TVAL_CRUSADE_BOOK,
    TVAL_HISSATSU_BOOK,
    TVAL_POTION,
    TVAL_RING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_SHOT,
    TVAL_STAFF,
    TVAL_WAND,
    StoreState,
    TVAL_HAFTED,
    TVAL_POLEARM,
    TVAL_SWORD,
    TVAL_WHISTLE,
    TVAL_SPIKE,
    TVAL_FIGURINE,
    TVAL_STATUE,
    TVAL_CAPTURE,
    TVAL_CARD,
    TVAL_BOTTLE,
    TVAL_CHEST,
    GridState,
    InventoryItem,
    MonsterState,
    Position,
    QuestState,
    Snapshot,
    StoreItem,
    item_requires_full_identification,
)
from hengbot.policy import ExplorationGoalIdentity, ExplorationGoalKind
from hengbot.policy_constants import (
    BACKTRACK_PENALTY, DOOR_OPEN_LIMIT, EXTENDED_STUCK_WINDOW,
    NAV_ESCAPE_STEP_LIMIT, OPEN_KEY, RUBBLE_DIG_LIMIT, RUBBLE_REJECT_LIMIT,
    STAIR_OBSERVATION_WAIT_LIMIT, STUCK_WINDOW, VISIT_PENALTY,
)


class NavigationMixin:

    def _suppress_pending_stair_command(self, snapshot: Snapshot, key: str) -> str:
        """Post at most one floor-changing command per observation."""
        if (
            self._pending_stair_command is not None
            and key
            and key[0] in {UP_STAIRS_KEY, DOWN_STAIRS_KEY}
        ):
            # The sender can refuse a floor key after policy selection (for
            # example when its prompt owner no longer matches).  That refusal
            # releases the ordinary observation expectation: there is then no
            # posted effect for this older watch to await.  Enforce the same
            # ownership here, at the suppressor, so the stale watch cannot
            # turn every recovery re-post into an unbounded empty command.
            if self._owner_may_select(snapshot, "stair-command"):
                self._pending_stair_command = None
                self._stair_observation_waits = 0
                return key
            self._stair_observation_waits += 1
            if self._stair_observation_waits >= STAIR_OBSERVATION_WAIT_LIMIT:
                # A message-bearing acknowledgement followed by quiet copies
                # of the same board is not conclusive rejection, but it also
                # cannot own the executor forever.  Cross the same visible,
                # identity-breaking observation barrier used after a sender
                # refusal, then let routing either repost or abandon the stair.
                self._pending_stair_command = None
                self._stair_observation_waits = 0
                self._owner_expectations.release("stair-command")
                probe = self._look_probe_key(snapshot)
                self.last_reason = "stair:observation-timeout-probe"
                return probe
            self.last_reason = "stair:await-observation"
            return ""
        return key

    def _remember_stair_command(
        self, snapshot: Snapshot, key: str, *, observation: Snapshot | None = None
    ) -> None:
        """Retain a stair command until its result snapshot can verify it."""
        if not key or key[0] not in {UP_STAIRS_KEY, DOWN_STAIRS_KEY}:
            return
        direction = key[0]
        position = snapshot.player.position
        self._pending_stair_command = (
            direction,
            snapshot.floor_key,
            position,
            snapshot.turn,
            snapshot if observation is None else observation,
        )
        self._stair_observation_waits = 0
        self._post_owner_expectation(
            snapshot, "stair-command", "turn", "floor", "position"
        )

    def _cell_readable_if_stood(
        self, snapshot: Snapshot, position: Position
    ) -> bool | None:
        """Return the emitter visibility predicate, or unknown for old palettes."""
        grid = snapshot.grid_at(position)
        if (
            grid is None
            or not grid.currently_observed
            or not grid.visibility_flags_present
        ):
            return None
        return grid.lit or grid.mnlt or (
            grid.in_view and grid.glow and not grid.mndk and grid.allows_los
        )

    def _dark_locomotion_key(self, snapshot: Snapshot) -> str | None:
        """Move without light, then expose exhaustion as a visible stop."""
        if (
            snapshot.in_town
            or not self._is_dark(snapshot)
            # A present own cell is normal in darkness; grids_observed already
            # makes the removed legacy clause impossible.
            or self._light_refill_item(snapshot) is not None
            or self._darkness_torch(snapshot) is not None
        ):
            return None
    
        position = snapshot.player.position
        if (
            position in self._remembered_upstairs
            or (
                position in self._remembered_downstairs
                and not self._returning_to_town
            )
        ):
            self._clear_dark_route()
            return None
        self._blocked_unknown.difference_update(
            (visited.y, visited.x)
            for visited, count in self._visit_counts.items()
            if count > 0
        )
        if self._dark_route_expected is not None:
            if position != self._dark_route_expected:
                expected_grid = snapshot.grid_at(self._dark_route_expected)
                obstacle_attempt = expected_grid is not None and (
                    expected_grid.is_closed_door or expected_grid.is_rubble
                )
                if self._dark_route_goal is not None and not obstacle_attempt:
                    goal = self._dark_route_goal
                    self._dark_goal_counts[(goal.y, goal.x)] += 1
                self._clear_dark_route()
            else:
                self._dark_route.pop(0)
                self._dark_route_expected = None
                if not self._dark_route:
                    if self._dark_route_goal is not None:
                        goal = self._dark_route_goal
                        self._dark_goal_counts[(goal.y, goal.x)] += 1
                    self._clear_dark_route()
    
        if not self._dark_route:
            route = self._dark_route_to_frontier(snapshot)
            if route is not None:
                goal, path = route
                self._dark_route_goal = goal
                self._dark_route = path
        if self._dark_route:
            step = self._dark_route[0]
            self._dark_route_expected = step
            key = self._step_toward(snapshot, step)
            self.last_reason = "dark:backtrack"
            return key
    
        step = self._probe_unknown_step(snapshot)
        if step is not None:
            self._clear_explore_path(ExplorationPathOutcome.PAUSE)
            key = self._step_toward(snapshot, step)
            self.last_reason = "dark:probe"
            return key
    
        self.last_reason = "dark:locomotion-exhausted"
        return WAIT_KEY

    def _dark_walkable_neighbors(
        self, snapshot: Snapshot, position: Position
    ) -> list[Position]:
        """Walk remembered terrain plus cells physically occupied this floor."""
        trail = {
            visited
            for visited, count in self._visit_counts.items()
            if count > 0
        }
        trail.add(snapshot.player.position)
        neighbors = self._walkable_neighbors(snapshot, position)
        for dy, dx in NEIGHBOR_OFFSETS:
            neighbor = Position(position.y + dy, position.x + dx)
            if (
                neighbor in trail
                and neighbor not in neighbors
                and snapshot.in_bounds(neighbor)
            ):
                neighbors.append(neighbor)
        return neighbors

    def _dark_route_to_frontier(
        self, snapshot: Snapshot
    ) -> tuple[Position, list[Position]] | None:
        """Route across remembered floor and the bot's own dark walking trail."""
        start = snapshot.player.position
        queue: deque[tuple[Position, list[Position]]] = deque([(start, [])])
        seen = {start}
        candidates: list[tuple[tuple[int, int, int, int], Position, list[Position]]] = []
        while queue:
            position, path = queue.popleft()
            if position != start and path:
                yx = (position.y, position.x)
                remembered = yx in self._remembered_floor_t
                upstairs = position in self._remembered_upstairs
                downstairs = position in self._remembered_downstairs
                grid = snapshot.grid_at(position)
                frontier = grid is not None and self._is_frontier(snapshot, grid)
                if (
                    (remembered or upstairs or downstairs or frontier)
                    and self._dark_goal_counts[yx] < PROBE_LIMIT
                ):
                    kind = 0 if upstairs else 1 if downstairs else 2
                    readable = self._cell_readable_if_stood(snapshot, position)
                    readability_rank = 0 if readable else 1
                    walked_rank = 1
                    if snapshot.unsafe_rows is not None:
                        walked_rank = (
                            1 if snapshot.unsafe_rows[position.y][position.x] else 0
                        )
                    candidates.append(
                        (
                            (
                                kind, readability_rank, walked_rank,
                                len(path), position.y, position.x,
                            ),
                            position,
                            path,
                        )
                    )
            for neighbor in self._dark_walkable_neighbors(snapshot, position):
                if (
                    neighbor in seen
                    or neighbor in self._engagement_avoid_cells
                ):
                    continue
                seen.add(neighbor)
                queue.append((neighbor, [*path, neighbor]))
        if not candidates:
            return None
        _score, goal, path = min(candidates, key=lambda candidate: candidate[0])
        return goal, path

    def _dark_without_recovery(self, snapshot: Snapshot) -> bool:
        equipped = next(
            (
                item
                for item in getattr(snapshot, "equipment", ())
                if item.is_light
            ),
            None,
        )
        return (
            equipped is not None
            and equipped.is_lantern
            and not equipped.known
            and self._is_dark(snapshot)
            and self._light_refill_item(snapshot) is None
            and self._darkness_torch(snapshot) is None
        )

    def _dungeon_entry_allowed(
        self,
        snapshot: Snapshot,
        *,
        via_recall: bool,
        destination_depth: int,
    ) -> bool:
        """Enforce every invariant at the final town-to-dungeon boundary."""
        if (
            self._morivant_full_identify is not None
            and self._morivant_full_identify.temporary_deposits
        ):
            return False
        # This is an additional boundary invariant, including for the absolute
        # recall-stock mining walk-in exemption below.  A queued Home take owns
        # both native entrance travel and the final entry command until it is
        # confirmed or visibly released to the standing shop fallback.
        if (
            self._home_digger_withdraw_pending
            and not self._digger_fallback_bought_this_visit
        ):
            self._town_blocked_reason = "home-digger-withdraw-pending"
            return False
        mining_walk_in = (
            not via_recall
            and destination_depth == 1
            and self._active_dungeon_target() == DUNGEON_YEEK_CAVE
            and self._fundraising_mode in {"mine", "scavenge"}
        )
        if mining_walk_in:
            return True
        if not self._destination_depth_allowed(snapshot, destination_depth):
            return False
        # Recall, direct entrance confirmation, native entrance travel, and
        # fixed-quest entry share this boundary. Mining is the sole absolute
        # exception. Open wilderness is explicitly outside the town gate.
        if (
            snapshot.dungeon_level == 0
            and snapshot.in_town
            and not self._equipment_departure_ready(snapshot)
        ):
            self._departure_block = self._departure_block_state(snapshot)
            self._departure_block_sequence = self._decision_sequence
            if not self._departure_block.get("failed"):
                self._departure_block["failed"] = ["equipment_departure_ready"]
            if self._town_blocked_reason is None:
                self._town_blocked_reason = "equipment-departure-incomplete"
            return False
        recall = self._supply_ledger(snapshot, destination_depth)["recall"]
        return recall.count >= max(1, recall.required_return)

    def _dungeon_entry_depth(
        self, snapshot: Snapshot, dungeon_id: int, *, via_recall: bool
    ) -> int:
        dungeon = self._dungeon_knowledge.get(dungeon_id)
        if not via_recall:
            return max(1, dungeon.min_depth if dungeon is not None else 1)
        depth = snapshot.dungeon_recall_depths.get(dungeon_id, 0)
        if snapshot.recall_dungeon_id == dungeon_id:
            depth = max(depth, snapshot.recall_depth)
        if depth <= 0 and dungeon is not None:
            depth = dungeon.min_depth
        return max(1, depth)

    def _break_positional_oscillation(
        self, snapshot: Snapshot, key: str
    ) -> str:
        """Break a combat-interspersed small-cell navigation oscillation."""
        if self._breeder_breakthrough_floor == snapshot.floor_key:
            self._oscillation_outcome_marker = None
            self._osc_positions.clear()
            return key
        if snapshot.in_town or snapshot.store is not None:
            self._oscillation_outcome_marker = None
            return key
        self._osc_positions.append(snapshot.player.position)
    
        hostile_hp = {
            monster.index: monster.hp
            for monster in snapshot.visible_monsters
            if monster.hostile
        }
        quest_kills = tuple(
            sorted(
                (quest_id, quest.cur_num)
                for quest_id, quest in snapshot.quests.items()
            )
        )
        carried = tuple(
            sorted(
                (item.slot, item.name, item.count, item.charges)
                for item in (*snapshot.inventory, *snapshot.equipment)
            )
        )
        marker = (
            snapshot.player.gold,
            snapshot.player.exp,
            carried,
            hostile_hp,
            quest_kills,
        )
        previous = self._oscillation_outcome_marker
        self._oscillation_outcome_marker = marker
        hp_progress = bool(
            previous is not None
            and any(
                index in previous[3] and hp < previous[3][index]
                for index, hp in hostile_hp.items()
            )
        )
        kill_progress = bool(
            previous is not None
            and (
                snapshot.player.exp > previous[1]
                or any(
                    cur_num is not None
                    and (
                        previous_cur := dict(previous[4]).get(quest_id)
                    ) is not None
                    and cur_num > previous_cur
                    for quest_id, cur_num in quest_kills
                )
            )
        )
        inventory_progress = bool(
            previous is not None
            and (snapshot.player.gold != previous[0] or carried != previous[2])
        )
        fresh_cell = (
            self._position_changed
            and self._visit_counts[snapshot.player.position] <= 1
        )
        stationary_by_design = (
            self.last_reason == "fundraise:dig-to-treasure"
            or self.last_reason.startswith("fundraise:sweep-")
            or self.last_reason in {
                "quest-strategy:hold",
                "quest:blocked:hold",
                "rest",
                "recover",
            }
            or self.last_reason.endswith(":hold")
            or self.last_reason.endswith(":recover")
        )
        if (
            previous is None
            or fresh_cell
            or inventory_progress
            or hp_progress
            or kill_progress
            or stationary_by_design
        ):
            self._osc_positions.clear()
            return key
    
        recent = list(self._osc_positions)
        if len(recent) < EXTENDED_STUCK_WINDOW:
            return key
        confined = set(recent[-EXTENDED_STUCK_WINDOW:])
        position_changes = sum(
            first != second
            for first, second in zip(
                recent[-EXTENDED_STUCK_WINDOW:],
                recent[-EXTENDED_STUCK_WINDOW + 1 :],
            )
        )
        if (
            len(confined) > LOOP_MAX_DISTINCT
            or position_changes < STUCK_WINDOW
        ):
            return key
    
        self._loot_target = None
        self._close_store_visit("refused-with-evidence")
        self._descent_target_goal = None
        self._nav_ledger.clear_descent_route()
        self._clear_explore_path(ExplorationPathOutcome.ABANDON)
        origin = snapshot.player.position
        candidates = []
        for dy, dx in NEIGHBOR_OFFSETS:
            neighbor = Position(origin.y + dy, origin.x + dx)
            grid = snapshot.grid_at(neighbor)
            if (
                neighbor not in confined
                and grid is not None
                and grid.passable
                and not grid.is_door
                and not grid.has_monster
            ):
                candidates.append(neighbor)
        self._osc_positions.clear()
        if candidates:
            step = min(
                candidates,
                key=lambda candidate: (
                    self._visit_counts[candidate],
                    candidate.y,
                    candidate.x,
                ),
            )
            self.last_reason = "nav:break-oscillation"
            return self._step_toward(snapshot, step)
    
        # Let the existing bounded recall/upstairs/visible-stop escape own the
        # no-neighbor case on the immediately following livelock pass.
        self._nav_exhausted = True
        return key

    def _navigation_livelock_key(self, snapshot: Snapshot) -> str | None:
        """Leave (or visibly stop on) a floor where navigation is exhausted (R1).
    
        Fires only after NAV_NO_PROGRESS_LIMIT consecutive dungeon decisions
        with no new coverage, no target-distance improvement, no combat and no
        gold/pack/equipment change — the mode-independent definition of a
        livelock. The escape itself is bounded by NAV_ESCAPE_STEP_LIMIT; past
        that (or when quest locks forbid leaving) the policy reports
        livelock:exhausted, which the CLI treats as a visible stop.
        """
        if not self._nav_exhausted or snapshot.in_town:
            return None
        if self._window_edge_fallback_pending:
            self._window_edge_fallback_pending = False
            edge_path = self._window_edge_relocation_path(snapshot)
            if edge_path:
                self._window_edge_goals.add(edge_path[-1])
                self._explore_path = edge_path[1:]
                self._record_explore_goal(
                    snapshot,
                    ExplorationGoalKind.WINDOW_EDGE,
                    edge_path[-1],
                )
                self._nav_stall_count = 0
                self._nav_exhausted = False
                self._nav_escape_steps = 0
                self.last_reason = "livelock:seek-window-edge"
                return self._step_toward(snapshot, edge_path[0])
        player = snapshot.player
        if player.recalling:
            # The countdown will end the floor by itself; stand down.
            self._nav_exhausted = False
            self._nav_stall_count = 0
            return None
        quest_locked = (
            self._quest_floor_exit_locked(snapshot)
            or snapshot.floor_key[2] != 0
        )
        if not quest_locked and self._nav_escape_steps < NAV_ESCAPE_STEP_LIMIT:
            self._nav_escape_steps += 1
            if (
                not player.blind
                and not player.confused
                and self._can_read_scrolls(snapshot)
            ):
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    self._returning_to_town = True
                    self.last_reason = "livelock:recall-escape"
                    return self._read_dungeon_recall_scroll_key(snapshot, recall)
            here = snapshot.grid_at(player.position)
            if here is not None and self._is_upstairs_target(here):
                self._defer_descent(snapshot)
                self.last_reason = "livelock:ascend"
                return UP_STAIRS_KEY
            step = self._nearest_goal_step(snapshot, self._is_upstairs_target)
            if step is not None:
                self.last_reason = "livelock:seek-upstairs"
                return self._step_toward(snapshot, step)
            if (
                self._returning_to_town
                and not player.blind
                and not player.confused
                and self._can_read_scrolls(snapshot)
                and (teleport := self._find_teleport_scroll(snapshot)) is not None
                and teleport.count > 1
            ):
                # The return explorer has proved that this remembered region has
                # no route to an up-stair. Relocate once, preserving one emergency
                # scroll, then let normal exploration rebuild its progress budget.
                self._nav_exhausted = False
                self._nav_stall_count = 0
                self.last_reason = "livelock:teleport-explore"
                return self._read_key(snapshot, teleport)
        self.last_reason = "livelock:exhausted"
        return WAIT_KEY

    def _window_edge_relocation_path(
        self, snapshot: Snapshot
    ) -> list[Position]:
        """BFS to one untried walkable boundary cell of the current emission."""
        if not self._emitted_t:
            return []
        min_y = min(y for y, _ in self._emitted_t)
        max_y = max(y for y, _ in self._emitted_t)
        min_x = min(x for _, x in self._emitted_t)
        max_x = max(x for _, x in self._emitted_t)
        extents = {
            (-1, 0): min_y,
            (1, 0): max(0, snapshot.height - 1 - max_y),
            (0, -1): min_x,
            (0, 1): max(0, snapshot.width - 1 - max_x),
        }
        start = snapshot.player.position
        queue: deque[Position] = deque([start])
        parent: dict[Position, Position | None] = {start: None}
        distance = {start: 0}
        while queue:
            position = queue.popleft()
            for neighbor in self._walkable_neighbors(
                snapshot, position, allow_damaging=False
            ):
                if (
                    neighbor in parent
                    or neighbor in self._engagement_avoid_cells
                ):
                    continue
                parent[neighbor] = position
                distance[neighbor] = distance[position] + 1
                queue.append(neighbor)
    
        ranked: list[tuple[tuple[int, int, int, int, int], Position]] = []
        for y, x in self._emitted_t:
            goal = Position(y, x)
            if (
                goal == start
                or goal not in parent
                or goal in self._window_edge_goals
                or (y, x) not in self._floor_t
            ):
                continue
            outward = [
                (dy, dx)
                for dy, dx in extents
                if snapshot.in_bounds(Position(y + dy, x + dx))
                and (y + dy, x + dx) not in self._emitted_t
            ]
            if not outward:
                continue
            direction = max(
                outward,
                key=lambda offset: (
                    extents[offset],
                    (y - start.y) * offset[0]
                    + (x - start.x) * offset[1],
                ),
            )
            displacement = (
                (y - start.y) * direction[0]
                + (x - start.x) * direction[1]
            )
            score = (
                extents[direction],
                displacement,
                -distance[goal],
                -y,
                -x,
            )
            ranked.append((score, goal))
        if not ranked:
            return []
        goal = max(ranked)[1]
        path: list[Position] = []
        node: Position | None = goal
        while node is not None and node != start:
            path.append(node)
            node = parent[node]
        path.reverse()
        return path

    def _disengage_move_or_escalate(
        self,
        snapshot: Snapshot,
        threats: list[MonsterState],
        hostiles: list[MonsterState],
    ) -> str | None:
        """One deterministic disengage move.
    
        Retreat only when it makes progress: a retreat step that re-enters a
        recently occupied cell is corner ping-pong, not an escape, so escalate
        to stairs, then to cutting a path through a survivable swarm toward open
        floor, instead of oscillating in a dead end until the loop guard stops
        the bot. Returns None only when genuinely stuck (caller bounded-waits).
        """
        # Leaving the floor beats relocating within it: read a carried Word of
        # Recall (then hold for the countdown) to escape directly. This does NOT
        # depend on the _returning_to_town latch, which a swarm's fruitless-combat
        # state can leave unset so _return_to_town_key never issues the scroll
        # (live: Yeek Cave worm mass, 5 recall scrolls carried yet never read).
        player = snapshot.player
        if (
            snapshot.floor_key[2] == 0
            and not self._floor_navigation_exit_locked(snapshot)
            and not player.recalling
            and not player.blind
            and not player.confused
            and self._can_read_scrolls(snapshot)
        ):
            recall = self._find_recall_scroll(snapshot)
            if recall is not None:
                self._returning_to_town = True
                self.last_reason = "combat:disengage-recall"
                return self._read_key(snapshot, recall)
        step = self._summoner_retreat_step(snapshot, threats, hostiles)
        if step is not None and not (
            self._is_oscillating() and step in set(self._recent)
        ):
            self.last_reason = "combat:disengage-step"
            return self._step_toward(snapshot, step)
        stairs = self._escape_by_stairs(snapshot)
        if stairs is not None:
            self.last_reason = "combat:disengage-stairs"
            return stairs
        # No stairs underfoot: route toward the nearest known up-stairs to leave
        # the floor entirely. The player outruns a speed-100 breeder swarm, so
        # reaching the stairs breaks contact where circling the same room never
        # can — the decisive escape when there is no recall or teleport left.
        to_stairs = self._nearest_goal_step(snapshot, self._is_upstairs_target)
        if to_stairs is not None:
            self.last_reason = "combat:disengage-seek-upstairs"
            return self._step_toward(snapshot, to_stairs)
        # A known exit behind a survivable single-file blocker chain remains
        # available when neither a retreat nor a route step exists.
        blocker = self._blocking_escape_melee_key(
            snapshot, hostiles, self._is_upstairs_target
        )
        if blocker is not None:
            self.last_reason = "combat:disengage-clear-path"
            return blocker
        if hostiles:
            # Cornered with no retreat or stairs. If the swarm's three-turn
            # projected damage is well under current HP it cannot kill us while
            # we leave, so head for open floor (attacking any breeder blocking
            # that direction) rather than flee deeper into the dead end. The
            # explore step targets a frontier, so the move makes real positional
            # progress instead of ping-ponging.
            threat = self.threat_prediction(
                snapshot, hostiles, 3
            )["operational_total"]
            if threat * 2 < snapshot.player.hp:
                target = self._explore_step(snapshot)
                if target is not None and target != snapshot.player.position:
                    self.last_reason = "combat:disengage-cut-through"
                    return self._step_toward(snapshot, target)
        adjacent = self._physical_adjacent_hostiles(snapshot)
        if adjacent:
            self.last_reason = "combat:disengage-melee"
            return self._direction_key(
                snapshot.player.position, self._weakest(adjacent).position
            )
        return None

    def _descent_is_blocked(self, snapshot: Snapshot) -> bool:
        self._descent_refusal_reason = None
        if self._returning_to_town or len(snapshot.inventory) >= PACK_CAPACITY:
            self._descent_refusal_reason = (
                "returning-to-town" if self._returning_to_town else "pack-full"
            )
            return True
        if (
            snapshot.in_town
            and
            self._recall_departure_shortage(snapshot)
            and not self._recall_shortage_opening_exempt(snapshot)
            and self._fundraising_mode not in {"mine", "scavenge"}
        ):
            self._descent_refusal_reason = "recall-departure-shortage"
            return True
        if self._next_depth_supply_shortage(snapshot):
            # Defence in depth: the return policy should already be taking us
            # upward, but the descent command itself must never permit depth 2+
            # without the agreed supplies even if return state is lost/reset.
            self._descent_refusal_reason = "next-depth-supply-shortage"
            return True
        if snapshot.in_town:
            if self._fundraising_mode in {"mine", "scavenge"}:
                if (
                    not self._town_restock_suppressed
                    and not self._fundraising_departure_ready(snapshot)
                ):
                    self._descent_refusal_reason = "fundraising-departure-not-ready"
                    return True
            else:
                # A departure-only visit may waive preferred procurement, but
                # never expose the dungeon entrance when it would be dark.
                if (
                    self._town_restock_suppressed
                    and not self._fundraising_light_ready(snapshot)
                ):
                    self._descent_refusal_reason = "fundraising-light-shortage"
                    return True
                if not self._town_restock_suppressed and (
                    self._rumor_unlock_pending
                    or not self._town_departure_ready(snapshot)
                ):
                    self._descent_refusal_reason = (
                        "rumor-unlock-pending"
                        if self._rumor_unlock_pending
                        else "town-departure-not-ready"
                    )
                    return True
            if self._fundraising_mode in {"mine", "scavenge"}:
                # A threat ascent from Yeek 1F defers deeper movement on that
                # dungeon visit.  Back in town, the next fundraising walk-in
                # generates a fresh level 1; carrying the 200-decision cooldown
                # across that boundary only hides the entrance and hands town
                # to stuck:wander after the mining kit is ready.
                return False
        if not self._descent_blocked:
            return False
        if self._descent_block_countdown <= 0:
            self._descent_blocked = False
            return False
        self._descent_refusal_reason = "descent-cooldown"
        return True

    def _open_neighbor_count(self, snapshot: Snapshot, position: Position) -> int:
        # Geometry must not change when a room fills with monsters.  The normal
        # routing index deliberately removes occupied cells, but choke scoring
        # is terrain-only.
        count = 0
        for dy, dx in NEIGHBOR_OFFSETS:
            grid = snapshot.grid_at(Position(position.y + dy, position.x + dx))
            if grid is not None and grid.known and (
                grid.passable or grid.is_closed_door
            ):
                count += 1
        return count

    def _build_grid_index(self, snapshot: Snapshot) -> None:
        remembered_floor = self._remembered_floor_t
        remembered_door = self._remembered_door_t
        remembered_rubble = self._remembered_rubble_t
        remembered_wall = self._remembered_wall_t
        remembered_known = self._remembered_known_t
        remembered_marked = self._remembered_marked_t
        blocked_doors = self._blocked_doors
        blocked_rubble = self._blocked_rubble
        for pos, grid in snapshot.grids.items():
            key = (pos.y, pos.x)
            if not grid.known:
                continue
            if grid.has_down_stairs and not self._is_downstairs_expired(pos):
                self._remembered_downstairs.add(pos)
            if grid.has_up_stairs and not self._nav_ledger.is_expired("ascend", pos):
                self._remembered_upstairs.add(pos)
            if grid.has_entrance:
                self._remembered_entrances.add(pos)
            remembered_known.add(key)
            if grid.marked:
                remembered_marked.add(key)
            remembered_floor.discard(key)
            remembered_door.discard(key)
            remembered_rubble.discard(key)
            remembered_wall.discard(key)
            if grid.is_closed_door:
                self._blocked_unknown.discard(key)
                self._probe_counts.pop(key, None)
                # Closed doors remain actionable frontiers until opened or
                # abandoned. Open doors are ordinary passable floor; retaining
                # them here makes exploration bounce forever between old doors.
                remembered_door.add(key)
            elif grid.is_rubble:
                self._blocked_unknown.discard(key)
                self._probe_counts.pop(key, None)
                # Rubble is passed by tunnelling ('T'+dir) — treat it like a door
                # the pathfinder may route through, until we give up on it.
                remembered_rubble.add(key)
            elif grid.passable:
                remembered_floor.add(key)
            elif grid.wall:
                remembered_wall.add(key)
        floor = set(remembered_floor)
        door = remembered_door - blocked_doors
        rubble = remembered_rubble - blocked_rubble
        known = set(remembered_known)
        marked = set(remembered_marked)
        for pos, grid in snapshot.grids.items():
            if not grid.has_monster:
                continue
            key = (pos.y, pos.x)
            floor.discard(key)
            door.discard(key)
            rubble.discard(key)
        for monster in snapshot.detected_monsters:
            key = (monster.position.y, monster.position.x)
            floor.discard(key)
            door.discard(key)
            rubble.discard(key)
        # In the Outpost — a fixed, fully-remembered town — supplement the emitted
        # map with the static layout the bot loaded from lib/edit/towns: add
        # walkable tiles the snapshot does not currently show (unlit at night) so
        # the pathfinder can still route across town to a store. Emitted tiles
        # always win (live monsters / walls), so only genuinely-absent tiles are
        # filled — this reveals nothing to the bot that a returning player would
        # not already remember about a static town.
        if self._town_map_active(snapshot):
            for pos in self._town_map.walkable:
                key = (pos.y, pos.x)
                if key not in known:
                    floor.add(key)
                    known.add(key)
                    marked.add(key)
        self._floor_t = floor
        self._door_t = door
        self._rubble_t = rubble
        self._marked_t = marked

    def _descent_step(self, snapshot: Snapshot) -> Position | None:
        """Follow the ledger-owned route to one committed descent target.
    
        Target selection happens only when no commitment is live.  A blocked
        step or an interrupt that moved the player off-route re-paths to the
        same stair; rejection, expiry, arrival, and floor change invalidate it.
        """
        self._descent_target_goal = None
        if self._descent_is_blocked(snapshot):
            return None
        # R1: a descent target whose approach stalled past the ledger budget is
        # expired for this floor visit — for EVERY mode at once. Without this,
        # seek/approach/breakout handed the same unreachable remembered stair
        # to each other forever (the 2026-07-17 starvation incident).
        expired = self._nav_ledger.expired_targets("descend")
        visible_descent_positions = {
            g.position
            for g in snapshot.grids.values()
            if g.is_descent
        }
        visible_targets = {
            g.position
            for g in snapshot.grids.values()
            if self._is_descent_target(snapshot, g)
            and not self._is_downstairs_expired(g.position)
        }
        targets = set(visible_targets)
        forgotten_targets: set[Position] = set()
        if (
            snapshot.dungeon_level > 0
            and self._fundraising_mode not in {"mine", "scavenge"}
            and not self._missing_required_abilities(
                snapshot, snapshot.dungeon_level + 1
            )
        ):
            forgotten_targets = (
                self._remembered_downstairs - visible_descent_positions - expired
            )
            targets.update(forgotten_targets)
        origin = snapshot.player.position
        # Reaching a route target ends that commitment.  If descent handling
        # deliberately falls through to routing while standing on a stair,
        # choose another stair rather than path away and then back to this one.
        targets.discard(origin)
        if self._nav_ledger.descent_target == origin:
            self._nav_ledger.clear_descent_route()
        if not targets:
            # Night in a static town: the '>' entrance is unlit and absent from
            # the emitted grids, so the emitted-target scan above finds nothing.
            # Commit to the town map's remembered entrance instead (only while
            # we would actually walk in — a deep run recalls).
            entrance = self._town_map_descent_entrance(snapshot)
            if entrance is not None and entrance not in expired:
                targets.add(entrance)
            else:
                self._nav_ledger.clear_descent_route()
                self._descent_refusal_reason = (
                    "expired-or-ineligible-downstairs"
                    if self._remembered_downstairs
                    else "no-known-downstairs"
                )
                return None
        committed = self._nav_ledger.descent_target
        if committed is not None and committed not in targets:
            self._nav_ledger.clear_descent_route()
            committed = None
        if committed is None:
            # Distance chooses the useful stair; coordinates make every tie
            # deterministic instead of inheriting set/BFS iteration order.
            target = min(targets, key=lambda t: (origin.distance_to(t), t.y, t.x))
            self._nav_ledger.commit_descent_route(target, ())
        else:
            target = committed
        self._descent_target_goal = target
        avoided_store_cells = self._town_entrance_cells(snapshot)
        avoided_store_cells.discard(origin)
        avoided_store_cells.discard(target)
        if self._town_map_goal_step(
            snapshot, target, allow_entrance_fallback=False
        ) is None:
            avoided_store_cells.clear()
        if origin == target:
            self._nav_ledger.clear_descent_route()
            self._descent_refusal_reason = "standing-on-target"
            return None
    
        self._nav_ledger.advance_descent_route(origin)
        route = self._nav_ledger.descent_path
        if route:
            nxt = route[0]
            if (
                origin.distance_to(nxt) == 1
                and nxt not in avoided_store_cells
                and self._is_step_open(snapshot, origin, nxt)
            ):
                # Both metrics bottom out at one before arrival: committed paths
                # use remaining length, while fresh BFS uses distance from origin.
                self._nav_ledger.observe("descend", target, len(route))
                if self._nav_ledger.is_expired("descend", target):
                    self._descent_target_goal = None
                    self._descent_refusal_reason = "expired-target"
                    return None
                self.last_reason = (
                    "seek-downstairs"
                    if route[-1] == target
                    else "approach-descent"
                )
                return nxt
            # A wall/monster or an off-path survival/combat move invalidates
            # only the path.  The target remains owned by the ledger.
            self._nav_ledger.replace_descent_path(())
    
        seen = {origin}
        queue: deque[tuple[Position, Position | None, int]] = deque([(origin, None, 0)])
        parent: dict[Position, Position | None] = {origin: None}
        best_first: Position | None = None
        best_frontier: Position | None = None
        best_score: tuple[int, int, int] | None = None
        while queue:
            pos, first, path_distance = queue.popleft()
            if pos != origin and pos == target:
                # Reachable target: record true path length. It shrinks every
                # real step, so a legitimate walk never expires — only a step
                # the game keeps rejecting accumulates stall here.
                self._nav_ledger.observe("descend", pos, path_distance)
                if self._nav_ledger.is_expired("descend", pos):
                    self._descent_target_goal = None
                    self._descent_refusal_reason = "expired-target"
                    return None
                path: list[Position] = []
                cursor: Position | None = pos
                while cursor is not None and cursor != origin:
                    path.append(cursor)
                    cursor = parent[cursor]
                path.reverse()
                self._nav_ledger.commit_descent_route(target, path)
                self.last_reason = "seek-downstairs"
                return first
            grid = snapshot.grids.get(pos)
            if pos != origin and grid is not None:
                if self._is_frontier(snapshot, grid):
                    visits = self._visit_counts[pos]
                    target_distance = pos.distance_to(target)
                    score = (
                        target_distance + path_distance + VISIT_PENALTY * visits,
                        visits,
                        target_distance,
                    )
                    if best_score is None or score < best_score:
                        best_score = score
                        best_first = first
                        best_frontier = pos
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen or neighbor in avoided_store_cells:
                    continue
                seen.add(neighbor)
                parent[neighbor] = pos
                queue.append(
                    (
                        neighbor,
                        neighbor if first is None else first,
                        path_distance + 1,
                    )
                )
    
        if best_first is not None and best_score is not None:
            # Unreachable target, frontier approach: no known path exists, so
            # progress is how close the best reachable FRONTIER has gotten to
            # the target — circumnavigating a vault keeps revealing frontiers
            # nearer the stair (improvement), while the doomed flicker pocket's
            # frontiers never get any closer. Spending the whole ledger budget
            # without the frontier line advancing means the floor will not
            # yield this stair — expire it.
            self._nav_ledger.observe("descend", target, best_score[2])
            if self._nav_ledger.is_expired("descend", target):
                self._descent_target_goal = None
                return None
            path = []
            cursor = best_frontier
            while cursor is not None and cursor != origin:
                path.append(cursor)
                cursor = parent[cursor]
            path.reverse()
            self._nav_ledger.commit_descent_route(target, path)
            self.last_reason = "approach-descent"
        else:
            # No path and no frontier can make progress toward this commitment.
            # Expire it now so deterministic selection cannot choose it again.
            self._nav_ledger.expire("descend", target)
            self._descent_target_goal = None
        return best_first

    def _explore_step(self, snapshot: Snapshot) -> Position | None:
        # A fully-known static town needs no exploration sweep: every walkable
        # tile is preloaded from the town map, so both the "visit each passable
        # tile once" and frontier goals in _plan_explore_path would otherwise
        # send us wandering the town at night (dark walls read as unknown).
        if self._town_map_active(snapshot):
            self._clear_explore_path(ExplorationPathOutcome.ABANDON)
            return None
        start = snapshot.player.position
        oscillating = self._is_oscillating()
        identity = self._explore_goal_identity
        if identity is not None:
            if self._explore_goal_is_complete(snapshot, identity):
                self._explore_path_outcome = ExplorationPathOutcome.SUCCESS
                self._explore_goal_identity = None
                self._explore_path = []
                identity = None
            elif not self._explore_goal_evidence_matches(snapshot, identity):
                self._retire_explore_goal(identity)
                identity = None
        if identity is not None and (oscillating or not self._explore_path):
            self._clear_explore_path(ExplorationPathOutcome.PAUSE)
            route = self._route_to_explore_goal(
                snapshot,
                identity.position,
                avoid=set(self._recent) if oscillating else set(),
            )
            if not route and oscillating:
                # Confinement is routing evidence, not proof that the goal is
                # structurally unreachable.  Confirm against the remembered
                # map with only the durable engagement vetoes applied.
                route = self._route_to_explore_goal(snapshot, identity.position)
            if route:
                self._explore_path = route[1:]
                if not self._explore_path:
                    self._explore_path_outcome = ExplorationPathOutcome.PAUSE
                    self._remember_one_step_explore(
                        snapshot, start, route[0]
                    )
                return route[0]
            self._retire_explore_goal(identity)
            identity = None
    
        if oscillating and identity is None:
            global_path = self._global_frontier_path(snapshot)
            if global_path:
                self._explore_path = global_path[1:]
                self._record_explore_goal(
                    snapshot,
                    ExplorationGoalKind.FRONTIER,
                    global_path[-1],
                )
                return global_path[0]
        # Follow the committed route while it stays valid, so open areas are
        # swept in straight lines instead of oscillating between two tiles.
        while self._explore_path:
            nxt = self._explore_path[0]
            if (
                nxt not in self._engagement_avoid_cells
                and start.distance_to(nxt) == 1
                and self._is_step_open(snapshot, start, nxt)
            ):
                self._explore_path.pop(0)
                if not self._explore_path:
                    self._explore_path_outcome = ExplorationPathOutcome.PAUSE
                    self._remember_one_step_explore(snapshot, start, nxt)
                return nxt
            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            identity = self._explore_goal_identity
            if identity is not None:
                route = self._route_to_explore_goal(snapshot, identity.position)
                if route:
                    self._explore_path = route[1:]
                    if not self._explore_path:
                        self._explore_path_outcome = (
                            ExplorationPathOutcome.PAUSE
                        )
                        self._remember_one_step_explore(
                            snapshot, start, route[0]
                        )
                    return route[0]
                self._retire_explore_goal(identity)
    
        path = self._plan_explore_path(snapshot)
        if not path:
            return None
        self._explore_path = path[1:]
        goal = path[-1]
        kind = (
            ExplorationGoalKind.VISIT
            if self._visit_counts[goal] == 0
            else ExplorationGoalKind.FRONTIER
        )
        self._record_explore_goal(snapshot, kind, goal)
        if not self._explore_path:
            self._explore_path_outcome = ExplorationPathOutcome.PAUSE
            self._remember_one_step_explore(snapshot, start, path[0])
        return path[0]

    def _explore_goal_evidence_matches(
        self,
        snapshot: Snapshot,
        identity: ExplorationGoalIdentity,
    ) -> bool:
        grid = snapshot.grid_at(identity.position)
        if grid is None:
            # An off-screen remembered goal has supplied no new evidence.
            return True
        current = self._explore_goal_signature(grid)
        # Monster occupancy is deliberately excluded: it pauses a commitment
        # but cannot turn the underlying terrain/information goal into another
        # identity.
        return current[:-1] == identity.evidence_signature[:-1]

    def _explore_goal_is_complete(
        self,
        snapshot: Snapshot,
        identity: ExplorationGoalIdentity,
    ) -> bool:
        if identity.kind == ExplorationGoalKind.VISIT:
            return (
                snapshot.player.position == identity.position
                or self._visit_counts[identity.position] > 0
            )
        if identity.kind == ExplorationGoalKind.FRONTIER:
            return not self._is_remembered_frontier(snapshot, identity.position)
        return snapshot.player.position == identity.position

    @staticmethod
    def _explore_goal_signature(
        grid: GridState | None,
    ) -> tuple[int, bool, bool, bool, int]:
        if grid is None:
            return (-1, False, False, False, 0)
        return (
            grid.terrain_id,
            grid.marked,
            grid.passable,
            grid.is_closed_door,
            grid.monster_index if grid.has_monster else 0,
        )

    def _plan_explore_path(self, snapshot: Snapshot) -> list[Position]:
        """Dijkstra to the nearest (visit-penalised) frontier, returning the full
        step path so we can commit to it."""
        path = self._plan_explore_path_pass(snapshot, allow_damaging=False)
        if path:
            return path
        return self._plan_explore_path_pass(snapshot, allow_damaging=True)

    def _global_frontier_path(self, snapshot: Snapshot) -> list[Position]:
        """Route to the most promising frontier anywhere on the remembered map."""
        candidates = {
            Position(y, x)
            for y, x in self._remembered_floor_t
            if Position(y, x) not in self._probed_frontiers
            and Position(y, x) not in self._unenterable_explore_goals
            and self._is_remembered_frontier(snapshot, Position(y, x))
        }
        candidates.discard(snapshot.player.position)
        if not candidates:
            return []
        visited_weight = sum(self._visit_counts.values())
        if visited_weight:
            centroid_y = sum(
                position.y * visits
                for position, visits in self._visit_counts.items()
            ) / visited_weight
            centroid_x = sum(
                position.x * visits
                for position, visits in self._visit_counts.items()
            ) / visited_weight
        else:
            centroid_y = snapshot.player.position.y
            centroid_x = snapshot.player.position.x
    
        def frontier_score(position: Position) -> tuple[int, float, int, int]:
            unknown = sum(
                (position.y + dy, position.x + dx) not in self._marked_t
                and (position.y + dy, position.x + dx)
                not in self._blocked_unknown
                and snapshot.in_bounds(
                    Position(position.y + dy, position.x + dx)
                )
                for dy, dx in NEIGHBOR_OFFSETS
            )
            # Immediate unknown exposure estimates region size; distance from
            # the over-visited centroid breaks ties toward genuinely new areas.
            centroid_distance = abs(position.y - centroid_y) + abs(
                position.x - centroid_x
            )
            return (unknown, centroid_distance, -position.y, -position.x)
    
        goal = max(candidates, key=frontier_score)
        start = snapshot.player.position
        digger = self._equipped_digging_tool(snapshot) is not None
        queue: deque[Position] = deque([start])
        parent: dict[Position, Position | None] = {start: None}
        while queue:
            position = queue.popleft()
            if position == goal:
                break
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor in parent or neighbor in self._engagement_avoid_cells:
                    continue
                grid = snapshot.grids.get(neighbor)
                walkable = neighbor in self._walkable_neighbors(snapshot, position)
                diggable = (
                    digger
                    and grid is not None
                    and grid.known
                    and grid.can_dig
                    and not grid.permanent
                    and neighbor not in self._mining_unmarkable_grids
                )
                if not walkable and not diggable:
                    continue
                parent[neighbor] = position
                queue.append(neighbor)
        if goal not in parent:
            self._probed_frontiers.add(goal)
            return []
        path: list[Position] = []
        node: Position | None = goal
        while node is not None and node != start:
            path.append(node)
            node = parent[node]
        path.reverse()
        return path

    def _plan_explore_path_pass(
        self, snapshot: Snapshot, *, allow_damaging: bool
    ) -> list[Position]:
        start = snapshot.player.position
        previous = self._recent[-2] if len(self._recent) >= 2 else None
        sequence = count()
        queue: list[tuple[int, int, Position]] = [(0, next(sequence), start)]
        best_cost = {start: 0}
        parent: dict[Position, Position | None] = {start: None}
        goal: Position | None = None
    
        while queue:
            cost, _, pos = heappop(queue)
            if cost != best_cost.get(pos):
                continue
            if pos != start:
                # Lighting a tile only reveals it from the current viewpoint;
                # walking onto it can expose corners and terrain beyond the
                # light boundary. Sweep every remembered passable tile at least
                # once before declaring that only frontier/secret-door work is
                # left.
                if (
                    self._visit_counts[pos] == 0
                    and (pos.y, pos.x) in self._floor_t
                    and pos not in self._unenterable_explore_goals
                ):
                    goal = pos
                    break
                if (
                    pos not in self._unenterable_explore_goals
                    and self._is_remembered_frontier(snapshot, pos)
                ):
                    goal = pos
                    break
            for neighbor in self._walkable_neighbors(
                snapshot, pos, allow_damaging=allow_damaging
            ):
                if neighbor in self._engagement_avoid_cells:
                    continue
                penalty = VISIT_PENALTY * self._visit_counts[neighbor]
                if neighbor == previous:
                    penalty += BACKTRACK_PENALTY
                next_cost = cost + 1 + penalty
                if next_cost >= best_cost.get(neighbor, next_cost + 1):
                    continue
                best_cost[neighbor] = next_cost
                parent[neighbor] = pos
                heappush(queue, (next_cost, next(sequence), neighbor))
    
        if goal is None:
            return []
        path: list[Position] = []
        node: Position | None = goal
        while node is not None and node != start:
            path.append(node)
            node = parent[node]
        path.reverse()
        return path

    def _is_oscillating(self) -> bool:
        # Tight 2-4 tile cycles are actionable quickly.  The longer secondary
        # window catches the live six-cell random-quest frontier loop without
        # classifying one normal traversal of a small room as oscillation.
        recent = list(self._recent)
        if (
            len(recent) >= STUCK_WINDOW
            and len(set(recent[-STUCK_WINDOW:])) <= 4
        ):
            return True
        return (
            len(recent) >= EXTENDED_STUCK_WINDOW
            and len(set(recent[-EXTENDED_STUCK_WINDOW:])) <= 6
        )

    def _undersearched_walls(self, position: Position) -> list[tuple[int, int]]:
        if self._search_counts[(position.y, position.x)] >= SEARCH_LIMIT:
            return []
        return [
            key
            for dy, dx in NEIGHBOR_OFFSETS
            if (key := (position.y + dy, position.x + dx))
            in self._remembered_wall_t
            and self._wall_search_counts[key] < SEARCH_LIMIT
        ]

    def _step_toward(
        self,
        snapshot: Snapshot,
        step: Position,
        *,
        tail: str = "",
        allow_paralyzer_ring_escape: bool = False,
    ) -> str:
        """Direction key toward an adjacent tile, but if it is a CLOSED door,
        open it (``o`` + direction) instead of walking — a closed door is a
        frontier the pathfinder heads for, yet walking into it may not open it.
        Doors that refuse to open (jammed / hard lock) are abandoned.
    
        SUFFIX OWNERSHIP INVARIANT: this method is the single owner of the
        final composed walk macro.  Callers that need follow-up keys for the
        screen the walk opens (quest-entry confirm, building command chains)
        pass them as ``tail`` — never by concatenating onto the returned key.
        input_check consumes queued keys (y/n answer it, Escape refuses it,
        anything else rings the bell and the prompt keeps waiting), so any
        queued suffix can decide a TR_WARNING entry prompt the caller never
        anticipated.  Owning the tail here lets the warning gate rule on the
        complete key: a latched grid is never entered while movement supplies
        remain regardless of what a caller wanted to append, and the walk's
        pending record notes whether the crossing was the sanctioned
        forced-walk so an unsanctioned tail-answered crossing is detected and
        latched by _warning_prompt_response_key instead of passing silently.
        A structural test pins that no other call site concatenates onto
        _step_toward's result."""
        if step == snapshot.player.position:
            self.last_reason = "nav:step-self"
            return WAIT_KEY + tail
        if step in self._paralyzer_avoid_cells:
            walkable = self._walkable_neighbors(
                snapshot, snapshot.player.position
            )
            fully_ringed = bool(walkable) and all(
                candidate in self._paralyzer_avoid_cells
                for candidate in walkable
            )
            if not (allow_paralyzer_ring_escape and fully_ringed):
                self.last_reason = "threat:paralyzer-avoid:blocked-step"
                return WAIT_KEY
        key = self._direction_key(snapshot.player.position, step)
        grid = snapshot.grids.get(step)
        if grid is not None and grid.trap:
            yx = (step.y, step.x)
            if self._floor_trap_disarm_attempts[yx] < CHEST_DISARM_BUDGET:
                self._floor_trap_disarm_attempts[yx] += 1
                return CHEST_DISARM_KEY + key + tail
        elif grid is not None:
            self._floor_trap_disarm_attempts.pop((step.y, step.x), None)
        if grid is not None and grid.is_closed_door:
            yx = (step.y, step.x)
            self._door_attempts[yx] += 1
            if self._door_attempts[yx] >= DOOR_OPEN_LIMIT:
                self._blocked_doors.add(yx)
            return OPEN_KEY + key + tail
        if grid is not None and grid.is_rubble:
            # Dig through the rubble; it clears to floor after a few turns, then
            # the next step walks in. Give up (route around) if it won't budge.
            yx = (step.y, step.x)
            signature = (yx, snapshot.turn)
            if signature == self._last_dig_signature:
                self._rejected_dig_attempts += 1
            else:
                self._last_dig_signature = signature
                self._rejected_dig_attempts = 0
            self._dig_attempts[yx] += 1
            if (
                self._dig_attempts[yx] >= RUBBLE_DIG_LIMIT
                or self._rejected_dig_attempts >= RUBBLE_REJECT_LIMIT
            ):
                self._blocked_rubble.add(yx)
            return TUNNEL_KEY + key + tail
        if (
            grid is not None
            and grid.can_dig
            and not grid.enterable
            and self._equipped_digging_tool(snapshot) is not None
        ):
            tunnel = self._mining_tunnel_key(snapshot, step)
            return (tunnel if tunnel is not None else key) + tail
        if step in self._warning_refused_cells:
            if not self._warning_supplies_exhausted(snapshot) or (
                step in self._engagement_owned_avoid_cells
            ):
                # The gate on the COMPLETE composed key: a latched warning
                # grid is never entered while a movement scroll remains (or
                # while the engagement owner independently requires the cell
                # avoided) — not even by a caller whose tail would have
                # answered the re-raised prompt.  A bare walk is not a safer
                # fallback: warning.cpp:501's old_damage suppression lets a
                # repeated attempt enter silently.
                #
                # Reachability of this WAIT, honestly: dungeon routing is
                # avoid-aware everywhere a picker can re-select statically
                # (loot/goal/mining/dig/device BFS, the loot wiggle, the
                # chest step-off), so a dungeon repeat requires one of the
                # windowed one-shot breakers (oscillation breakout,
                # _breakout_step) or a quest-floor navigator static route —
                # the former re-arm only after a fresh no-progress window,
                # the latter terminates at the CLI loop-detector visible
                # stop, the navigator's pre-existing terminal for its own
                # quest:blocked states.  The reachable-in-principle
                # unbounded route is a TOWN composed caller re-selecting a
                # latched special tile (e.g. a fixed-quest entrance) every
                # decision; the user has ruled that case out of scope
                # (2026-08-03: 町で警告ブロックが発生することはほぼなく、
                # 固定クエスト入口が封鎖されることは考えなくて良い), so it
                # is recorded here rather than defended against.
                self.last_reason = "warning:blocked-step"
                return WAIT_KEY
            # 物資が全て尽きている場合のみ徒歩強行を許す: the forced walk
            # carries its deliberate 'y' with the movement key, so the
            # re-raised input_check is answered inline; the caller's tail
            # then feeds the screen the crossing opens.  When warning.cpp:501
            # suppresses the re-check, the move executes and the stray 'y'
            # falls into the original-keyset illegal-command default (no
            # keymap for 'y' outside roguelike mode) — bounded, non-acting.
            self._warning_step_pending = (
                self._decision_sequence,
                snapshot.floor_key,
                snapshot.player.position,
                step,
                True,
            )
            return key + "y" + tail
        # A plain walk may meet a first-encounter TR_WARNING entry prompt;
        # remember which grid this decision entered — and that the crossing
        # was NOT the sanctioned forced walk — so the next snapshot's prompt
        # message is attributed to it (see _warning_prompt_response_key).
        self._warning_step_pending = (
            self._decision_sequence,
            snapshot.floor_key,
            snapshot.player.position,
            step,
            False,
        )
        command = key + tail
        if (
            snapshot.store is None
            and grid is not None
            and grid.store_number >= 0
        ):
            # A direction onto a disclosed shop entrance can open the store as
            # its movement side effect.  Own the resulting observation just as
            # a deliberate entrance WAIT does, so no surface decision can be
            # posted into the newly-open store.
            self._store_entry_wait_owner = grid.store_number
            self._store_entry_wait_key = command
        return command
