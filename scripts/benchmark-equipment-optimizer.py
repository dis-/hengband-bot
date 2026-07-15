"""Benchmark terminal-scale Warrior equipment optimization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic

from hengbot.equipment_encounters import normal_encounters, representative_encounters
from hengbot.equipment_optimizer import OwnedEquipment, optimize_loadout
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.monster_ranged_evaluator import SpellSelectionContext
from hengbot.warrior_defense_evaluator import WarriorDefenseInputs
from hengbot.warrior_equipment_evaluator import WarriorCombatInputs
from hengbot.warrior_loadout_evaluator import (
    CachedWarriorLoadoutEvaluator,
    WarriorLoadoutInputs,
)
from hengbot.warrior_loadout_search import enumerate_warrior_loadouts


TERMINAL_SLOT_COUNTS = {
    19: 6,
    20: 20,
    21: 14,
    22: 14,
    23: 14,
    34: 11,
    40: 17,
    39: 7,
    36: 21,
    35: 11,
    32: 13,
    31: 6,
    30: 4,
    45: 17,
}
UTILITY_FLAGS = (
    46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
    56, 57, 58, 59, 60, 61, 62, 63, 76, 79,
)


def terminal_catalog() -> tuple[OwnedEquipment, ...]:
    result = []
    serial = 0
    for tval, count in TERMINAL_SLOT_COUNTS.items():
        for index in range(count):
            serial += 1
            flags = {
                UTILITY_FLAGS[(index * 3 + offset + tval) % len(UTILITY_FLAGS)]
                for offset in range(1 + index % 4)
            }
            if tval == 45 and index % 4 == 0:
                flags.add(12)  # speed
            if tval in {20, 21, 22, 23} and index % 5 == 0:
                flags.add(0)  # strength
            weapon = tval in {20, 21, 22, 23}
            protector = tval in {30, 31, 32, 34, 35, 36}
            item = InventoryItem(
                slot=str(serial),
                name=f"terminal-{tval}-{index}",
                count=1,
                tval=tval,
                sval=index,
                aware=True,
                known=True,
                fully_known=True,
                is_equipment=True,
                known_flags=frozenset(flags),
                pval=(4 + index % 6) if flags.intersection({0, 12}) else 0,
                ac=index % 12 if protector else 0,
                to_a=index % 20 if protector else 0,
                to_h=index % 15,
                to_d=index % 18,
                damage_dice_num=1 + index % 6 if weapon else 0,
                damage_dice_sides=4 + index % 8 if weapon else 0,
                weight=50 + index * 7 if weapon else 0,
                weapon_proficiency=4000,
            )
            result.append(OwnedEquipment(f"home:{serial}", item, "home"))
    return tuple(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monrace", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-encounters", type=int, default=64)
    args = parser.parse_args()

    knowledge = load_monrace_knowledge(args.monrace)
    all_encounters = normal_encounters(knowledge, args.depth)
    encounters = representative_encounters(
        all_encounters, max_count=args.max_encounters
    )
    catalog = terminal_catalog()
    inputs = WarriorLoadoutInputs(
        WarriorCombatInputs(
            level=50,
            natural_str=238,
            natural_dex=238,
            melee_skill=200,
            two_weapon_skill=8000,
        ),
        WarriorDefenseInputs(
            level=50,
            natural_dex=238,
            shield_skill=8000,
            base_ac_bonus=20,
            base_speed=110,
            saving_skill=100,
        ),
        1000,
        SpellSelectionContext(),
    )
    evaluator = CachedWarriorLoadoutEvaluator(inputs, encounters)
    search = enumerate_warrior_loadouts(catalog)
    started = monotonic()
    result = optimize_loadout(
        catalog,
        lambda loadout: evaluator(loadout).metrics,
        depth=args.depth,
        has_destruction=True,
        timeout_seconds=args.timeout,
        candidate_loadouts=search,
    )
    print(
        json.dumps(
            {
                "catalog_items": len(catalog),
                "encounters": len(encounters),
                "encounters_total": len(all_encounters),
                "elapsed_seconds": round(monotonic() - started, 3),
                "considered": result.combinations_considered,
                "evaluated": result.combinations_evaluated,
                "invalid": result.invalid_combinations,
                "timed_out": result.timed_out,
                "search_truncated": result.search_truncated,
                "cache_sizes": evaluator.cache_sizes,
                "has_best": result.best is not None,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
