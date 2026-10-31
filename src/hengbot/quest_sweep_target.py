"""Fixed-quest sweep: the mobile target the sweep closes on, kept across decisions.

After the opening hold, the placement sweep closes on one observed mobile
enemy (a721b9294).  Choosing it afresh on every board made the sweep walk
between two cells when each step swapped the view (輪1, #47, n1-a life-447
Q22: from [11,14] the sleeping captain at [14,6] was seen and chosen by
priority, from [11,13] only a black orc).  The chosen target is kept by race
and last-seen cell, the pattern of Q2's q2-breeder-recommit, until that cell
is confirmed empty, the floor changes or no route remains; the approved
priority_targets order still picks each new target.
"""

from hengbot.model import Position

COMMIT_ATTRIBUTE = "_quest_sweep_engage_commit"


def engage_step(policy, snapshot, profile, mobile_targets) -> Position | None:
    """The route step toward the kept target, else toward a newly chosen one."""
    step = committed_step(policy, snapshot, profile, mobile_targets)
    if step is not None or not mobile_targets:
        return step
    target = min(
        mobile_targets,
        key=lambda monster: (
            profile.priority_targets.index(monster.race_id)
            if monster.race_id in profile.priority_targets
            else len(profile.priority_targets),
            snapshot.player.position.distance_to(monster.position),
            monster.hp,
        ),
    )
    step = policy._quest_strategy_route_step(snapshot, profile, target.position)
    if step is not None:
        setattr(policy, COMMIT_ATTRIBUTE,
                (snapshot.floor_key, target.race_id, target.position))
    return step


def committed_step(policy, snapshot, profile, mobile_targets) -> Position | None:
    """The step toward the kept target, or None after releasing it."""
    commit = getattr(policy, COMMIT_ATTRIBUTE, None)
    if commit is None:
        return None
    floor_key, race_id, last_seen = commit
    same_race = [monster for monster in mobile_targets if monster.race_id == race_id]
    if floor_key != snapshot.floor_key or (
        not same_race and _confirmed_empty(policy, snapshot, last_seen)
    ):
        setattr(policy, COMMIT_ATTRIBUTE, None)
        return None
    if same_race:
        last_seen = min(
            same_race, key=lambda monster: monster.position.distance_to(last_seen)
        ).position
    step = policy._quest_strategy_route_step(snapshot, profile, last_seen)
    setattr(policy, COMMIT_ATTRIBUTE,
            None if step is None else (floor_key, race_id, last_seen))
    return step


def _confirmed_empty(policy, snapshot, position: Position) -> bool:
    grid = snapshot.grid_at(position)
    return (
        grid is not None and grid.known and not grid.has_monster
        and policy._quest_cell_confirmed_empty(snapshot, position)
    )
