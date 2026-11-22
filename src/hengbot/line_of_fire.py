"""Whether an enemy has a line of fire to the player, and the escape count's record of it.

Owner 2026-11-14 (verbatim): 「テレポートを使い逃げにカウントするのは射線が通っている場合のみに
したい。」 (on 「強敵を感知したときの処理を確認したい。射線が通っているときといないとき、単体で強い
ときと群れで強いとき…」).  The count is the one of 2026-11-09 「全部の逃げを数え2回で帰還」
(escape_count): an escape joins it only when an enemy that caused it had a line of fire to the
player on the board the escape was decided on.  What the bot does in danger is unchanged; only
what is counted toward the two-escape return is.

The line of fire is the game's ``projectable`` (projection-path-calculator.cpp:262-271): the bolt
path from the monster toward the player, at most ``get_max_range()`` = 18 grids long
(angband-system.cpp:45-48, ``MONSTER_SPELL_MAX_RANGE``), stops on the first grid without
PROJECTION (projection-path-calculator.cpp:94-96, flag 0) and reaches when it ends on the
player.  A monster casts at the player only when it is projectable (mspell-lite.cpp:209-212).

The board is the player's knowledge, not the game's cave: a grid the board (with the floor's
remembered terrain, ``_with_grid_memory``) does not know stops the path here.  The game would
read the real terrain there, which the player cannot; an unknown grid is most often unexplored
rock, and the owner's rule counts an escape only when the line is shown open, so an unknown grid
never lets an enemy out of view count (n1-c life-207, 2026-11-14 16:29:42: a ヘル・ワイアーム known by
detection alone counted through the old straight line, which read no range limit).  A known grid
stops it as ``_may_block_projection`` reads PROJECTION from the board (no LOS and no MOVE: a wall,
a closed door; glass), the ported reading the spell reach uses.

Each decision that chooses an escape records, through ``note``, whether any of the enemies it
weighed has that line (``causes``); an escape no decision noted is judged on the board's awake
known hostiles that can hurt or summon (``known_causes``).  ``PROOF_REASONS`` count as before.

This is the counting reading (``counting``).  Every line of fire of the bot is read in this
module (maintainability review 2026-11-17, N4 / 5(a)-7: two readings had each claimed to
be the only one).  The readings, by name:

- ``counting``: the reading above (an unknown grid stops the path).  It decides what is
  counted, not what is done: the escape count (``note``), summon_response's count.
- ``danger``: what may hurt the player (owner 2026-11-08 「未知のマスを壁と見ない」, 2026-11-15
  Q5 「被害の見積りと同じにする」, 2026-11-17 Q5 「危険の判定は危険用に揃える」): the board's line
  with the map memory, else, for an awake monster, ``projectable`` (the unknown grids open).
- ``projectable``: the game's projectable() over the known map with the unknown grids open,
  awake or asleep (``across_glass``: read through glass, glass_reach).
- ``straight_line``: the board's straight line of sight, a known glass grid stopping it
  (``remembered``: the map memory read for a grid the board does not know).
- ``player_projectable``: projectable() for the player's own bolt (glass stops it).
- ``player_path``: the player's own bolt path itself (``player_projectable``'s), for an aim
  that must pass a monster on its way to another grid (policy ``_offset_fire_aim``).
- ``own_stop`` (not a reading of this module): a ``projection_path`` given a stop of its own
  elsewhere, each listed in ``READERS`` with why it is not ``player_path`` (review 2026-11-18
  S7-3: the glass class, a stop on LOS instead of PROJECTION, was one of these).
- ``fire_reaches``: the survival gate's "under fire" (within reach, a line of fire, a one-turn
  predicted damage above zero).

Which caller reads which, and why, is ``READERS`` below; scripts/line_of_fire_lint.py fails on a
call of these readings the table does not list, on a stale row, on a line-of-fire
computation outside this module, and on a ``projection_path`` given a stop of its own that the
table does not list (``own_stop``).  Naming the readings changed no caller's reading (whether a
caller should read another one is the owner's question, review Q5).

The "in view" readings (maintainability review 2026-11-17, N9 / 5(a)-8: eight of them, two of
one name until then), each named for what it reads:

==================================================  =================================================
destruction_use ``_visible_hostiles_except_target``  the visible hostiles but the target, awake or
                                                     asleep (the *Destruction* gate's seen threats)
threat_tiers ``_seen_and_projectable``               seen (not by detection only) and ``projectable``
                                                     to the player, awake or asleep (a T1 the
                                                     approach leaves to the in-view rules)
return_yield ``awake_visible_hostile_projectable``   an awake visible hostile (detection included)
                                                     ``projectable`` to the player
resist_potion ``_awake_visible_enemy_it_answers``    an awake visible hostile whose attack the
                                                     potion's resistance answers
safety_facts ``hostile_in_view``                     any visible hostile (the watch's recorded fact
                                                     name, kept)
quest25_battle ``_Ctx.seen_hostiles``                the visible hostiles not by detection only
me_powers ``Context.hostile_visible``                a physical visible hostile
me_powers ``Context.threat_visible``                 a visible threat (me_powers ``visible_threat``)
amberite_curse ``struck`` (inline)                   visible, or in the ``danger`` line of fire
==================================================  =================================================
"""

from __future__ import annotations

from hengbot import cross_rules, glass_reach
from hengbot.model import Position
from hengbot.policy_constants import MONSTER_SPELL_MAX_RANGE
from hengbot.projection_path import projection_path

# Owner 2026-11-14 「数える」: these two keep counting as escapes.  The summons or the damage
# reaching the player is taken as proof that a line of fire existed: summons:leave-teleport
# leaves an unseen summoner that summoned twice (summon_response), no-wait:escape-scroll leaves
# damage received from an unseen enemy (policy_combat's no-wait rung).  The leave's cast of the
# absorbed Teleportation on Quest 33 (owner 2026-11-19) is the same leave.
PROOF_REASONS = frozenset({"summons:leave-teleport", "summons:leave-teleport:absorbed-power",
                           "no-wait:escape-scroll"})

RECORD = "_escape_line_of_fire"
BOARD = "_escape_line_of_fire_board"

# Which caller reads which line of fire, and why: (module, function, reading) -> why.
# scripts/line_of_fire_lint.py keeps it equal to the calls (a missing row and a stale row fail).
READERS = {
    # counting: an unknown grid is a wall.  What is counted, not what is done.
    ("line_of_fire", "_note", "counting"):
        "the escape count (owner 2026-11-14 「射線が通っている場合のみ」)",
    ("line_of_fire", "counting", "counting"):
        "the counting reading from the monster's grid (counting_reaches)",
    ("summon_response", "_in_fire", "counting"):
        "the summon count: a cast counts from a caster with a line to the player",
    ("deep_teleport", "note_teleport", "counting"):
        "the 50F+ teleport's memory of the monsters in line before it (as the escape count)",
    ("deep_teleport", "observe", "counting"):
        "the landing: a remembered monster still in line on the landing board",
    # danger: an awake monster's unknown grids are open.  What may hurt the player.
    ("policy_combat", "threat_prediction", "danger"):
        "the damage estimate (owner 2026-11-08 「未知のマスを壁と見ない」)",
    ("deep_teleport", "in_fire_p95", "danger"):
        "fire_p95, the 50F+ instant death (owner 2026-11-15 Q5 「被害の見積りと同じにする」), and the "
        "unseen retreat's attacker come into view (policy_supply _unseen_attacker_in_view)",
    ("recall_wait_teleport", "_t1_in_fire", "danger"):
        "the recall wait's 「射線の通る T1」 (owner 2026-11-17 Q5 「危険の判定は危険用に揃える」)",
    ("amberite_curse", "struck", "danger"):
        "an Amberite the shot may hit (owner 2026-11-17 Q5 「危険の判定は危険用に揃える」)",
    ("me_powers", "_sensed_unbeatable_in_fire", "danger"):
        "the T1 known only by detection the Recall wait sends away (owner 2026-11-22 「撃つ」: "
        "「射線が通っている」 is what may hurt the player)",
    # projectable: the game's projectable() with the unknown grids open, awake or asleep.
    ("line_of_fire", "danger", "projectable"):
        "the danger reading's awake half",
    ("line_of_fire", "fire_reaches", "projectable"):
        "the survival gate's path gate (mspell-lite.cpp:209-212) when asked",
    ("glass_reach", "passing_abilities", "projectable"):
        "a spell crossing glass: projectable through it",
    ("policy_combat", "_ranged_attack_key", "projectable"):
        "the player's shot has a target a line projects to (from the player to the monster)",
    ("policy_combat", "_offset_spell_reach", "projectable"):
        "a monster's cast at the player or a grid beside it (adjacent_grid_check)",
    ("policy_combat", "_summoner_may_summon_at", "projectable"):
        "a summoner's cast at the player or a grid beside it",
    ("policy_combat", "_note_summoner_counter_targets", "projectable"):
        "a summoner a line from the player reaches (its counter-attack target)",
    ("return_yield", "awake_visible_hostile_projectable", "projectable"):
        "an awake visible hostile that can attack the player from where it stands",
    ("threat_escape", "out_of_reach", "projectable"):
        "a monster from which no line projects to the player (out of reach)",
    ("threat_tiers", "_seen_and_projectable", "projectable"):
        "a seen T1 with a line to the player: the in-view rules answer it, not the approach",
    # straight_line: the board's line of sight, a known glass grid stopping it.
    ("line_of_fire", "danger", "straight_line"):
        "the danger reading's line with the map memory",
    ("line_of_fire", "fire_reaches", "straight_line"):
        "the survival gate's line",
    ("glass_reach", "passing_abilities", "straight_line"):
        "a spell crossing glass: the line with the map memory through it",
    ("policy_combat", "_immobile_summoner_key", "straight_line"):
        "the grids a remembered immobile summoner's line reaches (avoided)",
    ("policy_combat", "_ranged_scroll_lock_threats", "straight_line"):
        "a caster's line for the scroll lock (the board's line, no map memory)",
    ("policy", "exposed_to", "straight_line"):
        "a named unseen shooter's line to a cover grid",
    ("paralyzer_contact", "spell_contact", "straight_line"):
        "a paralyzing caster with a line to the player",
    ("threat_escape", "need_not_fight", "straight_line"):
        "a shrieker with a line to the player",
    # player_projectable: the player's own bolt (glass stops it).
    ("immobile_ranged_kill", "_shooting_cell", "player_projectable"):
        "a grid the player's shot reaches an immobile summoner from",
    ("angband_finale_battle", "crowded", "player_projectable"):
        "the 99F/100F battle's leave when the target and another monster are both in the player's "
        "line of fire (owner 2026-11-20 「ターゲットとターゲット以外が同時に射線に入っているときは"
        "召喚直後でなくとも離脱する」)",
    ("angband_finale_battle", "_opens_line", "player_projectable"):
        "whether melting one wall of the 99F/100F stand (``opened``) would leave the player's "
        "line of fire to the target where it stands: that melt is never made, the target would act "
        "first on the open line (owner 2026-11-21 「溶かした時に先手を取られて何も出来ず離脱している"
        "場面が問題」)",
    ("angband_finale_battle", "_fight_key", "player_projectable"):
        "the 99F/100F powered Rocket at the target's grid: a ball aimed at a grid flies the bolt "
        "path to it (owner 2026-11-20 「岩石溶解を使って射線を通す」)",
    ("line_of_fire", "player_projectable", "player_path"):
        "the player's bolt path ends on the target",
    # player_path: the grids the player's own bolt passes (glass stops it).
    ("me_ranged_first", "_clear_projection", "player_path"):
        "an absorbed power aimed at a monster's cell off the eight rays: the path reaches the "
        "cell with no other body first (glass stops it, n1-c life-216 Glass castle 60F)",
    ("policy_combat", "_offset_fire_aim", "player_path"):
        "the shot at a victim past a nearer body: the victim before the aim on the arrow's path "
        "(n1-c life-216 Glass castle 60F, 2026-11-18: an LOS-only path through glass)",
    ("quest_firing_cells", "reach", "player_path"):
        "the Q2 / Q25 shot at a breeder (the corpse masses) from a firing cell: two grids or more "
        "away, the arrow's path ends on it (review 2026-11-18 6(a)-8: an LOS stop of its own "
        "until then; the Q2 and Q25 maps have no glass, tree or curtain, so no answer changed)",
    # own_stop: a projection_path given a stop of its own outside this module (review
    # 2026-11-18 S7-3 / 6(a)-8, the glass class).  Each one listed here, and why it keeps it.
    ("breeder_area_attack", "_projectable", "own_stop"):
        "the area attack's own projection over the board (ball shape, aimed grid): an unknown "
        "grid or one without MOVE stops it.  Not the glass class (no LOS read: glass, without "
        "MOVE, stops it); player_path would open the unknown grids, which changes answers",
    ("breeder_area_attack", "_ray", "own_stop"):
        "the area attack's direction-aimed ray (bolt / beam), the same stop as _projectable",
    ("breeder_area_attack", "_grid_ray", "own_stop"):
        "the area attack's grid-aimed projection, the same stop as _projectable",
    ("quest_exposure", "projectable", "own_stop"):
        "projectable() over a fixed quest's map read from its file (its terrain kinds, "
        "PROJECTING_KINDS), not over the board: there is no policy or board to read",
    ("quest_summon_answer", "_sight_line", "own_stop"):
        "quest_exposure.projectable over QUEST_33's map (quest_alignment_split's sight map, the "
        "doors as the board shows them) with the open cells computed once for the many cells the "
        "lure weighs; the map's own reading, as quest_exposure's row",
    ("quest_lure_approach", "_reaches", "own_stop"):
        "whether a bolt aimed at a tree of QUEST_33's map stops on that tree (the first grid without "
        "PROJECTION) over the map as the plan may open it (quest_wait_placement's reader, trees burnt "
        "and walls melted counted, ``with_opened``), not the board's own path",
    # fire_reaches: the survival gate's "under fire".
    ("policy_combat", "_forbid_wait_while_damaged", "fire_reaches"):
        "the survival gate: a visible hostile can shoot the player",
    ("summoner_wait", "_shot_at", "fire_reaches"):
        "a hold grid a visible hostile can shoot (owner 2026-11-02 「撃たれない場所で待つ」)",
}


def _stops(policy, snapshot, position: Position) -> bool:
    grid = snapshot.grid_at(position)
    return grid is None or not grid.known or policy._may_block_projection(snapshot, position)


def counting_reaches(policy, snapshot, source: Position, target: Position | None = None) -> bool:
    """The counting reading from ``source`` to ``target`` (the player): projectable() over the
    known board, an unknown grid stopping the path."""
    if target is None:
        target = snapshot.player.position
    if source == target:
        return True
    path = projection_path(source, target, MONSTER_SPELL_MAX_RANGE,
                           lambda position: _stops(policy, snapshot, position))
    return bool(path) and path[-1] == target


def counting(policy, snapshot, monster) -> bool:
    """The counting reading: the monster has a line of fire to the player over the known board."""
    return counting_reaches(policy, snapshot, monster.position)


def danger(policy, snapshot, monster) -> bool:
    """The danger reading: the monster has a line of fire to the player, as the damage estimate
    reads it (``threat_prediction`` and the 50F+ instant-death judgement, deep_teleport
    ``fire_p95``, owner 2026-11-15 maintainability review Q5 「被害の見積りと同じにする」; the
    recall-wait T1 and the Amberites' strike, owner 2026-11-17 Q5 「危険の判定は危険用に揃える」).
    The escape and summon counts keep ``counting``.

    An unknown grid is not a wall (owner 2026-11-08 「未知のマスを壁と見ない」) for an awake
    monster: the remembered line, else projectable() over the known map with the unknown
    grids open (``projectable``).  n1-a life-514 (2026-11-12, Angband 49F): the
    never-moving あつくもえるてき at distance 10 behind grids the board had never shown
    predicted 0 while its fire balls reached the player.  A sleeping monster casts nothing
    until it wakes (monster-processor.cpp:198-200: a sleeping monster's turn ends at
    awake_monster), so its unknown grids stay closed: opened, every sleeper telepathy shows
    through unexplored rock reads as reaching (the same floor's fifteen sleeping 巨大首なし
    read as a lethal swarm on arrival at full HP).  Waking one is the ranged rung's question
    (policy ``_sleeper_not_to_wake``).

    An awake monster in view (the board's ``visible_monsters``: its grid is in the player's view,
    CAVE_VIEW, bot-json-output.cpp make_visible_monsters_json) has a line: the view is the
    game's line of sight now, whatever the map memory says between (``_in_view_reaches``; only
    known glass, LOS without PROJECTION, and the spell range stop it).  n1-c life-219 (Angband
    80F, 2026-11-22 05:56:11): the absorbed mapping showed the rock around the player, then the
    混沌 swarm (KILL_WALL) dug it into floor the game no longer marks; the memory
    (``_with_grid_memory``) kept the walls, so nine of the twelve 混沌 in view read no line, the
    instant-death sum of those in fire read 517 against HP 766 (1199 with them), no
    Teleportation was offered (deep_teleport ``no_means``) and the bot drank Healing instead."""
    if not monster.asleep and _in_view(snapshot, monster) and _in_view_reaches(policy, snapshot, monster):
        return True
    return straight_line(
        policy, snapshot, monster.position, snapshot.player.position,
        remembered=policy._remembered_grids,
    ) or (not monster.asleep and projectable(
        policy, snapshot, monster.position, snapshot.player.position))


def _in_view(snapshot, monster) -> bool:
    """``monster`` is one of the board's monsters in the player's view (not by detection)."""
    return any(seen.index == monster.index and seen.position == monster.position
               for seen in snapshot.visible_monsters)


def _in_view_reaches(policy, snapshot, monster) -> bool:
    """The bolt path from a monster in view to the player within the spell range
    (projection-path-calculator.cpp), stopped only by known glass (glass_reach ``stops``): the
    player's view of the monster's grid is the line of sight, so a remembered wall on it is
    stale (``danger``)."""
    target = snapshot.player.position
    if monster.position == target:
        return True
    path = projection_path(monster.position, target, MONSTER_SPELL_MAX_RANGE,
                           lambda position: glass_reach.stops(policy, snapshot.grid_at(position)))
    return bool(path) and path[-1] == target


def straight_line(policy, snapshot, origin: Position, target: Position, *,
                  remembered: dict | None = None, across_glass: bool = False) -> bool:
    """The board's straight line of sight from ``origin`` to ``target``.

    ``remembered``: the map memory read for a grid the board does not know (the
    incoming-damage estimate; n1-c life-171, 城65階: after the darkness storm two floor grids
    the player had walked between it and 皇帝『レイザーク』 were off the board and read as
    walls, so the emperor's spells counted 0 while they landed).

    A known glass grid (LOS without PROJECTION) stops the line as it stops projectable()
    (projection-path-calculator.cpp:94, glass_reach); ``across_glass`` reads the line of sight
    through it, for the spells that cross it (glass_reach.passing_abilities)."""
    y0, x0 = origin.y, origin.x
    y1, x1 = target.y, target.x
    dy, dx = abs(y1 - y0), abs(x1 - x0)
    sy, sx = (1 if y0 < y1 else -1), (1 if x0 < x1 else -1)
    error = dx - dy
    while (y0, x0) != (y1, x1):
        twice = error * 2
        if twice > -dy:
            error -= dy
            x0 += sx
        if twice < dx:
            error += dx
            y0 += sy
        if (y0, x0) == (y1, x1):
            return True
        grid = snapshot.grid_at(Position(y0, x0))
        if (remembered is not None and (grid is None or not grid.known)
                and (memory := remembered.get(Position(y0, x0))) is not None):
            grid = memory
        if grid is None or not grid.allows_los or (
                not across_glass and glass_reach.stops(policy, grid)):
            return False
    return True


def projectable(policy, snapshot, source: Position, target: Position, *,
                across_glass: bool = False) -> bool:
    """projectable() (projection-path-calculator.cpp:254-270) over the known map with unknown
    grids open: the ported bolt path, range get_max_range() = 18 (angband-system.cpp:45-48),
    ends on the target.  ``across_glass``: the same line read through glass
    (policy ``_may_block_projection``)."""
    if source == target:
        return True
    path = projection_path(
        source, target, MONSTER_SPELL_MAX_RANGE,
        lambda position: policy._may_block_projection(
            snapshot, position, across_glass=across_glass),
    )
    return bool(path) and path[-1] == target


def player_projectable(policy, snapshot, source: Position, target: Position,
                       opened: tuple = ()) -> bool:
    """``projectable`` for the player's own projection (policy ``_stops_player_projection``).

    ``opened``: grids read as open whatever the board shows (a wall about to be melted)."""
    if source == target:
        return True
    path = player_path(policy, snapshot, source, target, MONSTER_SPELL_MAX_RANGE, opened)
    return bool(path) and path[-1] == target


def player_path(policy, snapshot, source: Position, target: Position, max_range: int,
                opened: tuple = ()) -> list:
    """The grids the player's own bolt, arrow or shot passes from ``source`` toward ``target``
    (project_path, projection-path-calculator.cpp), at most ``max_range`` long, the last one
    where it stops: a known grid without PROJECTION stops it, glass included
    (policy ``_stops_player_projection``; GLASS_WALL and PERMANENT_GLASS_WALL have LOS and no
    PROJECTION, TerrainDefinitions.jsonc), an unknown grid does not.

    n1-c life-216 (Glass castle 60F, 2026-11-18 01:10, loop-detected): from (8,163), behind
    the glass wall at (9,165), summoner:ranged-kill:named-caster fired 40 crossbow bolts
    at the 死の騎士 and the summoners beyond along a line of sight read as the arrow's path
    (policy ``_offset_fire_aim``); each bolt stopped on the glass."""
    return projection_path(
        source, target, max_range,
        lambda position: position not in opened
        and policy._stops_player_projection(snapshot, position),
    )


def fire_reaches(policy, snapshot, monster, cell: Position, *,
                 projectable_path: bool = False) -> bool:
    """Whether a visible hostile can shoot the player standing on ``cell``.

    This is the survival gate's "under fire" test: within the game's reach, a line of fire and
    a one-turn predicted damage above zero.  Every monster ranged attack (bolts, balls,
    breaths, arrows and direct spells) is a spell of make_attack_spell, which never casts at a
    player whose cdis exceeds get_max_range() = 18 (mspell-attack.cpp:320,
    angband-system.cpp:45-48); its projection path also ends at that range
    (projection-path-calculator.cpp:262-272).  ``projectable_path`` adds the game's own path
    gate: a monster casts only when projectable() reaches the player (mspell-lite.cpp:209-212
    decide_lite_projection), ``projectable``."""
    if policy._monster_cast_distance(monster.position, cell) > MONSTER_SPELL_MAX_RANGE:
        return False
    reaches = straight_line(policy, snapshot, monster.position, cell) or (
        projectable_path and projectable(policy, snapshot, monster.position, cell)
    ) or bool(glass_reach.passing_abilities(
        policy, snapshot, monster, policy._monrace_knowledge.get(monster.race_id), cell))
    return reaches and policy._predicted_damage(snapshot, [monster], turns=1) > 0


def known_causes(snapshot) -> list:
    """The known hostiles (seen or detected) that can hurt or summon: the awake ones, or every
    one when none is awake (escape_count.causes_of's reading: a leave from a sleeping strong
    monster, owner 2026-11-07, has that monster for its cause)."""
    hostiles = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                if monster.hostile
                and (monster.max_melee_damage > 0 or monster.max_ranged_damage > 0
                     or monster.can_summon)]
    return [monster for monster in hostiles if not monster.asleep] or hostiles


def instant_death_causes(policy, snapshot) -> list:
    """The engagement's monsters the 即死 test's next-action prediction counts damage from
    (instant_death: the one-turn operational contribution, each at its adjusted speed)."""
    from hengbot.threat_projection import _with_adjusted_speed, engagement

    hostiles = [_with_adjusted_speed(monster) for monster in engagement(policy, snapshot)]
    if not hostiles:
        return []
    rows = policy.threat_prediction(snapshot, hostiles, 1).get("monsters", ())
    return [monster for monster, row in zip(hostiles, rows)
            if row.get("operational_contribution", 0) > 0]


def ladder_causes(policy, snapshot, hostiles, summoners=()) -> list:
    """The emergency ladder's causes: its awake hostiles, the summoners that may summon at the
    player before its next action, and the monsters of the 即死 prediction."""
    causes = [monster for monster in hostiles if not monster.asleep]
    causes += list(summoners)
    causes += instant_death_causes(policy, snapshot)
    return causes


def note(policy, snapshot, causes, *, proof: bool = False) -> bool:
    """Record for the escape decided on this board whether a cause has a line of fire
    (``proof``: the damage reaching the player stands for it, as ``PROOF_REASONS``)."""
    cross_rules.consult(policy, cross_rules.ESCAPE_LINE_OF_FIRE)
    return _note(policy, snapshot, causes, proof=proof)


def _note(policy, snapshot, causes, *, proof: bool = False) -> bool:
    """``note`` without the observer's record: the count's own reading of an escape no
    producer noted (``counts``)."""
    value = bool(proof) or any(counting(policy, snapshot, monster) for monster in causes)
    setattr(policy, RECORD, value)
    return value


def counts(policy, snapshot, reason) -> bool:
    """Whether the escape ``reason`` decided on ``snapshot`` joins the count: the latches that
    start the return on the second escape before it is counted ask this too."""
    if reason in PROOF_REASONS:
        return True
    noted = getattr(policy, RECORD, None)
    if noted is None:
        noted = _note(policy, snapshot, known_causes(snapshot))
    return noted


def counted(policy, reason) -> bool:
    """The observation's reading for the escape decided on the previous board."""
    board = getattr(policy, BOARD, None)
    if board is None:
        return True  # no board seen by this process: as before
    return counts(policy, board, reason)


def new_board(policy, snapshot) -> None:
    """After the previous board's escape was counted: this board's decision records anew."""
    setattr(policy, RECORD, None)
    setattr(policy, BOARD, snapshot)
