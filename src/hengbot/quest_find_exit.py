"""A FIND_EXIT quest's floor: walk to the exit, fighting at chokes one by one.

``engagement_plan.find_exit`` on an approved strategy is the data:

 * ``choke_cells``: the cells to stand on while an awake enemy is about, chosen from
   the map (QUEST_18's plan gives its reasons);
 * ``choke_hold_turns``: how long one choke waits for an enemy that does not come;
 * ``rest_below_ratio``: below this HP the quiet floor is rested on before walking on.

``engagement_plan.sealed_races`` are monsters no route reaches; they count for nothing
here.  ``find_exit.exposure_races`` are never-moving casters: the cells their spells reach
are derived from the map (quest_exposure).  Owner 2026-11-04 「叫びを受ける位置を特定して
可能な限り避ける」: the walk takes the fewest such cells, nobody holds, rests or fights by
choice on one, and on one the walk goes on to the next free cell unless a monster
is in the only way.  A shriek wakes the whole floor and hastes every monster the player
has in view (spells-sight.cpp aggravate_monsters); n1-a took 47 of them on one cell and died.

Game (C:/hengband/src, player-move.cpp:256): stepping on the QUEST_EXIT of a FIND_EXIT
quest completes it there and then and leaves the floor; no stair command is sent, and
a Word of Recall under way is cancelled (word_recall = 0).  Nothing needs killing.

Owner 2026-11-04, Q18: 「狭い閉鎖空間であるため、隔離されているクラーケン二種以外との戦闘は
基本的には回避できない。隘路で各個撃破することを目標とする。」 and for an emergency
「薬で戦い線より下で帰還」: at the choke with Healing and Speed potions, and below the
strategy's line (``abort_conditions.hp_ratio``) with an enemy, Recall is read and the
fight goes on with potions and blows until it fires.  Cure Critical Wounds is no HP
recovery (owner 2026-11-03).  With no enemy the floor is rested on (owner 2026-11-03).

Owner 2026-11-04 「隘路で敵を十分倒してから先に進むことを明記する」: on an unexposed choke
nothing advances while ``comes_for_player`` holds for an awake enemy in view, or one known
beside the next leg.  ``choke_hold_turns`` ends only a wait with no such enemy, the quiet
wait after a fight on that choke; ``choke_enemy_wait_turns`` is the far bound on an enemy
that stays in view without ever making contact (a blow resets it).  With nothing fought or
known, the walk goes on at once.  An enemy that does not come does not freeze the walk: it
is shot from the choke when it stands in the way, otherwise passed.  A sleeper stays asleep
unless it is in the way or beside the next choke.

Owner 2026-11-06 「来ない遠くの敵を理由に隘路へ戻らないようにし」: a far (ESP-detected only)
mover sends the walk to a choke, or stops a dig, only once it is seen to close in
(``approaching``) or stands beside the walk ahead; a walk to a choke, once begun, goes on
while that reason holds instead of turning back to the exit cell by cell.

Owner 2026-11-08 「見えていても移動経路があるとは限らない。50行動で来なければ経路がないと判断
する。」: a monster in view with a walk to the player gets IN_VIEW_WAIT_ACTIONS player actions to
come (beside the player, or nearer); spent, it is no longer coming until it does
(``_in_view_waits``).  Within its wait it keeps a walk to a choke and the choke's wait going
when the walk takes the player out of its sight.  ``choke_enemy_wait_turns`` stays the bound
on one that keeps coming without contact.

``find_exit.dig_cells`` are veins the walk opens.  Owner 2026-11-04 「簡単に掘れるので道具が
なくても必ず掘る。」.  Game: exe_tunnel (tunnel-execution.cpp:53) on a vein without CAN_DIG
succeeds when skill_dig > power + randint0(40 * power), power 10 for magma on water, one
player turn a try and the T command repeats itself (always_repeat); a skill of 10 or less never
succeeds, so ``dig_attempt_limit`` bounds the commands and the walk falls back to the undug
route.  No tool, no weapon swap.  An enemy that comes is answered first, at a choke; the
dig resumes after.  Route planning counts the cell as open; what a caster reaches now is
derived from the cells really opened, since a hole opens lines of fire too.

Owner 2026-11-04 「叫ばれる条件とテレポートバックを受ける条件は少し異なる。テレポートバックは
確実に避けるべきなので条件を把握すること。」: a pull cell (quest_exposure ``pull``) is forbidden, not
costed: ``pull_cells`` is every walk's blocked set here and ``pull_step_refused`` the net in
_step_toward for every other walker.  A player already on one takes the walk with the fewest
of them, under PULLED_BACK_REASON.

Owner 2026-11-04, when a vein will not open: 「可能な限り多くのモンスターを事前に倒してから引き寄せの
マスを進む」.  With no pull-free way on, ``_clear_key`` kills first: what comes is fought at the
chokes, and each mapped mover's cell is visited from a cell off the pull lines.
``clearing_finished``: no awake enemy comes and no such cell is left, or ``clear_turn_limit``
is spent, so it cannot freeze.  Only then does ``_pull_walk`` cross, under PULL_WALK_REASON.

Owner 2026-11-04, the approved strategy's ``engagement_plan.max_simultaneous_melee``: no more
than that many fight the player at once.  n1-a life 515 (2026-11-12 15:14, decisions
48625-48632) stood on (3,20), off the choke, and meleed two seahorses 443 and a giant squid
482 beside it until it died.  More than the cap beside the player walks it back to the
nearest unexposed choke (``_melee_cap_retreat``), and no walk steps onto a cell where more
than the cap would stand beside it (``_crowded_step``).  The count is of the monsters that
come (``_Board.crowders``), so one that never comes cannot freeze a walk.

Its required force (n1-a life 515, the same death): accepted at max HP 716 on the row of
700, the seahorses' LOSE_CON bites drained it to 641 before the last fight.  Max HP below
the ``min_hp`` of the row the floor was entered under (``entry_force_min_hp``, recorded on
the floor's first board) is the strategy's line crossed (once_quest_recall.below_entry_force),
as the HP ratio is: with an enemy, Recall is read.

Owner 2026-11-12 (the same death and n1-a life 516):
 * 「加速手段を十分数確保することを必須にする。」: every row of QUEST_18 is ``always_hasted``
   (quest_plan_base._speed doses while an enemy comes and the haste is off) and its Speed
   doses are asked at acceptance and at the entrance (quest_force_rows.departure_speed_short).
 * Shrieker mushrooms 40: 「セイレーンと同じに扱う」: in ``exposure_races``; the pull (the
   forbidden cells) is the TELE_TO casters' only, ``find_exit.pull_races``.
 * A choke spent by its quiet wait is the retreat again while an enemy in view comes
   (``_readmitted``): life 515 left (1,19) for (3,22) across the open with a seahorse coming.

Owner 2026-11-22 (n1-b life-414, the fourth Q18 death), verbatim 「叫びを受けた理由を調査すること。
受けないように立ち回る指示なので。」: the walk took the plan's own route ([1,16] [1,17] [2,18] are
three of its eleven shouted cells: beside (2,17), the one cell of that corridor the siren on (6,14)
has a direct line to, through the gap (3,16); the corridor's other walls are permanent, "X" of
QuestPreferences).  What the shrieks woke and hasted came on after it: life-414 heard them on
(1,16) and (2,18), went on from the choke (1,19) at once, and met two hasted seahorses and a squid
on the open (3,20).  The plan's 「目を覚ました敵がいる間は、叫びの届かない隘路に立って1体ずつ倒す」
and 「戦った隘路では、敵が見えなくなってからも30手待って何も来なければ進む」: a shriek heard
(mspell-floor.cpp spell_RF4_SHRIEK's 「がかん高い金切り声をあげた」, or aggravate_monsters'
stirring, spells-sight.cpp) sends the walk's next unexposed choke into the wait a fight does
(``_shriek_hold``), ``choke_hold_turns`` quiet turns before the walk goes on.

Owner 2026-11-25 「叫びの届かない隘路を先に」 (n1-b life-418 went back from (1,19) to (1,15),
(1,12) and (1,5) over the siren (6,14)'s reach and was shrieked at again and again): a shriek heard
names the plan's casters that reach the cell it was heard on (``_attribute_shriek``), and the walk
to a choke goes to one reached off their cells when there is one (``_choke_walk``).

Owner 2026-11-22 「使う」 to 「Q18 で即死の見込みがある時と帰還待ちの間に、敵を飛ばすテレポート・
アウェイを使ってよいか」: on the 即死 rung the plan's escape is Teleport Away at the worst hostile in
a beam's line before the Recall (``_instant_death_escape``), and while the Recall counts down
an enemy that comes is sent away before any retreat or blow (``_recall_wait_away``): the absorbed
rod, then the absorbed wand, then a carried one (quest_plan_base.hall_away_key).  The player's own
teleport stays unread (owner 2026-11-04).  Game: teleport_away (spells-teleport.cpp) skips
CAVE_NO_TELEPORT_DEST only outside quests and cave_monster_teleportable_bold never reads it, so
the monster lands on this floor's water; the seahorse 443 and the giant squid 482 have no RES_TELE
(MonraceDefinitions).

Owner 2026-11-22 「加速してから入る」 to 「叫びの届くマスへ入る前に加速が切れていたら、敵が見えて
いなくても取り込んだスピードか薬で加速するか」: a walk's step onto a shouted cell, the haste off,
is a Speed dose first, whatever is in view (``_haste_before_shouted``).  QUEST_18's doses went
from 12 to 17 for it (its rationale: one per shouted stretch a haste does not outlast).

``key`` runs before the shared survival ladders while an enemy is about on such a
floor: their answers walk away from the choke, which is what this plan refuses.  A
quiet board stays with them (food, light, the unseen) and reaches ``walk_key`` through
the navigator.
"""

from __future__ import annotations

from hengbot import combat_answer, left_cells, once_quest_recall, quest_exposure, quest_plan_base, resist_potion, summon_response
from hengbot import speed_dose, threat_tiers
from hengbot.model import Position
from hengbot.policy_constants import TUNNEL_KEY, WAIT_KEY
from hengbot.quest_navigator import QuestFloorNavigator
# The scaffolding shared with quest_room_sweep and quest25_battle; the names stay importable here.
from hengbot.quest_plan_base import (  # noqa: F401 -- re-exported
    CURE_REASON,
    DEFAULT_SPEED_RATIO,
    HEAL_REASON,
    HOLD_REASON,
    MELEE_REASON,
    PERMANENT_HASTE_SPEED,
    RECALL_REASON,
    SPEED_REASON,
    STARVING,
    _cell,
    _cure,
    _heal,
    _healing_potion,
    _never_moves,
    _path_step,
    _rank,
    _rest,
    _speed,
    steps_aside_for_food,
)

TO_CHOKE_REASON = "quest-strategy:exit-to-choke"
WALK_REASON = "quest-strategy:exit-walk"
STEP_ON_EXIT_REASON = "quest-strategy:exit-step"
DIG_REASON = "quest-strategy:exit-dig"
PULLED_BACK_REASON = "quest-strategy:exit-pulled-back"
PULL_REFUSED_REASON = "quest-strategy:pull-cell-refused"
CLEAR_REASON = "quest-strategy:exit-clear-first"
PULL_WALK_REASON = "quest-strategy:exit-pull-walk"
MELEE_CAP_REASON = "quest-strategy:exit-crowd-back"
# Owner 2026-11-22 「使う」: Teleport Away at an enemy on the 即死 rung and in the Recall's countdown.
AWAY_REASON = "quest-strategy:exit-teleport-away"
# A shriek reached the player: the caster's line (mspell-floor.cpp spell_RF4_SHRIEK) or what it
# stirred (spells-sight.cpp aggravate_monsters), in both languages.
SHRIEK_MARKS = ("金切り声をあげた", "makes a high pitched shriek", "突如興奮した", "sudden stirring")
_PLANNED_STEPS = frozenset({TO_CHOKE_REASON, WALK_REASON, STEP_ON_EXIT_REASON, DIG_REASON,
                           PULLED_BACK_REASON, CLEAR_REASON, PULL_WALK_REASON, MELEE_CAP_REASON})


# Going round a monster on the way costs at most this many steps, else it is fought.
SIDESTEP_LIMIT = 2
VEIN_DIG_POWER = 10  # TerrainDefinitions MAGMA_VEIN_ON_DEEP_WATER tunnel power
# A far (detected only) monster comes when, within this many game turns (20 player turns
# at normal speed), it has closed APPROACH_CELLS on the player; a step back and forth
# never does.
APPROACH_WINDOW = 200
APPROACH_CELLS = 2
# Owner 2026-11-08 「見えていても移動経路があるとは限らない。50行動で来なければ経路がないと判断
# する。」: player actions an awake monster in view gets to come (beside the player, or nearer).
IN_VIEW_WAIT_ACTIONS = 50


def _plan(policy, snapshot) -> dict | None:
    """The plan of the TAKEN quest on this floor; a completed one has left the floor."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    return None if profile is None else profile.engagement_plan.get("find_exit")


def holds_choke(policy, snapshot) -> bool:
    """This board's wait is a choke hold of such a floor: under fire it still holds."""
    return policy.last_reason == HOLD_REASON and _plan(policy, snapshot) is not None


def planned_step(policy, snapshot) -> bool:
    """This board's step is the plan's own: the low-HP walk gate does not rewrite it."""
    return policy.last_reason in _PLANNED_STEPS and _plan(policy, snapshot) is not None


def sealed_races(profile) -> frozenset[int]:
    return frozenset(profile.engagement_plan.get("sealed_races", ()))


def _navigator(policy, snapshot, quest_id: int) -> QuestFloorNavigator:
    """The plans' navigator (quest_plan_base), over deep water too, with the planned veins dug."""
    navigator = quest_plan_base._navigator(policy, snapshot, quest_id)
    navigator.allow_deep_water = True  # hp-mp-processor.cpp:210 drowns only the overweight
    plan = _plan(policy, snapshot)
    if plan is not None:
        _observe_digs(snapshot, navigator, plan)
        _record_entry_force(policy, snapshot, navigator, quest_id)
        _observe_shriek(snapshot, navigator)
        _attribute_shriek(snapshot, navigator, plan)
    return navigator


def _observe_shriek(snapshot, navigator) -> None:
    """A shriek reached the player on this board: what it woke and hasted may come
    (``_shriek_hold``).  Not on the choke a fight or the last shriek holds the walk on
    (``exit_fought_at``): that wait is under way, and one each shriek restarted might not end."""
    if snapshot.player.position == navigator.exit_fought_at:
        return
    if _heard_shriek(snapshot):
        navigator.exit_shrieked = True


def _heard_shriek(snapshot) -> bool:
    return any(mark in message for message in snapshot.messages for mark in SHRIEK_MARKS)


def _attribute_shriek(snapshot, navigator, plan) -> None:
    """A shriek heard on this board: the plan's casters that reach the player's cell are the
    ones that shriek (``exit_shriekers``, ``_shriek_reach``).

    The line names no caster the player cannot see (「何かがかん高い金切り声をあげた」), so the
    cell it was heard on is the attribution: spell_RF4_SHRIEK (mspell-floor.cpp) is cast by
    make_attack_spell within the range 18, at the player's cell on a projectable line or aimed at
    a projectable cell beside him (quest_exposure, the map the plan already reads).  A caster that
    never shrieked (asleep, a sleeping one casts nothing, or gone) stays out of it."""
    if not _heard_shriek(snapshot):
        return
    casters = _exposure(navigator, plan).shout.get(_cell(snapshot.player.position), frozenset())
    if not casters <= navigator.exit_shriekers:
        navigator.exit_shriekers = navigator.exit_shriekers | casters


def _shriek_reach(navigator, plan) -> frozenset:
    """The cells a caster heard shrieking on this floor reaches, on the floor as it is."""
    if not navigator.exit_shriekers:
        return frozenset()
    return frozenset(Position(*cell) for cell, casters in _exposure(navigator, plan).shout.items()
                     if casters & navigator.exit_shriekers)


def _record_entry_force(policy, snapshot, navigator, quest_id: int) -> None:
    """The ``min_hp`` of the force row this character stands on, on the floor's first board
    (quest_force_rows.resolve, as acceptance read it).  The fight re-resolves its row each
    board, so a drained character would otherwise find a lower row and never cross."""
    if navigator.entry_force_min_hp is not None:
        return
    profile = policy.approved_quest_strategy(quest_id)
    if profile is None or "min_hp" not in profile.required_force:
        return
    force = policy._strategy_force_for_snapshot(snapshot, profile)
    navigator.entry_force_min_hp = int(force.get("min_hp", profile.required_force["min_hp"]))


_EXPOSURES: dict[tuple, quest_exposure.Exposure] = {}
_TERRAINS: dict[tuple, dict] = {}


def _opened_terrain(navigator, opened: frozenset) -> dict:
    """The quest map with these vein cells opened: DESTROYED leaves deep water."""
    key = (navigator.quest_id, opened)
    if key not in _TERRAINS:
        _TERRAINS[key] = {**navigator.battlefield.terrain, **{cell: "deep_water" for cell in opened}}
    return _TERRAINS[key]


def _exposure_with(navigator, plan, opened: frozenset) -> quest_exposure.Exposure:
    """The cells the plan's casters reach with these cells open, derived once."""
    races = tuple(plan.get("exposure_races", ()))
    pull_races = tuple(plan.get("pull_races", races))
    reach = tuple(sorted((int(race), int(cells))
                         for race, cells in plan.get("aimed_off_reach", {}).items()))
    key = (navigator.quest_id, races, pull_races, reach, opened)
    if key not in _EXPOSURES:
        placements = [(cell, race) for cell, race in navigator.battlefield.monster_placements
                      if race in races]
        by_race = dict(reach)
        _EXPOSURES[key] = quest_exposure.exposure_map(
            _opened_terrain(navigator, opened), [cell for cell, _ in placements],
            pullers={cell for cell, race in placements if race in pull_races},
            aimed_off_reach={cell: by_race[race] for cell, race in placements if race in by_race})
    return _EXPOSURES[key]


def _exposure(navigator, plan) -> quest_exposure.Exposure:
    """What the casters reach on the floor as it is now."""
    return _exposure_with(navigator, plan, navigator.exit_dug)


def _planned_open(navigator, plan) -> frozenset:
    """The cells the route counts as open: dug, or still to be dug."""
    wanted = frozenset(tuple(cell) for cell in plan.get("dig_cells", ()))
    return (wanted - navigator.exit_abandoned_digs) | navigator.exit_dug


def pull_cells(navigator, plan) -> frozenset:
    """Where a caster's direct line reaches, on the floor as it is or as planned."""
    now = _exposure_with(navigator, plan, navigator.exit_dug).pull
    planned = _exposure_with(navigator, plan, _planned_open(navigator, plan)).pull
    return frozenset(now) | frozenset(planned)


def pull_step_refused(policy, snapshot, step: Position) -> bool:
    """A walker other than the way back is about to step onto a pull cell of this floor."""
    plan = _plan(policy, snapshot)
    if plan is None or policy.last_reason in {PULLED_BACK_REASON, PULL_WALK_REASON}:
        return False
    navigator = policy._quest_navigators.get(snapshot.floor_key[2])
    if navigator is None:
        navigator = _navigator(policy, snapshot, snapshot.floor_key[2])
    return _cell(step) in pull_cells(navigator, plan)


def _observe_digs(snapshot, navigator, plan) -> None:
    """A planned vein the board shows open.  Other digs on the floor are not planned."""
    for raw in plan.get("dig_cells", ()):
        grid = snapshot.grid_at(Position(*raw))
        if grid is not None and grid.known and grid.passable:
            navigator.exit_dug = navigator.exit_dug | {tuple(raw)}


def _pulls(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "TELE_TO" in knowledge.abilities


def comes_for_player(policy, navigator, snapshot, monster) -> bool:
    """Awake, not NEVER_MOVE, and with a walk to beside the player for its kind of
    movement (an aquatic one in a sealed pocket has none)."""
    if monster.asleep or _never_moves(policy, monster):
        return False
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    flags = knowledge.flags if knowledge is not None else frozenset()
    return quest_exposure.can_reach(navigator.battlefield.terrain, flags,
                                    _cell(monster.position), _cell(snapshot.player.position))


def _track(navigator, snapshot, known) -> None:
    """Each known monster's cells over the last APPROACH_WINDOW game turns of this floor."""
    turn = snapshot.turn
    tracks = {}
    for index, (race, history) in navigator.exit_tracks.items():
        history = tuple(row for row in history if turn - APPROACH_WINDOW <= row[0] <= turn)
        if history:
            tracks[index] = (race, history)
    for monster in known:
        race, history = tracks.get(monster.index, (monster.race_id, ()))
        if race != monster.race_id:
            history = ()  # the index went to another monster
        tracks[monster.index] = (monster.race_id, history + ((turn, _cell(monster.position)),))
    navigator.exit_tracks = tracks


def approaching(navigator, snapshot, monster) -> bool:
    """Seen to close in: over its track of the window, nearer the player by APPROACH_CELLS.

    Owner 2026-11-06 「来ない遠くの敵を理由に隘路へ戻らないようにし」: whether a far
    monster comes is what it did, not a static walk to the player.  Both cells are measured
    to where the player is now, so the player's own walk does not count as its approach;
    a monster stepping back and forth one cell (n1-a life 490, seahorse 443 at (9,6) and
    (10,6) the whole time) never does.  A monster first known on this board has done
    nothing yet.
    """
    _, history = navigator.exit_tracks.get(monster.index, (monster.race_id, ()))
    if not history:
        return False
    player = _cell(snapshot.player.position)
    farthest = max(quest_exposure.game_distance(cell, player) for _, cell in history)
    now = quest_exposure.game_distance(_cell(monster.position), player)
    return farthest - now >= APPROACH_CELLS


def _outwaited(navigator, monster) -> bool:
    """A far monster that only stood beside the walk ahead through a choke's whole enemy bound.

    Owner (QUEST_18 formation): 「次の隘路までの道の隣に来る敵がいると分かっている間は進まない」 and
    「200手の打ち切りで終えた隘路は戻さない」: the bound (``choke_enemy_wait_turns``) ends the wait
    for it, and the walk goes on.  n1-a life 523 (2026-11-15 05:37, warrior Lv35, floor (0,35,18),
    three loop stops): the giant squid 482 on (5,26), beside the dig (5,25) and known by ESP only,
    held the choke (1,19) its 200 actions; still beside the walk ahead of (1,19), it then sent the
    walk to the choke behind, and on (2,18), where the walk ahead ends at (1,19), it was no reason,
    so the walk turned back: (1,19) '1' exit-to-choke, (2,18) '9' exit-walk, until the stop.  Game:
    it never came: its distance 9 (monster-update.cpp, cdis) is over its vision 8
    (MonraceDefinitions) and its cell was never in the player's view, so it is not processed at
    all (monster-processor.cpp decide_process_continue).  Seen to close in (``approaching``) it
    is a reason again."""
    return navigator.exit_outwaited.get(monster.index) == monster.race_id


def _count_action(navigator, snapshot) -> None:
    """One player action per board (``key`` and ``walk_key`` may both read one)."""
    if navigator.exit_action_turn != snapshot.turn:
        navigator.exit_action_turn = snapshot.turn
        navigator.exit_actions += 1


def _seen_gone(snapshot, cell: tuple[int, int]) -> bool:
    """The cell a monster was last seen on is in the player's view now with nobody on it."""
    grid = snapshot.grid_at(Position(*cell))
    return (grid is not None and grid.visibility_flags_present and grid.in_view
            and not grid.has_monster)


def _in_view_waits(navigator, snapshot, coming, known, sensed=()) -> tuple[list, list]:
    """Owner 2026-11-08 「見えていても移動経路があるとは限らない。50行動で来なければ経路がない
    と判断する。」 (n1-a life 495, floor (0,35,18): the swordfish 88 on (10,13), seen from
    (3,20) only, never moved; (3,20) stepped to the choke (1,19) and (2,20), out of its
    sight, stepped back to the exit, until the loop guard stopped the bot three times).

    A monster in view with a static walk to the player (``comes_for_player``) has
    IN_VIEW_WAIT_ACTIONS player actions from first being seen to come: beside the player,
    or on a cell nearer the player than the one its wait began on (both measured to where
    the player is now, so the player's own walk does not count).  Either starts its wait
    again; spent, it has no route and comes no more until it does.  The detected-only rule
    (``approaching``, owner 2026-11-06) is not touched.

    Returns the monsters in view still within their wait, and the ones within their wait
    out of sight now: never beside the player, last seen at their cell and not seen gone
    from it.  These keep a walk to a choke and its wait going, so the choke the walk went
    to out of their sight is not left for the cell they are seen from, one step each
    (``mobile_awake``); they are no enemy in view (``coming_in_view``).

    Out of sight includes known by telepathy or detection only (``sensed``: the reachable awake
    ones, ``perception`` "detected"): one within its wait, never beside the player since it
    began, is remembered at the cell the board shows it on, not read anew by the far rule
    (``approaching``); one that met the player is read anew, as one not known at all.
    n1-b life-418 (2026-11-25 06:22, Magic-Eater Lv38 with telepathy, floor (0,35,18)): the
    giant squid 482 on (9,24), first seen from (3,20) at distance 6, sent '8' exit-to-choke onto
    (2,20); there, out of sight and shown by ESP only, it was the far rule's, not closing in,
    and '2' exit-walk stepped back onto (3,20), until the ping-pong guard escalated to the
    livelock stop.
    """
    player = _cell(snapshot.player.position)
    now = navigator.exit_actions
    entries = dict(navigator.exit_in_view)
    waiting = []
    for monster in coming:
        cell = _cell(monster.position)
        distance = quest_exposure.game_distance(cell, player)
        race, began, origin, _, far = entries.get(monster.index, (None, now, cell, None, True))
        if (race != monster.race_id or distance <= 1
                or distance < quest_exposure.game_distance(origin, player)):
            began, origin = now, cell
        entries[monster.index] = (monster.race_id, began, origin, monster, far and distance > 1)
        if now - began < IN_VIEW_WAIT_ACTIONS:
            waiting.append(monster)
    known_indices = {monster.index for monster in known}
    sensed_now = {monster.index: monster for monster in sensed}
    remembered = []
    for index, (race, began, _, last, far) in list(entries.items()):
        monster = sensed_now.get(index)
        if monster is not None and monster.race_id == race:
            if not far:
                del entries[index]  # met: seen again, it starts anew
            elif now - began < IN_VIEW_WAIT_ACTIONS:
                remembered.append(monster)
            continue
        if index in known_indices:
            continue
        if not far or _seen_gone(snapshot, _cell(last.position)):
            del entries[index]  # met, or gone from where it stood: seen again, it starts anew
        elif now - began < IN_VIEW_WAIT_ACTIONS:
            remembered.append(last)
    navigator.exit_in_view = entries
    return waiting, remembered


class _Board:
    """The enemies of one board, as this plan weighs them."""

    def __init__(self, policy, snapshot, profile, navigator):
        sealed = sealed_races(profile)
        position = snapshot.player.position
        known = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                 if monster.hostile and monster.race_id not in sealed]
        self.in_view = [monster for monster in known if monster.perception != "detected"]
        self.occupied = {monster.position for monster in known}
        # The cells an owner left (left_cells): the walks below keep off them while a way off
        # them leads on (owner 2026-11-15, maintainability review Q2 「記録は読ませる・危ない範囲は
        # 今のまま」; the areas round a monster stay out).
        self.left = frozenset(left_cells.refused(policy, snapshot) - {snapshot.player.position})
        _track(navigator, snapshot, known)
        _count_action(navigator, snapshot)
        # A monster that cannot come is no reason to hold a choke; one beside the player
        # is left behind by walking on (a siren's pull ends beside it, 840 HP unfought).
        self.reachable_awake = [monster for monster in known
                                if comes_for_player(policy, navigator, snapshot, monster)]
        sensed = [monster for monster in self.reachable_awake if monster.perception == "detected"]
        self.coming_in_view, remembered = _in_view_waits(
            navigator, snapshot,
            [monster for monster in self.reachable_awake if monster.perception != "detected"],
            known, sensed)
        # What sends the walk to a choke or stops a dig: one in view, a far one seen to
        # close in, or one beside the walk ahead (in the way, moving or not).  A far one
        # that does not come is no reason (owner 2026-11-06).
        # One a choke's enemy bound already outwaited there (``_outwaited``) is no reason
        # beside the walk ahead until it is seen to close in.
        # One sensed within the wait it began in view is remembered (``_in_view_waits``): the
        # in-view verdict holds for it, the far rule does not read it a second time.
        waiting = {monster.index for monster in remembered}
        far = [monster for monster in sensed if monster.index not in waiting]
        leg = (_next_leg(navigator, _plan_of(profile), position)
               if any(not approaching(navigator, snapshot, monster)
                      and not _outwaited(navigator, monster) for monster in far) else [])
        self.mobile_awake = [*self.coming_in_view, *(
            monster for monster in far
            if approaching(navigator, snapshot, monster)
            or (not _outwaited(navigator, monster)
                and any(monster.position.distance_to(cell) <= 1 for cell in leg))), *remembered]
        # Of those, the far ones only beside the walk ahead (what ``_hold``'s bound outwaits).
        self.beside_leg = [monster for monster in far if monster in self.mobile_awake
                           and not approaching(navigator, snapshot, monster)]
        self.adjacent_mobile = [monster for monster in self.coming_in_view
                                if monster.position.distance_to(position) <= 1]
        # What the melee cap counts: what comes (in view within its wait, far and closing in,
        # or remembered), and what can come and is beside the player already.
        crowders = {monster.index: monster for monster in self.mobile_awake}
        crowders.update((monster.index, monster) for monster in self.reachable_awake
                        if monster.position.distance_to(position) <= 1)
        self.crowders = list(crowders.values())
        # A never-moving puller (a siren's TELE_TO) in view: no place to rest, and an
        # enemy for the line, but the answer to it is to walk out of its sight.
        self.pulling = [monster for monster in self.in_view
                        if not monster.asleep and _never_moves(policy, monster)
                        and _pulls(policy, monster)]
        self.hit_by_unseen = once_quest_recall._hit_by_unseen(policy, snapshot)
        # Known by telepathy or detection only and hurting the player from where it stands
        # (quest_plan_base.fires_at_player, n1-c life-220 2026-11-22): it acts on him now.
        self.firing = [monster for monster in known if monster.perception == "detected"
                       and quest_plan_base.fires_at_player(policy, snapshot, monster)]
        # The plan's contract (quest_plan_base.Contract): its chokes, no cell refused outright (the
        # walks keep off the left cells while a way off them leads on), its rest line.
        plan = _plan_of(profile)
        self.contract = quest_plan_base.Contract(
            stand_cells=frozenset(tuple(cell) for cell in plan.get("choke_cells", ())),
            recovery_line=quest_plan_base.recovery_line_of(plan))

    @property
    def engaged(self) -> bool:
        """Something can act on the player now: the potions and the fight are for this."""
        return bool(self.coming_in_view or self.hit_by_unseen or self.firing)

    @property
    def acting(self) -> list:
        """What acts on the player now (quest_plan_base ``Board.acting``, read by ``_speed``)."""
        return [*self.coming_in_view, *self.firing]

    @property
    def enemy_for_the_line(self) -> bool:
        return self.engaged or bool(self.pulling)


def _exit_cell(navigator) -> Position:
    return Position(*navigator.battlefield.exit)


def _step_on_exit(policy, snapshot, navigator, board) -> str | None:
    """The exit beside the player and free: the quest is done and the danger behind."""
    exit_cell = _exit_cell(navigator)
    if (snapshot.player.position.distance_to(exit_cell) > 1
            or exit_cell in board.occupied):
        return None
    return quest_plan_base.plan_walk(policy, snapshot, exit_cell, STEP_ON_EXIT_REASON)


def _below_line_recall(policy, snapshot, profile, *, line=True) -> str | None:
    """Recall below the strategy's line.  ``line=False``: the plan's escape asked by its 即死
    rung, whatever the HP (threat_tiers.instant_death_key)."""
    ratio = profile.abort_conditions.get("hp_ratio")
    if line and (ratio is None or (snapshot.player.hp_ratio > float(ratio)
                                   and not once_quest_recall.below_entry_force(policy, snapshot))):
        return None
    if snapshot.player.blind or snapshot.player.confused:
        return _cure(policy, snapshot)  # the scroll cannot be read until it is cured
    return once_quest_recall.read_key(policy, snapshot, RECALL_REASON)


def _chokes(navigator, plan, board=None) -> set[Position]:
    """The unexposed chokes worth waiting on.  With ``board`` showing an enemy in view that
    comes, the ones whose quiet wait ran out are worth it again (``_readmitted``)."""
    exposure = _exposure(navigator, plan)
    spent = navigator.exit_spent_chokes - _readmitted(navigator, board)
    return {Position(*cell) for cell in plan["choke_cells"]
            if not exposure.exposed(tuple(cell))} - spent


def _readmitted(navigator, board) -> frozenset:
    """Owner 2026-11-12, n1-a life 515: the choke (1,19), spent by its quiet wait (decision
    48623), was left for (3,22) across the open (2,20) and (3,20) while a seahorse came in
    sight (48624); the retreat goes to it again.

    Only a choke spent by ``choke_hold_turns`` (nothing came) comes back, and only for an
    enemy in view that comes and whose in-view wait (``_in_view_waits``: first seen, or last
    come nearer) began at or after that choke was spent: what the choke already waited for
    does not send the walk back to it (n1-a life 495's swordfish, seen from (3,20) only and
    never moving, would rock the walk between (3,20) and (1,19)).  One spent by
    ``choke_enemy_wait_turns`` (an enemy in view that never made contact) stays spent, so
    that bound still ends its wait."""
    if board is None or not board.coming_in_view:
        return frozenset()
    began = [navigator.exit_in_view.get(monster.index, (None, navigator.exit_actions))[1]
             for monster in board.coming_in_view]
    newest = max(began)
    return frozenset(choke for choke, spent_at in navigator.exit_quiet_spent.items()
                     if choke in navigator.exit_spent_chokes and newest >= spent_at)


def _next_leg(navigator, plan, position: Position) -> list[Position]:
    """The walk ahead up to and including the next choke."""
    chokes = {Position(*cell) for cell in plan["choke_cells"]}
    leg = []
    for cell in _least_exposed(navigator, plan, position, {_exit_cell(navigator)})[1:]:
        leg.append(cell)
        if cell in chokes:
            break
    return leg


def _must_wait(navigator, plan, position, board) -> bool:
    """An awake enemy that comes is in view, or known beside the next leg."""
    if board.coming_in_view:
        return True
    leg = _next_leg(navigator, plan, position)
    return any(monster.position.distance_to(cell) <= 1
               for monster in board.mobile_awake for cell in leg)


def _hold(policy, snapshot, navigator, plan, position, board) -> str | None:
    """Wait on this choke for what comes; a shot first.  None once its wait is spent."""
    if navigator.exit_hold_cell != position:
        navigator.exit_hold_cell, navigator.exit_hold_turns = position, 0
        navigator.exit_enemy_turns = 0
    quiet = not _must_wait(navigator, plan, position, board)
    if not quiet:
        navigator.exit_fought_at = position
        navigator.exit_hold_turns = 0
        navigator.exit_enemy_turns += 1
        spent = navigator.exit_enemy_turns > int(plan["choke_enemy_wait_turns"])
    else:
        navigator.exit_hold_turns += 1
        spent = navigator.exit_hold_turns > int(plan["choke_hold_turns"])
    if spent:
        navigator.exit_spent_chokes = navigator.exit_spent_chokes | {position}
        navigator.exit_quiet_spent = _without(navigator.exit_quiet_spent, position)
        if quiet:
            navigator.exit_quiet_spent = {**navigator.exit_quiet_spent,
                                          position: navigator.exit_actions}
        else:
            navigator.exit_outwaited = {**navigator.exit_outwaited,
                                        **{monster.index: monster.race_id for monster in board.beside_leg}}
        navigator.exit_fought_at = None
        return None
    shot = (policy._ranged_attack_key(snapshot, board.coming_in_view, [])
            if board.coming_in_view else None)
    if shot is not None:
        return shot
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _wait_after_fight(policy, snapshot, navigator, plan, board) -> str | None:
    """Nothing in sight on the choke that fought: what the noise woke may still come."""
    position = snapshot.player.position
    _shriek_hold(navigator, plan, position)
    if navigator.exit_fought_at != position or position in navigator.exit_spent_chokes:
        return None
    return _hold(policy, snapshot, navigator, plan, position, board)


def _shriek_hold(navigator, plan, position: Position) -> None:
    """A shriek heard since the last choke (``_observe_shriek``), and the player on an unexposed
    choke: it waits there as the choke that fought does (owner 2026-11-22, the module note;
    n1-b life-414 left (1,19) at once after the shrieks on (1,16) and (2,18) and died on (3,20)).
    A choke spent before is taken again and its waits start over."""
    if not navigator.exit_shrieked:
        return
    exposure = _exposure(navigator, plan)
    if [position.y, position.x] not in plan["choke_cells"] or exposure.exposed(_cell(position)):
        return
    navigator.exit_shrieked = False
    _start_over(navigator, position)
    navigator.exit_hold_cell = None
    navigator.exit_fought_at = position


def _clear_the_way_key(policy, snapshot, navigator, plan, board, path) -> str | None:
    """From a choke, a shot at what stands in the walk ahead and will not come, or sleeps
    in it or beside the next choke.  No shot to be had: the walk goes on."""
    position = snapshot.player.position
    chokes = {Position(*cell) for cell in plan["choke_cells"]}
    if position not in chokes or _exposure(navigator, plan).exposed(_cell(position)):
        return None
    leg = []
    for cell in path[1:]:
        leg.append(cell)
        if cell in chokes:
            break
    next_choke = leg[-1] if leg and leg[-1] in chokes else None
    targets = [
        monster for monster in board.in_view
        if not _never_moves(policy, monster) or monster.position in leg
    ]
    targets = [
        monster for monster in targets
        if monster.position in leg
        or (monster.asleep and next_choke is not None
            and monster.position.distance_to(next_choke) <= 1)
    ]
    return policy._ranged_attack_key(snapshot, targets, []) if targets else None


def _to_choke(policy, snapshot, navigator, plan, board) -> str | None:
    """Stand on the nearest choke still worth waiting on; None when there is none."""
    position = snapshot.player.position
    navigator.exit_choke_goal = None
    chokes = _chokes(navigator, plan, board)
    if position in chokes:
        _start_over(navigator, position)
        held = _hold(policy, snapshot, navigator, plan, position, board)
        if held is not None:
            return held
        if board.mobile_awake and all(monster in board.beside_leg and _outwaited(navigator, monster)
                                      for monster in board.mobile_awake):
            return None  # the bound outwaited all that held it: the walk goes on (_outwaited)
        chokes = _chokes(navigator, plan, board)
    path = _choke_walk(board, navigator, plan, position, chokes)
    if len(path) < 2:
        return None
    crowded = _crowded_step(policy, snapshot, navigator, plan, board, path[1])
    if crowded is not None:
        return crowded
    hasted = _haste_before_shouted(policy, snapshot, navigator, plan, path[1])
    if hasted is not None:
        return hasted
    navigator.exit_choke_goal = path[-1]
    _start_over(navigator, path[-1])
    return _path_step(policy, snapshot, path, TO_CHOKE_REASON)


def _choke_walk(board, navigator, plan, position: Position, chokes) -> list[Position]:
    """The walk to the choke ``_to_choke`` goes to: one that no cell a caster heard shrieking
    reaches lies on, else the least exposed and nearest as before.

    Owner 2026-11-25, to 「Q18 で隘路の待ちが尽きて別の隘路へ戻る時、叫ぶ敵の届くマスを通らない
    隘路を先に選びますか？」: 「叫びの届かない隘路を先に」.  n1-b life-418 (floor (0,35,18)) went back
    from (1,19) to (1,15), (1,12) and (1,5) over (2,18) (1,17) (1,16), the reach of the siren on
    (6,14) it had heard on (2,6), and was shrieked at there again and again.  Among such walks the
    plan's order holds (the fewest exposed cells, then the fewest steps); with none, the walk is
    the plan's as it was (there, the chokes past the vein (5,25) not yet dug)."""
    walk = _walk_off_left(board, navigator, plan, position, chokes, board.occupied, as_it_is=True)
    reach = _shriek_reach(navigator, plan) - {position}
    if not reach or not reach & set(walk[1:]):
        return walk
    clear = _walk_off_left(board, navigator, plan, position, chokes, board.occupied | reach,
                           as_it_is=True)
    return clear or walk


def _without(spent: dict, choke: Position) -> dict:
    return {cell: at for cell, at in spent.items() if cell != choke}


def _start_over(navigator, choke: Position) -> None:
    """A spent choke taken again (``_readmitted``): its waits start over there."""
    if choke not in navigator.exit_spent_chokes:
        return
    navigator.exit_spent_chokes = navigator.exit_spent_chokes - {choke}
    navigator.exit_quiet_spent = _without(navigator.exit_quiet_spent, choke)
    if navigator.exit_hold_cell == choke:
        navigator.exit_hold_cell = None


def _melee_cap(policy, navigator) -> int:
    profile = policy.approved_quest_strategy(navigator.quest_id)
    if profile is None:
        return 0
    return max(0, int(profile.engagement_plan.get("max_simultaneous_melee", 0)))


def _crowd(board, cell: Position) -> int:
    """The monsters that come and would stand beside ``cell``."""
    return sum(1 for monster in board.crowders if monster.position.distance_to(cell) <= 1)


def _back_to_a_choke(policy, snapshot, navigator, plan, board, cap: int) -> str | None:
    """A step toward the nearest unexposed choke (a spent one too) onto a cell with no more
    than ``cap`` beside it.  The choke's waits start over there."""
    position = snapshot.player.position
    exposure = _exposure(navigator, plan)
    chokes = [Position(*cell) for cell in plan["choke_cells"] if not exposure.exposed(tuple(cell))]
    if position in chokes:
        return None
    paths = [_walk_off_left(board, navigator, plan, position, {choke}, board.occupied, as_it_is=True)
             for choke in chokes]
    paths = sorted((path for path in paths if len(path) >= 2 and _crowd(board, path[1]) <= cap),
                   key=len)
    if not paths:
        return None
    goal = paths[0][-1]
    navigator.exit_spent_chokes = navigator.exit_spent_chokes - {goal}
    navigator.exit_quiet_spent = _without(navigator.exit_quiet_spent, goal)
    navigator.exit_choke_goal = goal
    return _path_step(policy, snapshot, paths[0], MELEE_CAP_REASON)


def _melee_cap_retreat(policy, snapshot, navigator, plan, board) -> str | None:
    """More than ``max_simultaneous_melee`` beside the player: back toward a choke."""
    cap = _melee_cap(policy, navigator)
    if not cap or _crowd(board, snapshot.player.position) <= cap:
        return None
    return _back_to_a_choke(policy, snapshot, navigator, plan, board, cap)


def _crowded_step(policy, snapshot, navigator, plan, board, step: Position) -> str | None:
    """A step onto a cell with more than the cap beside it, and more than here, is not taken:
    back toward a choke, or held here off the casters' reach.  None: the step is taken."""
    cap = _melee_cap(policy, navigator)
    if not cap:
        return None
    crowd = _crowd(board, step)
    if crowd <= cap or crowd <= _crowd(board, snapshot.player.position):
        return None
    back = _back_to_a_choke(policy, snapshot, navigator, plan, board, cap)
    if back is not None:
        return back
    if _exposure(navigator, plan).exposed(_cell(snapshot.player.position)):
        return None  # no hold on a shouted cell: the walk goes on
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _back_to_a_spent_choke(policy, snapshot, navigator, plan, board) -> str | None:
    """On a shouted cell with an enemy in view that comes and a choke behind spent by its quiet
    wait: the walk to the nearest free choke, that one included (``_readmitted``), rather than
    on along the shouted cells.

    Owner 2026-11-12 「(開けた所を次の隘路へ進まない)」: between the choke (1,19) and the next
    free one, (2,26), the way crosses the shriekers' (3,20) and (4,21); n1-a life 515 met the
    seahorses on (3,20).  With no such choke the shouted cell walks on as before (owner
    2026-11-04, 「次の届かないマスへ歩く」).  A pulled player and a floor still being cleared
    keep their own answers."""
    if (not _readmitted(navigator, board)
            or _cell(snapshot.player.position) in pull_cells(navigator, plan)
            or _floor_needs_clearing(navigator, plan)):
        return None
    return _to_choke(policy, snapshot, navigator, plan, board)


def _choke_walk_under_way(policy, snapshot, navigator, plan, board) -> str | None:
    """The walk to a choke goes on over cells that would otherwise walk to the exit.

    n1-a life 490 (2026-11-06): (1,8) stepped to the choke, the shouted (2,7) stepped to
    the exit, one cell each, until the loop guard stopped it; life 491 did the same between
    (5,23) and the dig at (5,25).  While what sent it there still holds, a shouted cell or a
    board with no enemy to strike goes on to the choke; it stops when that reason is gone.
    """
    goal = navigator.exit_choke_goal
    # A pulled player takes the way back by name (_advance); a floor that needs clearing has
    # its own answer to what comes and its own end (_clear_key, clear_turn_limit).
    if (goal is None or not board.mobile_awake or snapshot.player.position == goal
            or _cell(snapshot.player.position) in pull_cells(navigator, plan)
            or _floor_needs_clearing(navigator, plan)):
        navigator.exit_choke_goal = None
        return None
    return _to_choke(policy, snapshot, navigator, plan, board)


def _least_exposed(navigator, plan, start: Position, goals, blocked=(), *,
                   as_it_is: bool = False, left=frozenset()) -> list[Position]:
    """The least exposed walk over the planned floor, or (``as_it_is``) the present one; off
    the ``left`` cells (the board's left cells) when a way off them leads to a goal."""
    opened = navigator.exit_dug if as_it_is else _planned_open(navigator, plan)

    def walk(off) -> list:
        return quest_exposure.least_exposed_path(
            _opened_terrain(navigator, opened), _exposure_with(navigator, plan, opened),
            _cell(start), {_cell(goal) for goal in goals},
            frozenset(_cell(cell) for cell in off),
            forbidden=pull_cells(navigator, plan) - {_cell(start)})

    path = (walk(set(blocked) | set(left)) if left else []) or walk(blocked)
    return [Position(*cell) for cell in path]


def _walk_off_left(board, navigator, plan, start: Position, goals, blocked=(), *,
                   as_it_is: bool = False) -> list[Position]:
    """``_least_exposed`` off the board's left cells while a way off them leads on (the walks'
    one reading of the registry here, owner 2026-11-15 Q2)."""
    return _least_exposed(navigator, plan, start, goals, blocked, as_it_is=as_it_is, left=board.left)


def _off_left(board, walk, occupied: frozenset) -> list:
    """``walk(blocked)`` off the board's left cells too when that leads on, else as before."""
    left = frozenset(_cell(cell) for cell in board.left)
    return (walk(occupied | left) if left else []) or walk(occupied)


def _safe_region(navigator, plan) -> set:
    """The cells off every pull line from which the planned floor leads to the exit."""
    terrain = _opened_terrain(navigator, _planned_open(navigator, plan))
    forbidden = pull_cells(navigator, plan)
    start = _cell(_exit_cell(navigator))
    seen, pending = {start}, [start]
    while pending:
        cell = pending.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nxt = (cell[0] + dy, cell[1] + dx)
                if (nxt not in seen and nxt not in forbidden
                        and terrain.get(nxt) in {"deep_water", "shallow_water", "floor"}):
                    seen.add(nxt)
                    pending.append(nxt)
    return seen


def _way_back(policy, snapshot, navigator, plan, board) -> str | None:
    """Pulled onto a pull cell: over the floor as it is, the walk with the fewest of them
    to a cell the safe route goes on from."""
    position = _cell(snapshot.player.position)
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    exposure = _exposure_with(navigator, plan, navigator.exit_dug)
    goals = _safe_region(navigator, plan)
    occupied = frozenset(_cell(cell) for cell in board.occupied)
    path = (_off_left(board, lambda off: quest_exposure.least_exposed_path(
                terrain, exposure, position, goals, off), occupied)
            or quest_exposure.least_exposed_path(terrain, exposure, position, goals))
    if len(path) < 2:
        return None
    step = Position(*path[1])
    if step in board.occupied:
        blocker = next((monster for monster in board.in_view if monster.position == step), None)
        if blocker is not None:
            return combat_answer.strike_key(policy, snapshot, blocker, MELEE_REASON)
    return quest_plan_base.plan_walk(policy, snapshot, step, PULLED_BACK_REASON, reach=_exit_cell(navigator))


def _exposed_count(navigator, plan, path: list[Position]) -> int:
    exposure = _exposure_with(navigator, plan, _planned_open(navigator, plan))
    return sum(exposure.exposed(_cell(cell)) for cell in path)


def _dig(policy, snapshot, navigator, plan, board, profile, cell: Position) -> str | None:
    """The T command at a planned vein beside the player; a coming enemy is answered first."""
    skill = snapshot.player.digging_skill
    # exe_tunnel: skill_dig > power + randint0(40 * power); power 10 here, so 10 never opens it.
    hopeless = skill is not None and skill <= VEIN_DIG_POWER
    if not hopeless and (board.mobile_awake or board.adjacent_mobile or board.hit_by_unseen):
        return _fight(policy, snapshot, profile, navigator, plan, board)
    attempts = dict(navigator.exit_dig_attempts)
    attempts[_cell(cell)] = attempts.get(_cell(cell), 0) + 1
    navigator.exit_dig_attempts = attempts
    if hopeless or attempts[_cell(cell)] > int(plan["dig_attempt_limit"]):
        navigator.exit_abandoned_digs = navigator.exit_abandoned_digs | {_cell(cell)}
        return _advance(policy, snapshot, navigator, plan, board)
    policy.last_reason = DIG_REASON
    return TUNNEL_KEY + policy._direction_key(snapshot.player.position, cell)


def _floor_needs_clearing(navigator, plan) -> bool:
    """The entrance has no pull-free way to the exit any more: a vein did not open."""
    start = Position(*navigator.battlefield.player_start)
    return not _least_exposed(navigator, plan, start, {_exit_cell(navigator)})


def _unvisited_movers(policy, navigator, profile) -> dict[tuple[int, int], set]:
    """Each mapped mover's cell not yet seen empty, and the free cells to attack it from."""
    pull = pull_cells(navigator, _plan_of(profile))
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    sealed = sealed_races(profile)
    found: dict[tuple[int, int], set] = {}
    for cell, race in navigator.battlefield.monster_placements:
        if (race in sealed or cell in navigator.exit_cleared_placements
                or quest_plan_base.never_moves(policy, race)):
            continue
        found[cell] = {(cell[0] + dy, cell[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                       if (dy, dx) != (0, 0)
                       and terrain.get((cell[0] + dy, cell[1] + dx)) in {"deep_water", "shallow_water"}
                       and (cell[0] + dy, cell[1] + dx) not in pull}
    return found


def _plan_of(profile) -> dict:
    return profile.engagement_plan["find_exit"]


def _note_empty_placements(snapshot, navigator, board, movers) -> None:
    position = _cell(snapshot.player.position)
    occupied = {_cell(cell) for cell in board.occupied}
    for cell in movers:
        if quest_exposure.game_distance(cell, position) <= 1 and cell not in occupied:
            navigator.exit_cleared_placements = navigator.exit_cleared_placements | {cell}


def clearing_finished(navigator) -> bool:
    return navigator.exit_clearing_done


def _clear_key(policy, snapshot, navigator, plan, board) -> str | None:
    """Kill what can be fought off the pull lines; None when the clearing has ended."""
    profile = policy.approved_quest_strategy(navigator.quest_id)
    position = snapshot.player.position
    navigator.exit_clear_turns += 1
    if navigator.exit_clear_turns > int(plan["clear_turn_limit"]):
        navigator.exit_clearing_done = True
        return None
    exposed = _exposure(navigator, plan).exposed(_cell(position))
    if board.mobile_awake:
        moved = _to_choke(policy, snapshot, navigator, plan, board) if exposed else None
        answer = moved or _fight(policy, snapshot, profile, navigator, plan, board)
        if answer is not None:
            return answer
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    if exposed and snapshot.player.hp_ratio < float(plan["rest_below_ratio"]):
        # The rest comes off the shouted cells, before the next sleeper.
        path = _walk_off_left(board, navigator, plan, position,
                              {Position(*cell) for cell in plan["choke_cells"]}, board.occupied,
                              as_it_is=True)
        if len(path) >= 2:
            return quest_plan_base.plan_walk(policy, snapshot, path[1], CLEAR_REASON)
    movers = _unvisited_movers(policy, navigator, profile)
    _note_empty_placements(snapshot, navigator, board, movers)
    movers = _unvisited_movers(policy, navigator, profile)
    beside = next((monster for monster in board.in_view
                   if _cell(monster.position) in movers
                   and monster.position.distance_to(position) <= 1), None)
    if beside is not None:
        return combat_answer.strike_key(policy, snapshot, beside, MELEE_REASON)
    stands = {Position(*cell) for cells in movers.values() for cell in cells}
    path = _walk_off_left(board, navigator, plan, position, stands, board.occupied, as_it_is=True)
    if len(path) < 2:
        navigator.exit_clearing_done = True
        return None
    return _path_step(policy, snapshot, path, CLEAR_REASON)


def _pull_walk(policy, snapshot, navigator, plan, board) -> str | None:
    """The clearing is over: across the pull cells by the walk with the fewest of them."""
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    exposure = _exposure_with(navigator, plan, navigator.exit_dug)
    position, exit_cell = _cell(snapshot.player.position), {_cell(_exit_cell(navigator))}
    occupied = frozenset(_cell(cell) for cell in board.occupied)
    path = (_off_left(board, lambda off: quest_exposure.least_exposed_path(
                terrain, exposure, position, exit_cell, off), occupied)
            or quest_exposure.least_exposed_path(terrain, exposure, position, exit_cell))
    if len(path) < 2:
        return None
    step = Position(*path[1])
    if step in board.occupied:
        blocker = next((monster for monster in board.in_view if monster.position == step), None)
        if blocker is not None:
            return combat_answer.strike_key(policy, snapshot, blocker, MELEE_REASON)
    return quest_plan_base.plan_walk(policy, snapshot, step, PULL_WALK_REASON, reach=_exit_cell(navigator))


def _off_the_pull_lines(policy, snapshot, navigator, plan, board) -> str | None:
    """Pulled while the clearing runs: back to the nearest cell off the lines."""
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    exposure = _exposure_with(navigator, plan, navigator.exit_dug)
    pull = pull_cells(navigator, plan)
    goals = {cell for cell, kind in terrain.items()
             if kind in {"deep_water", "shallow_water"} and cell not in pull}
    occupied = frozenset(_cell(cell) for cell in board.occupied)
    path = _off_left(board, lambda off: quest_exposure.least_exposed_path(
        terrain, exposure, _cell(snapshot.player.position), goals, off), occupied)
    if len(path) < 2:
        return None
    return quest_plan_base.plan_walk(policy, snapshot, path[1], PULLED_BACK_REASON)


def _advance(policy, snapshot, navigator, plan, board) -> str | None:
    """A step of the least exposed walk to the exit, round a monster when that exposes no
    more and is a sidestep; else it is struck."""
    position, exit_cell = snapshot.player.position, _exit_cell(navigator)
    clearing = _floor_needs_clearing(navigator, plan)
    if _cell(position) in pull_cells(navigator, plan):
        if not clearing:
            return _way_back(policy, snapshot, navigator, plan, board)
        if clearing_finished(navigator):
            return _pull_walk(policy, snapshot, navigator, plan, board)
        return _off_the_pull_lines(policy, snapshot, navigator, plan, board)
    through = _walk_off_left(board, navigator, plan, position, {exit_cell})
    around = _walk_off_left(board, navigator, plan, position, {exit_cell}, board.occupied)
    path = around if (
        around and len(around) <= len(through) + SIDESTEP_LIMIT
        and _exposed_count(navigator, plan, around) <= _exposed_count(navigator, plan, through)
    ) else through
    if len(path) < 2:
        # Every way on crosses a caster's direct line: kill first, then cross.
        if not clearing_finished(navigator):
            cleared = _clear_key(policy, snapshot, navigator, plan, board)
            if cleared is not None:
                return cleared
        return _pull_walk(policy, snapshot, navigator, plan, board)
    shot = _clear_the_way_key(policy, snapshot, navigator, plan, board, path)
    if shot is not None:
        return shot
    step = path[1]
    if step in board.occupied:
        blocker = next((monster for monster in board.in_view if monster.position == step), None)
        if blocker is None:
            policy.last_reason = HOLD_REASON
            return WAIT_KEY
        return combat_answer.strike_key(policy, snapshot, blocker, MELEE_REASON)
    if _cell(step) in _planned_open(navigator, plan) - navigator.exit_dug:
        profile = policy.approved_quest_strategy(navigator.quest_id)
        return _dig(policy, snapshot, navigator, plan, board, profile, step)
    crowded = _crowded_step(policy, snapshot, navigator, plan, board, step)
    if crowded is not None:
        return crowded
    hasted = _haste_before_shouted(policy, snapshot, navigator, plan, step)
    if hasted is not None:
        return hasted
    return quest_plan_base.plan_walk(policy, snapshot, step, WALK_REASON, reach=exit_cell)


def key(policy, snapshot) -> str | None:
    """The board with an enemy about, or with HP to rest back, or on a cell the casters
    reach; None leaves it shared."""
    plan = _plan(policy, snapshot)
    if plan is None or steps_aside_for_food(policy, snapshot):
        return None
    quest_id = snapshot.floor_key[2]
    profile = policy.approved_quest_strategy(quest_id)
    navigator = _navigator(policy, snapshot, quest_id)
    board = _Board(policy, snapshot, profile, navigator)
    if not board.mobile_awake:
        navigator.exit_choke_goal = None  # what sent the walk to a choke is gone
    exposed = _exposure(navigator, plan).exposed(_cell(snapshot.player.position))
    stepped = _step_on_exit(policy, snapshot, navigator, board)
    if stepped is not None:
        return stepped
    if exposed:
        # Survival first, then out of their reach: no hold, rest or chosen fight here.
        # Owner 2026-11-07 「作戦が先・即死だけ例外」: the 1-turn 即死 heads each enemy board.
        return (
            threat_tiers.instant_death_key(
                policy, snapshot, lambda: _instant_death_escape(policy, snapshot, profile, board))
            or (_below_line_recall(policy, snapshot, profile) if board.enemy_for_the_line else None)
            # The shared survival stage: the cure and the Healing; on these cells the haste is the
            # plan's own dose before the step onto them (``_haste_before_shouted``).
            or (quest_plan_base.survival_stage(policy, snapshot, profile, board, enemy=True, haste=False)
                if board.engaged else None)
            or _recall_wait_away(policy, snapshot, board)
            or summon_response.key(policy, snapshot)
            or resist_potion.key(policy, snapshot)
            or _melee_cap_retreat(policy, snapshot, navigator, plan, board)
            or _back_to_a_spent_choke(policy, snapshot, navigator, plan, board)
            or _choke_walk_under_way(policy, snapshot, navigator, plan, board)
            or _advance(policy, snapshot, navigator, plan, board)
        )
    if not board.enemy_for_the_line:
        return (
            summon_response.key(policy, snapshot)
            or resist_potion.key(policy, snapshot)
            # The shared survival stage of a quiet board: the drained abilities' restore.
            or quest_plan_base.survival_stage(policy, snapshot, profile, board, enemy=False)
            or _rest(policy, snapshot, plan, board)
            or (_to_choke(policy, snapshot, navigator, plan, board) if board.mobile_awake else None)
            or _wait_after_fight(policy, snapshot, navigator, plan, board)
            or (_advance(policy, snapshot, navigator, plan, board) if board.in_view else None)
        )
    return (
        threat_tiers.instant_death_key(
            policy, snapshot, lambda: _instant_death_escape(policy, snapshot, profile, board))
        or _below_line_recall(policy, snapshot, profile)
        or (quest_plan_base.survival_stage(policy, snapshot, profile, board, enemy=True)
            if board.engaged else None)
        or _recall_wait_away(policy, snapshot, board)
        # Owner 2026-11-04: the answer to the summons, ahead of the plan's own order.
        or summon_response.key(policy, snapshot)
        or resist_potion.key(policy, snapshot)
        or (_fight(policy, snapshot, profile, navigator, plan, board) if board.engaged else None)
        # Nothing to fight or walk to a choke for: the choke's wait after a fight or a shriek
        # holds as on a quiet board (``_shriek_hold``, owner 2026-11-22).  n1-b life-418
        # (2026-11-25): the shriek heard on (1,16), the giant squid 482 breathing range away in
        # the lake (``firing``, 9a474abadd) made the board engaged, and (1,19) was walked off at
        # once onto the open (2,20) and (3,20), as life-414 had died doing.
        or _wait_after_fight(policy, snapshot, navigator, plan, board)
        or _choke_walk_under_way(policy, snapshot, navigator, plan, board)
        or _advance(policy, snapshot, navigator, plan, board)
    )


def _instant_death_escape(policy, snapshot, profile, board) -> str | None:
    """The plan's escape on its 即死 rung (threat_tiers.instant_death_key): Teleport Away at the
    worst hostile in view on a beam's line, then the Recall whatever the HP.

    Owner 2026-11-22 「使う」 (n1-b life-414 on (3,20), two hasted seahorses 443 beside it: the
    emergency's Speed and two steps; at (1,19) in the Recall's countdown two cornered blows, and
    death with the absorbed wand of Teleport Away at 23 charges).  The Recall fires in 15 to 35
    player turns; the blow that kills comes on the next one, which only sending its maker away
    answers.  On the next board, the line read again, the Recall is read as before."""
    return (_away(policy, snapshot, board.in_view)
            or _below_line_recall(policy, snapshot, profile, line=False))


def _recall_wait_away(policy, snapshot, board) -> str | None:
    """The Recall counting down and an enemy in view that comes: Teleport Away at the worst of
    them, before the plan's retreats and blows (owner 2026-11-22 「使う」).  The plan's heal (and,
    off the shouted cells, its cure and Speed) comes first; the 即死 board has its own rung above."""
    if not snapshot.player.recalling or not board.engaged:
        return None
    coming = [monster for monster in board.in_view if monster in board.reachable_awake]
    return _away(policy, snapshot, coming) if coming else None


def _away(policy, snapshot, candidates) -> str | None:
    """quest_plan_base.hall_away_key over ``candidates``: the absorbed rod, the absorbed wand, then
    a carried one; never at a never-moving monster or one the game surely keeps."""
    return quest_plan_base.hall_away_key(policy, snapshot, candidates, AWAY_REASON)


def _haste_before_shouted(policy, snapshot, navigator, plan, step: Position) -> str | None:
    """The Speed dose before a step onto a cell the casters reach, while the haste is off.

    Owner 2026-11-22 「加速してから入る」 to 「叫びの届くマスへ入る前に加速が切れていたら、敵が見えて
    いなくても取り込んだスピードか薬で加速するか」: the plan's own shouted cells (``_exposure``, the
    floor as dug), whatever is in view; the absorbed Speed first, then a potion (speed_dose.key).
    A siren reaches a cell beside its line one cast in four of its turns (1_IN_2, SHRIEK or
    TELE_TO, the pull refused off the line, mspell-attack.cpp check_thrown_mspell); at +10 against
    its +10 the three corridor cells (1,16) (1,17) (2,18) give it three turns, not six.  With no
    dose left the step is taken as before."""
    if policy._player_hasted(snapshot) or not _exposure(navigator, plan).exposed(_cell(step)):
        return None
    return speed_dose.key(policy, snapshot, SPEED_REASON)


def _fight(policy, snapshot, profile, navigator, plan, board) -> str | None:
    retreat = _melee_cap_retreat(policy, snapshot, navigator, plan, board)
    if retreat is not None:
        return retreat
    if board.adjacent_mobile:
        _note_contact(navigator, plan, snapshot.player.position)
        ranked = sorted(board.adjacent_mobile, key=lambda monster: _rank(profile, monster))
        target = summon_response.named_casters_first(policy, ranked)[0]
        answer = combat_answer.adjacent_attack(policy, snapshot, [target], MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
        # A blow the game refuses (fear) and no missile: the choke is still the place.
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    moved = _to_choke(policy, snapshot, navigator, plan, board) if board.mobile_awake else None
    if moved is None and board.coming_in_view and not _spent_here(navigator, snapshot):
        # No choke to be had: it is still fought here, not walked into.
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    return moved


def _spent_here(navigator, snapshot) -> bool:
    return snapshot.player.position in navigator.exit_spent_chokes


def _note_contact(navigator, plan, position: Position) -> None:
    """A blow on a choke: its waits start over and it is worth waiting on again."""
    if [position.y, position.x] in plan["choke_cells"]:
        navigator.exit_hold_cell = position
        navigator.exit_hold_turns = navigator.exit_enemy_turns = 0
        navigator.exit_fought_at = position
        navigator.exit_spent_chokes = navigator.exit_spent_chokes - {position}
        navigator.exit_quiet_spent = _without(navigator.exit_quiet_spent, position)


def note_answered(policy, snapshot) -> None:
    """``key`` answered this board: an unseen hit carried over from an earlier board of this
    floor (``_unseen_hit_pending_floor``) is answered by it, as the shared unseen retreat
    (policy_supply ``_unseen_retreat_key``) and quest_room_sweep's cover consume it.

    ``key`` answers every board with an enemy above the shared ladders, so nothing below ever
    consumed the carried hit here, and ``_Board.hit_by_unseen`` stayed true for the rest of the
    floor: every later board was "engaged", so the owner's 「HP が9割より低く敵がいなければ先に
    休む」 (``rest_below_ratio``, branch "no enemy for the line") never ran again.  n1-a life-520
    (2026-11-14, warrior Lv28, Q18): a siren's unseen curse at (2,6) (turn 1340352, HP 585->522)
    set it; from (1,7) on the walk went on unrested, at (2,13) with HP 379/553 and no Healing
    potion left, into the giant squid at (5,24) and died there.  A new unseen hit on a later board
    is fresh evidence of that board (``_unseen_attack_evidence``) and sets it again."""
    if getattr(policy, "_unseen_hit_pending_floor", None) == snapshot.floor_key:
        policy._unseen_hit_pending_floor = None


def walk_key(policy, snapshot) -> str | None:
    """A quiet board on such a floor, through the navigator: walk on."""
    plan = _plan(policy, snapshot)
    if plan is None:
        return None
    quest_id = snapshot.floor_key[2]
    navigator = _navigator(policy, snapshot, quest_id)
    board = _Board(policy, snapshot, policy.approved_quest_strategy(quest_id), navigator)
    return (_step_on_exit(policy, snapshot, navigator, board)
            or _wait_after_fight(policy, snapshot, navigator, plan, board)
            or _advance(policy, snapshot, navigator, plan, board))
