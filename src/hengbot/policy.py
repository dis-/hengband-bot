from __future__ import annotations

from collections import Counter, deque
from heapq import heappop, heappush
from itertools import count

from hengbot.model import GridState, Position, Snapshot


DIRECTION_KEYS: dict[tuple[int, int], str] = {
    (-1, -1): "7",
    (-1, 0): "8",
    (-1, 1): "9",
    (0, -1): "4",
    (0, 1): "6",
    (1, -1): "1",
    (1, 0): "2",
    (1, 1): "3",
}

NEIGHBOR_OFFSETS = tuple(DIRECTION_KEYS.keys())
VISIT_PENALTY = 4


class ConservativePolicy:
    def __init__(self) -> None:
        self._visit_counts: Counter[Position] = Counter()
        self._floor_key: tuple[int, int, int] | None = None
        self._last_position: Position | None = None

    def choose_key(self, snapshot: Snapshot) -> str:
        self._observe_position(snapshot)

        if snapshot.player.hp_ratio < 0.30 and self._hostiles(snapshot):
            retreat = self._retreat_step(snapshot)
            if retreat is not None:
                return self._direction_key(snapshot.player.position, retreat)
            return "5"

        adjacent = self._adjacent_hostile(snapshot)
        if adjacent is not None:
            return self._direction_key(snapshot.player.position, adjacent.position)

        downstairs = self._nearest_matching_grid(snapshot, lambda grid: grid.has_down_stairs)
        if downstairs is not None:
            step = self._next_step_toward(snapshot, downstairs.position)
            if step is not None:
                return self._direction_key(snapshot.player.position, step)

        frontier_step = self._next_step_to_frontier(snapshot)
        if frontier_step is not None:
            return self._direction_key(snapshot.player.position, frontier_step)

        return "5"

    def _observe_position(self, snapshot: Snapshot) -> None:
        if snapshot.floor_key != self._floor_key:
            self._visit_counts.clear()
            self._floor_key = snapshot.floor_key
            self._last_position = None

        position = snapshot.player.position
        if position != self._last_position:
            self._visit_counts[position] += 1
            self._last_position = position

    def _hostiles(self, snapshot: Snapshot):
        return [monster for monster in snapshot.visible_monsters if monster.hostile]

    def _adjacent_hostile(self, snapshot: Snapshot):
        for monster in self._hostiles(snapshot):
            if snapshot.player.position.distance_to(monster.position) <= 1:
                return monster
        return None

    def _retreat_step(self, snapshot: Snapshot) -> Position | None:
        hostiles = self._hostiles(snapshot)
        candidates = self._walkable_neighbors(snapshot, snapshot.player.position)
        if not candidates:
            return None

        def score(pos: Position) -> tuple[int, int]:
            nearest = min(pos.distance_to(monster.position) for monster in hostiles)
            unsafe = 1 if snapshot.grids[pos].unsafe else 0
            return nearest, -unsafe

        return max(candidates, key=score)

    def _nearest_matching_grid(self, snapshot: Snapshot, predicate) -> GridState | None:
        start = snapshot.player.position
        seen = {start}
        queue = deque([start])
        while queue:
            pos = queue.popleft()
            grid = snapshot.grids.get(pos)
            if grid is not None and pos != start and predicate(grid):
                return grid

            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(neighbor)

        return None

    def _next_step_toward(self, snapshot: Snapshot, target: Position) -> Position | None:
        start = snapshot.player.position
        if start == target:
            return None

        seen = {start}
        queue = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                next_first = neighbor if first_step is None else first_step
                if neighbor == target:
                    return next_first
                seen.add(neighbor)
                queue.append((neighbor, next_first))

        return None

    def _next_step_to_frontier(self, snapshot: Snapshot) -> Position | None:
        start = snapshot.player.position
        sequence = count()
        queue: list[tuple[int, int, int, Position, Position | None]] = [
            (0, 0, next(sequence), start, None)
        ]
        best_cost = {start: 0}

        while queue:
            cost, steps, _, pos, first_step = heappop(queue)
            if cost != best_cost.get(pos):
                continue

            grid = snapshot.grids.get(pos)
            if pos != start and grid is not None and self._is_frontier(snapshot, grid):
                return first_step

            for neighbor in self._walkable_neighbors(snapshot, pos):
                next_cost = cost + 1 + VISIT_PENALTY * self._visit_counts[neighbor]
                if next_cost >= best_cost.get(neighbor, next_cost + 1):
                    continue
                best_cost[neighbor] = next_cost
                next_first = neighbor if first_step is None else first_step
                heappush(queue, (next_cost, steps + 1, next(sequence), neighbor, next_first))

        return None

    def _walkable_neighbors(self, snapshot: Snapshot, pos: Position) -> list[Position]:
        neighbors: list[Position] = []
        for dy, dx in NEIGHBOR_OFFSETS:
            neighbor = Position(pos.y + dy, pos.x + dx)
            grid = snapshot.grids.get(neighbor)
            if grid is None or not grid.passable or grid.has_monster:
                continue
            neighbors.append(neighbor)
        return neighbors

    def _is_frontier(self, snapshot: Snapshot, grid: GridState) -> bool:
        if not grid.passable:
            return False

        for dy, dx in NEIGHBOR_OFFSETS:
            neighbor = snapshot.grids.get(Position(grid.position.y + dy, grid.position.x + dx))
            if neighbor is not None and not neighbor.known:
                return True
        return False

    def _direction_key(self, origin: Position, target: Position) -> str:
        dy = max(-1, min(1, target.y - origin.y))
        dx = max(-1, min(1, target.x - origin.x))
        return DIRECTION_KEYS[(dy, dx)]
