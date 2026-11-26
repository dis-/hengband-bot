"""Class-table inputs for the shared equipped-sheet loadout evaluator."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EquipmentClassProfile:
    max_blows: int
    minimum_weapon_weight: int
    strength_multiplier: int
    warrior_bonuses: bool = False
    # player-status.cpp calc_num_blow :1467-1468: a Rogue's weapon under 5.0 lb with DEX
    # stat_index 30+ gives one more blow.
    light_weapon_extra_blow: bool = False
    # player-status.cpp calc_num_fire :983-989: ammo tval -> shots (of 100) per level.
    shots_per_level: tuple[tuple[int, int], ...] = field(default_factory=tuple)


TVAL_SHOT, TVAL_ARROW, TVAL_BOLT = 16, 17, 18
ROGUE_LIGHT_WEAPON_WEIGHT = 50
ROGUE_LIGHT_WEAPON_DEX_INDEX = 30

# src/player-info/class-info.cpp: num, wgt, mul (Warrior :82-85, Rogue :97-100,
# Magic-Eater :162-165). Skills and stat adjustments already come from the visible
# board and C sheet, respectively.
EQUIPMENT_CLASS_PROFILES = {
    0: EquipmentClassProfile(
        6, 70, 5, warrior_bonuses=True,
        shots_per_level=((TVAL_SHOT, 2), (TVAL_ARROW, 2), (TVAL_BOLT, 2))),
    3: EquipmentClassProfile(
        5, 40, 3, light_weapon_extra_blow=True, shots_per_level=((TVAL_SHOT, 4),)),
    16: EquipmentClassProfile(5, 100, 3),
}


def class_extra_blows(class_id: int, *, level: int, weapon_weight: int, dex_idx: int) -> int:
    """calc_num_blow's class term after the table (:1463-1469)."""
    profile = EQUIPMENT_CLASS_PROFILES[class_id]
    if profile.warrior_bonuses:
        return level // 40
    if (profile.light_weapon_extra_blow and weapon_weight < ROGUE_LIGHT_WEAPON_WEIGHT
            and dex_idx >= ROGUE_LIGHT_WEAPON_DEX_INDEX):
        return 1
    return 0


def class_shots_bonus(class_id: int, *, level: int, ammo_tval: int) -> int:
    """calc_num_fire's class term for a launcher that is not too heavy (:960-989)."""
    profile = EQUIPMENT_CLASS_PROFILES.get(class_id)
    if profile is None:
        return 0
    return level * dict(profile.shots_per_level).get(ammo_tval, 0)
