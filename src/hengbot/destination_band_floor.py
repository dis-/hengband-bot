"""Wear the owned set the destination's depth gate needs before fundraising for it.

Owner 2026-11-21 (verbatim): 「唯一のカオス耐性を自宅に仕舞い込んで勝手に持っていない判定にした経緯を
解析」.  n1-c life-218 (Lv34 Magic-Eater, recall landings the Mountain 49, Angband 48, the
Castle 48): a ★Pike 『ティル=イ=アルク』 found at 20:43 raised the unconstrained best melee to
238 per game time, so the depth-band descent (owner 2026-08-10, the half-melee limit 「打撃性能が
極端に下がる場合は一つ帯を下げて試行させたい」) refused band 49, whose only resist_chaos sets
wield the (混沌)ヘヴィ・フレイル (melee 92, ratio 0.39), and adopted band 30.  The transaction
put the flail in Home.  The town's departure then refused the Mountain's 49 for the missing
resist_chaos (the depth gate reads the worn abilities), the unsafe-recall fallback found no
entered landing in 29..30 (the fallback depth floor, 49 - 20), and the no-safe-destination
fundraising mined the Yeek cave -- for an ability the Home already held, and with no band-30
landing to reach, every mining run ended at the same refusal.

The band one step lower is worth trying only where it can be gone to.  When the departure is
about to open that fundraising and the last descent refused the destination's band by the
half-melee limit alone (a set of it is owned, the catalogue includes Home), the destination's
depth becomes the descent's floor (``optimize_loadout``'s ``destination_floor``): that band is
taken without the limit, the transaction withdraws and wears its set, and the departure's depth
gate passes.  A deeper band keeps the limit, and nothing else of the descent changes.

The floor holds for the (dungeon, depth) it was engaged for while that dungeon stays the target;
a target switch leaves it unread, and engaging another one replaces it.
"""

from __future__ import annotations

from hengbot import equipment_target
from hengbot.equipment_optimizer import DEPTH_BANDS

STATE = "_destination_band_floor"


def band_of(depth: int) -> int:
    """The descent band holding ``depth`` (the shallowest band label at or below it)."""
    return min((band for band in DEPTH_BANDS if band >= depth), default=DEPTH_BANDS[0])


def floor(policy) -> int | None:
    """The engaged floor depth while its dungeon is the target, else None."""
    held = getattr(policy, STATE, None)
    if held is None:
        return None
    dungeon_id, depth = held
    return depth if getattr(policy, "_target_dungeon_id", None) == dungeon_id else None


def _melee_refused(policy, depth: int) -> bool:
    """Whether the last descent refused ``depth``'s band by the half-melee limit alone."""
    result = equipment_target.loadout_target_result(policy)
    target = band_of(depth)
    return any(
        decision.band == target
        and decision.satisfying_set_existed
        and decision.refusal_reason == "melee-ratio"
        for decision in getattr(result, "band_decisions", ()) or ()
    )


def engage(policy, snapshot, destination_depth: int) -> bool:
    """Make ``destination_depth`` the descent's floor when an owned set meets its band.

    True when the floor was engaged now and the optimizer re-searched with it; False when it was
    already engaged (its set is then worn or cannot be: the existing refusal stands) or no owned
    set meets the band.
    """
    held = (policy._target_dungeon_id, destination_depth)
    if getattr(policy, STATE, None) == held or not _melee_refused(policy, destination_depth):
        return False
    setattr(policy, STATE, held)
    equipment_target.invalidate_loadout_search(policy)
    policy._prepare_equipment_optimization(snapshot)
    return True
