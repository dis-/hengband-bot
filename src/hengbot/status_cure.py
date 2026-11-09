"""Status treatment: Cure Critical Wounds (or Healing) for blindness, confusion, cuts.

A Magic-Eater casts its absorbed Cure Light Wounds for blindness before the
cheap cure potion (owner 2026-11-07, ``absorbed_cure_key``); a cast counts as
a cure for the re-blind latch below.

Cure Critical Wounds is status treatment, never an HP-response potion
(_find_status_cure_potion keeps it ahead of Healing).  Blindness also hides
every monster and forbids reading, so the unseen-attacker branch cures it
before walking (death 1, #47, n1-a life-446: blinded beside a dragon, it
stepped into the adjacent monster five times and drank the cure at HP 15).

Blinded again right after a cure (owner 2026-11-01, #47 D57, memory
d57-survival-answers-decision-20261101): 「基本的には今のまま。回復後即盲目に
なった場合は戦闘による状況打開を試みる。致命傷治癒はHP回復の効果に期待しない。
HPが減ったら体力回復かテレポート。」  n1-c life-084 (迷宮14階): a 充血アイ
(NEVER_MOVE, GAZE:BLIND) re-blinded it on the board right after each Cure
Critical Wounds -- the board showed the cure's 「やっと目が見えるようになった。」
(status/bad-status-setter.cpp:68) and the player blind again -- until all
nine were spent.  Such a board latches the blindness until the player sees
again or leaves the floor: while blind_strike remembers an attacker beside
the player no cure is drunk for it and ``fight_through_key`` strikes that
cell instead; below the low-HP threshold the survival ladders keep the turn
(Healing, a teleport, their own blind strike).  With no remembered attacker
the unseen attacker's melee blow on the board is struck back the way every
survival path answers it (unseen_strike, owner 2026-10-03 「近接で敵の方向が
分からなければランダムな方向に攻撃。」); with neither there is nothing to
fight and the cure stays as before.  n1-b life-299 (2026-11-03 01:26,
オークの洞窟19階): a ヴラスタ (BITE:BLIND x2) came out of the dark and
blinded it before any sighted board showed it, so nothing was remembered;
seven Cure Critical Wounds went on the blindness, each re-blinded by the
next bite.  Confusion and cuts are still treated.

The latch holds while the blow that re-blinded the player keeps landing.
n1-b life-306 (2026-11-04 01:54, 鉄獄19階): the ヴラスタ that re-blinded it died
on the third blind board; no bite landed again, yet the latch kept nine Cure
Critical Wounds and fifteen Teleport scrolls shut for 35 blind strikes, most at
empty air, from HP 378 to death under 赤オクタロック's crush and shots.  On a board
without that blow the cure is drunk as before; a new re-blinding latches again.

A heavy loss while blind (owner 2026-11-04): 「スピードの薬を先に飲む。加えて、
体力が減っているand盲目の状態では致命傷の治癒より体力回復の薬を優先して使用
する。」  n1-a life-474 (2026-11-03 21:39, 鉄獄49階): 何か's darkness storm
took HP 774 -> 505 and blinded it; it drank Cure Critical Wounds with three
Potions of Speed carried and the next two spells killed it.  An unseen caster's
heavy hit takes the Speed dose first (``speed_first_key``; a hasted player goes
straight to the cure), and a heavy total loss cures with the potion that also
restores HP (``cure_potion``).  Cure Critical Wounds is still no HP recovery:
this only reorders the blindness cures.  Below the low-HP threshold a carried
HP recovery potion goes before the Speed dose (owner 2026-11-04 「低い時は体力
回復が先」).

Confused again right after a cure, on the 即死 board (owner 2026-11-09, question D
of n1-b life-350: 「加速できていなければ加速を先に使う。HPが減っている時は体力回復を
優先。」).  迷宮15階: the アンバーハルク's gaze (GAZE:CONFUSE) confused the player
again on the board after each Cure Critical Wounds -- the board showed the cure's
「やっと混乱がおさまった。」 (status/bad-status-setter.cpp:147) and the player
confused -- and HP 196 went 168, 77, 23, dead, with two Potions of Healing
carried.  Confused, no scroll is read (cmd-read.cpp:37 cmd_limit_confused) and no
absorbed power cast (cmd-magiceat.cpp:463); a potion is quaffed (cmd-quaff.cpp and
ObjectQuaffEntity have no confusion refusal), so the Speed dose is the potion
(speed_dose.key: the absorbed Speed is refused while confused,
me_staff_sequence.cast_blocked).  Such a board latches the confusion
(``confusion_relapsed``) until the player is clear or leaves the floor.  There the
emergency ladder's cure (``instant_death``, threat tiers 3.1) takes the Speed dose
first when not hasted, and cures with the HP recovery potion when HP is down -- the
11-04 line of 「体力が減っている」 (a loss of at least 1/3 of max HP,
``_heavy_loss``); below the low-HP threshold with such a potion carried it goes
before the Speed dose, as for blindness (owner 2026-11-04 「低い時は体力回復が先」).
"""

from hengbot import blind_strike, me_absorbed_substitutes, me_capability, speed_dose, unseen_strike
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import power_command_refused
from hengbot.model import (
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_LIFE,
    SV_POTION_STAR_HEALING,
)
from hengbot.policy_constants import REST_MACRO


SIGHT_RESTORED = frozenset({"やっと目が見えるようになった。", "You can see again."})
# status/bad-status-setter.cpp:147 (set_confusion, the confusion ending).
CONFUSION_ENDED = frozenset({"やっと混乱がおさまった。", "You feel less confused now."})
_CONFUSION_PENDING = "_confusion_cure_turn"     # (floor, turn) of the last confusion cure
_CONFUSION_LATCH = "_confusion_relapse_floor"    # floor whose confusion came back after a cure
RELAPSE_SPEED_REASON = "emergency:reconfused-speed"
BLINDED = "目が見えなくなってしまった！"   # status/bad-status-setter.cpp set_blindness
_PENDING = "_blind_cure_turn"         # (floor, turn) of the last blindness cure
_LATCH = "_blind_cure_futile_floor"   # floor whose current blindness is not cured
_LATCH_BLOW = "_blind_cure_futile_blow"  # the blow text that re-blinded it, if named
_ATTACKER = "_blind_attacker_floor"   # floor whose unseen attacker no kill has followed
# monster-damage.cpp show_kill_message (also after 「せっかくだから」).
_KILL_ENDINGS = ("を殺した。", "を倒した。", "を葬り去った。")
FIGHT_THROUGH_REASON = "blind:fight-through"
# The absorbed Cure Light Wounds cast (absorbed_cure_key adds the cast suffix).
ABSORBED_CURE_REASON = "item:cure-light"
EMERGENCY_ABSORBED_CURE_REASON = "emergency:cure-light"
# Food states in which a long rest does not starve the player (the rest gate
# of the survival ladder uses the same three).
_REST_FOOD_STATES = frozenset({"normal", "full", "gorged"})
# A loss of at least 1/3 of max HP is heavy (the one line of owner 2026-11-04).
_HEAVY_LOSS_DIVISOR = 3
# Cheapest first.  Every one clears blindness: Healing and *Healing* are
# cure_critical_wounds(300 / 1200), Life is life_stream (quaff-effects.cpp:128-133,
# spells-status.cpp:289 and 397).
_HP_RECOVERY_CURES = (SV_POTION_HEALING, SV_POTION_STAR_HEALING, SV_POTION_LIFE)


def _observe_attacker(policy, snapshot) -> None:
    """Remember, per floor, an unseen attacker that hit the blind player and
    that no kill has followed (the board's messages in their order)."""
    player = snapshot.player
    if not player.blind or getattr(policy, _ATTACKER, None) not in (None, snapshot.floor_key):
        setattr(policy, _ATTACKER, None)
    if not player.blind:
        return
    for message in snapshot.messages:
        text = unseen_strike.message_text(message)
        if text.endswith(unseen_strike.JA_BLOW_ACTS) or (
                getattr(policy, "_took_damage", False) and policy._is_unseen_attack_message(text)):
            setattr(policy, _ATTACKER, snapshot.floor_key)
        elif text.endswith(_KILL_ENDINGS):
            setattr(policy, _ATTACKER, None)


def attacker_gone(policy, snapshot) -> bool:
    """No unseen attacker is left on this floor as far as the blind player
    knows: none hit it since it went blind, or a kill followed the last blow."""
    return getattr(policy, _ATTACKER, None) != snapshot.floor_key


def _observe_confusion(policy, snapshot) -> None:
    """Latch the confusion when the board after a cure shows it ended and back again."""
    player = snapshot.player
    if not player.confused or getattr(policy, _CONFUSION_LATCH, None) != snapshot.floor_key:
        setattr(policy, _CONFUSION_LATCH, None)
    pending = getattr(policy, _CONFUSION_PENDING, None)
    if pending is None or snapshot.turn <= pending[1]:
        return
    setattr(policy, _CONFUSION_PENDING, None)
    if (pending[0] == snapshot.floor_key and player.confused
            and any(message in CONFUSION_ENDED for message in snapshot.messages)):
        setattr(policy, _CONFUSION_LATCH, snapshot.floor_key)


def confusion_relapsed(policy, snapshot) -> bool:
    """Confused again on the board right after a confusion cure, on this floor."""
    return snapshot.player.confused and getattr(policy, _CONFUSION_LATCH, None) == snapshot.floor_key


def observe(policy, snapshot) -> None:
    """Latch the blindness when the board after a cure shows it again; the same
    for the confusion."""
    _observe_confusion(policy, snapshot)
    _observe_attacker(policy, snapshot)
    player = snapshot.player
    if not player.blind or getattr(policy, _LATCH, None) != snapshot.floor_key:
        setattr(policy, _LATCH, None)
    pending = getattr(policy, _PENDING, None)
    if pending is None or snapshot.turn <= pending[1]:
        return
    setattr(policy, _PENDING, None)
    if (pending[0] == snapshot.floor_key and player.blind
            and any(message in SIGHT_RESTORED for message in snapshot.messages)):
        setattr(policy, _LATCH, snapshot.floor_key)
        setattr(policy, _LATCH_BLOW, _blinding_blow(snapshot.messages))


def _blinding_blow(messages) -> str | None:
    """The blow text printed right before the blindness set in, else None."""
    for previous, message in zip(messages, messages[1:]):
        if message == BLINDED:
            return next((act for act in unseen_strike.JA_BLOW_ACTS
                         if previous.endswith(act)), None)
    return None


def _blinder_still_hitting(policy, snapshot) -> bool:
    """The re-blinding blow landed on this board.  No blow named is a blindness
    no blow set (a spell: n1-c life-171, 城65階, 皇帝『レイザーク』's darkness
    storm blinded it again right after the cure): nothing to fight through, so
    the cure is not futile."""
    blow = getattr(policy, _LATCH_BLOW, None)
    return blow is not None and any(
        unseen_strike.message_text(message).endswith(blow) for message in snapshot.messages)


def cure_futile(policy, snapshot) -> bool:
    """Whether this blindness came back right after a cure and its attacker
    can be fought instead (no cure for it): the blow that re-blinded the player
    still lands, and that attacker is remembered beside the player, or an
    unseen one whose melee blow landed on this board has a neighbour to
    strike it in (an unknown one counts while blind, unseen_strike).

    The blow is read from the board, not from an HP loss: n1-c life-156
    (2026-11-07 23:08, 迷宮12階) drank Cure Critical Wounds into five re-blinding
    ヴラスタ bites in a row because each cure's heal outweighed the bite (HP
    196 -> 207 -> 225 -> 229), so no HP loss showed a melee hit."""
    return (getattr(policy, _LATCH, None) == snapshot.floor_key
            and _blinder_still_hitting(policy, snapshot)
            and (bool(blind_strike.remembered_cells(policy, snapshot))
                 or unseen_strike.strike_cell(
                     policy, snapshot, policy._physical_hostiles(snapshot),
                     blow_landed=unseen_strike.blow_on_board(snapshot)) is not None))


def fight_through_key(policy, snapshot) -> str | None:
    """Strike the attacker instead of the futile cure, else None."""
    player = snapshot.player
    if (not player.blind or player.afraid or not cure_futile(policy, snapshot)
            or player.hp < policy._low_hp_walk_threshold(player.max_hp)
            or not policy._can_fight_in_dungeon(snapshot.floor_key[0])):
        return None
    return (blind_strike.strike_key(policy, snapshot, FIGHT_THROUGH_REASON)
            or unseen_strike.key(policy, snapshot, policy._physical_hostiles(snapshot),
                                 FIGHT_THROUGH_REASON,
                                 blow_landed=unseen_strike.blow_on_board(snapshot)))


def treats(policy, snapshot, *, blind_only: bool = False) -> bool:
    """Whether the player has a status this module treats now."""
    player = snapshot.player
    blind = player.blind and not cure_futile(policy, snapshot)
    return blind or (not blind_only and (player.confused or player.cut))


def note_cure(policy, snapshot) -> None:
    """A status cure was chosen: remember a blindness or confusion cure for the next board."""
    if snapshot.player.blind:
        setattr(policy, _PENDING, (snapshot.floor_key, snapshot.turn))
    if snapshot.player.confused:
        setattr(policy, _CONFUSION_PENDING, (snapshot.floor_key, snapshot.turn))


def low_hp_heal(policy, snapshot, hostiles, *, observed_loss):
    """Below the low-HP threshold, blind or confused: the heal-first potion.

    Owner 2026-11-01 (D57): 「致命傷治癒はHP回復の効果に期待しない。HPが減ったら
    体力回復かテレポート。」  A blind or confused player cannot read the
    teleport, so the heal-vs-teleport rule's potion (_low_hp_heal_first_potion,
    owner 2026-10-03) is drunk; every potion it chooses (Cure Serious,
    Healing, *Healing*, Life -- quaff-effects.cpp) also clears blindness and
    confusion (spells-status.cpp).  n1-c life-103 (2026-11-02 13:47,
    城42階): blind at HP 97/512 beside 濃尾無双『岩本虎眼』
    after a 291-HP round, it drank Cure Critical Wounds (6d8) with Healing
    carried and died two boards later.  None above the threshold, when the
    status does not block reading, or when no heal potion covers the
    next-turn damage: the cheap cure stays first.
    """
    player = snapshot.player
    if (not (player.blind or player.confused)
            or player.hp >= policy._low_hp_walk_threshold(player.max_hp)):
        return None
    return policy._low_hp_heal_first_potion(snapshot, hostiles, observed_loss=observed_loss)


def _heavy_loss(loss: int, max_hp: int) -> bool:
    return loss * _HEAVY_LOSS_DIVISOR >= max_hp


def _hp_recovery_cure(policy, snapshot):
    """The cheapest carried potion that restores HP and clears blindness."""
    for sval in _HP_RECOVERY_CURES:
        if (potion := policy._find_exact_potion(snapshot, sval)) is not None:
            return potion
    return None


def _relapse_on_instant_death(policy, snapshot, instant_death: bool) -> bool:
    """Owner 2026-11-09 D: confused again right after a cure, on the 即死 board."""
    return instant_death and confusion_relapsed(policy, snapshot)


def speed_first_key(policy, snapshot, *, instant_death: bool = False) -> str | None:
    """Blind from an unseen caster's heavy hit, not hasted: the Speed dose
    before the cure (the next decision cures).  Confused again right after a
    cure on the 即死 board (``instant_death``, owner 2026-11-09 D), not hasted:
    the same.  None otherwise, and below the low-HP threshold with an HP
    recovery potion carried: that potion is first."""
    player = snapshot.player
    if _relapse_on_instant_death(policy, snapshot, instant_death):
        if ((player.hp < policy._low_hp_walk_threshold(player.max_hp)
             and _hp_recovery_cure(policy, snapshot) is not None)
                or policy._player_hasted(snapshot)):
            return None
        return speed_dose.key(policy, snapshot, RELAPSE_SPEED_REASON)
    if (not player.blind
            or not _heavy_loss(policy._attributable_observed_loss(snapshot), player.max_hp)
            or (player.hp < policy._low_hp_walk_threshold(player.max_hp)
                and _hp_recovery_cure(policy, snapshot) is not None)):
        return None
    return unseen_strike.spell_speed_key(policy, snapshot)


def _hp_recovery_first(policy, snapshot, *, instant_death: bool = False) -> bool:
    """Blind and heavily hurt with an HP recovery potion carried: that potion
    is the cure (owner 2026-11-04); confused again right after a cure on the
    即死 board and heavily hurt, the same (owner 2026-11-09 D)."""
    player = snapshot.player
    return ((player.blind or _relapse_on_instant_death(policy, snapshot, instant_death))
            and _heavy_loss(player.max_hp - player.hp, player.max_hp)
            and _hp_recovery_cure(policy, snapshot) is not None)


def cure_potion(policy, snapshot, *, instant_death: bool = False):
    """The potion for the treated status: blind and heavily hurt, the cheapest
    carried HP recovery potion (also confused again on the 即死 board,
    ``instant_death``); otherwise the cheap cure first."""
    if _hp_recovery_first(policy, snapshot, instant_death=instant_death):
        return _hp_recovery_cure(policy, snapshot)
    return policy._find_status_cure_potion(snapshot)


def _absorbed_cure_castable(policy, snapshot) -> bool:
    """The Magic-Eater's absorbed Cure Light Wounds can clear this blindness now.

    cure_light_wounds sets blindness 0 (spell/spells-status.cpp), and the ``m``
    command refuses only confusion among the statuses (cmd-magiceat.cpp
    do_cmd_magic_eater; input-key-processor.cpp adds NO_MAGIC, anti-magic and
    berserk, magic_eater_devices.power_command_refused), so it is cast blind.
    Confusion, which it does not cure, is left to the potion."""
    player = snapshot.player
    power = me_absorbed_substitutes.CURE_LIGHT
    return (player.blind and not (player.confused or player.hallucinated or player.paralyzed)
            and snapshot.store is None and not power_command_refused(snapshot)
            and me_capability.has(policy, snapshot, *power)
            and me_capability.charges(policy, snapshot, *power) > 0)


def absorbed_cure_key(policy, snapshot, reason: str) -> str | None:
    """Blind: cast the absorbed Cure Light Wounds before a potion, else None.

    Owner 2026-11-07 「取り込んだ軽傷の治癒で盲目を治す。」  n1-c life-156
    (迷宮12階) drank its ten Cure Critical Wounds and its Healing into the
    ヴラスタ's bites with the staff's seven charges absorbed and never cast.
    It takes the cheap cure's place: a heavy loss still drinks the HP recovery
    potion first (``cure_potion``), and the callers keep the low-HP heal and
    the Speed dose ahead of it.  ``last_reason`` is ``reason`` with the cast
    suffix, which admits the device key (me_device_attacks_input)."""
    if _hp_recovery_first(policy, snapshot) or not _absorbed_cure_castable(policy, snapshot):
        return None
    policy.last_reason = reason + me_absorbed_substitutes.CAST_SUFFIX
    return me_absorbed_substitutes.POWERS[me_absorbed_substitutes.CURE_LIGHT].key


def blind_missile_supply_key(policy, snapshot, hostiles) -> str | None:
    """Blind with no cure, hit only by an unseen missile or spell, about to walk.

    Owner 2026-11-04: 「ダメージ量で判断し、通常加速や体力回復を使用する場面で使用。
    脅威度が低ければ歩いて離れる。」  The rules that normally spend these supplies judge
    the loss: the low-HP heal, the heavy spell's dose and the strong fight's dose.
    None lets the walk go on.  A melee blow is answered by unseen_strike instead.
    """
    if (not snapshot.player.blind or cure_potion(policy, snapshot) is not None
            or _absorbed_cure_castable(policy, snapshot)
            or unseen_strike.hit_in_melee(policy, snapshot)):
        return None
    loss = policy._attributable_observed_loss(snapshot)
    if loss <= 0:
        return None
    potion = low_hp_heal(policy, snapshot, hostiles, observed_loss=loss)
    if potion is not None:
        policy.last_reason = "item:heal"
        return reserved_item_command(policy, snapshot, "quaff", potion)
    return speed_first_key(policy, snapshot) or policy._strong_fight_speed_key(
        snapshot, hostiles, loss)


def status_cure_key(policy, snapshot, *, blind_only: bool = False) -> str | None:
    """Quaff the status cure for the player's blindness (or any treated status),
    after the Speed dose a heavy unseen spell asks for."""
    if not treats(policy, snapshot, blind_only=blind_only):
        return None
    if (speed := speed_first_key(policy, snapshot)) is not None:
        return speed
    if (cast := absorbed_cure_key(policy, snapshot, ABSORBED_CURE_REASON)) is not None:
        note_cure(policy, snapshot)
        return cast
    potion = cure_potion(policy, snapshot)
    if potion is None:
        return None
    policy.last_reason = (
        "item:cure-critical"
        if potion.sval == SV_POTION_CURE_CRITICAL
        else "item:cure-status-healing"
    )
    key = reserved_item_command(policy, snapshot, "quaff", potion)
    if key is not None:
        note_cure(policy, snapshot)
    return key


def wait_for_sight_key(policy, snapshot, reason: str, *, producer: str) -> str | None:
    """Rest out a blindness no carried cure treats before acting on the map.

    n1-b life-294 (2026-11-02 13:14, Yeek cave 1F): a gas trap blinded the
    mining warrior (trap.cpp TrapType::BLIND, 25-74 turns) with no Cure
    Critical Wounds carried.  A blind player's map is not updated, so the
    floor work went on against the board from before the blindness: it dug
    a vein it had already dug (cmd-tunnel.cpp 「そこは掘れない。」, no turn
    spent, a stalled command), stepped back onto the trap (blinded again),
    and waited with '5' at one cell until the cell guard stopped it.
    ``R&`` rests until ``is_fully_healthy`` (player-processor.cpp), which
    includes sight.  The survival rungs run before this (a carried cure is
    quaffed, an unseen attacker is struck); when something hits or is in
    sight, or the player is too hungry to rest, nothing is returned.
    """
    player = snapshot.player
    if (not player.blind or snapshot.dungeon_level < 1
            or getattr(policy, "_took_damage", False)
            or policy._physical_hostiles(snapshot)
            or player.food_state not in _REST_FOOD_STATES):
        return None
    policy.last_reason = reason
    policy._offer_execution(
        REST_MACRO, producer=producer, work_id=reason,
        next_step="player.rest", expected_effect="sight-restored",
    )
    return REST_MACRO
