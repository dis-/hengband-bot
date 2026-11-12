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

Owner 2026-11-03, later: 「HP に関係なく、敵が見えず攻撃も受けていない間は帰還を読まず回復します。
敵がいて巻物も無い時は、今までどおり帰還を読みます。」; 「休んで治らない範疇ならどのみち助からない。
敵がいないなら毒切り傷でも休む。」  A poison or cut tick (player-damage.cpp:308 disturbs the
rest, hp-mp-processor.cpp:410-415 regenerates nothing until it ends) is no threat on a
quiet floor: the low-HP walk gate rests through it and spends no scroll.
"""

from __future__ import annotations

from hengbot import breeder_quest, quest_no_teleport
from hengbot.policy_constants import ONCE_QUEST_TICK_REST_REASON, REST_MACRO, STUCK_ESCAPE_LIMIT


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


def _quiet(policy, snapshot) -> bool:
    return not (_enemy_about(snapshot) or _hit_by_unseen(policy, snapshot))


def below_scroll_floor(policy, snapshot, profile) -> bool | None:
    """``abort_conditions.recall_below_teleports``: this count, not the HP line, decides
    the recall (Q25, owner 2026-11-04 「テレポートで立て直すだけ」, and below 5 scrolls
    Recall is read, the give-up point of a kill-all floor).  None: the plan names no count."""
    floor = profile.abort_conditions.get("recall_below_teleports")
    if floor is None:
        return None
    return policy._quest_named_item_count(snapshot, "required_scrolls", "teleport") < int(floor)


def below_entry_force(policy, snapshot) -> bool:
    """Maximum HP drained below the ``min_hp`` of the force row this quest floor was entered
    under (``QuestFloorNavigator.entry_force_min_hp``, recorded by the plan that keeps it):
    the strategy's line is crossed, as the HP ratio line is.

    n1-a life 515 (2026-11-12, Q18, warrior Lv33): accepted at max HP 716 on the row of 700;
    the seahorses' LOSE_CON bites drained it to 641 before the last fight and 485 at death,
    and nothing on the floor looked at it.
    """
    quest_id = policy._active_fixed_quest_id(snapshot)
    navigator = None if quest_id is None else policy._quest_navigators.get(quest_id)
    floor = getattr(navigator, "entry_force_min_hp", None)
    return (floor is not None and navigator.floor_key == snapshot.floor_key
            and snapshot.player.max_hp < int(floor))


def held(policy, snapshot) -> bool:
    """The ONCE quest floor keeps us: at any HP with no enemy about (the walk gate then
    drinks or rests), or above the strategy's HP line with an escape left."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    if quest_id is None or not policy._fixed_quest_is_once(quest_id):
        return False
    profile = policy.approved_quest_strategy(quest_id)
    hold_line = None if profile is None else profile.abort_conditions.get("hp_ratio")
    if hold_line is None or _deliberate_leave(policy, snapshot):
        return False
    if below_scroll_floor(policy, snapshot, profile) is not None:
        return _quiet(policy, snapshot) or not below_scroll_floor(policy, snapshot, profile)
    return _quiet(policy, snapshot) or (
        snapshot.player.hp_ratio > float(hold_line)
        and not below_entry_force(policy, snapshot)
        and (policy._escape_scroll(snapshot) is not None
             # No scroll is ever read here: the line alone decides (owner 2026-11-04
             # 「薬で戦い線より下で帰還」).
             or quest_no_teleport.forbids(policy, snapshot))
    )


def tick_is_no_threat(policy, snapshot) -> bool:
    """Poison or a cut on a held, quiet floor: its damage asks for no escape."""
    player = snapshot.player
    return (player.poisoned or player.cut) and _quiet(policy, snapshot) and held(policy, snapshot)


def _can_rest(snapshot) -> bool:
    player = snapshot.player
    return not player.confused and player.food_state in {"normal", "full", "gorged"}


def tick_rest_key(policy, snapshot) -> str | None:
    """Rest through the tick, under the reason the stop guards know as bounded by it."""
    if not (tick_is_no_threat(policy, snapshot) and _can_rest(snapshot)):
        return None
    policy.last_reason = ONCE_QUEST_TICK_REST_REASON
    return REST_MACRO


def tick_rest_before_navigator(policy, snapshot) -> str | None:
    """The low-HP rest with no potion to drink, before the navigator is asked.

    A step the walk gate turns into a rest stays in the Q2 phases' route memory as a
    blocked step: 15 rested ticks on one cell ended in quest:blocked and a WAIT, which
    no-wait read as a teleport.  With a potion the walk gate below still drinks.
    """
    if (
        not policy._low_hp_walk_gate_active(snapshot)[1]
        or policy._find_heal_potion(snapshot, expected_damage=1) is not None
    ):
        return None
    return tick_rest_key(policy, snapshot)


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
