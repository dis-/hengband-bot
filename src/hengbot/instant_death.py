"""Threat tiers: 3.1 即死, the one-player-action test (design 3.1, answer 2).

Split out of ``threat_tiers`` (maintainability review 2026-11-09, step 4): ``InstantDeath`` and
``instant_death``, the part of ``assess`` that is never past the cost cap.  The plans' 即死 rung
(``instant_death_key``) stays in ``threat_tiers``, which re-exports every name here.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import paralyzer_contact, return_yield
from hengbot.threat_projection import _with_adjusted_speed, engagement, unseen_correction


@dataclass(frozen=True)
class InstantDeath:
    """3.1 即死 on one board: why it holds, and the next-action damage it read."""
    reasons: tuple = ()
    next_action_p95: int = 0
    unseen_correction: int = 0

    @property
    def holds(self) -> bool:
        return bool(self.reasons)

    @property
    def next_action(self) -> bool:
        """The 1-turn p95 test (answer 2 「次の1手の95%で判定」), the one the ladders act on."""
        return NEXT_ACTION_P95 in self.reasons


NEXT_ACTION_P95 = "next-action-p95"


def _instant_death(policy, snapshot, hostiles, melee_slots=None,
                   contact=False) -> tuple[InstantDeath, dict]:
    """3.1 on hostiles already at their adjusted speed; also the 1-turn prediction it read."""
    player = snapshot.player
    hp = player.hp
    one_turn = policy.threat_prediction(snapshot, hostiles, 1, melee_slots=melee_slots,
                                        contact=contact)
    next_action_p95 = one_turn["operational_total"]
    correction = unseen_correction(policy, snapshot, hostiles)
    reasons = []
    if next_action_p95 + correction >= hp:
        reasons.append(NEXT_ACTION_P95)
    if any(not monster.asleep and paralyzer_contact.in_contact(policy, snapshot, monster)
           for monster in policy._paralyzing_monsters(snapshot, hostiles)):
        reasons.append("paralyzer-contact")
    if (player.hallucinated and hp < policy._low_hp_walk_threshold(player.max_hp)
            and return_yield.awake_hostile_in_view(policy, snapshot)):
        reasons.append("hallucination")
    return InstantDeath(tuple(reasons), next_action_p95, correction), one_turn


def instant_death(policy, snapshot, hostiles=None) -> InstantDeath:
    """3.1 alone, the part of ``assess`` that is never past the cost cap (one action ahead)."""
    if hostiles is None:
        hostiles = engagement(policy, snapshot)
    hostiles = [_with_adjusted_speed(monster) for monster in hostiles]
    if not hostiles:
        return InstantDeath()
    return _instant_death(policy, snapshot, hostiles)[0]
