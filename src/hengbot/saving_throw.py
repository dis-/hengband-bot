"""The saving throw of a loadout: the board's value with the worn gear's terms swapped.

The loadout evaluator scored every candidate with the board's saving throw
(``player.saving_skill``), so a set without the worn ★運命のオーブ (r呪) kept
its +30 (n1-b life-411, 2026-11-20: the ★飛行石 set was scored at 119
instead of 89).  calc_saving_throw (src/player/player-status.cpp) sums

- the race, class and personality bases and their level terms,
- +15 + level/5 for the MAGIC_RES mutation, +6 + (level-1)/10 for bless_blade,
- +30 with resist curse (``has_resist_curse``: TR_RES_CURSE on a worn item or
  from the race / class / personality),
- ``adj_wis_sav`` of the WIS index (src/player/player-status-table.cpp),
- -10 with vulnerability to curse (``has_vuln_curse``: TR_VUL_CURSE on a worn
  item), -20 more when that item is heavily cursed, -30 while berserk,
- then raises it to 90 + level with anti-magic (TR_NO_MAGIC worn) and to
  95 + level with the ultimate resistance / resist-magic / magicdef effects,
  sets 10 while crushed and halves it under the down-saving curse.

The gear terms here are resist curse, vulnerability to curse, the WIS index
and the anti-magic floor; everything else is the same for every loadout and
stays in the board's value.  The base is the board's value without the worn
loadout's gear terms (``saving_base``); a candidate adds its own.  The heavy
curse is not visible on the board (a cursed item is no candidate), and a board
whose value is overridden (anti-magic worn, a timed effect) gives no base:
the board's value is then used for every loadout, as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hengbot.warrior_equipment_evaluator import modify_stat_value, stat_index

if TYPE_CHECKING:
    from hengbot.equipment_optimizer import Loadout

TR_WIS = 2
TR_NO_MAGIC = 69
TR_RES_CURSE = 148
TR_VUL_CURSE = 162

RESIST_CURSE_BONUS = 30
VULNERABLE_CURSE_PENALTY = 10

# adj_wis_sav (src/player/player-status-table.cpp), indexed by stat_index.
ADJ_WIS_SAV = (
    0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2,
    2, 2, 3, 3, 3, 3, 3, 4,
    4, 5, 5, 6, 7, 8, 9,
    10, 11, 12, 13, 14, 15,
    16, 17, 18, 19,
)


def _pval_total(loadout: "Loadout", flag: int) -> int:
    return sum(item.item.pval for _, item in loadout.slots if flag in item.flags)


def gear_terms(
    loadout: "Loadout", *, natural_wis: int, intrinsic_wis: int,
    intrinsic_flags: frozenset[int],
) -> int:
    """The saving-throw terms of calc_saving_throw that ``loadout`` changes."""
    flags = loadout.flags | intrinsic_flags
    wisdom = modify_stat_value(natural_wis, intrinsic_wis + _pval_total(loadout, TR_WIS))
    terms = ADJ_WIS_SAV[stat_index(wisdom)]
    if TR_RES_CURSE in flags:
        terms += RESIST_CURSE_BONUS
    if TR_VUL_CURSE in flags:
        terms -= VULNERABLE_CURSE_PENALTY
    return terms


def saving_base(
    board_saving: int, worn: "Loadout", *, level: int, natural_wis: int,
    intrinsic_wis: int, intrinsic_flags: frozenset[int],
) -> int | None:
    """The board's saving throw without the worn loadout's gear terms.

    None when the board's value is the anti-magic floor (the sum is not
    readable back), so the board's value stands for every loadout."""
    if TR_NO_MAGIC in worn.flags and board_saving <= 90 + level:
        return None
    return board_saving - gear_terms(
        worn, natural_wis=natural_wis, intrinsic_wis=intrinsic_wis,
        intrinsic_flags=intrinsic_flags)


def loadout_saving(
    base: int, loadout: "Loadout", *, level: int, natural_wis: int,
    intrinsic_wis: int, intrinsic_flags: frozenset[int],
) -> int:
    """``base`` with ``loadout``'s gear terms and its anti-magic floor."""
    value = base + gear_terms(
        loadout, natural_wis=natural_wis, intrinsic_wis=intrinsic_wis,
        intrinsic_flags=intrinsic_flags)
    if TR_NO_MAGIC in loadout.flags:
        value = max(value, 90 + level)
    return value
