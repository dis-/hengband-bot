"""Hold the dive above the runtime RANDOM quest floors until Q2 is resolved.

Owner 2026-11-02: 「angband 6F, 12Fのランダムクエストに挑む順が早いので達成率が
低い。Q2の後に回したい」.  While the gating fixed quest (Q2, 下水道) is still
open, no voluntary descent may cross a dungeon floor that holds a pending
RANDOM quest: the dive stops above it.  ``down_destination`` reads the stair: a
shaft lands two floors down.  After Q2 the hold lifts and nothing else changes.

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

Owner 2026-11-05: 「下水道をクリアするまで鉄獄に帰還しない」「地上からの経路はそもそも
禁止しているはずだが、改めて明確に禁止する」.  While the hold is active nothing enters
Angband from the surface: ``entry_refused`` is the one answer for the recall
destination (PolicyObservation's target, _pick_alternate_dungeon) and for the
walk ('>' on a surface tile, _is_descent_target).  The target falls back to the
Yeek cave, as for a character whose Angband recall was never unlocked.  A
character already inside Angband plays on above the hold until its ordinary
return; the next departure goes elsewhere.
"""

from __future__ import annotations

from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy_constants import QUEST_STATUS_TAKEN, QUEST_STATUS_UNTAKEN
from hengbot.q2_tower_recharge import Q2_QUEST_ID
from hengbot.quest_knowledge import QUEST_TYPE_RANDOM

# The fixed quest whose resolution releases the hold (owner 2026-11-02).
GATING_QUEST_ID = Q2_QUEST_ID
_OPEN_STATUSES = frozenset({QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN})
# Display only (spectator): why the target is not Angband though its recall is unlocked.
TARGET_REASON = "angband_closed_before_q2"


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


def hold_active(snapshot) -> bool:
    """Whether Q2 still holds.  A board without quest rows (legacy) cannot tell."""
    return bool(snapshot.quests) and _gating_quest_open(snapshot)


def entry_refused(snapshot, dungeon_id: int | None) -> bool:
    """Whether recall or the walk may not enter ``dungeon_id`` from the surface now."""
    return dungeon_id == DUNGEON_ANGBAND and hold_active(snapshot)


def crossing_held(policy, snapshot, dungeon_id: int, current: int, destination: int) -> bool:
    """Whether going from ``current`` to ``destination`` enters or passes a held floor."""
    return hold_active(snapshot) and any(
        current < level <= destination
        for level in _pending_random_levels(policy, snapshot, dungeon_id))
