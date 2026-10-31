"""Whether a latched town return owns the decision on a dungeon floor.

Death 1 (#47, n1-a life-446, 鉄獄48階 2026-10-31): the second emergency escape
latched the town return (emergency-repeat), but the immobile-summoner
avoidance runs before the return owner (_return_to_town_key) and kept
exploring and looting; 14 teleports later the last scroll was gone.  An owner
that only steers around a threat asks here before taking the decision.

D46 (n1-b life-279, Castle 22F 2026-10-31): on a breakthrough-latched floor
the same avoidance meleed the adjacent weak breeders (巨大ゴキブリ) from HP 333
to death; the breakthrough owner below it would have read Recall.
"""


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


def breeder_walkout_owns(policy, snapshot) -> bool:
    """The floor is latched as a breeder breakthrough (extermination proved
    impossible): its own exits -- Recall, the up-stairs route, the frontier
    through the swarm (_breeder_breakthrough_key) -- leave it."""
    return policy._breeder_breakthrough_floor == snapshot.floor_key
