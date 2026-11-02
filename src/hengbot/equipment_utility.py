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
