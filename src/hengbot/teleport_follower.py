"""A monster beside the player that follows the player's teleport (n1-a life-500, 2026-11-09).

Owner 2026-11-09, verbatim: 「*破壊*>テレポートアウェイ>戦闘　の順で対処」.

Game (C:/hengband/src): ``teleport_player`` (spell-kind/spells-teleport.cpp:383-411) moves the
player, then every monster that stood in the 3x3 around the player's old cell, is not ridden,
has the TPORT ability, lacks RESIST_TELEPORT and is awake is teleported next to the player
(``teleport_monster_to``).  Phase Door is the same function with distance 10
(object-use/read/scroll-read-executor.cpp:141), the Teleportation scroll distance 100 (:145), the
Staff of Teleportation 100 (cmd-item/cmd-usestaff.cpp:102, the absorbed staff casts it too), so
every one of them is followed.  Teleport Level (``teleport_level``) and Word of Recall leave the
floor and are not followed.  n1-a life-500 (warrior Lv45, オークの洞窟23階): 禁断の護り手 (TPORT,
no RES_TELE, speed +20, a blinding blow) was beside the player at both Teleportation reads and
stood beside it again on each landing; it died with a Wand of Teleport Other (11 charges) unused.

While such a monster (a *follower*) is adjacent, no player teleport counts as an escape: the
finders every rung reads one through answer None (policy ``_escape_scroll``,
threat_tiers ``escape_means`` / ``blind_teleport_means``), so a rung falls to its next answer.
The emergency ladder answers in the owner's order (``response_key``): *Destruction* by its own
rules (destruction_use: a fixed quest floor and a guardian in the circle refuse it; blindness
does not), then Teleport Other aimed at the follower (``away_key``), then the fight.  Teleport
Other always moves a follower: effect_monster_away_resist (effect/effect-monster-evil.cpp:7-30)
resists only for RES_TELE, which a follower lacks by definition.  A wand or a rod is zapped
blind (zapwand-execution.cpp:122-129 ``check_can_zap`` refuses only the time stop and the stun;
zaprod-execution.cpp:146 the same); confused, the aim is random (get_aim_dir), so none is used
then; the absorbed power is cast blind as the ``m`` command allows (``blind_castable``) and
refused while confused (cmd-magiceat.cpp:463).  Once no follower is adjacent the teleports count
again.

A pack (owner 2026-11-12, n1-c life-201, verbatim): 「*破壊*前にテレポート追尾の群れに踏み込むのは
レアケース。対応を個別に決めるのであれば、テレポート追尾が3体以上で致死的なときは破壊の次にテレポートを
優先して試す。テレポートすることによって数が減ることが見込めるためである。」  ``teleport_monster_to``
(spells-teleport.cpp:192-201) moves each adjacent follower only when ``randint1(100) <= power``, and
``teleport_player`` passes the race level as the power (:407): a Lv37 ウィル・オー・ウィスプ comes
along 37 times in 100, so a teleport leaves most of a pack behind, where Teleport Other removes one
a turn.  n1-c life-201 (Magic-Eater Lv31, 鉄獄30階): a Teleportation read landed among 13 of them
(race 582: Lv37, speed +20, TPORT, PASS_WALL); the absorbed Teleport Other sent one away a turn
(decisions 24281-24286) while the others closed in, and it died with 13 Teleportation scrolls.
With ``PACK_MIN`` or more followers engaged (``pack``) on a lethal board the emergency ladder
answers *Destruction*, then the teleport itself (``pack_teleport_key``: the scroll, the absorbed
Teleportation, the carried staff), then Teleport Other and the fight as before; with fewer the
11-09 order stands.

Followers that cannot kill alone (owner 2026-11-14, n1-a life-522, verbatim): 「付いてくる敵だけで
死なないなら読む」.  n1-a life-522 (warrior Lv40, 49階): 魔王『マレキス』 (race 628: Lv47, TPORT, no
RES_TELE) stood beside the player while 迷路の神『アイホート』 and three ショゴス (RES_TELE) closed
in; the 即死 board kept the 14 Teleportation scrolls unread (a follower was beside it) and, with
no *Destruction* and no Teleport Other carried, quaffed Cure Light Wounds three times and died.
On the 即死 board (``instant_death``) with fewer than ``PACK_MIN`` followers engaged, when the
followers' own next-action p95 (instant_death.instant_death read on them alone: whatever comes
along is at worst all of them) stays below the HP (``survivable_due``), the pack rung's teleport
(``pack_teleport_key`` with ``SURVIVABLE_REASON``) goes after *Destruction* and before Teleport
Other: the followers come along with their level in percent, every other monster stays behind.
"""

from __future__ import annotations

from hengbot import me_absorbed_substitutes, me_capability, quest_no_teleport
from hengbot.instant_death import instant_death
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    SV_ROD_TELEPORT_AWAY, SV_STAFF_TELEPORTATION, SV_WAND_TELEPORT_AWAY, TVAL_ROD, TVAL_STAFF,
    TVAL_WAND,
)
from hengbot.policy_constants import speed_energy


AWAY_REASON = "emergency:teleport-follower:teleport-away"
# The same Teleport Other at a faster blinder beside a blind player (status_cure.outpacing_blinders).
BLINDER_REASON = "emergency:blinder:teleport-away"
# The absorbed rod, then the absorbed wand, then the carried rod, then the carried wand: the
# absorbed power first (destruction_use, speed_dose), the rod before the wand (it recharges,
# me_powers' Teleport Away rows).
ABSORBED = me_absorbed_substitutes.TELEPORT_AWAY
CARRIED = (("rod", TVAL_ROD, SV_ROD_TELEPORT_AWAY), ("wand", TVAL_WAND, SV_WAND_TELEPORT_AWAY))


def follows(policy, monster) -> bool:
    """``teleport_player``'s test on one monster's race: TPORT, no RESIST_TELEPORT, awake."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return (knowledge is not None and not monster.asleep
            and "TPORT" in knowledge.abilities and "RES_TELE" not in knowledge.flags)


def adjacent(snapshot) -> list:
    """The hostiles shown in the 3x3 around the player."""
    here = snapshot.player.position
    return [monster for monster in snapshot.visible_monsters
            if monster.hostile and monster.position != here
            and max(abs(monster.position.y - here.y), abs(monster.position.x - here.x)) <= 1]


def followers(policy, snapshot) -> list:
    """The adjacent monsters a teleport read now would bring along."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        return []
    return [monster for monster in adjacent(snapshot) if follows(policy, monster)]


def followed(policy, snapshot) -> bool:
    return bool(followers(policy, snapshot))


# Owner 2026-11-12 「テレポート追尾が3体以上で致死的なとき」.
PACK_MIN = 3
PACK_REASON = "emergency:teleport-follower:pack-teleport"


def pack(policy, snapshot) -> list:
    """The followers engaged now: the adjacent ones (``followers``), and every other awake
    follower in view that stands beside the player before its next action (its moves per player
    action, at the exported haste / slowness, cover the distance less one, and it can close).
    The pack's members move between the boards (n1-c life-201: 2 to 4 of 13 adjacent, the rest
    1-2 moves off), so the adjacent count alone undercounts it."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        return []
    here = snapshot.player.position
    player_energy = max(1, speed_energy(snapshot.player.speed))
    engaged = []
    for monster in snapshot.visible_monsters:
        if not monster.hostile or monster.position == here or not follows(policy, monster):
            continue
        distance = max(abs(monster.position.y - here.y), abs(monster.position.x - here.x))
        if distance > 1:
            speed = monster.speed + (10 if monster.fast else 0) - (10 if monster.slow else 0)
            moves = speed_energy(speed) // player_energy
            if distance - 1 > moves or not policy._monster_can_approach(snapshot, monster):
                continue
        engaged.append(monster)
    return engaged


def pack_due(policy, snapshot) -> bool:
    """``PACK_MIN`` or more followers engaged, one of them adjacent (else nothing follows)."""
    return followed(policy, snapshot) and len(pack(policy, snapshot)) >= PACK_MIN


# Owner 2026-11-14 「付いてくる敵だけで死なないなら読む」.
SURVIVABLE_REASON = "emergency:teleport-follower:survivable-teleport"


def survivable_due(policy, snapshot) -> bool:
    """Followers adjacent whose own next-action p95 (the 即死 test read on them alone) stays
    below the HP: a teleport that brings every one of them along does not die to them."""
    chosen = followers(policy, snapshot)
    return bool(chosen) and not instant_death(policy, snapshot, chosen).next_action


def pack_teleport_means(policy, snapshot):
    """The teleport the pack rung uses: ``teleport_means`` read beside the followers."""
    return teleport_means(policy, snapshot, beside_followers=True)


def teleport_means(policy, snapshot, *, beside_followers=False):
    """The player's own teleport: ("scroll", item) when the ladder's teleport scroll can be
    read (``_escape_scroll``'s rules: Teleportation, else Teleport Level, which leaves the floor
    and is followed by none; Phase Door excluded: its 10 cells keep a pursuer in reach), else
    ("absorbed", None) for the absorbed Teleportation (cast blind too, refused confused:
    cmd-magiceat.cpp:463), else ("staff", item) for a carried Staff of Teleportation
    (threat_escape.blind_teleport_means' order); None when none can be used here.  No rod
    teleports the player (sv-rod-types.h: only Teleport Other).  ``beside_followers``: the pack
    rung teleports beside followers anyway; every other caller gets None while one is adjacent
    (``followed``), as ``_escape_scroll`` answers."""
    if (snapshot.store is not None or quest_no_teleport.forbids(policy, snapshot)):
        return None
    scroll = policy._escape_scroll(snapshot, teleport_only=True, beside_followers=beside_followers)
    if scroll is not None:
        return "scroll", scroll
    player = snapshot.player
    if (player.confused or policy._teleport_blocked_by_equipment(snapshot)
            or (not beside_followers and followed(policy, snapshot))):
        return None
    power = me_absorbed_substitutes.TELEPORTATION
    if (not quest_no_teleport.forbids_absorbed(policy, snapshot)
            and me_absorbed_substitutes.cast_key(
                policy, snapshot, me_absorbed_substitutes.POWERS[power], blind_ok=True) is not None):
        return "absorbed", None
    staff = next((item for item in snapshot.inventory
                  if item.tval == TVAL_STAFF and item.sval == SV_STAFF_TELEPORTATION
                  and item.aware and item.charges > 0), None)
    return None if staff is None else ("staff", staff)


def pack_teleport_key(policy, snapshot, reason: str = PACK_REASON) -> str | None:
    """The teleport of ``pack_teleport_means`` as an emergency escape (counted at the read like
    the ladder's own: reasons.EMERGENCY, ``_latch_repeat_emergency_return``), else None.
    ``reason``: ``PACK_REASON`` for the pack, ``SURVIVABLE_REASON`` for ``survivable_due``; the
    carried staff's use carries the ``-staff`` suffix (threat_escape.STAFF_REASON_SUFFIX's form),
    the absorbed cast the cast suffix."""
    means = pack_teleport_means(policy, snapshot)
    if means is None:
        return None
    if means[0] == "scroll":
        return policy._issue_emergency_consumable(snapshot, means[1], reason)
    key = device_teleport_key(policy, snapshot, means, reason, reason + "-staff")
    if key is None:
        return None
    policy._emergency_return_active = True
    policy._latch_repeat_emergency_return(snapshot, policy.last_reason)
    return key


def device_teleport_key(policy, snapshot, means, reason: str, staff_reason: str) -> str | None:
    """The cast of the absorbed Teleportation (``reason`` + the cast suffix, the owner
    me_device_attacks_input answers the power prompt for) or the use of the carried staff
    (``staff_reason``) of a ``teleport_means`` answer other than the scroll, setting
    ``last_reason``; None when its key cannot be composed.  The 50F+ rule's substitute
    (deep_teleport) answers in the teleport's place where it refuses it."""
    from hengbot import deep_teleport

    if (instead := deep_teleport.substitute(policy, snapshot)) is not None:
        return instead
    kind, item = means
    if kind == "absorbed":
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        key = me_absorbed_substitutes.cast_key(policy, snapshot, power, blind_ok=True)
        reason = reason + me_absorbed_substitutes.CAST_SUFFIX
    else:
        key = reserved_item_command(policy, snapshot, "staff", item)
        reason = staff_reason
    if key is None:
        return None
    policy.last_reason = reason
    return key


def _aim_ready(snapshot) -> bool:
    player = snapshot.player
    return not (player.confused or player.hallucinated or player.paralyzed
                or snapshot.inside_arena or snapshot.store is not None)


def _target(policy, snapshot, chosen):
    """The follower that hurts most on the next turn (destruction_use's measure)."""
    here = snapshot.player.position
    return max(chosen, key=lambda monster: (policy._predicted_damage(snapshot, [monster], turns=1),
                                            -here.distance_to(monster.position), -monster.index))


def _absorbed(policy, snapshot):
    for ident in ABSORBED:
        if (me_capability.has(policy, snapshot, *ident)
                and me_capability.charges(policy, snapshot, *ident) > 0):
            return ident
    return None


def _carried(snapshot):
    for kind, tval, sval in CARRIED:
        item = next((item for item in snapshot.inventory
                     if item.tval == tval and item.sval == sval and item.aware
                     and (item.charges > 0 if kind == "wand" else not item.charging)), None)
        if item is not None:
            return kind, item
    return None


def away_usable(policy, snapshot) -> bool:
    """A Teleport Other could be aimed now (no state is changed)."""
    if not _aim_ready(snapshot):
        return False
    absorbed = _absorbed(policy, snapshot)
    if absorbed is not None and me_absorbed_substitutes.cast_key(
            policy, snapshot, me_absorbed_substitutes.POWERS[absorbed], "1", blind_ok=True):
        return True
    return _carried(snapshot) is not None


def away_key(policy, snapshot, chosen, reason: str = AWAY_REASON) -> str | None:
    """Teleport Other aimed at the worst of ``chosen`` (adjacent), else None."""
    if not chosen or not _aim_ready(snapshot):
        return None
    target = _target(policy, snapshot, chosen)
    direction = policy._direction_key(snapshot.player.position, target.position)
    absorbed = _absorbed(policy, snapshot)
    if absorbed is not None:
        key = me_absorbed_substitutes.cast_key(
            policy, snapshot, me_absorbed_substitutes.POWERS[absorbed], direction, blind_ok=True)
        if key is not None:
            policy.last_reason = reason + me_absorbed_substitutes.CAST_SUFFIX
            _remember_sent(policy, snapshot, target)
            return key
    carried = _carried(snapshot)
    if carried is None:
        return None
    kind, item = carried
    key = reserved_item_command(policy, snapshot, kind, item, suffix=direction)
    if key is not None:
        policy.last_reason = reason
        _remember_sent(policy, snapshot, target)
    return key


def _remember_sent(policy, snapshot, target) -> None:
    # Owner 2026-11-09 E: a T1 sent away outside quests returns to town (sent_away_t1).
    from hengbot import sent_away_t1

    sent_away_t1.remember(policy, snapshot, target)

