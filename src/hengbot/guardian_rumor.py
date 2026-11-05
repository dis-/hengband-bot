"""Open another dungeon through the inn rumors for a bounced character before Q2.

Owner 2026-11-05: 「噂で別のダンジョンを開く」.  A character the guardian bounced,
with no other entered dungeon to go to, used to go to Angband (owner 2026-10-27),
but Angband stays shut until Q2 is resolved (random_quest_hold.entry_refused).  So
it reads rumors until a dungeon it can use opens, then goes there.

What a rumor does (src/cmd-building/cmd-inn.cpp, src/rumor/rumor-list.cpp,
src/store/rumor.cpp): the inn's 10 gold rumor is MEDIUM rarity.  One read in four
is a dungeon rumor, chosen evenly among the dungeons entered at 30F or shallower,
and it sets that dungeon's max level to its entry floor, which lists it in
``entered_dungeon_ids``.  The player cannot choose the dungeon.

The rumor reads, the funds wait and the mining set are the existing inn rumor
owner in TownMixin; this module only says when that owner works for a dungeon and
when the work is over.  A dungeon counts as usable by the same answers as
``_pick_alternate_dungeon``, so whatever this waits for is what that pick takes.
"""

from __future__ import annotations

from hengbot import random_quest_hold
from hengbot.model import DUNGEON_ANGBAND

# rumor-list.cpp DEPTH_THRESHOLD: deeper entries are only in the HIGH rarity table,
# which the inn's 10 gold rumor never reads.
RUMOR_MAX_ENTRY_DEPTH = 30
# Display only (spectator): why the target moved.
TARGET_REASON = "guardian_rumor_opened"


def pending(policy) -> bool:
    """Whether the inn rumor owner is reading for a dungeon to go to."""
    return getattr(policy, "_guardian_rumor_bounced", None) is not None


def _openable(policy, snapshot) -> tuple[int, ...]:
    """The dungeons not opened yet that a rumor can open and the pick would take."""
    return tuple(
        info.id for info in policy._dungeon_knowledge.values()
        if 0 < info.min_depth <= RUMOR_MAX_ENTRY_DEPTH
        and info.id not in snapshot.entered_dungeon_ids
        and policy._fallback_destination_allowed(info.id)
        and policy._fallback_landing_allowed(snapshot, info.id, info.min_depth))


def _can_open(policy, snapshot) -> bool:
    return (random_quest_hold.entry_refused(snapshot, DUNGEON_ANGBAND)
            and bool(_openable(policy, snapshot)))


def arm(policy, snapshot, bounced: int) -> bool:
    """Take a bounce with no alternate; False leaves the visible stop to the caller."""
    if not _can_open(policy, snapshot):
        return False
    policy._guardian_rumor_bounced = bounced
    return True


def release(policy) -> None:
    policy._guardian_rumor_bounced = None


def settle(policy, snapshot) -> None:
    """On a town board: go to what opened, or end the work when it has no point."""
    bounced = getattr(policy, "_guardian_rumor_bounced", None)
    if bounced is None or not snapshot.in_town:
        return
    alternate = policy._pick_alternate_dungeon(snapshot, guardian_bounced_dungeon=bounced)
    if alternate is not None:
        policy._alternate_dungeon = alternate
        policy._alternate_dungeon_reason = TARGET_REASON
        policy._conquest_committed = None
        release(policy)
    elif (not _can_open(policy, snapshot)
          or not policy._guardian_floor_blocked(
              snapshot, bounced, snapshot.dungeon_recall_depths.get(bounced, 0))):
        release(policy)
