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
"""

from __future__ import annotations

from hengbot import me_absorbed_substitutes, me_capability
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_ROD_TELEPORT_AWAY, SV_WAND_TELEPORT_AWAY, TVAL_ROD, TVAL_WAND


AWAY_REASON = "emergency:teleport-follower:teleport-away"
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

