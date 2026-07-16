"""One-line economy summary from the EconomyLedger JSONL, for status events.

The operator runs this each monitoring cycle and pastes the line into its
status event, so the ledger aggregation stays deterministic and costs the
operator nothing to compute.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def summarize(path: Path, since_minutes: int, now: float | None = None) -> str:
    cutoff = (now if now is not None else time.time()) - since_minutes * 60
    income = expense = mining = picks = 0
    events = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            stamp = time.mktime(
                time.strptime(row["time"][:19], "%Y-%m-%dT%H:%M:%S")
            )
        except (KeyError, ValueError):
            continue
        if stamp < cutoff:
            continue
        events += 1
        if row.get("kind") == "income":
            income += row.get("amount", 0)
            if str(row.get("cause_reason", "")).startswith("fundraise:"):
                mining += row.get("amount", 0)
                picks += 1
        else:
            expense += row.get("amount", 0)
    net = income - expense
    rate = net / since_minutes if since_minutes else 0.0
    return (
        f"economy[{since_minutes}m]: income {income}g"
        f" (mining {mining}g/{picks} picks), expense {expense}g,"
        f" net {net:+}g, {rate:.1f} g/min, {events} events"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--since-minutes", type=int, default=60)
    args = parser.parse_args(argv)
    if not args.ledger.exists():
        print(f"economy[{args.since_minutes}m]: no ledger yet")
        return 0
    print(summarize(args.ledger, args.since_minutes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
