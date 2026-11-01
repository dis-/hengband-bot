"""The over-extended dive streak: the evidence the empty-dive valve switches on.

One judgement per finished normal dive (``policy_observation._observe``), read
by the valve in town (``EMPTY_DIVE_LIMIT`` dives in a row switch to a
shallower already-entered dungeon, ``_pick_alternate_dungeon``):

- a real haul (more than ``OVEREXTEND_LOOT_MAX`` pickups) clears the streak;
- else at least ``OVEREXTEND_EMERGENCY_MIN`` emergency escapes advance it;
- else a guardian bounce (the return this dive started on a guardian floor
  the kit cannot pass) advances it and the guardian-bounce count;
- else the streak holds: a lone quiet dive neither advances nor resets it.

Owner 2026-11-01 (#47 D57, memory d57-survival-answers-decision-20261101,
question 6): 「代わりのダンジョンも数える」 -- the emergency escapes of a dive of
the over-extension alternate count as they do for the main target.  While
Angband's recall is unlocked the main target is Angband and the alternate's
dives (the Labyrinth of n1-c life-084/085) were judged on the guardian
bounce alone, so repeated emergency escapes there never moved the character
shallower.

Owner 2026-11-01 (#47, answer 5 「緊急の逃げも数える」): a conquest target's
dives after Angband is unlocked count their emergency escapes too, so every
judged dive does.  The esp-threat return (``esp-threat:leave-recall``) is no
emergency escape (EMERGENCY_ESCAPE_REASONS) and stays uncounted (answer 6).
"""

from __future__ import annotations

from hengbot.policy_constants import OVEREXTEND_EMERGENCY_MIN, OVEREXTEND_LOOT_MAX


def judge_dive(policy, *, guardian_bounce: bool) -> None:
    """Advance, clear or hold ``_target_empty_dives`` for the dive that just ended."""
    if policy._dive_loot > OVEREXTEND_LOOT_MAX:
        policy._target_empty_dives = 0
        policy._guardian_bounce_dives = 0
    elif policy._dive_emergencies >= OVEREXTEND_EMERGENCY_MIN:
        policy._target_empty_dives += 1
    elif guardian_bounce:
        # Uncounted, a guardian we cannot yet beat flip-flops town<->guardian
        # forever, burning ~2 recall scrolls a round trip (live: Labyrinth,
        # recall 9 -> 0); the valve releases the conquest latch instead.
        policy._target_empty_dives += 1
        policy._guardian_bounce_dives = getattr(policy, "_guardian_bounce_dives", 0) + 1
