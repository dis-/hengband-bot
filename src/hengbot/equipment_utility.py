"""Equipment value the combat simulation cannot see: telepathy and stealth.

Owner 2026-11-02: 「装備の比較方法は定義済のはずだが、改めて答えるとその中では
テレパシーを高く評価、隠密を多少評価する」.  The defined comparison (AGENTS.md
"maximize offense and defense"; user decision 2026-10-02 「生存÷撃破の比で比べる」)
ranks loadouts by the ratio survival / kill turns with a 1% equivalence band and
a 5% material-offense threshold.  Neither ESP nor stealth changes a simulated
fight, so they enter as a relative bonus on that ratio, sized against those two
existing thresholds:

- full telepathy (TR_TELEPATHY): +10%, twice the 5% "material" threshold, so it
  outweighs a small AC gain but not a large survival or offense difference;
- each limited ESP kind (TR_ESP_ANIMAL..TR_ESP_UNIQUE): +1% (one equivalence
  band), at most +5% together and nothing beside full telepathy, so full
  telepathy stays the highest;
- stealth (TR_STEALTH, per point of pval): +0.5%, so +2 stealth is one band:
  a tie-break between otherwise equal loadouts, not a trade against combat.

Other utility flags (see invisible, regeneration, slow digestion, warning,
auras) are deliberately not valued: the owner did not ask for them.

The *Destruction* means (``destruction_means_bonus``).  Owner 2026-11-15 (n1-a
life-525 died on ガラスの城 49F with twelve staves of *Destruction* in the Home and
the gear that made them reliable left there, since the staff was asked only from
50F), verbatim 「深さに関係なく持っていく」: at every depth a loadout whose device
skill makes an owned staff reliable (device_skill.StaffGate) earns
``DESTRUCTION_MEANS_BONUS``, the size of full telepathy (the highest utility the
owner named), so the swap's combat loss is weighed by this comparison and not
forced: a loss of more than about 10% keeps the stronger set.  The staff is a
survival means (it ends the engagement it is used on), so the bonus is on the
survival side: ``survival_turns`` and with it the ratio.  On the ratio alone the
selector's survival floor (equipment_optimizer SUFFICIENT_SURVIVAL_TURNS) dropped
the set before the ratio was read: at n1-a's fatal 21:05 departure the gloves and
the amulet (skill 64, 85%) kept 98.5% of the damage but 28.97 of 30.76 turns.
From 50F the staff is a requirement of the band (equipment_optimizer
``destruction_means``) and the bonus only ranks the sets that meet it.
"""

from __future__ import annotations

from typing import Iterable

TR_STEALTH = 8
TR_TELEPATHY = 79
# TR_ESP_ANIMAL (104) .. TR_ESP_UNIQUE (115), src/object-enchant/tr-types.h.
TR_ESP_KINDS = frozenset(range(104, 116))
UTILITY_FLAGS = frozenset({TR_STEALTH, TR_TELEPATHY}) | TR_ESP_KINDS

TELEPATHY_BONUS = 0.10
ESP_KIND_BONUS = 0.01
ESP_KINDS_BONUS_CAP = 0.05
STEALTH_POINT_BONUS = 0.005
DESTRUCTION_MEANS_BONUS = TELEPATHY_BONUS


def utility_value(items: Iterable, intrinsic_flags: frozenset[int]) -> float:
    """Relative margin bonus of worn ``OwnedEquipment`` ``items``.

    Telepathy counts once whether it is worn or intrinsic (every loadout of
    the character then carries the same bonus); stealth adds each item's
    pval, signed, as the game does (player-status/player-stealth.cpp, the
    TR_STEALTH pval of each worn item).
    """
    items = tuple(items)
    flags = set(intrinsic_flags)
    stealth = 0
    for item in items:
        flags.update(item.flags)
        if TR_STEALTH in item.flags:
            stealth += item.item.pval
    if TR_TELEPATHY in flags:
        esp = TELEPATHY_BONUS
    else:
        esp = min(ESP_KINDS_BONUS_CAP, ESP_KIND_BONUS * len(flags & TR_ESP_KINDS))
    return esp + STEALTH_POINT_BONUS * stealth


def destruction_means_bonus(loadout, staff_gate) -> float:
    """``DESTRUCTION_MEANS_BONUS`` when ``loadout``'s device skill makes the owned
    *Destruction* staff of ``staff_gate`` reliable, else 0."""
    return DESTRUCTION_MEANS_BONUS if staff_gate is not None and staff_gate.opens(loadout) else 0.0


def with_destruction_means(metrics, loadout, staff_gate):
    """``metrics`` with ``destruction_means_bonus`` on the survival side: a finite
    ``survival_turns`` and combat margin (survival / kill turns) scaled by it, and
    the utility (the tie-breaks) raised by it."""
    bonus = destruction_means_bonus(loadout, staff_gate)
    if not bonus:
        return metrics
    from dataclasses import replace
    from math import isfinite

    survival, margin = metrics.survival_turns, metrics.combat_margin
    if isfinite(survival):
        survival *= 1.0 + bonus
        if isfinite(margin):
            margin *= 1.0 + bonus
    return replace(metrics, survival_turns=survival, combat_margin=margin,
                   utility_value=metrics.utility_value + bonus)
