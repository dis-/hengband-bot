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

Owner 2026-11-06 「開いた中で条件を満たす階へ」: 「深さの条件を満たす開いたダンジョンの
うち、一番深い階へ行きます。迷宮も候補です。条件を満たす所がなければイークの洞穴のまま
です」.  A character with the Yeek cave conquered has nothing left to do there, so
``settle_target`` takes the deepest landing ``_pick_alternate_dungeon`` allows, with
all of its gates.  It reads the choice on town boards only, so a dive keeps the
target it left with and the valve judges that dive by it.  The over-extension
alternate overrides this target later in the same observation and stays until its
own end, so a step down does not bounce back.
"""

from __future__ import annotations

from hengbot.model import DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE
from hengbot.policy_constants import QUEST_STATUS_TAKEN, QUEST_STATUS_UNTAKEN
from hengbot.q2_tower_recharge import Q2_QUEST_ID
from hengbot.quest_knowledge import QUEST_TYPE_RANDOM

# The fixed quest whose resolution releases the hold (owner 2026-11-02).
GATING_QUEST_ID = Q2_QUEST_ID
_OPEN_STATUSES = frozenset({QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN})
# Display only (spectator): why the target is not Angband though its recall is unlocked.
TARGET_REASON = "angband_closed_before_q2"
# Display only (spectator): the deepest open floor that passes the depth conditions.
DEEPEST_OPEN_REASON = "deepest_open_before_q2"


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


def settle_target(policy, snapshot) -> None:
    """The recall target this board, for the part of it that Q2 decides."""
    held_choice = policy._target_dungeon_reason == DEEPEST_OPEN_REASON
    if not entry_refused(snapshot, DUNGEON_ANGBAND):
        if held_choice:  # Q2 resolved: the ordinary selection takes over from the start
            policy._target_dungeon_id = DUNGEON_YEEK_CAVE
            policy._target_dungeon_reason = "initial_yeek_cave"
        return
    if snapshot.yeek_cave_conquered and snapshot.in_town:
        deepest = policy._pick_alternate_dungeon(  # an intended destination: no fallback floor
            snapshot, prefer_deepest=True, require_shallower=False, depth_floor=False)
        if deepest is not None:
            policy._target_dungeon_id = deepest
            policy._target_dungeon_reason = DEEPEST_OPEN_REASON
            return
    elif held_choice:
        return
    if (snapshot.yeek_cave_conquered or snapshot.angband_recall_unlocked
            or policy._target_dungeon_id == DUNGEON_ANGBAND):
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._target_dungeon_reason = TARGET_REASON


def crossing_held(policy, snapshot, dungeon_id: int, current: int, destination: int) -> bool:
    """Whether going from ``current`` to ``destination`` enters or passes a held floor."""
    return hold_active(snapshot) and any(
        current < level <= destination
        for level in _pending_random_levels(policy, snapshot, dungeon_id))
