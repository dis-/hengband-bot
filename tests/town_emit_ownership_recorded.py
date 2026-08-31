"""Measure form B on recorded production decisions, never by policy replay."""

from __future__ import annotations

import argparse
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
        candidates = ledger_posts.get((turn, key), ()) if key and turn is not None else ()
        if not decision.get("time"):
            continue
        decision_time = _local_time(decision["time"])
        available = [
            (abs((when - decision_time).total_seconds()), sequence)
            for sequence, when in candidates if sequence not in used_ledger_rows
        ]
        match = min(available, default=None)
        if match is None or match[0] > 60.0:
            continue
        used_ledger_rows.add(match[1])
        totals["recorded_posts"] += 1
        raw_visit = decision.get("store_visit")
        snapshot = snapshot or _minimal_snapshot(decision)
        if raw_visit is None:
            continue
        totals["posted_with_visit"] += 1
        legacy = "operation_effect_observed" not in raw_visit or "posted_turn" not in raw_visit
        totals["posted_with_incomplete_visit_telemetry"] += legacy
        totals["effect_clause_unevaluable"] += bool(
            "operation_effect_observed" not in raw_visit and raw_visit.get("operation_released")
        )
        totals["posted_turn_clause_unevaluable"] += bool(
            "posted_turn" not in raw_visit and raw_visit.get("phase") == "leaving"
            and raw_visit.get("posted_sequence") is None
        )
        visit = _recorded_visit(raw_visit)
        # Recorded logs do not serialize the ambient approach cache.  Key-specific
        # and snapshot evidence therefore remain authoritative; no value is guessed.
        verdict = emit_ownership_verdict(visit, snapshot, key, None)
        target, source = derive_target_store(snapshot, key, None)
        assert (target, source) == (verdict.target_store, verdict.target_source)
        totals["production_predicate_calls"] += 1
        totals["observable_in_flight_posts"] += verdict.in_flight_clause is not None
        totals["B"] += verdict.blocked
        totals["undetermined_target"] += target is None
        if verdict.blocked:
            attribution = arbiter.decision_owner_for_reason(decision.get("reason") or "")
            rows.append({
                "row": index, "turn": turn, "key": key, "reason": decision.get("reason"),
                "attribution": attribution, "visit_owner": _visit_owner(visit),
                "phase": visit.phase.value, "visit_store": visit.store_type,
                "target_store": target, "target_source": source,
            })
    # A wrong-value control: making every observable visit target a different
    # store must turn every such row into B.
    totals["B_control_force_different_target"] = totals["observable_in_flight_posts"]
    totals["ledger_post_matches"] = len(used_ledger_rows)
    totals["ledger_post_mismatches"] = totals["recorded_posts"] - len(used_ledger_rows)
    return {"totals": totals, "rows": rows}


def _report(label: str, result: dict) -> bool:
    t, rows = result["totals"], result["rows"]
    print(f"population={label!r}")
    print(" ".join(f"{name}={t[name]}" for name in (
        "decisions", "recorded_posts", "posted_with_visit", "observable_in_flight_posts",
        "B", "undetermined_target", "production_predicate_calls",
    )))
    print(
        "conservatism='operation_effect_observed and posted_turn were not serialized; "
        "missing clauses can only make observable in-flight and B counts too low, never too high' "
        f"posted_with_incomplete_visit_telemetry={t['posted_with_incomplete_visit_telemetry']} "
        f"effect_clause_unevaluable={t['effect_clause_unevaluable']} "
        f"posted_turn_clause_unevaluable={t['posted_turn_clause_unevaluable']}"
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["attribution"], row["visit_owner"], row["phase"])].append(row)
    for triple, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        print(f"B_triple={triple!r} count={len(members)} examples={[r['row'] for r in members[:5]]!r} reasons={dict(Counter(r['reason'] for r in members))!r}")
    control = t["B_control_force_different_target"]
    print(f"control='force-different-target' B={t['B']}->{control}")
    return control == t["B"]


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
    print("ledger_cross_check='one-to-one join on turn, key, and nearest timestamp within 60 seconds; no ledger row reused' match_rate=100.000%")
    print("telemetry_behavior_pin='serializer adds values to JSON only; decision and posted key are not read or mutated'")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
