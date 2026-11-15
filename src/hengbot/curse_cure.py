"""The worn curse removed in the dungeon before a rest or a wait (owner 2026-11-15).

Owner 2026-11-15: 「クエストでも通常探索でも、休憩中に呪いが発動したら解呪を試みるロジックを
組み込みたい」, and on the questions:

 1. 「呪われていれば休む前に解く」: worn gear is cursed (and not known to carry a curse the means
    cannot remove), the board is safe, and the bot would rest or wait: the curse is removed
    first.  It also takes the curses that print nothing (random teleport, experience drain)
    and catches a curse before it grows heavier.
 2. 「クエストの階は残って続ける」: with no means, or with the curse still there, a summoning
    curse (call animal / demon / dragon / undead) or a drain-HP curse on a normal floor reads
    Word of Recall (the town cures it); on a quest floor nothing more is done and the plan goes
    on (it answers the summoned monsters).  Every other curse waits for the town as before.
 3. 「持ち歩かない」: a character other than the Magic-Eater carries no Remove Curse scroll; it
    is cured in town as before, and in the dungeon only rule 2 applies to it.
 4. 「強力発動を先にする」: the Magic-Eater's absorbed Staff of Remove Curse through Powerful
    Activation first (*Remove Curse*, every curse); only when the HP left after its cost would
    reach the low-HP line, its ordinary use.

The game (C++ source):
 - execute_cursed_items_effect (inventory/inventory-curse.cpp) runs the worn curses from the
   world turn (world/world-turn-processor.cpp): CALL_ANIMAL 1 in 2500, CALL_DEMON and
   CALL_UNDEAD 1 in 1111, CALL_DRAGON 1 in 800 (「{}が動物を引き寄せた！」 / 「Your {} has
   attracted an animal!」 ...), DRAIN_HP 1 in 666 (「{}はあなたの体力を吸収した！」 / 「Your {} drains
   HP from you!」, min(lev * 2, 100) HP); each disturbs, so a rest is cut.  A quest floor gets
   no natural spawns (decide_alloc_monster: ``!floor.is_in_quest()``), so a summoning curse
   alone feeds it (n1-c life-211, Q25: 7 cursed pieces, the druj's CAUSE_3).
 - The staff's effect (cmd-item/cmd-usestaff.cpp): powerful ? remove_all_curse : remove_curse
   (spell-kind/spells-curse-removal.cpp exe_curse_removal over the worn slots): the ordinary
   one skips a HEAVY_CURSE item; both leave a PERMA_CURSE item cursed but cut its curses down to
   CURSED / HEAVY_CURSE / PERMA_CURSE, so its summoning and drain go.  A curse the item carries
   as a TR flag (update_curses, player/player-status-flags.cpp: TR_CALL_ANIMAL ...) is no curse
   flag: nothing removes it.
 - Neither ``U`` (cmd-action/cmd-racial.cpp) nor ``m`` (cmd-item/cmd-magiceat.cpp) refuses
   blindness or darkness (cmd_limit_confused only); the absorbed power has its own fail chance
   in both (do_cmd_magic_eater), and Powerful Activation pays its cost in HP
   (me_powerful_activation.cost).

What decides here: ``removal_key`` alone decides a removal in the dungeon, asked from the
dungeon ladder's safe-now layer (``key``, with rule 2's recall after it) and before every rest
or wait key of the quest plans (``before_rest``: quest_plan_base._rest, quest25_battle's holds
and rests, the navigator's hold).  Its results are learnt as the town's are: a completed
Powerful Activation that leaves the item cursed proves PERMA_CURSE (me_powerful_activation
.observe), a completed ordinary use that leaves it cursed proves HEAVY_CURSE (``observe``, as
policy ``_observe_remove_curse`` learns from a scroll), and each target has
me_powerful_activation.ATTEMPTS_PER_TARGET uses, so nothing loops on a curse it cannot remove.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from hengbot import cross_rules, me_absorbed_substitutes, me_capability, me_powers
from hengbot import me_powerful_activation as powerful
from hengbot.equipment_optimizer import (
    TR_CALL_ANIMAL, TR_CALL_DEMON, TR_CALL_DRAGON, TR_CALL_UNDEAD, TR_DRAIN_HP,
)
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.me_staff_sequence import cast_blocked


REASON = "curse-cure"
POWERFUL_REASON = f"{REASON}:powerful"
NORMAL_REASON = f"{REASON}:normal"
# The ordinary use's owner, as me_device_attacks_input answers it (me_absorbed_substitutes).
NORMAL_OWNER = NORMAL_REASON + me_absorbed_substitutes.CAST_SUFFIX
# Rule 2's read: the planned town return's Word of Recall (destruction_use.MEANS_SPENT_REASON),
# named by its trigger; the ``emergency-`` prefix makes the return a survival one
# (town_hold.is_survival_return_trigger): no loot sweep delays it.
RECALL_REASON = "return:recall"
RECALL_TRIGGER = "emergency-curse-summons-remain"
MEMORY = "_curse_cure"
UNCURSE = powerful.UNCURSE

# The curses rule 2 answers, as their TR flags (an item's own, which no removal takes).
SUMMONING_FLAGS = frozenset({TR_CALL_ANIMAL, TR_CALL_DEMON, TR_CALL_DRAGON, TR_CALL_UNDEAD})
RULE2_FLAGS = SUMMONING_FLAGS | {TR_DRAIN_HP}
# The game's messages of those curses (inventory-curse.cpp curse_call_monster, curse_drain_hp),
# naming the worn item (describe_flavor OD_OMIT_PREFIX | OD_NAME_ONLY).
_ANNOUNCED = (
    re.compile(r"^(?P<name>.+?)が(?:動物|悪魔|ドラゴン|死霊)を引き寄せた！$"),
    re.compile(r"^(?P<name>.+?)はあなたの体力を吸収した！$"),
    re.compile(r"^Your (?P<name>.+?) has attracted an? (?:animal|demon|dragon|undead)!$"),
    re.compile(r"^Your (?P<name>.+?) drains HP from you!$"),
)


@dataclass
class Memory:
    announced: dict = field(default_factory=dict)   # slot -> the item name the message gave
    normal_attempts: dict = field(default_factory=dict)   # signature -> ordinary uses
    normal_pending: tuple | None = None             # (turn, cursed signatures) of the last use
    powerful_turn: int | None = None                # the turn of the last Powerful Activation
    cursed_slots: frozenset = frozenset()           # the worn slots cursed on the last board


def _memory(policy) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Memory()
        setattr(policy, MEMORY, memory)
    return memory


def _message_text(message: str) -> str:
    return re.sub(r" <x[1-9]\d*>$", "", message)


def _announced_name(message: str) -> str | None:
    for pattern in _ANNOUNCED:
        match = pattern.match(_message_text(message))
        if match is not None:
            return match["name"]
    return None


# -- what is worn ---------------------------------------------------------------


def _inherent(item) -> bool:
    """A summoning or drain-HP TR flag the item shows: no removal takes it."""
    return bool(RULE2_FLAGS & set(item.known_flags))


def rule2_items(policy, snapshot) -> list:
    """Worn items whose summoning or drain-HP curse is known: announced by the game since the
    last removal, or shown as the item's own flag."""
    announced = _memory(policy).announced
    return [item for item in snapshot.equipment
            if _inherent(item) or (item.slot in announced and announced[item.slot] in item.name)]


def _permanent(policy, item) -> bool:
    return policy._item_signature(item) in getattr(policy, "_permanent_cursed_items", ())


def targets(policy, snapshot) -> list:
    """The worn cursed items a removal may serve: not proven permanent, or permanent with a
    summoning or drain-HP curse announced (exe_curse_removal cuts a PERMA_CURSE item's curses
    down to CURSED / HEAVY / PERMA: those go)."""
    announced = {id(item) for item in rule2_items(policy, snapshot) if not _inherent(item)}
    return [item for item in snapshot.equipment if item.is_cursed
            and (not _permanent(policy, item) or id(item) in announced)]


# -- the removal ----------------------------------------------------------------


def _magic_eater_staff(policy, snapshot) -> bool:
    return (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            and me_capability.has(policy, snapshot, UNCURSE.kind, UNCURSE.sval))


def _dungeon(snapshot) -> bool:
    return (not snapshot.in_town and snapshot.dungeon_level >= 1
            and not getattr(snapshot, "inside_arena", False))


def safe(policy, snapshot) -> bool:
    """No enemy threatening: no hit taken and no visible hostile the combat ladder judges
    dangerous (me_powers.utility_device_permitted, the absorbed utility powers' rule), none
    beside the player (me_powerful_activation's town rule); and nothing stops the command
    (cast_blocked: a store, blindness, confusion, hallucination, paralysis, a refused ``m``)."""
    return (_dungeon(snapshot) and not cast_blocked(snapshot)
            and not policy._physical_adjacent_hostiles(snapshot)
            and me_powers.utility_device_permitted(policy, snapshot))


def _powerful_work(policy, snapshot, items):
    if snapshot.player.level < powerful.MIN_LEVEL:
        return None
    return powerful._first_open(policy, UNCURSE, items)


def _normal_target(policy, items):
    """The first item the ordinary use can serve: not known heavy or permanent, uses left."""
    attempts = _memory(policy).normal_attempts
    return next((item for item in items if not policy._curse_unremovable(item)
                 and attempts.get(policy._item_signature(item), 0) < powerful.ATTEMPTS_PER_TARGET),
                None)


def removal_key(policy, snapshot) -> str | None:
    """The Magic-Eater's removal on a safe dungeon board with cursed gear worn, else None.

    Rule 4: Powerful Activation while its cost leaves HP above the low-HP line
    (me_powerful_activation.pays_safely); else, or below its level, the ordinary use for an
    item it can serve.  Without a charge nothing is cast: the absorbed staff regains it, the
    rest goes on (owner 2026-10-31 「取り込んだ魔法道具は再充填される」 for the town's use).
    """
    cross_rules.consult(policy, cross_rules.UNCURSE_BEFORE_REST)
    if not _magic_eater_staff(policy, snapshot) or not safe(policy, snapshot):
        return None
    items = targets(policy, snapshot)
    if not items or powerful.charges_left(policy, snapshot, UNCURSE) <= 0:
        return None
    work = _powerful_work(policy, snapshot, items)
    if work is not None and powerful.pays_safely(policy, snapshot):
        _memory(policy).powerful_turn = snapshot.turn
        return powerful._use(policy, snapshot, *work, reason=POWERFUL_REASON)
    target = _normal_target(policy, items)
    if target is None:
        return None
    key = me_absorbed_substitutes.cast(policy, snapshot, me_absorbed_substitutes.REMOVE_CURSE,
                                       NORMAL_REASON)
    if key is not None:
        memory = _memory(policy)
        signature = policy._item_signature(target)
        memory.normal_attempts[signature] = memory.normal_attempts.get(signature, 0) + 1
        memory.normal_pending = (snapshot.turn, frozenset(
            policy._item_signature(item) for item in snapshot.equipment if item.is_cursed))
    return key


def before_rest(policy, snapshot) -> str | None:
    """Asked by a quest plan before its rest or wait key: the removal, else None (rule 2 on a
    quest floor: nothing more, the plan goes on)."""
    return removal_key(policy, snapshot)


# -- rule 2 ---------------------------------------------------------------------


def _means(policy, snapshot, items) -> bool:
    """A removal is still to be had for one of ``items``: the absorbed staff and a use left on
    an item the curse flags of which a removal takes (an item's own TR flag no use takes)."""
    if not _magic_eater_staff(policy, snapshot):
        return False
    open_targets = {id(item) for item in targets(policy, snapshot)}
    for item in items:
        if id(item) not in open_targets or _inherent(item):
            continue
        if _powerful_work(policy, snapshot, [item]) is not None:
            return True
        if _normal_target(policy, [item]) is not None:
            return True
    return False


def remains(policy, snapshot) -> bool:
    """A summoning or drain-HP curse is worn and no removal is to be had (rule 2)."""
    items = rule2_items(policy, snapshot)
    return bool(items) and not _means(policy, snapshot, items)


def recall_key(policy, snapshot) -> str | None:
    """Rule 2 on a normal floor: the town return starts (``RECALL_TRIGGER``) and Word of Recall
    is read when this floor lets one be read (once_quest_recall.read_key).  Without a read the
    return stays latched and its own rungs leave the floor.  A quest floor: None."""
    from hengbot import once_quest_recall  # import cycle

    if not _dungeon(snapshot) or snapshot.floor_key[2] != 0 or not remains(policy, snapshot):
        return None
    if not policy._returning_to_town or policy._last_return_trigger != RECALL_TRIGGER:
        if not policy._returning_to_town:
            policy._note_return_start(RECALL_TRIGGER)
        policy._returning_to_town = True
        policy._last_return_trigger = RECALL_TRIGGER
    return once_quest_recall.read_key(policy, snapshot, RECALL_REASON)


def key(policy, snapshot) -> str | None:
    """The dungeon ladder's rung (safe-now): the removal, then rule 2's recall."""
    return removal_key(policy, snapshot) or recall_key(policy, snapshot)


# -- the evidence ---------------------------------------------------------------


def observe(policy, snapshot) -> None:
    """Every decision: the curses the game announced, the last ordinary use's result.

    An announcement names its item; it holds while that item is worn and cursed, and is dropped
    when the item's curse is removed (cursed on the last board, not on this one), after a
    completed Powerful Activation of Remove Curse (it takes every worn summoning and drain
    curse, a permanent item's too) and in town (the town cures; a curse still there announces
    itself again on the next floor)."""
    memory = _memory(policy)
    worn = {item.slot: item for item in snapshot.equipment}
    cursed_slots = frozenset(slot for slot, item in worn.items() if item.is_cursed)
    if snapshot.in_town:
        memory.announced.clear()
    else:
        for message in snapshot.messages:
            name = _announced_name(message)
            if name is None:
                continue
            slot = next((slot for slot, item in worn.items() if name in item.name), None)
            if slot is not None:
                memory.announced[slot] = name
    refusal = (snapshot.completed_operation_receipt or {}).get("refusal")
    failed = isinstance(refusal, str) and refusal.startswith("failed")
    powerful_turn, memory.powerful_turn = memory.powerful_turn, None
    if (powerful_turn is not None and snapshot.turn != powerful_turn
            and snapshot.completed_operation_owner == POWERFUL_REASON and not failed):
        memory.announced.clear()
    for slot in [slot for slot, name in memory.announced.items()
                 if slot not in worn or name not in worn[slot].name
                 or (slot in memory.cursed_slots and slot not in cursed_slots)]:
        del memory.announced[slot]
    memory.cursed_slots = cursed_slots
    _settle_normal(policy, snapshot, memory, failed)


def _settle_normal(policy, snapshot, memory, failed) -> None:
    """A completed ordinary use (the game turn moved on, no failure) that left an item cursed:
    HEAVY_CURSE, as a Remove Curse scroll that left it cursed proves (policy
    ``_observe_remove_curse``); an item it freed gives its uses back."""
    pending = memory.normal_pending
    if pending is None or snapshot.turn == pending[0]:
        return
    memory.normal_pending = None
    if snapshot.completed_operation_owner != NORMAL_OWNER or failed:
        return
    cursed = {policy._item_signature(item) for item in snapshot.equipment if item.is_cursed}
    for signature in pending[1] & cursed:
        if signature in getattr(policy, "_permanent_cursed_items", ()):
            continue
        policy._heavy_cursed_items.add(signature)
        if policy._heavy_curse_inscription_pending is None:
            policy._heavy_curse_inscription_pending = signature
    for signature in [signature for signature in memory.normal_attempts if signature not in cursed]:
        del memory.normal_attempts[signature]
