"""Status treatment: Cure Critical Wounds (or Healing) for blindness, confusion, cuts.

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
"""

from hengbot import blind_strike, unseen_strike
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_LIFE,
    SV_POTION_STAR_HEALING,
)
from hengbot.policy_constants import REST_MACRO


SIGHT_RESTORED = frozenset({"やっと目が見えるようになった。", "You can see again."})
_PENDING = "_blind_cure_turn"         # (floor, turn) of the last blindness cure
_LATCH = "_blind_cure_futile_floor"   # floor whose current blindness is not cured
FIGHT_THROUGH_REASON = "blind:fight-through"
# Food states in which a long rest does not starve the player (the rest gate
# of the survival ladder uses the same three).
_REST_FOOD_STATES = frozenset({"normal", "full", "gorged"})
# A loss of at least 1/3 of max HP is heavy (the one line of owner 2026-11-04).
_HEAVY_LOSS_DIVISOR = 3
# Cheapest first.  Every one clears blindness: Healing and *Healing* are
# cure_critical_wounds(300 / 1200), Life is life_stream (quaff-effects.cpp:128-133,
# spells-status.cpp:289 and 397).
_HP_RECOVERY_CURES = (SV_POTION_HEALING, SV_POTION_STAR_HEALING, SV_POTION_LIFE)


def observe(policy, snapshot) -> None:
    """Latch the blindness when the board after a cure shows it again."""
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


def cure_futile(policy, snapshot) -> bool:
    """Whether this blindness came back right after a cure and its attacker
    can be fought instead (no cure for it): one remembered beside the player,
    or an unseen one whose melee blow landed on this board and a free
    neighbour to strike it in."""
    return (getattr(policy, _LATCH, None) == snapshot.floor_key
            and (bool(blind_strike.remembered_cells(policy, snapshot))
                 or unseen_strike.strike_cell(policy, snapshot,
                                              policy._physical_hostiles(snapshot)) is not None))


def fight_through_key(policy, snapshot) -> str | None:
    """Strike the attacker instead of the futile cure, else None."""
    player = snapshot.player
    if (not player.blind or player.afraid or not cure_futile(policy, snapshot)
            or player.hp < policy._low_hp_walk_threshold(player.max_hp)
            or not policy._can_fight_in_dungeon(snapshot.floor_key[0])):
        return None
    return (blind_strike.strike_key(policy, snapshot, FIGHT_THROUGH_REASON)
            or unseen_strike.key(policy, snapshot, policy._physical_hostiles(snapshot),
                                 FIGHT_THROUGH_REASON))


def treats(policy, snapshot, *, blind_only: bool = False) -> bool:
    """Whether the player has a status this module treats now."""
    player = snapshot.player
    blind = player.blind and not cure_futile(policy, snapshot)
    return blind or (not blind_only and (player.confused or player.cut))


def note_cure(policy, snapshot) -> None:
    """A status cure was chosen: remember a blindness cure for the next board."""
    if snapshot.player.blind:
        setattr(policy, _PENDING, (snapshot.floor_key, snapshot.turn))


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


def speed_first_key(policy, snapshot) -> str | None:
    """Blind from an unseen caster's heavy hit, not hasted: the Speed dose
    before the cure (the next decision cures).  None otherwise, and below the
    low-HP threshold with an HP recovery potion carried: that potion is first."""
    player = snapshot.player
    if (not player.blind
            or not _heavy_loss(policy._attributable_observed_loss(snapshot), player.max_hp)
            or (player.hp < policy._low_hp_walk_threshold(player.max_hp)
                and _hp_recovery_cure(policy, snapshot) is not None)):
        return None
    return unseen_strike.spell_speed_key(policy, snapshot)


def cure_potion(policy, snapshot):
    """The potion for the treated status: blind and heavily hurt, the cheapest
    carried HP recovery potion; otherwise the cheap cure first."""
    player = snapshot.player
    if player.blind and _heavy_loss(player.max_hp - player.hp, player.max_hp):
        if (potion := _hp_recovery_cure(policy, snapshot)) is not None:
            return potion
    return policy._find_status_cure_potion(snapshot)


def status_cure_key(policy, snapshot, *, blind_only: bool = False) -> str | None:
    """Quaff the status cure for the player's blindness (or any treated status),
    after the Speed dose a heavy unseen spell asks for."""
    if not treats(policy, snapshot, blind_only=blind_only):
        return None
    if (speed := speed_first_key(policy, snapshot)) is not None:
        return speed
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
