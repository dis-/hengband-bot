"""Gear that closes or narrows an unmet depth row is kept and worn (supervisor 2026-11-28).

n1-b life-419 (Magic-Eater CL50, permanent speed +17: ★進化する銃『クリムゾン』 +4, スピードの指輪 (+9),
★シヴァの化身の軟革ブーツ +4; the other ring ダメージの追加攻撃の指輪) was held at Angband 80F by the
81F row's speed +25 (angband_cap's speed ceiling).  From 2026-11-27 04:3x (turn 8958547) its Home
held a second スピードの指輪 (+9): wearing it in place of the extra-attack ring makes +26.  The
equipment search had not run since 2026-11-26 19:52 (every town decision answered
``calibration-required``), so nothing wore it, and on 11-27 18:57 the full-Home relief sold a third
ring, スピードの指輪 (+8) found at 80F (turn 12672802), to the magic shop for $30,000 as
``dominated`` (item_fate: the two +9 rings are at least as good).  The bot hunted on at 80F.

This module answers one question for the keep (item_need ``keep_reason``) and the descent
(destination_band_floor): which unmet row the character is held by, and whether a piece closes or
narrows it.  The rows are read, never derived again:

* the speed rows from the speed ceiling (angband_cap ``speed_ceiling``: the floor above the
  shallowest speed row the board does not meet, haste_sustain ``row_met``) and that row's
  permanent speed (policy_constants ``speed_gate``);
* the ability rows from the depth table's abilities the character lacks with its worn kit and its
  own permanent sources (ability_sources ``gap_sources``).

A piece narrows the speed row when its speed is above the smallest speed of the worn pieces in the
slots it may take (an empty slot is 0): worn there, the permanent speed rises.  A Ring of Speed is
kept whatever its pval while the row is unmet (owner 「スピードの指輪…生成階層は80Fである」: the
ring is why the character works the ceiling).  Once the row is met nothing here keeps a piece: the
existing rules decide (item_fate's dominance keeps the two best rings of a two-slot kind).
"""

from __future__ import annotations

from typing import Any

from hengbot.item_reservation import decision_memo

# object-enchant/tr-types.h TR_SPEED (warrior_defense_evaluator.TR_SPEED).
TR_SPEED = 12
# lib/edit/BaseitemDefinitions.jsonc id 136: the Ring of Speed, tval 45 (TV_RING) sval 31.
TVAL_RING = 45
SV_RING_SPEED = 31
# The worn slots a piece of each tval may take (equipment_optimizer slot_for, hand and ring rules).
_WEAPON_TVALS = frozenset({21, 22, 23})
_TVAL_SLOTS = {
    19: ("bow",), 30: ("feet",), 31: ("arms",), 32: ("head",), 33: ("head",), 34: ("sub_hand",),
    35: ("outer",), 36: ("body",), 37: ("body",), 38: ("body",), 39: ("light",), 40: ("neck",),
    TVAL_RING: ("main_ring", "sub_ring"),
}
# Reasons of item_need ``keep_reason`` (reasons are data, not prose).
KEEP_SPEED_RING = "depth-gap:speed-ring"
KEEP_SPEED_GEAR = "depth-gap:speed"
KEEP_ABILITY = "depth-gap:ability"


def speed_row(policy: Any, snapshot: Any) -> tuple[str, int] | None:
    """The unmet speed row the character is held by: (label, permanent speed it asks), or None.

    The shallowest unmet row, read from angband_cap's speed ceiling (the floor above it)."""
    if snapshot is None or getattr(snapshot, "player", None) is None:
        return None

    def compute():
        from hengbot import angband_cap
        from hengbot.policy_constants import speed_gate
        ceiling = angband_cap.speed_ceiling(policy, snapshot)
        return None if ceiling is None else speed_gate(ceiling + 1)

    return decision_memo(policy, "depth-gap-speed-row", snapshot, None, compute)


def gate_floor(policy: Any, snapshot: Any) -> int | None:
    """The first floor of the unmet speed row (the band the descent should reach), or None."""
    if speed_row(policy, snapshot) is None:
        return None
    from hengbot import angband_cap
    ceiling = angband_cap.speed_ceiling(policy, snapshot)
    return None if ceiling is None else ceiling + 1


def piece_speed(item: Any) -> int:
    """The speed a worn ``item`` gives (its pval when TR_SPEED is known, else 0)."""
    return item.pval if TR_SPEED in getattr(item, "known_flags", ()) else 0


def is_speed_ring(item: Any) -> bool:
    return item.tval == TVAL_RING and item.sval == SV_RING_SPEED


def _slots(item: Any) -> tuple[str, ...]:
    if item.tval in _WEAPON_TVALS:
        return ("main_hand", "sub_hand")
    return _TVAL_SLOTS.get(item.tval, ())


def narrows_speed(snapshot: Any, item: Any) -> bool:
    """Worn in one of its slots in place of the slowest piece there, ``item`` raises the speed."""
    speed = piece_speed(item)
    slots = _slots(item)
    if speed <= 0 or not slots:
        return False
    worn = {piece.slot: piece_speed(piece) for piece in snapshot.equipment}
    return speed > min(worn.get(slot, 0) for slot in slots)


def keep_reason(policy: Any, snapshot: Any, item: Any) -> str | None:
    """Why ``item`` closes or narrows an unmet depth row (never sold or destroyed), or None."""
    if snapshot is None or not getattr(item, "is_equipment", False) or getattr(item, "is_ammo", False):
        return None
    if not item.known or getattr(item, "is_cursed", False) or getattr(item, "is_broken", False):
        return None
    if speed_row(policy, snapshot) is not None:
        if is_speed_ring(item):
            return KEEP_SPEED_RING
        if narrows_speed(snapshot, item):
            return KEEP_SPEED_GEAR
    from hengbot import ability_sources
    if ability_sources.gap_source(policy, snapshot, item):
        return KEEP_ABILITY
    return None
