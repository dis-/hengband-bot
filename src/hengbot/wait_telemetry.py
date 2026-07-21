from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable


class WaitTelemetry:
    """Persist cumulative intentional wait time without logging every poll."""

    def __init__(
        self,
        path: Path | None,
        *,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        flush_interval: float = 1.0,
    ) -> None:
        self.path = path
        self._wall_clock = wall_clock
        self._monotonic = monotonic
        self._flush_interval = flush_interval
        self._last_flush = monotonic()
        self._data = self._load()

    def _load(self) -> dict:
        if self.path is not None and self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if payload.get("version") == 1 and isinstance(payload.get("categories"), dict):
                    return payload
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass
        now = self._wall_clock()
        return {
            "version": 1,
            "started_at_epoch": now,
            "updated_at_epoch": now,
            "total_seconds": 0.0,
            "total_calls": 0,
            "categories": {},
        }

    def record(self, category: str, seconds: float, *, force_flush: bool = False) -> None:
        if not category or seconds < 0:
            return
        entry = self._data["categories"].setdefault(
            category, {"seconds": 0.0, "calls": 0}
        )
        entry["seconds"] += float(seconds)
        entry["calls"] += 1
        self._data["total_seconds"] += float(seconds)
        self._data["total_calls"] += 1
        self._data["updated_at_epoch"] = self._wall_clock()
        now = self._monotonic()
        if force_flush or now - self._last_flush >= self._flush_interval:
            self.flush()

    def flush(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
            self._last_flush = self._monotonic()
        except OSError:
            # Telemetry must never interrupt play; the next record retries.
            return

    @property
    def data(self) -> dict:
        return self._data
