"""Measure form B on recorded production decisions, never by policy replay."""

from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from hengbot.emit_ownership import derive_target_store, emit_ownership_verdict
from hengbot.model import Position
from hengbot.policy import _new_town_turn_arbiter
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "jsonlog" / "bot-decisions.jsonl"
LEDGER = ROOT / "capture-ledger" / "read-batches.jsonl"
WINDOWS = {
    "equip-swap (recorded)": (
        ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.jsonl",
        ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl",
    ),
    "no-actionable (recorded)": (
        ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.jsonl",
        ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.snapshots.jsonl",
    ),
    "live capture (recorded)": (DECISIONS, ROOT / "jsonlog" / "bot-state-fixed.jsonl"),
}


def _json_rows(path: Path):
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _snapshot_from_json(decoded: dict):
    player = decoded.get("player") or {}
    store = decoded.get("store")
    sidecars = {
        Position(int(cell["y"]), int(cell["x"])): int(cell["s"])
        for cell in (decoded.get("grid_map") or {}).get("cells", []) if "s" in cell
    }
    return SimpleNamespace(
        store=None if store is None else SimpleNamespace(store_type=int(store["store_type"])),
        player=SimpleNamespace(position=Position(int(player.get("y", 0)), int(player.get("x", 0)))),
        grid_at=lambda position: (
            None if position not in sidecars
            else SimpleNamespace(store_number=sidecars[position])
        ),
    )


def _snapshot_index(path: Path) -> tuple[dict[int, list], Counter]:
    indexed: dict[int, list] = defaultdict(list)
    turns = Counter()
    for decoded in _json_rows(path):
        turn = decoded.get("turn")
        if turn is None:
            continue
        if decoded.get("type") in {"player_turn", "store"}:
            turns[turn] += 1
            indexed[turn].append(_snapshot_from_json(decoded))
    return indexed, turns


def _minimal_snapshot(decision: dict):
    store_type = decision.get("store_type")
    position = decision.get("position") or {"y": 0, "x": 0}
    return SimpleNamespace(
        store=None if store_type is None else SimpleNamespace(store_type=store_type),
        player=SimpleNamespace(position=Position(position["y"], position["x"])),
        grid_at=lambda _position: None,
    )


def _local_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=None)


def _ledger_posts() -> dict[tuple[int, str], list[tuple[int, datetime]]]:
    posts = defaultdict(list)
    sequence = 0
    for batch in _json_rows(LEDGER):
        sequence += 1
        key = batch.get("posted_key")
        if key is None:
            continue
        for turn in set(batch.get("line_turns") or []):
            posts[(turn, key)].append((sequence, _local_time(batch["time"])))
    return posts


def _visit_owner(visit: StoreVisit) -> str:
    if (
        visit.owner in {"shop-handler", "shop-one-shot", "home-one-shot"}
        and not visit.operation_posted
        and visit.phase in {StoreVisitPhase.APPROACHING, StoreVisitPhase.ENTERING}
    ):
        return "store-router"
    return {
        "shop-handler": "shop-buy", "shop-one-shot": "shop-buy",
        "home-one-shot": "home-visit", "equipment-transaction": "equipment-txn",
        "town-errand": "town-plan",
    }.get(visit.owner, visit.owner)


def _recorded_visit(raw: dict) -> StoreVisit:
    return StoreVisit(
        owner=raw["owner"], purpose=raw["purpose"], store_type=raw["store_type"],
        opened_sequence=raw["opened_sequence"], phase=StoreVisitPhase(raw["phase"]),
        operation_posted=raw.get("operation_posted", False),
        operation_released=raw.get("operation_released", False),
        # Missing telemetry is deliberately conservative: these values make
        # neither unobservable clause true.  The report counts the gap.
        operation_effect_observed=raw.get("operation_effect_observed", True),
        posted_sequence=raw.get("posted_sequence"),
        posted_turn=raw.get("posted_turn"),
    )


def measure(
    decision_path: Path, snapshot_path: Path | None,
    ledger_posts: dict[tuple[int, str], list[tuple[int, datetime]]],
    *, restrict_to_snapshots: bool = True,
) -> dict:
    snapshots, window_turns = ({}, set()) if snapshot_path is None else _snapshot_index(snapshot_path)
    arbiter = _new_town_turn_arbiter()
    totals = Counter()
    rows = []
    scope_rows = []
    used_ledger_rows = set()
    for index, decision in enumerate(_json_rows(decision_path)):
        turn, key = decision.get("turn"), decision.get("key")
        snapshot = None
        if snapshot_path is not None:
            candidates = snapshots.get(turn, [])
            position = decision.get("position") or {}
            wanted_position = Position(int(position.get("y", 0)), int(position.get("x", 0)))
            wanted_store = decision.get("store_type")
            match = next((i for i, candidate in enumerate(candidates) if (
                candidate.player.position == wanted_position
                and (None if candidate.store is None else candidate.store.store_type) == wanted_store
            )), None)
            if match is None and restrict_to_snapshots:
                continue
            if match is not None:
                snapshot = candidates.pop(match)
        totals["decisions"] += 1
        decision_visit = decision.get("store_visit")
        if decision_visit is not None:
            core_fields = {"operation_posted", "operation_released", "posted_sequence"}
            if core_fields <= decision_visit.keys():
                totals["open_visit_rows_telemetry_era"] += 1
                totals.setdefault("telemetry_era_first_row", index)
            else:
                totals["open_visit_rows_structurally_blind"] += 1
        candidates = ledger_posts.get((turn, key), ()) if key and turn is not None else ()
        totals[f"ledger_candidates_{len(candidates)}"] += 1
        if not decision.get("time"):
            totals["unmatched_missing_time"] += 1
            continue
        decision_time = _local_time(decision["time"])
        available = [
            (abs((when - decision_time).total_seconds()), sequence)
            for sequence, when in candidates if sequence not in used_ledger_rows
        ]
        match = min(available, default=None)
        if not candidates:
            totals["unmatched_no_candidate"] += 1
            continue
        if match is None:
            totals["unmatched_candidates_consumed"] += 1
            continue
        if match[0] > 60.0:
            totals["unmatched_outside_60_seconds"] += 1
            continue
        used_ledger_rows.add(match[1])
        totals["recorded_posts"] += 1
        raw_visit = decision.get("store_visit")
        snapshot = snapshot or _minimal_snapshot(decision)
        if raw_visit is None:
            continue
        totals["posted_with_visit"] += 1
        telemetry_fields = {
            "operation_posted", "operation_released", "operation_effect_observed",
            "posted_sequence", "posted_turn",
        }
        core_fields = {"operation_posted", "operation_released", "posted_sequence"}
        missing_fields = telemetry_fields - raw_visit.keys()
        totals["posted_with_incomplete_visit_telemetry"] += bool(missing_fields)
        totals["posted_structurally_blind"] += not (core_fields <= raw_visit.keys())
        if core_fields <= raw_visit.keys():
            totals["posted_telemetry_era"] += 1
        totals["effect_clause_unevaluable"] += bool(
            "operation_effect_observed" not in raw_visit and raw_visit.get("operation_released")
        )
        totals["posted_turn_clause_unevaluable"] += bool(
            "posted_turn" not in raw_visit and raw_visit.get("phase") == "leaving"
            and raw_visit.get("posted_sequence") is None
        )
        visit = _recorded_visit(raw_visit)
        # Old rows do not serialize the ambient approach cache.  Key-specific
        # and snapshot evidence therefore remain authoritative; no value is guessed.
        approach_store = decision.get("shopping_approach_store_type")
        verdict = emit_ownership_verdict(visit, snapshot, key, approach_store)
        target, source = derive_target_store(snapshot, key, approach_store)
        assert (target, source) == (verdict.target_store, verdict.target_source)
        totals["production_predicate_calls"] += 1
        totals["observable_in_flight_posts"] += verdict.in_flight_clause is not None
        totals["B"] += verdict.blocked
        totals["undetermined_target"] += target is None
        open_row = {
            "row": index, "turn": turn, "key": key, "reason": decision.get("reason"),
            "phase": visit.phase.value, "visit_store": visit.store_type,
            "target_store": target, "target_source": source,
            "in_flight_clause": verdict.in_flight_clause,
        }
        scope_rows.append(open_row)
        if verdict.in_flight_clause is not None:
            totals["observable_and_target_determined"] += target is not None
            totals["observable_and_undetermined"] += target is None
            totals[f"target_source_observable:{source}"] += 1
            totals[f"observable_key:{key}"] += 1
            totals[f"observable_clause:{verdict.in_flight_clause}"] += 1

            different_store = (visit.store_type + 1) % 8
            forced = emit_ownership_verdict(
                visit, snapshot, key, different_store,
            )
            totals["control_force_different_target_before"] += verdict.blocked
            totals["control_force_different_target_after"] += forced.blocked
            totals["control_force_different_target_determined"] += forced.target_store is not None

            no_flight = copy.copy(visit)
            no_flight.operation_posted = False
            no_flight.operation_released = False
            no_flight.operation_effect_observed = True
            no_flight.posted_sequence = None
            no_flight.posted_turn = None
            cleared = emit_ownership_verdict(no_flight, snapshot, key, approach_store)
            totals["control_clear_in_flight_before"] += verdict.in_flight_clause is not None
            totals["control_clear_in_flight_after"] += cleared.in_flight_clause is not None
        if verdict.blocked:
            attribution = arbiter.decision_owner_for_reason(decision.get("reason") or "")
            rows.append({
                "row": index, "turn": turn, "key": key, "reason": decision.get("reason"),
                "attribution": attribution, "visit_owner": _visit_owner(visit),
                "phase": visit.phase.value, "visit_store": visit.store_type,
                "target_store": target, "target_source": source,
            })
    totals["ledger_post_matches"] = len(used_ledger_rows)
    return {"totals": totals, "rows": rows, "scope_rows": scope_rows}


def _histogram(rows: list[dict], field: str) -> dict:
    return dict(Counter(row[field] for row in rows).most_common())


def _scope_report(name: str, rows: list[dict], *, phases: bool) -> None:
    determined = [row for row in rows if row["target_store"] is not None]
    different = [row for row in determined if row["target_store"] != row["visit_store"]]
    print(
        f"scope={name!r} count={len(rows)} keys={_histogram(rows, 'key')!r} "
        f"target_sources={_histogram(rows, 'target_source')!r} "
        f"target_determined={len(determined)} target_different_from_visit={len(different)}"
        + (f" phases={_histogram(rows, 'phase')!r}" if phases else "")
    )


def _report(label: str, result: dict) -> bool:
    t, rows, scope_rows = result["totals"], result["rows"], result["scope_rows"]
    print(f"population={label!r}")
    print(" ".join(f"{name}={t[name]}" for name in (
        "decisions", "recorded_posts", "posted_with_visit", "observable_in_flight_posts",
        "observable_and_target_determined", "observable_and_undetermined", "B",
        "undetermined_target", "production_predicate_calls",
    )))
    print(
        "conservatism='pre-telemetry rows lack operation_posted, operation_released, "
        "operation_effect_observed, posted_sequence, and posted_turn; missing clauses can only "
        "make observable in-flight and B counts too low, never too high' "
        f"posted_with_incomplete_visit_telemetry={t['posted_with_incomplete_visit_telemetry']} "
        f"posted_structurally_blind={t['posted_structurally_blind']} "
        f"posted_telemetry_era={t['posted_telemetry_era']} "
        f"telemetry_era_first_row={t.get('telemetry_era_first_row')!r} "
        f"open_visit_rows_structurally_blind={t['open_visit_rows_structurally_blind']} "
        f"open_visit_rows_telemetry_era={t['open_visit_rows_telemetry_era']} "
        f"effect_clause_unevaluable={t['effect_clause_unevaluable']} "
        f"posted_turn_clause_unevaluable={t['posted_turn_clause_unevaluable']}"
    )
    print(
        f"target_source_observable={{{', '.join(repr(k.removeprefix('target_source_observable:')) + ': ' + str(v) for k, v in sorted(t.items()) if k.startswith('target_source_observable:'))}}} "
        f"observable_keys={{{', '.join(repr(k.removeprefix('observable_key:')) + ': ' + str(v) for k, v in sorted(t.items()) if k.startswith('observable_key:'))}}} "
        f"in_flight_clauses={{{', '.join(repr(k.removeprefix('observable_clause:')) + ': ' + str(v) for k, v in sorted(t.items()) if k.startswith('observable_clause:'))}}} "
        f"determined_target_subpopulation_status={'currently empty' if not t['observable_and_target_determined'] else 'nonempty'!r}"
    )
    print(
        "whole_log_exposure='telemetry-era matched subset plus structurally blind matched rows' "
        f"telemetry_era_subset={t['posted_telemetry_era']} "
        f"structurally_blind_rows={t['posted_structurally_blind']}"
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["attribution"], row["visit_owner"], row["phase"])].append(row)
    for triple, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        print(f"B_triple={triple!r} count={len(members)} examples={[r['row'] for r in members[:5]]!r} reasons={dict(Counter(r['reason'] for r in members))!r}")
    print(
        "control='force-different-ambient-target' "
        f"B={t['control_force_different_target_before']}->{t['control_force_different_target_after']} "
        f"target_determined_after={t['control_force_different_target_determined']}"
    )
    print(
        "control='clear-in-flight' "
        f"in_flight={t['control_clear_in_flight_before']}->{t['control_clear_in_flight_after']}"
    )
    in_flight = [row for row in scope_rows if row["in_flight_clause"] is not None]
    not_in_flight = [row for row in scope_rows if row["in_flight_clause"] is None]
    _scope_report("visit OPEN", scope_rows, phases=True)
    _scope_report("visit OPEN and in flight", in_flight, phases=False)
    _scope_report("visit OPEN, not in flight", not_in_flight, phases=True)
    esc = [row for row in in_flight if row["key"] and not row["key"].strip("\x1b")]
    non_esc = [row for row in in_flight if row not in esc]
    print(
        "ESC_design='an all-ESC key only exits the current store and can never be a form-B "
        "violation; this avoids freezing the sole exit under a stale foreign visit' "
        f"in_flight_ESC={len(esc)} enforced_relevant_non_ESC={len(non_esc)}"
    )
    return bool(
        t["observable_in_flight_posts"]
        and t["control_force_different_target_after"] == t["control_force_different_target_before"]
    ) or bool(t["control_clear_in_flight_after"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("population", choices=(*WINDOWS, "whole", "all"), nargs="?", default="all")
    args = parser.parse_args()
    ledger = _ledger_posts()
    selected = WINDOWS if args.population == "all" else ({args.population: WINDOWS[args.population]} if args.population != "whole" else {})
    failed = False
    for label, (decisions, snapshots) in selected.items():
        result = measure(decisions, snapshots, ledger)
        failed |= _report(label, result)
    if args.population in {"whole", "all"}:
        result = measure(
            DECISIONS, WINDOWS["live capture (recorded)"][1], ledger,
            restrict_to_snapshots=False,
        )
        failed |= _report("bot-decisions.jsonl (whole recorded log)", result)
    whole = measure(
        DECISIONS, WINDOWS["live capture (recorded)"][1], ledger,
        restrict_to_snapshots=False,
    )
    t = whole["totals"]
    denominator = t["recorded_posts"] + t["unmatched_no_candidate"] + t["unmatched_candidates_consumed"] + t["unmatched_outside_60_seconds"]
    match_rate = 100.0 * t["recorded_posts"] / denominator if denominator else 0.0
    print(
        "ledger_cross_check='one-to-one consumption join on turn and key; timestamp proximity "
        "selected among candidates but the 60-second bound rejected no match' "
        f"matched={t['recorded_posts']} denominator={denominator} match_rate={match_rate:.3f}% "
        f"unmatched_no_candidate={t['unmatched_no_candidate']} "
        f"unmatched_candidates_consumed={t['unmatched_candidates_consumed']} "
        f"unmatched_outside_60_seconds={t['unmatched_outside_60_seconds']} "
        f"candidate_histogram={{0: {t['ledger_candidates_0']}, 1: {t['ledger_candidates_1']}, 2: {t['ledger_candidates_2']}}}"
    )
    print("telemetry_behavior_pin='serializer adds values to JSON only; decision and posted key are not read or mutated'")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
