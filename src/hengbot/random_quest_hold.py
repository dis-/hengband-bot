"""Hold the dive above the runtime RANDOM quest floors until Q2 is resolved.

Owner 2026-11-02: 「angband 6F, 12Fのランダムクエストに挑む順が早いので達成率が
低い。Q2の後に回したい」.  While the gating fixed quest (Q2, 下水道) is still
open, no voluntary descent or recall landing may cross into a dungeon floor
that holds a pending RANDOM quest: the dive stops one floor above the
shallowest one (Angband deepest allowed = first random quest level - 1).
After Q2 the hold lifts and nothing else changes.

Data, not numbers: the random quest floors are the RANDOM rows of the quest
knowledge (lib/edit/quests/04N_RandomQuest.jsonc, "level" and "dungeon").
birth/game-play-initializer.cpp init_dungeon_quests sets every one TAKEN at
birth with that data level, and the game discloses the shallowest one in the
quest list only once the dungeon's max depth reaches it
(QuestList::find_shallowest_random_quest_id, bot-json-output.cpp
make_disclosed_quests_json), and then its status (TAKEN, COMPLETED,
FINISHED, FAILED).  A random quest is therefore pending unless a disclosed
row reports it resolved.  An UNTAKEN fixed quest is not disclosed at all, so
an absent Q2 row is open.

Only the crossing is held (``current < level <= destination``): a character
already on (or below) a random quest floor is left to the quest owners and
their exit lock (QuestPolicyMixin._quest_floor_exit_locked).
"""

from __future__ import annotations

from hengbot.policy_constants import QUEST_STATUS_TAKEN, QUEST_STATUS_UNTAKEN
from hengbot.q2_tower_recharge import Q2_QUEST_ID
from hengbot.quest_knowledge import QUEST_TYPE_RANDOM

# The fixed quest whose resolution releases the hold (owner 2026-11-02).
GATING_QUEST_ID = Q2_QUEST_ID
_OPEN_STATUSES = frozenset({QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN})
REASON = "depth-gate:random-quest-after-q2"


def _gating_quest_open(snapshot) -> bool:
    """Q2 is untaken (not disclosed) or taken; any other status resolves it."""
    quest = snapshot.quests.get(GATING_QUEST_ID)
    return quest is None or quest.status in _OPEN_STATUSES


def _pending_random_levels(policy, snapshot, dungeon_id: int) -> list[int]:
    """The data levels of ``dungeon_id``'s random quests no row reports resolved."""
    levels = []
    for info in policy._quest_knowledge.values():
        if info.type != QUEST_TYPE_RANDOM or info.dungeon != dungeon_id or info.level <= 0:
            continue
        disclosed = snapshot.quests.get(info.id)
        if disclosed is None or disclosed.status == QUEST_STATUS_TAKEN:
            levels.append(info.level)
    return levels


def first_held_level(policy, snapshot, dungeon_id: int) -> int | None:
    """The shallowest random quest floor of ``dungeon_id`` held now, if any."""
    # A board without any quest rows (legacy protocol) cannot tell Q2 apart.
    if not snapshot.quests or not _gating_quest_open(snapshot):
        return None
    levels = _pending_random_levels(policy, snapshot, dungeon_id)
    return min(levels) if levels else None


def crossing_held(policy, snapshot, dungeon_id: int, current: int, destination: int) -> bool:
    """Whether going from ``current`` to ``destination`` enters a held floor."""
    level = first_held_level(policy, snapshot, dungeon_id)
    return level is not None and current < level <= destination
