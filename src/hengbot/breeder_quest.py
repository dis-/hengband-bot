"""What a breeder stalemate does on a quest floor (owner 2026-11-02).

Owner, verbatim: 「全滅要求のクエストは達成できないので放棄。ランダムクエストなど
ターゲット討伐要求の場合はテレポートで距離を取り、増殖モンスターの近くを避けて続行」

When the 100-attack rule (breeder_stalemate) latches a quest floor, the
floor's quest type decides the response (``RESPONSE_BY_QUEST_TYPE``):

* ABANDON -- the quest completes only when every hostile on the floor is
  dead (quest-completion-checker.cpp complete_kill_all / complete_tower:
  ``count_all_hostile_monsters() != 1`` returns), which a growing breeder
  population never allows.  The floor is left by Word of Recall (or the
  exit the floor offers); world-movement-processor.cpp leaves an in-quest
  floor through leave_quest_check, which records an ONCE quest FAILED
  (quest.cpp leave_quest_check; every KILL_ALL quest in lib/edit/quests is
  PRESET+ONCE), and leave_tower_check fails the tower.  A FAILED quest is
  neither TAKEN nor offered, so the bot never re-enters it.
* PURSUE -- the quest completes by killing its named target
  (complete_random: KILL_LEVEL / RANDOM count ``q_ptr->r_idx`` kills
  only).  While the quest exit lock holds, a Scroll of Teleportation
  gains distance once per stalemate (the 100-attack window restarts), and
  routing vetoes the cells within one step of every perceived breeder --
  the reach of a bite, the same ring the paralyzer avoidance uses
  (policy_combat._refresh_paralyzer_avoidance: NEIGHBOR_OFFSETS + (0, 0)).
  Only Teleportation itself: Teleport Level and Deep Descent leave a quest
  floor (spells-world.cpp teleport_level -> leave_quest_check).  A biting
  breeder beside the player is still fought (survival_preemption).
  Without a readable scroll the floor keeps the breakthrough's behaviour.

The bite ring of a breeder out of sight stays at its last shown cell (owner 2026-11-09
「起きた敵も最後の位置を覚える」, the memory of monster_memory and its window): n1-a life-505
(Angband 6F, random quest 49, 2026-11-10 02:34 and 02:35) saw 巨大白シラミ (race 69) up the
corridor from [46,74], whose rings closed it, and explore stepped '1' to [47,73]; there
they were out of sight, the rings were released and explore stepped '9' straight back,
until the loop detector, twice.  The weak breeders of the latched floor are not strategic
hostiles (policy ``_strategic_subset``), so sleeper_reach_memory does not keep them: this
module keeps its own.  A remembered breeder is forgotten when shown again (then kept where
shown), killed, on the floor's change or after the window.

Quest types absent from the table (KILL_NUMBER: every kill counts, so
breeders advance it; FIND_*) keep the breakthrough's behaviour.
"""
from __future__ import annotations

from hengbot import breeder_floor_record, breeder_stalemate, monster_memory, quest_no_teleport
from hengbot.model import Position
from hengbot.policy_constants import NEIGHBOR_OFFSETS, QUEST_STATUS_TAKEN
from hengbot.quest_knowledge import (
    QUEST_TYPE_KILL_ALL,
    QUEST_TYPE_KILL_ANY_LEVEL,
    QUEST_TYPE_KILL_LEVEL,
    QUEST_TYPE_RANDOM,
    QUEST_TYPE_TOWER,
)
from hengbot.sleeper_loot_block import remembered_gone


ABANDON = "abandon"
PURSUE = "pursue"
RESPONSE_BY_QUEST_TYPE = {
    QUEST_TYPE_KILL_ALL: ABANDON,
    QUEST_TYPE_TOWER: ABANDON,
    QUEST_TYPE_KILL_LEVEL: PURSUE,
    QUEST_TYPE_KILL_ANY_LEVEL: PURSUE,
    QUEST_TYPE_RANDOM: PURSUE,
}
TELEPORT_REASON = "breeder-breakthrough:teleport"
# A bite reaches the eight neighbours; the breeder's own cell is occupied.
_BITE_RING = NEIGHBOR_OFFSETS + ((0, 0),)
# The perceived breeders of the pursued floor, kept at their last shown cell out of sight.
BREEDER_SEEN = monster_memory.Kind("_breeder_quest_seen")


def response(policy, snapshot) -> str | None:
    """The latched floor's response by its TAKEN quest's type, else None."""
    if policy._breeder_breakthrough_floor != snapshot.floor_key:
        return None
    quest = snapshot.quests.get(snapshot.floor_key[2])
    if quest is None or quest.status != QUEST_STATUS_TAKEN:
        return None
    info = policy._quest_knowledge.get(quest.id)
    return RESPONSE_BY_QUEST_TYPE.get(info.type if info is not None else quest.type)


def abandons_floor(policy, snapshot) -> bool:
    """The latched floor's quest cannot be completed: leave it."""
    return response(policy, snapshot) == ABANDON


def abandon_key(policy, snapshot, hostiles) -> str | None:
    """The leave of an abandoned floor, for the owner that holds the whole floor.

    An approved quest's navigator returns above the breakthrough rung, so the
    latched floor must be left from there.  With the recall active the leave
    is decided and None gives the board back: the floor's own attack logic
    keeps fighting until the recall takes the player away."""
    if not abandons_floor(policy, snapshot) or snapshot.player.recalling:
        return None
    return policy._breeder_breakthrough_key(snapshot, hostiles)


def _pursuing(policy, snapshot) -> bool:
    # A released exit lock (teleport reserve, light, panic ...) leaves the
    # floor through the breakthrough's recall instead.
    return response(policy, snapshot) == PURSUE and policy._return_exit_locked(snapshot)


def refresh_avoidance(policy, snapshot) -> None:
    """Veto the bite ring of every perceived breeder while pursuing."""
    previous = getattr(policy, "_breeder_quest_avoid_cells", set())
    if previous:
        policy._refresh_warning_avoidance(snapshot, released_cells=previous)
    cells = set()
    if _pursuing(policy, snapshot):
        monster_memory.observe(policy, snapshot, BREEDER_SEEN, remember=_perceived_breeders,
                               gone=remembered_gone)
        breeders = (*_perceived_breeders(policy, snapshot),
                    *monster_memory.remembered(policy, snapshot, BREEDER_SEEN))
        cells = {
            cell
            for monster in breeders
            for dy, dx in _BITE_RING
            if (cell := Position(monster.position.y + dy, monster.position.x + dx))
            in snapshot.grids
        }
    policy._breeder_quest_avoid_cells = cells
    if cells:
        policy._refresh_warning_avoidance(snapshot, added_cells=cells)


def _perceived_breeders(policy, snapshot) -> list:
    return [monster for monster in policy._sighted_or_detected_hostiles(snapshot)
            if monster.can_multiply]


def teleport_key(policy, snapshot) -> str | None:
    """Read Teleportation once per stalemate on a pursued quest floor."""
    if not _pursuing(policy, snapshot) or not breeder_stalemate.stalemate_standing(policy):
        return None
    player = snapshot.player
    if player.blind or player.confused or not policy._can_read_scrolls(snapshot):
        return None
    if quest_no_teleport.forbids(policy, snapshot) or policy._relocation_refused(snapshot):
        return None
    scroll = policy._first_item(snapshot, lambda item: item.is_teleport_scroll)
    if scroll is None:
        return None
    if (takeoff := policy._anti_teleport_takeoff_key(snapshot, scroll)) is not None:
        return takeoff    # the stalemate stands: the read comes on the next decision
    breeder_stalemate.forget(policy)
    breeder_floor_record.record(policy, snapshot)
    policy.last_reason = TELEPORT_REASON
    return policy._read_key(snapshot, scroll)
