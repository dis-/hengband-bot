"""The objectives layer of the dungeon ladder (dungeon_ladder.LADDER, layer "objectives").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the safe-now layer
(ladder_safe_now), above the rest (ladder_rest).  Town and dungeon rungs interleave here, in
the order ``_decide`` had them: the kill quest's floor recovery, the hunt target's route, the
Home disposal, the unsafe recall's cancel and the town's recall waits, the town's eating,
shelter and recovery, the weapon restore, the fixed quests and the loot of victory and
conquest, the potions to quaff, the equipment identification, fundraising, the full pack, the
chests and the loot, the livelock, the returns to town, the Home catalogue and the shopping
approach, the town's item, device, curse, launcher and teleport work, the equipment
transaction, the light, the town's special work, destruction and overflow, the Home's atomic
withdrawal and the restock.  The rungs are asked top-down and the first answer wins, as in
``_decide``: several end the decision with None (an entry refused), and that None is
``_decide``'s answer as it was.  ``PASS`` hands the decision on to the rest.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the table
still states this order.
"""
from __future__ import annotations

from hengbot import hunt_target
from hengbot.dungeon_ladder import PASS
from hengbot.home_visit import HomeVisitKind
from hengbot.item_reservation import reserved_item_command
from hengbot.model import STORE_ALCHEMIST, STORE_HOME, STORE_TEMPLE
from hengbot.policy_constants import HOME_BATCH_RESERVED_SLOTS, MIN_FREE_PACK_SLOTS, MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY, REST_MACRO, WAIT_KEY
from hengbot.town_hold import LOOT_OWNERS as CLAIM_LOOT_OWNERS, standing_claim as town_standing_claim
from hengbot.town_terminal import NOT_APPLICABLE, gather_identify_device, identification_ready_in_pack, rung_terminal, terminal_admission

# An ordinary supply return may make a short detour for realised value. Critical
# returns (food/light/pack/emergency) never wait for loot (policy.py imports these).
RETURN_LOOT_SWEEP_MAX_DISTANCE = 12
RETURN_LOOT_SWEEP_TRIGGERS = frozenset(
    {"recall-low", "teleport-low", "cure-low", "next-depth-kit"}
)


def key(policy, snapshot, *, strategic_hostiles, physical_hostiles, physical_adjacent):
    """The objectives layer's answer, or PASS when none of its rungs acts."""
    player = snapshot.player
    quest_floor_recovery = policy._town_producer_entry("_kill_quest_floor_recovery_key", lambda: policy._kill_quest_floor_recovery_key(snapshot))
    if quest_floor_recovery is not None:
        return quest_floor_recovery
    # The hunted quest target or guardian a detection showed (hunt_target).
    hunt_route = hunt_target.route_key(policy, snapshot, physical_hostiles)
    if hunt_route is not None:
        return hunt_route

    home_disposal = policy._town_producer_entry("_home_disposal_processing_key", lambda: policy._home_disposal_processing_key(snapshot))
    if home_disposal is not None:
        return home_disposal

    cancel_unsafe_recall = policy._town_producer_entry("_town_cancel_unsafe_recall_key", lambda: policy._town_cancel_unsafe_recall_key(snapshot), family="survival")
    if cancel_unsafe_recall is not None:
        return cancel_unsafe_recall
    if snapshot.in_town and snapshot.player.recalling:
        # Once Hengband has accepted a town recall, departure owns every
        # remaining surface decision.  This covers both a fresh process
        # attaching to an engine-owned recall and a recall armed by this
        # policy: rebuilding the optional town plan here could otherwise
        # start a new shop/Home errand after the final departure read.
        # Store tiles are still stepped off so the recall can complete.
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.is_store:
            neighbors = policy._walkable_neighbors(
                snapshot, snapshot.player.position
            )
            if neighbors:
                policy.last_reason = "town:wait-recall-step-off"
                policy._declare_reach(neighbors[0])
                key = policy._town_producer_entry("_step_toward:departure", lambda: policy._step_toward(snapshot, neighbors[0]), family="departure")
                if key is not None:
                    policy._offer_execution(
                        key, producer="departure",
                        work_id="town:recall-step-off",
                        next_step="recall.step-off-store",
                        expected_effect="store-cell-cleared",
                    )
                else:
                    policy._offer_execution_no_step(
                        producer="departure",
                        work_id="town:recall-step-off",
                        cause="step-off-unavailable",
                    )
                return key
        policy.last_reason = "town:wait-recall"
        policy._offer_execution(
            WAIT_KEY, producer="departure",
            work_id="town:recall-countdown",
            next_step="recall.observe-arrival",
            expected_effect="floor-change",
        )
        return WAIT_KEY

    # Native travel can cross most of town without another bot decision.
    # Eat first once hunger is visible so a long shop trip cannot continue
    # into weakness merely because the ordinary food check is later below.
    if snapshot.in_town and player.hungry and not physical_hostiles:
        food = policy._find_edible(snapshot)
        if food is not None:
            policy.last_reason = "town:eat-before-travel"
            return reserved_item_command(policy, snapshot, "eat", food)

    # Wilderness monsters can enter town, so shopping is not safe while
    # injured. After an unseen hit, head for the nearest store entrance;
    # otherwise recover fully before crossing town again.
    if snapshot.in_town and not physical_hostiles:
        if policy._took_damage:
            policy._claim_target_capture = []
            try:
                shelter = policy._nearest_goal_step(snapshot, lambda grid: grid.is_store)
            finally:
                shelter_target = policy._take_claim_target()
            if shelter is not None:
                policy.last_reason = "town:seek-shelter"
                policy._declare_reach(shelter_target)
                return policy._town_producer_entry("_step_toward:survival", lambda: policy._step_toward(snapshot, shelter), family="survival")
        if (
            player.hp < player.max_hp
            or player.mp < player.max_mp
            or not policy._temporary_status_clear(snapshot)
        ) and player.food_state in {"normal", "full", "gorged"}:
            policy.last_reason = "town:recover"
            policy._offer_execution(
                REST_MACRO, producer="survival", work_id="town:recover",
                next_step="player.rest", expected_effect="hp/mp/status-recovered",
            )
            return REST_MACRO

    # An already-required combat-weapon restoration is an equipment safety
    # continuation, not new town work.  Finish it before pack-pressure
    # routing can relocate the player and invalidate the prepared mutation.
    restore_weapon = policy._town_producer_entry("_town_restore_weapon_key", lambda: policy._town_restore_weapon_key(snapshot))
    if restore_weapon is not None:
        return restore_weapon

    # Rung #1 applies only while stage-2 quest travel owns the town
    # (its intended_terminal, town_terminal.fixed_quest_return_intended_terminal).
    fixed_quest = policy._town_producer_entry("_fixed_quest_key#1", lambda: policy._fixed_quest_key(snapshot, strategic_hostiles))
    if fixed_quest is not None:
        return fixed_quest

    space_deposit = policy._town_producer_entry("_town_space_deposit_key", lambda: policy._town_space_deposit_key(snapshot))
    if space_deposit is not None:
        return space_deposit

    victory_loot = policy._town_producer_entry("_victory_loot_key", lambda: policy._victory_loot_key(snapshot))
    if victory_loot is not None:
        return victory_loot

    conquest_loot = policy._town_producer_entry("_conquest_loot_key", lambda: policy._conquest_loot_key(snapshot))
    if conquest_loot is not None:
        return conquest_loot

    fixed_quest = policy._town_producer_entry("_fixed_quest_key#2", lambda: policy._fixed_quest_key(snapshot, strategic_hostiles))
    if fixed_quest is not None:
        return fixed_quest

    stat_restore = policy._town_producer_entry("_stat_restore_quaff_key", lambda: policy._stat_restore_quaff_key(
        snapshot, physical_hostiles
    ))
    if stat_restore is not None:
        return stat_restore

    experience = policy._town_producer_entry("_experience_potion_quaff_key", lambda: policy._experience_potion_quaff_key(
        snapshot, physical_hostiles
    ))
    if experience is not None:
        return experience

    stat_gain = policy._town_producer_entry("_stat_gain_quaff_key", lambda: policy._stat_gain_quaff_key(snapshot, physical_hostiles))
    if stat_gain is not None:
        return stat_gain

    bounty = policy._town_producer_entry("_town_order_step4_key#2", lambda: policy._town_order_step4_key(snapshot))
    if bounty is not None:
        return bounty

    dungeon_identify = policy._dungeon_equipment_identify_key(
        snapshot, physical_hostiles
    )
    if dungeon_identify is not None:
        return dungeon_identify

    fundraising = policy._town_producer_entry("_fundraising_key#1", lambda: policy._fundraising_key(snapshot, strategic_hostiles))
    if fundraising is not None:
        return fundraising

    if (
        policy._count_recall_scrolls(snapshot)
        < policy._recall_shortage_retreat_threshold(snapshot.dungeon_level)
        and not policy._recall_shortage_opening_exempt(snapshot)
        and policy._fundraising_mode not in {"prepare", "mine", "scavenge"}
        and not snapshot.in_town
    ):
        # Preserve quest-floor exit locks below: setting the ordinary
        # return latch is sufficient, and the existing return owner
        # decides whether walking upward is currently legal.
        policy._note_return_start("recall-shortage")
        policy._returning_to_town = True
        policy._last_return_trigger = "recall-shortage"

    identify = policy._town_producer_entry("_pack_pressure_identify_key", lambda: policy._pack_pressure_identify_key(snapshot), family="identification")
    if identify is not None:
        return identify

    # In town, compact before departure whenever fewer than the required
    # number of loot slots remain. Dungeon compaction still waits for a full
    # pack, where returning becomes necessary if nothing can be discarded.
    if len(snapshot.inventory) >= PACK_CAPACITY or (
        snapshot.in_town
        and PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS
    ):
        destroy = policy._town_producer_entry("_full_pack_destroy_key", lambda: policy._full_pack_destroy_key(snapshot), family="shop-sell")
        if destroy is not None:
            return destroy

    # Process a carried chest while things are calm — BEFORE committing to
    # a supply return: the pipeline takes a couple dozen decisions and the
    # contents may themselves be the supplies (drop → step beside → s ×N →
    # D ×N → o ×N, the user-specified procedure). Emergencies never reach
    # here (handled at the top), so only the leisurely return is deferred.
    chest = policy._town_producer_entry("_chest_processing_key#2", lambda: policy._chest_processing_key(snapshot, physical_hostiles))
    if chest is not None:
        return chest

    # A routine supply return can afford a short sweep for already-seen safe
    # loot. Hunger, darkness, a full pack, and emergency returns never detour.
    # loot-before-recall (user 2026-09-23) deliberately does NOT widen this
    # gate: nothing may delay reading the scroll.  The collection it asks
    # for happens afterwards, inside the recall countdown, where the return
    # owner would otherwise stand still (_return_to_town_key).
    return_starting = (
        not snapshot.in_town and policy._should_start_town_return(snapshot)
    )
    if (
        (return_starting or policy._returning_to_town)
        and not player.recalling
        and not policy._emergency_return_active
        and policy._last_return_trigger in RETURN_LOOT_SWEEP_TRIGGERS
    ):
        return_loot = policy._town_producer_entry("_normal_loot_key#1", lambda: policy._normal_loot_key(
            snapshot,
            strategic_hostiles,
            max_path_distance=RETURN_LOOT_SWEEP_MAX_DISTANCE,
            seek_reason="return:seek-loot",
        ))
        if return_loot is not None:
            return return_loot

    # R1 navigation invariant: every mode below (including a latched town
    # return that can only wander) is some form of navigation. When
    # NAV_NO_PROGRESS_LIMIT decisions have produced no new coverage, no
    # first-visit tile, no target-distance improvement and no combat, they
    # are collectively livelocked regardless of how varied their reasons
    # look — leave the floor (recall/up-stairs), or stop visibly. This must
    # run ABOVE the town return: a return with no reachable exit degrades
    # to return:wander forever and would shadow the escape.
    livelock = policy._town_producer_entry("_navigation_livelock_key", lambda: policy._navigation_livelock_key(snapshot))
    if livelock is not None:
        return livelock

    # A fled breeder floor turns the ordinary return into a persistent
    # walk-out, but it remains a navigation owner: survival/combat above
    # and the livelock escape immediately above must retain priority.
    if (
        policy._breeder_walkout_active(snapshot)
        and policy._escape_state.owner in {None, "return"}
    ):
        policy._note_return_start(None)
        policy._returning_to_town = True
        walkout = policy._town_producer_entry("_return_to_town_key#2", lambda: policy._return_to_town_key(
            snapshot,
            strategic_hostiles,
            allow_recall=(
                policy._fundraising_mode != "mine"
                and policy._active_quest_id(snapshot) is None
            ),
        ))
        if walkout is not None:
            policy._escape_state.enter("return", policy.last_reason)
            return walkout

    # Worthless remains never travel to town (#70, owner 2026-10-18):
    # destroy them in the dungeon when a return starts, before the
    # latch and the Recall read; a latched return is not interrupted.
    if (
        return_starting and not policy._returning_to_town
        and not player.recalling
        and not policy._return_exit_locked(snapshot)
    ):
        junk = policy._town_producer_entry("_worthless_junk_destroy_key", lambda: policy._worthless_junk_destroy_key(snapshot), family="shop-sell")
        if junk is not None:
            return junk

    # Low supplies and a full pack are expedition-ending conditions. Once
    # triggered, keep heading upward even if using an item opens a pack slot.
    town_return = (
        None
        if policy._escape_state.owner not in {None, "return"}
        else policy._town_producer_entry("_return_to_town_key#3", lambda: policy._return_to_town_key(snapshot, strategic_hostiles))
    )
    if town_return is not None:
        policy._escape_state.enter("return", policy.last_reason)
        return town_return

    # Acquire the Home catalogue before a crowded pack blocks town work.
    if (
        snapshot.store is None
        and policy._active_quest_id(snapshot) is None
        and "quest-request" not in policy._town_turn_arbiter._retired
        and len(snapshot.inventory) >= PACK_CAPACITY - HOME_BATCH_RESERVED_SLOTS - 1
        and not policy._town_space_deposit_actionable(snapshot)
        and policy._home_atomic_withdraw_pending is None
        and policy._home_atomic_deposit_pending is None
        and not policy._home_entry_operation_posted
        and (not policy._equipment_catalog.home_scan_complete
             or policy._home_knowledge_invalidated)
        and not (
            policy._equipment_transaction_session is not None
            and policy._equipment_transaction_session.current_action is not None
            and policy._equipment_transaction_session.required_context == "outside_home"
        )
        and not policy._defer_town_errand("equipment-txn", "acquire-home-catalog")
        and policy._ensure_home_visit_request(snapshot)
    ):
        step = policy._shopping_approach_step(
            snapshot, STORE_HOME, requester="home-scan"
        )
        here = snapshot.grid_at(snapshot.player.position)
        if step is None and here is not None and here.store_number == STORE_HOME:
            # Acquiring an initial visit while already standing on the
            # entrance is the intentional WAIT activation, not a failed
            # route and not authority to step off/re-enter.
            step = snapshot.player.position
        if step is not None and policy._shopping_approach_store_type == STORE_HOME:
            catalogue_key = (policy._equipment_catalogue_only(snapshot)
                             and policy._town_producer_entry(
                "_home_catalogue_work_key",
                lambda: policy._home_catalogue_work_key(snapshot),
                family="equipment-txn",
            ))
            if isinstance(catalogue_key, str):
                return catalogue_key
            policy.last_reason = "equipment-transaction:acquire-home-catalog"
            key = policy._town_producer_entry("_shopping_approach_key#1", lambda: policy._shopping_approach_key(
                snapshot, step, "equipment-transaction:travel-home"
            ))
            if key is not None:
                policy._offer_execution(
                    key, producer="equipment-txn",
                    work_id="equipment:acquire-home-catalog",
                    next_step="home.approach-for-equipment-catalog",
                    expected_effect="home-catalog-available",
                )
            else:
                policy._offer_execution_no_step(
                    producer="equipment-txn",
                    work_id="equipment:acquire-home-catalog",
                    cause="home-approach-unavailable",
                )
            return key

    # Identification shares the mining budget: secure detection and a tool
    # first, retaining pending identification requests for afterwards.
    # A carried source reading a carried target spends none of it (owner
    # 10-31 「鑑定の手段がある時に…取り出して鑑定」): n1-a life-476 2026-11-04
    # 03:08 took five weapons out for its three *Identify* scrolls with a
    # mining set open, none was read, and the pack and the weight stopped
    # the visit under town:blocked:survival:recall_departure_ready.
    mining_holds_identification = (
        policy._fundraising_mode in {"prepare", "mine", "scavenge"}
        and not policy._fundraising_supplies_ready(snapshot)
    )
    if not mining_holds_identification:
        equipped_identification = policy._town_producer_entry("_town_equipped_identification_key", lambda: policy._town_equipped_identification_key(snapshot, macro=True))
        if equipped_identification is not None:
            return equipped_identification
    if not mining_holds_identification or identification_ready_in_pack(policy, snapshot):
        item_processing = policy._town_item_processing_key(snapshot)
        if item_processing is not None:
            return item_processing
    # A carried device identified by a held source (the Magic-Eater's
    # absorbed Identify, a carried staff or scroll) spends none of the
    # mining budget either: n1-c life-203 2026-11-12 22:38 held its
    # unknown wand and staff of Light through the mining set whose food
    # gate they would have answered, and stopped three times (owner
    # 「充填できない理由と食事ができない理由は鑑定を後回しにしているロジックの不備」).
    if (not mining_holds_identification
            or gather_identify_device(policy, snapshot).source_held):
        device_processing = policy._town_producer_entry("_town_device_processing_key", lambda: policy._town_device_processing_key(snapshot))
        if device_processing is not None:
            return device_processing
    if not mining_holds_identification:

        # A Home-held identification source is upstream of the equipment
        # candidate that requested it. Bind that source from the completed
        # Home address catalog before optimization gets another chance to
        # reject the still-incomplete equipment catalog.
        policy._queue_home_identification_source(snapshot)
        # The identification-withdrawal NeedSpec is only a routing claim;
        # bind its exact catalogue signature to the Home executor before
        # town-plan projection is allowed to approach Home.
        policy._bind_catalogued_home_identification_withdrawal(snapshot)

    mark_heavy_curse = policy._town_producer_entry("_heavy_curse_inscription_key", lambda: policy._heavy_curse_inscription_key(snapshot))
    if mark_heavy_curse is not None:
        return mark_heavy_curse

    remove_curse = policy._town_producer_entry("_town_remove_curse_key", lambda: policy._town_remove_curse_key(snapshot))
    if remove_curse is not None:
        return remove_curse
    policy._bind_home_star_remove_curse_withdrawal(snapshot)

    enchant_launcher = policy._town_producer_entry("_town_enchant_launcher_key", lambda: policy._town_enchant_launcher_key(snapshot))
    if enchant_launcher is not None:
        return enchant_launcher

    suppress_random_teleport = policy._town_producer_entry("_town_random_teleport_suppression_key", lambda: policy._town_random_teleport_suppression_key(
        snapshot
    ))
    if suppress_random_teleport is not None:
        return suppress_random_teleport

    # Equipment changes have one owner: after Home identification and the
    # complete-page scan, execute the globally optimized loadout transaction.
    # Legacy per-item weapon trials and jewellery upgrades must not race this
    # plan or repeatedly withdraw and re-deposit candidates.
    equipment_transaction = policy._town_producer_entry("_equipment_transaction_town_key#2", lambda: policy._equipment_transaction_town_key(snapshot))
    if equipment_transaction is not None:
        return equipment_transaction

    # USER DECISION 2026-10-02 「帰還が進んでいる間だけ止める」: the
    # emergency return shuts ordinary loot out only while it progresses
    # (recall read and waiting, or walking to the exit); on a floor it
    # cannot leave, the bot picks up even with the flag set.
    emergency_return_progressing = policy._emergency_return_progressing(snapshot)
    if (
        not emergency_return_progressing
        and not policy._required_supply_suppresses_normal_loot(snapshot)
    ):
        loot = policy._town_producer_entry("_normal_loot_key#2", lambda: policy._normal_loot_key(snapshot, strategic_hostiles))
        if loot is not None:
            return loot
    elif emergency_return_progressing:
        # S2b.1b, for the town hold: the progressing emergency return shuts
        # ordinary loot out, so the committed loot walk (often suspended
        # by the emergency that set the flag) ends here.
        policy._release_claim_goal(
            "loot-suppressed:emergency-return",
            policy._loot_target,
            owners=CLAIM_LOOT_OWNERS,
        )

    # Keep a light lit before any town errand can approach a store or the
    # dungeon entrance: native town travel is rejected at night unless a
    # light is equipped. Skip equipment changes while confused, and while
    if not player.confused:
        restore_lantern = policy._empty_lantern_to_restore(snapshot)
        if restore_lantern is not None:
            policy.last_reason = "restore-lantern"
            return policy._equipment_wield(
                snapshot, "light-loadout", restore_lantern, "light"
            )
        wield = policy._light_to_wield(snapshot)
        if wield is not None:
            policy.last_reason = "wield-light"
            key = policy._equipment_wield(
                snapshot, "light-loadout", wield, "light"
            )
            if key is not None:
                policy._offer_execution(
                    key, producer="equipment-txn",
                    work_id="equipment:wield-light",
                    next_step="equipment.wield-light",
                    arguments=(policy._item_signature(wield),),
                    expected_effect="light-equipped",
                )
            else:
                policy._offer_execution_no_step(
                    producer="equipment-txn",
                    work_id="equipment:wield-light",
                    cause="light-wield-unavailable",
                )
            return key
        refill = policy._light_refill_item(snapshot)
        if refill is not None:
            policy.last_reason = "refill-light"
            return reserved_item_command(policy, snapshot, "refill", refill)
        departure_refill = policy._unknown_lantern_departure_refill_item(snapshot)
        if departure_refill is not None:
            policy._unknown_lantern_departure_refilled = True
            policy.last_reason = "refill-light"
            return reserved_item_command(policy, snapshot, "refill", departure_refill)

    # _observe schedules the town circuit breaker before _decide runs.  It
    # must preempt the shopping approach below: that router otherwise
    # returns on every decision and starves _town_special_key forever,
    # leaving the breaker pending while the character repeats the same
    # unaffordable errand.
    if policy._town_restock_suppressed:
        supplier = policy._departure_supplier_counterfactual(snapshot)
        if supplier is not None:
            # E6 routes suppression release through the same I5
            # counterfactual as terminal selection.  The arbiter's
            # owner/vector recurrence budget, not this latch, bounds a
            # supplier that returns without durable progress.
            policy._town_suppression_claim_stores.add(supplier)
            policy._town_restock_suppressed = False
            policy._town_blocked_reason = None
            policy._retire_town_errand_plan_for_rebuild()
    if policy._town_cycle_pending:
        town_cycle_repair = policy._town_producer_entry("_town_special_key", lambda: policy._town_special_key(snapshot), family="departure")
        if town_cycle_repair is not None:
            return town_cycle_repair

    # 2a. Before diving: while in town with money and no lantern, walk to the
    #     General Store to buy one. A brass lantern lights radius 2 vs a torch's
    #     radius 1 — seeing the dark is what the Half-Troll lacked when it died.
    if snapshot.in_town:
        policy._end_fundraising_set_at_gold_target(snapshot)
        policy._town_order_select_required_supply(snapshot)
        policy._bind_home_star_remove_curse_withdrawal(snapshot)
        # The departure seam (_town_special_key) releases a stale Home
        # candidate latch before it evaluates departure; _observe re-derives
        # that latch on every in-town board (a Home identify scroll alone
        # sets it).  When that latch is the only failing departure leaf,
        # the release flips the verdict the claim registry reads (optional
        # claims register only when departure is ready).  Release it here
        # in exactly that case, so the registry below and the departure
        # seam read one departure verdict in one decision (live 2026-10-02
        # 17:00:51: not ready here hid the optional launcher-enchant claim
        # from this router, ready there kept it active and deferred the
        # departure verdict -> no owner).  With another leaf failing both
        # seams already read "not ready"; the latch is left as it was.
        if policy._home_candidate_waiting and [
            name for name, ready
            in policy._town_departure_conjuncts(snapshot).items()
            if not ready
        ] == ["home_candidate_resolved"]:
            policy._release_stale_home_candidate_waiting(snapshot)
        claims_active = policy._town_claims_active(snapshot)
        if not claims_active:
            # The former router performed terminal bookkeeping before it
            # returned None. Preserve those latch releases and pending-disposal
            # handoffs without letting the errand plan own this departure turn.
            policy._town_terminal_transitions(snapshot)
            # A released identification wait hid every later need from
            # the registry (_town_need_candidates returns at a live
            # identification need): the needs it frees are this board's
            # claims, not the town end's (n1-a life-468 07:26).
            claims_active = policy._town_claims_active(snapshot)
        if claims_active:
            step = policy._shopping_approach_step(
                snapshot, router_plan_stop=True
            )
            if step is not None:
                holder = town_standing_claim(policy)
                scan_wait = bool(
                    policy._shopping_approach_store_type == STORE_HOME
                    and holder is not None and holder.is_open
                    and holder.owner.value == "home-scan"
                    and holder.execution is not None
                    and holder.execution.continuation == "home.knowledge.observe"
                    and policy._home_knowledge_scan_inflight
                    and not policy._home_knowledge_current
                    and (policy._home_pending_item is not None or policy._home_pending_batch
                         or (policy._shopping_approach_goal == snapshot.player.position
                             and policy._home_visit.request is not None
                             and policy._home_visit.request.kind == HomeVisitKind.SCAN))
                    and policy._home_atomic_withdraw_pending is None
                    and policy._home_atomic_deposit_pending is None
                    and not policy._town_space_deposit_actionable(snapshot)
                    and policy._equipment_transaction_session is None
                )
                # The posted catalogue/take prerequisite answers at this
                # router rung, before its own redundant Home entry.
                if scan_wait:
                    return policy._town_producer_entry(
                        "_home_full_knowledge_key",
                        lambda: policy._home_full_knowledge_key(snapshot),
                        family="home-scan")
                policy.last_reason = "shop:approach"
                terminal = rung_terminal(policy, "_shopping_approach_key#2", snapshot)
                refused = (terminal is not None and terminal != NOT_APPLICABLE
                           and not terminal_admission(policy, snapshot, terminal).admitted)
                approach = policy._town_producer_entry("_shopping_approach_key#2", lambda: policy._shopping_approach_key(snapshot, step, "shop:travel"))
                if approach is not None or not refused:
                    return approach

    destroy = policy._town_producer_entry("_town_destroy_key", lambda: policy._town_destroy_key(snapshot), family="equipment-txn")
    if destroy is not None:
        return destroy

    # Exhaust preserving overflow remedies before terminal destruction.
    if (
        snapshot.in_town
        and not physical_adjacent
        and PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS
    ):
        overflow_destroy = policy._town_producer_entry("_town_overflow_destroy_key", lambda: policy._town_overflow_destroy_key(snapshot, try_relief=True))
        if overflow_destroy is not None:
            policy._terminal_pack_space_signature = None
            return overflow_destroy
        if PACK_CAPACITY - len(snapshot.inventory) >= MIN_TERMINAL_FREE_PACK_SLOTS:
            signature = policy._town_pack_space_signature(snapshot)
            if policy._terminal_pack_space_signature != signature:
                policy._terminal_pack_space_signature = signature

    town_special = policy._town_producer_entry(
        "_town_special_key", lambda: policy._town_special_key(snapshot), family="departure")
    if town_special is not None:
        return town_special

    # The posted Home take owns this entrance until the outside inventory
    # observation confirms or clears it.  Survival, combat, town work, and
    # cycle repair above retain priority; this only prevents the generic
    # exploration breakout below from walking off the entrance.
    if policy._home_atomic_withdraw_pending is not None:
        home_entrance = snapshot.grid_at(player.position)
        if (
            snapshot.in_town
            and snapshot.store is None
            and home_entrance is not None
            and home_entrance.store_number == STORE_HOME
        ):
            policy.last_reason = "home:atomic-withdraw-pending-hold"
            return WAIT_KEY

    if (
        snapshot.in_town
        and policy._recall_departure_shortage(snapshot)
        and not policy._recall_shortage_opening_exempt(snapshot)
        and policy._fundraising_mode not in {"prepare", "mine", "scavenge"}
        and not policy._town_cycle_pending
        and policy._town_blocked_reason != "repetition"
    ):
        # Existing shopping, processing, and restock owners above get their
        # normal opportunity. At the ordinary departure boundary, shortage
        # permits only the established fundraising or restock-wait flow.
        if policy._start_fundraising(snapshot):
            fundraising = policy._town_producer_entry("_fundraising_key#2", lambda: policy._fundraising_key(
                snapshot, strategic_hostiles
            ))
            if fundraising is not None:
                return fundraising
        recall_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
        if (
            not all(
                policy._shelf_stop_tried(snapshot, store, "recall")
                for store in recall_stores
            )
            and getattr(policy._town_map, "store_position", None) is not None
        ):
            return policy._town_producer_entry("_released_restock_store_key", lambda: policy._released_restock_store_key(
                snapshot, recall_stores
            ))
        return policy._town_producer_entry("_recall_restock_key", lambda: policy._recall_restock_key(snapshot), family="departure")
    return PASS
