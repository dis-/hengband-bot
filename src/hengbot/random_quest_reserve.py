"""The teleport reserve that ends a runtime RANDOM (or covered fixed) quest floor.

#47 (n1-a life-451, 鉄獄38階 2026-10-31): on random quest 45 (『カルバノグの
殺人兎』, never seen) fourteen emergency teleports each latched the town return
(EMERGENCY_RETURN_COUNT), and the quest exit lock
(QuestPolicyMixin._quest_floor_exit_locked) cancelled every one of them; the
lock released only once the last scroll was read, and the character died
waiting for Recall with no escape left.

Owner decision 2026-11-01 「テレポートが残り少なくなったら帰る」「5本」: on a
runtime RANDOM quest floor, whether or not the target was seen or hurt, the
exit lock releases once the carried Scrolls of Teleportation fall below the
reserve, and the town return reads Recall.  Recall activates 15-35 player
turns after the read (spells-world.cpp recall_player: randint0(21) + 15), and
the remaining scrolls cover that wait.  Until then the 07-26 rule stands
(thirty or more teleports on such a floor are normal).

Fixed kill quests (KILL_LEVEL / KILL_NUMBER) share the same exit lock.
Owner 2026-11-01 (#47, answer 4 「014 だけ広げる」): the reserve covers the
fixed quests of RESERVE_FIXED_QUESTS too -- 014 Warg problem only; 008
Oberon and 009 Serpent of Chaos are decided again for the final stage and
keep their own releases.
"""

RANDOM_QUEST_TELEPORT_RESERVE = 5
RETURN_TRIGGER = "random-quest-teleport-reserve"
# Fixed quests the reserve also covers (lib/edit/quests/014_WargProblem.jsonc).
RESERVE_FIXED_QUESTS = frozenset({14})


def teleport_reserve_spent(policy, snapshot) -> bool:
    """This floor's covered kill quest has drawn teleports below the reserve."""
    if snapshot.in_town:
        return False
    quest_id = policy._active_kill_quest_id(snapshot)
    return (
        quest_id is not None
        and (quest_id in RESERVE_FIXED_QUESTS
             or policy._runtime_random_quest(snapshot, quest_id))
        and policy._count_teleport_scrolls(snapshot) < RANDOM_QUEST_TELEPORT_RESERVE
    )
