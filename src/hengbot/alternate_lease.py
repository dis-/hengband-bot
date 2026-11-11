"""The over-extension switch is a lease: after its dives the original destination is tried again.

Owner 2026-11-11 (PLAN-50F C3, the answer 「5回で本来の行き先へ戻す」, verbatim):
「切り替え先に5回潜ったら、一度本来の行き先へ戻す。そこでまた厳しければ、次は10回、その次は20回と
切り替えの期間を延ばす。」  Before, a switch made because a depth was too hard
(``over_extended_dives``, ``no_depth_progress``) ended only with a new conquest, so all three
viewing characters stayed on the Orc cave 23F (alternate-dungeon.json, 2026-11-10).

And where the original destination is (C5, the answer 「一番深い帰還先」, verbatim):
「帰還先の中で一番深い所（今ならメインのダンジョンの70階）で稼ぐ。」  When the lease ends the target
is the deepest recall destination that passes every landing check (``_recall_destination_safe``:
the depth requirements, a guardian floor the kit cannot pass -- the floor above it is allowed
since C2 -- and P3's T1 guardian bottom floor), among the entered dungeons and Angband once its
recall is open, held as the target (reason ``deepest_destination``, no lease of its own) until
the next switch or conquest.  A conquest target whose landing may be taken keeps its priority.

- A switch from the original destination starts a lease of 5 dives, the next one after a lease
  ended 10, then 20 (doubling); a step down from one leased alternate to another keeps the
  lease and counts again from 0.  A new conquest forgets the lease (the switch ends anyway).
- Only finished normal dives of the alternate count (``dive_ended``).
- The lease and its dives are carried across restarts by ``alternate_dungeon_record``.
"""
from __future__ import annotations

from hengbot.dungeon_knowledge import exploration_destination_allowed
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_CHAMELEON_CAVE, DUNGEON_YEEK_CAVE

LEASED_REASONS = frozenset({"over_extended_dives", "no_depth_progress"})
FIRST_LEASE = 5
DEEPEST_REASON = "deepest_destination"


def _leased(policy) -> bool:
    return (policy._alternate_dungeon is not None
            and policy._alternate_dungeon_reason in LEASED_REASONS)


def switched(policy, previous_alternate, previous_reason) -> None:
    """The valve just set a leased alternate: its lease and a fresh dive count."""
    lease = getattr(policy, "_alternate_lease", 0) or 0
    if previous_alternate is not None and previous_reason in LEASED_REASONS:
        lease = lease or FIRST_LEASE       # a step down keeps the running lease
    else:
        lease = FIRST_LEASE if lease <= 0 else lease * 2
    policy._alternate_lease = lease
    policy._alternate_dives = 0


def dive_ended(policy, dungeon_id, normal_dive: bool) -> None:
    if normal_dive and _leased(policy) and dungeon_id == policy._alternate_dungeon:
        policy._alternate_dives = getattr(policy, "_alternate_dives", 0) + 1


def forget(policy) -> None:
    policy._alternate_lease = 0
    policy._alternate_dives = 0


def deepest_destination(policy, snapshot) -> int | None:
    """The deepest recall destination this character may land on now (C5)."""
    best, best_depth = None, -1
    candidates = list(snapshot.entered_dungeon_ids or ())
    if snapshot.angband_recall_unlocked and DUNGEON_ANGBAND not in candidates:
        candidates.append(DUNGEON_ANGBAND)
    for did in candidates:
        info = policy._dungeon_knowledge.get(did)
        if (info is None or not exploration_destination_allowed(did)
                or did in (DUNGEON_CHAMELEON_CAVE, DUNGEON_YEEK_CAVE)
                or (did == DUNGEON_ANGBAND and not snapshot.angband_recall_unlocked)
                or not policy._can_fight_in_dungeon(did)
                or (did in snapshot.conquered_dungeon_ids
                    and {"MAZE", "FORGET"}.issubset(info.flags))
                or not policy._recall_destination_safe(snapshot, did)):
            continue
        depth = policy._dungeon_entry_depth(snapshot, did, via_recall=True)
        if depth > best_depth or (depth == best_depth and did < best):
            best, best_depth = did, depth
    return best


def settle(policy, snapshot) -> bool:
    """On a town board: end a lease whose dives are done.  True when it ended."""
    if not snapshot.in_town or not _leased(policy):
        return False
    lease = getattr(policy, "_alternate_lease", 0) or FIRST_LEASE
    policy._alternate_lease = lease
    if getattr(policy, "_alternate_dives", 0) < lease:
        return False
    policy._alternate_dungeon = None
    policy._alternate_dungeon_reason = None
    policy._alternate_dives = 0
    policy._target_empty_dives = 0
    policy._guardian_bounce_dives = 0
    policy._no_depth_progress_dives = 0
    # A conquest target whose landing the character may take keeps its priority (its guardian
    # is beatable); one refused there (n1-b's Mountain 50F, P3's T1 guardian) does not.
    conquest = policy._conquest_target(snapshot)
    if conquest is not None and policy._recall_destination_safe(snapshot, conquest):
        return True
    deepest = deepest_destination(policy, snapshot)
    if deepest is None:
        return True
    policy._alternate_dungeon = deepest
    policy._alternate_dungeon_reason = DEEPEST_REASON
    policy._conquest_committed = None
    return True
