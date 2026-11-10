"""The light layer of the dungeon ladder (dungeon_ladder.LADDER, layer "light").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the floor avoidance,
above the opening and the approved quest floor.  The rungs are asked top-down and the first
key returned wins, as in ``_decide``; ``None`` hands the decision on to the layers below.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the
table still states this order and a reorder is a table diff.
"""
from __future__ import annotations

from hengbot import me_powers


def key(policy, snapshot) -> str | None:
    """The light layer's key, or None when none of its rungs acts."""
    # Player light radius >= 1 always gives CAVE_LITE to the player's own
    # square (cave-map.cpp update_lite); a non-blind player whose own square
    # is not lit therefore has radius zero. In darkness note_spot records
    # nothing (grid.cpp), so repair the light before combat/mining/navigation.
    darkness_recovery = policy._town_producer_entry("_darkness_recovery_key", lambda: policy._darkness_recovery_key(snapshot), family="survival")
    if darkness_recovery is not None:
        return darkness_recovery
    # Class 16 lights the dark with an absorbed power before walking it (me_powers).
    dark_power = me_powers.power_key(policy, snapshot, me_powers.DARK)
    if dark_power is not None:
        return dark_power
    dark_locomotion = policy._town_producer_entry("_dark_locomotion_key", lambda: policy._dark_locomotion_key(snapshot))
    if dark_locomotion is not None:
        return dark_locomotion
    # In town the light out comes before the class sequences' travels
    # (n1-b life-343: the staff sequence's inn travel into the dark street).
    town_light = policy._town_producer_entry("_town_light_restore_key", lambda: policy._town_light_restore_key(snapshot), family="survival")
    if town_light is not None:
        return town_light
    # Falls off with None: an explicit ``return None`` would read as an inline rung.
