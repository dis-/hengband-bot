"""Persistent, user-approved disposal of consumables idling in the Home."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Iterable


Signature = tuple[str, int, int]
CONSUMABLE_TVALS = frozenset({55, 65, 66, 70, 75, 80})
VALID_DECISIONS = frozenset({"keep", "sell", "destroy"})


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
        self.withdrawn: set[Signature] = set()
        self.decisions: dict[Signature, str] = {}
        self._load_history()
        self.reload_decisions()

    @classmethod
    def in_repo(cls, root: Path | None = None) -> "HomeDisposalState":
        root = Path.cwd() if root is None else Path(root)
        return cls(
            root / "home-withdraw-history.jsonc",
            root / "home-disposal-decisions.jsonc",
            root / "jsonlog" / "home-disposal-queue.json",
            root / "jsonlog" / "sol-events.jsonl",
        )

    @staticmethod
    def _read_json(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _load_history(self) -> None:
        data = self._read_json(self.history_path)
        if not isinstance(data, dict):
            return
        self.recall_count = max(0, int(data.get("dungeon_recall_count", 0)))
        records = data.get("transactions", [])
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict):
                continue
            signature = parse_signature(record.get("signature"))
            if signature is None or record.get("action") not in {"deposit", "withdraw"}:
                continue
            self.history.append(record)
            if record["action"] == "withdraw":
                self.withdrawn.add(signature)

    def _save_history(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "dungeon_recall_count": self.recall_count,
            "transactions": self.history,
        }
        temporary = self.history_path.with_suffix(self.history_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Antivirus/indexers and concurrent readers can briefly hold the old
        # file without delete sharing on Windows.  Preserve atomic replacement,
        # but tolerate that transient sharing violation instead of killing the
        # gameplay bot.
        for attempt in range(5):
            try:
                temporary.replace(self.history_path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

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
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
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
        self.queue_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
