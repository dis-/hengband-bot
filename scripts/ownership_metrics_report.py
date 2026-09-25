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

Then the S2b.1 ladder numbers that replace (a) and (b) (design rev 10 item 5,
rev 10.1 items 7-8, ``ownership_metrics.ladder_numbers``): violations per
runtime hour by pair and retarget violations by owner, each split into the
in-scope families (the S2b.2 gate), the S3 families and survival;
preemptions by pair; displacements; and how suspended claims left the stack.
Rows written before the ladder are reclassified by rank through the writer's
own functions (rev 10.1 item 11).  (c) counts one final ending per claim id.

Last, the S2b.2 bar table (design 3.2 / 3.3, ``ownership_metrics.bar_numbers``):
would-bar events per owner (decisions whose owner and goal met a standing bar;
with the switch off they are only recorded), bars set per owner and kind, the
lifetimes of the bars lifted, the bars still standing when a session ended,
and the rungs a bar skipped (switch on only).
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
    bar_numbers,
    gate_numbers,
    implicit_handoffs,
    ladder_numbers,
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
    lines.append(
        f"(d) multi-row Terminal claims whose position changed           "
        f"{mistyped['count']:>5}   (position unknown: "
        f"{mistyped['position_unknown']})"
    )
    for owner, times in list(mistyped["by_owner"].items())[:20]:
        lines.append(f"    {owner:<48} {times}")
    # Rev 9.2 (D): goal_missing rows are out of (d) and on their own lines.
    missing_total = sum(gate["goal_missing"].values())
    lines.append(
        f"goal_missing rows (Reach declared Terminal)                    "
        f"{missing_total:>5}   by reason: "
        + (
            ", ".join(
                f"{reason}={times}"
                for reason, times in gate["goal_missing_by_reason"].items()
            )
            or "none"
        )
    )
    for owner, times in gate["goal_missing"].items():
        lines.append(f"    {owner:<48} {times}")
    mismatch_total = sum(gate["owner_mismatch"].values())
    lines.append(
        f"owner-mismatch rows (a slot of another owner, not used)        "
        f"{mismatch_total:>5}"
    )
    for owner, times in gate["owner_mismatch"].items():
        lines.append(f"    {owner:<48} {times}")
    return lines


LADDER_SCOPES = (
    ("in-scope", "in-scope families (the S2b.2 gate)"),
    ("S3", "S3 families (store, Home, equipment, calibration, departure in town)"),
    ("survival", "a survival claim on either side (outside the gate)"),
)


def ladder_report(rows, hours: float | None = None) -> list[str]:
    """Design rev 10 item 5 / rev 10.1 items 7-8: the S2b.1 ladder numbers.

    Rows written before the ladder are reclassified through the writer's own
    functions (``ownership_metrics.ladder_numbers``, rev 10.1 item 11).
    """
    ladder = ladder_numbers(rows)

    def rate(count: int) -> str:
        return f"{count / hours:.3f}" if hours else "n/a"

    lines = [
        "S2b.1 ladder (design rev 10.1), "
        f"{ladder['legacy_events']} older (a)/(b) event(s) reclassified by rank:",
    ]
    for scope, title in LADDER_SCOPES:
        block = ladder["violations"][scope]
        lines.append(
            f"violations, {title:<70} {block['count']:>5}   "
            f"per runtime hour {rate(block['count'])}"
        )
        for pair, times in list(block["pairs"].items())[:20]:
            lines.append(f"    {pair:<48} {times}")
    for scope, title in LADDER_SCOPES:
        block = ladder["retargets"][scope]
        lines.append(
            f"retarget violations, {title:<61} {block['count']:>5}   "
            f"per runtime hour {rate(block['count'])}"
        )
        for owner, times in list(block["by_owner"].items())[:20]:
            lines.append(f"    {owner:<48} {times}")
    preemptions = ladder["preemptions"]
    lines.append(
        f"preemptions (suspended, informational)                         "
        f"{preemptions['count']:>5}   per runtime hour {rate(preemptions['count'])}"
    )
    for pair, times in list(preemptions["pairs"].items())[:20]:
        lines.append(f"    {pair:<48} {times}")
    displacements = ladder["displacements"]
    lines.append(
        f"displacements (a suspended claim released resume-displaced)    "
        f"{displacements['count']:>5}"
    )
    for pair, times in list(displacements["pairs"].items())[:20]:
        lines.append(f"    {pair:<48} {times}")
    replaced = ladder["survival_displaced"]
    lines.append(
        f"survival displacements (exempt, not violations)               "
        f"{replaced['count']:>5}"
    )
    for pair, times in list(replaced["pairs"].items())[:20]:
        lines.append(f"    {pair:<48} {times}")
    suspended = ladder["suspended"]
    lines.append(
        "suspended claims: "
        + (
            ", ".join(f"{label}={times}" for label, times in suspended.items())
            or "none"
        )
    )
    return lines


def bar_report(rows, hours: float | None = None) -> list[str]:
    """S2b.2 (design 3.2 / 3.3): would-bar events per owner, bar lifetimes.

    Read through ``ownership_metrics.bar_numbers``.  With the switch off (the
    shipped setting) a would-bar event is only recorded: it names a decision
    the bar would have skipped.
    """
    bars = bar_numbers(rows)

    def rate(count: int) -> str:
        return f"{count / hours:.3f}" if hours else "n/a"

    def spread(block) -> str:
        if not block["count"]:
            return "none"
        return (
            f"n={block['count']} min={block['min']} "
            f"median={block['median']} max={block['max']}"
        )

    would = bars["would_bar"]
    lines = [
        "S2b.2 bar table (design 3.2 / 3.3):",
        f"would-bar events (decisions whose owner and goal met a bar)    "
        f"{would['count']:>5}   per runtime hour {rate(would['count'])}",
    ]
    for owner, counts in would["by_owner"].items():
        lines.append(
            f"    {owner:<48} {counts['events']} "
            f"({counts['claims']} claim(s))"
        )
    placed = bars["bars_set"]
    lines.append(
        f"bars set                                                       "
        f"{placed['count']:>5}"
    )
    for name, times in placed["by_owner_kind"].items():
        lines.append(f"    {name:<48} {times}")
    lines.append("bar lifetimes (bars lifted), game turns / decisions:")
    for owner, block in bars["lifetimes"].items():
        lines.append(
            f"    {owner:<32} turns {spread(block['turns'])}; "
            f"decisions {spread(block['decisions'])}"
        )
    if not bars["lifetimes"]:
        lines.append("    (no bar lifted)")
    lines.append("bars still standing at the end of their session:")
    for owner, block in bars["still_barred"].items():
        lines.append(
            f"    {owner:<32} {block['count']} "
            f"(oldest {block['max_age_turns']} game turns)"
        )
    if not bars["still_barred"]:
        lines.append("    (none)")
    skipped = bars["skipped"]
    lines.append(
        f"rungs skipped by a bar (switch on only)                        "
        f"{skipped['count']:>5}"
    )
    for owner, times in skipped["by_owner"].items():
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
    lines.extend(ladder_report(rows, hours))
    lines.extend(bar_report(rows, hours))
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
                    "ladder": ladder_numbers(claim_rows),
                    "bars": bar_numbers(claim_rows),
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
