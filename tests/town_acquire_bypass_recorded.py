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
from historical_emit_fixture import DECISIONS as FROZEN_DECISIONS
from historical_emit_fixture import LEDGER as FROZEN_LEDGER
from historical_emit_fixture import POSTED as FROZEN_POSTED
from historical_emit_fixture import rows as fixture_rows
from store_visit_constructor_census import EXPECTED_ORIGINS, production_constructor_sites


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = FROZEN_DECISIONS
LEDGER = FROZEN_LEDGER
POSTED = FROZEN_POSTED


def _rows(path: Path):
    yield from fixture_rows(path)


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
    for name, default in (
        ("operation_posted", False), ("operation_released", False),
        ("operation_effect_observed", False), ("posted_sequence", None),
        ("posted_turn", None),
    ):
        if not hasattr(adapted, name):
            setattr(adapted, name, default)
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
    timed = sorted(
        ((_time(row["time"]), row) for row in decisions if row.get("time")),
        key=lambda pair: pair[0],
    )
    decision_times = [pair[0] for pair in timed]
    timed_decisions = [pair[1] for pair in timed]
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
        if origin is None:
            owner = visit.get("owner")
            if owner == "town-errand":
                origin = "acquire"
            elif owner in {"shop-one-shot", "shop-handler", "recovered-store-context", "store-router", "home-one-shot"}:
                origin = "direct"
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
    decisionless_visit_gaps = []
    decisionless_bare_visit_gaps = []
    if posted is not None:
        remaining_ledger_identities = Counter({
            identity: len(options) for identity, options in candidates.items()
        })
        sends = [row for row in posted if row.get("character_index") == 0 and row.get("time") and first_time <= _time(row["time"]) <= last_time]
        totals["posts_in_window"] = len(sends)
        totals["posts_with_decision"] = sum(row.get("decision") is not None for row in sends)
        totals["posts_without_decision"] = sum(row.get("decision") is None for row in sends)
        posted_without_ledger = []
        for row in sends:
            attached = row.get("decision")
            if attached is not None:
                identity = (attached.get("turn"), attached.get("key"))
                if remaining_ledger_identities[identity]:
                    remaining_ledger_identities[identity] -= 1
                else:
                    posted_without_ledger.append({
                        "time": row["time"], "turn": attached.get("turn"),
                        "key": attached.get("key"), "reason": attached.get("reason"),
                    })
                continue
            totals[f"decisionless_key:{row.get('composed_key')}"] += 1
            preceding_at = bisect_right(decision_times, _time(row["time"])) - 1
            preceding = timed_decisions[preceding_at] if preceding_at >= 0 else None
            gap = None if preceding is None else (
                _time(row["time"]) - decision_times[preceding_at]
            ).total_seconds()
            visit = None if preceding is None or gap > 5.0 else preceding.get("store_visit")
            if visit and row.get("composed_key") in {"\x1b", "l\x1b"}:
                totals["decisionless_while_visit_open"] += 1
                decisionless_visit_gaps.append(gap)
                if row.get("composed_key") == "\x1b":
                    decisionless_bare_visit_gaps.append(gap)
                totals["decisionless_attribution_gap_ms_total"] += round(gap * 1000)
                if visit.get("phase") == "operating":
                    totals["decisionless_while_store_page_open"] += 1
                post_breakdown[(row.get("composed_key"), visit.get("owner"), visit.get("store_type"), visit.get("phase"), _in_flight_clause(visit))] += 1
        totals["posts_with_decision_without_ledger_row"] = len(posted_without_ledger)
    totals["decisions_in_forward_denominator"] = len(decisions) - totals["forward_unmatched_missing_time"]
    totals["decisions_without_ledger_match"] = totals["decisions_in_forward_denominator"] - len(used_decisions)
    return {"totals": totals, "used_decisions": used_decisions, "unmatched_posts": unmatched_posts,
            "posted_without_ledger": posted_without_ledger if posted is not None else [],
            "decisionless_visit_gaps": decisionless_visit_gaps,
            "decisionless_bare_visit_gaps": decisionless_bare_visit_gaps,
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
    half = measure(decisions[::2], clean_ledger, posted)
    half_ledger = measure(decisions, clean_ledger[::2], posted)
    classified = deepcopy(decisions)
    for row in classified:
        visit = row.get("store_visit")
        if visit and not visit.get("visit_origin"):
            visit["visit_origin"] = "acquire" if visit.get("owner") == "town-errand" else "direct"
    classified_result = measure(classified, clean_ledger, posted)
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
        "halve_decisions": tuple(
            (baseline if name == "before" else half)["totals"][metric]
            for metric in ("decisions_in_forward_denominator", "decisions_without_ledger_match")
            for name in ("before", "after")
        ),
        "halve_ledger": (baseline["totals"]["posts_with_decision_without_ledger_row"],
                          half_ledger["totals"]["posts_with_decision_without_ledger_row"]),
        "classify_origins": (dict(baseline["origins"]), dict(classified_result["origins"])),
    }


SEND_SITES = (
    ("decision path", "observable", "observable", "decision attached"),
    ("stall-recovery nudge", "absent", "posted_key overwritten/combined", "bare ESC; not call-site attributable"),
    ("look probe cli.py:2741/2743", "absent", "posted_key overwritten/combined", "l\\x1b; call-site attributable"),
    ("floor-transition ESC cli.py:2760", "absent", "posted_key overwritten/combined", "bare ESC; not call-site attributable"),
    ("terminal-resync cli.py:3310", "observable", "posted_key overwritten/combined", "decision attached; recovery did not fire in window"),
    ("stuck-prompt cli.py:3343", "observable", "posted_key overwritten/combined", "decision attached; recovery did not fire in window"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("all",), nargs="?", default="all")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    decisions_path, ledger_path, posted_path = DECISIONS, LEDGER, POSTED
    if args.live:
        decisions_path = ROOT / "jsonlog" / "bot-decisions.jsonl"
        ledger_path = ROOT / "capture-ledger" / "read-batches.jsonl"
        posted_path = ROOT / "jsonlog" / "bot-posted-characters.jsonl"
    decisions, raw_ledger, posted = list(_rows(decisions_path)), list(_rows(ledger_path)), list(_rows(posted_path))
    clean_ledger = filter_synthetic_ledger(decisions, raw_ledger)
    raw = measure(decisions, raw_ledger, posted)
    report = measure(decisions, clean_ledger, posted)
    controls = magnitude_controls(decisions, raw_ledger, clean_ledger, posted, report)
    t = report["totals"]
    print("R48-R53 corrected recorded acquire-bypass measurement (no policy replay)")
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
    print("recovery attribution: lESC is uniquely _look_probe_key; bare decision-less ESC can only be stall-nudge or floor-transition in this window; terminal-resync and stuck-prompt attach decisions and did not fire")
    print("non-opener proxy/store targeting:", {"proxy": t["non_opener_posts_proxy"], "derivable": t["non_opener_target_derivable"],
          "same": t["non_opener_target_same"], "different": t["non_opener_target_different"]})
    direct = report["origins"]["direct"]
    constructor_sites = production_constructor_sites(ROOT / "src")
    assert Counter(constructor_sites.values()) == EXPECTED_ORIGINS
    print("production StoreVisit constructor AST census:", constructor_sites)
    print("matched visit-open split by origin:", dict(report["origins"]), "direct-total:", direct)
    print("identified posts carrying decisions with no ledger row:", report["posted_without_ledger"])
    gaps = sorted(report["decisionless_visit_gaps"])
    bare_gaps = sorted(report["decisionless_bare_visit_gaps"])
    percentile = lambda values, fraction: values[round((len(values) - 1) * fraction)]
    gap_summary = {"bound_seconds": 5.0, "all_keys_count": len(gaps), "bare_ESC_count": len(bare_gaps)}
    if bare_gaps:
        gap_summary.update({"bare_ESC_min": round(bare_gaps[0], 3),
                            "bare_ESC_p50": round(percentile(bare_gaps, .5), 3),
                            "bare_ESC_p90": round(percentile(bare_gaps, .9), 3),
                            "bare_ESC_max": round(bare_gaps[-1], 3)})
    print("decision-less attribution bound:", gap_summary)
    print("scope: E6 one-shot routing now appears only through acquire_store_visit; its prior direct constructor is absent from the asserted AST census")
    print("closed send-site observability (decision log / read-batches / posted-characters):")
    for row in SEND_SITES: print(" ", row)
    print("magnitude controls (all re-run measure):", controls)
    assert controls == {"filter_reverse": (436, 2), "filter_open_visit": (248, 0),
                        "remove_decisionless": (15101, 14740, 361, 0),
                        "remove_decision_posts": (14740, 0), "clear_visits": (119, 0, 7, 0, 2818, 0),
                        "equalize_openers": (1870, 0), "force_different": (0, 222),
                        "halve_decisions": (16068, 8035, 1343, 493),
                        "halve_ledger": (14, 7377),
                        "classify_origins": ({"acquire": 1910, "direct": 443, "pre-telemetry/unknown": 465},
                                             {"acquire": 1910, "direct": 908})}
    print("production derive_target_store calls:", t["non_opener_posts_proxy"])
    print("tests_touched: tests/run_follow_hygiene.py tests/test_cli.py tests/test_loot_triage.py tests/town_acquire_bypass_recorded.py tests/test_town_acquire_bypass_recorded.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
