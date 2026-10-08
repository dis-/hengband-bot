"""Reproduce the Part A Home measurement from a read-only recorded catalogue."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hengbot.equipment_optimizer import OwnedEquipmentCatalog
from hengbot.equipment_sale_classifier import classify_equipment_sales
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.warrior_optimization import (
    WarriorEvaluatorCache, _effective_intrinsic_abilities, load_character_calibration,
    prepare_warrior_optimization,
)

FIXTURE = ROOT / "tests/fixtures/equipment-sale-home-20261008.json.gz"


def capture(source: Path, calibration_path: Path, monsters_path: Path) -> None:
    raw = source.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    home_index = max(i for i, row in enumerate(rows) if row.get("knowledge", {}).get("category") == "home")
    skill = next(row for row in reversed(rows) if row.get("knowledge", {}).get("category") == "skill_exp")
    knowledge = load_monrace_knowledge(monsters_path)
    def encode(value):
        if isinstance(value, (set, frozenset)):
            return sorted(value)
        raise TypeError(type(value).__name__)
    payload = {
        "source": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "home_line": home_index + 1, "home": rows[home_index],
        "suffix": rows[home_index + 1:], "latest": rows[-1], "skill": skill,
        "calibration": json.loads(calibration_path.read_text(encoding="utf-8")),
        "monsters_source": str(monsters_path),
        "monsters_sha256": hashlib.sha256(monsters_path.read_bytes()).hexdigest(),
        "knowledge": {key: asdict(value) for key, value in knowledge.items()},
    }
    decisions_path = source.parent.parent / "home-disposal-decisions.jsonc"
    if decisions_path.exists():
        decisions = decisions_path.read_bytes()
        payload["home_disposal_decisions"] = decisions.decode("utf-8")
        payload["home_disposal_decisions_sha256"] = hashlib.sha256(decisions).hexdigest()
    FIXTURE.write_bytes(gzip.compress(json.dumps(payload, default=encode, ensure_ascii=False).encode("utf-8"), mtime=0))


def recorded_inputs(path: Path = FIXTURE):
    data = json.loads(gzip.decompress(path.read_bytes()))
    knowledge = {}
    for key, value in data["knowledge"].items():
        value["flags"] = frozenset(value["flags"])
        value["abilities"] = frozenset(value["abilities"])
        value["blows"] = tuple(MonsterBlow(**row) for row in value["blows"])
        knowledge[int(key)] = MonraceKnowledge(**value)
    # An isolated policy reads captured ownership decisions and never chooses a key.
    # The state log records equipment/supplies, not checkpoint-only purchases
    # or open transactions; that limitation is stated in the report.
    with tempfile.TemporaryDirectory(prefix="equipment-sale-A-") as directory:
        if "home_disposal_decisions" in data:
            (Path(directory) / "home-disposal-decisions.jsonc").write_text(data["home_disposal_decisions"], encoding="utf-8")
        policy = HengbotPolicy(monrace_knowledge=knowledge,
                               home_disposal_state=HomeDisposalState.in_repo(Path(directory)))
        policy.consume_skill_knowledge(data["skill"])
        snapshot = policy._with_cached_skill_exp(parse_snapshot(data["latest"], knowledge))
        home_data = data["home"]["knowledge"]["items"]
        home = tuple(_parse_items(home_data, protocol=data["home"]["protocol_version"]))
        catalog = OwnedEquipmentCatalog()
        catalog.complete_home_scan(home)
        catalog.refresh_carried(snapshot.inventory, snapshot.equipment)
        policy._equipment_catalog = catalog
        # A complete ~9 list remains current only if every later Home page
        # matches it and no carried item changed during the recorded suffix.
        current = True
        baseline_pack = data["home"]["inventory"]
        for row in data["suffix"]:
            if row["inventory"] != baseline_pack:
                current = False
            store = row.get("store")
            if store and store["store_type"] == 7:
                if store["stock_num"] != len(home_data):
                    current = False
                for offset, item in enumerate(store["items"]):
                    original = home_data[store["page_top"] + offset]
                    for key in ("name", "count", "tval", "sval", "known", "fully_known", "known_flags", "to_h", "to_d", "to_a", "pval"):
                        if item.get(key) != original.get(key):
                            current = False
        calibration_path = Path(directory) / "calibration.json"
        calibration_path.write_text(json.dumps(data["calibration"]), encoding="utf-8")
        calibration = load_character_calibration(calibration_path)
        if calibration is None:
            raise ValueError("recorded calibration unavailable")
        cache = WarriorEvaluatorCache()
        ammunition = (*snapshot.inventory, *home)
        destruction = policy._has_destruction_method(snapshot)
        preparation = prepare_warrior_optimization(
            snapshot, catalog.items, knowledge, depth=None,
            home_scan_complete=catalog.home_scan_complete,
            calibration=calibration, evaluator_cache=cache,
            has_destruction=destruction, obtainable_ammunition=ammunition,
            timeout_seconds=120,
        )
        if preparation.result is None or cache.evaluator is None:
            raise ValueError(f"recorded preparation blocked: {preparation.blockers}")
        reserved = policy.equipment_sale_reserved_ids(snapshot)
    return data, catalog, snapshot, cache.evaluator, {
        "class_id": snapshot.player.class_id,
        "home_scan_complete": catalog.home_scan_complete,
        "catalogue_current": current,
        "reserved_ids": reserved,
        "intrinsic_abilities": _effective_intrinsic_abilities(snapshot.player, calibration.intrinsic_abilities),
        "has_destruction": destruction,
        "obtainable_ammunition": ammunition,
        "timeout_seconds": 120,
    }


def category(owned) -> str:
    tval = owned.item.tval
    if tval in {19, 20, 21, 22, 23}:
        return "weapons"
    if tval in {36, 37, 38}:
        return "body"
    if tval in {40, 45}:
        return "jewelry"
    if tval in {30, 31, 32, 33}:
        return "head/hands/feet"
    return {34: "shields", 35: "cloaks", 39: "lights"}.get(tval, "other")


def measure():
    data, catalog, snapshot, evaluator, options = recorded_inputs()
    home = tuple(owned for owned in catalog.items if owned.origin == "home")
    variants = {}
    classifications = {}
    for scope, duplicates in (("E", "S"), ("E", "D"), ("J", "S"), ("J", "D")):
        result = classify_equipment_sales(catalog.items, lambda loadout: evaluator(loadout).metrics,
                                          scope=scope, duplicates=duplicates, **options)
        if result.blockers:
            raise ValueError(f"classification blocked: {result.blockers}")
        key = scope + duplicates
        counts = {name: sum(owned.id in result.sold_ids and category(owned) == name for owned in home)
                  for name in ("weapons", "body", "jewelry", "head/hands/feet", "shields", "cloaks", "lights")}
        sold = sum(owned.id in result.sold_ids for owned in home)
        variants[key] = {"sold": sold, "kept_equipment": len(home) - sold,
                         "kept_home_entries": len(data["home"]["knowledge"]["items"]) - sold,
                         "pareto": sum(owned.id in result.pareto_ids for owned in home),
                         "needs_identification": sum(owned.id in result.needs_identification_ids for owned in home),
                         "categories": counts}
        classifications[key] = result
    return data, home, variants, classifications


def report() -> str:
    data, home, variants, classifications = measure()
    lines = ["Variant | Weapons | Body | Jewelry | Head/hands/feet | Shields | Cloaks | Lights | SOLD | Kept equipment | Kept Home entries | Existing Pareto | Needs ID",
             "--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:"]
    for key, row in variants.items():
        counts = row["categories"]
        lines.append(" | ".join(map(str, [key, *counts.values(), row["sold"], row["kept_equipment"], row["kept_home_entries"], row["pareto"], row["needs_identification"]])))
    validation_path = ROOT / "validation/sell-equipment-A/results.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else {}
    lines.extend([
        "", "STATUS: INCOMPLETE -- stop condition in SOL-TASK.txt encountered.",
        "The table is provisional under the existing cumulative depth gates, not the authoritative AGENTS.md per-band gates.",
        "Conflict: equipment_optimizer.required_abilities (line 162) carries 20-30F requirements into 31F+. AGENTS.md requires chaos only at 31-39F and chaos/nether at 40-49F.",
        "Existing asserted expectation tests/test_equipment_optimizer.py:test_deeper_resists_cannot_skip_missing_free_action_band requires chaos/nether without Free Action to stop at 19F; the authoritative table allows 49F. test_elemental_resists_alone_stop_at_the_free_action_gate also contradicts the 26-30F band.",
        "The newly added test_depth_none_exposes_lower_band_winner_after_selection expects 39F with chaos-only armour but receives 25F. No existing assertion was changed. Stopped when this conflict was identified, as explicitly directed.",
        "Outstanding: reconcile existing cumulative-gate expectations with the authoritative table, rerun the measurement and tests; tighten J jewelry scope to explicitly non-ego jewelry (current measurement includes all magical jewelry). No sale-path work is authorized in Part A.",
        f"Validation: {len(validation.get('tests', []))} tests, {len(validation.get('failures', []))} failure(s), {len(validation.get('errors', []))} error(s), --workers 1; validation/sell-equipment-A/results.json and summary.json.",
        "All 93 existing equipment-optimizer tests, 13 fakery-lint tests and 7 existing Home equipment-disposal regression tests passed; 12 new pins passed, the new authoritative-band pin failed. Initial required-only run: 118/118 passed before adding that pin.",
        "Pins cover the recorded catalogue, 28 artifacts, an otherwise saleable artifact, unidentified/full-ID missing items, reserved items, S/D duplicates, ring/melee/fixed capacities, retained witnesses, ability/resistance swaps, launcher damage/ammo/grade and class/scan/freshness gates.",
        "Token usage: exact counter is unavailable in this environment (tokens_used=null); dispatch cap 60,000. Stopping because of the explicit expectation-conflict rule, not the token cap.",
    ])
    lines.extend([
        "", "E: ego/excellent weapons and armour. J: E plus magical jewelry and dragon armour/shields/boots.",
        "S: strict upgrades only. D: identical copies beyond capacity (rings/melee 2, other slots 1).",
        f"Source: read-only copy of {data['source']}; SHA256 {data['source_sha256']}.",
        f"Last complete Home knowledge: line {data['home_line']}, turn {data['home']['turn']}; latest board turn {data['latest']['turn']}.",
        f"Home equipment catalogue: {len(home)} entries; full Home: {len(data['home']['knowledge']['items'])} entries.",
        "Later Home pages and carried inventory match the complete knowledge (freshness gate).",
        "Japanese names and numeric/identification fields are preserved verbatim from the UTF-8 JSONL. No names or identification fields inferred from the older dump.",
        "Numbers are hypothetical Home-entry counts, not completed sales. Pack/worn gear participates as witnesses; consumables are outside these scopes.",
        "Captured durable Home keep decisions are applied with observed supplies/light/digging retention. JSONL does not serialize open transactions or visit purchases; the measurement assumes no unrecorded owners. Live callers must pass equipment_sale_reserved_ids from their actual policy.",
        "Existing Pareto column uses disposable_dominated_item_ids with the same scope/identification/reservation/winner guards, independently of the score result.",
        "Design: equipment_sale_classifier.classify_equipment_sales; policy_equipment.equipment_sale_reserved_ids; equipment_optimizer.optimize_loadout.band_best_loadouts; launcher_damage.launcher_dominates (shared legacy proof).",
        "Scores: confirmed-current single-slot trials, existing WarriorSingleSlotSearch hand rules, AC-100 per-turn combat/survival evaluator and _prefer; flags must cover abilities/resistances/slays/brands. No weight ranking.",
        "Band protection uses depth=None and retains every existing optimizer band winner. Warrior, complete Home, current catalogue and complete evaluation gates fail closed.",
        "Part A only: no sale path or live scope choice installed. No game/bot launch or push.",
        "", "Artifacts kept in all variants:",
    ])
    for owned in home:
        if owned.item.is_artifact:
            lines.append(f"- slot {owned.item.slot}, tval/sval {owned.item.tval}/{owned.item.sval}: {owned.item.name}")
    lines.append("\nNeeds identification first (all variants):")
    unknown = classifications["ES"].needs_identification_ids
    lines.extend(f"- slot {owned.item.slot}, tval/sval {owned.item.tval}/{owned.item.sval}: {owned.item.name}" for owned in home if owned.id in unknown)
    if not any(owned.id in unknown for owned in home):
        lines.append("- none")
    for key, result in classifications.items():
        lines.append(f"\n{key} kept non-artifact equipment and reason:")
        lines.extend(f"- slot {owned.item.slot}, tval/sval {owned.item.tval}/{owned.item.sval}: {owned.item.name} -- {result.reasons[owned.id]}"
                     for owned in home if not owned.item.is_artifact and owned.id not in result.sold_ids)
        lines.append(f"\n{key} hypothetical sale list (retained-witness proof):")
        lines.extend(f"- slot {owned.item.slot}, {owned.item.name} -- witnesses: {', '.join(result.dominators[owned.id])}"
                     for owned in home if owned.id in result.sold_ids)
    lines.append(json.dumps({"topic": "sell-equipment-A", "variants": variants,
                             "source_sha256": data["source_sha256"], "part": "A", "sale_path_built": False,
                             "status": "INCOMPLETE", "provisional": True,
                             "blocker": "authoritative depth gates conflict with existing asserted expectations",
                             "tests": {"total": len(validation.get("tests", [])),
                                       "failures": validation.get("failures", []), "errors": validation.get("errors", []), "workers": 1},
                             "tokens_used": None, "token_cap": 60000}))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--monsters", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "SOL-REPORT-A.txt")
    args = parser.parse_args()
    if args.capture:
        capture(args.capture, args.calibration, args.monsters)
    output = report()
    args.output.write_text(output, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(output, end="")


if __name__ == "__main__":
    main()
