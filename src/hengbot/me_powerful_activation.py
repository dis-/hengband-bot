"""The Magic-Eater's Powerful Activation of two absorbed staff powers.

Owner 2026-10-31 (night): 「魔道具術師の強力発動について。一旦鑑定と解呪だけ
取り扱う。該当の杖を取り込んだら上位鑑定と上位解呪の巻物は以降購入せず強力発動で
対応する。」

The game (C++ source):
 - 強力発動 / Powerful Activation is the second class power of class 16
   (racial/class-racial-switcher.cpp: min level 10, cost
   10 + (lvl - 10) / 2, INT, fail 0).  The racial command ``U``
   (io/input-key-processor.cpp) lists the powers and asks
   「(特殊能力 a-c, '*'で一覧, '/'で閲覧, ESCで中断) どの能力を使いますか？」
   (cmd-action/cmd-racial.cpp); racial-switcher.cpp then calls
   ``do_cmd_magic_eater(player, false, true)``: the same kind question and
   power list as an ordinary absorbed use.
 - A Magic-Eater has no mana (ClassMagicDefinitions MAGIC_EATER
   first_spell_level 99, player-status.cpp update_max_mana), so the cost is
   paid in hit points: racial_power_reduce_mana takes cost/2 + 1d(cost/2) HP
   ("過度の集中"), and check_racial_level asks 「本当に今の衰弱した状態で
   この能力を使いますか？」 when HP is below the cost.  The power is used only
   with HP above its cost; below that the character rests first.
 - Staff of Perception (sval 5) powerful = identify_fully (*Identify*:
   「どのアイテムを*鑑定*しますか? 」 then screen_object); Staff of Remove
   Curse (sval 6) powerful = remove_all_curse (every worn curse except
   PERMA_CURSE, no prompt) (cmd-item/cmd-usestaff.cpp staff_effect,
   spell-kind/spells-perception.cpp, spells-curse-removal.cpp).

Rules: once a power is absorbed (the game's displayed staff list, else the
staff sequence's absorption record) its scroll is never bought or required
(``replaces_scroll``, ``serves``), and the town work it serves is this
module's ``town_key``.  Only these two powers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import me_powers, me_staff_sequence
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import (
    SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_STAR_REMOVE_CURSE, SV_STAFF_IDENTIFY, TVAL_SCROLL,
    item_requires_full_identification,
)
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY, REST_MACRO


REASON = "me-powerful"
RACIAL_KEY = "U"
MIN_LEVEL = 10           # class-racial-switcher.cpp rpi.min_level
SV_STAFF_REMOVE_CURSE = 6  # sv-definition/sv-staff-types.h
MEMORY = "_me_powerful"
# Uses of one power on one item before it is given up (the owner's retry
# bound for absorbed powers, me_powers.FAILURES_PER_PLACE).
ATTEMPTS_PER_TARGET = me_powers.FAILURES_PER_PLACE


@dataclass(frozen=True)
class Effect:
    name: str
    sval: int                  # the absorbed staff power
    names: tuple[str, str]     # its list name (BaseitemDefinitions ja, en)
    scroll_sval: int           # the scroll it replaces
    targeted: bool             # identify_fully asks for an item
    kind: str = "staff"

    @property
    def key(self) -> str:
        return RACIAL_KEY + me_powers.KIND_LETTER[self.kind] + me_powers.encode_letter(self.sval)

    @property
    def reason(self) -> str:
        return f"{REASON}:{self.name}"


IDENTIFY = Effect("identify", SV_STAFF_IDENTIFY, me_staff_sequence.POWER_NAMES[SV_STAFF_IDENTIFY],
                  SV_SCROLL_STAR_IDENTIFY, True)
UNCURSE = Effect("uncurse", SV_STAFF_REMOVE_CURSE, ("解呪", "Remove Curse"),
                 SV_SCROLL_STAR_REMOVE_CURSE, False)
EFFECTS = (UNCURSE, IDENTIFY)
BY_SVAL = {effect.sval: effect for effect in EFFECTS}


def cost(level: int) -> int:
    """class-racial-switcher.cpp: rpi.cost = 10 + (lvl - 10) / 2."""
    return 10 + (level - 10) // 2


@dataclass
class Memory:
    attempts: dict = field(default_factory=dict)   # (effect, signature) -> uses
    pending: tuple | None = None                    # (effect, signature, turn)


def _memory(policy) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Memory()
        setattr(policy, MEMORY, memory)
    return memory


# -- the purchase and supply rules ---------------------------------------------

def serves(policy, snapshot, effect: Effect) -> bool:
    """Whether class 16 has absorbed the effect's staff power."""
    return snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER and absorbed(policy, effect)


def absorbed(policy, effect: Effect) -> bool:
    """The last displayed list of the kind, else the staff sequence's record.

    Both are class 16's own (me_device_attacks.observe_lists clears the
    lists for every other class every decision).
    """
    lists = getattr(policy, "_me_device_lists", None) or {}
    if effect.kind in lists:
        return any(row.get("name") in effect.names for row in lists[effect.kind][1])
    return me_staff_sequence.absorbed(policy, effect.sval)


def replaces_scroll(policy, snapshot, item) -> bool:
    """A *Identify* / *Remove Curse* scroll whose power is absorbed."""
    return item.tval == TVAL_SCROLL and any(
        item.sval == effect.scroll_sval and serves(policy, snapshot, effect)
        for effect in EFFECTS)


# -- the town work --------------------------------------------------------------

def _uncurse_target(policy, snapshot):
    permanent = getattr(policy, "_permanent_cursed_items", ())
    return next((item for item in snapshot.equipment if item.is_cursed
                 and policy._item_signature(item) not in permanent), None)


def _identify_target(policy, snapshot):
    return next((item for item in (*snapshot.equipment, *snapshot.inventory)
                 if item.known and not item.fully_known
                 and item_requires_full_identification(item)), None)


TARGETS = {UNCURSE: _uncurse_target, IDENTIFY: _identify_target}


def _address(item) -> str:
    """The item chooser's answer: a pack letter, or '/' + an equipment letter."""
    slot = EQUIPMENT_SLOT_KEY.get(item.slot)
    return item.slot if slot is None else "/" + slot


def _work(policy, snapshot):
    memory = _memory(policy)
    for effect in EFFECTS:
        if not serves(policy, snapshot, effect):
            continue
        target = TARGETS[effect](policy, snapshot)
        if target is None:
            continue
        signature = policy._item_signature(target)
        if memory.attempts.get((effect.name, signature), 0) < ATTEMPTS_PER_TARGET:
            return effect, target, signature
    return None


def _safe(policy, snapshot) -> bool:
    """Survival first: no hit this turn and no hostile beside the player."""
    player = snapshot.player
    return (snapshot.in_town and snapshot.store is None
            and not policy._physical_adjacent_hostiles(snapshot)
            and not getattr(policy, "_took_damage", False)
            and not (player.blind or player.confused or player.hallucinated
                     or player.paralyzed))


def _rest_key(policy, snapshot, hostiles) -> str | None:
    """The town recovery rest (policy_town ``town:recover``) before the cost."""
    if (hostiles or policy._physical_hostiles(snapshot)
            or snapshot.player.food_state not in {"normal", "full", "gorged"}
            or snapshot.player.hp >= snapshot.player.max_hp):
        return None
    policy.last_reason = f"{REASON}:recover-hp"
    return REST_MACRO


def town_key(policy, snapshot, hostiles) -> str | None:
    """Uncurse, then *Identify*, with Powerful Activation on a safe town board."""
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER or not _safe(policy, snapshot):
        return None
    work = _work(policy, snapshot)
    if work is None or snapshot.player.level < MIN_LEVEL:
        return None
    effect, target, signature = work
    if me_powers.charges(policy, snapshot, effect) <= 0:
        return None  # the absorbed power regenerates; nothing is bought
    if snapshot.player.hp <= cost(snapshot.player.level):
        return _rest_key(policy, snapshot, hostiles)
    memory = _memory(policy)
    memory.attempts[(effect.name, signature)] = memory.attempts.get((effect.name, signature), 0) + 1
    memory.pending = (effect, signature, snapshot.turn)
    policy.last_reason = effect.reason
    return effect.key + (_address(target) if effect.targeted else "")


def observe(policy, snapshot) -> None:
    """Every decision: settle the previous use from player-visible evidence.

    A completed use whose curse stays on the item proves PERMA_CURSE (the
    only curse remove_all_curse leaves), as a failed *Remove Curse* scroll
    does (policy ``_observe_remove_curse``).
    """
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.pending is None:
        return
    effect, signature, turn = memory.pending
    if snapshot.turn == turn:
        return
    memory.pending = None
    refusal = (snapshot.completed_operation_receipt or {}).get("refusal")
    if (snapshot.completed_operation_owner != effect.reason
            or (isinstance(refusal, str) and refusal.startswith("failed"))):
        return
    if effect is UNCURSE:
        for item in snapshot.equipment:
            if item.is_cursed and policy._item_signature(item) == signature:
                policy.__dict__.setdefault("_permanent_cursed_items", set()).add(signature)
