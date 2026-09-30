"""Summarize OFF S3.3 verdicts in a half-open live decision-log window.

python scripts/s33_shadow_report.py DECISIONS --start ISO --end ISO [--json]
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import json

from s3_live_report import rows_in_window, timestamp


def summarize(decisions, start, end):
    if end <= start:
        raise ValueError("end must be after start")
    stops = Counter()
    first = {}
    gaps, mismatches, leaks, skips = (Counter() for _ in range(4))
    count = shadow_count = 0
    for row in rows_in_window(Path(decisions), start, end):
        count += 1
        shadow = row.get("s33_shadow")
        if shadow is None:
            shadow = (row.get("claim") or {}).get("s33_shadow")
        if not isinstance(shadow, dict):
            continue
        shadow_count += 1
        family = shadow.get("holder_family") or "unknown"
        reason = shadow.get("would_stop")
        if reason:
            stops[(reason, family)] += 1
            signature = (reason, family, row.get("reason"))
            first.setdefault(signature, {
                "reason": reason, "family": family,
                "producer_reason": row.get("reason"),
                "decision_sequence": row.get("decision_sequence"),
                "time": row["time"],
            })
            if reason.startswith("ownership:gate-missing:"):
                leaks[reason.rsplit(":", 1)[-1]] += 1
        if shadow.get("declaration_gap"):
            gaps[family] += 1
        if shadow.get("mismatch"):
            mismatches[family] += 1
        skips.update(set(shadow.get("would_skip_families") or ()))
    return {
        "minutes": (end - start).total_seconds() / 60,
        "decisions": count, "shadow_decisions": shadow_count,
        "would_stop": [{"reason": reason, "family": family, "count": n}
                       for (reason, family), n in sorted(stops.items())],
        "first_stops": list(first.values()),
        "declaration_gaps": dict(sorted(gaps.items())),
        "mismatches": dict(sorted(mismatches.items())),
        "gate_leaks": dict(sorted(leaks.items())),
        "would_skip": dict(sorted(skips.items())),
    }


def render(report):
    lines = [f"minutes={report['minutes']:g} decisions={report['decisions']} "
             f"shadow_decisions={report['shadow_decisions']}"]
    for stop in report["would_stop"]:
        lines.append(f"would_stop {stop['reason']} holder={stop['family']} "
                     f"count={stop['count']}")
    for first in report["first_stops"]:
        lines.append(f"first {first['reason']} holder={first['family']} "
                     f"producer={first['producer_reason']} "
                     f"sequence={first['decision_sequence']} time={first['time']}")
    for name in ("declaration_gaps", "mismatches", "gate_leaks", "would_skip"):
        lines.append(name + "=" + json.dumps(report[name], sort_keys=True))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--start", required=True, type=timestamp)
    parser.add_argument("--end", required=True, type=timestamp)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = summarize(args.decisions, args.start, args.end)
    print(json.dumps(report, ensure_ascii=False) if args.json else render(report))


if __name__ == "__main__":
    main()
