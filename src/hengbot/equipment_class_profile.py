"""Class-table inputs for the shared equipped-sheet loadout evaluator."""
from dataclasses import dataclass


@dataclass(frozen=True)
class EquipmentClassProfile:
    max_blows: int
    minimum_weapon_weight: int
    strength_multiplier: int
    warrior_bonuses: bool = False


# src/player-info/class-info.cpp: num, wgt, mul. Skills and stat adjustments
# already come from the visible board and C sheet, respectively.
EQUIPMENT_CLASS_PROFILES = {
    0: EquipmentClassProfile(6, 70, 5, warrior_bonuses=True),
    16: EquipmentClassProfile(5, 100, 3),
}
