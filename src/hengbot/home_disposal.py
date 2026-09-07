"""Persistent, user-approved disposal of consumables idling in the Home."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable


Signature = tuple[str, int, int]
CONSUMABLE_TVALS = frozenset({55, 65, 66, 70, 75, 80})
VALID_DECISIONS = frozenset({"keep", "sell", "destroy"})
HOME_HISTORY_DIR_ENV = "HENGBOT_HOME_HISTORY_DIR"


class HomeDisposalReadError(OSError):
    """A durable disposal file remained unreadable after bounded retries."""


def signature_key(signature: Signature) -> str:
    """Unambiguous JSON-object key for a player-visible item signature."""
    return json.dumps(list(signature), ensure_ascii=False, separators=(",", ":"))


def parse_signature(value: object) -> Signature | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return str(value[0]), int(value[1]), int(value[2])
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class HomeDisposalCandidate:
    signature: Signature
    name: str
    tval: int
    sval: int
    count: int
    aware: bool
    known: bool


class HomeDisposalState:
    """Owns durable history/cadence and hot-reloaded approval decisions."""

    def __init__(
        self,
        history_path: Path,
        decisions_path: Path,
        queue_path: Path,
        events_path: Path,
    ) -> None:
        self.history_path = Path(history_path)
        self.decisions_path = Path(decisions_path)
        self.queue_path = Path(queue_path)
        self.events_path = Path(events_path)
        self.recall_count = 0
        self.history: list[dict[str, object]] = []
        self._unloadable_history: list[object] = []
        self.withdrawn: set[Signature] = set()
        self.decisions: dict[Signature, str] = {}
        self._load_history()
        self.reload_decisions()

    @classmethod
    def in_repo(cls, root: Path | None = None) -> "HomeDisposalState":
        if root is None:
            root = Path(os.environ.get(HOME_HISTORY_DIR_ENV, Path.cwd()))
        else:
            root = Path(root)
        return cls(
            root / "home-withdraw-history.jsonc",
            root / "home-disposal-decisions.jsonc",
            root / "jsonlog" / "home-disposal-queue.json",
            root / "jsonlog" / "sol-events.jsonl",
        )

    @staticmethod
    def _loadable_history_record(record: object) -> bool:
        return (
            isinstance(record, dict)
            and parse_signature(record.get("signature")) is not None
            and record.get("action") in {"deposit", "withdraw"}
        )

    @staticmethod
    def _read_json(path: Path) -> object:
        for attempt in range(3):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return {}
            except OSError as error:
                if attempt == 2:
                    raise HomeDisposalReadError(
                        f"cannot read Home disposal state after 3 attempts: {path}"
                    ) from error
                time.sleep(0.05 * (attempt + 1))
            except ValueError:
                return {}
        raise AssertionError("unreachable")

    @staticmethod
    def _atomic_write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
        try:
            for attempt in range(5):
                try:
                    temporary.replace(path)
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _load_history(self) -> None:
        data = self._read_json(self.history_path)
        if not isinstance(data, dict):
            return
        self.recall_count = max(0, int(data.get("dungeon_recall_count", 0)))
        records = data.get("transactions", [])
        if not isinstance(records, list):
            return
        for record in records:
            if not self._loadable_history_record(record):
                self._unloadable_history.append(record)
                continue
            assert isinstance(record, dict)
            signature = parse_signature(record.get("signature"))
            assert signature is not None
            self.history.append(record)
            if record["action"] == "withdraw":
                self.withdrawn.add(signature)

    def _save_history(self) -> None:
        disk_data = self._read_json(self.history_path)
        unloadable = self._unloadable_history
        if isinstance(disk_data, dict):
            disk_records = disk_data.get("transactions", [])
            if isinstance(disk_records, list):
                disk_loadable = sum(self._loadable_history_record(record) for record in disk_records)
                unloadable = [record for record in disk_records if not self._loadable_history_record(record)]
            else:
                disk_loadable = 0
            if disk_loadable > len(self.history):
                raise RuntimeError(
                    "refusing to shrink Home transaction history "
                    f"from {disk_loadable} to {len(self.history)} loadable records"
                )
        payload = {
            "version": 1,
            "dungeon_recall_count": self.recall_count,
            # Preserve records this version cannot interpret instead of
            # silently deleting them during the next durable update.
            "transactions": [*unloadable, *self.history],
        }
        self._atomic_write_json(self.history_path, payload)

    def record(self, action: str, signature: Signature, turn: int) -> None:
        if action not in {"deposit", "withdraw"}:
            raise ValueError(f"invalid Home transaction: {action}")
        self.history.append({
            "action": action,
            "signature": list(signature),
            "turn": int(turn),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if action == "withdraw":
            self.withdrawn.add(signature)
        self._save_history()

    def note_dungeon_recall(self) -> bool:
        self.recall_count += 1
        self._save_history()
        return self.recall_count % 5 == 0

    def reload_decisions(self) -> None:
        data = self._read_json(self.decisions_path)
        if isinstance(data, dict) and isinstance(data.get("decisions"), dict):
            data = data["decisions"]
        loaded: dict[Signature, str] = {}
        if isinstance(data, dict):
            for raw_signature, decision in data.items():
                try:
                    signature = parse_signature(json.loads(raw_signature))
                except (TypeError, ValueError):
                    signature = None
                if signature is not None and decision in VALID_DECISIONS:
                    loaded[signature] = decision
        self.decisions = loaded

    def decision(self, signature: Signature) -> str | None:
        return self.decisions.get(signature)

    def is_idle(self, signature: Signature) -> bool:
        return signature not in self.withdrawn

    def pending(self, candidates: Iterable[HomeDisposalCandidate]) -> list[HomeDisposalCandidate]:
        unique: dict[Signature, HomeDisposalCandidate] = {}
        for candidate in candidates:
            if candidate.tval not in CONSUMABLE_TVALS:
                continue
            if self.is_idle(candidate.signature) and candidate.signature not in self.decisions:
                unique.setdefault(candidate.signature, candidate)
        return list(unique.values())

    def emit_queue(self, candidates: Iterable[HomeDisposalCandidate], turn: int) -> None:
        pending = self.pending(candidates)
        self._read_json(self.queue_path)
        payload = {
            "version": 1,
            "generated_turn": int(turn),
            "items": [
                {
                    "signature": list(item.signature),
                    "signature_key": signature_key(item.signature),
                    "name": item.name,
                    "tval": item.tval,
                    "sval": item.sval,
                    "count": item.count,
                    "aware": item.aware,
                    "known": item.known,
                    "proposed_default_action": "identify-then-sell",
                }
                for item in pending
            ],
        }
        self._atomic_write_json(self.queue_path, payload)
        if pending:
            event = {
                "event": "question",
                "kind": "home-idle-consumable-disposal",
                "turn": int(turn),
                "queue": str(self.queue_path),
                "count": len(pending),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with self.events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
