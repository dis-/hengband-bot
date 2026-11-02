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
there is nothing to fight and the cure stays as before.  Confusion and cuts
are still treated.
"""

from hengbot import blind_strike
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_POTION_CURE_CRITICAL
from hengbot.policy_constants import REST_MACRO


SIGHT_RESTORED = frozenset({"やっと目が見えるようになった。", "You can see again."})
_PENDING = "_blind_cure_turn"         # (floor, turn) of the last blindness cure
_LATCH = "_blind_cure_futile_floor"   # floor whose current blindness is not cured
FIGHT_THROUGH_REASON = "blind:fight-through"
# Food states in which a long rest does not starve the player (the rest gate
# of the survival ladder uses the same three).
_REST_FOOD_STATES = frozenset({"normal", "full", "gorged"})


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
    """Whether this blindness came back right after a cure and a remembered
    attacker beside the player can be fought instead (no cure for it)."""
    return (getattr(policy, _LATCH, None) == snapshot.floor_key
            and bool(blind_strike.remembered_cells(policy, snapshot)))


def fight_through_key(policy, snapshot) -> str | None:
    """Strike the remembered attacker instead of the futile cure, else None."""
    player = snapshot.player
    if (not player.blind or player.afraid or not cure_futile(policy, snapshot)
            or player.hp < policy._low_hp_walk_threshold(player.max_hp)
            or not policy._can_fight_in_dungeon(snapshot.floor_key[0])):
        return None
    return blind_strike.strike_key(policy, snapshot, FIGHT_THROUGH_REASON)


def treats(policy, snapshot, *, blind_only: bool = False) -> bool:
    """Whether the player has a status this module treats now."""
    player = snapshot.player
    blind = player.blind and not cure_futile(policy, snapshot)
    return blind or (not blind_only and (player.confused or player.cut))


def note_cure(policy, snapshot) -> None:
    """A status cure was chosen: remember a blindness cure for the next board."""
    if snapshot.player.blind:
        setattr(policy, _PENDING, (snapshot.floor_key, snapshot.turn))


def status_cure_key(policy, snapshot, *, blind_only: bool = False) -> str | None:
    """Quaff the status cure for the player's blindness (or any treated status)."""
    if not treats(policy, snapshot, blind_only=blind_only):
        return None
    potion = policy._find_status_cure_potion(snapshot)
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
