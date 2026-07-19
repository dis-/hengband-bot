"""Single state-machine owner for approved fixed-quest navigation."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hengbot.model import Position, Snapshot
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


@dataclass
class QuestFloorNavigator:
    quest_id: int
    battlefield: QuestBattlefield
    phase: QuestPhase = QuestPhase.ENTER

    def __post_init__(self) -> None:
        self.door_searches: Counter[tuple[int, int]] = Counter()
        self.hold_turns = 0
        self.sweep_turns = 0
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
        self.opened.clear()

    @staticmethod
    def enter_from_town(owner: Any, snapshot: Snapshot, quest_id: int) -> str | None:
        """Route to a fixed entrance using only reviewed town-map/BFS facts."""
        positions = owner._fixed_quest_entrance_positions(snapshot, quest_id)
        if not positions:
            return None
        if snapshot.player.position in positions:
            owner.last_reason = "quest:enter"
            return ">y"
        step = owner._nearest_goal_step(
            snapshot, lambda grid: grid.has_quest_enter and grid.quest_id == quest_id
        )
        if step is None:
            candidates = [owner._town_map_goal_step(snapshot, pos) for pos in positions]
            step = min(
                (candidate for candidate in candidates if candidate is not None),
                key=lambda pos: snapshot.player.position.distance_to(pos),
                default=None,
            )
        if step is None:
            owner.last_reason = "quest:blocked:enter"
            return "5"
        owner.last_reason = "quest:enter:approach"
        return owner._step_toward(snapshot, step)

    def decide(self, owner: Any, snapshot: Snapshot, hostiles: list[Any], adjacent: list[Any]) -> str:
        self.reset_for_floor(snapshot.floor_key)
        quest = snapshot.quests.get(self.quest_id)
        completed = quest is not None and quest.status == 2

        # Completion never overrides immediate combat. The ordinary survival
        # gates have already run above this call; adjacent enemies are cleared
        # here before the FSM is allowed to walk toward loot or the exit.
        if completed and adjacent and not snapshot.player.afraid:
            owner.last_reason = "quest-strategy:melee"
            return owner._direction_key(snapshot.player.position, owner._weakest(adjacent).position)
        if completed and self.phase in {QuestPhase.ENTER, QuestPhase.EXECUTE}:
            self.phase = QuestPhase.SWEEP

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
                return action
            self.phase = QuestPhase.EXIT

        return self._exit(owner, snapshot)

    def _hold_budget(self, owner: Any) -> int:
        profile = owner.approved_quest_strategy(self.quest_id)
        plan = profile.engagement_plan if profile is not None else {}
        return int(plan.get("hold_budget", DEFAULT_HOLD_BUDGET))

    def _sweep(self, owner: Any, snapshot: Snapshot, hostiles: list[Any]) -> str | None:
        if hostiles:
            action = owner._quest_execute_key(snapshot, hostiles, owner._adjacent_hostiles(snapshot))
            if action is not None:
                return action
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.object_count > 0:
            owner.last_reason = "quest:sweep:pickup"
            if here.object_count > 1:
                return PICKUP_KEY + ("a" * here.object_count)
            return PICKUP_KEY
        loot = {
            pos for pos, grid in snapshot.grids.items()
            if grid.object_count > 0 and self._static_walkable(pos)
        }
        if loot and self.sweep_turns < SWEEP_BUDGET:
            step = self._route(snapshot, loot)
            if step is not None:
                self.sweep_turns += 1
                owner.last_reason = "quest:sweep:collect"
                return owner._step_toward(snapshot, step)
        return None

    def _exit(self, owner: Any, snapshot: Snapshot) -> str:
        target_t = self.battlefield.exit or self.battlefield.entrance
        if target_t is None:
            owner.last_reason = "quest:blocked:exit"
            return "5"
        target = Position(*target_t)
        if snapshot.player.position == target:
            owner.last_reason = "quest:exit"
            return "<"
        path = self._static_path(snapshot.player.position, {target})
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
        return pos in self.opened or self.battlefield.terrain.get((pos.y, pos.x)) in {
            "floor", "exit", "door", "passage", "rubble", "shallow_water"
        }

    def route_to_static_goals(
        self, start: Position, goals: set[Position]
    ) -> Position | None:
        path = self._static_path(start, goals)
        return path[1] if len(path) > 1 else None

    def _static_path(self, start: Position, goals: set[Position]) -> list[Position]:
        queue = deque([start])
        previous: dict[Position, Position | None] = {start: None}
        end = None
        while queue:
            current = queue.popleft()
            if current in goals:
                end = current
                break
            for dy, dx in ((-1, 0), (0, -1), (0, 1), (1, 0)):
                nxt = Position(current.y + dy, current.x + dx)
                if nxt not in previous and self._static_walkable(nxt):
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
