"""Measure recorded store-visit bypasses across all three posting artifacts."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

from hengbot.emit_ownership import derive_target_store, in_flight_clause
from hengbot.model import Position
from hengbot.policy import _new_town_turn_arbiter
from hengbot.policy_types import StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "jsonlog" / "bot-decisions.jsonl"
LEDGER = ROOT / "capture-ledger" / "read-batches.jsonl"
POSTED = ROOT / "jsonlog" / "bot-posted-characters.jsonl"


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
    adapted = SimpleNamespace(**visit)
    adapted.phase = StoreVisitPhase(visit["phase"])
    return in_flight_clause(adapted)


def is_synthetic_ledger_row(row: dict, minimum_trajectory_turn: int) -> bool:
    """Test fixtures use tiny turns; the recorded trajectory starts at 865427."""
    turns = row.get("line_turns") or []
    return bool(turns) and max(turns) < minimum_trajectory_turn and all(
        value is None for value in (row.get("line_types") or [])
    )


def filter_synthetic_ledger(decisions: list[dict], ledger: list[dict]) -> list[dict]:
    minimum = min(row["turn"] for row in decisions if isinstance(row.get("turn"), int))
    return [row for row in ledger if not is_synthetic_ledger_row(row, minimum)]


def ledger_pollution(decisions: list[dict], ledger: list[dict]) -> dict:
    minimum = min(row["turn"] for row in decisions if isinstance(row.get("turn"), int))
    rows = [row for row in ledger if is_synthetic_ledger_row(row, minimum)]
    return {
        "rows": len(rows), "with_posted_key": sum(row.get("posted_key") is not None for row in rows),
        "first": min(row["time"] for row in rows), "last": max(row["time"] for row in rows),
    }


def measure(decisions: list[dict], ledger: list[dict], posted: list[dict] | None = None) -> dict:
    """Return artifact-derived counts; no policy decision is replayed."""
    totals = Counter(decisions=len(decisions), ledger_batches=len(ledger))
    candidates: dict[tuple[int, str], list[tuple[int, datetime]]] = {}
    for ledger_index, batch in enumerate(ledger):
        key = batch.get("posted_key")
        if key is not None:
            for turn in set(batch.get("line_turns") or []):
                candidates.setdefault((turn, key), []).append((ledger_index, _time(batch["time"])))
    used_decisions, used_ledger = set(), set()
    decision_times = [_time(row["time"]) for row in decisions if row.get("time")]
    timed_decisions = [row for row in decisions if row.get("time")]
    first_time, last_time = min(decision_times), max(decision_times)
    for decision_index, decision in enumerate(decisions):
        key, turn = decision.get("key"), decision.get("turn")
        options = candidates.get((turn, key), ()) if key and turn is not None else ()
        if not decision.get("time"):
            totals["forward_unmatched_missing_time"] += 1
            continue
        if not options:
            totals["forward_unmatched_no_candidate"] += 1
            continue
        when = _time(decision["time"])
        available = [(abs((at - when).total_seconds()), index) for index, at in options if index not in used_ledger]
        match = min(available, default=None)
        if match is not None and match[0] <= 60:
            used_ledger.add(match[1]); used_decisions.add(decision_index)
        elif match is None:
            totals["forward_unmatched_candidates_consumed"] += 1
        else:
            totals["forward_unmatched_outside_60_seconds"] += 1
    unmatched_posts = []
    for ledger_index, batch in enumerate(ledger):
        key = batch.get("posted_key")
        if key is None or not (first_time <= _time(batch["time"]) <= last_time):
            continue
        totals["ledger_posts"] += 1
        if ledger_index in used_ledger:
            totals["ledger_posts_with_decision"] += 1
            continue
        totals["ledger_posts_without_decision"] += 1
        preceding_at = bisect_right(decision_times, _time(batch["time"])) - 1
        preceding = timed_decisions[preceding_at] if preceding_at >= 0 else None
        visit = None if preceding is None else preceding.get("store_visit")
        if visit:
            totals["ledger_posts_without_decision_while_visit_open"] += 1
        unmatched_posts.append((key, visit))
    arbiter = _new_town_turn_arbiter()
    breakdown, target_relation, origins = Counter(), Counter(), Counter()
    for index in sorted(used_decisions):
        decision, visit = decisions[index], decisions[index].get("store_visit")
        if not visit:
            continue
        totals["decision_posts_while_visit_open"] += 1
        origin = visit.get("visit_origin")
        if origin is None and visit.get("owner") in {"shop-one-shot", "shop-handler", "recovered-store-context"}:
            origin = {"shop-handler": "shop-handler-recovery"}.get(visit.get("owner"), visit.get("owner"))
        origins[origin or "pre-telemetry/unknown"] += 1
        if decision.get("decision_sequence") == visit.get("opened_sequence"):
            continue
        totals["non_opener_posts_proxy"] += 1
        breakdown[(arbiter.decision_owner_for_reason(decision.get("reason") or ""), visit.get("owner"), visit.get("phase"))] += 1
        target, source = derive_target_store(_snapshot(decision), decision.get("key") or "", decision.get("shopping_approach_store_type"))
        if target is not None:
            totals["non_opener_target_derivable"] += 1
            relation = "same" if target == visit.get("store_type") else "different"
            totals[f"non_opener_target_{relation}"] += 1
            target_relation[(relation, source)] += 1
    post_breakdown = Counter()
    if posted is not None:
        sends = [row for row in posted if row.get("character_index") == 0 and row.get("time") and first_time <= _time(row["time"]) <= last_time]
        totals["posts_in_window"] = len(sends)
        totals["posts_with_decision"] = sum(row.get("decision") is not None for row in sends)
        totals["posts_without_decision"] = sum(row.get("decision") is None for row in sends)
        totals["posts_with_decision_without_ledger_row"] = totals["posts_with_decision"] - totals["ledger_posts"]
        for row in sends:
            if row.get("decision") is not None:
                continue
            totals[f"decisionless_key:{row.get('composed_key')}"] += 1
            preceding_at = bisect_right(decision_times, _time(row["time"])) - 1
            preceding = timed_decisions[preceding_at] if preceding_at >= 0 else None
            visit = None if preceding is None else preceding.get("store_visit")
            if visit and row.get("composed_key") == "\x1b":
                totals["decisionless_while_visit_open"] += 1
                if visit.get("phase") == "operating":
                    totals["decisionless_while_store_page_open"] += 1
                post_breakdown[(row.get("composed_key"), visit.get("owner"), visit.get("store_type"), visit.get("phase"), _in_flight_clause(visit))] += 1
    totals["decisions_in_forward_denominator"] = len(decisions) - totals["forward_unmatched_missing_time"]
    totals["decisions_without_ledger_match"] = totals["decisions_in_forward_denominator"] - len(used_decisions)
    return {"totals": totals, "used_decisions": used_decisions, "unmatched_posts": unmatched_posts,
            "breakdown": breakdown, "target_relation": target_relation, "post_breakdown": post_breakdown,
            "origins": origins}


def magnitude_controls(decisions: list[dict], raw_ledger: list[dict], clean_ledger: list[dict],
                       posted: list[dict], baseline: dict) -> dict:
    """Bulk input perturbations; every result re-enters measure end to end."""
    raw = measure(decisions, raw_ledger, posted)
    decision_only_posts = [row for row in posted if row.get("decision") is not None]
    decisionless_only_posts = [row for row in posted if row.get("decision") is None]
    decision_only = measure(decisions, clean_ledger, decision_only_posts)
    decisionless_only = measure(decisions, clean_ledger, decisionless_only_posts)
    no_visits = deepcopy(decisions)
    for row in no_visits:
        row["store_visit"] = None
    cleared = measure(no_visits, clean_ledger, posted)
    equalized = deepcopy(decisions)
    for index in baseline["used_decisions"]:
        visit = equalized[index].get("store_visit")
        if visit:
            visit["opened_sequence"] = equalized[index].get("decision_sequence")
    all_openers = measure(equalized, clean_ledger, posted)
    forced = deepcopy(decisions)
    for index in baseline["used_decisions"]:
        decision, visit = forced[index], forced[index].get("store_visit")
        if not visit or decision.get("decision_sequence") == visit.get("opened_sequence"):
            continue
        target, _source = derive_target_store(_snapshot(decision), decision.get("key") or "",
                                               decision.get("shopping_approach_store_type"))
        if target is not None:
            visit["store_type"] = target + 1000
    different = measure(forced, clean_ledger, posted)
    return {
        "filter_reverse": (raw["totals"]["ledger_posts_without_decision"], baseline["totals"]["ledger_posts_without_decision"]),
        "filter_open_visit": (raw["totals"]["ledger_posts_without_decision_while_visit_open"], baseline["totals"]["ledger_posts_without_decision_while_visit_open"]),
        "remove_decisionless": (baseline["totals"]["posts_in_window"], decision_only["totals"]["posts_in_window"],
                                baseline["totals"]["posts_without_decision"], decision_only["totals"]["posts_without_decision"]),
        "remove_decision_posts": (baseline["totals"]["posts_with_decision"], decisionless_only["totals"]["posts_with_decision"]),
        "clear_visits": (baseline["totals"]["decisionless_while_visit_open"], cleared["totals"]["decisionless_while_visit_open"],
                         baseline["totals"]["decisionless_while_store_page_open"], cleared["totals"]["decisionless_while_store_page_open"],
                         baseline["totals"]["decision_posts_while_visit_open"], cleared["totals"]["decision_posts_while_visit_open"]),
        "equalize_openers": (baseline["totals"]["non_opener_posts_proxy"], all_openers["totals"]["non_opener_posts_proxy"]),
        "force_different": (baseline["totals"]["non_opener_target_different"], different["totals"]["non_opener_target_different"]),
    }


SEND_SITES = (
    ("decision path", "observable", "observable", "decision attached"),
    ("stall-recovery nudge", "absent", "posted_key overwritten/combined", "bare ESC; not call-site attributable"),
    ("look probe cli.py:2712", "absent", "posted_key overwritten/combined", "l\\x1b; call-site attributable"),
    ("floor-transition ESC", "absent", "posted_key overwritten/combined", "bare ESC; not call-site attributable"),
    ("death-exit ESC", "absent", "posted_key overwritten/combined", "bare ESC; not call-site attributable"),
    ("stuck-prompt ESC", "absent", "posted_key overwritten/combined", "bare ESC; not call-site attributable"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("all",), nargs="?", default="all")
    parser.parse_args()
    decisions, raw_ledger, posted = list(_rows(DECISIONS)), list(_rows(LEDGER)), list(_rows(POSTED))
    clean_ledger = filter_synthetic_ledger(decisions, raw_ledger)
    raw = measure(decisions, raw_ledger, posted)
    report = measure(decisions, clean_ledger, posted)
    controls = magnitude_controls(decisions, raw_ledger, clean_ledger, posted, report)
    t = report["totals"]
    print("R37-R42 corrected recorded acquire-bypass measurement (no policy replay)")
    print("ledger synthetic pollution (retained on disk):", ledger_pollution(decisions, raw_ledger))
    print("ledger-derived with/without synthetic filter:", {
        "without_filter": {k: raw["totals"][k] for k in ("ledger_posts", "ledger_posts_with_decision", "ledger_posts_without_decision", "ledger_posts_without_decision_while_visit_open")},
        "with_filter": {k: t[k] for k in ("ledger_posts", "ledger_posts_with_decision", "ledger_posts_without_decision", "ledger_posts_without_decision_while_visit_open")}})
    print("retractions:", {"ledger_posted_without_decision_path": "0 by construction, not evidence",
          "unmatched_while_preceding_visit_open": t["ledger_posts_without_decision_while_visit_open"]})
    print("forward/reverse reconciliation:", {"decisions_in_window": t["decisions_in_forward_denominator"],
          "real_posts_carrying_decision": t["posts_with_decision"], "decisions_never_posted": t["decisions_in_forward_denominator"] - t["posts_with_decision"],
          "forward_unmatched": t["decisions_without_ledger_match"], "real_ledger_rows_with_key": t["ledger_posts"],
          "posts_without_ledger_row": t["posts_with_decision_without_ledger_row"], "matched": t["ledger_posts_with_decision"],
          "real_reverse_unmatched": t["ledger_posts_without_decision"]})
    print("posted-character ownership bypass:", {"posts": t["posts_in_window"], "with_decision": t["posts_with_decision"],
          "without_decision": t["posts_without_decision"], "keys": {"ESC": t["decisionless_key:\x1b"], "lESC": t["decisionless_key:l\x1b"]},
          "while_visit_open": t["decisionless_while_visit_open"], "while_store_page_open": t["decisionless_while_store_page_open"]})
    print("decision-less post breakdown key/owner/store/phase/clause:", dict(sorted(report["post_breakdown"].items(), key=str)))
    print("recovery attribution: lESC is uniquely _look_probe_key; bare ESC can be any of stall-nudge, floor-transition, death-exit, or stuck-prompt and needs a call-site tag")
    print("non-opener proxy/store targeting:", {"proxy": t["non_opener_posts_proxy"], "derivable": t["non_opener_target_derivable"],
          "same": t["non_opener_target_same"], "different": t["non_opener_target_different"]})
    direct = {key: report["origins"][key] for key in ("shop-one-shot", "shop-handler-recovery", "recovered-store-context")}
    print("five direct-construction sites:", {"policy.py:4316": "equipment-transaction-recovery", "policy.py:4324": "shop-handler-recovery",
          "policy.py:4415": "shop-one-shot", "policy.py:15202": "home-operation-staging", "town_arbiter.py:503": "recovered-store-context"})
    print("matched visit-open split by origin:", dict(report["origins"]), "direct-only:", direct, "direct-only-total:", sum(direct.values()))
    print("scope: routing emits through acquire_store_visit (E6 as scoped) does not close this; routing visit creation would")
    print("closed send-site observability (decision log / read-batches / posted-characters):")
    for row in SEND_SITES: print(" ", row)
    print("magnitude controls (all re-run measure):", controls)
    assert controls == {"filter_reverse": (436, 2), "filter_open_visit": (248, 0),
                        "remove_decisionless": (15101, 14740, 361, 0),
                        "remove_decision_posts": (14740, 0), "clear_visits": (119, 0, 7, 0, 2818, 0),
                        "equalize_openers": (1870, 0), "force_different": (0, 222)}
    print("production derive_target_store calls:", t["non_opener_posts_proxy"])
    print("tests_touched: tests/run_follow_hygiene.py tests/test_cli.py tests/test_control_client.py tests/test_emit_ownership.py tests/town_acquire_bypass_recorded.py tests/test_town_acquire_bypass_recorded.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
