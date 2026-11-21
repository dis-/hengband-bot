"""Shared value-level launcher damage arithmetic."""

STORE_AMMO_AVERAGE_DAMAGE = {16: 2.0, 17: 2.5, 18: 3.0}
LAUNCHER_PROPERTIES = {
    2: (16, 8000, 2),
    12: (17, 10000, 2),
    13: (17, 10000, 3),
    23: (18, 12000, 3),
    24: (18, 13333, 4),
}
# TR flag numbers (src/object-enchant/tr-types.h).
TR_XTRA_MIGHT = 82
TR_XTRA_SHOTS = 83


def launcher_multiplier(launcher) -> int:
    """The launcher's own multiplier: its kind's, plus one for extra might (shoot.cpp tmul++)."""
    multiplier = LAUNCHER_PROPERTIES[launcher.sval][2]
    return multiplier + (TR_XTRA_MIGHT in getattr(launcher, "known_flags", frozenset()))


def launcher_average_damage(launcher, ammo=None) -> float:
    """Return per-shot launcher damage for one compatible ammunition stack."""
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    ammo_tval = LAUNCHER_PROPERTIES[launcher.sval][0]
    multiplier = launcher_multiplier(launcher)
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


def launcher_turn_damage(launcher, ammo=None) -> float:
    """Damage per player turn (100 energy) of one compatible stack, or of plain store ammunition.

    The per-shot damage times the launcher's own shots per turn: num_fire 100 plus 100 for its
    extra shots, over its kind's energy (player-status.cpp calc_num_fire, the bow's
    ``(1.20turn)``).  Owner 2026-11-19 「攻撃力の判定はすべて10ゲームターンあたりの被害で評価」:
    at one speed, per player turn orders as per game time does."""
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    energy = LAUNCHER_PROPERTIES[launcher.sval][1]
    shots = 100 + 100 * (TR_XTRA_SHOTS in getattr(launcher, "known_flags", frozenset()))
    return launcher_average_damage(launcher, ammo) * shots * 100 / energy


def best_obtainable_launcher_turn_damage(launcher, ammunition) -> float:
    """``launcher_turn_damage`` with the best compatible stack of ``ammunition``."""
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    ammo_tval = LAUNCHER_PROPERTIES[launcher.sval][0]
    return max(
        (
            launcher_turn_damage(launcher, ammo)
            for ammo in ammunition
            if ammo.tval == ammo_tval and ammo.count > 0
        ),
        default=0.0,
    )
