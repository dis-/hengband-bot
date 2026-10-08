"""Shared value-level launcher damage arithmetic."""

STORE_AMMO_AVERAGE_DAMAGE = {16: 2.0, 17: 2.5, 18: 3.0}
LAUNCHER_PROPERTIES = {
    2: (16, 8000, 2),
    12: (17, 10000, 2),
    13: (17, 10000, 3),
    23: (18, 12000, 3),
    24: (18, 13333, 4),
}


def launcher_average_damage(launcher, ammo=None) -> float:
    """Return per-shot launcher damage for one compatible ammunition stack."""
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    ammo_tval, _energy, multiplier = LAUNCHER_PROPERTIES[launcher.sval]
    if ammo is not None and (ammo.tval != ammo_tval or ammo.count <= 0):
        return 0.0
    ammo_damage = STORE_AMMO_AVERAGE_DAMAGE[ammo_tval]
    if ammo is not None:
        if ammo.damage_dice_num > 0 and ammo.damage_dice_sides > 0:
            ammo_damage = ammo.damage_dice_num * (ammo.damage_dice_sides + 1) / 2
        ammo_damage += ammo.to_d
    return max(0.0, (ammo_damage + launcher.to_d) * multiplier)


def best_obtainable_launcher_damage(launcher, ammunition) -> float:
    """Return damage with the best compatible carried or catalogued ammo."""
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    ammo_tval = LAUNCHER_PROPERTIES[launcher.sval][0]
    return max(
        (
            launcher_average_damage(launcher, ammo)
            for ammo in ammunition
            if ammo.tval == ammo_tval and ammo.count > 0
        ),
        default=0.0,
    )


def launcher_dominates(
    left, right, left_damage: float, right_damage: float, *, same_ammo: bool = True,
) -> bool:
    """The spare-launcher proof, usable with equipped or owned launchers."""
    from hengbot.equipment_optimizer import launcher_is_high_grade, ordinary_launcher_yields_to_light_crossbow

    if ((same_ammo and (left.ammo_tval is None or left.ammo_tval != right.ammo_tval))
            or ordinary_launcher_yields_to_light_crossbow(left, right)):
        return False
    left_grade = (int(left.is_artifact), int(launcher_is_high_grade(left) if same_ammo else left.is_ego))
    right_grade = (int(right.is_artifact), int(launcher_is_high_grade(right) if same_ammo else right.is_ego))
    return (
        left_damage >= right_damage
        and left.to_h >= right.to_h
        and left.pval >= right.pval
        and left.known_flags.issuperset(right.known_flags)
        and left_grade >= right_grade
        and (left_damage > right_damage or left.to_h > right.to_h
             or left.pval > right.pval or left.known_flags > right.known_flags
             or left_grade > right_grade)
    )
