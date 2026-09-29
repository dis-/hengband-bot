"""Summarize one S3.3 live window from decision and state JSONL logs.

Usage: python scripts/s3_live_report.py DECISIONS STATES --start ISO --end ISO
The sibling ownership-metrics.jsonl supplies classified stop records when present.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hengbot.stop_shape import SHAPES, classify_stop  # noqa: E402


OBSERVATION_WAITS = {
    "store:entry-await-observation",
    "shop:one-shot-in-flight",
    "home:atomic-deposit-await-confirmation",
    "home:atomic-withdraw-await-confirmation",
}


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def rows_in_window(path: Path, start: datetime, end: datetime):
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
                when = timestamp(row["time"])
            except (KeyError, TypeError, ValueError):
                continue  # A live writer may have left a partial final line.
            if start <= when < end:
                yield row


def summarize(decisions: Path, states: Path, start: datetime, end: datetime,
              metrics: Path | None = None) -> dict:
    if end <= start:
        raise ValueError("end must be after start")
    hours = (end - start).total_seconds() / 3600
    decision_rows = list(rows_in_window(decisions, start, end))
    state_rows = list(rows_in_window(states, start, end))
    metric_rows = list(rows_in_window(metrics or decisions.with_name(
        "ownership-metrics.jsonl"), start, end))
    stops = [row for row in metric_rows if row.get("kind") == "stop"]
    # Older or synthetic decision logs may hold stops directly.
    if not stops:
        stops = [row for row in decision_rows if row.get("kind") == "stop"]
    shapes = Counter()
    for row in stops:
        shape = row.get("shape")
        if shape not in SHAPES:
            shape = classify_stop(
                kind=row.get("stop_kind", "other"),
                reasons=row.get("recent_reasons") or [],
                terminal=row.get("terminal"),
            ).shape
        shapes[shape] += 1

    violations = 0
    conflicts = 0
    deferred = 0
    waits = Counter()
    typed_stops = []
    for row in decision_rows:
        claim = row.get("claim") or {}
        violation = claim.get("violation")
        if isinstance(violation, dict) and violation.get("scope") == "S3":
            violations += 1
        violations += sum(1 for item in claim.get("purpose_duplicates") or []
                          if isinstance(item, dict) and item != violation)
        conflicts += bool(claim.get("claim_verdict_conflict"))
        deferred += len(claim.get("errand_deferred") or [])
        reason = row.get("reason") or ""
        if row.get("key") == "" and reason in OBSERVATION_WAITS:
            waits[reason] += 1
        if (reason.startswith("ownership:holder-silent:")
                or "owner-retired" in reason
                or "barrier-provenance-missing" in reason):
            typed_stops.append((row.get("decision_sequence"), reason))
    return {
        "minutes": (end - start).total_seconds() / 60,
        "decisions": len(decision_rows), "states": len(state_rows),
        "stops": dict(shapes),
        "stops_per_hour": {name: shapes[name] / hours for name in SHAPES},
        "s3_violations": violations, "s3_violations_per_hour": violations / hours,
        "claim_verdict_conflict": conflicts, "errand_deferred": deferred,
        "typed_stops": typed_stops, "typed_observation_waits": dict(waits),
    }


def format_report(result: dict) -> str:
    lines = [f"run minutes: {result['minutes']:.1f}",
             f"decisions: {result['decisions']}; state rows: {result['states']}",
             "stops/h by shape: " + ", ".join(
                 f"{name}={result['stops_per_hour'][name]:.2f}" for name in SHAPES),
             f"S3 violations/h: {result['s3_violations_per_hour']:.2f} "
             f"({result['s3_violations']} total)",
             f"claim_verdict_conflict: {result['claim_verdict_conflict']}",
             f"errand_deferred: {result['errand_deferred']}",
             "typed stops:"]
    lines += [f"  {sequence}: {reason}" for sequence, reason in result["typed_stops"]]
    lines.append("typed observation waits: " + (
        ", ".join(f"{name}={count}" for name, count in sorted(
            result["typed_observation_waits"].items())) or "none"))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("states", type=Path)
    parser.add_argument("--start", required=True, type=timestamp)
    parser.add_argument("--end", required=True, type=timestamp)
    parser.add_argument("--metrics", type=Path)
    args = parser.parse_args()
    print(format_report(summarize(args.decisions, args.states,
                                  args.start, args.end, args.metrics)))


if __name__ == "__main__":
    main()
