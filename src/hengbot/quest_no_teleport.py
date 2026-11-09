"""A quest floor whose strategy forbids reading any relocation scroll.

Owner 2026-11-04, Q18: 「テレポート禁止エリアが設定されているため、テレポートすると必ず
中央に飛ばされる。叫びとテレポートバックを受け、非常に危険な戦闘になるため絶対に回避するべきで
ある。」

``engagement_plan.no_teleport: true`` on a quest strategy is the data; ``forbids`` is
the one reading of it.  The finders every rung reads a relocation scroll through
(``_find_teleport_scroll``, ``_find_phase_scroll``, hence ``_escape_scroll``) and the
few rungs that pick a scroll themselves answer None on such a floor, so an emergency,
flee, status-threat, no-wait, enclosure, breeder or stuck rung falls to its next answer.

Game (C:/hengband/src): Teleportation and Phase Door are both ``teleport_player``
and land only where ``cave_player_teleportable_bold`` allows (spells-teleport.cpp:305,
339), which refuses a NO_TELEPORT_DEST cell (grid.cpp:952), so Phase Door has no safer
landing than Teleportation and is forbidden with it.  Teleport Level does nothing on a
fixed quest floor, so it would only spend a turn.  A monster sent away by Teleport
Away does not move the player and ``teleport_away`` skips that check inside a quest
(spells-teleport.cpp:143): it is outside this rule.
"""

from __future__ import annotations


def forbids(policy, snapshot) -> bool:
    """This floor's approved strategy forbids reading a relocation scroll."""
    profile = policy.approved_quest_strategy(snapshot.floor_key[2])
    return profile is not None and profile.engagement_plan.get("no_teleport") is True


# Owner 2026-11-09 (n1-c life-178, Q3): 「成功率が80%以上なら体力回復は使っても良い。テレポートは
# 許可しない」 -- inside Quest 25 the absorbed Teleportation is not cast (the scrolls stay the plan's).
NO_ABSORBED_TELEPORT_QUESTS = frozenset({25})


def forbids_absorbed(policy, snapshot) -> bool:
    """This floor forbids casting the absorbed Teleportation (its scrolls' rule, or the owner's)."""
    return (forbids(policy, snapshot)
            or policy._active_fixed_quest_id(snapshot) in NO_ABSORBED_TELEPORT_QUESTS)
