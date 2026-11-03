"""The one emergency Word of Recall read, and its hold on a one-time quest floor.

Owner 2026-11-03: 「回復の手段がある間は回復か休憩を選び、帰還は作戦の撤退の線以下か、
逃げ手段が尽きた時だけにします。」 Leaving an incomplete ONCE quest fails it for good
(src/dungeon/quest.cpp leave_quest_check).  n1-c life-116 (2026-11-03 11:40, Q31,
decision 4142) read recall on a walk at HP 174/354 with no enemy in view and 12
Teleport scrolls: the low-HP walk gate reads no teleport without a threat, and the
exit lock only covers the kill-count quest types, so nothing stood before the recall.

Every emergency recall site asks here.  The hold covers a quest whose approved
strategy allows an abort; the other fixed quests keep their reads (an owner question).
"""

from __future__ import annotations

from hengbot import breeder_quest
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT


def _deliberate_leave(policy, snapshot) -> bool:
    """A leave already decided on this floor, which the hold must not reverse."""
    return (
        policy._unviable_quest_floor == snapshot.floor_key
        or policy._starving_with_nothing_edible(snapshot)
        or policy._light_releases_quest_exit(snapshot)
        or breeder_quest.abandons_floor(policy, snapshot)
        or policy._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
    )


def held(policy, snapshot) -> bool:
    """Above the abort line, with an escape left, the ONCE quest floor keeps us."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    if quest_id is None or not policy._fixed_quest_is_once(quest_id):
        return False
    profile = policy.approved_quest_strategy(quest_id)
    abort_ratio = None if profile is None else policy._quest_abort_hp_ratio(profile)
    return (
        abort_ratio is not None
        and snapshot.player.hp_ratio > abort_ratio
        and policy._escape_scroll(snapshot) is not None
        and not _deliberate_leave(policy, snapshot)
    )


def read_key(policy, snapshot, reason: str = "emergency:recall") -> str | None:
    """Read Word of Recall as an escape, when this floor lets one be read."""
    if (
        snapshot.player.recalling
        or not policy._emergency_recall_leaves_danger(snapshot)
        or policy._quest_floor_exit_locked(snapshot)
        or held(policy, snapshot)
        or not policy._can_read_scrolls(snapshot)
    ):
        return None
    recall = policy._find_recall_scroll(snapshot)
    if recall is None:
        return None
    return policy._issue_emergency_consumable(snapshot, recall, reason)
