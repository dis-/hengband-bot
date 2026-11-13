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
run out, then the fight).  *Destruction* comes first where the existing order already puts it
(destruction_use.key, as the paralyzer and status-threat rungs ask it before their scroll).
A Phase Door is no substitute (owner 2026-11-02 「ショートテレポートはテレポートの代替にならない」).

The rung stands in the emergency layer after the paralyzer prevention: below the emergency
ladder (the 即死 board and the tiers' rules answer there first) and above the summoner shots.
"""

from __future__ import annotations

from hengbot import destruction_use, paralyzer_contact, quest_no_teleport
from hengbot.threat_projection import _with_adjusted_speed, adjusted_speed

REASON = "status-threat:confuser-leave"
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
    """*Destruction* where it comes first, else Teleportation, before the confuser's blow.

    Once confused neither is asked here: destruction_use refuses a confused player
    (``_clear_headed``) and ``_escape_scroll`` a confused or blind one (cmd-read.cpp), so the
    cures and the fight below stay as they are.  Blind, *Destruction* is still used (owner
    2026-11-08 「盲目でも使う」, as the status-threat rung does)."""
    threats = confusers(policy, snapshot, hostiles)
    if not threats:
        return None
    if (used := destruction_use.key(policy, snapshot)) is not None:
        policy._declare_triggers(threats)
        return used
    if quest_no_teleport.forbids(policy, snapshot) or policy._relocation_refused(snapshot):
        return None
    scroll = policy._escape_scroll(snapshot, teleport_only=True)
    if scroll is None:
        return None
    policy.last_reason = REASON
    policy._declare_triggers(threats)
    return policy._read_key(snapshot, scroll)
