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

  1. 即死 (threat_tiers ``instant_death``, the next player action's p95 against the HP): the
     absorbed Teleportation, else a Scroll of Teleportation (see below).  Without either the plan's
     own 即死 rung right after answers (its escape, then the emergency ladder).
  2. Else, a summoner the next one player action kills (attack_expectation's expected damage per
     player action against its board HP: ``melee`` beside the player, else ``ranged_against``,
     the larger of the launcher and the devices): that blow or shot.  "One action" is one player
     action (100 energy), as attack_expectation reads it today; the per-10-game-turn rework
     (2026-11-19, attack-per-10gt-1119) keeps the per-action figures, and this rule reads those.
  3. Else disengage: a walk of at most ``DISENGAGE_WALK_STEPS`` to the nearest cell no awake
     hostile on the board (the summoner and its summons) has a line to; else the absorbed
     Teleportation or a Scroll of Teleportation; else the longer walk.  The walk is held over the next boards (``walk_key``)
     until the player stands out of their lines, at most ``DISENGAGE_WALK_LIMIT`` steps, then a
     scroll.  The battle state is ``navigator.summon_state``: ``disengaging`` while walking,
     ``disengaged`` once out (after a teleport at once).

After the disengage, owner 2026-11-19 (verbatim): 「まず離脱後の周辺状況を確認。召還持ちを優先して周辺の
モンスターを倒す。安全になったら休息してから召還主や召還されたモンスターを少しずつ釣りだして数を減らす。」
(``after_key``, ``summon_state`` ``disengaged`` then ``luring``):

  1. The surroundings: every board, the awake hostiles on the board (seen or sensed) that act on the
     player where he stands (``acting_around``).  The game processes a monster only while the player is
     within its vision (``aaf``) or in the player's line within MAX_PLAYER_SIGHT
     (monster-processor.cpp decide_process_continue); an asleep one does not act.  What the
     summon was answered against (the summoner and every awake hostile of that board) is the group
     to reduce (``summon_group``), and what acts on the player afterwards joins it.
  2. Those around are killed, summoners first (MonraceKnowledge.can_summon), then in the plan's
     order: the blow beside the player, else the shot.  One around that no blow or shot reaches is
     waited for (the plan's hold) as long as the plan waits for a coming enemy (``enemy_wait_turns``).
  3. Safe (nothing acts on the player): rest (the game's ``R&``, until HP and SP are full) whenever
     HP or SP is short.
  4. Then the group is lured out a few at a time: the member to pull is the one whose pulling cell
     wakes the fewest of the others (summoners first on a tie, then the nearest); the pulling cell is
     a cell where it acts on the player and as few others as can be do, and the player walks there and
     holds (the plan's hold) for what follows, which step 2 then fights.  A member that does not come
     within ``enemy_wait_turns`` is closed on: the cells it would be seen from (in the player's light
     and line).  A member out of sight is looked for at its last cell; looked at with nothing on it
     (in the player's light, or on a lit grid, in his line), or named by a kill line, it leaves the
     group.  Steps 2-4 repeat until the group is empty; the plan then goes on.
     While no member has a pulling cell a walk of the plan reaches (the walks never cross the cells
     where both sides act, so the lower rooms are shut while the Queens and the EVIL summoners both
     live), the plan's own fight and walk answer the board and the luring is asked again on the next.

QUEST_33's sides (quest_alignment_split): every walk here goes round the cells where both sides act,
and a member of one side is pulled only to a cell no living summoner of the other side acts on (by its
vision or its line), so the pulled monster is not drawn into the other side's line.  A summon received
while luring is answered as above (即死 first) and the disengage starts the steps again.

Owner 2026-11-19 (verbatim): 「Q33では離脱に取り込んだテレポートの杖の使用を許可する。ない場合はテレポート
の巻物を40巻用意すること。」  Every teleport here, and the plan's own escape (quest_plan_base._below_line: the
HP line and the 即死 step of a board with no summon), casts the absorbed Teleportation first on Quest 33
(``ABSORBED_FIRST_QUESTS``) when it has a charge and the ``m`` command can cast it (blind too:
cmd-magiceat.cpp refuses confusion only), else reads the scroll; quest_force_rows asks for ``teleport_scrolls_without_absorbed`` scrolls of a character with no
absorbed Teleportation.

The lines are the game's (quest_alignment_split's sight map: the pits and lavas pass a line, a tree and a
closed door do not).
"""

from __future__ import annotations

from hengbot import (
    attack_expectation,
    combat_answer,
    me_absorbed_substitutes,
    quest_alignment_split,
    quest_exposure,
    quest_no_teleport,
    quest_plan_base,
    quest_room_light,
    summon_response,
    teleport_follower,
    threat_tiers,
)
from hengbot.model import Position
from hengbot.policy_constants import REST_MACRO, WAIT_KEY
from hengbot.projection_path import projection_path
from hengbot.q2_kill_credit import _killed as kill_line

FIELD = "summon_answer"
KILL_OR_DISENGAGE = "kill_or_disengage"
DISENGAGING = "disengaging"
DISENGAGED = "disengaged"
LURING = "luring"
# The states after the disengage (``after_key``): the surroundings first, then the luring.
AFTER_STATES = frozenset({DISENGAGED, LURING})
TELEPORT_REASON = "quest-strategy:summoned-teleport"
STRIKE_REASON = "quest-strategy:summoned-strike"
DISENGAGE_TELEPORT_REASON = "quest-strategy:summoned-disengage-teleport"
DISENGAGE_WALK_REASON = "quest-strategy:summoned-disengage-walk"
LURE_WALK_REASON = "quest-strategy:summoned-lure-walk"
REST_REASON = "quest-strategy:summoned-rest"
# A walk this short is taken before a scroll: a teleport on this floor lands among sleeping clones
# and summoners of both sides (quest_alignment_split), a walk keeps the plan's map.  Three steps:
# the Queen at +10 against a hasted player (+10) acts once a player action, so at most three of
# her casts land before the player is out of her line.
DISENGAGE_WALK_STEPS = 3
# The longest walk held before the scroll is read in its place.
DISENGAGE_WALK_LIMIT = 10
# The cells looked at for a way out of the lines: game distance from the player.
_SEARCH_RADIUS = DISENGAGE_WALK_LIMIT
# MAX_PLAYER_SIGHT (system/gamevalue.h): a monster in the player's line this near acts
# (monster-processor.cpp decide_process_continue).
MAX_PLAYER_SIGHT = 20
_STAND = frozenset({"floor", "passage"})


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


def _cell(position: Position) -> tuple[int, int]:
    return position.y, position.x


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


# Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」: the quests whose every
# teleport away casts the absorbed Teleportation before reading the scroll (this module's answers and
# the plan's own escape, quest_plan_base._below_line).  Other quests keep the scroll first (Q25
# forbids the absorbed one, quest_no_teleport).
ABSORBED_FIRST_QUESTS = frozenset({33})


def absorbed_teleport_key(policy, snapshot, reason) -> str | None:
    """On an ``ABSORBED_FIRST_QUESTS`` floor, the absorbed Teleportation with a charge, cast as
    teleport_follower casts it (through the 50F+ rule's point); not confused (cmd-magiceat.cpp
    refuses only confusion, so blind it is cast).  Else None: the caller reads the scroll."""
    power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
    if (policy._active_fixed_quest_id(snapshot) not in ABSORBED_FIRST_QUESTS
            or quest_no_teleport.forbids_absorbed(policy, snapshot) or snapshot.player.confused
            or policy._teleport_blocked_by_equipment(snapshot)
            or me_absorbed_substitutes.cast_key(policy, snapshot, power, blind_ok=True) is None):
        return None
    return teleport_follower.device_teleport_key(policy, snapshot, ("absorbed", None), reason,
                                                 reason + "-staff")


def _scroll_teleport(policy, snapshot, reason) -> str | None:
    if not policy._can_read_scrolls(snapshot):
        return None
    scroll = policy._find_teleport_scroll(snapshot)
    if scroll is None:
        return None
    policy.last_reason = reason
    return policy._read_key(snapshot, scroll)


def _teleport(policy, snapshot, navigator, reason) -> str | None:
    """The absorbed Teleportation first, else the scroll; the player is then out (``disengaged``)."""
    if quest_no_teleport.forbids(policy, snapshot):
        return None
    key = absorbed_teleport_key(policy, snapshot, reason) or _scroll_teleport(policy, snapshot, reason)
    if key is None:
        return None
    navigator.summon_state = DISENGAGED
    navigator.summon_walk = 0
    return key


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
        answer = _teleport(policy, snapshot, navigator, TELEPORT_REASON)
    else:
        for target in summoners:
            if next_action_kills(policy, snapshot, target) and (struck := _strike(policy, snapshot, target)):
                # The strike ends a walk out; the steps after a disengage go on (``after_key``).
                if navigator.summon_state not in AFTER_STATES:
                    navigator.summon_state = None
                return struck
        answer = _disengage(policy, snapshot, navigator, plan, board)
    if answer is not None:
        # The group the steps after the disengage reduce: the summoner and its summons.
        _join(navigator, (*summoners, *_watchers(snapshot)))
    return answer


def observe(policy, snapshot, navigator, plan) -> None:
    """Every board: a walk out that has left every line is done; the group is brought up to date."""
    if not answers(plan):
        return
    if (navigator.summon_state == DISENGAGING
            and _out_of_lines(snapshot, navigator, _watchers(snapshot))):
        navigator.summon_state = DISENGAGED
        navigator.summon_walk = 0
    if navigator.summon_state in AFTER_STATES:
        _note_group(policy, snapshot, navigator)


def walk_key(policy, snapshot, navigator, plan, board) -> str | None:
    """The walk out held over the boards after the summon; past its limit, the teleport."""
    if not answers(plan) or navigator.summon_state != DISENGAGING:
        return None
    if navigator.summon_walk < DISENGAGE_WALK_LIMIT:
        stepped = _walk(policy, snapshot, navigator, plan, board)
        if stepped is not None:
            return stepped
    navigator.summon_state = DISENGAGED
    navigator.summon_walk = 0
    return _teleport(policy, snapshot, navigator, DISENGAGE_TELEPORT_REASON)


# -- after the disengage: the group ------------------------------------------------------


def _join(navigator, monsters) -> None:
    """``monsters`` join the group: index -> (race, cell, can summon); replaced whole."""
    group = dict(navigator.summon_group)
    for monster in monsters:
        if monster.hostile:
            group[monster.index] = (monster.race_id, _cell(monster.position), bool(monster.can_summon))
    navigator.summon_group = group


def _on_board(snapshot) -> list:
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile]


def _vision(policy, race) -> int:
    knowledge = policy._monrace_knowledge.get(race)
    return int(getattr(knowledge, "vision", 0) or 0)


def _open_cells(navigator, snapshot) -> frozenset:
    return frozenset(cell for cell, kind in quest_alignment_split._sight(navigator, snapshot).items()
                     if kind == "floor")


def _sight_line(open_cells, source, target) -> bool:
    """quest_exposure.projectable over a precomputed set of the cells a line passes."""
    path = projection_path(Position(*source), Position(*target), MAX_PLAYER_SIGHT,
                           lambda pos: (pos.y, pos.x) not in open_cells)
    return not path or path[-1] == Position(*target)


def _acts(open_cells, monster_cell, vision, player_cell) -> bool:
    """decide_process_continue: the player within the monster's vision, or in the player's line
    within MAX_PLAYER_SIGHT."""
    distance = quest_exposure.game_distance(monster_cell, player_cell)
    return distance <= vision or (distance <= MAX_PLAYER_SIGHT and _sight_line(open_cells, player_cell, monster_cell))


def acting_around(policy, snapshot, navigator) -> list:
    """Step 1: the awake hostiles on the board that act on the player where he stands."""
    open_cells = _open_cells(navigator, snapshot)
    here = _cell(snapshot.player.position)
    return [monster for monster in _on_board(snapshot) if not monster.asleep
            and _acts(open_cells, _cell(monster.position), _vision(policy, monster.race_id), here)]


def _looked_at(navigator, snapshot, cell) -> bool:
    """A monster on ``cell`` would be seen from where the player stands: in his line, and in his
    light or on a lit grid (a room lit by the plan's scroll)."""
    here = _cell(snapshot.player.position)
    distance = quest_exposure.game_distance(here, cell)
    return (not snapshot.player.blind and distance <= MAX_PLAYER_SIGHT
            and (distance <= max(1, snapshot.light_radius or 1) or quest_room_light.drawn_lit(snapshot, cell))
            and quest_exposure.projectable(navigator.battlefield.terrain, here, cell))


def _killed_races(policy, snapshot) -> set:
    """The races this board's kill lines name."""
    races = set()
    for message in snapshot.messages:
        killed = kill_line(message)
        if killed is None:
            continue
        races |= {race for race, knowledge in policy._monrace_knowledge.items()
                  if killed[0] in getattr(knowledge, "names", ())}
    return races


def _note_group(policy, snapshot, navigator) -> None:
    """Each board after the disengage: the members on the board where they are, what acts on the
    player joins, and a member gone from the board leaves when its last cell is looked at with nothing
    on it or a kill line names its race."""
    known = {monster.index: monster for monster in _on_board(snapshot)}
    _join(navigator, [known[index] for index in navigator.summon_group if index in known])
    _join(navigator, acting_around(policy, snapshot, navigator))
    killed = _killed_races(policy, snapshot)
    navigator.summon_group = {
        index: entry for index, entry in navigator.summon_group.items()
        if index in known or not (entry[0] in killed or _looked_at(navigator, snapshot, entry[1]))}
    if navigator.summon_target not in navigator.summon_group:
        navigator.summon_target = None
        navigator.summon_hold = 0


# -- after the disengage: the steps ------------------------------------------------------


def _strike_around(policy, snapshot, board, acting) -> str | None:
    """Step 2: a blow or a shot at what acts on the player, summoners first, then the plan's order."""
    indices = {monster.index for monster in acting}
    targets = sorted((monster for monster in board.in_view if monster.index in indices),
                     key=lambda monster: not monster.can_summon)
    for target in targets:
        if target in board.beside:
            answer = combat_answer.adjacent_attack(policy, snapshot, [target], quest_plan_base.MELEE_REASON)
            if answer is not None and answer.key is not None:
                return answer.key
        elif (shot := quest_plan_base._shot(policy, snapshot, target)) is not None:
            return shot
    return None


def _hold_for(policy, navigator) -> str:
    navigator.summon_hold += 1
    policy.last_reason = quest_plan_base.HOLD_REASON
    return WAIT_KEY


def _rest_key(policy, snapshot) -> str | None:
    """Step 3: short of HP or SP, the game's rest (``R&``, cmd-move.cpp REST_UNTIL_DONE)."""
    player = snapshot.player
    if ((player.hp >= player.max_hp and player.mp >= player.max_mp) or player.confused
            or player.food_state not in {"normal", "full", "gorged"}):
        return None
    policy.last_reason = REST_REASON
    return REST_MACRO


def _side_of(policy, race, split) -> str | None:
    knowledge = policy._monrace_knowledge.get(race)
    mark = quest_alignment_split.side(knowledge)
    if mark is None and getattr(knowledge, "symbol", "") in split.get("good_summons_symbols", ()):
        return quest_alignment_split.GOOD
    return mark


def lure_cells(policy, snapshot, navigator, plan, board, index, *, close) -> dict[int, set]:
    """Step 4: the pulling cells of member ``index`` by how many other members act there: where it
    acts on the player (``close``: where it would be seen); never where both sides act, nor, for a
    member with a side, where a living summoner of the other side acts."""
    race, cell, _summons = navigator.summon_group[index]
    open_cells = _open_cells(navigator, snapshot)
    walkable = quest_plan_base._terrain_of(navigator, snapshot, water=False)
    refused = quest_alignment_split.refused_cells(policy, snapshot, navigator, plan)
    split = quest_alignment_split.split_of(plan)
    mark = None if split is None else _side_of(policy, race, split)
    other_side = [] if mark is None else [
        (spot, vision) for side, spot, vision in quest_alignment_split.summoners(policy, snapshot, navigator, plan)
        if side != mark]
    others = [(entry[1], _vision(policy, entry[0])) for other, entry in navigator.summon_group.items()
              if other != index]
    vision = _vision(policy, race)
    reach = max(1, snapshot.light_radius or 1) if close else max(vision, MAX_PLAYER_SIGHT)
    occupied = {_cell(position) for position in board.occupied}
    by_count: dict[int, set] = {}
    for spot, kind in walkable.items():
        if (kind not in _STAND or spot in refused or spot in occupied
                or quest_exposure.game_distance(spot, cell) > reach):
            continue
        pulls = _sight_line(open_cells, spot, cell) if close else _acts(open_cells, cell, vision, spot)
        if not pulls or any(_acts(open_cells, where, seen, spot) for where, seen in other_side):
            continue
        count = sum(1 for where, seen in others if _acts(open_cells, where, seen, spot))
        by_count.setdefault(count, set()).add(spot)
    return by_count


def _lure_path(policy, snapshot, navigator, plan, board, index, *, close):
    """(how many others act there, the walk) to the reachable pulling cells of member ``index`` where
    the fewest others act; the walk is ``[here]`` standing on one; None with none reachable."""
    from hengbot import quest_room_sweep  # it asks this module for its rungs

    here = _cell(snapshot.player.position)
    for count, cells in sorted(lure_cells(policy, snapshot, navigator, plan, board, index, close=close).items()):
        if here in cells:
            return count, [snapshot.player.position]
        path = quest_room_sweep._path(policy, navigator, plan, snapshot,
                                      {Position(*spot) for spot in cells}, board.occupied)
        if path:
            return count, path
    return None


def _lure(policy, snapshot, navigator, plan, board) -> str | None:
    """Step 4: walk to the pulling cell of the member to pull, or hold there for it."""
    close = False
    if navigator.summon_target is None:
        choices = []
        for index, (_race, _cell_, summons) in navigator.summon_group.items():
            found = _lure_path(policy, snapshot, navigator, plan, board, index, close=False)
            if found is not None:
                choices.append((found[0], not summons, len(found[1]), index))
        if not choices:
            return None
        navigator.summon_target = min(choices)[-1]
        navigator.summon_hold = 0
    else:
        close = navigator.summon_hold >= int(plan.get("enemy_wait_turns", 0))
    found = _lure_path(policy, snapshot, navigator, plan, board, navigator.summon_target, close=close)
    if found is None:
        navigator.summon_target = None
        navigator.summon_hold = 0
        return None
    path = found[1]
    if len(path) == 1:
        # On a pulling cell: hold for what follows; seen from here, its cell is read by _note_group.
        return None if close else _hold_for(policy, navigator)
    return quest_plan_base._path_step(policy, snapshot, path, LURE_WALK_REASON)


def after_key(policy, snapshot, navigator, plan, board) -> str | None:
    """The steps after the disengage (module docstring), until the group is gone."""
    if (not answers(plan) or navigator.summon_state not in AFTER_STATES
            or snapshot.player.blind or snapshot.player.confused):
        return None
    acting = acting_around(policy, snapshot, navigator)
    if acting:
        if (struck := _strike_around(policy, snapshot, board, acting)) is not None:
            navigator.summon_hold = 0
            return struck
        if navigator.summon_hold < int(plan.get("enemy_wait_turns", 0)):
            return _hold_for(policy, navigator)
        # Past the plan's wait it has not come: it is closed on as a lure (step 4).
        if navigator.summon_target not in {monster.index for monster in acting}:
            navigator.summon_target = min(acting, key=lambda monster: (
                not monster.can_summon, snapshot.player.position.distance_to(monster.position))).index
        navigator.summon_state = LURING
        return _lure(policy, snapshot, navigator, plan, board)
    if (rested := _rest_key(policy, snapshot)) is not None:
        return rested
    if not navigator.summon_group:
        navigator.summon_state = None
        navigator.summon_target = None
        navigator.summon_hold = 0
        return None
    navigator.summon_state = LURING
    return _lure(policy, snapshot, navigator, plan, board)
