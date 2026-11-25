"""Fixed-quest sweep: the mobile target the sweep closes on, kept across decisions.

After the opening hold, the placement sweep closes on one observed mobile
enemy (a721b9294).  Choosing it afresh on every board made the sweep walk
between two cells when each step swapped the view (輪1, #47, n1-a life-447
Q22: from [11,14] the sleeping captain at [14,6] was seen and chosen by
priority, from [11,13] only a black orc).  The chosen target is kept by race
and last-seen cell, the pattern of Q2's q2-breeder-recommit, until that cell
is confirmed empty, the floor changes or no route remains; the approved
priority_targets order still picks each new target.  A summoner of a higher
priority than the kept target replaces it when it comes into view (owner
2026-11-04 「召喚を受けたら本人を先に」): the choice moves one way, to a strictly
higher priority, and cannot swing back (n1-a life-538 Q32, 2026-11-26: the
sweep kept walking to a cloud giant's last-seen cell [6,4] -- the giant was
since killed at the hold -- with the plan's first target, the summoning
閾に棲む者, in view).  Any other target keeps the kept one (輪1: the sleeping
captain seen from one cell only does not take over from the black orc).

The hold's verdict is kept here too (``hold_kept``).  The sweep and the
retake of the hold read one verdict (_quest_strategy_may_leave_hold, #47),
but it was read afresh from each board's view: an awake enemy seen from the
sweep's step sends the player back toward the hold, and one step on the enemy
is out of view and the verdict sends the player back to the sweep.  n1-a
life-538 Q32 (2026-11-26 04:35, livelock-exhausted): グリッドバグ seen from
[17,6] and [18,6], not from [19,5] and [19,6]; ``retake-hold`` and
``sweep-engage-mobile`` alternated about 60 decisions before the stop.  The
retake is a step away for the enemies the board named, and the owner's rule
for a step away (2026-11-13 「離れたマスの共通の記録」: the reason is kept
until it is gone, the walkers do not step back while it holds) keeps the
verdict until those enemies are gone -- the retreat veto's lifetime
(retreat_veto_life: died, changed shape, or not shown for UNSEEN_GAME_TURNS;
owner 2026-11-06 「脅威が見えなくなったら消す」) -- or a board shows them and
allows leaving (fleeing, asleep and weak).
"""

from hengbot import retreat_veto_life
from hengbot.model import Position

COMMIT_ATTRIBUTE = "_quest_sweep_engage_commit"
HOLD_ATTRIBUTE = "_quest_hold_threats"


def engage_step(policy, snapshot, profile, mobile_targets) -> Position | None:
    """The route step toward the kept target, else toward a newly chosen one.

    A summoner in view of a higher priority than the kept target is chosen afresh (module
    docstring); the kept one stays while the new one has no route."""
    # The race's place in the plan's priority_targets (unlisted: after every listed race).
    places = {race_id: place for place, race_id in reversed(list(enumerate(profile.priority_targets)))}
    unlisted = len(profile.priority_targets)
    target = min(
        mobile_targets,
        key=lambda monster: (
            places.get(monster.race_id, unlisted),
            snapshot.player.position.distance_to(monster.position),
            monster.hp,
        ),
        default=None,
    )
    commit = getattr(policy, COMMIT_ATTRIBUTE, None)
    if (target is not None and target.can_summon and commit is not None
            and commit[0] == snapshot.floor_key
            and places.get(target.race_id, unlisted) < places.get(commit[1], unlisted)):
        step = policy._quest_strategy_route_step(snapshot, profile, target.position)
        if step is not None:
            setattr(policy, COMMIT_ATTRIBUTE,
                    (snapshot.floor_key, target.race_id, target.position))
            return step
    step = committed_step(policy, snapshot, profile, mobile_targets)
    if step is not None or target is None:
        return step
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


def hold_kept(policy, snapshot, denying, allowed) -> bool:
    """Whether the hold's verdict holds over this board (module docstring).

    ``denying``: the hostiles this board keeps the player at the hold for; ``allowed``: the
    hostiles this board lets him leave with.  The kept ones are tracked by the retreat veto's
    lifetime (retreat_veto_life ``claim``; its ``observe`` ends them each board); one an
    allowing board shows is released.  Returns True while any kept one is still there."""
    held = getattr(policy, HOLD_ATTRIBUTE, None)  # restored checkpoints predate it
    keys = set(held[1]) if held is not None and held[0] == snapshot.floor_key else set()
    keys -= {(monster.index, monster.race_id) for monster in allowed}
    if denying:
        retreat_veto_life.claim(policy, snapshot, (), tuple(denying))
        keys |= {(monster.index, monster.race_id) for monster in denying}
    life = getattr(policy, retreat_veto_life.MEMORY, None)
    keys &= set(life.threats) if life is not None else set()
    setattr(policy, HOLD_ATTRIBUTE, (snapshot.floor_key, frozenset(keys)) if keys else None)
    return bool(keys)
