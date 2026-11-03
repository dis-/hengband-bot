"""Whether a latched town return owns the decision on a dungeon floor.

Death 1 (#47, n1-a life-446, 鉄獄48階 2026-10-31): the second emergency escape
latched the town return (emergency-repeat), but the immobile-summoner
avoidance runs before the return owner (_return_to_town_key) and kept
exploring and looting; 14 teleports later the last scroll was gone.  An owner
that only steers around a threat asks here before taking the decision.

D46 (n1-b life-279, Castle 22F 2026-10-31): on a breakthrough-latched floor
the same avoidance meleed the adjacent weak breeders (巨大ゴキブリ) from HP 333
to death; the breakthrough owner below it would have read Recall.

Owner 2026-10-31 「隣に敵がいても譲る」: the yield also comes before the
avoidance's adjacent melee.  The generic melee rung of the ladder would take
that board ahead of the return owner, so the return owner is asked directly
(latched_return_key); it reads Recall, walks out or gives way.

n1-a life-475 (城49階, 2026-11-04 02:25): the second emergency teleport latched the
return and landed among sleeping undead with ten Recall scrolls.  It shot and
meleed them for 33 decisions, the room woke, and no Recall was read.  Owner
2026-11-04: 「隣に起きた敵がいない、は条件として弱い。視界内=攻撃を受ける範囲に起きた
敵がいない、くらいの条件は必要。」  With no awake hostile able to project at the
player, a latched emergency return reads Recall before any shot or blow
(``quiet_recall_key``); sleepers and monsters known only by detection do not count.
"""

from hengbot import once_quest_recall
from hengbot.town_hold import SURVIVAL_RETURN_TRIGGER_PREFIX


def latched_return_owns(policy, snapshot) -> bool:
    """A return is latched (or due) and Recall is not yet active.

    The return owner itself gives way on a locked one-shot quest floor
    (_return_exit_locked), so those floors keep their own owner.  While the
    recall counts down, avoidance keeps walking the player around the threat.
    """
    return (
        not snapshot.player.recalling
        and not policy._return_exit_locked(snapshot)
        and (policy._returning_to_town or policy._should_start_town_return(snapshot))
    )


def latched_return_key(policy, snapshot) -> str | None:
    """The return owner's key for a board a latched return owns.

    The same escape-state guard as the ladder's return rung: an escape owner
    other than the return keeps its decision.  None lets the ladder go on
    (the fight rungs answer the adjacent hostile).
    """
    if policy._escape_state.owner not in {None, "return"}:
        return None
    key = policy._return_to_town_key(snapshot, policy._strategic_hostiles(snapshot))
    if key is not None:
        policy._escape_state.enter("return", policy.last_reason)
    return key


def awake_hostile_in_view(policy, snapshot) -> bool:
    """An awake hostile on the board can attack the player from where it stands."""
    here = snapshot.player.position
    return any(
        monster.hostile and not monster.asleep
        and policy._may_project(snapshot, monster.position, here)
        for monster in snapshot.visible_monsters
    )


def quiet_recall_due(policy, snapshot) -> bool:
    """An emergency return is latched and no awake hostile is in view."""
    player = snapshot.player
    return (
        policy._returning_to_town
        and (policy._last_return_trigger or "").startswith(SURVIVAL_RETURN_TRIGGER_PREFIX)
        and not (player.blind or player.confused)
        and policy._escape_state.owner in {None, "return"}
        and latched_return_owns(policy, snapshot)
        and policy._find_recall_scroll(snapshot) is not None
        and not awake_hostile_in_view(policy, snapshot)
    )


def quiet_recall_key(policy, snapshot) -> str | None:
    """The Recall read of ``quiet_recall_due``; the one emergency read keeps its holds."""
    if not quiet_recall_due(policy, snapshot):
        return None
    return once_quest_recall.read_key(policy, snapshot, "return:recall")


def breeder_walkout_owns(policy, snapshot) -> bool:
    """The floor is latched as a breeder breakthrough (extermination proved
    impossible): its own exits -- Recall, the up-stairs route, the frontier
    through the swarm (_breeder_breakthrough_key) -- leave it."""
    return policy._breeder_breakthrough_floor == snapshot.floor_key
