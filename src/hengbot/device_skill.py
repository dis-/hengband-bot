"""The magic device skill a loadout gives, and the *Destruction* staff it makes reliable.

Owner 2026-11-15 (n1-a life-525, a Lv37 warrior at device skill 31 with eleven
staves of *Destruction* in the Home and the 50F gate unmet), verbatim:
「装備で魔法道具使用能力を向上させて杖の成功率を上げることで先に進むことができる」.
The 50F+ gate (owner 2026-11-04, destruction_use.holds_means) asks a staff or an
absorbed power at RELIABLE_MIN_SUCCESS; this module tells which loadout reaches it.

Game (C:/hengband/src):
 * player/player-status.cpp calc_device_ability: race + class + personality, the
   class's and personality's level terms, ``8 * pval`` for every worn item
   (INVEN_WIELDING_SLOTS: main hand to feet) with TR_MAGIC_MASTERY, then
   adj_int_dev[stat_index[A_INT]], and -20 while berserk.  Only the worn
   items' MAGIC_MASTERY and INT move with the loadout.
 * object-use/use-execution.cpp: the staff's chance is skill - item level
   (attack_expectation.device_use_success; the Staff of *Destruction* is level
   50, BaseitemDefinitions.jsonc id 307).

``StaffGate.base`` is the board's skill without the worn loadout's part, so the
worn loadout's skill is the board's own number and any other loadout's differs
by its MAGIC_MASTERY and INT only.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from hengbot.warrior_equipment_evaluator import modify_stat_value, stat_index

TR_INT = 1
TR_MAGIC_MASTERY = 6
INT = 1
# player/player-status-table.cpp adj_int_dev, indexed by stat_index.
ADJ_INT_DEV = (
    0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2,
    2, 2, 3, 3, 4, 4, 5, 5,
    6, 6, 7, 7, 8, 9, 10,
    11, 12, 13, 14, 15, 16,
    17, 18, 19, 20,
)


def item_mastery(owned) -> int:
    """calc_device_ability's ``8 * pval`` of one worn item with TR_MAGIC_MASTERY."""
    return 8 * owned.item.pval if TR_MAGIC_MASTERY in owned.flags else 0


def _pval_total(loadout, flag: int) -> int:
    return sum(item.item.pval for _, item in loadout.slots if flag in item.flags)


TVAL_RING = 45
WEAPON_TVALS = frozenset({21, 22, 23, 34})  # the two hands: weapons and the shield


def mastery_bound(rows) -> int:
    """The most MAGIC_MASTERY skill ``rows`` ((tval, item_mastery) of wearable items)
    can give together: the best per body slot, the two best rings and the two best
    for the hands.  An upper bound: the requirements of the loadout are not asked."""
    from hengbot.equipment_optimizer import slot_for  # import cycle

    groups: dict[object, list[int]] = {}
    for tval, mastery in rows:
        if mastery <= 0:
            continue
        if tval == TVAL_RING:
            group, size = "rings", 2
        elif tval in WEAPON_TVALS:
            group, size = "hands", 2
        else:
            group, size = slot_for(SimpleNamespace(tval=tval)), 1
            if group is None:
                continue
        groups.setdefault((group, size), []).append(mastery)
    return sum(sum(sorted(values, reverse=True)[:size]) for (_group, size), values in groups.items())


def reliable_staff_skill(level: int, threshold: float) -> int:
    """The least device skill whose staff success at ``level`` is ``threshold``%+."""
    from hengbot.attack_expectation import device_use_success  # import cycle

    skill = 0
    while device_use_success(skill, level) * 100 < threshold:
        skill += 1
    return skill


@dataclass(frozen=True)
class StaffGate:
    """An owned charged staff that turns reliable at ``need`` device skill."""

    need: int
    base: int
    natural_int: int
    intrinsic_int: int

    def _int_adjustment(self, loadout) -> int:
        intelligence = modify_stat_value(
            self.natural_int, self.intrinsic_int + _pval_total(loadout, TR_INT))
        return ADJ_INT_DEV[min(stat_index(intelligence), len(ADJ_INT_DEV) - 1)]

    def skill(self, loadout) -> int:
        """calc_device_ability with ``loadout`` worn."""
        return (self.base + sum(item_mastery(item) for _, item in loadout.slots)
                + self._int_adjustment(loadout))

    def opens(self, loadout) -> bool:
        return self.skill(loadout) >= self.need

    def key(self) -> tuple[int, int, int, int]:
        return (self.need, self.base, self.natural_int, self.intrinsic_int)


def staff_gate(player, worn, natural_int: int, intrinsic_int: int, need: int) -> StaffGate:
    """The gate of ``need`` for the board's ``player`` wearing ``worn`` (a Loadout)."""
    gate = StaffGate(need, 0, natural_int, intrinsic_int)
    return StaffGate(need, player.device_skill - gate.skill(worn), natural_int, intrinsic_int)
