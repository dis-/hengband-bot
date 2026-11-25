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
  2b. Else, owner 2026-11-19 (verbatim): 「召還からの離脱の優先度を下げ、予測被害が小さいうちは召還主の
     撃破を優先する」, 「小さい」 answered as 「受けても HP40% を割らない間」 (``bears_the_fight``): while
     the HP less the predicted damage -- the 即死 reading itself (instant_death's next player
     action p95 plus its unseen correction) -- stays at or above the plan's withdrawal line
     (``abort_conditions.hp_ratio`` of the max HP), the summoner is gone after (``ENGAGING``,
     ``navigator.summon_chase``): the blow beside the player, else the shot aimed at it
     (me_ranged_first: the absorbed powers aimed at its cell, the launcher when stronger; else the
     launcher), else a step toward it over the plan's walks
     (which never cross the cells where both sides act, quest_alignment_split).  It stays the
     target on the boards after (``chase_key``, under the plan's survival rungs) while the line
     holds, until it dies or leaves sight; then the next summoner of the group in sight, then the
     summoned (nearest first).  With none left in sight the chase ends in the steps after a
     disengage (below) while the group lasts.  The line broken, the player disengages as in 3.
     On the summon's board another wounded monster in view the next action kills (the one being
     fought, nearly dead) is finished first (``_finishing_blow``), and the summoner chased after it.
     A summon by a caster not seen (「何かが魔法で…」) names no summoner: this rule does not answer
     it; summon_response's leave answers it, with the absorbed Teleportation first on Quest 33.
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
     live), the plan's own fight and walk answer the board.  A member found so (no pulling cell,
     or past the wait no cell it would be seen from) is left out (``summon_unreached``) of the
     waits and the luring until a tracked summoner dies or it comes into view: one acting on the
     player from beyond the pits no longer holds him for ever (n1-c life-217, 2026-11-19).

A member that never comes (NEVER_MOVE, or AQUATIC in its water) is killed from where its shot is
taken or, with no shot, from the dry cells beside it by the blow (``attack_cells``, n1-a life-537).
Owner 2026-11-25 (verbatim) 「撃つ手も取り込んだ魔法道具の手も無い時はそれを許可するが、休憩して魔法道具の
使用回数を戻せる場合はその限りではない」: a Magic-Eater closes on it to melee only with no shot and no
absorbed attack power for it; with a power a rest restores (``recharges_first``) he leaves its line and
rests there (``_recharge_key``), then shoots it with the power.  Owner 2026-11-25 (b)-1 (the audit's
question 「寄って近接の相手の範囲」, answered as recommended): only such a member is closed on to melee;
one that does not come for another reason (a pack that hides, one that runs, one in a locked room) is
closed on to a shot's cell, and with no shot it is the plan's (its wait, its lure, its sweep).

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
    me_capability,
    me_device_attacks,
    me_ranged_first,
    quest_alignment_split,
    quest_exposure,
    quest_no_teleport,
    quest_plan_base,
    quest_room_light,
    quest_wait_placement,
    summon_response,
    teleport_follower,
    threat_tiers,
)
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.item_reservation import decision_memo
from hengbot.model import MonsterState, Position
from hengbot.policy_constants import RANGED_MAX_DISTANCE, REST_MACRO, WAIT_KEY
from hengbot.projection_path import projection_path
from hengbot.q2_kill_credit import _killed as kill_line
from hengbot.q34_recharge import REST_KEY as RECHARGE_REST_KEY

FIELD = "summon_answer"
KILL_OR_DISENGAGE = "kill_or_disengage"
DISENGAGING = "disengaging"
DISENGAGED = "disengaged"
LURING = "luring"
# Going after the summoner while the HP bears its fight (``bears_the_fight``, owner 2026-11-19).
ENGAGING = "engaging"
# The states after the disengage (``after_key``): the surroundings first, then the luring.
AFTER_STATES = frozenset({DISENGAGED, LURING})
TELEPORT_REASON = "quest-strategy:summoned-teleport"
STRIKE_REASON = "quest-strategy:summoned-strike"
DISENGAGE_TELEPORT_REASON = "quest-strategy:summoned-disengage-teleport"
DISENGAGE_WALK_REASON = "quest-strategy:summoned-disengage-walk"
LURE_WALK_REASON = "quest-strategy:summoned-lure-walk"
APPROACH_REASON = "quest-strategy:summoned-approach"
REST_REASON = "quest-strategy:summoned-rest"
# The Magic-Eater's counted rest ('R100', the Q34/Q25 recharge rest) out of the lines for the absorbed
# attack powers a monster that never comes is killed with (``recharges_first``, owner 2026-11-25).
RECHARGE_REST_REASON = "quest-strategy:summoned-rest-recharge"
# What fires at the player and no blow or shot of the board reaches (``fire_answer_key``): the step
# to where it is shot from, else out of its line.
FIRE_APPROACH_REASON = "quest-strategy:fire-approach"
FIRE_WALK_REASON = "quest-strategy:fire-disengage-walk"
FIRE_TELEPORT_REASON = "quest-strategy:fire-disengage-teleport"
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
_STAND = quest_exposure.STAND_KINDS


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
        if (kind not in _STAND or quest_exposure.game_distance(here, cell) > _SEARCH_RADIUS
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

# Owner 2026-11-19 「階段へ逃げず戦い続ける」 (on Q33 with the absorbed Teleportation, the scrolls and the
# potions gone on a 即死 board): the quests on whose floors no escape leaves the level by a staircase
# -- the emergency's walk to the up stair (policy_combat), its '<' (the exit lock's panic release,
# policy_quest._quest_floor_exit_locked) -- and the player fights on.
FIGHT_ON_QUESTS = frozenset({33})


def fights_on(policy, snapshot) -> bool:
    """On a ``FIGHT_ON_QUESTS`` floor: no stair escape, the fight goes on."""
    return policy._active_fixed_quest_id(snapshot) in FIGHT_ON_QUESTS


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


# The emergency ladder's read of Teleportation (policy_combat._emergency_item and the other rungs that read
# through policy._issue_emergency_consumable), cast from the absorbed Teleportation here.
EMERGENCY_TELEPORT_REASON = "emergency:teleport"


def emergency_scroll_substitute(policy, snapshot, item, reason) -> str | None:
    """On an ``ABSORBED_FIRST_QUESTS`` floor, the absorbed Teleportation (``absorbed_teleport_key``)
    in the place of the emergency ladder's read of a Scroll of Teleportation (``reason``
    ``EMERGENCY_TELEPORT_REASON``); else None (the scroll is read).  The other reads through
    policy._issue_emergency_consumable (Phase Door, the reads under other reasons) are unchanged.

    Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」 and, asked how far the
    plan fights, 「取り込んだ杖を優先しようすれば問題ない」: every teleport away on Quest 33 casts the
    absorbed power first.  The plan's escapes and the summon answers did (``_teleport``,
    quest_plan_base._below_line, summon_response's leave); the emergency ladder's read did not.
    The ladder noted the line of fire of its causes before the read (policy_combat, line_of_fire.note).

    n1-b life-418 (Quest 33, 2026-11-25 15:08:00-15:08:53, Zombie Magic-Eater Lv44, HP 455-622/948,
    no 即死 on any of those boards): the ladder read all 15 Scrolls of Teleportation under
    ``emergency:teleport`` while the absorbed Teleportation was cast between the reads
    (``quest-strategy:sweep-teleport:absorbed-power`` at 15:08:21 and 15:08:52).  At 15:39:50 the
    absorbed power was found empty (its ``mAe`` closed on the game's list) on a 即死 board (HP 520,
    45 monsters in view) with no scroll left; the fight that followed ended at 15:39:56."""
    from hengbot import deep_teleport  # it reads the quest modules

    if reason != EMERGENCY_TELEPORT_REASON or not deep_teleport.is_self_teleport_scroll(item):
        return None
    return absorbed_teleport_key(policy, snapshot, EMERGENCY_TELEPORT_REASON)


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
    """The blow beside the player, else the shot aimed at the target itself: me_ranged_first's
    answer (it aims at the target's cell off the eight lines, and weighs the launcher against the
    devices), else the launcher."""
    if snapshot.player.position.distance_to(target.position) <= 1:
        answer = combat_answer.adjacent_attack(policy, snapshot, [target], STRIKE_REASON)
        return None if answer is None else answer.key
    return (me_ranged_first.attack_key(policy, snapshot, target)
            or policy._ranged_attack_key(snapshot, [target], []))


def _out_of_lines_path(policy, snapshot, navigator, plan, board, watchers) -> list:
    """The plan's walk to the nearest cell out of ``watchers``' lines, [] with none."""
    from hengbot import quest_room_sweep  # it asks this module for its rungs

    goals = _out_of_sight(policy, snapshot, navigator, watchers)
    if not goals:
        return []
    return quest_room_sweep._path(policy, navigator, plan, snapshot, goals, board.occupied)


def _walk(policy, snapshot, navigator, plan, board, *, limit=None) -> str | None:
    """A step toward the nearest cell out of the watchers' lines, within ``limit`` steps."""
    path = _out_of_lines_path(policy, snapshot, navigator, plan, board, _watchers(snapshot))
    if not path or (limit is not None and len(path) - 1 > limit):
        return None
    key = quest_plan_base._path_step(policy, snapshot, path, DISENGAGE_WALK_REASON)
    if key is not None:
        navigator.summon_state = DISENGAGING
        navigator.summon_walk += 1
    return key


def _shooting_cells(policy, snapshot, navigator, firer) -> set[Position]:
    """The ground from which the player's shot reaches ``firer``: within RANGED_MAX_DISTANCE (the
    bot's own reach for a shot, policy ``_ranged_target`` and me_ranged_first ``_clear_projection``)
    with a line to its cell over the map, not beside it, and only while some shot of the player's
    deals it damage from there (attack_expectation.ranged_against)."""
    cell = _cell(firer.position)
    if attack_expectation.ranged_against(policy, snapshot, firer.race_id, RANGED_MAX_DISTANCE) <= 0:
        return set()
    open_cells = _open_cells(navigator, snapshot)
    walkable = quest_plan_base._terrain_of(navigator, snapshot, water=False)
    return {Position(*spot) for spot, kind in walkable.items()
            if kind in _STAND and 2 <= quest_exposure.game_distance(spot, cell) <= RANGED_MAX_DISTANCE
            and _sight_line(open_cells, spot, cell)}


def _blow_cells(policy, snapshot, navigator, monster) -> set[Position]:
    """The dry ground beside a monster that never comes to the player (``_stays``: NEVER_MOVE, or
    AQUATIC in its water) from which the player's blow reaches it: melee scores above it zero
    (attack_expectation.melee).  A monster that comes is met where it comes (the plan's hold).
    A Magic-Eater closes on it to melee only with no shot and no absorbed power for it
    (``melee_withheld``, owner 2026-11-25).  ``stays``: the member's verdict (``never_comes``), else
    the race's (``_stays``)."""
    if (melee_approach(policy, snapshot, monster, site=BLOW_SITE) != MELEE
            or attack_expectation.melee(policy, snapshot, monster) <= 0):
        return set()
    cell = _cell(monster.position)
    walkable = quest_plan_base._terrain_of(navigator, snapshot, water=False)
    return {Position(*spot) for spot, kind in walkable.items()
            if kind in _STAND and quest_exposure.game_distance(spot, cell) == 1}


def recharges_first(policy, snapshot, race_id) -> bool:
    """A Magic-Eater with no shot at ``race_id`` now (attack_expectation.ranged_against: the
    launcher and the charged absorbed powers) and an absorbed attack power for it that a rest
    restores (me_device_attacks.restorable_powers).

    Owner 2026-11-25 (verbatim), asked whether the Magic-Eater too closes on the shore or beside a
    monster that never leaves the water or never moves to melee it when it has no shot: 「撃つ手も
    取り込んだ魔法道具の手も無い時はそれを許可するが、休憩して魔法道具の使用回数を戻せる場合はその限りでは
    ない」.  So it rests out of the lines (``_recharge_key``) and kills it with the powers."""
    return (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            and attack_expectation.ranged_against(policy, snapshot, race_id, RANGED_MAX_DISTANCE) <= 0
            and bool(me_device_attacks.restorable_powers(policy, snapshot, race_id)))


def melee_withheld(policy, snapshot, race_id) -> bool:
    """A Magic-Eater does not close on a monster that never comes to melee it while it has a shot
    at it or an absorbed attack power for it that a rest restores (``recharges_first``, owner
    2026-11-25 「撃つ手も取り込んだ魔法道具の手も無い時はそれを許可する」).  Another class closes on it
    whenever a blow reaches (n1-a life-537)."""
    return (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            and (attack_expectation.ranged_against(policy, snapshot, race_id, RANGED_MAX_DISTANCE) > 0
                 or recharges_first(policy, snapshot, race_id)))


# The answers of the one gate on the walks that close on a monster to melee it (``melee_approach``):
# walk to melee it, rest first (out of the lines, for an absorbed power a rest restores), or not.
MELEE = "melee"
REST_FIRST = "rest-first"
REFUSED = "refused"
# Its sites (scripts/melee_site_lint.py ``MELEE_APPROACH_ENTRIES``): the dry cells beside a monster that
# never comes (``_blow_cells``, which ``attack_cells`` reads), the room sweep's walk to what stands
# still in view (quest_room_sweep ``_fight``) and the chase of a summoner (``_approach``).
BLOW_SITE = "blow"
SWEEP_SITE = "sweep"
CHASE_SITE = "chase"


def melee_approach(policy, snapshot, monster, *, site) -> str:
    """The one gate on the walks that close on ``monster`` to melee it (contradiction audit
    2026-11-25 (a)-4): ``MELEE``, ``REST_FIRST`` or ``REFUSED`` at ``site``.

    * ``BLOW_SITE`` and ``SWEEP_SITE``, a monster the plan closes on because it does not come:
      owner 2026-11-25 (b)-1 (the audit's question 「寄って近接の相手の範囲」, as recommended): only one that
      never leaves the water or never moves (``_stays``: quest_plan_base.never_moves ``in_water``).
      A pack that hides, a monster that runs, one in a locked room is not closed on to melee: with no
      shot it is the plan's (its wait, its lure, its sweep).
    * ``CHASE_SITE``: the summoner gone after (owner 2026-11-19 「予測被害が小さいうちは召還主の撃破を
      優先する」).

    At every site, owner 2026-11-25 (b)-2 (the audit's question 「魔道具術師が召喚主を追う時も休めば
    戻るなら休む」, answered as recommended, the 11-25 rule 「撃つ手も取り込んだ魔法道具の手も無い時は
    それを許可するが、休憩して魔法道具の使用回数を戻せる場合はその限りではない」 carried to the chase and to
    the sweep): a Magic-Eater with no shot now and an absorbed attack power for it that a rest
    restores rests first, out of the lines (``recharges_first``: ``REST_FIRST``, ``recharge_rest_key``);
    with a shot he does not walk to melee a monster that does not come (``melee_withheld``)."""
    if recharges_first(policy, snapshot, monster.race_id):
        return REST_FIRST if site == CHASE_SITE or _stays(policy, monster.race_id) else REFUSED
    if site == CHASE_SITE:
        return MELEE
    if not _stays(policy, monster.race_id) or melee_withheld(policy, snapshot, monster.race_id):
        return REFUSED
    return MELEE


def attack_cells(policy, snapshot, navigator, monster) -> set[Position]:
    """The one verdict of where the player stands to kill ``monster`` when it does not come to him:
    a cell its shot is taken from (``_shooting_cells``) or, for one that never comes, a dry cell
    beside it (``_blow_cells``).  The fire answer closes on these (``fire_answer_key``) and the lure
    of a member that never comes walks to them (``_lure``), so neither walks off the cells the other
    walks to.

    n1-a life-537 (Quest 33, 2026-11-25 10:11, Zombie warrior Lv48 with no bolts): two 船幽霊
    (race 1389: AQUATIC, 10d10 HP, BO_WATE/SCARE 1_IN_8) in the deep water [12..13,43..44] cast
    water bolts at the player on [15,41].  The lure walked to a cell they are seen from, the fire
    answer (no shot) walked out of their line, and the two alternated with the hold until the
    livelock stop, while one blow (expected 100 a player action) from [14,42] kills one."""
    return (_shooting_cells(policy, snapshot, navigator, monster)
            | _blow_cells(policy, snapshot, navigator, monster))


def stranded(policy, snapshot, navigator, plan, board, acting) -> list:
    """Of ``acting`` (what acts on the player), those in view that do not come (``never_comes``),
    are not beside him and have cells they are killed from (``attack_cells``: a shot's cell, and for
    one that never leaves the water or never moves the dry cell beside it, owner 2026-11-25 (b)-1):
    no wait brings them (owner 2026-11-19 「有効な場所で待つ」), so they are closed on as the fire is
    (``fire_answer_key``).  One that never leaves the water or never moves and that the
    Magic-Eater recharges for (``recharges_first``) has no such cell yet: the fire answer takes him
    out of its line, where the rest is taken (``_recharge_key``).  One that does not come with no
    such cell (a hiding pack, a monster in a locked room, no shot) is not closed on: the plan's."""
    indices = {monster.index for monster in acting}
    return [monster for monster in board.in_view
            if monster.index in indices and not monster.asleep and monster not in board.beside
            and _comes_not(policy, snapshot, navigator, plan, board, monster)
            and (attack_cells(policy, snapshot, navigator, monster)
                 or (_stays(policy, monster.race_id) and recharges_first(policy, snapshot, monster.race_id)))]


def fire_answer_key(policy, snapshot, navigator, plan, board, firers) -> str | None:
    """``firers``: hostiles that hurt the player from where they stand and that no blow or shot of
    this board reaches.  A step toward the nearest cell one of them is killed from (``attack_cells``:
    its shot, or the blow beside one that never comes) while the player is on none; else out of their
    line: a step toward the
    nearest cell none of them has a line to, else the teleport (the absorbed Teleportation first on
    Quest 33); else None.

    Owner 2026-11-19 (verbatim) 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で待つ」: a monster
    with ranged attacks and a line to the player stays where it is and casts
    (monster-sweep-grid.cpp RangedAttackMoveGridDecider, quest_wait_placement's reading), so a wait in
    its line only takes its fire.  So it is closed on to be shot, or left (the plan's 「無理なら離脱」,
    QUEST_33 owner 2026-11-19); the plan's survival rungs above answer the HP on the way.  On a
    shooting cell with still no shot (the power failed to aim, the target moved behind another body)
    the player leaves the line rather than holds in it.  n1-c life-220 (Quest 33, 2026-11-22
    19:35:52-19:36:01): two 船幽霊 in deep water (AQUATIC: they never leave it), 14 grids away on
    [4,41] and [5,41], fired water bolts at the player on [1,27] while the plan held for them, HP 811
    to death."""
    from hengbot import quest_room_sweep  # it asks this module for its rungs

    if not firers or not answers(plan):
        return None
    shooting = set()
    for firer in firers:
        shooting |= attack_cells(policy, snapshot, navigator, firer)
    if shooting and snapshot.player.position not in shooting:
        path = quest_room_sweep._path(policy, navigator, plan, snapshot, shooting, board.occupied)
        if (key := quest_plan_base._path_step(policy, snapshot, path, FIRE_APPROACH_REASON)) is not None:
            return key
    path = _out_of_lines_path(policy, snapshot, navigator, plan, board, firers)
    if (key := quest_plan_base._path_step(policy, snapshot, path, FIRE_WALK_REASON)) is not None:
        return key
    if quest_no_teleport.forbids(policy, snapshot):
        return None
    return (absorbed_teleport_key(policy, snapshot, FIRE_TELEPORT_REASON)
            or _scroll_teleport(policy, snapshot, FIRE_TELEPORT_REASON))


def _disengage(policy, snapshot, navigator, plan, board) -> str | None:
    navigator.summon_walk = 0
    return (_walk(policy, snapshot, navigator, plan, board, limit=DISENGAGE_WALK_STEPS)
            or _teleport(policy, snapshot, navigator, DISENGAGE_TELEPORT_REASON)
            or _walk(policy, snapshot, navigator, plan, board))


def _withdrawal_line(policy, snapshot) -> float | None:
    """The plan's withdrawal line in HP: ``abort_conditions.hp_ratio`` of the max HP (QUEST_33: 40%)."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    ratio = None if profile is None else profile.abort_conditions.get("hp_ratio")
    return None if ratio is None else float(ratio) * snapshot.player.max_hp


def predicted_damage(death) -> int:
    """The damage taken before the player acts again, as 即死 reads it (instant_death: the next
    player action's p95 plus the unseen correction)."""
    return death.next_action_p95 + death.unseen_correction


def bears_the_fight(policy, snapshot, death=None) -> bool:
    """Owner 2026-11-19 「予測被害が小さいうちは召還主の撃破を優先する」 (「小さい」 = 「受けても HP40% を
    割らない間」): the HP less the predicted damage stays at or above the plan's withdrawal line."""
    line = _withdrawal_line(policy, snapshot)
    if line is None:
        return False
    if death is None:
        death = threat_tiers.instant_death(policy, snapshot)
    return snapshot.player.hp - predicted_damage(death) >= line


def _chase_order(snapshot, navigator) -> list:
    """The group in sight to go after: the chased summoner first, then the other summoners, then
    the summoned, each nearest first."""
    here = snapshot.player.position
    members = [monster for monster in snapshot.visible_monsters
               if monster.hostile and monster.index in navigator.summon_group]
    return sorted(members, key=lambda monster: (
        monster.index != navigator.summon_chase, not monster.can_summon,
        here.distance_to(monster.position), monster.index))


def _approach(policy, snapshot, navigator, plan, board, target) -> str | None:
    """A step toward the cells beside ``target`` over the plan's walks, as the gate allows
    (``melee_approach`` at ``CHASE_SITE``); a Magic-Eater the gate sends to rest first rests out of
    the lines (``recharge_rest_key``, owner 2026-11-25 (b)-2)."""
    from hengbot import quest_room_sweep  # it asks this module for its rungs

    verdict = melee_approach(policy, snapshot, target, site=CHASE_SITE)
    if verdict == REST_FIRST:
        return recharge_rest_key(policy, snapshot, navigator, plan, board, {target.race_id})
    if verdict != MELEE:
        return None
    goals = {Position(target.position.y + dy, target.position.x + dx)
             for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx}
    path = quest_room_sweep._path(policy, navigator, plan, snapshot, goals, board.occupied)
    return quest_plan_base._path_step(policy, snapshot, path, APPROACH_REASON) if path else None


def _go_after(policy, snapshot, navigator, plan, board) -> str | None:
    """The blow, the shot or the step at the first of the chase order that has one; the summoner
    chased stays the target while it is in sight."""
    order = _chase_order(snapshot, navigator)
    if not order:
        return None
    navigator.summon_chase = order[0].index
    for target in order:
        answer = _strike(policy, snapshot, target)
        if answer is None and snapshot.player.position.distance_to(target.position) > 1:
            answer = _approach(policy, snapshot, navigator, plan, board, target)
        if answer is not None:
            navigator.summon_state = ENGAGING
            navigator.summon_walk = 0
            return answer
    return None


def key(policy, snapshot, navigator, plan, board) -> str | None:
    """The board of a summon received: teleport on 即死, else the killing action, else the
    summoner gone after while the HP bears it, else disengage."""
    if not answers(plan):
        return None
    summoners = summon_response.summoners_at_player(policy, snapshot)
    if not summoners:
        return None
    # The group the steps after the disengage reduce, and the chase goes after: the summoner and
    # its summons.
    _join(navigator, (*summoners, *_watchers(snapshot)))
    death = threat_tiers.instant_death(policy, snapshot)
    if death.holds:
        return _teleport(policy, snapshot, navigator, TELEPORT_REASON)
    for target in summoners:
        if next_action_kills(policy, snapshot, target) and (struck := _strike(policy, snapshot, target)):
            # The strike ends a walk out; the steps after a disengage go on (``after_key``).
            if navigator.summon_state not in AFTER_STATES:
                navigator.summon_state = None
            return struck
    if bears_the_fight(policy, snapshot, death):
        if navigator.summon_chase not in {monster.index for monster in summoners}:
            navigator.summon_chase = summoners[0].index
        # Another monster the next action kills (the one being fought, nearly dead) is finished
        # first: the summon of a different monster does not make the player leave it; the
        # summoner is then gone after on the boards that follow (``chase_key``).
        if (finished := _finishing_blow(policy, snapshot, summoners)) is not None:
            navigator.summon_state = ENGAGING
            navigator.summon_walk = 0
            return finished
        if (answer := _go_after(policy, snapshot, navigator, plan, board)) is not None:
            return answer
    navigator.summon_chase = None
    return _disengage(policy, snapshot, navigator, plan, board)


def _finishing_blow(policy, snapshot, summoners) -> str | None:
    """The blow or shot at a wounded hostile in view (the one being fought) other than the
    summoners that the next player action kills (``next_action_kills``), nearest first.  An unhurt
    one is no fight under way: the summoner comes first."""
    named = {monster.index for monster in summoners}
    here = snapshot.player.position
    for target in sorted((monster for monster in snapshot.visible_monsters
                          if monster.hostile and monster.index not in named and monster.hp < monster.max_hp),
                         key=lambda monster: (here.distance_to(monster.position), monster.index)):
        if next_action_kills(policy, snapshot, target) and (struck := _strike(policy, snapshot, target)):
            return struck
    return None


def chase_key(policy, snapshot, navigator, plan, board) -> str | None:
    """The boards after the summon while going after the summoner: on while the HP bears the
    fight, else the disengage (3).  Under the plan's survival rungs: 即死 is theirs."""
    if not answers(plan) or navigator.summon_state != ENGAGING:
        return None
    if not bears_the_fight(policy, snapshot):
        navigator.summon_chase = None
        return _disengage(policy, snapshot, navigator, plan, board)
    return _go_after(policy, snapshot, navigator, plan, board)


def _end_chase(navigator) -> None:
    """None of the group left in sight: the steps after a disengage while the group lasts."""
    navigator.summon_chase = None
    navigator.summon_state = DISENGAGED if navigator.summon_group else None


def observe(policy, snapshot, navigator, plan) -> None:
    """Every board: a walk out that has left every line is done; the group is brought up to date;
    a chase with none of the group left in sight ends."""
    if not answers(plan):
        return
    if (navigator.summon_state == DISENGAGING
            and _out_of_lines(snapshot, navigator, _watchers(snapshot))):
        navigator.summon_state = DISENGAGED
        navigator.summon_walk = 0
    if navigator.summon_state in AFTER_STATES or navigator.summon_state == ENGAGING:
        _note_group(policy, snapshot, navigator)
    if navigator.summon_state == ENGAGING and not _chase_order(snapshot, navigator):
        _end_chase(navigator)


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
    # A member's verdict whether it comes (``never_comes``) leaves with it.
    navigator.summon_comes = {index: comes for index, comes in navigator.summon_comes.items()
                              if index in navigator.summon_group}
    navigator.summon_comes_basis = {index: basis for index, basis in navigator.summon_comes_basis.items()
                                    if index in navigator.summon_group}
    if navigator.summon_target is not None and navigator.summon_target not in navigator.summon_group:
        # The member lured is gone: the next one starts its own wait.  (With no member lured the
        # holds for what acts on the player keep counting: n1-c life-217, see ``after_key``.)
        navigator.summon_target = None
        navigator.summon_hold = 0


# -- after the disengage: the steps ------------------------------------------------------


def _strike_around(policy, snapshot, board, acting) -> str | None:
    """Step 2: a blow or a shot at what acts on the player, summoners first, then the plan's order;
    a monster known by telepathy that fires at the player from out of view (``Board.firing``) is
    shot as one in view (target-preparation.cpp target_able: ``ml`` and projectable)."""
    indices = {monster.index for monster in acting}
    targets = sorted((monster for monster in (*board.in_view, *board.firing) if monster.index in indices),
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


def _recharging(policy, snapshot, navigator) -> frozenset:
    """The members of the group that never come (``_stays``) and that the Magic-Eater rests for
    before he kills them (``recharges_first``)."""
    return frozenset(index for index, (race, _cell_, _summons) in navigator.summon_group.items()
                     if _stays(policy, race) and recharges_first(policy, snapshot, race))


def _recharge_key(policy, snapshot, navigator, plan, board, recharging) -> str | None:
    """``recharge_rest_key`` for the members ``recharging`` (their races)."""
    return recharge_rest_key(policy, snapshot, navigator, plan, board,
                             {navigator.summon_group[index][0] for index in recharging})


def recharge_rest_key(policy, snapshot, navigator, plan, board, races) -> str | None:
    """Owner 2026-11-25 「休憩して魔法道具の使用回数を戻せる場合はその限りではない」: against the races
    ``races``, out of every awake hostile's line a counted rest (``R100``, as the Q34 and Q25
    recharge rests) that restores the absorbed powers (me_device_attacks.restorable_powers); in a
    line, a step out of it first (the fire answer's walk).  The displayed lists of those powers are
    stale after the rest and are read again before the next decision (me_device_attacks
    ``mark_stale``, me_powers_refresh ``resume_read_key``); a power with a use again is a shot, and
    the member is closed on to its shooting cells (``attack_cells``).  The rests on one cell are
    bounded (stationary_bounds ``SUMMONED_RECHARGE_REST_MAX_DECISIONS``)."""
    player = snapshot.player
    watchers = _watchers(snapshot)
    if watchers and not _out_of_lines(snapshot, navigator, watchers):
        path = _out_of_lines_path(policy, snapshot, navigator, plan, board, watchers)
        return quest_plan_base._path_step(policy, snapshot, path, FIRE_WALK_REASON)
    if player.confused or player.food_state not in {"normal", "full", "gorged"}:
        return None
    kinds = set()
    for race in races:
        kinds |= {power.kind for power in me_device_attacks.restorable_powers(policy, snapshot, race)}
    me_device_attacks.mark_stale(policy, kinds)
    policy.last_reason = RECHARGE_REST_REASON
    return RECHARGE_REST_KEY


# Owner 2026-11-25 (c)-1 (verbatim answer, as recommended) 「Q33 で取り込んだテレポートの回数が少ない時は
# 射線の外で休んで回数を戻してから釣り出しを続ける」.  No count of "few" was named before (no constant of
# the absorbed Teleportation's charges in me_powers or the Q33 plan): the one escape left, the least
# that still takes the player out once.
TELEPORT_FEW_CHARGES = 1


def teleport_short(policy, snapshot) -> bool:
    """On an ``ABSORBED_FIRST_QUESTS`` floor, the absorbed Teleportation (me_capability) has at most
    ``TELEPORT_FEW_CHARGES`` and fewer than its count, so a rest restores some (hpmp/
    hp-mp-regenerator.cpp regenmagic: each absorbed staff gains charge toward its count)."""
    if policy._active_fixed_quest_id(snapshot) not in ABSORBED_FIRST_QUESTS:
        return False
    kind, sval = me_absorbed_substitutes.TELEPORTATION
    if not me_capability.has(policy, snapshot, kind, sval):
        return False
    charges = me_capability.charges(policy, snapshot, kind, sval)
    return charges <= TELEPORT_FEW_CHARGES and charges < me_capability.count(policy, snapshot, kind, sval)


def teleport_rest_key(policy, snapshot, navigator, plan, board) -> str | None:
    """Owner 2026-11-25 (c)-1: the absorbed Teleportation short (``teleport_short``), out of every
    awake hostile's line the counted rest of ``recharge_rest_key`` (its list read again after it),
    before the lure goes on."""
    if not teleport_short(policy, snapshot):
        return None
    player = snapshot.player
    watchers = _watchers(snapshot)
    if watchers and not _out_of_lines(snapshot, navigator, watchers):
        path = _out_of_lines_path(policy, snapshot, navigator, plan, board, watchers)
        return quest_plan_base._path_step(policy, snapshot, path, FIRE_WALK_REASON)
    if player.confused or player.food_state not in {"normal", "full", "gorged"}:
        return None
    me_device_attacks.mark_stale(policy, {me_absorbed_substitutes.TELEPORTATION[0]})
    policy.last_reason = RECHARGE_REST_REASON
    return RECHARGE_REST_KEY


def _side_of(policy, race, split) -> str | None:
    knowledge = policy._monrace_knowledge.get(race)
    mark = quest_alignment_split.side(knowledge)
    if mark is None and getattr(knowledge, "symbol", "") in split.get("good_summons_symbols", ()):
        return quest_alignment_split.GOOD
    return mark


def lure_cells(policy, snapshot, navigator, plan, board, index, *, close, wander=False) -> dict[int, set]:
    """Step 4: the pulling cells of member ``index`` by how many other members act there: where it
    acts on the player (``close``: where it would be seen; for one on the board that never comes,
    where it is killed from, ``attack_cells``); never where both sides act, nor, for a
    member with a side, where a living summoner of the other side acts.  ``wander``: where it acts
    from its last cell or a cell one step from it (``_lure_path``'s kept wait)."""
    race, cell, _summons = navigator.summon_group[index]
    froms = ([(cell[0] + dy, cell[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)] if wander
             else [cell])
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
    # A member that never comes, on the board: closed on to the cells it is killed from
    # (``attack_cells``, the fire answer's own), not merely to where it is seen (n1-a life-537).
    attack = None
    if close and never_comes(policy, snapshot, navigator, plan, board, index):
        attack = {_cell(spot) for spot in attack_cells(
            policy, snapshot, navigator, _member(policy, snapshot, navigator, index))}
    by_count: dict[int, set] = {}
    for spot, kind in walkable.items():
        if (kind not in _STAND or spot in refused or spot in occupied
                or (attack is None and min(quest_exposure.game_distance(spot, at) for at in froms) > reach)):
            continue
        if attack is not None:
            pulls = spot in attack
        else:
            pulls = any(_sight_line(open_cells, spot, at) if close else _acts(open_cells, at, vision, spot)
                        for at in froms)
        if not pulls or any(_acts(open_cells, where, seen, spot) for where, seen in other_side):
            continue
        count = sum(1 for where, seen in others if _acts(open_cells, where, seen, spot))
        by_count.setdefault(count, set()).add(spot)
    return by_count


# How many more other members act on the cell the lure's wait holds than when the wait began on it,
# from which the wait leaves it for the cell where the fewest act (owner 2026-11-25 (b)-6).
KEEP_WAIT_MORE_OTHERS = 3


def _lure_path(policy, snapshot, navigator, plan, board, index, *, close, keep=False):
    """(how many others act there, the walk) to the reachable pulling cells of member ``index`` where
    the fewest others act; the walk is ``[here]`` standing on one; None with none reachable.

    ``keep``: the wait on a pulling cell has begun, so the player stays on any pulling cell of the
    member, however many others act there, and while the member acts on it from its last cell or one
    step from it (``lure_cells`` ``wander``).  How many others act on a cell, and whether the member
    itself does, change with every step they take, and walking to the fewest each board turns the
    wait into a walk back and forth (n1-a life-537, Quest 33, 2026-11-25 12:37: the 巨大火アリ 9
    stepping between [27,53] and [26,54] at the edge of its vision (14) put [29,40] in and out of its
    pulling cells, and the player between [29,40] and [29,41] until the livelock stop; owner
    2026-11-13 pingpong 「理由が消えるまで戻らない」: the cell is kept while its reason holds).
    Owner 2026-11-25 (b)-6 (verbatim answer) 「誘い出しで待ち始めたマスに、待ち始めた時より他の敵が3体以上
    多く来られるようになったら、一番少ないマスへ移る」: not kept once ``KEEP_WAIT_MORE_OTHERS`` or more
    other members act on it than when the wait began there (``navigator.summon_hold_basis``); then
    the cell where the fewest act, as at the start (owner 2026-11-19)."""
    from hengbot import quest_room_sweep  # it asks this module for its rungs

    here = _cell(snapshot.player.position)
    by_count = sorted(lure_cells(policy, snapshot, navigator, plan, board, index, close=close).items())
    if keep:
        basis = navigator.summon_hold_basis
        for count, cells in sorted(lure_cells(policy, snapshot, navigator, plan, board, index, close=close,
                                              wander=True).items()):
            if here in cells:
                if (basis is not None and basis[:2] == (index, here)
                        and count - basis[2] >= KEEP_WAIT_MORE_OTHERS):
                    break
                return count, [snapshot.player.position]
    for count, cells in by_count:
        if here in cells:
            return count, [snapshot.player.position]
        path = quest_room_sweep._path(policy, navigator, plan, snapshot,
                                      {Position(*spot) for spot in cells}, board.occupied)
        if path:
            return count, path
    return None


def _kills(navigator) -> int:
    """The tracked summoners' kill lines read on this floor (quest_alignment_split)."""
    return sum(int(count) for count in navigator.split_kills.values())


def _unreached(navigator, board) -> frozenset:
    """The members no walk of the plan reaches a pulling or seeing cell of, as last found: kept
    until a tracked summoner dies (the cells both sides act on, which the walks go round, change
    only then) or the monster comes into view (then it is struck or shot).  Pruned in place."""
    in_view = {monster.index for monster in board.in_view}
    kills = _kills(navigator)
    navigator.summon_unreached = {index: at for index, at in navigator.summon_unreached.items()
                                  if at == kills and index not in in_view}
    return frozenset(navigator.summon_unreached)


def _mark_unreached(navigator, index) -> None:
    navigator.summon_unreached = {**navigator.summon_unreached, index: _kills(navigator)}


def _stays(policy, race) -> bool:
    """A race that never comes to a pulling cell (the pulling cells are dry ground):
    quest_plan_base.never_moves with ``in_water`` (NEVER_MOVE, or AQUATIC)."""
    return quest_plan_base.never_moves(policy, race, in_water=True)


# The pulling cells read for a member's coming (``never_comes``): the nearest of them, as the lure
# walks to the nearest; a farther one is no wait the lure would take.
_COMING_SPOTS = 24


def _member(policy, snapshot, navigator, index):
    """Member ``index``: the board's monster, else one of its race on its last cell."""
    found = next((monster for monster in _on_board(snapshot) if monster.index == index), None)
    if found is not None:
        return found
    race, cell, summons = navigator.summon_group[index]
    knowledge = policy._monrace_knowledge.get(race)
    hp = int(getattr(knowledge, "max_hp", 0) or 0)
    names = getattr(knowledge, "names", None) or ("",)
    return MonsterState(index=index, position=Position(*cell), hp=hp, max_hp=hp, distance=0,
                        friendly=False, pet=False, name=names[0], race_id=race, can_summon=bool(summons))


def never_comes(policy, snapshot, navigator, plan, board, index) -> bool:
    """The one verdict, read by the lure, its wait and the closing on (``stranded``, ``lure_cells``),
    whether member ``index`` comes to the player: no (``True``) for a race that never steps off its
    ground (``_stays``), and for one that, by the game's own moves (quest_wait_placement ``will_come``:
    the sweep grid's flow, the hiding of an animal pack, the doors and the ground it cannot cross),
    comes to none of the nearest pulling cells (``_COMING_SPOTS``).  A member that does not come is
    not lured nor waited for (owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で
    待つ」): it is closed on to the cells it is killed from (``attack_cells``: a shot's cells, and the
    dry cells beside it only for one that never leaves the water or never moves, owner 2026-11-25
    (b)-1), and one no walk reaches such a cell of, or with none, is left to the plan (``_unreached``).

    n1-a life-537 (Quest 33, 2026-11-25 13:18): the 巨大火アリ (race 548: FRIENDS, ANIMAL, no spell)
    by the tree columns [24..27,53..55] hid from the player at full HP and SP
    (monster-sweep-grid.cpp HidingMoveGridDecider: the open grids round the player, less 2 in a room
    and 2 for no spell, below 8 x (HP + SP) / (max HP + max SP)): the lure held 200 boards for them on
    [28,52] and on [27,44], then walked to where they were last seen and the sweep to where it last
    saw them, in turn, until the livelock stop."""
    race, cell, _summons = navigator.summon_group[index]
    if _stays(policy, race):
        return True
    # Kept for the member while it stays in the group (``_note_group``): read afresh from each cell it
    # steps to, a member wandering by the edge of its reach comes on one board and not on the next,
    # and the lure walks to its pulling cells and to its killing cells in turn (n1-b life-418,
    # Quest 33, 2026-11-25 15:08:59: Fang (race 55, RAND_25) in its locked room [24..26,1..4] read
    # in turn, the walk between [25,11], [26,12] and [26,11] until the livelock stop).
    # Owner 2026-11-25 (b)-3 (verbatim answer, as recommended) 「「来るか」は固定しておき、待ちの上限が
    # 尽きた時と、HP が隠れの境目をまたいで大きく変わった時だけ判断し直す」: read again when the board's
    # hiding line (quest_wait_placement.hide_line, the game's HidingMoveGridDecider) is not the one
    # it was read under, and once when the wait's cap runs out (``_rejudge_after_wait``).
    line = quest_wait_placement.hide_line(snapshot)
    basis = navigator.summon_comes_basis.get(index)
    if index in navigator.summon_comes and basis is not None and basis[0] == line:
        return not navigator.summon_comes[index]

    def compute() -> bool:
        here = _cell(snapshot.player.position)
        cells = set()
        for found in lure_cells(policy, snapshot, navigator, plan, board, index, close=False).values():
            cells |= found
        spots = sorted(cells, key=lambda spot: (quest_exposure.game_distance(here, spot), spot))[:_COMING_SPOTS]
        on_board = next((monster for monster in _on_board(snapshot) if monster.index == index), None)
        return not quest_wait_placement.will_come(policy, snapshot, navigator, race, cell, spots, on_board,
                                                   first=True)

    verdict = decision_memo(policy, "quest_summon_answer.never_comes", snapshot,
                            (index, race, tuple(cell), tuple(sorted(navigator.summon_group))), compute)
    navigator.summon_comes = {**navigator.summon_comes, index: not verdict}
    # The cap's reading is spent once per hiding line.
    capped = basis is not None and basis[0] == line and basis[1]
    navigator.summon_comes_basis = {**navigator.summon_comes_basis, index: (line, capped)}
    return verdict


def _rejudge_after_wait(navigator, indices) -> None:
    """Owner 2026-11-25 (b)-3: the wait's cap (``enemy_wait_turns``) ran out on ``indices``: each
    verdict is read again on the next ``never_comes``, once until the hiding line changes."""
    comes, basis_of = dict(navigator.summon_comes), dict(navigator.summon_comes_basis)
    for index in indices:
        basis = basis_of.get(index)
        if index in comes and basis is not None and not basis[1]:
            del comes[index]
            basis_of[index] = (basis[0], True)
    navigator.summon_comes, navigator.summon_comes_basis = comes, basis_of


def _comes_not(policy, snapshot, navigator, plan, board, monster) -> bool:
    """``never_comes`` of a board monster (a member, or one acting on the player not yet one)."""
    if monster.index not in navigator.summon_group:
        return _stays(policy, monster.race_id)
    return never_comes(policy, snapshot, navigator, plan, board, monster.index)


def _lure(policy, snapshot, navigator, plan, board) -> str | None:
    """Step 4: walk to the pulling cell of the member to pull, or hold there for it.  A member no
    walk reaches is left to the plan (``_unreached``); with none reachable the plan goes on.  A
    member that never comes (``_stays``) is not lured from afar (owner 2026-11-19 「有効な場所で
    待つ」): it is closed on at once, to a cell it is killed from while it is on the board
    (``attack_cells``), else to a cell it would be seen from."""
    unreached = _unreached(navigator, board)
    if navigator.summon_target is None:
        choices = []
        for index, (race, _cell_, summons) in navigator.summon_group.items():
            if index in unreached:
                continue
            found = _lure_path(policy, snapshot, navigator, plan, board, index,
                               close=never_comes(policy, snapshot, navigator, plan, board, index))
            if found is None:
                _mark_unreached(navigator, index)
            else:
                choices.append((found[0], not summons, len(found[1]), index))
        if not choices:
            return None
        navigator.summon_target = min(choices)[-1]
        navigator.summon_hold = 0
    capped = navigator.summon_hold >= int(plan.get("enemy_wait_turns", 0))
    if capped:
        _rejudge_after_wait(navigator, (navigator.summon_target,))
    close = capped or never_comes(policy, snapshot, navigator, plan, board, navigator.summon_target)
    # The wait has begun (a hold spent on this member): it goes on on any of its pulling cells.
    found = _lure_path(policy, snapshot, navigator, plan, board, navigator.summon_target, close=close,
                       keep=not close and navigator.summon_hold > 0)
    if found is None:
        _mark_unreached(navigator, navigator.summon_target)
        navigator.summon_target = None
        navigator.summon_hold = 0
        return None
    path = found[1]
    if len(path) == 1:
        # On a pulling cell: hold for what follows; seen from here, its cell is read by _note_group.
        if close:
            return None
        here = _cell(snapshot.player.position)
        basis = navigator.summon_hold_basis
        if basis is None or basis[:2] != (navigator.summon_target, here):
            # The wait begins on this cell (owner 2026-11-25 (b)-6): how many others act on it now.
            navigator.summon_hold_basis = (navigator.summon_target, here, found[0])
        return _hold_for(policy, navigator)
    return quest_plan_base._path_step(policy, snapshot, path, LURE_WALK_REASON)


def after_key(policy, snapshot, navigator, plan, board) -> str | None:
    """The steps after the disengage (module docstring), until the group is gone."""
    if (not answers(plan) or navigator.summon_state not in AFTER_STATES
            or snapshot.player.blind or snapshot.player.confused):
        return None
    acting = acting_around(policy, snapshot, navigator)
    if (struck := _strike_around(policy, snapshot, board, acting)) is not None:
        navigator.summon_hold = 0
        return struck
    # What fires at the player from out of view and no blow or shot reaches: no wait in its line
    # (owner 2026-11-19 「有効な場所で待つ」), closed on to be shot or left (``fire_answer_key``).
    # One in view that never comes and that no blow or shot above reached is closed on the same way
    # (``stranded``, ``attack_cells``): the hold below would wait in its line for nothing.
    indices = {monster.index for monster in acting}
    firers = [*(monster for monster in board.firing if monster.index in indices),
              *stranded(policy, snapshot, navigator, plan, board, acting)]
    if (answered := fire_answer_key(policy, snapshot, navigator, plan, board, firers)) is not None:
        return answered
    # n1-c life-217 (2026-11-19 18:32-19:05, 15,900 holds at [2,56]): two ボーシン awake beyond the
    # pits acted on the player (within their vision) and no walk reaches them.  Past the wait they
    # are left to the plan like any member no walk reaches (``_unreached``): the rest, the lure of
    # the others and the plan's own sweep go on.
    unreached = _unreached(navigator, board)
    acting = [monster for monster in acting if monster.index not in unreached]
    # Owner 2026-11-25 「休憩して魔法道具の使用回数を戻せる場合はその限りではない」: a member that never comes
    # and that the Magic-Eater rests for is neither waited for nor closed on until its power is back
    # (``_recharge_key`` below), nor left as one no walk reaches.
    recharging = _recharging(policy, snapshot, navigator)
    acting = [monster for monster in acting if monster.index not in recharging]
    # Owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で待つ」: held for only while one
    # of them will come (their kept verdict, ``never_comes``, owner 2026-11-25 (b)-3: one reading,
    # not a reading of its own each board); else closed on at once, as past the wait.  The cap run
    # out, the verdicts are read again once.
    coming = [monster for monster in acting
              if not _comes_not(policy, snapshot, navigator, plan, board, monster)]
    if coming and navigator.summon_hold >= int(plan.get("enemy_wait_turns", 0)):
        _rejudge_after_wait(navigator, [monster.index for monster in coming])
        coming = [monster for monster in coming
                  if not _comes_not(policy, snapshot, navigator, plan, board, monster)]
    if coming and navigator.summon_hold < int(plan.get("enemy_wait_turns", 0)):
        return _hold_for(policy, navigator)
    if acting:
        # Past the plan's wait they have not come: each is closed on as a lure (step 4), those no
        # walk reaches a cell they would be seen from are left to the plan.
        for monster in acting:
            if _lure_path(policy, snapshot, navigator, plan, board, monster.index, close=True) is None:
                _mark_unreached(navigator, monster.index)
        acting = [monster for monster in acting if monster.index not in navigator.summon_unreached]
    if acting:
        if navigator.summon_target not in {monster.index for monster in acting}:
            navigator.summon_target = min(acting, key=lambda monster: (
                not monster.can_summon, snapshot.player.position.distance_to(monster.position))).index
        navigator.summon_state = LURING
        return _lure(policy, snapshot, navigator, plan, board)
    if navigator.summon_target is None:
        # Nothing acts on the player and nothing is lured: the next one to act starts its own wait.
        navigator.summon_hold = 0
    if (rested := _rest_key(policy, snapshot)) is not None:
        return rested
    # Owner 2026-11-25 (c)-1: the absorbed Teleportation short, a rest out of the lines first.
    if (rested := teleport_rest_key(policy, snapshot, navigator, plan, board)) is not None:
        return rested
    if recharging and (recharged := _recharge_key(policy, snapshot, navigator, plan, board, recharging)) is not None:
        return recharged
    if not navigator.summon_group:
        navigator.summon_state = None
        navigator.summon_target = None
        navigator.summon_hold = 0
        return None
    navigator.summon_state = LURING
    return _lure(policy, snapshot, navigator, plan, board)
