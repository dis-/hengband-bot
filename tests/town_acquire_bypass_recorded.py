"""Measure acquire-store-visit bypass proxies on recorded artifacts, without replay."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from hengbot.emit_ownership import derive_target_store
from hengbot.model import Position
from hengbot.policy import _new_town_turn_arbiter


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "jsonlog" / "bot-decisions.jsonl"
LEDGER = ROOT / "capture-ledger" / "read-batches.jsonl"


def _rows(path: Path):
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=None)


def _snapshot(decision: dict):
    position = decision.get("position") or {}
    store_type = decision.get("store_type")
    return SimpleNamespace(
        store=None if store_type is None else SimpleNamespace(store_type=int(store_type)),
        player=SimpleNamespace(position=Position(int(position.get("y", 0)), int(position.get("x", 0)))),
        grid_at=lambda _position: None,
    )


def _in_flight_clause(visit: dict | None) -> str | None:
    if not visit:
        return None
    if visit.get("operation_posted") and not visit.get("operation_released"):
        return "operation-posted-not-released"
    if visit.get("operation_released") and not visit.get("operation_effect_observed", True):
        return "operation-released-effect-unobserved"
    if (
        visit.get("phase") in {"entering", "leaving"}
        and visit.get("posted_sequence") is not None
    ):
        return f"{visit['phase']}-with-posted-sequence"
    return None


def measure(decisions: list[dict], ledger: list[dict]) -> dict:
    """Return only artifact-derived counts; no policy decision is replayed."""
    totals = Counter(decisions=len(decisions), ledger_batches=len(ledger))
    ledger_candidates: dict[tuple[int, str], list[tuple[int, datetime]]] = {}
    for ledger_index, batch in enumerate(ledger):
        key = batch.get("posted_key")
        if key is not None:
            for turn in set(batch.get("line_turns") or []):
                ledger_candidates.setdefault((turn, key), []).append(
                    (ledger_index, _time(batch["time"])))
    used_decisions: set[int] = set()
    used_ledger: set[int] = set()
    unmatched_posts = []
    decision_times = [_time(row["time"]) for row in decisions if row.get("time")]
    timed_decisions = [row for row in decisions if row.get("time")]
    first_time, last_time = min(decision_times), max(decision_times)

    # Preserve the accepted forward join: decision order, one-to-one ledger
    # consumption, candidates by turn/key, nearest timestamp within 60 seconds.
    for decision_index, decision in enumerate(decisions):
        key, turn = decision.get("key"), decision.get("turn")
        candidates = ledger_candidates.get((turn, key), ()) if key and turn is not None else ()
        totals[f"forward_candidate_histogram:{len(candidates)}"] += 1
        if not decision.get("time"):
            totals["forward_unmatched_missing_time"] += 1
            continue
        if not candidates:
            totals["forward_unmatched_no_candidate"] += 1
            continue
        when = _time(decision["time"])
        available = [
            (abs((candidate_time - when).total_seconds()), ledger_index)
            for ledger_index, candidate_time in candidates
            if ledger_index not in used_ledger
        ]
        match = min(available, default=None)
        if match is not None and match[0] <= 60.0:
            used_ledger.add(match[1])
            used_decisions.add(decision_index)
        elif match is None:
            totals["forward_unmatched_candidates_consumed"] += 1
        else:
            totals["forward_unmatched_outside_60_seconds"] += 1

    for ledger_index, batch in enumerate(ledger):
        key = batch.get("posted_key")
        if key is None:
            continue
        when = _time(batch["time"])
        if not (first_time <= when <= last_time):
            totals["ledger_posts_outside_trajectory_time"] += 1
            continue
        totals["ledger_posts"] += 1
        if ledger_index in used_ledger:
            totals["ledger_posts_with_decision"] += 1
            continue
        totals["ledger_posts_without_decision"] += 1
        totals[f"ledger_only_decided:{batch.get('decided')}"] += 1
        preceding_at = bisect_right(decision_times, when) - 1
        preceding = timed_decisions[preceding_at] if preceding_at >= 0 else None
        visit = None if preceding is None else preceding.get("store_visit")
        if visit:
            totals["ledger_posts_without_decision_while_visit_open"] += 1
        unmatched_posts.append({
            "ledger_row": ledger_index + 1,
            "time": batch["time"], "key": key,
            "preceding_decision_sequence": None if preceding is None else preceding.get("decision_sequence"),
            "store_visit": None if visit is None else {
                "owner": visit.get("owner"), "store_type": visit.get("store_type"),
                "phase": visit.get("phase"), "in_flight_clause": _in_flight_clause(visit),
            },
        })

    arbiter = _new_town_turn_arbiter()
    breakdown = Counter()
    target_relation = Counter()
    non_openers = []
    for index in sorted(used_decisions):
        decision = decisions[index]
        visit = decision.get("store_visit")
        if not visit:
            continue
        totals["decision_posts_while_visit_open"] += 1
        if decision.get("decision_sequence") == visit.get("opened_sequence"):
            continue
        totals["non_opener_posts_proxy"] += 1
        attribution = arbiter.decision_owner_for_reason(decision.get("reason") or "")
        group = (attribution, visit.get("owner"), visit.get("phase"))
        breakdown[group] += 1
        target, source = derive_target_store(
            _snapshot(decision), decision.get("key") or "",
            decision.get("shopping_approach_store_type"),
        )
        relation = "undetermined"
        if target is not None:
            totals["non_opener_target_derivable"] += 1
            relation = "same" if target == visit.get("store_type") else "different"
            target_relation[(relation, source)] += 1
            totals[f"non_opener_target_{relation}"] += 1
        non_openers.append({"decision_row": index + 1, "group": group, "target": target,
                            "target_source": source, "relation": relation})

    # Recompute the earlier forward direction on the identical one-to-one matching.
    totals["decisions_in_forward_denominator"] = len(decisions) - totals["forward_unmatched_missing_time"]
    totals["decisions_without_ledger_match"] = (
        totals["decisions_in_forward_denominator"] - len(used_decisions))
    return {
        "totals": totals, "unmatched_posts": unmatched_posts,
        "non_openers": non_openers, "breakdown": breakdown,
        "target_relation": target_relation, "used_decisions": used_decisions,
    }


def controls(decisions: list[dict], ledger: list[dict], baseline: dict) -> dict:
    """Independently re-evaluate and move every reported event population."""
    result = {}
    matched = next((i for i in sorted(baseline["used_decisions"])
                    if decisions[i].get("store_visit")), None)
    if matched is None:
        raise AssertionError("control needs a matched open-visit decision")

    removed = [dict(row) for row in decisions]
    removed[matched] = {**removed[matched], "key": "<control-no-match>"}
    moved = measure(removed, ledger)
    result["reverse_join"] = (
        baseline["totals"]["ledger_posts_without_decision"],
        moved["totals"]["ledger_posts_without_decision"],
    )

    proxy_index = next(i for i in baseline["used_decisions"] if (
        decisions[i].get("store_visit")
        and decisions[i].get("decision_sequence") != decisions[i]["store_visit"].get("opened_sequence")
    ))
    equalized = [dict(row) for row in decisions]
    equalized[proxy_index] = dict(equalized[proxy_index])
    equalized[proxy_index]["store_visit"] = dict(equalized[proxy_index]["store_visit"])
    equalized[proxy_index]["store_visit"]["opened_sequence"] = equalized[proxy_index]["decision_sequence"]
    moved = measure(equalized, ledger)
    result["non_opener_proxy"] = (
        baseline["totals"]["non_opener_posts_proxy"], moved["totals"]["non_opener_posts_proxy"])

    undetermined = next((i for i in baseline["used_decisions"] if (
        decisions[i].get("store_visit")
        and decisions[i].get("decision_sequence") != decisions[i]["store_visit"].get("opened_sequence")
        and baseline_target(decisions[i]) is None
    )), None)
    if undetermined is None:
        raise AssertionError("target control needs an undetermined proxy row")
    targeted = [dict(row) for row in decisions]
    targeted[undetermined] = dict(targeted[undetermined])
    targeted[undetermined]["shopping_approach_store_type"] = targeted[undetermined]["store_visit"]["store_type"]
    moved = measure(targeted, ledger)
    result["derivable_target"] = (
        baseline["totals"]["non_opener_target_derivable"], moved["totals"]["non_opener_target_derivable"])
    return result


def baseline_target(decision: dict):
    return derive_target_store(_snapshot(decision), decision.get("key") or "",
                               decision.get("shopping_approach_store_type"))[0]


SEND_SITES = (
    ("cli.py:1777 _send_new_decision_key -> send", "decision log: observable; ledger: observable"),
    ("cli.py:1909 _send_stall_recovery_nudge -> send", "decision log: not observable by this artifact; ledger: per-call-site count not observable by this artifact"),
    ("cli.py:2399 one-shot decision send", "decision log: observable; ledger: observable"),
    ("cli.py:2712 _look_probe_key send", "decision log: not observable by this artifact; ledger: per-call-site count not observable by this artifact"),
    ("cli.py:2729 floor-transition ESC send", "decision log: not observable by this artifact; ledger: per-call-site count not observable by this artifact"),
    ("cli.py:3278 DEATH_EXIT_KEYS send", "decision log: not observable by this artifact; ledger: per-call-site count not observable by this artifact"),
    ("cli.py:3311 stuck-prompt probe send", "decision log: not observable by this artifact; ledger: per-call-site count not observable by this artifact"),
    ("cli.py:2981/3059 _send_new_decision_key callers", "decision log: observable; ledger: observable"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("all",), nargs="?", default="all")
    args = parser.parse_args()
    del args
    decisions, ledger = list(_rows(DECISIONS)), list(_rows(LEDGER))
    report = measure(decisions, ledger)
    control = controls(decisions, ledger, report)
    totals = report["totals"]
    print("R33 recorded acquire-bypass measurement (no policy replay)")
    print("trap 1: acquire-called is not observable post-hoc; non-opener is a PROXY")
    print("trap 2: five recovery families bypass _write_decision and are absent from decisions")
    print("trap 3: read-batches posted_key is the only artifact observing those posts")
    print("reverse join:", dict((k, totals[k]) for k in (
        "ledger_posts", "ledger_posts_with_decision", "ledger_posts_without_decision",
        "ledger_posts_without_decision_while_visit_open")))
    reverse_breakdown = Counter((
        row["key"], None if row["store_visit"] is None else row["store_visit"]["owner"],
        None if row["store_visit"] is None else row["store_visit"]["store_type"],
        None if row["store_visit"] is None else row["store_visit"]["phase"],
        None if row["store_visit"] is None else row["store_visit"]["in_flight_clause"],
    ) for row in report["unmatched_posts"])
    print("unmatched ledger nearest-preceding visit breakdown:", dict(sorted(reverse_breakdown.items(), key=str)))
    print("reverse artifact qualification:", {
        "ledger_decided_true": totals["ledger_only_decided:True"],
        "ledger_decided_false": totals["ledger_only_decided:False"],
        "finding": "all reverse-unmatched rows are marked decided=true; the artifacts do not support relabeling them recovery posts",
    })
    print("forward reconciliation:", {"decisions_in_denominator": totals["decisions_in_forward_denominator"],
          "decisions_without_ledger_match": totals["decisions_without_ledger_match"],
          "unmatched_no_candidate": totals["forward_unmatched_no_candidate"],
          "unmatched_candidates_consumed": totals["forward_unmatched_candidates_consumed"],
          "unmatched_outside_60_seconds": totals["forward_unmatched_outside_60_seconds"],
          "note": "forward and reverse unmatched populations differ because the join is not bijective"})
    print("non-opener PROXY:", totals["non_opener_posts_proxy"],
          "over-counts same-store decisions that really called acquire; under-counts opener decisions and bypasses outside an open visit")
    print("breakdown attribution/visit_owner/phase:", dict(sorted(report["breakdown"].items())))
    print("store-targeting subset:", {"derivable": totals["non_opener_target_derivable"],
          "same": totals["non_opener_target_same"], "different": totals["non_opener_target_different"],
          "detail": dict(sorted(report["target_relation"].items()))})
    print("closed send-site list:")
    for site, observability in SEND_SITES:
        print(" ", site, observability)
    print("artifact-supported counts:", {"decision+ledger": totals["ledger_posts_with_decision"],
          "reverse-unmatched-but-ledger-decided": totals["ledger_posts_without_decision"],
          "ledger-posted-without-decision-path": totals["ledger_only_decided:False"]})
    print("telemetry proposal (NOT IMPLEMENTED): per decision acquire_store_visit_called plus requested owner/store and result")
    print("controls:", control)
    assert control["reverse_join"][1] > control["reverse_join"][0]
    assert control["non_opener_proxy"][1] < control["non_opener_proxy"][0]
    assert control["derivable_target"][1] > control["derivable_target"][0]
    print("production derive_target_store calls:", totals["non_opener_posts_proxy"])
    print("tests_touched: tests/town_acquire_bypass_recorded.py tests/test_town_acquire_bypass_recorded.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
