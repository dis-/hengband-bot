"""Read the S0 ownership metrics ledger and print the baseline.

Read-only: it opens the ledger for reading and writes nothing except its own
stdout, or the file given with ``--output``.

    python scripts/ownership_metrics_report.py jsonlog/ownership-metrics.jsonl

It prints, per session and in total: the runtime and which end of the session
it came from (``session-end`` when the process exited cleanly, otherwise the
last decision row it recorded, which is all a killed process leaves), the
number of decisions, the stops per runtime hour for each shape, and the
approximation of design section 5.2 - the rate of ``arbiter.owner`` changes
per runtime hour - together with its blind spot.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hengbot.ownership_metrics import (  # noqa: E402
    RUNTIME_SOURCE_LAST_DECISION,
    RUNTIME_SOURCE_NONE,
    aggregate,
    read_records,
    summarise_sessions,
)
from hengbot.stop_shape import SHAPES  # noqa: E402


BLIND_SPOT = (
    "Blind spot of the arbiter.owner rate (design 5.2): the town turn arbiter "
    "only runs in town and clears itself when the board is not a town one "
    "(town_arbiter.py), so dungeon decisions carry no owner and no change of "
    "one is visible there.  The town share of decisions printed above says "
    "how much of the measured work the rate can see; the 2026-09-23 06:00 "
    "stop happened in the part it cannot."
)


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}"


def render(summaries, totals) -> str:
    lines = [f"ownership metrics: {totals['sessions']} session(s)", ""]
    for summary in summaries:
        counts: dict[str, int] = {}
        for stop in summary["stops"]:
            counts[stop["shape"]] = counts.get(stop["shape"], 0) + 1
        lines.append(
            f"session {summary['session']} pid={summary['pid']} "
            f"commit={summary['git_commit']}"
        )
        lines.append(
            f"  start        {summary['start_time']}"
        )
        lines.append(
            f"  runtime      {_duration(summary['runtime_seconds'])} "
            f"(source: {summary['runtime_source']}"
            + (
                f", end {summary['end_time']} how={summary['end_how']})"
                if summary["end_how"]
                else f", last decision {summary['last_decision_time']} "
                f"#{summary['last_decision_sequence']})"
            )
        )
        lines.append(
            f"  decisions    {summary['decisions']} "
            f"(town {summary['town_decisions']}), "
            f"arbiter.owner changes {summary['arbiter_owner_changes']}"
        )
        if summary["stops"]:
            for stop in summary["stops"]:
                lines.append(
                    f"  stop         {stop['time']} {stop['stop_kind']} "
                    f"-> {stop['shape']} ({stop['rule']})"
                )
        else:
            lines.append("  stop         none recorded")
        if counts:
            lines.append(
                "  shapes       "
                + ", ".join(f"{shape}={counts[shape]}" for shape in sorted(counts))
            )
        lines.append("")

    hours = totals["runtime_hours"]
    lines.append(f"total runtime  {_duration(totals['runtime_seconds'])} "
                 f"({hours:.3f} h)")
    lines.append(
        "runtime source " + ", ".join(
            f"{source}={count}"
            for source, count in sorted(totals["runtime_sources"].items())
        )
    )
    lines.append(f"decisions      {totals['decisions']} "
                 f"(town {totals['town_decisions']})")
    lines.append(f"stops          {totals['stops_total']}")
    for shape in SHAPES:
        count = totals["stops"].get(shape, 0)
        rate = (
            f"{totals['stops_per_hour'][shape]:.3f}"
            if totals["stops_per_hour"] is not None
            else "n/a"
        )
        lines.append(f"  {shape:<22} {count:>4}   per runtime hour {rate}")
    rate = totals["arbiter_owner_changes_per_hour"]
    lines.append(
        f"arbiter.owner changes {totals['arbiter_owner_changes']}   "
        f"per runtime hour "
        + (f"{rate:.3f}" if rate is not None else "n/a")
    )
    town_share = (
        totals["town_decisions"] / totals["decisions"]
        if totals["decisions"]
        else None
    )
    lines.append(
        "town share of decisions "
        + (f"{town_share:.3f}" if town_share is not None else "n/a")
    )
    lines.append("")
    lines.append(BLIND_SPOT)
    unknown = totals["runtime_sources"].get(RUNTIME_SOURCE_NONE, 0)
    recovered = totals["runtime_sources"].get(RUNTIME_SOURCE_LAST_DECISION, 0)
    if recovered or unknown:
        lines.append(
            f"{recovered} session(s) had no session-end and were measured from "
            f"their last decision row; {unknown} recorded no decision at all "
            "and contribute no runtime."
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, help="jsonlog/ownership-metrics.jsonl")
    parser.add_argument(
        "--output", type=Path, default=None,
        help="write the report to this file instead of stdout",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit the summaries and totals as JSON",
    )
    args = parser.parse_args(argv)
    if not args.ledger.exists():
        print(f"no ledger at {args.ledger}", file=sys.stderr)
        return 2
    summaries = summarise_sessions(read_records(args.ledger))
    totals = aggregate(summaries)
    if args.json:
        text = json.dumps(
            {"sessions": summaries, "totals": totals, "blind_spot": BLIND_SPOT},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    else:
        text = render(summaries, totals)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
