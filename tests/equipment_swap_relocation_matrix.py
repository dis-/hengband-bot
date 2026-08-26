"""Reproduce the 504-cell equipment-transaction relocation measurement."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import json

from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_FINALIZE,
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy, TOWN_TRAVEL_STORE_SYMBOLS


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"
RAG = "8cc0213094bf60d5"
HARD = "ba9b081829fa4479"
TRAVEL = "\x1b`n!."
REASONS = (
    "equipment-transaction:await-confirmation",
    "stuck:wander",
    "novel:explore",
    "breakout:least-visited",
    "town:wait-restock:magic",
    "town:cycle-break",
    "town:blocked:repetition",
)
BLOCKERS = ((), ("home-route-unavailable",), ("equip-item-missing:hard",))
POSITIONS = ((45, 123), (31, 119), (45, 93))


def _surface_snapshot():
    with SNAPSHOTS.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") != 1172205 or row.get("store") is not None:
                continue
            snapshot = parse_snapshot(row, {})
            if snapshot.store is None:
                return snapshot
    raise RuntimeError("capture entry snapshot is missing")


def _plans():
    equip = EquipmentTransaction(PHASE_EQUIP, "equip", "hard", "body", HARD)
    deposit = EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", "rag", None, RAG)
    withdraw = EquipmentTransaction(PHASE_HOME_PREPARE, "withdraw", "hard", None, HARD)
    return (
        ("equip+home_finalize", (equip, deposit)),
        ("home_prepare+equip", (withdraw, equip)),
        ("equip-only", (equip,)),
        ("empty-remainder", ()),
    )


def measure():
    """Return (relocating cells, total cells, survivor descriptions)."""
    base = _surface_snapshot()
    survivors = []
    total = 0
    for y, x in POSITIONS:
        snapshot = replace(
            base,
            player=replace(base.player, position=replace(base.player.position, y=y, x=x)),
        )
        for plan_name, actions in _plans():
            for blockers in BLOCKERS:
                for owned in ((), ((RAG, "body"),)):
                    for reason in REASONS:
                        total += 1
                        policy = HengbotPolicy()
                        session = EquipmentTransactionSession(
                            EquipmentTransactionPlan(actions, (), 0)
                        )
                        for blocker in blockers:
                            session.block(blocker)
                        policy._equipment_transaction_session = session
                        policy._equipment_transaction_owned_items = list(owned)

                        policy.last_reason = reason
                        with patch.object(
                            policy,
                            "_town_procurement_progress_key",
                            return_value=(TRAVEL, "town-progress-invariant:approach"),
                        ):
                            key = policy.choose_key(snapshot)
                        if (
                            len(key) >= 5
                            and key.startswith("\x1b`n")
                            and key.endswith(".")
                            and key[3] in TOWN_TRAVEL_STORE_SYMBOLS
                            and TOWN_TRAVEL_STORE_SYMBOLS.index(key[3]) != 7
                        ):
                            survivors.append(
                                (y, x, plan_name, blockers, bool(owned), reason, key)
                            )
    return len(survivors), total, survivors


if __name__ == "__main__":
    relocating, total, survivors = measure()
    print(f"{relocating}/{total} relocating")
    for survivor in survivors[:20]:
        print(repr(survivor))
    raise SystemExit(bool(relocating))
