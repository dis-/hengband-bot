"""Shared value-level launcher damage arithmetic.

``plain_ammo_turn_damage`` is the one figure launchers are compared by (owner 2026-11-22,
verbatim: 「射撃武器の比較には店で買える並の矢弾を使って。」): every launcher with the plain round
of its kind the Weaponsmith always stocks, never the rounds one of them happens to own.  The
optimizer's ``ranged_dps`` (warrior_loadout_evaluator), the shop's waiting launcher
(launcher_upgrade) and the spare-launcher check (policy_equipment) read it.
"""
from __future__ import annotations

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


# The plain round of each kind the Weaponsmith always stocks (store/articles-on-sale.cpp:44-49,
# SV_AMMO_NORMAL): (dice number, dice sides, weight) from lib/edit/BaseitemDefinitions.jsonc
# (鉄弾 1d3 weight 5, 矢 1d4 weight 2, クロスボウの矢 1d5 weight 3), +0/+0.
PLAIN_AMMO = {16: (1, 3, 5), 17: (1, 4, 2), 18: (1, 5, 3)}
BTH_PLUS_ADJ = 3
CROSSBOW_SVALS = frozenset({23, 24})
MEDIAN_WEAPON_EXP = 4000  # PlayerSkill::weapon_exp_at(MASTER) / 2


def launcher_proficiency_term(launcher) -> int:
    """exec_shoot's weapon-experience term (shoot.cpp:499-507, C division truncates to zero)."""
    proficiency = getattr(launcher, "weapon_proficiency", 0) or 0
    if launcher.sval in CROSSBOW_SVALS:
        return proficiency // 400
    return int((proficiency - MEDIAN_WEAPON_EXP) / 200)


def shot_hit_chance(chance: int, ac: int, *, lazy: bool = False) -> float:
    """test_hit_fire (shoot.cpp:959-1018) for a visible target as a probability: 5% always
    misses, 5% always hits, else ``randint0(chance) >= ac * 3 / 4``; a lazy personality misses
    one in 20 of the rest."""
    if chance <= 0:
        return 0.05
    passed = max(0, chance - ac * 3 // 4) / chance
    return 0.05 + 0.90 * passed * (19 / 20 if lazy else 1.0)


def shot_critical_factor(power: int, ammo_weight: int) -> float:
    """The expected damage factor of critical_shot (shoot.cpp:1026-1077), as
    calc_expect_crit_shot (:1129-1160) computes it: a critical at ``power`` / 10000; then by
    ``weight * randint1(500)``: below 900 x1.5, below 1350 x2, else x3."""
    chance = min(10000, max(0, power)) / 10000
    good = min(500, 900 // ammo_weight)
    great = min(500, 1350 // ammo_weight) - good
    superb = max(0, 500 - good - great)
    critical = (1.5 * good + 2 * great + 3 * superb) / 500
    return chance * critical + (1 - chance)


def plain_ammo_turn_damage(
    launcher,
    *,
    skill_thb: int,
    to_h_b: int = 0,
    str_td: int = 0,
    extra_shots: int = 0,
    shots_bonus: int = 0,
    xtra_might: bool = False,
    target_ac: int = 100,
    lazy: bool = False,
) -> float:
    """Expected damage per player turn (100 energy) of ``launcher`` shooting the plain store
    round of its kind at a visible target of ``target_ac``.

    combat/shoot.cpp exec_shoot: the base (dice + ammo to_d + bow to_d, :489) times tmul -
    the kind's multiplier, +1 for extra might (:511-516), times (100 + adj_str_td - 128) / 100
    (:518-522, ``str_td``) - hit with ``chance = skill_thb + (weapon-exp term + to_h_b + ammo
    to_h + bow to_h) * BTH_PLUS_ADJ`` (:492-507, test_hit_fire), the critical with ``power =
    skill_thb + (weapon-exp term + to_h_b + ammo to_h) * BTH_PLUS_ADJ + bow to_h * 40``
    (critical_shot :1026-1062, the ammunition's weight).  Shots: num_fire = 100 + 100 per
    extra shots (the launcher's own and ``extra_shots`` of the other gear) + ``shots_bonus``
    (the class term, player-status.cpp calc_num_fire :930-990), over the kind's energy
    (get_bow_energy).  ``to_h_b`` is calc_to_hit_bow's (stats, the other gear's to_h, a heavy
    launcher's penalty); ``xtra_might`` the other gear's flag (the launcher's own is read here).
    """
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    ammo_tval, energy, multiplier = LAUNCHER_PROPERTIES[launcher.sval]
    dice_num, dice_sides, weight = PLAIN_AMMO[ammo_tval]
    flags = getattr(launcher, "known_flags", frozenset())
    multiplier += int(xtra_might or TR_XTRA_MIGHT in flags)
    base = dice_num * (dice_sides + 1) / 2 + launcher.to_d
    damage = max(0.0, base * multiplier * (100 + str_td) / 100)
    proficiency = launcher_proficiency_term(launcher)
    hit = shot_hit_chance(
        skill_thb + (proficiency + to_h_b + launcher.to_h) * BTH_PLUS_ADJ, target_ac, lazy=lazy)
    critical = shot_critical_factor(
        skill_thb + (proficiency + to_h_b) * BTH_PLUS_ADJ + launcher.to_h * 8 * 5, weight)
    shots = 100 + 100 * (extra_shots + (TR_XTRA_SHOTS in flags)) + shots_bonus
    return hit * damage * critical * shots * 100 / energy


def snapshot_plain_ammo_turn_damage(snapshot, launcher) -> float:
    """``plain_ammo_turn_damage`` for a launcher checked outside an evaluated loadout (the
    shop's waiting launcher, Home's spare launcher): the sheet's shooter for every launcher of
    the check.  skill_thb is the sheet's; to_h_b is read back from the sheet's shooting value
    (skill_thb + (to_h_b + the worn bow's to_h) * BTH_PLUS_ADJ, status-first-page.cpp:294),
    0 without it; the STR term is left out (a common factor of every launcher)."""
    player = snapshot.player
    skill = getattr(player, "shooting_skill", 0) or 0
    rating = getattr(player, "shooting_rating", None)
    worn = next((item for item in getattr(snapshot, "equipment", ())
                 if getattr(item, "slot", None) == "bow"), None)
    to_h_b = 0
    if rating is not None:
        to_h_b = (rating - skill) // BTH_PLUS_ADJ - (worn.to_h if worn is not None else 0)
    return plain_ammo_turn_damage(launcher, skill_thb=skill, to_h_b=to_h_b)
