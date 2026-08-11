from __future__ import annotations

import dataclasses
import enum
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections import Counter, deque
from pathlib import Path
from typing import Any


DEFAULT_DISK_BUDGET_BYTES = 3 * 1024**3
DEFAULT_CHECKPOINT_INTERVAL = 100
DEFAULT_LOG_ROTATE_BYTES = 128 * 1024**2
DEFAULT_LOG_GENERATIONS = 8
DEFAULT_CAPTURE_LOG_ROTATE_BYTES = 5 * 1024**3
DEFAULT_SNAPSHOT_GENERATION_BYTES = 64 * 1024**2
INCIDENT_DECISION_TAIL_BYTES = 16 * 1024**2
INCIDENT_SNAPSHOT_BYTES = 256 * 1024**2
WINDOWS_ILLEGAL_COMPONENT_CHARS = '<>:"/\\|?*'


def safe_filename_component(value: object, *, fallback: str = "unknown") -> str:
    """Return one portable filename component for diagnostic-derived text."""
    translated = "".join(
        "-" if character in WINDOWS_ILLEGAL_COMPONENT_CHARS or ord(character) < 32
        else character
        for character in str(value)
    ).strip().rstrip(". ")
    return translated or fallback


def _warn(operation: str, exc: OSError) -> None:
    print(f"flight recorder failed to {operation}: {exc}", file=sys.stderr)


def _position(value: Any) -> list[int] | Any:
    if hasattr(value, "y") and hasattr(value, "x"):
        return [value.y, value.x]
    return value


def jsonable(value: Any) -> Any:
    """Convert policy internals to stable JSON without invoking gameplay code."""
    value = _position(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, enum.Enum):
        return jsonable(value.value)
    if dataclasses.is_dataclass(value):
        return {
            field.name: jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Counter):
        return [
            {"key": jsonable(key), "count": count}
            for key, count in sorted(value.items(), key=lambda item: repr(item[0]))
        ]
    if isinstance(value, dict):
        return {
            str(jsonable(key)): jsonable(item)
            for key, item in sorted(value.items(), key=lambda item: repr(item[0]))
        }
    if isinstance(value, (set, frozenset)):
        return [jsonable(item) for item in sorted(value, key=repr)]
    if isinstance(value, (list, tuple, deque)):
        return [jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: jsonable(item)
            for key, item in vars(value).items()
            if not callable(item) and not key.startswith("__")
        }
    return repr(value)


def _positions(values: Any) -> list[list[int]]:
    return sorted((_position(value) for value in (values or ())))


def map_memory_summary(policy) -> dict[str, Any]:
    known = getattr(policy, "_remembered_known_t", set())
    visits = getattr(policy, "_visit_counts", {})
    frontiers = 0
    frontier_test = getattr(policy, "_is_frontier", None)
    if frontier_test is not None:
        # Calling _is_frontier requires a snapshot and can affect cost. The
        # remembered topology gives a cheap, conservative open-edge count.
        floor = getattr(policy, "_remembered_floor_t", set())
        for y, x in floor:
            if any(
                (y + dy, x + dx) not in known
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ):
                frontiers += 1
    return {
        "known_cells": len(known),
        "visited_cells": sum(1 for count in visits.values() if count > 0),
        "open_frontiers": frontiers,
        "down_stairs": _positions(getattr(policy, "_remembered_downstairs", set())),
        "up_stairs": _positions(getattr(policy, "_remembered_upstairs", set())),
    }


def policy_state(policy, snapshot=None) -> dict[str, Any]:
    """Serialize volatile policy evidence shared by checkpoints and incidents."""
    terrain_names = (
        "_remembered_known_t",
        "_remembered_floor_t",
        "_remembered_wall_t",
        "_remembered_door_t",
        "_remembered_rubble_t",
        "_remembered_downstairs",
        "_remembered_upstairs",
        "_remembered_entrances",
    )
    required_names = (
        "_town_blocked_reason",
        "_visit_counts",
        "_explore_goal_identity",
        "_explore_path",
        "_explore_path_outcome",
        "_nav_ledger",
        "_escape_state",
        "_unseen_retreat_target",
        "_unseen_retreat_direction",
        "_unseen_retreat_floor",
        "_unseen_choke_position",
        "_unseen_wait_remaining",
        "_unseen_wait_intercepted",
        "_unseen_attack_evidence",
        "_engagement_avoid_cells",
        "_probed_frontiers",
        "_unenterable_explore_goals",
        "_window_edge_goals",
        "_descent_target_goal",
        "_descent_blocked",
        "_descent_block_countdown",
        "_descent_refusal_reason",
        "_remembered_downstairs",
        "_cross_town_shopping",
        "_cross_town_shopping_funds",
        "_shop_selector_diagnostics",
        "_identification_source_reservation",
        "_home_scan_source",
        "_home_scan_item_count",
        # Equipment quarantine sets: without these the 2026-08-02 20:06
        # no-valid-loadout stop could not be diagnosed post-hoc.
        "_equipment_transaction_failed_items",
        "_deferred_home_items",
        "_equipment_quarantine_readmitted_ids",
        "_equipment_quarantine_second_chance_ids",
        "_equipment_quarantine_burned_ids",
        "_home_knowledge_current",
        "_home_knowledge_valid_before",
        "_home_page_size",
    )
    # Include every simple mode/latch/counter as cheap insurance against a field
    # omitted from a hand-maintained diagnostic list.
    simple = {}
    for name, value in vars(policy).items():
        if name.startswith("_latch_capture_"):
            continue
        if (
            any(token in name for token in ("mode", "latch", "quest", "town", "fundrais", "return"))
            and (
                value is None
                or isinstance(value, (str, int, float, bool, enum.Enum))
                or isinstance(value, (set, frozenset, list, tuple, dict))
            )
        ):
            simple[name] = jsonable(value)
    return {
        "format": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "floor": jsonable(snapshot.floor_key) if snapshot is not None else None,
        "terrain": {
            name.removeprefix("_remembered_"): jsonable(getattr(policy, name, set()))
            for name in terrain_names
        },
        "state": {
            name: jsonable(getattr(policy, name, None)) for name in required_names
        },
        "modes_and_latches": simple,
    }


def render_remembered_map(policy, snapshot=None) -> str:
    layers = (
        ("#", getattr(policy, "_remembered_wall_t", set())),
        ("+", getattr(policy, "_remembered_door_t", set())),
        (":", getattr(policy, "_remembered_rubble_t", set())),
        (".", getattr(policy, "_remembered_floor_t", set())),
    )
    cells: dict[tuple[int, int], str] = {}
    for glyph, positions in layers:
        for item in positions:
            cells[tuple(_position(item))] = glyph
    for item in getattr(policy, "_remembered_upstairs", set()):
        cells[tuple(_position(item))] = "<"
    for item in getattr(policy, "_remembered_downstairs", set()):
        cells[tuple(_position(item))] = ">"
    for item in getattr(policy, "_remembered_entrances", set()):
        cells.setdefault(tuple(_position(item)), "E")
    if snapshot is not None:
        cells[tuple(_position(snapshot.player.position))] = "@"
    if not cells:
        return "(no remembered cells)\n"
    ys = [cell[0] for cell in cells]
    xs = [cell[1] for cell in cells]
    return "\n".join(
        "".join(cells.get((y, x), " ") for x in range(min(xs), max(xs) + 1))
        for y in range(min(ys), max(ys) + 1)
    ) + "\n"


def rotate_log(path: Path | None, max_bytes: int, generations: int) -> None:
    if path is None or max_bytes <= 0:
        return
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        for generation in range(max(1, generations) - 1, 0, -1):
            older = path.with_name(f"{path.name}.{generation}")
            newer = path.with_name(f"{path.name}.{generation + 1}")
            if older.exists():
                if generation + 1 >= generations:
                    older.unlink()
                else:
                    os.replace(older, newer)
        os.replace(path, path.with_name(f"{path.name}.1"))
    except OSError as exc:
        _warn(f"rotate {path}", exc)


def append_session_marker(
    path: Path | None,
    argv: list[str],
    *,
    input_delays: dict[str, float] | None = None,
) -> None:
    if path is None:
        return
    commit = None
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        ).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    record = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "kind": "session-start",
        "argv": argv,
        "git_commit": commit,
    }
    if input_delays is not None:
        record["input_delays"] = input_delays
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False)
            file.write("\n")
    except OSError as exc:
        _warn("append session marker", exc)


class FlightRecorder:
    def __init__(
        self,
        root: Path,
        incident_root: Path,
        *,
        budget_bytes: int = DEFAULT_DISK_BUDGET_BYTES,
        checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
        snapshot_generation_bytes: int = DEFAULT_SNAPSHOT_GENERATION_BYTES,
    ) -> None:
        self.root = root
        self.incident_root = incident_root
        self.budget_bytes = budget_bytes
        self.checkpoint_interval = max(1, checkpoint_interval)
        self.snapshot_generation_bytes = snapshot_generation_bytes
        self.snapshot_dir = root / "snapshots"
        self.checkpoint_dir = root / "checkpoints"
        self.snapshot_path = self.snapshot_dir / "snapshots-current.jsonl.gz"
        self.decisions = 0
        self.last_floor = None

    def record_snapshot_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        try:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            if (
                self.snapshot_path.exists()
                and self.snapshot_path.stat().st_size >= self.snapshot_generation_bytes
            ):
                stamp = time.strftime("%Y%m%d-%H%M%S")
                os.replace(
                    self.snapshot_path,
                    self.snapshot_dir / f"snapshots-{stamp}-{uuid.uuid4().hex[:6]}.jsonl.gz",
                )
            with gzip.open(self.snapshot_path, "at", encoding="utf-8") as file:
                for line in lines:
                    file.write(line.rstrip("\r\n") + "\n")
            self.prune_budget()
        except OSError as exc:
            _warn("record snapshots", exc)

    def after_decision(self, policy, snapshot) -> None:
        self.decisions += 1
        changed_floor = self.last_floor is not None and snapshot.floor_key != self.last_floor
        if changed_floor or self.decisions % self.checkpoint_interval == 0:
            self.checkpoint(policy, snapshot)
        self.last_floor = snapshot.floor_key

    def before_floor_change(self, policy, next_floor) -> None:
        """Preserve the old map before policy observation clears it."""
        if self.last_floor is not None and next_floor != self.last_floor:
            self._write_map(policy, self.last_floor)

    def checkpoint(self, policy, snapshot) -> None:
        try:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            target = self.checkpoint_dir / "policy-state.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(policy_state(policy, snapshot), ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temporary, target)
        except OSError as exc:
            _warn("write checkpoint", exc)

    def _write_map(self, policy, floor) -> None:
        try:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            name = "-".join(safe_filename_component(part) for part in floor)
            (self.checkpoint_dir / f"map-left-{name}.txt").write_text(
                render_remembered_map(policy), encoding="utf-8"
            )
        except OSError as exc:
            _warn("write floor map", exc)

    def freeze(self, kind: str, policy, snapshot, decision_log: Path | None, reasons: list[str]) -> Path | None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe_kind = safe_filename_component(kind, fallback="incident")
        final = self.incident_root / f"{stamp}-{safe_kind}"
        temporary = self.incident_root / f".{final.name}-{uuid.uuid4().hex}.tmp"
        try:
            temporary.mkdir(parents=True)
            tail = b""
            if decision_log is not None and decision_log.exists():
                with decision_log.open("rb") as file:
                    file.seek(max(0, decision_log.stat().st_size - INCIDENT_DECISION_TAIL_BYTES))
                    tail = file.read()
            (temporary / "decision-tail.jsonl").write_bytes(tail)
            captured = temporary / "snapshots"
            captured.mkdir()
            if self.snapshot_dir.exists():
                remaining = INCIDENT_SNAPSHOT_BYTES
                sources = sorted(
                    self.snapshot_dir.glob("*.gz"),
                    key=lambda path: path.stat().st_mtime_ns,
                    reverse=True,
                )
                for source in sources:
                    size = source.stat().st_size
                    if size > remaining and remaining < INCIDENT_SNAPSHOT_BYTES:
                        continue
                    shutil.copy2(source, captured / source.name)
                    remaining -= size
                    if remaining <= 0:
                        break
            (temporary / "policy-state.json").write_text(
                json.dumps(policy_state(policy, snapshot), ensure_ascii=False),
                encoding="utf-8",
            )
            (temporary / "remembered-map.txt").write_text(
                render_remembered_map(policy, snapshot), encoding="utf-8"
            )
            meta = {
                "kind": kind,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "turn": snapshot.turn,
                "floor": jsonable(snapshot.floor_key),
                "position": jsonable(snapshot.player.position),
                "last_reasons": reasons[-20:],
            }
            (temporary / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (temporary / "README.md").write_text(
                f"# Automatic incident capture\n\nStop kind: `{kind}`; turn: {snapshot.turn}; "
                f"floor: `{snapshot.floor_key}`.\n",
                encoding="utf-8",
            )
            self.incident_root.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, final)
            return final
        except OSError as exc:
            _warn("freeze incident", exc)
            return None

    def prune_budget(self) -> None:
        """Remove oldest rotated snapshots only; incidents and live logs are sacred."""
        try:
            files = [
                path
                for path in self.root.rglob("*")
                if path.is_file()
            ]
            incidents = (
                [path for path in self.incident_root.rglob("*") if path.is_file()]
                if self.incident_root.exists()
                else []
            )
            total = sum(path.stat().st_size for path in files + incidents)
            rotated = sorted(
                (
                    path
                    for path in self.snapshot_dir.glob("snapshots-*.jsonl.gz")
                    if path != self.snapshot_path
                ),
                key=lambda path: path.stat().st_mtime_ns,
            )
            for path in rotated:
                if total <= self.budget_bytes:
                    break
                size = path.stat().st_size
                path.unlink()
                total -= size
        except OSError as exc:
            _warn("prune snapshot history", exc)
