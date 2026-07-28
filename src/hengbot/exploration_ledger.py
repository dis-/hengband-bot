"""Persistent, player-observed exploration state for one dungeon floor."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable

from hengbot.model import GridState, Position, Snapshot


# Keep the ledger beside runtime logs so it remains local operational state.
EXPLORATION_LEDGER_PATH = Path("jsonlog/exploration-ledger.json")
# A compact spread of terrain observations reliably fingerprints a floor.
EXPLORATION_SAMPLE_SIZE = 32
# Amortize disk writes while retaining useful state across abrupt restarts.
EXPLORATION_SAVE_CADENCE = 16
# Permit a few emitter/terrain-memory discrepancies without accepting a new layout.
EXPLORATION_SAMPLE_MISMATCH_TOLERANCE = 0.15


def _sample(snapshot: Snapshot) -> list[tuple[int, int, int]]:
    candidates = sorted(
        (
            grid.position.y,
            grid.position.x,
            grid.terrain_id,
        )
        for grid in snapshot.grids.values()
        if grid.known and grid.marked and grid.terrain_id >= 0
    )
    if len(candidates) <= EXPLORATION_SAMPLE_SIZE:
        return candidates
    # Evenly span the remembered map instead of fingerprinting one local pocket.
    last = len(candidates) - 1
    return [
        candidates[round(index * last / (EXPLORATION_SAMPLE_SIZE - 1))]
        for index in range(EXPLORATION_SAMPLE_SIZE)
    ]


class ExplorationLedger:
    """JSON-backed state for only the currently occupied floor instance."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.floor_key: tuple[int, int, int] | None = None
        self.sample: list[tuple[int, int, int]] = []
        self.visit_counts: Counter[Position] = Counter()
        self.probed_frontiers: set[Position] = set()
        self.search_counts: Counter[tuple[int, int]] = Counter()
        self.wall_search_counts: Counter[tuple[int, int]] = Counter()
        self.blocked_unknown: set[tuple[int, int]] = set()
        self.marked_high = 0
        self._dirty_decisions = 0
        self._loaded = False

    def _clear(self, floor_key: tuple[int, int, int] | None = None) -> None:
        self.floor_key = floor_key
        self.sample = []
        self.visit_counts.clear()
        self.probed_frontiers.clear()
        self.search_counts.clear()
        self.wall_search_counts.clear()
        self.blocked_unknown.clear()
        self.marked_high = 0
        self._dirty_decisions = 0

    def bind(self, snapshot: Snapshot) -> bool:
        """Load once, accepting state only when key and terrain sample agree."""
        if self._loaded:
            if self.floor_key != snapshot.floor_key:
                self.save(force=True)
                self._clear(snapshot.floor_key)
                self.sample = _sample(snapshot)
                self.marked_high = self.marked_count(snapshot)
                return False
            return True
        self._loaded = True
        try:
            data = (
                json.loads(self.path.read_text(encoding="utf-8"))
                if self.path is not None
                else {}
            )
        except (OSError, ValueError, TypeError):
            data = {}
        stored_key = tuple(data.get("floor_key", ()))
        stored_sample = [tuple(item) for item in data.get("sample", ())]
        if stored_key != snapshot.floor_key or not self._sample_agrees(
            snapshot, stored_sample
        ):
            self._clear(snapshot.floor_key)
            self.sample = _sample(snapshot)
            self.marked_high = self.marked_count(snapshot)
            return False
        self.floor_key = snapshot.floor_key
        self.sample = stored_sample
        self.visit_counts.update(
            {
                Position(int(y), int(x)): int(value)
                for y, x, value in data.get("visit_counts", ())
            }
        )
        self.probed_frontiers = self._positions(data.get("probed_frontiers", ()))
        self.search_counts.update(self._counter(data.get("search_counts", ())))
        self.wall_search_counts.update(
            self._counter(data.get("wall_search_counts", ()))
        )
        self.blocked_unknown = {
            (int(y), int(x)) for y, x in data.get("blocked_unknown", ())
        }
        self.marked_high = max(
            int(data.get("marked_high", 0)), self.marked_count(snapshot)
        )
        return True

    @staticmethod
    def marked_count(snapshot: Snapshot) -> int:
        return sum(
            getattr(grid, "marked", False)
            for grid in getattr(snapshot, "grids", {}).values()
        )

    @staticmethod
    def _positions(values: Iterable[Iterable[int]]) -> set[Position]:
        return {Position(int(y), int(x)) for y, x in values}

    @staticmethod
    def _counter(values: Iterable[Iterable[int]]) -> dict[tuple[int, int], int]:
        return {(int(y), int(x)): int(value) for y, x, value in values}

    @staticmethod
    def _sample_agrees(
        snapshot: Snapshot, sample: list[tuple[int, int, int]]
    ) -> bool:
        if not sample:
            return False
        observed = {
            (grid.position.y, grid.position.x): grid.terrain_id
            for grid in snapshot.grids.values()
            if grid.known and grid.marked and grid.terrain_id >= 0
        }
        comparable = [
            observed[(y, x)] == terrain
            for y, x, terrain in sample
            if (y, x) in observed
        ]
        # Missing remembered coordinates are disagreement: otherwise a tiny
        # local launch snapshot could accidentally validate an unrelated floor.
        mismatches = len(sample) - sum(comparable)
        return mismatches / len(sample) <= EXPLORATION_SAMPLE_MISMATCH_TOLERANCE

    def note_decision(self) -> None:
        self._dirty_decisions += 1
        if self._dirty_decisions >= EXPLORATION_SAVE_CADENCE:
            self.save()

    def save(self, *, force: bool = False) -> None:
        if (
            self.path is None
            or self.floor_key is None
            or (not force and self._dirty_decisions == 0)
        ):
            return
        payload = {
            "floor_key": list(self.floor_key),
            "sample": [list(item) for item in self.sample],
            "visit_counts": [
                [position.y, position.x, value]
                for position, value in self.visit_counts.items()
            ],
            "probed_frontiers": [
                [position.y, position.x] for position in self.probed_frontiers
            ],
            "search_counts": [
                [y, x, value] for (y, x), value in self.search_counts.items()
            ],
            "wall_search_counts": [
                [y, x, value] for (y, x), value in self.wall_search_counts.items()
            ],
            "blocked_unknown": [list(item) for item in self.blocked_unknown],
            "marked_high": self.marked_high,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(self.path)
            self._dirty_decisions = 0
        except OSError:
            # Navigation must remain available if local persistence is unwritable.
            return
