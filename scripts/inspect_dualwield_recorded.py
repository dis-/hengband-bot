"""Read-only reconstruction of the 2026-10-01 loadout search."""
from dataclasses import asdict, replace
import json
from pathlib import Path

from hengbot.equipment_optimizer import Loadout, OwnedEquipmentCatalog
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import (
    CharacterCalibration, WarriorEvaluatorCache, prepare_warrior_optimization,
)

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/dualwield-20261001.json"


def recorded_inputs():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snapshot = parse_snapshot(data["board"], {})
    skills = {row["id"]: row["exp"] for row in data["skills"]["knowledge"]["skills"]}
    snapshot = replace(snapshot, player=replace(
        snapshot.player, two_weapon_skill=skills[1], shield_skill=skills[3],
    ))
    catalog = OwnedEquipmentCatalog()
    catalog.refresh_carried(snapshot.inventory, snapshot.equipment)
    catalog.complete_home_scan(_parse_items(data["home"]["knowledge"]["items"], protocol=3))
    # Recorded macro dkdjdd\x1b at T1493262 deposits k, j, then d.
    before = _parse_items(data["before_deposit"]["inventory"], protocol=3)
    for item in before:
        if item.slot in {"j", "k", "d"}:
            catalog.record_home_deposit(item, intent=(1493262, item.slot))
    constants = data["calibration"]
    for key in ("stat_cur", "base_stats", "pinned_identities", "mutation_signature"):
        constants[key] = tuple(constants[key])
    for key in ("intrinsic_abilities", "intrinsic_tr_flags"):
        constants[key] = frozenset(constants[key])
    return data, snapshot, catalog.items, CharacterCalibration(**constants)


def reconstruct(monrace_path):
    data, snapshot, items, calibration = recorded_inputs()
    cache = WarriorEvaluatorCache()
    knowledge = load_monrace_knowledge(Path(monrace_path))
    preparation = prepare_warrior_optimization(
        snapshot, items, knowledge, depth=None, home_scan_complete=True,
        calibration=calibration, evaluator_cache=cache, timeout_seconds=120,
    )
    evaluator = cache.evaluator
    if evaluator is None or preparation.result is None:
        raise RuntimeError(preparation.blockers)
    current = preparation.current
    main = current.item_at("main_hand")
    sub = current.item_at("sub_hand")
    armor = tuple((s, i) for s, i in current.slots if s not in {"main_hand", "sub_hand"})
    loadouts = {
        "spear_two_handed": Loadout(tuple(sorted(armor + (("main_hand", main),))), "two_handed"),
        "scythe_two_handed": Loadout(tuple(sorted(armor + (("main_hand", sub),))), "two_handed"),
        "dual": current,
        "chosen": preparation.result.best.loadout,
    }
    result = {
        "turn": snapshot.turn, "catalog_size": len(items),
        "inputs": asdict(evaluator.inputs.combat),
        "considered": preparation.result.combinations_considered,
        "evaluated": preparation.result.combinations_evaluated,
        "chosen_band": preparation.result.chosen_depth,
        "bands": [asdict(d) for d in preparation.result.band_decisions],
        "loadouts": {},
    }
    for name, loadout in loadouts.items():
        detail = evaluator(loadout)
        result["loadouts"][name] = {
            "slots": {s: i.id for s, i in loadout.slots},
            "melee": detail.metrics.expected_dps,
            "survival": detail.metrics.survival_turns,
            "margin": detail.metrics.combat_margin,
            "hands": [asdict(h) for h in detail.melee.hands],
        }
    return result


if __name__ == "__main__":
    import sys
    print(json.dumps(reconstruct(sys.argv[1]), ensure_ascii=False, indent=2))
