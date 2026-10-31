"""Single state-machine owner for approved fixed-quest navigation."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, replace
from enum import Enum
import re
from typing import Any

from hengbot.equipment_optimizer import Q34_ITEM_TAG, q34_item_tagged
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position, Snapshot, TVAL_CHEST, TVAL_GOLD
from hengbot.policy_constants import (
    EQUIPMENT_SLOT_KEY,
    POST_CLEAR_PICKUP_ATTEMPT_LIMIT,
    QUEST_STATUS_TAKEN,
    WAIT_KEY,
)
from hengbot.policy_types import DecisionCandidate, QuestTravelDeclaration
from hengbot.quest_final_room import avoided_doors, door_gates, post_clear_pickup
from hengbot.quest_knowledge import QuestBattlefield


class QuestPhase(str, Enum):
    ENTER = "enter"
    EXECUTE = "execute"
    SWEEP = "sweep"
    EXIT = "exit"


# Searching is a phase transition bound: once every static door on a candidate
# route has consumed this budget, the FSM stops loudly instead of re-entering
# generic exploration. It deliberately matches the policy's established secret
# search evidence budget.
DOOR_SEARCH_BUDGET = 8
# Phase bound fallback when a strategy profile supplies no engagement hold budget.
DEFAULT_HOLD_BUDGET = 2000
# Phase bound prevents an unreachable loot target from trapping the sweep forever.
SWEEP_BUDGET = 200
PICKUP_KEY = "g"
RANGED_VANTAGE_DIRECTIONS = (
    (-1, -1), (-1, 0), (-1, 1), (0, -1),
    (0, 1), (1, -1), (1, 0), (1, 1),
)
Q34_QUEST_ID = 34


def _unidentified_identity(item: Any) -> tuple[int, int, str]:
    """A carried unidentified item's identity, stable when a feeling appears.

    The display name gains ``{並}`` (a pseudo-ID feeling) or an inscription
    block later; strip trailing brace blocks so the item stays the same one.
    """
    return (item.tval, item.sval, re.sub(r"(\s*\{[^{}]*\})+\s*$", "", item.name))


@dataclass
class QuestFloorNavigator:
    quest_id: int
    battlefield: QuestBattlefield
    phase: QuestPhase = QuestPhase.ENTER
    allow_deep_water: bool = False
    allow_diagonal: bool = False

    # Unidentified equipment carried when the Q34 floor was first decided, and
    # the items already sent the inscription.  Class defaults keep restored
    # checkpoints without these attributes on the old behaviour.
    q34_carried_before = None
    q34_inscription_sent = frozenset()

    def __post_init__(self) -> None:
        self.door_searches: Counter[tuple[int, int]] = Counter()
        self.hold_turns = 0
        self.sweep_turns = 0
        self.post_clear_pickups = 0
        self.floor_key: tuple[int, int, int] | None = None
        self.opened: set[Position] = set()

    def reset_for_floor(self, floor_key: tuple[int, int, int]) -> None:
        if self.floor_key == floor_key:
            return
        self.floor_key = floor_key
        self.phase = QuestPhase.EXECUTE
        self.door_searches.clear()
        self.hold_turns = 0
        self.sweep_turns = 0
        self.post_clear_pickups = 0
        self.opened.clear()
        self.q34_carried_before = None
        self.q34_inscription_sent = frozenset()

    def _q34_inscription_key(self, owner: Any, snapshot: Snapshot, adjacent: list[Any]) -> str | None:
        """Inscribe ``Q34`` on unidentified equipment picked up on the Q34 floor.

        Owner 2026-10-31: 「Q34習得品も付けて良い」 and 「Q34で拾った品を覚える
        必要があるなら銘を刻むこと」.  The game's inscription is the record the
        equipment optimizer reads later (``q34_item_tagged``); the bot keeps no
        private list.  An item counts as picked up here when it was not carried
        at the first decision on this floor (a restart mid-quest therefore
        leaves earlier pickups untagged).  Inscribing takes no game time
        (cmd-item.cpp do_cmd_inscribe uses no energy); it still waits while a
        monster is adjacent.  Each item is sent the command once.
        """
        if self.quest_id != Q34_QUEST_ID:
            return None
        carried = [
            *((item, False) for item in snapshot.inventory),
            *((item, True) for item in snapshot.equipment),
        ]
        unidentified = [
            (item, worn) for item, worn in carried
            if item.is_equipment and not item.known and not q34_item_tagged(item)
        ]
        if self.q34_carried_before is None:
            self.q34_carried_before = frozenset(
                _unidentified_identity(item) for item, _ in unidentified
            )
            return None
        if adjacent:
            return None
        for item, worn in unidentified:
            identity = _unidentified_identity(item)
            if identity in self.q34_carried_before or identity in self.q34_inscription_sent:
                continue
            address = EQUIPMENT_SLOT_KEY.get(item.slot) if worn else None
            if worn and address is None:
                continue
            kind = "inscribe-equipped" if worn else "inscribe"
            prefix = reserved_item_command(
                owner, snapshot, kind, item, "quest-launcher", address=address
            )
            if prefix is None:
                continue
            self.q34_inscription_sent = self.q34_inscription_sent | {identity}
            # An existing inscription opens in overwrite mode; Ctrl-E moves to
            # its end in insert mode first (the heavy-curse marker does the same).
            text = ("\x05 " if item.inscription else "") + Q34_ITEM_TAG
            owner.last_reason = "quest-strategy:q34-inscribe-pickup"
            return prefix + text + "\r"
        return None

    @staticmethod
    def enter_from_town(owner: Any, snapshot: Snapshot, quest_id: int) -> str | None:
        """Route to a fixed entrance using only reviewed town-map/BFS facts."""
        positions = owner._fixed_quest_entrance_positions(snapshot, quest_id)
        context = getattr(owner, "_decision_context", None)
        quest = snapshot.quests.get(quest_id)
        source = (
            owner._effective_town_id(snapshot) if context is not None else 0
        )
        candidate_identity = object()
        if not positions:
            # No public entrance fact exists yet.  Waiting cannot reveal one;
            # hand control back to the existing town explorer instead.
            return None
        if snapshot.player.position in positions:
            if not owner._quest_equipment_entry_allowed(snapshot, quest_id):
                return None
            owner.last_reason = "quest:enter"
            return ">"
        if context is None:
            step = owner._nearest_goal_step(
                snapshot,
                lambda grid: grid.has_quest_enter and grid.quest_id == quest_id,
            )
            if step is None:
                candidates = [
                    owner._town_map_goal_step(snapshot, pos) for pos in positions
                ]
                step = min(
                    (candidate for candidate in candidates if candidate is not None),
                    key=lambda pos: snapshot.player.position.distance_to(pos),
                    default=None,
                )
            if step is None:
                owner.last_reason = "quest:blocked:enter"
                return WAIT_KEY
            if step in positions and not owner._quest_equipment_entry_allowed(
                snapshot, quest_id
            ):
                return None
            owner.last_reason = "quest:enter:approach"
            return owner._step_toward(snapshot, step)
        route = owner._nearest_goal_route(
            snapshot, lambda grid: grid.has_quest_enter and grid.quest_id == quest_id
        )
        if route is None:
            candidates = [owner._town_map_goal_route(snapshot, pos) for pos in positions]
            route = min(
                (candidate for candidate in candidates if candidate is not None),
                key=lambda candidate: snapshot.player.position.distance_to(
                    candidate.first_step
                ),
                default=None,
            )
        if route is None:
            return QuestFloorNavigator._unavailable_entry_candidate(
                owner, snapshot, quest_id, quest, source, context,
                candidate_identity,
            )
        reason = "quest:enter:approach"
        if route.first_step in positions and not owner._quest_equipment_entry_allowed(
            snapshot, quest_id
        ):
            return None
        # The step's owner is the entering owner before the step is composed
        # (#102: _step_toward admits a quest entrance only for that owner).
        owner.last_reason = reason
        key = owner._step_toward(snapshot, route.first_step)
        owner.last_reason = reason
        if context is None or quest is None:
            return key
        declaration = QuestTravelDeclaration(
            quest_id=quest_id, quest_status=quest.status,
            stage="enter-approach", source_town_id=source,
            destination_town_id=source, floor=snapshot.floor_key,
            goal=route.target, first_step=route.first_step,
            bfs_rank=route.remaining_edges, composed_key=key,
            decision_identity=context.identity,
            candidate_identity=candidate_identity,
            producer_branch="quest-enter-approach",
        )
        return DecisionCandidate(
            key, reason=reason, decision_identity=context.identity,
            route_declaration=declaration, identity=candidate_identity,
        )

    @staticmethod
    def _unavailable_entry_candidate(
        owner: Any, snapshot: Snapshot, quest_id: int, quest: Any,
        source: int, context: Any, candidate_identity: object,
    ) -> str | None:
        if context is None or quest is None or quest.status != QUEST_STATUS_TAKEN:
            return None
        reason = "quest:enter:approach:route-unavailable"
        declaration = QuestTravelDeclaration(
            quest_id=quest_id, quest_status=quest.status,
            stage="enter-approach-route-unavailable", source_town_id=source,
            destination_town_id=source, floor=snapshot.floor_key,
            goal=None, first_step=None, bfs_rank=None, composed_key=WAIT_KEY,
            decision_identity=context.identity,
            candidate_identity=candidate_identity,
            producer_branch="quest-enter-approach",
        )
        owner.last_reason = reason
        return DecisionCandidate(
            WAIT_KEY, reason=reason, decision_identity=context.identity,
            route_declaration=declaration, identity=candidate_identity,
        )

    def decide(self, owner: Any, snapshot: Snapshot, hostiles: list[Any], adjacent: list[Any]) -> str:
        self.reset_for_floor(snapshot.floor_key)
        quest = snapshot.quests.get(self.quest_id)
        completed = quest is not None and quest.status == 2

        # Completion never overrides immediate combat. The ordinary survival
        # gates have already run above this call; adjacent enemies are cleared
        # here before the FSM is allowed to walk toward loot or the exit.
        if completed and adjacent and not snapshot.player.afraid and owner._can_fight_in_dungeon(snapshot.floor_key[0]):
            owner.last_reason = "quest-strategy:melee"
            return owner._direction_key(snapshot.player.position, owner._weakest(adjacent).position)
        if completed and self.phase in {QuestPhase.ENTER, QuestPhase.EXECUTE}:
            self.phase = QuestPhase.SWEEP
        inscription = self._q34_inscription_key(owner, snapshot, adjacent)
        if inscription is not None:
            return inscription

        if self.phase == QuestPhase.EXECUTE:
            action = owner._quest_execute_key(snapshot, hostiles, adjacent)
            if action is not None:
                if owner.last_reason == "quest-strategy:hold":
                    self.hold_turns += 1
                    budget = self._hold_budget(owner)
                    if self.hold_turns > budget:
                        owner.last_reason = "quest:blocked:hold"
                        return "5"
                else:
                    self.hold_turns = 0
                return action
            owner.last_reason = "quest:blocked:execute"
            return "5"

        if self.phase == QuestPhase.SWEEP:
            action = self._sweep(owner, snapshot, hostiles)
            if action is not None:
                if owner.last_reason == "quest:sweep:collect":
                    # The navigator reports its sweep phase; the completed
                    # decision walks toward floor loot. Use the existing loot
                    # namespace without stealing quest-request's census reasons.
                    owner.last_reason = "loot:seek-quest-sweep"
                    owner._declare_reach(owner._loot_target)
                return action
            self.phase = QuestPhase.EXIT

        if completed:
            pickup = self._post_clear_pickup(owner, snapshot)
            if pickup is not None:
                return pickup
        return self._exit(owner, snapshot)

    def _hold_budget(self, owner: Any) -> int:
        profile = owner.approved_quest_strategy(self.quest_id)
        plan = profile.engagement_plan if profile is not None else {}
        return int(plan.get("hold_budget", DEFAULT_HOLD_BUDGET))

    @staticmethod
    def with_loot_memory(snapshot: Snapshot) -> Snapshot:
        """Use public remembered objects without changing terrain visibility."""
        grids = dict(snapshot.grids)
        for y, x, count, *tvals in snapshot.found_items or ():
            pos = Position(y, x)
            grid = grids.get(pos)
            if grid is not None and grid.object_count == 0:
                grids[pos] = replace(grid, object_count=count, object_tvals=tuple(tvals))
        return replace(snapshot, grids=grids)

    def _sweep(self, owner: Any, snapshot: Snapshot, hostiles: list[Any]) -> str | None:
        if hostiles:
            action = owner._quest_execute_key(
                snapshot, hostiles, owner._strategic_adjacent_hostiles(snapshot)
            )
            if action is not None:
                return action
        here = snapshot.grid_at(snapshot.player.position)
        processed_chests = getattr(owner, "_processed_chest_positions", set())
        profile = owner.approved_quest_strategy(self.quest_id)
        plan = profile.engagement_plan if profile is not None else {}
        chest_value = plan.get("chest_position")
        reserved_chests = (
            {Position(*chest_value)} if chest_value is not None else set()
        )
        if (
            here is not None
            and here.object_count > 0
            and here.position not in processed_chests
            and here.position not in reserved_chests
            and here.position not in getattr(owner, "_deferred_loot", set())
            and not owner._floor_pile_is_junk(snapshot, here)
            and TVAL_CHEST not in here.object_tvals
        ):
            pack_space = owner._quest_sweep_pack_space_key(snapshot, here)
            if pack_space is not None:
                return pack_space
            owner.last_reason = "quest:sweep:pickup"
            if here.object_count > 1:
                return PICKUP_KEY + ("a" * here.object_count)
            return PICKUP_KEY
        # Reuse ordinary loot value/safety judgment; only routing belongs to
        # the fixed-map navigator (including its avoided doors).
        loot = {
            pos for pos in owner._loot_candidates(snapshot, include_unsafe=True)
            if self._static_walkable(pos)
            and pos not in processed_chests
            and pos not in reserved_chests
            and not (
                (grid := snapshot.grid_at(pos)) is not None
                and TVAL_CHEST in grid.object_tvals
            )
        }
        if loot and self.sweep_turns < SWEEP_BUDGET:
            blocked = {
                Position(*raw) for raw in plan.get("avoid_door_positions", ())
            }
            final_door_value = plan.get("final_door")
            if final_door_value is not None:
                blocked.discard(Position(*final_door_value))
            loot.difference_update(blocked)
            path = self._static_path(
                snapshot.player.position, loot, blocked=blocked
            )
            if len(path) > 1:
                self.sweep_turns += 1
                owner._loot_target = path[-1]
                owner.last_reason = "quest:sweep:collect"
                owner._declare_reach(owner._loot_target)
                return owner._step_toward(snapshot, path[1])
        return None

    def _post_clear_pickup(self, owner: Any, snapshot: Snapshot) -> str | None:
        """Collect the plan's ``post_clear_pickup`` gold before the exit.

        Runs after the loot sweep, so its route budget cannot drop the gold.
        The cell is done once the board shows it without gold or the bounded
        pickup fallback is used up; walking onto gold normally collects it.
        """
        profile = owner.approved_quest_strategy(self.quest_id)
        plan = profile.engagement_plan if profile is not None else {}
        cell = post_clear_pickup(plan)
        if cell is None:
            return None
        grid = snapshot.grid_at(cell)
        if grid is not None and grid.known and TVAL_GOLD not in grid.object_tvals:
            return None
        if snapshot.player.position == cell:
            attempts = getattr(self, "post_clear_pickups", 0)
            if attempts >= POST_CLEAR_PICKUP_ATTEMPT_LIMIT:
                return None
            self.post_clear_pickups = attempts + 1
            owner.last_reason = "quest:post-clear:pickup-gold"
            return PICKUP_KEY
        path = self._static_path(
            snapshot.player.position, {cell}, blocked=door_gates(snapshot, plan)
        )
        if len(path) < 2:
            return None
        owner.last_reason = "quest:post-clear:seek-gold"
        owner._declare_reach(cell)
        return owner._step_toward(snapshot, path[1])

    def _exit(self, owner: Any, snapshot: Snapshot) -> str:
        target_t = self.battlefield.exit or self.battlefield.entrance
        if target_t is None:
            owner.last_reason = "quest:blocked:exit"
            return "5"
        target = Position(*target_t)
        if snapshot.player.position == target:
            owner.last_reason = "quest:exit"
            return "<"
        profile = owner.approved_quest_strategy(self.quest_id)
        plan = profile.engagement_plan if profile is not None else {}
        blocked = avoided_doors(plan)
        path = self._static_path(
            snapshot.player.position, {target}, blocked=blocked
        )
        if len(path) < 2:
            owner.last_reason = "quest:blocked:exit"
            return "5"
        nxt = path[1]
        kind = self.battlefield.terrain.get((nxt.y, nxt.x))
        grid = snapshot.grid_at(nxt)
        if kind == "door" and (grid is None or not grid.enterable):
            door = (nxt.y, nxt.x)
            if self.door_searches[door] >= DOOR_SEARCH_BUDGET:
                owner.last_reason = "quest:blocked:exit"
                return "5"
            self.door_searches[door] += 1
            owner.last_reason = "quest:exit:search-door"
            return "s"
        owner.last_reason = "quest:exit:route"
        return owner._step_toward(snapshot, nxt)

    def _static_walkable(self, pos: Position) -> bool:
        kind = self.battlefield.terrain.get((pos.y, pos.x))
        return pos in self.opened or kind in {
            "floor", "exit", "door", "passage", "rubble", "shallow_water",
            "tree",
        } or (self.allow_deep_water and kind == "deep_water")

    @staticmethod
    def placement_sweep_blocked(
        owner: Any, snapshot: Snapshot, plan: dict[str, Any]
    ) -> set[Position]:
        """Keep placement routes and their exploration fallback behind door gates."""
        # Q34's final door is opened by the approved engagement phase. Only
        # reuse that crossing after observing it open; the sweep cannot open it.
        blocked = door_gates(snapshot, plan)
        # Static terrain regards every door as walkable. Honour the ordinary
        # movement owner's bounded open failures instead of retrying forever.
        blocked.update(Position(*yx) for yx in owner._blocked_doors)
        blocked.update(
            Position(*yx) for floor, yx in getattr(owner, "_stuck_doors", ())
            if floor == snapshot.floor_key
        )
        return blocked

    def route_to_static_goals(
        self,
        start: Position,
        goals: set[Position],
        blocked: set[Position] | None = None,
    ) -> Position | None:
        path = self._static_path(start, goals, blocked=blocked)
        return path[1] if len(path) > 1 else None

    def ranged_vantage_goals(
        self, target: Position, max_distance: int
    ) -> set[Position]:
        """Static dry/shallow firing cells with an unobstructed 8-way ray."""
        goals: set[Position] = set()
        ray_terrain = {
            "floor", "exit", "passage", "shallow_water", "deep_water"
        }
        for dy, dx in RANGED_VANTAGE_DIRECTIONS:
            for distance in range(1, max_distance + 1):
                candidate = Position(
                    target.y - dy * distance, target.x - dx * distance
                )
                if not self._static_walkable(candidate):
                    continue
                clear = all(
                    Position(target.y - dy * step, target.x - dx * step) in self.opened
                    or self.battlefield.terrain.get(
                        (target.y - dy * step, target.x - dx * step)
                    ) in ray_terrain
                    for step in range(1, distance)
                )
                if clear:
                    goals.add(candidate)
        return goals

    def observation_goals(
        self, target: Position, max_distance: int
    ) -> set[Position]:
        """Walkable cells near a mobile target's fixed-map start position."""
        return {
            Position(y, x)
            for (y, x) in self.battlefield.terrain
            if Position(y, x).distance_to(target) <= max_distance
            and self._static_walkable(Position(y, x))
        }

    def _static_path(
        self,
        start: Position,
        goals: set[Position],
        *,
        blocked: set[Position] | None = None,
    ) -> list[Position]:
        blocked = blocked or set()
        queue = deque([start])
        previous: dict[Position, Position | None] = {start: None}
        end = None
        while queue:
            current = queue.popleft()
            if current in goals:
                end = current
                break
            directions = (
                RANGED_VANTAGE_DIRECTIONS
                if self.allow_diagonal
                else ((-1, 0), (0, -1), (0, 1), (1, 0))
            )
            for dy, dx in directions:
                nxt = Position(current.y + dy, current.x + dx)
                if (
                    nxt not in previous
                    and nxt not in blocked
                    and self._static_walkable(nxt)
                ):
                    previous[nxt] = current
                    queue.append(nxt)
        if end is None:
            return []
        path = []
        while end is not None:
            path.append(end)
            end = previous[end]
        return list(reversed(path))

    def _route(self, snapshot: Snapshot, goals: set[Position]) -> Position | None:
        path = self._static_path(snapshot.player.position, goals)
        return path[1] if len(path) > 1 else None
