"""*Destruction* in place of the Teleportation a rung reads away from a threat.

Owner 2026-11-04: 「成功率80%以上の*破壊*を使えるとき、強敵からのテレポートによる逃走に
代わり*破壊*を使用する。」  Answers: 「杖と取り込んだ力だけ」; 「脅威が範囲内に見える時に
使用。また、ランダムクエストの階ではターゲット以外の脅威を排除するのに使う。傷を負った
ターゲットは巻き込まない場面に限定する。」; 「治して階の探索を続ける。破壊の回数だけでは
帰還しない。」  The 50F ban stays (policy_constants.DESTRUCTION_USE_IMPLEMENTED).

Game (C:/hengband/src):
 * spell-kind/spells-floor.cpp destroy_area: refused on a fixed quest floor and on
   the surface.  Radius 13 + randint0(5) (cmd-usestaff.cpp:282; the Powerful
   Activation's 18 is never cast here).  Every monster is deleted (no experience)
   but a QUESTOR, which is healed fully and teleported away.  A dungeon guardian
   is not a QUESTOR (only the bounty of the floor's quest is set so,
   dungeon-processor.cpp:102).  Items and non-permanent terrain go, the map
   knowledge of the circle goes, and 「燃えるような閃光が発生した！」 is printed, with
   blindness 10+1d10 unless the player resists blindness or light.
 * A staff (object-use/use-execution.cpp): no blind or confused refusal, but
   confusion halves the skill, stun may refuse it, a Berserker always fails, a
   failure spends the turn and keeps the charge.  The absorbed power
   (cmd-magiceat.cpp) refuses a confused player; a failure spends the turn and
   keeps the charge.

Gates (``key``): the rung holds a Teleportation scroll to read; the character is
clear-headed; a means is reliable (``me_capability.RELIABLE_MIN_SUCCESS``, the
absorbed power first as in speed_dose); the floor is one the game destroys; the
most dangerous awake visible hostile other than the quest target is in
``GUARANTEED_RADIUS``; and no damaged target or guardian is in ``WORST_RADIUS``.  Anything
else leaves the rung's read as it was.

A use that printed no flash (a failure, the empty staff) or a key the game did
not take falls back to the Teleportation on the next ask: speed_dose's rule for
a failed cast on the survival rungs, with no retry number of its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import attack_expectation, me_capability
from hengbot import me_absorbed_substitutes as substitutes
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_STAFF, game_distance
from hengbot.policy_constants import PLAYER_CLASS_BERSERKER


REASON = "emergency:destruction"
POWER = ("staff", SV_STAFF_DESTRUCTION)
STAFF = (TVAL_STAFF, SV_STAFF_DESTRUCTION)
STAFF_LEVEL = 50             # BaseitemDefinitions.jsonc id 307
GUARANTEED_RADIUS = 13       # cmd-usestaff.cpp:282 13 + randint0(5)
WORST_RADIUS = 17
FLASH = ("燃えるような閃光が発生した！", "There is a searing blast of light!")
MEMORY = "_destruction_use_memory"

@dataclass
class Memory:
    pending: tuple | None = None   # (floor, turn, position) of the last use
    fallback: tuple | None = None  # the floor whose next ask reads the Teleportation


def _memory(policy) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Memory()
        setattr(policy, MEMORY, memory)
    return memory


# -- the means ------------------------------------------------------------------

def _absorbed_key(policy, snapshot) -> str | None:
    """The reliable power (me_capability's counting row) with a charge here."""
    if me_capability.replacing_charges(policy, snapshot, STAFF) <= 0:
        return None
    return substitutes.cast_key(policy, snapshot, substitutes.POWERS[POWER])


def _reliable_staff(snapshot) -> bool:
    """use-execution.cpp's chance (attack_expectation) at the table's number."""
    if snapshot.player.class_id == PLAYER_CLASS_BERSERKER:
        return False
    success = attack_expectation.device_use_success(snapshot.player.device_skill, STAFF_LEVEL)
    return success * 100 >= me_capability.RELIABLE_MIN_SUCCESS


def _carried_key(policy, snapshot) -> str | None:
    if not _reliable_staff(snapshot):
        return None
    staff = next((item for item in snapshot.inventory
                  if policy._is_destruction_staff(item) and item.known and item.charges > 0), None)
    return None if staff is None else reserved_item_command(policy, snapshot, "staff", staff)


# -- the scene ------------------------------------------------------------------

def _clear_headed(player) -> bool:
    return not (player.blind or player.confused or player.hallucinated or player.stunned)


def _floor_destroyed(policy, snapshot) -> bool:
    """destroy_area refuses a fixed quest floor and the surface."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        return False
    quest_id = snapshot.floor_key[2]
    return not quest_id or (quest_id in snapshot.quests
                            and policy._runtime_random_quest(snapshot, quest_id))


def _target_race(policy, snapshot) -> int | None:
    quest_id = policy._active_kill_quest_id(snapshot)
    quest = snapshot.quests.get(quest_id) if quest_id is not None else None
    return policy._quest_target_race_id(quest) if quest is not None else None


def _guardian_race(policy, snapshot) -> int | None:
    info = policy._dungeon_knowledge.get(snapshot.floor_key[0])
    if info is None or snapshot.dungeon_level != info.max_depth or info.guardian_id <= 0:
        return None
    return info.guardian_id


def _spared_in_circle(policy, snapshot, target) -> bool:
    """A damaged quest target (healed by the use) or the floor's guardian (deleted;
    the owner's words do not cover it, so the rung reads as today)."""
    guardian = _guardian_race(policy, snapshot)
    return any(
        game_distance(snapshot.player.position, monster.position) <= WORST_RADIUS
        and (monster.race_id == guardian
             or (monster.race_id == target and monster.hp < monster.max_hp))
        for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))


def _threat_in_range(policy, snapshot, target) -> bool:
    """The most dangerous awake visible hostile but the target is in the guaranteed
    radius; an attacker the board does not show is no such threat."""
    if getattr(policy, "_unseen_attack_evidence", None) is not None:
        return False
    awake = [m for m in snapshot.visible_monsters
             if m.hostile and not m.asleep and m.race_id != target]
    if not awake:
        return False
    here = snapshot.player.position
    worst = max(awake, key=lambda m: (policy._predicted_damage(snapshot, [m], turns=1),
                                      -game_distance(here, m.position)))
    return game_distance(here, worst.position) <= GUARANTEED_RADIUS


def _scene_holds(policy, snapshot) -> bool:
    if not _clear_headed(snapshot.player) or not _floor_destroyed(policy, snapshot):
        return False
    target = _target_race(policy, snapshot)
    return (_threat_in_range(policy, snapshot, target)
            and not _spared_in_circle(policy, snapshot, target))


def _falls_back(memory, snapshot) -> bool:
    """The last use failed or its key was not taken: this ask reads the scroll."""
    if memory.pending is not None and memory.pending[:2] == (snapshot.floor_key, snapshot.turn):
        memory.pending = None
        return True
    if memory.fallback == snapshot.floor_key:
        memory.fallback = None
        return True
    return False


def key(policy, snapshot, scroll) -> str | None:
    """The use in place of reading ``scroll``, setting ``last_reason``; else None."""
    if not scroll.is_teleport_scroll or _falls_back(_memory(policy), snapshot):
        return None
    if not _scene_holds(policy, snapshot):
        return None
    cast = _absorbed_key(policy, snapshot)
    used = cast or _carried_key(policy, snapshot)
    if used is None:
        return None
    policy.last_reason = REASON + (substitutes.CAST_SUFFIX if cast else "")
    _memory(policy).pending = (snapshot.floor_key, snapshot.turn, snapshot.player.position)
    return used


# -- after the use --------------------------------------------------------------

def observe(policy, snapshot) -> None:
    """Every decision, before the board joins the map memory: settle the last use."""
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        return
    if memory.fallback is not None and memory.fallback != snapshot.floor_key:
        memory.fallback = None
    if memory.pending is None:
        return
    floor, turn, _position = memory.pending
    if snapshot.floor_key != floor:
        memory.pending = None
    elif any(message in FLASH for message in snapshot.messages):
        memory.pending = None
    elif snapshot.turn != turn:
        memory.pending = None
        memory.fallback = floor
