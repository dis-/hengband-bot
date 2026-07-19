"""Static global-wilderness routing from Hengband's WildernessDefinition.txt."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path


# Roads are deliberately much cheaper than open terrain. Water is excluded:
# every normal town is road-connected, so a return never needs to risk it.
_TERRAIN_COST = {
    "*": 1, "!": 1, "+": 1,
    ".": 7, ",": 6, "T": 16, "D": 31, "=": 36,
    "^": 51, "$": 61, "&": 81,
    # Only use water when it is the sole connection from an isolated region.
    "_": 10_000, "~": 100_000,
}
_DIRECTIONS = (
    (-1, -1, "7"), (-1, 0, "8"), (-1, 1, "9"),
    (0, -1, "4"), (0, 1, "6"),
    (1, -1, "1"), (1, 0, "2"), (1, 1, "3"),
)


@dataclass(frozen=True)
class WildernessMap:
    rows: tuple[str, ...]

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    @property
    def towns(self) -> frozenset[tuple[int, int]]:
        return frozenset(
            (y, x)
            for y, row in enumerate(self.rows)
            for x, cell in enumerate(row)
            if cell.isdigit() and cell != "0"
        )

    def next_key_to_town(self, y: int, x: int) -> str | None:
        """Return the first step on the least-danger route to any town."""
        start = (y, x)
        if start in self.towns:
            return ">"
        if not self._passable(y, x):
            return None

        queue: list[tuple[int, int, int]] = [(0, y, x)]
        costs = {start: 0}
        first_key: dict[tuple[int, int], str] = {}
        while queue:
            cost, cy, cx = heappop(queue)
            current = (cy, cx)
            if cost != costs.get(current):
                continue
            if current in self.towns:
                return first_key[current]
            for dy, dx, key in _DIRECTIONS:
                ny, nx = cy + dy, cx + dx
                if not self._passable(ny, nx):
                    continue
                step_cost = self._cost(ny, nx) + (1 if dy and dx else 0)
                new_cost = cost + step_cost
                neighbor = (ny, nx)
                if new_cost >= costs.get(neighbor, 10**9):
                    continue
                costs[neighbor] = new_cost
                first_key[neighbor] = first_key.get(current, key)
                heappush(queue, (new_cost, ny, nx))
        return None

    def _passable(self, y: int, x: int) -> bool:
        if not (0 <= y < self.height and 0 <= x < self.width):
            return False
        cell = self.rows[y][x]
        return (cell.isdigit() and cell != "0") or cell in _TERRAIN_COST

    def _cost(self, y: int, x: int) -> int:
        cell = self.rows[y][x]
        return 1 if cell.isdigit() else _TERRAIN_COST[cell]


def load_wilderness_map(path: Path) -> WildernessMap:
    """Load the first (normal-game) wilderness layout block."""
    rows: list[str] = []
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if raw.startswith("W:D:"):
            rows.append(raw[4:])
            continue
        if rows:
            break
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"invalid wilderness layout: {path}")
    return WildernessMap(tuple(rows))


def find_wilderness_definition(start: Path | None = None) -> Path | None:
    bases = [base for base in (start, Path.cwd()) if base is not None]
    seen: set[Path] = set()
    for base in bases:
        for directory in (base, *base.parents):
            if directory in seen:
                continue
            seen.add(directory)
            candidate = directory / "lib" / "edit" / "WildernessDefinition.txt"
            if candidate.is_file():
                return candidate
    return None
