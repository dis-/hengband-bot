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

The town agrees with that floor (n1-b life-306, 2026-11-03): the ordinary
shallow departure asks for four scrolls, so a character with four kept reading
Recall to 014's floor (Yeek cave 5F), where the reserve sent it straight back:
72 rounds of two scrolls each until the shop ran out of Recall.  A departure
heading for a covered quest's dungeon therefore asks for the reserve too
(``departure_requirement``, read by the supply ledger).
"""

RANDOM_QUEST_TELEPORT_RESERVE = 5
RETURN_TRIGGER = "random-quest-teleport-reserve"
# Fixed quests the reserve also covers (lib/edit/quests/014_WargProblem.jsonc).
RESERVE_FIXED_QUESTS = frozenset({14})


def _covered(policy, snapshot, quest_id: int) -> bool:
    return (quest_id in RESERVE_FIXED_QUESTS
            or policy._runtime_random_quest(snapshot, quest_id))


def teleport_reserve_spent(policy, snapshot) -> bool:
    """This floor's covered kill quest has drawn teleports below the reserve."""
    if snapshot.in_town:
        return False
    quest_id = policy._active_kill_quest_id(snapshot)
    return (
        quest_id is not None
        and _covered(policy, snapshot, quest_id)
        and policy._count_teleport_scrolls(snapshot) < RANDOM_QUEST_TELEPORT_RESERVE
    )


def departure_requirement(policy, snapshot) -> int:
    """The scrolls a town departure needs so ``teleport_reserve_spent`` stays false.

    Income runs stay on the mining floors and keep their own requirements.
    Every floor of the quest's dungeon counts, not only the recall landing: the
    stairs (or the walk-in above a taken quest) reach the quest floor as well.
    """
    if (not snapshot.in_town or snapshot.player.recalling
            or policy._fundraising_mode is not None):
        return 0
    _destination, dungeon_id = policy._town_recall_destination(
        snapshot, guardian_gate=False, safety_gate=False)
    covered = any(
        quest_dungeon == dungeon_id and _covered(policy, snapshot, quest.id)
        for quest, quest_dungeon, _level in policy._incomplete_kill_quests(snapshot)
    )
    return RANDOM_QUEST_TELEPORT_RESERVE if covered else 0
