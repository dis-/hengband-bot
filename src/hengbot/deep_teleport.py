"""50F+: the player's own teleport only on 即死 by the monsters with a line of fire.

Owner 2026-11-14 (verbatim): 「50F以降のテレポートの条件を厳しくする。深い階層のテレポートには
即死抽選があるためである。射線の通っている敵の合計予測被害95%が現在HPを上回るとき=即死のとき
のみ。当てはまらない時は破壊または近寄って破壊を試みる。」

``allows``: on a dungeon floor of depth ``policy_constants.DEEP_FLOOR_DEPTH`` or deeper where the
tiers act (threat_tiers.acts_here: not on an approved quest plan's floor, whose own order stands, nor in
town, a store, the arena or the wilderness), the self-teleport -- Teleportation and Phase Door
scrolls, the Staff of Teleportation, the absorbed Teleportation; anything that moves the player
to a random cell (spells-teleport.cpp teleport_player) -- is allowed only when the summed
one-turn p95 of the monsters that have a line of fire to the player (line_of_fire, the game's
projectable at range 18) reaches the current HP.  It is the 即死 test's sum (instant_death: the
next action's operational p95 of the engagement, each monster at its adjusted speed, plus the
observed unseen loss, ``>=`` the HP as there) with every monster without a line of fire left out
(an unseen attacker whose damage reached the player has one: ``fire_p95``).  Not covered (owner's
reading of 2026-11-14): Teleport Away (it moves the monster), Teleport Level, Word of Recall,
stairs.

``substitute``: where a rung would read or cast that teleport and ``allows`` refuses it, the
answer is *Destruction* -- destruction_use's ``key`` with the concerned monsters as the hostiles
it leaves (its sure radius 13, cmd-usestaff.cpp:282 and scroll-read-executor.cpp:342 13 +
randint0(5); its gates: a clear head, a reliable means with a charge, a floor the game destroys,
no guardian or hurt quest target in its worst radius; any concerned monster within the sure
radius, owner 2026-11-17 Q1) -- else the walk toward the most dangerous concerned monster from
contact (destruction_use ``reach_subject``) until one is within the sure radius (threat_tiers.approach_key for monsters known by detection alone; the
same walk for one in view).  The concerned monsters are the hostiles of the engagement, awake or
asleep, that hurt from contact (``threat_prediction(contact=True)``, as the tiers judge a far
monster), but those *Destruction* spares (destruction_use ``spares``: the active quest's target,
and the floor's guardian unless it is T1 alone, owner 2026-11-17 Q3):
the rungs that read the teleport leave sleeping monsters too (a summoner asleep may summon on
its next move, policy_combat ``_summoner_may_summon_next_turn``; owner 2026-11-07 「強い敵からは
離れる」 asleep or not; destruction_use ``_threat_in_reach``, owner 2026-11-09 B, awake or asleep).
Until 2026-11-16 only the awake counted, so a teleport read for a sleeping summoner found no
concerned monster and read Recall: n1-c life-216 (64F, HP 784/784, the absorbed *Destruction*
at 22 charges) read it on the first board after the town's Recall, a sleeping ミッド・タイタン at 15.  Every rung that reads a relocation scroll passes ``_read_key`` or
``_issue_emergency_consumable`` (or composes the read beside ``_anti_teleport_takeoff_key``), and
the staff and absorbed casts pass ``threat_escape.blind_teleport_key`` or
``teleport_follower.device_teleport_key``: the substitute is asked there.

No teleport off the 即死 board (``_refused_key``).  With no concerned monster, or none
*Destruction* can be used on now and no walk toward one (confused, the means spent or
unreliable, the guardian in the circle, a failed use's fallback, no known way), the floor is
left by Word of Recall (``RECALL_REASON``), not by the teleport: the owner's rule names the
即死 board as the only one the teleport is read on, and 2026-11-14 「50F以降で破壊手段なしの探索
は許可しない。敵への対処以前に手段が尽きた時点で帰還させる。」  Until 2026-11-15 this branch read the
teleport as before; n1-b life-397 (Angband 79F, 10:48) read Teleportation so at full HP with no
monster in view (the sum with a line of fire 0), landed beside a dragon pit and died before its
next turn, and the life had read twenty such teleports in three hours on 64F, 79F and 80F.
Recall is not read on a quest floor (it fails the quest), nor while it is already counting
down (a second read cancels it), nor blind or confused.

No means (``no_means``, ``NO_MEANS_BRANCH``): no Recall, and no concerned monster or none
*Destruction* answers (no use on it, no walk toward one).  The owner's rule has no teleport here
either, so the self-teleport is not offered at all: the finders of the Teleportation and Phase Door scrolls
(policy ``_find_teleport_scroll``, ``_find_phase_scroll``), the blind and the follower ladders'
staff and absorbed Teleportation (threat_escape ``blind_teleport_means``, teleport_follower
``pack_teleport_means``) and the breeders' read answer none, and the combat and survival ladder
acts as it does without a teleport (the heal, the Speed dose, the fight, the choke).  The
decision record carries ``{"branch": "deep-teleport:no-means-fight"}`` (``report``).  Until
2026-11-15 the teleport was read there as the last means; no other answer is given in its
place.  A read that still reaches ``substitute`` there (none is known) is refused with a search
turn under ``HOLD_REASON``.

The movement teleports (``movement_refused``): the stuck and livelock escapes, the
*Destruction* circle's leave and the veto enclosure's leave read a teleport with no monster
prompting it, so their askers do not reach the read on 50F+ off the 即死 board.  Owner
2026-11-15, asked how the stuck escape leaves without it: 「岩石溶解で掘る・だめなら帰還」.
``stuck_key`` answers in their place: the walk to the nearest known staircase the floor may
be left by or the nearest frontier when one is reachable after all (``STUCK_WALK_REASON``),
else Stone to Mud along the route that melts the fewest walls to one (retreat_enclosure's
route, the absorbed power before a carried wand; ``STUCK_MELT_REASON``), else Recall
(``STUCK_RECALL_REASON``).  The walk and the melt hold the stuck count, so the escape goes on
until the player stands on a goal; there the count restarts and the floor's own ladder (the
explore, the stairs) takes over, and that goal is not walked to again on the floor visit.  A
wall the beam left me_powers.FAILURES_PER_PLACE times is no route (retreat_enclosure
``meltable``), so a dig that does not get out ends in Recall.  No new number.

The landing in fire.  Owner 2026-11-14 (n1-c life-207, 金鉱80F, a small cave floor: five
Teleportation scrolls each landed within the ストーム・ワイアーム's line of fire, spells-teleport.cpp
teleport_player_aux picking among the farther half of the floor's few cells), verbatim
「前の着地が射線内なら次は *破壊*」: on the 即死 board, when the previous Teleportation on this floor
(scroll, staff or absorbed power; not Phase Door, whose short hop lands in sight by design) landed
with a monster that had a line of fire before it still having one on the landing board, and that
monster is now within *Destruction*'s sure radius and *Destruction* can be used on it, ``allows``
refuses the next teleport and ``substitute`` answers with *Destruction* leaving those monsters.
The first teleport keeps the 11-13 order (the scroll before *Destruction*).  ``note_teleport``
remembers each Teleportation ``substitute`` lets through; ``observe`` settles it on the next board
of the floor (a board where the player has not moved forgets it: the read was not taken).
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import return_start
from hengbot import cross_rules, deep_recall_loot, line_of_fire, no_ac_recall, recall_wait_teleport, search_ban
from hengbot.item_reservation import decision_memo
from hengbot.model import SV_SCROLL_PHASE_DOOR, SV_SCROLL_TELEPORT, TVAL_SCROLL
from hengbot.policy_constants import DEEP_FLOOR_DEPTH

SCROLL_SVALS = frozenset({SV_SCROLL_TELEPORT, SV_SCROLL_PHASE_DOOR})
DESTRUCTION_SUFFIX = ":deep-teleport"
LANDED_SUFFIX = ":teleport-landed-in-fire"
MEMORY = "_deep_teleport_landing"
RECALL_REASON = "deep-teleport:recall"
HOLD_REASON = "deep-teleport:hold"
STUCK_WALK_REASON = "stuck:deep-walk"
STUCK_MELT_REASON = "stuck:deep-stone-to-mud"
STUCK_RECALL_REASON = "stuck:deep-recall"
CAST_SUFFIX = ":absorbed-power"  # me_absorbed_substitutes.CAST_SUFFIX (import cycle)
# The stuck escape's steps on the way to a goal: the stuck count holds (policy_observation).
STUCK_HELD_REASONS = frozenset({STUCK_WALK_REASON, STUCK_MELT_REASON, STUCK_MELT_REASON + CAST_SUFFIX})
STUCK_MEMORY = "_deep_stuck_reached"  # (floor_key, frozenset of the goals reached)
NO_MEANS_BRANCH = "deep-teleport:no-means-fight"
NO_MEANS_NOTE = "_deep_teleport_no_means"    # the turn the finders held the teleport back on
_NO_MEANS_BUSY = "_deep_teleport_no_means_busy"  # the predicate is being computed (re-entry)


@dataclass
class Landing:
    """``pending``: (floor, turn, position, indices with a line of fire) of the Teleportation let
    through; ``landed``: (floor, indices still with one on its landing board)."""
    pending: tuple | None = None
    landed: tuple | None = None


def _memory(policy) -> Landing:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Landing()
        setattr(policy, MEMORY, memory)
    return memory


def applies(policy, snapshot) -> bool:
    """A 50F+ floor where the tiers act, but the 99F/100F battle's (angband_finale_battle): the
    owner's 2026-11-20 directive names its own Teleportation there (「召喚または攻撃を受けてHPが
    800を下回ったとき、または対象が距離2より近づいたときテレポートの巻物で離脱する」)."""
    from hengbot import angband_finale_battle, deep_climb, destruction_use, threat_tiers  # noqa: F401 -- import cycle

    # Owner 2026-11-22 「上りの間は即死以外でもテレポートを許す」: the Castle's climb off 50F+
    # (deep_climb) reads the teleport as above 50F.
    return (snapshot.dungeon_level >= DEEP_FLOOR_DEPTH and threat_tiers.acts_here(policy, snapshot)
            and not angband_finale_battle.applies(policy, snapshot)
            and not deep_climb.on_floor(policy, snapshot))


def fire_p95(policy, snapshot) -> int:
    """The next action's p95 of the engagement's monsters with a line of fire, read as the
    damage estimate reads it (line_of_fire ``danger``: owner 2026-11-15,
    maintainability review Q5 「被害の見積りと同じにする」; it read line_of_fire.counting, which
    takes an unknown grid for a wall, before).

    Plus the observed unseen loss, the correction the 即死 test adds (threat_projection
    ``unseen_correction``, instant_death's own reader): damage that reached the player is proof
    of a line of fire (line_of_fire ``note(proof=True)``), so an unseen attacker is not a monster
    "without a line of fire".  n1-c life-216 (Angband 80F, 2026-11-18): while Recall counted
    down an unseen はぐれメタル took 369 and then 228 per board; 即死 held (HP 261, 133), but this
    sum read 0, so no teleport was offered (``no_means``) and the character died waiting."""
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    from hengbot.threat_projection import _with_adjusted_speed, unseen_correction

    def compute():
        hostiles = [_with_adjusted_speed(monster)
                    for monster in threat_tiers.engagement(policy, snapshot)]
        if not hostiles:
            return 0
        in_fire = sum(p95 for _monster, p95 in in_fire_p95(policy, snapshot, hostiles))
        return in_fire + unseen_correction(policy, snapshot, hostiles)
    return decision_memo(policy, "deep_teleport.fire_p95", snapshot, None, compute)


def in_fire_p95(policy, snapshot, hostiles) -> list:
    """(monster, its next action's operational p95) of each of ``hostiles`` (at their adjusted
    speed) with a line of fire to the player (line_of_fire ``danger``): ``fire_p95``'s terms,
    also the unseen retreat's reading of a monster that came into view (policy_supply
    ``_unseen_retreat_key``)."""
    if not hostiles:
        return []
    rows = policy.threat_prediction(snapshot, hostiles, 1).get("monsters", ())
    return [(monster, row.get("operational_contribution", 0))
            for monster, row in zip(hostiles, rows)
            if line_of_fire.danger(policy, snapshot, monster)]


def allows(policy, snapshot) -> bool:
    """The self-teleport may be read or cast on this board.  While Recall counts down the owner's
    2026-11-15 rule (recall_wait_teleport) holds too, at every depth.  A worn NO_AC piece with a
    melee hostile closing lets it through (no_ac_recall, owner 2026-11-21 「打撃の届く敵を寄せない」)."""
    if no_ac_recall.teleport_due(policy, snapshot):
        return True
    if recall_wait_teleport.withheld(policy, snapshot):
        return False
    if not applies(policy, snapshot):
        return True
    return fire_p95(policy, snapshot) >= snapshot.player.hp and not landed_threats(policy, snapshot)


def _monsters(snapshot) -> list:
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile]


def note_teleport(policy, snapshot) -> None:
    """A Teleportation is let through on this board: remember who has a line of fire now."""
    if not applies(policy, snapshot):
        return
    in_fire = frozenset(monster.index for monster in _monsters(snapshot)
                        if line_of_fire.counting(policy, snapshot, monster))
    _memory(policy).pending = (snapshot.floor_key, snapshot.turn, snapshot.player.position, in_fire)


def observe(policy, snapshot) -> None:
    """Every decision: settle the Teleportation let through on the previous board."""
    setattr(policy, NO_MEANS_NOTE, None)
    recall_wait_teleport.observe(policy)
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        return
    if memory.landed is not None and memory.landed[0] != snapshot.floor_key:
        memory.landed = None
    if memory.pending is None or snapshot.turn <= memory.pending[1]:
        return
    floor, _turn, position, in_fire = memory.pending
    memory.pending = None
    if snapshot.floor_key != floor or snapshot.player.position == position:
        return
    still = frozenset(monster.index for monster in _monsters(snapshot)
                      if monster.index in in_fire and line_of_fire.counting(policy, snapshot, monster))
    memory.landed = (floor, still) if still else None


def landed_threats(policy, snapshot) -> list:
    """The engagement's monsters the previous Teleportation on this floor landed in the line of
    fire of, now within *Destruction*'s sure radius, when *Destruction* can be used on them."""
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    memory = getattr(policy, MEMORY, None)
    landed = None if memory is None else memory.landed
    if landed is None or landed[0] != snapshot.floor_key:
        return []
    threats = [monster for monster in threat_tiers.engagement(policy, snapshot)
               if monster.index in landed[1]
               and destruction_use.in_sure_radius(snapshot, monster)]
    if not threats or not destruction_use.usable(policy, snapshot, leaving=threats):
        return []
    return threats


def concerned(policy, snapshot) -> list:
    """The engagement hostiles, awake or asleep, that hurt from contact, but those
    *Destruction* spares (the module docstring)."""
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    hostiles = [monster for monster in threat_tiers.engagement(policy, snapshot)
                if not destruction_use.spares(policy, snapshot, monster)]
    if not hostiles:
        return []
    rows = policy.threat_prediction(snapshot, hostiles, 1, contact=True).get("monsters", ())
    return [monster for monster, row in zip(hostiles, rows)
            if row.get("operational_contribution", 0) > 0]


def is_self_teleport_scroll(item) -> bool:
    return item is not None and item.tval == TVAL_SCROLL and item.sval in SCROLL_SVALS


def _walk_step(policy, snapshot, targets):
    """The step toward the nearest grid within the sure radius of the walk's subject
    (destruction_use ``reach_subject``: the most dangerous of ``targets`` from contact), else
    None: under the approach's gates (threat_tiers._approach_targets but its in-view refusal),
    and none when that monster is in reach already (only the use answers there, and its gates
    refused it).  A nearer, weaker target inside the radius is no reason to stop short (n1-c
    life-216, 64F 2026-11-16: the sleeping 白衣の高位修行僧 at 10 held the walk while the use
    waited for the sleeping ミッド・タイタン at 15, and Recall was read in its place); since owner
    2026-11-17 Q1 (「脅威のどれか1体が半径13以内なら使う」) the use itself answers there first
    (``usable(leaving=targets)``: any of them in the radius), so the walk is asked only when the
    use's other gates refuse it."""
    from hengbot import destruction_use

    if not destruction_use.approach_gates(policy, snapshot):
        return None
    # The quest's target is never walked to (destruction_use ``walk_spared_race``, owner
    # 2026-11-22 「近づかず」).
    return destruction_use.walk_step(policy, snapshot, destruction_use.reach_subject(
        policy, snapshot, targets, destruction_use.walk_spared_race(policy, snapshot)))


def _walk_key(policy, snapshot, targets) -> str | None:
    """A step of ``_walk_step``, else None."""
    from hengbot import threat_tiers  # noqa: F401 -- import cycle

    step = _walk_step(policy, snapshot, targets)
    if step is None:
        return None
    policy.last_reason = threat_tiers.APPROACH_REASON
    return policy._step_toward(snapshot, step)


def movement_refused(policy, snapshot) -> bool:
    """A teleport no monster prompts (the stuck and livelock escapes) is not read here: 50F+
    where the tiers act, off the 即死 board (the module docstring)."""
    return applies(policy, snapshot) and fire_p95(policy, snapshot) < snapshot.player.hp


def _recall_key(policy, snapshot, reason: str) -> str | None:
    """Word of Recall in the teleport's place under ``reason``, else None: not on a quest floor,
    not while it counts down, and only when a scroll can be read."""
    player = snapshot.player
    if (snapshot.floor_key[2] != 0 or player.recalling or player.blind or player.confused
            or not policy._can_read_scrolls(snapshot)):
        return None
    recall = policy._find_recall_scroll(snapshot)
    if recall is None:
        return None
    key = policy._read_dungeon_recall_scroll_key(snapshot, recall)
    if key is None:
        return None
    policy._stuck_escape_streak = 0
    return_start.start(policy)
    policy.last_reason = reason
    if reason == RECALL_REASON:
        # Owner 2026-11-23 「帰還を読んでから待つ間に拾う」: the wait's pickup (deep_recall_loot).
        deep_recall_loot.note_read(policy, snapshot)
    return key


def _recall_available(policy, snapshot) -> bool:
    """``_recall_key`` would read Recall here (no state is changed)."""
    player = snapshot.player
    return (snapshot.floor_key[2] == 0 and not player.recalling and not player.blind
            and not player.confused and policy._can_read_scrolls(snapshot)
            and policy._find_recall_scroll(snapshot) is not None)


def _walk_available(policy, snapshot, targets) -> bool:
    """``_walk_key`` would step here (no state)."""
    return _walk_step(policy, snapshot, targets) is not None


def no_means(policy, snapshot) -> bool:
    """50F+ off the 即死 board with no Recall, and no concerned monster or no *Destruction* use on
    the concerned ones and no walk toward one: the self-teleport is not offered (the module
    docstring).  Pure, memoised for the decision; False while it is being computed (a finder
    asked from inside).

    The one predicate every finder of the self-teleport asks, so the owner's 2026-11-15 rule
    while Recall counts down (recall_wait_teleport, at every depth) withholds it here too; a worn
    NO_AC piece with a melee hostile closing offers it (no_ac_recall, owner 2026-11-21)."""
    if no_ac_recall.teleport_due(policy, snapshot):
        return False
    if recall_wait_teleport.withheld(policy, snapshot):
        return True
    if getattr(policy, _NO_MEANS_BUSY, False) or not applies(policy, snapshot):
        return False

    def compute():
        from hengbot import destruction_use

        capture = policy.__dict__.pop("_claim_target_capture", None)
        setattr(policy, _NO_MEANS_BUSY, True)
        try:
            if fire_p95(policy, snapshot) >= snapshot.player.hp:
                return False
            if _recall_available(policy, snapshot):
                return False
            targets = concerned(policy, snapshot)
            return not targets or (not destruction_use.usable(policy, snapshot, leaving=targets)
                                   and not _walk_available(policy, snapshot, targets))
        finally:
            setattr(policy, _NO_MEANS_BUSY, False)
            if capture is not None:
                policy._claim_target_capture = capture
    held = decision_memo(policy, "deep_teleport.no_means", snapshot, None, compute)
    if held:
        setattr(policy, NO_MEANS_NOTE, snapshot.turn)
    return held


def report(policy) -> dict | None:
    """The decision record's field: the branch, when the finders held the teleport back."""
    turn = getattr(policy, NO_MEANS_NOTE, None)
    if turn is None:
        return recall_wait_teleport.report(policy)
    return {"branch": NO_MEANS_BRANCH, "turn": turn}


def _refused_key(policy, snapshot) -> str | None:
    """Off the 即死 board, nothing *Destruction* answers: Recall, else a search turn (nothing is
    read).  Without Recall the finders hold the teleport back first (``no_means``), so this
    search only answers a read that bypassed them (a read whose *Destruction* answer
    ``no_means`` foresaw and the use then refused)."""
    recall = _recall_key(policy, snapshot, RECALL_REASON)
    if recall is not None:
        return recall
    setattr(policy, NO_MEANS_NOTE, snapshot.turn)
    policy.last_reason = HOLD_REASON
    return search_ban.wait_key(snapshot)


def _stuck_goals(policy, snapshot) -> set:
    """The known staircases the floor may be left by (the idle ladder's stair goal) and the
    frontiers (the unexplored ground)."""
    locked = policy._floor_navigation_exit_locked(snapshot)
    descent = not locked and not policy._descent_is_blocked(snapshot)
    goals = set()
    for grid in snapshot.grids.values():
        if not locked and (policy._is_upstairs_target(grid)
                           or descent and policy._is_descent_target(snapshot, grid)):
            goals.add(grid.position)
        elif policy._is_frontier(snapshot, grid):
            goals.add(grid.position)
    return goals


def stuck_key(policy, snapshot, *, recall: bool = True) -> str | None:
    """In place of a movement teleport ``movement_refused`` refuses (the module docstring): the
    walk to a goal, else Stone to Mud toward one, else Recall (not with ``recall`` False: the
    99F/100F battle's floors, angband_finale_battle ``keeps_scrolls``); None on a goal (the
    floor's own ladder goes on) or with no means left."""
    from hengbot import retreat_enclosure

    if snapshot.player.recalling:
        return None
    here = snapshot.player.position
    memory = getattr(policy, STUCK_MEMORY, None)
    reached = memory[1] if memory is not None and memory[0] == snapshot.floor_key else frozenset()
    goals = _stuck_goals(policy, snapshot) - reached
    if here in goals:
        setattr(policy, STUCK_MEMORY, (snapshot.floor_key, reached | {here}))
        policy._stuck_escape_streak = 0
        return None
    if goals:
        walk = policy._nearest_goal_step(snapshot, lambda grid: grid.position in goals)
        if walk is not None:
            policy.last_reason = STUCK_WALK_REASON
            return policy._step_toward(snapshot, walk)
        melt = retreat_enclosure.melt_toward_key(
            policy, snapshot, frozenset(), goals, STUCK_MELT_REASON, power_first=True)
        if melt is not None:
            return melt
    return _recall_key(policy, snapshot, STUCK_RECALL_REASON) if recall else None


def substitute(policy, snapshot, *, teleportation: bool = True) -> str | None:
    """The key in place of a self-teleport ``allows`` refuses here, else None (read it).
    ``teleportation``: the teleport is a Teleportation (not Phase Door); one let through is
    remembered for its landing (``note_teleport``)."""
    cross_rules.consult(policy, cross_rules.DEEP_TELEPORT)
    instead = _substitute(policy, snapshot)
    if instead is None and teleportation:
        note_teleport(policy, snapshot)
    return instead


def _substitute(policy, snapshot) -> str | None:
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    if allows(policy, snapshot):
        return None
    if recall_wait_teleport.withheld(policy, snapshot):
        # While Recall counts down nothing is read in the refused teleport's place.
        policy.last_reason = recall_wait_teleport.HOLD_REASON
        return search_ban.wait_key(snapshot)
    if fire_p95(policy, snapshot) >= snapshot.player.hp:
        # The 即死 board refused only for the landing in fire: *Destruction*, else the teleport.
        return destruction_use.key(policy, snapshot, leaving=landed_threats(policy, snapshot),
                                   suffix=LANDED_SUFFIX)
    targets = concerned(policy, snapshot)
    if not targets:
        return _refused_key(policy, snapshot)
    if destruction_use.usable(policy, snapshot, leaving=targets):
        used = destruction_use.key(policy, snapshot, leaving=targets, suffix=DESTRUCTION_SUFFIX)
        if used is not None:
            return used
    approach = threat_tiers.approach_key(policy, snapshot, targets)
    if approach is not None:
        return approach
    walk = _walk_key(policy, snapshot, targets)
    if walk is not None:
        return walk
    return _refused_key(policy, snapshot)


def scroll_substitute(policy, snapshot, item) -> str | None:
    """``substitute`` for a read of ``item`` (only Teleportation and Phase Door)."""
    if not is_self_teleport_scroll(item):
        return None
    return substitute(policy, snapshot, teleportation=item.sval == SV_SCROLL_TELEPORT)


def forget_destroyed(policy, keys) -> None:
    """The monsters a *Destruction* deleted (``keys``: (index, race)) leave this memory
    (owner 2026-11-15, maintainability review Q6 「全部から消す」; monster_memory
    ``DESTRUCTION_FORGETS``)."""
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        return
    indices = {index for index, _race in keys}
    if memory.pending is not None:
        floor, turn, position, in_fire = memory.pending
        memory.pending = (floor, turn, position, frozenset(in_fire) - indices)
    if memory.landed is not None:
        floor, still = memory.landed
        kept = frozenset(still) - indices
        memory.landed = (floor, kept) if kept else None
