"""A plan's Scroll of Light is read once per area: ``engagement_plan.light_areas``.

Owner 2026-07-18 (QUEST_2 opening): 「初手で光の巻物を読んで開始エリアを照らし、以後も新しい
エリアに進入するたび射撃の前に光の巻物で照明を確保する」; its rationale counts five firing
areas and one spare, six scrolls carried.

The areas are rows ``{"name", "bounds": [top, left, bottom, right]}``; the first row holding
the player's cell is the area.  Outside every area nothing is read.  n1-a lives 478-482
(2026-11-04/05) read all six within about 150 game turns of entering, standing in the start
room: the shot's light rung asks per target cell, a rat moves, and the board's cell flag says
unlit whatever was read.

A plan without areas keeps its callers' own attempt bookkeeping.
"""

from __future__ import annotations

PLAN_KEY = "light_areas"


def _area(areas, position) -> str | None:
    for row in areas:
        top, left, bottom, right = row["bounds"]
        if top <= position.y <= bottom and left <= position.x <= right:
            return row["name"]
    return None


def key(policy, snapshot, profile, reason: str) -> str | None:
    """The Light key when this area's reading is still due; sets ``last_reason``."""
    areas = profile.engagement_plan.get(PLAN_KEY)
    if areas is None:
        return policy._quest_light_key(snapshot, reason)
    area = _area(areas, snapshot.player.position)
    spent = (snapshot.floor_key, area)
    if area is None or spent in policy._quest_light_areas_read:
        return None
    light = policy._quest_light_key(snapshot, reason)
    if light is not None:
        policy._quest_light_areas_read.add(spent)
    return light
