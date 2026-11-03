"""The one emergency Word of Recall read, and its hold on a one-time quest floor.

Owner 2026-11-03: 「回復の手段がある間は回復か休憩を選び、帰還は作戦の撤退の線以下か、
逃げ手段が尽きた時だけにします。」 Leaving an incomplete ONCE quest fails it for good
(src/dungeon/quest.cpp leave_quest_check).  n1-c life-116 (2026-11-03 11:40, Q31,
decision 4142) read recall on a walk at HP 174/354 with no enemy in view and 12
Teleport scrolls: the low-HP walk gate reads no teleport without a threat, and the
exit lock only covers the kill-count quest types, so nothing stood before the recall.

Owner 2026-11-03, for Q1, Q2 and Q34: 「HP が 30% より上で、テレポートなどの逃げの巻物が
残っている間は緊急の帰還を読みません。30% 以下か巻物が無ければ今までどおり読みます。階段での
撤退は今までどおりしません。」

Every emergency recall site asks here.  The hold covers every approved strategy and
uses its own ``abort_conditions.hp_ratio``.  ``allowed`` says whether the strategy may
withdraw by the stairs or the exit (policy_quest ``quest-strategy:abort``); it does not
gate this hold.  A quest without an approved strategy keeps its reads.

Owner 2026-11-03, every fixed ONCE quest with a line: 「敵が見えず、攻撃も受けていない間は
帰還を読まず、薬か休憩で回復します。敵が現れたら線より下の時の今の判断に戻ります。見えない敵に
殴られている時は敵がいるものとして扱います。」  ``quest-strategy:abort`` yields to the same hold.
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


def _enemy_about(snapshot) -> bool:
    return any(
        monster.hostile for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))


def _hit_by_unseen(policy, snapshot) -> bool:
    """The unseen-attacker evidence of the observation (the retreat's own), and the
    silent hits the lethal rung counts as one; a hit is as good as an enemy in view."""
    return (
        policy._unseen_attack_evidence is not None
        or policy._unseen_hit_pending_floor == snapshot.floor_key
        or policy._unexplained_damage_streak >= 2
    )


def held(policy, snapshot) -> bool:
    """The ONCE quest floor keeps us: above the strategy's HP line with an escape
    left, or below it with no enemy about (the walk gate then drinks or rests)."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    if quest_id is None or not policy._fixed_quest_is_once(quest_id):
        return False
    profile = policy.approved_quest_strategy(quest_id)
    hold_line = None if profile is None else profile.abort_conditions.get("hp_ratio")
    if hold_line is None or _deliberate_leave(policy, snapshot):
        return False
    if snapshot.player.hp_ratio > float(hold_line):
        return policy._escape_scroll(snapshot) is not None
    return not (_enemy_about(snapshot) or _hit_by_unseen(policy, snapshot))


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
