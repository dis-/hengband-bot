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

Absorbed powers cast in the dungeon (owner 2026-11-01 「安全なら強力発動で使う」,
the Rod of Detection): a me_powers row with a ``powerful`` condition is cast
as ``racial_key`` when that condition holds; ``pays_safely`` is the HP rule
(the worst cost, cost(level), leaves HP above the dungeon ladder's highest
low-HP threshold) and ``activatable`` names what such a key casts for the
executor (me_powerful_activation_input).

Rules: once a power is absorbed (``me_capability.has``) its scroll is never
bought or required (the ``me_capability.REPLACES`` rows of the *Identify* and
*Remove Curse* scrolls), and the town work it serves is this module's
``town_key``.  Only these two powers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import me_capability, me_powers
from hengbot.equipment_optimizer import AMMUNITION_TVALS, average_hides_modifiers, equipment_identity
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER, power_command_refused
from hengbot.model import (
    SV_STAFF_IDENTIFY, SV_STAFF_REMOVE_CURSE, item_requires_full_identification,
)
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY, REST_MACRO


REASON = "me-powerful"
RACIAL_KEY = "U"
MIN_LEVEL = 10           # class-racial-switcher.cpp rpi.min_level
MEMORY = "_me_powerful"
# Uses of one power on one item before it is given up (the owner's retry
# bound for absorbed powers, me_powers.FAILURES_PER_PLACE).
ATTEMPTS_PER_TARGET = me_powers.FAILURES_PER_PLACE


@dataclass(frozen=True)
class Effect:
    name: str
    sval: int                  # the absorbed staff power
    targeted: bool             # identify_fully asks for an item
    kind: str = "staff"

    @property
    def names(self) -> tuple[str, str]:
        """Its list name (the device policy table's BaseitemDefinitions name)."""
        return me_capability.names(self.kind, self.sval)

    @property
    def key(self) -> str:
        return racial_key(self.kind, self.sval)

    @property
    def reason(self) -> str:
        return f"{REASON}:{self.name}"


IDENTIFY = Effect("identify", SV_STAFF_IDENTIFY, True)
UNCURSE = Effect("uncurse", SV_STAFF_REMOVE_CURSE, False)
EFFECTS = (UNCURSE, IDENTIFY)
BY_SVAL = {effect.sval: effect for effect in EFFECTS}
BY_KEY = {(effect.kind, effect.sval): effect for effect in EFFECTS}


def racial_key(kind: str, sval: int) -> str:
    """``U``, the kind question's letter and the power's list letter."""
    return RACIAL_KEY + me_powers.KIND_LETTER[kind] + me_powers.encode_letter(sval)


def activatable(kind: str, sval: int) -> Effect | None:
    """What a Powerful Activation key casts: a town effect, or a me_powers row
    with a ``powerful`` condition (no aim: the racial stepper asks no direction)."""
    effect = BY_KEY.get((kind, sval))
    if effect is not None:
        return effect
    power = me_powers.BY_KEY.get((kind, sval))
    if power is None or power.powerful is None or power.aimed:
        return None
    return Effect(power.effect, sval, False, kind)


def cost(level: int) -> int:
    """class-racial-switcher.cpp: rpi.cost = 10 + (lvl - 10) / 2."""
    return 10 + (level - 10) // 2


def pays_safely(policy, snapshot) -> bool:
    """Level ``MIN_LEVEL`` and HP after the worst cost above every low-HP rung.

    racial_power_reduce_mana takes cost/2 + 1d(cost/2) <= cost(level)
    (cmd-action/cmd-racial.cpp:442).  The dungeon ladder's highest low-HP
    threshold is ``_low_hp_walk_threshold`` (max(50%, max - 300), the low-HP
    walk gate, survival_preemption and status_cure); strictly above it is
    also above the emergency return (<= 50%), heal/flee (40%) and panic (20%).
    """
    player = snapshot.player
    return (player.level >= MIN_LEVEL
            and player.hp - cost(player.level) > policy._low_hp_walk_threshold(player.max_hp))


@dataclass
class Memory:
    attempts: dict = field(default_factory=dict)   # (effect, signature) -> uses
    takes: dict = field(default_factory=dict)      # signature -> Home takes for *Identify*
    pending: tuple | None = None                    # (effect, signature, turn)


def _memory(policy) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Memory()
        setattr(policy, MEMORY, memory)
    return memory


# -- the town work --------------------------------------------------------------

def _uncurse_targets(policy, snapshot):
    permanent = getattr(policy, "_permanent_cursed_items", ())
    return (item for item in snapshot.equipment if item.is_cursed
            and policy._item_signature(item) not in permanent)


def _identify_targets(policy, snapshot):
    """Worn jewellery hiding its numbers, gear that needs *Identify*, then -
    with time to spare - carried gear the equipment transaction will shelve."""
    yield from (item for item in snapshot.equipment if average_hides_modifiers(item))
    yield from (item for item in (*snapshot.equipment, *snapshot.inventory)
                if item.known and not item.fully_known
                and item_requires_full_identification(item))
    if spare_identify_ready(policy, snapshot):
        yield from _planned_deposits(policy, snapshot)


def _planned_deposits(policy, snapshot):
    """Carried gear not fully known that the equipment transaction deposits.

    Owner 2026-11-06 「預ける前に＋自宅の品も — 預ける予定の装備は預ける前に
    *鑑定* する」: n1-c life-146 10:58 shelved the Q31 ring 22 s before the
    recall-read pass (``spare_identify_key``) began.  This town work runs
    before the transaction's walk to Home, so the piece is *identified* before
    it is deposited; without a charge or time to spare it is shelved as before.
    """
    plan = getattr(policy._equipment_transaction_session, "plan", None)
    planned = {action.item_identity for action in getattr(plan, "actions", ())
               if action.kind == "deposit"}
    return (item for item in snapshot.inventory
            if spare_identify_target(item) and equipment_identity(item) in planned)


def spare_identify_target(item) -> bool:
    """Gear not fully known (identify_fully's chooser: object_is_not_fully_identified).

    Owner: 「装備品とは武器防具だけではない」 - every equipment tval but plain
    ammunition.  lose_all_info (status/base-status.cpp) spares only a
    FULL_KNOWN item.
    """
    return (item.is_equipment and not item.fully_known
            and item.tval not in AMMUNITION_TVALS)


def _spare_identify_targets(policy, snapshot):
    return (item for item in (*snapshot.equipment, *snapshot.inventory)
            if spare_identify_target(item))


def spare_identify_ready(policy, snapshot) -> bool:
    """The town has time to spare for *Identify* (owner 2026-11-04 「余裕」).

    A safe town board with no hostile, the cost paid without reaching any
    low-HP rung (``pays_safely``), and an absorbed *Identify* with a charge.
    """
    return (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            and _safe(policy, snapshot) and not policy._physical_hostiles(snapshot)
            and pays_safely(policy, snapshot)
            and me_capability.has(policy, snapshot, IDENTIFY.kind, IDENTIFY.sval)
            and me_capability.charges(policy, snapshot, IDENTIFY.kind, IDENTIFY.sval) > 0)


TARGETS = {UNCURSE: _uncurse_targets, IDENTIFY: _identify_targets}


def _address(item) -> str:
    """The item chooser's answer: a pack letter, or '/' + an equipment letter."""
    slot = EQUIPMENT_SLOT_KEY.get(item.slot)
    return item.slot if slot is None else "/" + slot


def _first_open(policy, effect, targets):
    """The first target with uses left: a target that never lands is left behind."""
    memory = _memory(policy)
    for target in targets:
        signature = policy._item_signature(target)
        if memory.attempts.get((effect.name, signature), 0) < ATTEMPTS_PER_TARGET:
            return effect, target, signature
    return None


def _work(policy, snapshot):
    for effect in EFFECTS:
        if me_capability.has(policy, snapshot, effect.kind, effect.sval):
            work = _first_open(policy, effect, TARGETS[effect](policy, snapshot))
            if work is not None:
                return work
    return None


def _safe(policy, snapshot) -> bool:
    """Survival first: no hit this turn and no hostile beside the player."""
    player = snapshot.player
    return (snapshot.in_town and snapshot.store is None
            and not policy._physical_adjacent_hostiles(snapshot)
            and not getattr(policy, "_took_damage", False)
            and not (player.blind or player.confused or player.hallucinated
                     or player.paralyzed or power_command_refused(snapshot)))


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
    if me_capability.charges(policy, snapshot, effect.kind, effect.sval) <= 0:
        return None  # the absorbed power regenerates; nothing is bought
    if snapshot.player.hp <= cost(snapshot.player.level):
        return _rest_key(policy, snapshot, hostiles)
    return _use(policy, snapshot, effect, target, signature)


def _use(policy, snapshot, effect, target, signature) -> str:
    memory = _memory(policy)
    memory.attempts[(effect.name, signature)] = memory.attempts.get((effect.name, signature), 0) + 1
    memory.pending = (effect, signature, snapshot.turn)
    policy.last_reason = effect.reason
    return effect.key + (_address(target) if effect.targeted else "")


def spare_identify_key(policy, snapshot) -> str | None:
    """*Identify* one more piece of gear at the recall read, all town work done.

    Owner 2026-11-04 「魔道具術師の場合はLv.10以降街で余裕があるときに可能な限り
    全ての装備を*鑑定*しておきたい」.  The town's owners and its recovery come
    first; without an enemy, HP to pay or a charge the rest waits for the next
    visit and the read goes on.
    """
    if not spare_identify_ready(policy, snapshot):
        return None
    work = _first_open(policy, IDENTIFY, _spare_identify_targets(policy, snapshot))
    if work is not None:
        return _use(policy, snapshot, *work)
    return _home_take_key(policy, snapshot)


def _home_take_key(policy, snapshot) -> str | None:
    """Take one shelved piece of gear out for *Identify* (owner 2026-11-06).

    「自宅にある *鑑定* されていない装備も、町で余裕がある時に取り出して *鑑定*
    し、また仕舞う。」  Nothing is carried for *Identify* any more, so one Home
    piece not fully known is filed as the catalogue take Home identification
    already uses (home_identification); once carried, ``town_key`` *identifies*
    it and the deposit flow shelves it again.  Each piece is taken at most
    ``ATTEMPTS_PER_TARGET`` times, so a piece that never lands is left behind.
    """
    from hengbot import home_identification
    from hengbot.home_errand import HomeErrandRequest
    from hengbot.town_pack_budget import home_take_fits

    # A Memory restored from an older checkpoint has no ``takes`` yet.
    takes = _memory(policy).__dict__.setdefault("takes", {})
    errand = policy._home_errand
    if errand.active or policy._home_pending_batch:
        return None
    for owned in policy._equipment_catalog.items:
        item = owned.item
        signature = policy._item_signature(item)
        if (owned.origin != "home" or not spare_identify_target(item)
                or signature in policy._deferred_home_items
                or takes.get(signature, 0) >= ATTEMPTS_PER_TARGET
                or not home_take_fits(snapshot, item, 1)):
            continue
        if not policy._file_home_errand(
                snapshot, HomeErrandRequest(signature, 1, "home-catalog",
                                            home_identification.CATALOGUE_PURPOSE),
                knowledge_current=policy._home_knowledge_current):
            return None
        takes[signature] = takes.get(signature, 0) + 1
        policy._home_candidate_waiting = True
        return home_identification.rearmed_home_route_key(policy, snapshot)
    return None


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
