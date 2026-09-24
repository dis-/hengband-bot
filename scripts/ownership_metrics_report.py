"""Read the ownership ledgers and print the baseline and the S1 metric.

Read-only: it opens the ledgers for reading and writes nothing except its own
stdout, or the file given with ``--output``.

    python scripts/ownership_metrics_report.py jsonlog/ownership-metrics.jsonl

It prints, per session and in total: the runtime and which end of the session
it came from (``session-end`` when the process exited cleanly, otherwise the
last decision row it recorded, which is all a killed process leaves), the
number of decisions, the stops per runtime hour for each shape, and the
approximation of design section 5.2 - the rate of ``arbiter.owner`` changes
per runtime hour - together with its blind spot.

It then reads the S1 claim ledger beside it (``--claims`` to name another
file) and prints design section 5.2 proper: **implicit owner changes per
runtime hour**, broken down by (from family, to family) - rows whose owner
changed while nothing had ended the previous claim.  The same count is printed
twice more: by ``producer``, which separates the dungeon producers the two
catch-all families hold, and by ``claim_id``, which counts every unended claim
that gave way to another.  The first is the number design 5.2 gates S2 on; the
other two say where it is hiding when the family breakdown looks quiet.

Last, the four numbers S2b's gate reads (design rev 9.1 item 4,
``ownership_metrics.gate_numbers``): (a) owner changes that left a Reach /
Observe claim unclosed, (b) the same owner replacing its own unclosed Reach /
Observe goal, both outside survival; (c) how every Reach / Observe claim ended,
per owner and kind, with ``goal_missing`` per owner; and (d) Terminal claims
that spanned several rows while the player moved.  Since a Terminal claim now
closes when it is posted, the implicit-handoff counts above fall mechanically;
(c) and (d) are printed beside them so a fall caused by wrong typing shows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hengbot.ownership_metrics import (  # noqa: E402
    ENDINGS,
    OWNERSHIP_CLAIMS_NAME,
    RUNTIME_SOURCE_LAST_DECISION,
    RUNTIME_SOURCE_NONE,
    aggregate,
    gate_numbers,
    implicit_handoffs,
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


CLAIM_BREAKDOWNS = ("owner", "producer", "claim_id")
NO_CLAIM_LEDGER = (
    "No S1 claim ledger was found beside the session ledger, so design 5.2's "
    "implicit-handoff rate cannot be computed.  Only the arbiter.owner "
    "approximation above is available, and it is town-only."
)


def gate_report(rows, hours: float | None = None, *, owner_of=None) -> list[str]:
    """Design rev 9.1 item 4: the four numbers S2b's gate reads."""
    gate = gate_numbers(rows, owner_of=owner_of)

    def rate(count: int) -> str:
        return f"{count / hours:.3f}" if hours else "n/a"

    dropped = gate["dropped_by_other_owner"]
    retargets = gate["retargets"]
    mistyped = gate["mistyped_terminal"]
    lines = [
        "S2b gate (design rev 9.1 item 4), outside survival for (a)/(b):",
        f"(a) owner changes with the previous Reach/Observe claim not closed "
        f"{dropped['count']:>5}   per runtime hour {rate(dropped['count'])}",
    ]
    for pair, times in list(dropped["pairs"].items())[:20]:
        lines.append(f"    {pair:<48} {times}")
    lines.append(
        f"(b) same owner replacing its unclosed Reach/Observe goal      "
        f"{retargets['count']:>5}   per runtime hour {rate(retargets['count'])}"
    )
    for owner, times in list(retargets["by_owner"].items())[:20]:
        lines.append(f"    {owner:<48} {times}")
    lines.append(
        "(c) how Reach/Observe claims ended, per owner/kind: "
        + " / ".join(ENDINGS)
    )
    for name, counts in gate["endings"].items():
        lines.append(
            f"    {name:<40} "
            + " ".join(f"{counts[ending]:>5}" for ending in ENDINGS)
        )
    if not gate["endings"]:
        lines.append("    (no Reach/Observe claim)")
    lines.append("    goal_missing rows per owner:")
    for owner, times in gate["goal_missing"].items():
        lines.append(f"      {owner:<46} {times}")
    if not gate["goal_missing"]:
        lines.append("      (none)")
    lines.append(
        f"(d) multi-row Terminal claims whose position changed           "
        f"{mistyped['count']:>5}   (position unknown: "
        f"{mistyped['position_unknown']})"
    )
    for owner, times in list(mistyped["by_owner"].items())[:20]:
        lines.append(f"    {owner:<48} {times}")
    return lines


def claim_report(rows, hours: float | None) -> list[str]:
    """Design 5.2, from the claim ledger: implicit owner changes per hour."""
    lines = [f"claim rows     {len(rows)}"]
    for by in CLAIM_BREAKDOWNS:
        measured = implicit_handoffs(rows, by=by)
        count = measured["implicit_handoffs"]
        rate = (
            f"{count / hours:.3f}" if hours else "n/a"
        )
        lines.append(
            f"implicit handoffs by {by:<9} {count:>5}   per runtime hour {rate}"
        )
        for pair, times in list(measured["pairs"].items())[:20]:
            lines.append(f"    {pair:<48} {times}")
        if not measured["pairs"]:
            lines.append("    (none)")
    lines.extend(gate_report(rows, hours))
    return lines


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}"


def render(summaries, totals, claim_rows=None) -> str:
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
    share = totals["claim_share"]
    lines.append(
        f"decision rows carrying a claim_id {totals['claims']} "
        + (f"(share {share:.3f})" if share is not None else "(share n/a)")
    )
    lines.append("")
    if claim_rows:
        lines.extend(claim_report(claim_rows, totals["runtime_hours"]))
    else:
        lines.append(NO_CLAIM_LEDGER)
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
        "--claims", type=Path, default=None,
        help=(
            "the S1 claim ledger; by default the "
            f"{OWNERSHIP_CLAIMS_NAME} beside the session ledger"
        ),
    )
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
    claims_path = (
        args.claims
        if args.claims is not None
        else args.ledger.with_name(OWNERSHIP_CLAIMS_NAME)
    )
    claim_rows = read_records(claims_path) if claims_path.exists() else []
    if args.json:
        text = json.dumps(
            {
                "sessions": summaries,
                "totals": totals,
                "claims": {
                    "path": str(claims_path),
                    "rows": len(claim_rows),
                    "runtime_hours": totals["runtime_hours"],
                    "breakdowns": [
                        implicit_handoffs(claim_rows, by=by)
                        for by in CLAIM_BREAKDOWNS
                    ],
                    "gate": gate_numbers(claim_rows),
                },
                "blind_spot": BLIND_SPOT,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    else:
        text = render(summaries, totals, claim_rows)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
