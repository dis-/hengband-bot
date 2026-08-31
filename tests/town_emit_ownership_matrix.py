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
from hengbot.emit_ownership import (
    EmitOwnershipVerdict, emit_ownership_verdict, in_flight_clause,
    movement_destination,
)
from hengbot.cli import (
    POLICY_FINAL_STOP_REASONS, STARVING_STOP_LIMIT, STALLED_COMMAND_STATE_LIMIT,
    TOWN_RESIDENCE_STOP_LIMIT, PostingContract, _advance_stalled_command_count,
    _advance_starving_streak, _advance_town_residence_streak,
    _command_state_signature, _duplicate_snapshot_ready, _send_new_decision_key,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS
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
    ("once-main-decision", "in", "not exercised", "One-shot policy decision; enforce the same posted-key gate."),
    ("follow-main-decision", "in", "exercised", "Normal policy decision and the principal E3 enforcement site."),
    ("posting-contract-retry", "in", "exercised", "A recomposed policy decision after refusal; same ownership contract."),
    ("look-probe-desync-barrier", "out", "not exercisable by snapshot replay", "Transport resynchronization, not a policy store-target decision."),
    ("floor-transition-escape", "out", "not exercisable by snapshot replay", "Prompt-clearing ESC required for transport progress."),
    ("stall-recovery-nudge", "out", "not exercisable by snapshot replay", "Withholding recovery ESC can freeze a silent town/store modal."),
    ("death-terminal-resync", "out", "not exercisable by snapshot replay", "Terminal process recovery is outside town ownership."),
    ("stuck-prompt-probe", "out", "not exercisable by snapshot replay", "Bounded modal recovery must remain able to clear a prompt."),
)

MODEL_VARIANTS = (
    ("committed-harness", False, False, False, False),
    ("suppress-only", True, False, False, False),
    ("confirm-only", False, True, False, False),
    ("suppress+confirm", True, True, False, False),
    ("+duplicate-gate", True, True, True, False),
    ("+contract-retry", True, True, True, True),
)

REPLAY_IGNORED_TYPES = frozenset({"knowledge", "look", "character"})
MOVEMENT_KEYS = frozenset("12346789")


def _old_target_store(snapshot, key: str, approach_store: int | None):
    """The exact f79ad2e precedence, retained only as a measurement control."""
    if snapshot.store is not None:
        return snapshot.store.store_type, "snapshot.store.store_type"
    if approach_store is not None:
        return approach_store, "_shopping_approach_store_type"
    for store_type, symbol in enumerate(TOWN_TRAVEL_STORE_SYMBOLS):
        if key == f"\x1b`n{symbol}.":
            return store_type, "native-travel-key"
    if key in MOVEMENT_KEYS:
        grid = snapshot.grid_at(movement_destination(snapshot.player.position, key))
        if grid is not None and grid.store_number >= 0:
            return grid.store_number, "stepped-onto-store-grid"
    return None, "undetermined"


def _verdict(visit, snapshot, key, approach_store, derivation):
    if derivation == "new":
        return emit_ownership_verdict(visit, snapshot, key, approach_store)
    clause = in_flight_clause(visit)
    target, source = _old_target_store(snapshot, key, approach_store)
    visit_store = None if visit is None else visit.store_type
    return EmitOwnershipVerdict(
        blocked=bool(clause is not None and target is not None and target != visit_store),
        target_store=target, visit_store=visit_store,
        phase=None if visit is None else visit.phase.value,
        in_flight_clause=clause, target_source=source,
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


def measure(
    path: Path, *, model_suppress: bool = True, model_confirm: bool = True,
    model_duplicate: bool = True, model_retry: bool = True,
    derivation: str = "new", production_filter: bool = True,
    production_reachable: bool = False,
) -> dict:
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
    previous_decision_line = None
    previous_decision_reason = None
    last_command_signature = None
    stalled_command_count = 0
    starving_last_position = None
    starving_streak = 0
    residence_floor_key = None
    town_residence_streak = 0

    with path.open(encoding="utf-8-sig") as stream:
        for row_index, line in enumerate(stream):
            if not line.strip():
                continue
            totals["snapshot_rows"] += 1
            decoded = json.loads(line)
            if production_filter and decoded.get("type") in REPLAY_IGNORED_TYPES:
                totals["production_type_filter_drops"] += 1
                continue
            snapshot_line = line.rstrip("\r\n")
            snapshot = parse_snapshot(decoded, knowledge)
            if model_duplicate and not _duplicate_snapshot_ready(
                snapshot_line, previous_decision_line, previous_decision_reason,
            ):
                totals["duplicate_gate_drops"] += 1
                continue
            previous_decision_line = snapshot_line
            store_leave_was_inflight = policy._store_leave_inflight is not None
            visit = copy.copy(policy._store_visit)
            approach_store = policy._shopping_approach_store_type
            acquire_calls.clear()
            key = policy.choose_key(snapshot)
            attribution = policy.decision_attribution
            reason = policy.last_reason
            previous_decision_reason = reason
            validated_key = policy.validate_read_key(snapshot, key)
            suppress = bool(
                model_suppress
                and store_leave_was_inflight
                and policy._store_leave_inflight is not None
            )

            clause = in_flight_clause(visit)
            chosen_verdict = _verdict(
                visit, snapshot, key, approach_store, derivation,
            )
            validated_verdict = _verdict(
                visit, snapshot, validated_key, approach_store, derivation,
            )
            comparison_derivation = "old" if derivation == "new" else "new"
            comparison_chosen_verdict = _verdict(
                visit, snapshot, key, approach_store, comparison_derivation,
            )
            comparison_validated_verdict = _verdict(
                visit, snapshot, validated_key, approach_store,
                comparison_derivation,
            )
            if chosen_verdict.target_source != comparison_chosen_verdict.target_source:
                totals["derivation_source_divergences"] += 1
                totals[
                    "derivation_source:" + comparison_chosen_verdict.target_source
                    + "->" + chosen_verdict.target_source
                ] += 1
            in_town_population = snapshot.in_town or snapshot.store is not None
            if in_town_population:
                totals["in_town_blocked_verdicts"] += int(validated_verdict.blocked)
                totals["validate_target_changed"] += int(
                    chosen_verdict.target_store != validated_verdict.target_store
                )
            signature = _command_state_signature(snapshot, reason, key)
            stalled_command_count = _advance_stalled_command_count(
                stalled_command_count, signature=signature,
                previous_signature=last_command_signature,
            )
            last_command_signature = signature
            position_changed = (
                starving_last_position is not None
                and snapshot.player.position != starving_last_position
            )
            starving_last_position = snapshot.player.position
            starving_streak = _advance_starving_streak(
                starving_streak, food_state=snapshot.player.food_state,
                has_edible=policy.has_edible(snapshot), reason=reason,
                position_changed=position_changed,
            )
            town_residence_streak = _advance_town_residence_streak(
                town_residence_streak, residence_floor_key, snapshot.floor_key,
            )
            residence_floor_key = snapshot.floor_key
            stop_reason = None
            if stalled_command_count >= STALLED_COMMAND_STATE_LIMIT:
                stop_reason = "loop-detected:stalled-command"
            elif reason in POLICY_FINAL_STOP_REASONS:
                stop_reason = reason
            elif starving_streak >= STARVING_STOP_LIMIT:
                stop_reason = "loop-detected:starvation"
            elif reason == "livelock:exhausted":
                stop_reason = "livelock-exhausted"
            elif reason == "combat:fruitless":
                stop_reason = "loop-detected:combat-fruitless"
            elif town_residence_streak >= TOWN_RESIDENCE_STOP_LIMIT:
                stop_reason = "loop-detected:town-residence"
            if stop_reason is not None:
                totals["production_stop_rows"] += 1
                if "production_stop_row" not in totals:
                    totals["production_stop_row"] = row_index
                    totals["production_stop_reason"] = stop_reason
                if production_reachable:
                    totals["production_reachable_pop"] = totals.get("posted_key_population", 0)
                    totals["production_reachable_B"] = totals.get("posted_key_B_violations", 0)
                    break
            sent, posted_line = _send_new_decision_key(
                lambda *_args, **_kwargs: True,
                snapshot_line, validated_key, posted_line, posted_keys,
                in_store=snapshot.store is not None,
                suppress=suppress,
                decision={"reason": reason, "prompt_owner_handoff": policy.prompt_owner_handoff},
                snapshot=snapshot, posting_contract=posting_contract,
            )
            posted_verdict = validated_verdict
            comparison_posted_verdict = comparison_validated_verdict
            posted_visit = visit
            posted_clause = clause
            posted_path = "follow-main-decision"
            if model_retry and posting_contract.last_incident is not None:
                incident = posting_contract.last_incident
                policy.refuse_key_posting(
                    str(incident.get("owner", incident.get("answer_owner", reason))),
                    str(incident.get("key", validated_key)),
                )
                posted_visit = copy.copy(policy._store_visit)
                retry_approach = policy._shopping_approach_store_type
                retry_key = policy.choose_key(snapshot)
                reason = policy.last_reason
                previous_decision_reason = reason
                retry_key = policy.validate_read_key(snapshot, retry_key)
                posted_verdict = _verdict(
                    posted_visit, snapshot, retry_key, retry_approach,
                    derivation,
                )
                comparison_posted_verdict = _verdict(
                    posted_visit, snapshot, retry_key, retry_approach,
                    comparison_derivation,
                )
                posted_clause = in_flight_clause(posted_visit)
                sent, posted_line = _send_new_decision_key(
                    lambda *_args, **_kwargs: True,
                    snapshot_line, retry_key, posted_line, posted_keys,
                    in_store=snapshot.store is not None,
                    decision={
                        "reason": reason,
                        "prompt_owner_handoff": policy.prompt_owner_handoff,
                    },
                    snapshot=snapshot, posting_contract=posting_contract,
                )
                validated_key = retry_key
                posted_path = "posting-contract-retry"
                totals["contract_retries"] += 1
            if model_confirm and sent:
                policy.confirm_key_posted(validated_key)
            if in_town_population and clause is not None and key:
                totals["chosen_key_population"] += 1
                totals["chosen_key_B_violations"] += int(chosen_verdict.blocked)
                totals["comparison_chosen_key_B_violations"] += int(
                    comparison_chosen_verdict.blocked
                )
            if in_town_population and posted_clause is not None and sent:
                totals["posted_key_population"] += 1
                totals["posted_key_B_violations"] += int(posted_verdict.blocked)
                totals["comparison_posted_key_B_violations"] += int(
                    comparison_posted_verdict.blocked
                )
                totals["path-" + posted_path] += 1

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
            totals["comparison_B_violations"] += int(comparison_chosen_verdict.blocked)
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
                phase=StoreVisitPhase.LEAVING, posted_sequence=1,
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
    totals.setdefault("production_reachable_pop", totals.get("posted_key_population", 0))
    totals.setdefault("production_reachable_B", totals.get("posted_key_B_violations", 0))
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
        f"in_town_blocked_verdicts={totals.get('in_town_blocked_verdicts', 0)} "
        f"chosen_key={totals.get('chosen_key_B_violations', 0)}"
        f"/{totals.get('chosen_key_population', 0)} "
        f"posted_key={totals.get('posted_key_B_violations', 0)}"
        f"/{totals.get('posted_key_population', 0)} "
        f"validate_read_key_target_changes={totals.get('validate_target_changed', 0)} "
        f"contract_retries={totals.get('contract_retries', 0)} "
        "posted_definition='what a bot that decided on every serialized snapshot would post; not production posted set'"
    )
    print(
        f"production_reachable_pop={totals.get('production_reachable_B', 0)}"
        f"/{totals.get('production_reachable_pop', 0)} "
        f"production_stop_row={totals.get('production_stop_row', None)!r} "
        f"production_stop_reason={totals.get('production_stop_reason', None)!r} "
        f"production_type_filter_drops={totals.get('production_type_filter_drops', 0)}"
    )
    for path, recommendation, exercise, reason in EMIT_PATHS:
        measured = (
            str(totals.get("path-" + path, 0))
            if exercise == "exercised" else exercise
        )
        print(
            f"emit_path={path!r} in_flight_posts={measured!r} "
            f"instrument={exercise!r} E3={recommendation!r} reason={reason!r}"
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
        variants = []
        for model, suppress, confirm, duplicate, retry in MODEL_VARIANTS:
            measured = measure(
                path, model_suppress=suppress, model_confirm=confirm,
                model_duplicate=duplicate, model_retry=retry,
            )
            variants.append((model, measured))
        print(f"derivation_posted_model_matrix population={label!r}")
        for index in (0, 2, len(variants) - 1):
            model, measured = variants[index]
            t = measured["totals"]
            for derivation, prefix in (("old", "comparison_"), ("new", "")):
                print(
                    f"derivation={derivation!r} posted_model={model!r} "
                    f"A={t.get('A_violations', 0)} "
                    f"B={t.get(prefix + 'B_violations', 0)} "
                    f"C={t.get('C_violations', 0)} D={t.get('D_violations', 0)} "
                    f"chosen_B={t.get(prefix + 'chosen_key_B_violations', 0)}"
                    f"/{t.get('chosen_key_population', 0)} "
                    f"posted_B={t.get(prefix + 'posted_key_B_violations', 0)}"
                    f"/{t.get('posted_key_population', 0)}"
                )
            print(
                f"derivation_attribution posted_model={model!r} "
                "A_delta=0 C_delta=0 D_delta=0 "
                f"B_derivation_delta={t.get('B_violations', 0) - t.get('comparison_B_violations', 0):+d} "
                f"posted_B_derivation_delta={t.get('posted_key_B_violations', 0) - t.get('comparison_posted_key_B_violations', 0):+d} "
                "posted_model_delta_requires_within-derivation_adjacent-model_comparison"
            )
        print(f"posted_model_increments population={label!r}")
        previous = None
        for model, measured in variants:
            model_totals = measured["totals"]
            pair = (
                model_totals.get("posted_key_B_violations", 0),
                model_totals.get("posted_key_population", 0),
            )
            delta = "baseline" if previous is None else (
                f"delta={pair[0] - previous[0]:+d}/{pair[1] - previous[1]:+d}"
            )
            print(f"posted_model={model!r} B={pair[0]}/{pair[1]} {delta}")
            previous = pair
        result = variants[-1][1]
        source_totals = result["totals"]
        print(
            f"derivation_source_divergences={source_totals.get('derivation_source_divergences', 0)} "
            f"pairs={{{', '.join(repr(k.removeprefix('derivation_source:')) + ': ' + str(v) for k, v in sorted(source_totals.items()) if k.startswith('derivation_source:'))}}}"
        )
        reachable = measure(path, production_reachable=True)
        legacy = measure(path, production_filter=False)
        print(f"R13_R15_combined_effect population={label!r}")
        for scope, measured in (
            ("unfiltered_full", legacy),
            ("filtered_full", result),
            ("filtered_production_reachable", reachable),
        ):
            t = measured["totals"]
            print(
                f"scope={scope!r} "
                + " ".join(f"{name}={t.get(name, 0)}" for name in (
                    "decisions", "keys", "in_flight_emitting_decisions",
                    "A_violations", "B_violations", "C_violations", "D_violations",
                    "chosen_key_B_violations", "chosen_key_population",
                    "posted_key_B_violations", "posted_key_population",
                ))
                + f" stop_row={t.get('production_stop_row', None)!r}"
                f" stop_reason={t.get('production_stop_reason', None)!r}"
            )
        print(
            "termination_window_conditions="
            "'stalled-command, policy-final, starvation, livelock-exhausted, "
            "combat-fruitless, town-residence; replay observed policy-final only'"
        )
        _print_report(label, result)
        print("production_reachable_detail")
        _print_report(label, reachable)
        _print_b_runs(label, result["rows"])
        all_rows.extend(result["rows"])
        totals = result["totals"]
        failed |= totals.get("A_control", -1) != 0
        failed |= totals.get("C_control", -1) != 0
        failed |= totals.get("D_control", -1) != 0
        failed |= totals.get("B_control", -1) != len(result["rows"])
        for form in FORMS:
            if totals.get(f"{form}_violations", 0) == totals.get(f"{form}_control", 0):
                print(f"CONTROL FAILURE: {form} count did not move")
                failed = True
    if len(selected) > 1:
        _print_b_runs("all-three-populations", all_rows)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
