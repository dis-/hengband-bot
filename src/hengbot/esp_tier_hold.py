"""The rest slot's ESP tier keeps the side decided first between WEAK and MEDIUM.

``policy_combat._esp_threat_assess`` tiers the awake hostiles known only by telepathy or
detection from one player turn of their damage at contact, the melee capped by the K slots
around the player's own cell.  WEAK hunts them (a step toward the nearest, ``esp-threat:
hunt-weak``), MEDIUM keeps exploring.  The slots are those of the cell the player stands on, so
a hunt step can walk into a cell where the same group reads MEDIUM.

Recorded n1-b life-362 (Orc cave 23F, 2026-11-10 09:32:31 and again 09:32:50 after the restart,
loop-detected): 27 ogres and black ogres sensed south of the corridor (34,51)-(34,56).  At
(34,53) two cells were open beside the player, strength 36 of HP 450 (ratio 0.08 < 0.10, WEAK):
the hunt stepped '4' to (34,52).  There three were open, strength 47 (0.104, MEDIUM): no hunt,
and the committed exploration toward its frontier (16,60) stepped '6' straight back, until the
loop guard stopped the bot.

Owner 2026-11-08 「境に余裕を持たせる」 (threat_tier_memory: once a monster's tier is decided,
small changes do not flip it; fight or leave stays on the side decided first) holds here too:
once a reading decides WEAK or MEDIUM on a floor, a later WEAK or MEDIUM reading of the same
group, or of part of it, keeps that tier.  STRONG is never held and is always taken as read
(its hunt has the feasibility estimate and the leave path); a monster new to the group, a new
floor or a STRONG reading decides again.  No new number.
"""

from __future__ import annotations

HOLD = "_esp_tier_hold"
HELD_TIERS = frozenset({"weak", "medium"})


def held(policy, snapshot, tier: str, tiered) -> str:
    """The tier the rest slot acts on for the reading ``tier`` of ``tiered``."""
    group = frozenset((monster.index, monster.race_id) for monster in tiered)
    memory = policy.__dict__.get(HOLD)
    if (tier in HELD_TIERS and memory is not None and memory[0] == snapshot.floor_key
            and memory[1] in HELD_TIERS and group <= memory[2]):
        return memory[1]
    setattr(policy, HOLD, (snapshot.floor_key, tier, group))
    return tier
