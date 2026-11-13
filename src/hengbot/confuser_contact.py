"""Leave a faster confuser before its blow lands (owner 2026-11-14 「混乱する前に離れるだけ」).

n1-b life-392 (2026-11-13 19:52, オークの洞窟19階, Lv20, no resist_conf): a
<スラーネッシュ>の女悪魔 (race 319, speed +10, two CLAW CONFUSE blows) stood two cells away
at full HP (turn 1124309) and the summoner shot (``summoner:ranged-kill``) traded a bolt with
it.  Its claws confused the player on that and every following board: a confused player
cannot read (cmd-read.cpp do_cmd_read_scroll: cmd_limit_confused) nor use an absorbed power
(cmd-magiceat.cpp: cmd_limit_confused), so the 13 Teleportation scrolls stayed unread, the
cure potions ran out and the character died there.

Owner 2026-11-14 (the question of that death, option C only): without resist_conf and not
yet confused, when a monster faster than the player (threat_projection.adjusted_speed, the
threat tiers' comparison) whose blows confuse can reach the player before its next action
(paralyzer_contact.in_contact, the game's energy arithmetic), read Teleportation to leave
instead of trading shots.  Once confused the current behaviour stands (the cures until they
run out, then the fight).  The leave is the player's own teleport and nothing else
(teleport_follower.teleport_means): the Teleportation scroll first, as the decision says, else
the absorbed Teleportation, else a carried Staff of Teleportation; with none the rungs below
answer as today.  *Destruction* is not a leave and is not asked here.  A Phase Door is no
substitute (owner 2026-11-02 「ショートテレポートはテレポートの代替にならない」).

The rung stands in the emergency layer after the paralyzer prevention: below the emergency
ladder (the 即死 board and the tiers' rules answer there first) and above the summoner shots.
"""

from __future__ import annotations

from hengbot import paralyzer_contact, teleport_follower
from hengbot.threat_escape import STAFF_REASON_SUFFIX
from hengbot.threat_projection import _with_adjusted_speed, adjusted_speed

REASON = "status-threat:confuser-leave"
STAFF_REASON = REASON + STAFF_REASON_SUFFIX
CONFUSE_EFFECT = "CONFUSE"


def confusers(policy, snapshot, hostiles) -> list:
    """The awake hostiles faster than the player whose confusing blow reaches it before its
    next action; none with resist_conf."""
    if "resist_conf" in snapshot.player.abilities:
        return []
    found = []
    for monster in hostiles:
        if monster.asleep or adjusted_speed(monster) <= snapshot.player.speed:
            continue
        knowledge = policy._monrace_knowledge.get(monster.race_id)
        if knowledge is None or "NEVER_BLOW" in knowledge.flags:
            continue
        if not any(blow.effect == CONFUSE_EFFECT for blow in knowledge.blows):
            continue
        if paralyzer_contact.in_contact(policy, snapshot, _with_adjusted_speed(monster)):
            found.append(monster)
    return found


def leave_key(policy, snapshot, hostiles) -> str | None:
    """The player's own teleport (``teleport_means``) before the confuser's blow, else None.

    Once confused none is asked: ``teleport_means`` refuses a confused player (cmd-read.cpp,
    cmd-magiceat.cpp:463), so the cures and the fight below stay as they are."""
    threats = confusers(policy, snapshot, hostiles)
    if not threats or policy._relocation_refused(snapshot):
        return None
    means = teleport_follower.teleport_means(policy, snapshot)
    if means is None:
        return None
    if means[0] == "scroll":
        policy.last_reason = REASON
        key = policy._read_key(snapshot, means[1])
    else:
        key = teleport_follower.device_teleport_key(policy, snapshot, means, REASON, STAFF_REASON)
    if key is not None:
        policy._declare_triggers(threats)
    return key
