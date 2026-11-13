"""The combat layer of the dungeon ladder (dungeon_ladder.LADDER, layer "combat").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the pre-combat rungs
(ladder_pre_combat), above the safe-now maintenance, objectives, rest, descent and idle.  The
status threats, the flee, the sensed T1 leave, the summoner's retreat, the fundraising
equipment, the adjacent answer, the gear retreat, the ranged phase, the summoner wait, the
material threat's repositioning and the quest target's hunt.  The rungs are asked top-down
and the first answer wins, as in ``_decide``: several end the decision with None (an entry
refused, or the detected-threat hold's timeout), and that None is ``_decide``'s answer as it
was.  ``PASS`` hands the decision on to the layers below.  scripts/dungeon_ladder_lint.py
reads the rows here (dungeon_ladder.LAYER_MODULES), so the table still states this order.

The hostile views are ``_decide``'s, passed in unchanged, by name; ``mining_hostiles`` is the
view the pre-combat layer chose (ladder_pre_combat.MiningViews).
"""
from __future__ import annotations

from hengbot import combat_answer, destruction_use, disenchant_avoid, immobile_threat_memory, me_ranged_first, paralyzer_contact, threat_tiers, town_last_stand
from functools import partial
from hengbot.dungeon_ladder import PASS
from hengbot.policy_constants import DETECTED_THREAT_HOLD_MAX_GAME_TURNS, ExplorationPathOutcome, SUMMONER_CHOKE_NEIGHBORS, SUMMONER_EXPOSED_NEIGHBORS, SUMMONER_RANGED_KILL_SHOTS, UP_STAIRS_KEY, WAIT_KEY
from hengbot.summoner_wait import hold_key
from hengbot.town_hold import MONSTER_CHASE_OWNERS as CLAIM_MONSTER_CHASE_OWNERS


def key(
    policy,
    snapshot,
    *,
    strategic_hostiles,
    strategic_adjacent,
    physical_hostiles,
    physical_adjacent,
    mining_hostiles,
):
    """The combat layer's answer, or PASS when none of its rungs acts."""
    player = snapshot.player
    # 1. Survival: flee when hurt, swarmed, or too afraid to fight back.
    # Once a confusion/paralysis attacker has triggered this rung on the
    # floor, it stays a threat while it can reach us: a one-step retreat
    # (or a speed potion) pushes it just outside its 3-turn reach, and
    # the ordinary ladder then fired at / meleed it until it closed again
    # (Castle 20F 2026-10-02 13:10:57-13:11:05, ピンク・ホラー: retreat at
    # path distance 3, ranged:fire-target at 4, alternating).
    latch = getattr(policy, "_status_threat_latch", None)
    latched = (
        latch[1] if latch is not None and latch[0] == snapshot.floor_key
        else frozenset()
    )
    status_threats = policy._unresisted_melee_status_threats(
        snapshot, physical_hostiles, latched=latched
    )
    if physical_adjacent and not any(
        monster.distance <= 1 for monster in status_threats
    ) and status_threats and all(
        any(
            blow.effect == "PARALYZE"
            for blow in policy._monrace_knowledge[monster.race_id].blows
        )
        for monster in status_threats
    ):
        # Finish the fight already in contact; a merely approaching status
        # monster must not pull us away from a different adjacent enemy.
        status_threats = []
    if status_threats:
        policy._status_threat_latch = (
            snapshot.floor_key,
            latched | {
                (monster.index, monster.race_id) for monster in status_threats
            },
        )
        escape = policy._town_producer_entry("_escape_by_stairs", lambda: policy._escape_by_stairs(snapshot), family="survival")
        if escape is not None:
            policy.last_reason = "status-threat:stairs"
            return escape
        # Once a confusion/paralysis attacker is adjacent, taking a normal
        # retreat step donates the disabling blow.  Relocate before it lands.
        # A walk cannot outpace a mover at least as fast either
        # (paralyzer_contact.follows_walk).
        if (
            any(
                monster.distance <= 1
                or paralyzer_contact.follows_walk(policy, snapshot, monster)
                for monster in status_threats
            )
            and not player.confused
        ):
            # *Destruction* is used blind too (owner 2026-11-08 「盲目でも使う」); the scroll needs sight.
            if (used := destruction_use.key(policy, snapshot)) is not None:
                return used
            scroll = None if player.blind else policy._escape_scroll(snapshot)
            if scroll is not None:
                policy.last_reason = "status-threat:scroll"
                return policy._read_key(snapshot, scroll)
        step = policy._town_producer_entry("_flee_step#1", lambda: policy._flee_step(snapshot, status_threats))
        if step is not None:
            # Make the retreat a persistent navigation veto for this floor.
            # Otherwise fundraising/exploration immediately re-enters the
            # disabling monster's melee ring and alternates forever against
            # a stationary confusion/paralysis monster (notably Floating Eye).
            # Remember the whole visible adjacency ring rather than only the
            # cell we happened to retreat from: loot routing can approach the
            # same unsafe drop from several different directions.
            for threat in status_threats:
                policy._claim_engagement_avoid_cells(
                    (grid.position
                     for grid in snapshot.grids.values()
                     if grid.position.distance_to(threat.position) <= 1),
                    snapshot=snapshot, threats=(threat,),
                )
            policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            policy.last_reason = "status-threat:retreat"
            policy._declare_reach(step)
            return policy._town_producer_entry("_step_toward:survival", lambda: policy._step_toward(snapshot, step), family="survival")
        if not player.confused:
            # *Destruction* is used blind too (owner 2026-11-08 「盲目でも使う」); the scroll needs sight.
            if (used := destruction_use.key(policy, snapshot)) is not None:
                return used
            scroll = None if player.blind else policy._escape_scroll(snapshot)
            if scroll is not None:
                policy.last_reason = "status-threat:scroll"
                return policy._read_key(snapshot, scroll)
        policy.last_reason = "status-threat:wait"
        return WAIT_KEY

    # Ordinary flee deliberately stays strategic: once weak-breeder
    # extermination is impossible, their mere presence must not turn the
    # approved walk-out into flight. Physical status and escape hazards are
    # handled by the dedicated rungs above.
    if policy._should_flee(
        snapshot, strategic_hostiles, strategic_adjacent
    ):
        # For the town hold: every exit of this rung is escape, fleeing these.
        policy._declare_triggers(strategic_hostiles, family="escape")
        escape = policy._town_producer_entry("_escape_by_stairs", lambda: policy._escape_by_stairs(snapshot), family="survival")
        if escape is not None:
            policy.last_reason = (
                "flee:stairs-quest-fail"
                if policy._quest_exit_would_fail(snapshot)
                else "flee:stairs"
            )
            return escape
        if (
            (
                policy._fruitless_disengage_floor == snapshot.floor_key
                or policy._returning_to_town
                or policy._escape_state.owner in {"disengage", "return"}
            )
            and (
                blocker := policy._town_producer_entry("_blocking_escape_melee_key", lambda: policy._blocking_escape_melee_key(
                    snapshot, physical_hostiles, policy._is_upstairs_target
                ))
            )
            is not None
        ):
            # A declared walk-out must keep moving toward its known exit at
            # low HP too. One projected-easy corridor kill is safer than the
            # generic flee rung retreating back into the floor.
            policy.last_reason = "combat:disengage-clear-path"
            return blocker
        if (stand := town_last_stand.key(policy, snapshot, strategic_hostiles, "flee:cornered-attack")) is not None:
            return stand
        if (ranged := me_ranged_first.outpaced_afraid_key(policy, snapshot, strategic_adjacent)) is not None:
            return ranged  # a faster attacker follows every step away
        # Threat tiers step 6 (design 3.2): a leave the tiers decide walks only while no awake
        # hostile is faster and none reaches at range; else the relocation below (n1-c
        # life-168: 闇の審判『デス』, speed 120 against 110, walked to its death).
        tiers_leave = threat_tiers.leave_due(policy, snapshot, strategic_hostiles)
        tiers_walk = not tiers_leave or threat_tiers.walk_leaves(
            policy, snapshot, strategic_hostiles)
        step = (policy._town_producer_entry("_flee_step#2", lambda: policy._flee_step(snapshot, strategic_hostiles))
                if tiers_walk else None)
        if step is not None:
            # A survival flee can pre-empt the material-threat gate below
            # (notably for an over-level monster).  Persist the abandoned
            # square here as well, otherwise a remembered loot target can
            # immediately route back into it when the monster flickers out
            # of view, producing a seek-loot/flee two-cell oscillation.
            # A leave the threat tiers decided is such a square too (owner 2026-11-08
            # 「境に余裕を持たせる」: the decided side holds while the pack is out of sight,
            # threat_tiers.decided; n1-b's bear pack, T2 by 3 HP, was walked back to).
            if tiers_leave or policy._is_material_threat(snapshot, strategic_hostiles):
                policy._claim_engagement_avoid_cells(
                    (snapshot.player.position,),
                    snapshot=snapshot, threats=strategic_hostiles,
                )
                policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            policy.last_reason = "flee"
            return policy._town_producer_entry("_step_toward:escape", lambda: policy._step_toward(snapshot, step), family="escape")
        # Cornered: try a relocation scroll before anything desperate.  A leave the tiers
        # decided (T1) is the owner's 2026-11-09 B case: *Destruction* need not see the
        # threat awake (destruction_use.key leaving).
        if (used := destruction_use.key(policy, snapshot, leaving=threat_tiers.engagement(
                policy, snapshot) if tiers_leave else None)) is not None:
            return used
        scroll = policy._escape_scroll(snapshot)
        if scroll is not None:
            policy.last_reason = "flee:scroll"
            return policy._read_key(snapshot, scroll)
        cornered = combat_answer.adjacent_attack(
            policy, snapshot, strategic_adjacent, "flee:cornered-attack",
            blow=lambda target: policy._town_producer_entry(
                "_direction_key#1", partial(combat_answer.direct_blow, policy, snapshot, target)))
        if cornered is not None:
            return cornered.key
        # A mining run the ruled-out unique ended takes its decided exit
        # rather than waiting in place (n1-c life-193, _mining_abort_exit_key).
        if (abort_exit := policy._town_producer_entry(
                "_mining_abort_exit_key",
                lambda: policy._mining_abort_exit_key(snapshot, strategic_hostiles),
                family="fundraising")) is not None:
            return abort_exit
        policy.last_reason = "flee:wait"
        return WAIT_KEY

    # Owner 2026-11-08: inside the sensing radius of an awake T1 hostile, seen or detected,
    # leave now (threat_tiers.sensed_t1_leave_key); never rest there.
    if (sensed := threat_tiers.sensed_t1_leave_key(policy, snapshot)) is not None:
        return sensed

    # A summoner with room around the player can turn a manageable fight into
    # an irreversible surround. Leave open terrain before engaging, ideally
    # breaking into a corridor where only a few monsters can reach us. But an
    # ALREADY-ADJACENT summoner is past that point: walking away just donates
    # free hits every step (and a faster summoner stays adjacent the whole
    # way) — kill it instead; melee below already targets summoners first.
    summoners = [
        monster for monster in strategic_hostiles
        if monster.can_summon and not monster.asleep
        and not policy._summoner_never_approaches(snapshot, monster)
    ]
    # A KILL_NUMBER pack gets the same reviewed choke-point movement as a
    # summoner fight.  The normal ranged phase below then softens pursuers.
    corridor_threats = summoners
    if summoners and policy._active_kill_quest_id(snapshot) is not None:
        corridor_threats = strategic_hostiles
    summoner_adjacent = any(
        player.position.distance_to(monster.position) <= 1 for monster in corridor_threats
    )
    if (
        corridor_threats
        and not summoner_adjacent
        and policy._open_neighbor_count(snapshot, player.position)
        >= SUMMONER_EXPOSED_NEIGHBORS
        and not any(
            (shots := policy._summoner_shots_to_kill(snapshot, monster))
            is not None and shots <= SUMMONER_RANGED_KILL_SHOTS
            and policy._summoner_ranged_attack_available(snapshot, monster)
            for monster in summoners
        )
    ):
        current = snapshot.grid_at(player.position)
        if current is not None and policy._is_upstairs_target(current) and not policy._quest_floor_exit_locked(snapshot):
            policy._defer_descent(snapshot)
            policy.last_reason = (
                "summoner:stairs-quest-fail"
                if policy._quest_exit_would_fail(snapshot)
                else "summoner:stairs"
            )
            policy._declare_triggers(corridor_threats)
            return UP_STAIRS_KEY
        step = policy._summoner_retreat_step(
            snapshot, corridor_threats, strategic_hostiles
        )
        if step is not None:
            # The same navigation veto as the flee / threat:reposition
            # retreats: persist the abandoned (exposed, in-view) square.
            # One step later the summoner is out of view, the retreat
            # rung falls silent, and a remembered loot target routed
            # straight back into this square -- summoner:retreat '3' /
            # seek-loot '7' between (23,115)/(24,116) until the loop
            # detector stopped the bot (Castle 20F, 2026-10-02 15:14-15:16).
            policy._claim_engagement_avoid_cells(
                (snapshot.player.position,), snapshot=snapshot, threats=corridor_threats)
            policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            policy.last_reason = "summoner:retreat"
            return policy._town_producer_entry("_step_toward:escape", lambda: policy._step_toward(snapshot, step), family="escape")

    combat_equip = policy._town_producer_entry("_fundraising_combat_equipment_key", lambda: policy._fundraising_combat_equipment_key(
        snapshot, mining_hostiles
    ), family="equipment-txn")
    if combat_equip is not None:
        return combat_equip

    # With no approved fixed-map profile, a visible runtime quest race owns
    # ordinary combat selection after all emergency/flee/reposition gates.
    quest_targets = policy._locked_kill_quest_targets(
        snapshot, strategic_hostiles
    )
    combat_hostiles = quest_targets or strategic_hostiles
    combat_adjacent = disenchant_avoid.not_avoided(policy, snapshot, [
        monster
        for monster in strategic_adjacent
        if monster in combat_hostiles
    ])

    # 2. Melee an adjacent hostile (weakest first) — unless too afraid.
    adjacent_answer = combat_answer.adjacent_attack(
        policy, snapshot, combat_adjacent, "melee",
        # A town fight is survival (owner 2026-10-31) and _town_kill_mob_key
        # delegates the adjacent one to this rung: an errand hold must not
        # refuse it, or the WAIT it leaves spends the escape kit and walks
        # away from a monster the hunt walks back to (n1-c life-123).
        blow=lambda target: policy._town_producer_entry(
            "_direction_key#2", partial(combat_answer.direct_blow, policy, snapshot, target),
            family="survival"),
        # A chase closed on its monster: combat takes over (rev 9.2 M, for
        # whichever chasing owner holds it).
        on_engage=lambda: policy._complete_claim_goal(
            "closed-to-melee",
            owners=CLAIM_MONSTER_CHASE_OWNERS,
            monsters={
                (monster.index, monster.race_id) for monster in combat_adjacent
            },
        ))
    if adjacent_answer is not None:
        return adjacent_answer.key  # NO_MELEE refuses melee only (fear flees above)

    # Owner 2026-11-05: what disenchants the gear is walked away from, not shot.
    gear_retreat = disenchant_avoid.retreat_key(
        policy, snapshot, strategic_hostiles, immobile_threat_memory.ringed)
    if gear_retreat is not None:
        return gear_retreat
    combat_hostiles = disenchant_avoid.fought(policy, snapshot, combat_hostiles)

    # 2r. Ranged attack: fire matching ammo (or throw a spare oil flask) at a
    # ray-aligned hostile before it closes. Fear blocks melee but NOT firing,
    # so an afraid archer still fights back while it retreats.
    ranged = policy._town_producer_entry("_ranged_attack_key#2", lambda: policy._ranged_attack_key(
        snapshot, combat_hostiles, combat_adjacent
    ))
    if ranged is not None:
        return ranged

    if summoners and all(monster.distance > 2 for monster in summoners):
        # A detected summoner can reach this generic combat wait before
        # detected-threat preparation runs. Start the same bounded episode
        # here, at the choke cell, so loot cannot pull us off it and make
        # preparation re-arm the clock on every return.
        unseen_detected = any(
            monster.perception == "detected"
            for monster in policy._perceived_hostiles(snapshot)
        )
        at_choke = (
            policy._open_neighbor_count(snapshot, player.position)
            <= SUMMONER_CHOKE_NEIGHBORS - 1
        )
        if unseen_detected and at_choke and not snapshot.visible_monsters:
            hold = getattr(policy, "_detected_threat_hold", None)
            if hold is None or hold[0] != snapshot.floor_key:
                hold = (snapshot.floor_key, snapshot.turn)
                policy._detected_threat_hold = hold
                policy._detected_threat_hold_position = player.position
            elif getattr(policy, "_detected_threat_hold_position", None) is None:
                # A restored pre-position checkpoint keeps its original
                # timer and adopts the current choke cell.
                policy._detected_threat_hold_position = player.position
            if snapshot.turn - hold[1] > DETECTED_THREAT_HOLD_MAX_GAME_TURNS:
                return None
        hold = hold_key(policy, snapshot, summoners)
        if hold is not None:
            return hold

    # A material threat that cannot be attacked from the current square
    # must not fall through to descent or exploration.  Live on Orc cave
    # 19F, three fast monsters at distance two were already worth 57% of
    # current HP over three turns; ordinary exploration then stepped into
    # their pack and turned them into a five-monster surround.
    if strategic_hostiles and policy._is_material_threat(snapshot, strategic_hostiles):
        step = policy._town_producer_entry("_flee_step#3", lambda: policy._flee_step(snapshot, strategic_hostiles))
        if step is not None:
            # This is the same navigation veto as the projected-melee gate
            # below.  Without persisting the abandoned square, generic
            # secret-wall exploration can immediately reverse this retreat
            # and alternate with it forever.
            policy._claim_engagement_avoid_cells(
                (snapshot.player.position,), snapshot=snapshot, threats=strategic_hostiles)
            policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            policy.last_reason = "threat:reposition"
            policy._declare_reach(step)
            policy._declare_triggers(strategic_hostiles)
            return policy._town_producer_entry("_step_toward:positioning", lambda: policy._step_toward(snapshot, step), family="positioning")
        if (used := destruction_use.key(policy, snapshot)) is not None:
            return used
        scroll = policy._escape_scroll(snapshot)
        if scroll is not None:
            policy.last_reason = "threat:scroll"
            return policy._read_key(snapshot, scroll)
        policy.last_reason = "threat:wait"
        return WAIT_KEY

    if quest_targets:
        step = policy._town_producer_entry("_hunt_step#1", lambda: policy._hunt_step(snapshot, quest_targets, allow_cooling=False))
        if step is not None:
            policy.last_reason = "hunt:quest-target"
            policy._declare_monster(getattr(policy, "_hunt_step_target", None))
            return policy._town_producer_entry("_step_toward:hunt", lambda: policy._step_toward(snapshot, step), family="hunt")
    return PASS
