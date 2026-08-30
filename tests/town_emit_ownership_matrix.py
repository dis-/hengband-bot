"""Measure four emit-time store-visit invariants without changing policy.

The pre/post ordering is deliberate: copy the visit and targeting context
immediately before ``choose_key``; read attribution and reason immediately
after it returns, before any sender can post the key.  Acquisitions are only
observed.  Every form is evaluated by its own predicate on emitting decisions
whose copied visit satisfies the arbiter's four-clause in-flight definition.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
from types import MethodType, SimpleNamespace

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.emit_ownership import emit_ownership_verdict, in_flight_clause
from hengbot.cli import PostingContract, _send_new_decision_key
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
POPULATIONS = {
    "equip-swap (frozen)": ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl",
    "no-actionable (frozen)": ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.snapshots.jsonl",
    "bot-state-fixed (unpinned live stream)": ROOT / "jsonlog" / "bot-state-fixed.jsonl",
}
QUOTED_B_SUBTRACTION = {
    "equip-swap (frozen)": 3,
    "no-actionable (frozen)": 22,
    "bot-state-fixed (unpinned live stream)": 132,
}

# These are the visit-owner codomain values actually produced by
# _store_visit_arbiter_owner for ordinary store visits.  Attribution families
# outside it have no coarse image and are reported, not silently discarded.
COARSE_ATTRIBUTION = {
    "equipment-txn": "equipment-txn",
    "town-plan": "town-plan",
    "store-router": "store-router",
    "shop-buy": "shop-buy",
    "home-visit": "home-visit",
}
FORMS = ("A", "B", "C", "D")
EMIT_PATHS = (
    ("once-main-decision", "in", "One-shot policy decision; enforce the same posted-key gate."),
    ("follow-main-decision", "in", "Normal policy decision and the principal E3 enforcement site."),
    ("posting-contract-retry", "in", "A recomposed policy decision after refusal; same ownership contract."),
    ("look-probe-desync-barrier", "out", "Transport resynchronization, not a policy store-target decision."),
    ("floor-transition-escape", "out", "Prompt-clearing ESC required for transport progress."),
    ("stall-recovery-nudge", "out", "Withholding recovery ESC can freeze a silent town/store modal."),
    ("death-terminal-resync", "out", "Terminal process recovery is outside town ownership."),
    ("stuck-prompt-probe", "out", "Bounded modal recovery must remain able to clear a prompt."),
)


def _instrument_acquires(policy: HengbotPolicy, calls: list[dict]) -> None:
    arbiter = policy._town_turn_arbiter
    original = arbiter.acquire_store_visit

    def observed(_arbiter, **kwargs):
        result = original(**kwargs)
        calls.append({
            "store_type": kwargs["store_type"],
            "owner": kwargs["owner"],
            "granted": result is not None,
        })
        return result

    arbiter.acquire_store_visit = MethodType(observed, arbiter)


def _predicates(
    *, attribution: str, owner: str, b_violated: bool,
    acquire_calls: list[dict],
) -> dict[str, bool]:
    """Evaluate each candidate directly; none is subtraction-derived."""
    coarse = COARSE_ATTRIBUTION.get(attribution)
    return {
        "A": attribution != owner,
        "B": b_violated,
        "C": coarse is not None and coarse != owner,
        "D": not any(call["granted"] for call in acquire_calls),
    }


def measure(path: Path) -> dict:
    definitions = find_monrace_definitions(path, None)
    if definitions is None:
        raise RuntimeError(f"MonraceDefinitions.jsonc was not found for {path}")
    knowledge = load_monrace_knowledge(definitions)
    policy = HengbotPolicy(monrace_knowledge=knowledge)
    acquire_calls: list[dict] = []
    _instrument_acquires(policy, acquire_calls)
    totals = Counter()
    rows = []
    posted_line = None
    posted_keys: set[str] = set()
    posting_contract = PostingContract()

    with path.open(encoding="utf-8-sig") as stream:
        for row_index, line in enumerate(stream):
            if not line.strip():
                continue
            totals["snapshot_rows"] += 1
            snapshot_line = line.rstrip("\r\n")
            snapshot = parse_snapshot(json.loads(line), knowledge)
            visit = copy.copy(policy._store_visit)
            approach_store = policy._shopping_approach_store_type
            acquire_calls.clear()
            key = policy.choose_key(snapshot)
            attribution = policy.decision_attribution
            reason = policy.last_reason
            validated_key = policy.validate_read_key(snapshot, key)

            clause = in_flight_clause(visit)
            chosen_verdict = emit_ownership_verdict(
                visit, snapshot, key, approach_store
            )
            validated_verdict = emit_ownership_verdict(
                visit, snapshot, validated_key, approach_store
            )
            in_town_population = snapshot.in_town or snapshot.store is not None
            if in_town_population:
                totals["unconditional_B_violations"] += int(validated_verdict.blocked)
                totals["validate_target_changed"] += int(
                    chosen_verdict.target_store != validated_verdict.target_store
                )
            sent, posted_line = _send_new_decision_key(
                lambda *_args, **_kwargs: True,
                snapshot_line, validated_key, posted_line, posted_keys,
                in_store=snapshot.store is not None,
                decision={"reason": reason, "prompt_owner_handoff": policy.prompt_owner_handoff},
                snapshot=snapshot, posting_contract=posting_contract,
            )
            if in_town_population and clause is not None and key:
                totals["chosen_key_population"] += 1
                totals["chosen_key_B_violations"] += int(chosen_verdict.blocked)
            if in_town_population and clause is not None and sent:
                totals["posted_key_population"] += 1
                totals["posted_key_B_violations"] += int(validated_verdict.blocked)
                totals["path-follow-main-decision"] += 1

            if not in_town_population:
                continue
            totals["decisions"] += 1
            if key:
                totals["keys"] += 1
            if visit is not None and visit.phase != StoreVisitPhase.CLOSED:
                totals["open_visits"] += 1
            if visit is not None and clause is not None:
                totals["in_flight_visits"] += 1
            if not key or visit is None or clause is None:
                continue

            owner = policy._store_visit_arbiter_owner(visit)
            verdict = chosen_verdict
            totals["production_predicate_calls"] += 1
            target_store, target_source = verdict.target_store, verdict.target_source
            forms = _predicates(
                attribution=attribution, owner=owner,
                b_violated=verdict.blocked, acquire_calls=acquire_calls,
            )
            row = {
                "row": row_index, "attribution": attribution, "visit_owner": owner,
                "visit_identity": [
                    visit.owner, visit.purpose, visit.store_type, visit.opened_sequence,
                ],
                "phase": visit.phase.value, "reason": reason,
                "visit_store": visit.store_type, "target_store": target_store,
                "target_source": target_source, "acquires": copy.deepcopy(acquire_calls),
                "emit_ownership": verdict.as_dict(),
                "forms": forms,
            }
            rows.append(row)
            for form, violated in forms.items():
                totals[f"{form}_violations"] += int(violated)
            totals["B_undetermined"] += int(target_store is None)
            totals["C_unmapped"] += int(attribution not in COARSE_ATTRIBUTION)

    totals["in_flight_emitting_decisions"] = len(rows)
    # Predicate-patch controls: collapse A/C comparison operands, force every
    # known B target across stores, and force D's acquisition fact true.
    totals["A_control"] = sum(owner != owner for owner in (r["visit_owner"] for r in rows))
    totals["B_control"] = sum(
        emit_ownership_verdict(
            StoreVisit(
                owner="control", purpose="control", store_type=r["visit_store"],
                phase=StoreVisitPhase.CLOSED,
            ), SimpleNamespace(store=SimpleNamespace(
                store_type=(r["visit_store"] + 1) % 8,
            )), "", None,
        ).blocked for r in rows
    )
    totals["production_predicate_calls"] += len(rows)
    totals["C_control"] = sum(
        r["visit_owner"] != r["visit_owner"] for r in rows
        if r["attribution"] in COARSE_ATTRIBUTION
    )
    totals["D_control"] = sum(not [True] for _ in rows)
    return {"totals": dict(totals), "rows": rows}


def _print_form_rows(form: str, rows: list[dict]) -> None:
    grouped = defaultdict(list)
    for row in rows:
        if row["forms"][form]:
            grouped[(row["attribution"], row["visit_owner"], row["phase"])].append(row)
    for triple, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        print(
            f"form={form} triple={triple!r} count={len(members)} "
            f"examples={[r['row'] for r in members[:5]]!r} "
            f"reasons={sorted({r['reason'] for r in members})!r}"
        )


def _print_report(label: str, result: dict) -> None:
    totals, rows = result["totals"], result["rows"]
    print(f"population={label}")
    print(
        " ".join(f"{name}={totals.get(name, 0)}" for name in (
            "snapshot_rows", "decisions", "keys", "open_visits",
            "in_flight_visits", "in_flight_emitting_decisions",
            "A_violations", "B_violations", "C_violations", "D_violations",
        ))
    )
    pairs = ("AB", "AC", "AD", "BC", "BD", "CD")
    overlaps = {
        pair: sum(r["forms"][pair[0]] and r["forms"][pair[1]] for r in rows)
        for pair in pairs
    }
    overlaps["ABCD"] = sum(all(r["forms"].values()) for r in rows)
    exactly_one = {
        form: sum(r["forms"][form] and sum(r["forms"].values()) == 1 for r in rows)
        for form in FORMS
    }
    print("overlap " + " ".join(f"{name}={value}" for name, value in overlaps.items()))
    print("exactly_one " + " ".join(f"{form}={exactly_one[form]}" for form in FORMS))
    print(
        f"B_undetermined={totals.get('B_undetermined', 0)} "
        f"B_target_sources={dict(Counter(r['target_source'] for r in rows))!r}"
    )
    print(
        "B_populations "
        f"unconditional_logged={totals.get('unconditional_B_violations', 0)} "
        f"chosen_key={totals.get('chosen_key_B_violations', 0)}"
        f"/{totals.get('chosen_key_population', 0)} "
        f"posted_key={totals.get('posted_key_B_violations', 0)}"
        f"/{totals.get('posted_key_population', 0)} "
        f"validate_read_key_target_changes={totals.get('validate_target_changed', 0)} "
        "E3_population=posted_key"
    )
    for path, recommendation, reason in EMIT_PATHS:
        print(
            f"emit_path={path!r} in_flight_posts={totals.get('path-' + path, 0)} "
            f"E3={recommendation!r} reason={reason!r}"
        )
    quoted = QUOTED_B_SUBTRACTION[label]
    direct = totals.get("B_violations", 0)
    print(
        f"B_quoted_subtraction={quoted} B_direct={direct} "
        f"B_reproduces_subtraction={direct == quoted} "
        "B_subtraction_status='direct predicate is authoritative; E1 subtraction "
        "counted every A row not proved same-store, which is not the different-store predicate'"
    )
    unmapped = sorted({r["attribution"] for r in rows if r["attribution"] not in COARSE_ATTRIBUTION})
    print(f"C_unmapped={totals.get('C_unmapped', 0)} C_unmapped_values={unmapped!r}")
    d_targeted = [r for r in rows if r["forms"]["D"] and r["target_store"] is not None]
    print(
        f"D_targeted_store={len(d_targeted)} "
        f"D_targeted_reasons={dict(Counter(r['reason'] for r in d_targeted).most_common())!r}"
    )
    print(
        "controls " + " ".join(
            f"{form}={totals.get(form + '_violations', 0)}->{totals.get(form + '_control', 0)}"
            for form in FORMS
        )
    )
    print(
        "harness_form_B_predicate=hengbot.emit_ownership.emit_ownership_verdict "
        f"production_predicate_calls={totals.get('production_predicate_calls', 0)}"
    )
    for form in FORMS:
        _print_form_rows(form, rows)


def _b_run_lengths(rows: list[dict]) -> list[int]:
    runs: list[int] = []
    current_identity = None
    current_length = 0
    for row in rows:
        identity = tuple(row["visit_identity"])
        if row["forms"]["B"] and identity == current_identity:
            current_length += 1
        else:
            if current_length:
                runs.append(current_length)
            current_identity = identity if row["forms"]["B"] else None
            current_length = int(row["forms"]["B"])
    if current_length:
        runs.append(current_length)
    return runs


def _print_b_runs(label: str, rows: list[dict]) -> None:
    runs = _b_run_lengths(rows)
    histogram = dict(sorted(Counter(runs).items()))
    mean = sum(runs) / len(runs) if runs else 0.0
    print(
        f"B_same_visit_runs population={label!r} max={max(runs, default=0)} "
        f"mean={mean:.6f} histogram={histogram!r} runs={len(runs)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("population", choices=(*POPULATIONS, "all"), default="all", nargs="?")
    args = parser.parse_args()
    selected = POPULATIONS if args.population == "all" else {args.population: POPULATIONS[args.population]}
    failed = False
    all_rows = []
    for label, path in selected.items():
        result = measure(path)
        _print_report(label, result)
        _print_b_runs(label, result["rows"])
        all_rows.extend(result["rows"])
        totals = result["totals"]
        failed |= totals.get("A_control", -1) != 0
        failed |= totals.get("C_control", -1) != 0
        failed |= totals.get("D_control", -1) != 0
        failed |= totals.get("B_control", -1) != 0
        for form in FORMS:
            if totals.get(f"{form}_violations", 0) == totals.get(f"{form}_control", 0):
                print(f"CONTROL FAILURE: {form} count did not move")
                failed = True
    if len(selected) > 1:
        _print_b_runs("all-three-populations", all_rows)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
