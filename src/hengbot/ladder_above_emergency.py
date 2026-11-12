"""The above-emergency layer of the dungeon ladder (dungeon_ladder.LADDER, layer "above-emergency").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the floor plans
(plan-above-survival), above the emergency ladder (ladder_emergency).  Its one rung is the
committed STRONG-tier hunt, which drinks by its own estimate (owner 2026-09-22; whether it
stays here is the review's open question, dungeon_ladder._ABOVE_EMERGENCY).  ``PASS`` hands the
decision on to the layers below.  scripts/dungeon_ladder_lint.py reads the rows here
(dungeon_ladder.LAYER_MODULES), so the table still states this order.
"""
from __future__ import annotations

from hengbot.dungeon_ladder import PASS


def key(policy, snapshot, *, strategic_hostiles):
    """The above-emergency layer's answer, or PASS when none of its rungs acts."""
    # A committed STRONG-tier hunt (esp-threat-rest) owns its fight,
    # including Healing drinks, ahead of the emergency/flee ladder.
    esp_threat_hunt = policy._town_producer_entry("_esp_threat_hunt_key", lambda: policy._esp_threat_hunt_key(
        snapshot, strategic_hostiles
    ))
    if esp_threat_hunt is not None:
        return esp_threat_hunt
    return PASS
