"""Passive, per-decision capture of a Home approach and store session."""

from __future__ import annotations

import base64
import json
import pickle
import sys
from pathlib import Path
from typing import Any

from hengbot.flight_recorder import jsonable
from hengbot.latch_onset_capture import checkpoint
from hengbot.model import STORE_HOME, Snapshot


STATE_FIELDS = (
    "_shopping_approach_store_type",
    "_shopping_approach_goal",
    "_store_entry_wait_owner",
    "_store_entry_wait_key",
    "_store_entry_posted_owner",
    "_store_entry_failed_owner",
    "_store_leave_inflight",
    "_last_snapshot_store_type",
    "_home_entry_operation_posted",
    "_home_pending_item",
    "_home_pending_slot",
    "_home_pending_quantity",
    "_home_pending_batch",
    "_home_atomic_withdraw_pending",
    "_home_atomic_deposit_pending",
    "_home_knowledge_current",
    "_home_knowledge_valid_before",
    "_home_page_size",
    "_home_knowledge_scan_requested",
    "_home_knowledge_scan_inflight",
    "_home_knowledge_scan_retries_remaining",
    "_home_knowledge_scan_leave_turn",
    "_home_scan_source",
    "_home_scan_item_count",
)


def _store_projection(snapshot: Snapshot) -> dict[str, Any] | None:
    store = snapshot.store
    if store is None:
        return None
    return {
        "store_type": store.store_type,
        "stock_num": getattr(store, "stock_num", None),
        "page_top": getattr(store, "page_top", None),
        "page_size": getattr(store, "page_size", None),
        "item_count": len(store.items),
    }


def snapshot_projection(snapshot: Snapshot) -> dict[str, Any]:
    """Project the fields needed to identify the observed entry sequence."""
    return {
        "type": type(snapshot).__name__,
        "turn": snapshot.turn,
        "store": _store_projection(snapshot),
        "messages": list(snapshot.messages),
        "player_position": jsonable(snapshot.player.position),
    }


def state_projection(policy: Any) -> dict[str, Any]:
    """Name every scan/entry term captured at the decision boundary."""
    return {name: jsonable(getattr(policy, name, None)) for name in STATE_FIELDS}


def _home_owned(policy: Any, snapshot: Snapshot) -> bool:
    store = snapshot.store
    return bool(
        (store is not None and store.store_type == STORE_HOME)
        or getattr(policy, "_shopping_approach_store_type", None) == STORE_HOME
        or getattr(policy, "_store_entry_wait_owner", None) == STORE_HOME
        or getattr(policy, "_store_entry_posted_owner", None) == STORE_HOME
        or getattr(policy, "_home_scan_prepared", False)
        or getattr(policy, "_home_scan_burst_pending", False)
        or getattr(policy, "_home_scan_burst_short", False)
        or getattr(policy, "_home_scan_processing", False)
    )


class HomeEntryCapture:
    """Join decisions, posted WM_CHARs, and the next snapshot read by the CLI."""

    def __init__(self, path: Path | None):
        self.path = path
        self.active = False
        self.pending: dict[str, Any] | None = None
        self._reported_failures: set[tuple[str, str, str]] = set()

    def report_failure(
        self, operation: str, exc: Exception, field: str = "unknown"
    ) -> None:
        """Expose a diagnostic failure once without endangering gameplay."""
        identity = (operation, type(exc).__name__, f"{field}:{exc}")
        if identity in self._reported_failures:
            return
        self._reported_failures.add(identity)
        marker = {
            "format": 1,
            "capture_error": True,
            "operation": operation,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "field": field,
        }
        print(
            "home-entry-capture "
            f"{operation} failed at {field}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        try:
            self._write(marker)
        except Exception as marker_exc:
            print(
                "home-entry-capture error-marker write failed at path: "
                f"{type(marker_exc).__name__}: {marker_exc}",
                file=sys.stderr,
            )

    def choose_key(self, policy: Any, snapshot: Snapshot) -> str:
        """Capture one call through the policy's public decision boundary."""
        boundary = None
        try:
            boundary = self.before_decision(policy, snapshot)
        except Exception as exc:
            self.report_failure("before_decision", exc, "policy checkpoint/state")
        key = policy._choose_key_with_latch_capture(snapshot)
        if boundary is not None:
            try:
                self.record_decision(
                    policy, snapshot, key, policy.last_reason, *boundary
                )
            except Exception as exc:
                self.report_failure("record_decision", exc, "decision record")
        return key

    def observe_snapshot(self, snapshot: Snapshot) -> None:
        """Attach the first subsequently read snapshot to the pending decision."""
        if self.pending is None:
            return
        self.pending["next_snapshot"] = snapshot_projection(snapshot)
        self.pending["next_snapshot_pickle_b64"] = base64.b64encode(
            pickle.dumps(snapshot, protocol=5)
        ).decode("ascii")
        self._write(self.pending)
        self.pending = None

    def record_decision(
        self,
        policy: Any,
        snapshot: Snapshot,
        key: str,
        reason: str,
        predecision_checkpoint: str,
        predecision_state: dict[str, Any],
        owned_before: bool,
    ) -> None:
        """Start a join record after the public choose_key has returned."""
        owned_after = _home_owned(policy, snapshot)
        if not (self.active or owned_before or owned_after):
            return
        self.active = True
        self.pending = {
            "format": 1,
            "decision_index": policy._decision_sequence,
            "last_reason": reason,
            "key": key,
            "posted_characters": [],
            "decision_snapshot": snapshot_projection(snapshot),
            "next_snapshot": None,
            "scan_entry_state": predecision_state,
            "predecision_policy_checkpoint_pickle_b64": predecision_checkpoint,
            "decision_snapshot_pickle_b64": base64.b64encode(
                pickle.dumps(snapshot, protocol=5)
            ).decode("ascii"),
            "next_snapshot_pickle_b64": None,
        }
        if not owned_after:
            # This closing decision is retained; its next observation completes
            # the record before capture becomes idle.
            self.active = False

    def record_posted_character(self, decision_index: int, character: str) -> None:
        if self.pending is None:
            return
        if self.pending["decision_index"] == decision_index:
            self.pending["posted_characters"].append(character)

    def before_decision(
        self, policy: Any, snapshot: Snapshot
    ) -> tuple[str, dict[str, Any], bool]:
        """Take an exact checkpoint before public choose_key mutates policy."""
        return checkpoint(policy), state_projection(policy), _home_owned(policy, snapshot)

    def _write(self, record: dict[str, Any]) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")
