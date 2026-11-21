"""The town's loadout search knows the destination: its band is the depth-band descent's floor.

Owner 2026-11-21 (verbatim): 「唯一のカオス耐性を自宅に仕舞い込んで勝手に持っていない判定にした経緯を
解析」.  n1-c life-218 (Lv34 Magic-Eater, recall landings the Mountain 49, Angband 48, the
Castle 48): a ★Pike 『ティル=イ=アルク』 found at 20:43 raised the unconstrained best melee to
238 per game time, so the depth-band descent (owner 2026-08-10, the half-melee limit 「打撃性能が
極端に下がる場合は一つ帯を下げて試行させたい」) refused band 49, whose only resist_chaos sets
wield the (混沌)ヘヴィ・フレイル (melee 92, ratio 0.39), and adopted band 30.  The transaction
put the flail in Home.  The town's departure then refused the Mountain's 49 for the missing
resist_chaos (the depth gate read the worn abilities), and the no-safe-destination fundraising
mined the Yeek cave -- for an ability the Home already held.

The first fix (2026-11-21) engaged a floor only when that fundraising was about to open (one
scene, a third state).  Equipment review 2026-11-22 (maintainability-review-equip-1122, stage
E4) folds it into the rule, owner Q4 (verbatim choice): 「深さの条件を満たす組があれば打撃が半分を
下回っても着て行く。打撃の半分の決まりは条件を満たす組が複数ある時の選び方だけ」.  Every town search
without a fixed depth (``policy_equipment._prepare_equipment_optimization``) passes the band of
the planned departure's landing (``_equipment_departure_destination_depth``) as
``optimize_loadout``'s ``destination_floor``: the descent still tries the deeper bands first
with the half-melee limit, takes the destination's band whenever one of its sets is owned (the
limit then only chooses among its sets: those keeping half of the best melee when there are
any), and reaches a shallower band only when the destination's band has no set.  The visit's
target therefore wears (withdrawing from Home) the set the destination needs, and the town's
destination gates count it (ability_sources ``OWNED``, owner Q3).

Outside the town (a pickup in the dungeon) and for a search at a fixed depth there is no floor.
A change of the destination's band within a visit decides the target again (equipment_target
``destination-band-floor``).
"""

from __future__ import annotations

from hengbot.equipment_optimizer import DEPTH_BANDS


def band_of(depth: int) -> int:
    """The descent band holding ``depth`` (the shallowest band label at or below it)."""
    return min((band for band in DEPTH_BANDS if band >= depth), default=DEPTH_BANDS[0])


def floor(policy, snapshot) -> int | None:
    """The band of the planned departure's landing, in town; None elsewhere."""
    if snapshot is None or not getattr(snapshot, "in_town", False):
        return None
    return band_of(max(1, policy._equipment_departure_destination_depth(snapshot)))
