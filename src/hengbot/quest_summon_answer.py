"""A room-sweep floor that answers each summon received itself: ``room_sweep.summon_answer``.

QUEST_33 (クローン地獄), owner 2026-11-19 (verbatim): 「召喚を受ける機会が多いクエストである。召喚を何度
受けても放棄しない。即死はテレポートで離脱。即死でなく、次の一行動で召喚主を倒す見込みがあるなら戦闘。
無理なら離脱。離脱後の作戦は別途用意すること。」

``summon_answer: "kill_or_disengage"`` on a ``room_sweep`` plan:

* No abandonment for summons (``never_abandons``): summon_response's rule 3 (three summons from
  casters in line of fire on one floor read Recall, owner 2026-11-04 / 2026-11-16) does not read
  Recall on such a floor.  QUEST_33's own abort for its sides summoning at each other
  (quest_alignment_split ``facing_casts_to_abort``) is no longer in its data.  The floor is still
  left by the plan's other lines (the teleport-scroll floor, the exit with no Healing left): those
  are about supplies and HP, not about summons.
* A summon received (summon_response ``summoners_at_player``: a named caster in view whose cast
  had a line of fire to the player on this board; the one reader of summon messages):

  1. 即死 (threat_tiers ``instant_death``, the next player action's p95 against the HP): a Scroll
     of Teleportation.  Without one the plan's own 即死 rung right after answers (its escape, then
     the emergency ladder).
  2. Else, a summoner the next one player action kills (attack_expectation's expected damage per
     player action against its board HP: ``melee`` beside the player, else ``ranged_against``,
     the larger of the launcher and the devices): that blow or shot.  "One action" is one player
     action (100 energy), as attack_expectation reads it today; the per-10-game-turn rework
     (2026-11-19, attack-per-10gt-1119) keeps the per-action figures, and this rule reads those.
  3. Else disengage: a walk of at most ``DISENGAGE_WALK_STEPS`` to the nearest cell no awake
     hostile on the board (the summoner and its summons) has a line to; else a Scroll of
     Teleportation; else the longer walk.  The walk is held over the next boards (``walk_key``)
     until the player stands out of their lines, at most ``DISENGAGE_WALK_LIMIT`` steps, then a
     scroll.  The battle state is ``navigator.summon_state``: ``disengaging`` while walking,
     ``disengaged`` once out (after a teleport at once).

What follows the disengage is not decided yet (「離脱後の作戦は別途用意すること」): the plan goes on
as before from the cell reached, and the state is left for that plan to read.  The lines are the
game's (quest_alignment_split's sight map: the pits and lavas pass a line, a tree and a closed
door do not).
"""

from __future__ import annotations

from hengbot import (
    attack_expectation,
    combat_answer,
    quest_alignment_split,
    quest_exposure,
    quest_no_teleport,
    quest_plan_base,
    summon_response,
    threat_tiers,
)
from hengbot.model import Position

FIELD = "summon_answer"
KILL_OR_DISENGAGE = "kill_or_disengage"
DISENGAGING = "disengaging"
DISENGAGED = "disengaged"
TELEPORT_REASON = "quest-strategy:summoned-teleport"
STRIKE_REASON = "quest-strategy:summoned-strike"
DISENGAGE_TELEPORT_REASON = "quest-strategy:summoned-disengage-teleport"
DISENGAGE_WALK_REASON = "quest-strategy:summoned-disengage-walk"
# A walk this short is taken before a scroll: a teleport on this floor lands among sleeping clones
# and summoners of both sides (quest_alignment_split), a walk keeps the plan's map.  Three steps:
# the Queen at +10 against a hasted player (+10) acts once a player action, so at most three of
# her casts land before the player is out of her line.
DISENGAGE_WALK_STEPS = 3
# The longest walk held before the scroll is read in its place.
DISENGAGE_WALK_LIMIT = 10
# The cells looked at for a way out of the lines: game distance from the player.
_SEARCH_RADIUS = DISENGAGE_WALK_LIMIT


def answers(plan) -> bool:
    return isinstance(plan, dict) and plan.get(FIELD) == KILL_OR_DISENGAGE


def valid(value) -> bool:
    """The schema (quest_strategies reads it at load)."""
    return value == KILL_OR_DISENGAGE


def _plan(policy, snapshot):
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    return None if profile is None else profile.engagement_plan.get("room_sweep")


def never_abandons(policy, snapshot) -> bool:
    """This floor's plan answers each summon itself and never leaves for summons."""
    return answers(_plan(policy, snapshot))


# -- the lines --------------------------------------------------------------------------


def _watchers(snapshot) -> list:
    """The summoner and its summons: every awake hostile on the board."""
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile and not monster.asleep]


def _seen_from(sight, watchers, cell) -> bool:
    return any(quest_exposure.projectable(sight, (monster.position.y, monster.position.x), cell)
               for monster in watchers)


def _out_of_sight(policy, snapshot, navigator, watchers) -> set[Position]:
    """The ground near the player no watcher has a line to, none of it beside a watcher."""
    sight = quest_alignment_split._sight(navigator, snapshot)
    here = (snapshot.player.position.y, snapshot.player.position.x)
    walkable = quest_plan_base._terrain_of(navigator, snapshot, water=False)
    found = set()
    for cell, kind in walkable.items():
        if (kind not in {"floor", "passage"} or quest_exposure.game_distance(here, cell) > _SEARCH_RADIUS
                or any(quest_exposure.game_distance(cell, (m.position.y, m.position.x)) <= 1
                       for m in watchers)):
            continue
        if not _seen_from(sight, watchers, cell):
            found.add(Position(*cell))
    return found


def _out_of_lines(snapshot, navigator, watchers) -> bool:
    here = (snapshot.player.position.y, snapshot.player.position.x)
    return not _seen_from(quest_alignment_split._sight(navigator, snapshot), watchers, here)


# -- the answers ------------------------------------------------------------------------


def _teleport(policy, snapshot, navigator, reason) -> str | None:
    if quest_no_teleport.forbids(policy, snapshot) or not policy._can_read_scrolls(snapshot):
        return None
    scroll = policy._find_teleport_scroll(snapshot)
    if scroll is None:
        return None
    navigator.summon_state = DISENGAGED
    navigator.summon_walk = 0
    policy.last_reason = reason
    return policy._read_key(snapshot, scroll)


def next_action_kills(policy, snapshot, target) -> bool:
    """The next player action's expected damage reaches the summoner's HP on the board."""
    distance = snapshot.player.position.distance_to(target.position)
    if distance <= 1:
        figure = attack_expectation.melee(policy, snapshot, target)
    else:
        figure = attack_expectation.ranged_against(policy, snapshot, target.race_id, distance)
    return figure > 0 and figure >= max(target.hp, 1)


def _strike(policy, snapshot, target) -> str | None:
    if snapshot.player.position.distance_to(target.position) <= 1:
        answer = combat_answer.adjacent_attack(policy, snapshot, [target], STRIKE_REASON)
        return None if answer is None else answer.key
    return quest_plan_base._shot(policy, snapshot, target)


def _walk(policy, snapshot, navigator, plan, board, *, limit=None) -> str | None:
    """A step toward the nearest cell out of the watchers' lines, within ``limit`` steps."""
    from hengbot import quest_room_sweep  # it asks this module for its rungs

    goals = _out_of_sight(policy, snapshot, navigator, _watchers(snapshot))
    if not goals:
        return None
    path = quest_room_sweep._path(policy, navigator, plan, snapshot, goals, board.occupied)
    if not path or (limit is not None and len(path) - 1 > limit):
        return None
    key = quest_plan_base._path_step(policy, snapshot, path, DISENGAGE_WALK_REASON)
    if key is not None:
        navigator.summon_state = DISENGAGING
        navigator.summon_walk += 1
    return key


def _disengage(policy, snapshot, navigator, plan, board) -> str | None:
    navigator.summon_walk = 0
    return (_walk(policy, snapshot, navigator, plan, board, limit=DISENGAGE_WALK_STEPS)
            or _teleport(policy, snapshot, navigator, DISENGAGE_TELEPORT_REASON)
            or _walk(policy, snapshot, navigator, plan, board))


def key(policy, snapshot, navigator, plan, board) -> str | None:
    """The board of a summon received: teleport on 即死, else the killing action, else disengage."""
    if not answers(plan):
        return None
    summoners = summon_response.summoners_at_player(policy, snapshot)
    if not summoners:
        return None
    if threat_tiers.instant_death(policy, snapshot).holds:
        return _teleport(policy, snapshot, navigator, TELEPORT_REASON)
    for target in summoners:
        if next_action_kills(policy, snapshot, target) and (struck := _strike(policy, snapshot, target)):
            navigator.summon_state = None
            return struck
    return _disengage(policy, snapshot, navigator, plan, board)


def observe(snapshot, navigator, plan) -> None:
    """Every board: a walk out that has left every line is done."""
    if (answers(plan) and navigator.summon_state == DISENGAGING
            and _out_of_lines(snapshot, navigator, _watchers(snapshot))):
        navigator.summon_state = DISENGAGED
        navigator.summon_walk = 0


def walk_key(policy, snapshot, navigator, plan, board) -> str | None:
    """The walk out held over the boards after the summon; past its limit, the scroll."""
    if not answers(plan) or navigator.summon_state != DISENGAGING:
        return None
    if navigator.summon_walk < DISENGAGE_WALK_LIMIT:
        stepped = _walk(policy, snapshot, navigator, plan, board)
        if stepped is not None:
            return stepped
    navigator.summon_state = DISENGAGED
    navigator.summon_walk = 0
    return _teleport(policy, snapshot, navigator, DISENGAGE_TELEPORT_REASON)
