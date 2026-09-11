from __future__ import annotations

from hengbot.policy_constants import DESTRUCTION_GATE_LABEL, SPEED_GATE_LABEL, SPEED_GATE_MINIMUM, required_depth_gates, EMERGENCY_ESCAPE_REASONS, EMPTY_DIVE_LIMIT, ExplorationPathOutcome, HOME_PLAN_OWNED_PROCESSING_REASONS, NO_DEPTH_PROGRESS_DIVE_LIMIT, OVEREXTEND_EMERGENCY_MIN, OVEREXTEND_LOOT_MAX, PICKUP_REASONS, STORE_RETRY_TURNS, STUCK_FAMILY_REASONS, STUCK_NEUTRAL_REASONS, TOWN_CYCLE_IGNORED_REASONS, TOWN_NO_PROGRESS_LIMIT, TOWN_WANDER_LIMIT, TOWN_WANDER_REASONS
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, STORE_HOME, Snapshot
from hengbot.policy_constants import FIXED_QUEST_ALLOWLIST, QUEST_STATUS_FINISHED, QUEST_STATUS_REWARDED
from hengbot.quest_strategies import StrategyProfile
from hengbot.policy_types import TownVisitLedger
from hengbot.warrior_optimization import character_intrinsic_flags
from hengbot.equipment_optimizer import equipment_identity

class ObservationMixin:
    def observe_character_snapshot(self, character) -> None:
        """Consume a `C` character snapshot (naked capture or periodic dump).

        Always refreshes the mutation signature from ``mutations`` — the
        pre-existing periodic status dump (cli DUMP_INTERVAL_SECONDS) makes
        this the autonomous, observation-bounded post-calibration trigger for
        the mutation invalidation.  While the calibration capture step's
        naked dump is in flight, the ``characteristics`` table is additionally
        recorded as the worn-independent intrinsic TR flag set.
        """
        if not isinstance(character, dict):
            return
        mutations = character.get("mutations")
        if mutations is not None:
            try:
                self._mutation_signature = tuple(
                    sorted(int(value) for value in mutations)
                )
            except (TypeError, ValueError):
                pass
        if (
            self._calibration_naked_dump_inflight
            and self._calibration_phase == "capture"
        ):
            self._calibration_naked_flags = character_intrinsic_flags(
                character.get("characteristics")
            )
            self._calibration_naked_dump_inflight = False

    def _observe(
        self, snapshot: Snapshot, *, observation: Snapshot | None = None
    ) -> None:
        # The threat memo exists only for repeat lookups within ONE decision
        # (gates + telemetry); a new decision must never see the old entries.
        self._threat_prediction_memo.clear()
        self._observe_remove_curse(snapshot)
        self._observe_launcher_enchant(snapshot)
        self._observe_departure_prices(snapshot)
        previous_floor = self._floor_key
        if self._breeder_fled_floor is not None and (
            snapshot.in_town
            or snapshot.floor_key[0] != self._breeder_fled_floor[0]
        ):
            self._breeder_fled_floor = None
        if self._emergency_recall_sanctioned:
            if previous_floor is not None and previous_floor != snapshot.floor_key:
                self._emergency_recall_sanctioned = False
            elif (
                self._town_blocked_reason != "repetition"
                and not snapshot.player.recalling
            ):
                self._emergency_recall_sanctioned = False
        if snapshot.in_town and not self._town_was_in_town:
            self._town_visit_ledger = TownVisitLedger()
            if (
                getattr(self, "_home_visit", None) is not None
                and not self._home_visit.active
            ):
                self._home_visit.reset_epoch()
            self._unknown_lantern_departure_refilled = False
            self._abandoned_quest_carry_requirements.clear()
            self._calibration_aborts_this_visit = 0
            self._calibration_blocked_this_visit = False
            self._calibration_last_abort = None
        self._town_was_in_town = snapshot.in_town
        if previous_floor is None and snapshot.in_town and snapshot.player.recalling:
            self._startup_town_recall = True
        current_town_id = (
            self._effective_town_id(snapshot) if snapshot.in_town else None
        )
        town_changed = (
            current_town_id is not None
            and self._observed_town_id is not None
            and current_town_id != self._observed_town_id
        )
        if town_changed:
            self._town_supplier_stock_observations.clear()
        self._observed_town_id = current_town_id
        self._observe_stair_command(snapshot, observation=observation)
        if not snapshot.in_town and snapshot.player.recalling:
            self._saw_dungeon_recall = True
            self._emergency_return_active = False
        if (
            snapshot.in_town
            and previous_floor is not None
            and previous_floor[1] > 0
            and previous_floor != snapshot.floor_key
            and self._saw_dungeon_recall
        ):
            self._home_disposal_pass = self._home_disposal.note_dungeon_recall()
            self._home_disposal_seen_pages.clear()
            self._home_disposal_candidates.clear()
            self._saw_dungeon_recall = False
            self._town_errand_plan = None
            self._town_store_attempted.pop(STORE_HOME, None)
        if snapshot.in_town:
            self._home_disposal.reload_decisions()
        if previous_floor is not None and previous_floor != snapshot.floor_key:
            self._quest_strategy_visible_targets.clear()
            self._quest_strategy_cleared_targets.clear()
            self._quest_strategy_pending_recovery.clear()
            self._quest_strategy_recovery_claims.clear()
            self._quest_strategy_recovery_pickup_prepared = None
            self._quest_strategy_recovery_pickup_prepared_key = None
            self._quest_strategy_recovery_pickup_posted = None
            self._quest_strategy_initial_hold_turns.clear()
            self._quest_strategy_surveyed_placements.clear()
            self._quest_strategy_sweep_rounds.clear()
            self._quest_strategy_opening_phase.clear()
            self._quest_strategy_hold_positions.clear()
            self._quest_strategy_post_wave_light_attempted.clear()
            if (
                self._quest_regen_phase == "ascend"
                and self._quest_regen_id is not None
                and snapshot.floor_key[0] == previous_floor[0]
                and snapshot.floor_key[1] == previous_floor[1] - 1
            ):
                self._quest_regen_phase = "descend"
            self._fruitless_disengage_floor = None
            self._fruitless_disengage_decisions = 0
            if snapshot.floor_key[2] in FIXED_QUEST_ALLOWLIST:
                self._fixed_quest_speed_floor = snapshot.floor_key
                self._fixed_quest_speed_attempted = False
            else:
                self._fixed_quest_speed_floor = None
                self._fixed_quest_speed_attempted = False
            # Surface-travel bookkeeping is per-visit: positions repeat across
            # town visits (static map), so a stale no-progress latch from the
            # previous visit would suppress native travel forever.
            self._town_travel_state = None
            self._town_travel_fallback = None
            self._town_hunt_target = None
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
            self._town_cycle_pending = False
            self._town_cycle_breaks = 0
            self._town_restock_suppressed = False
            self._town_suppression_claim_stores.clear()
            self._town_errand_plan = None
            self._terminal_pack_space_signature = None
            self._town_restock_wait_until = None
            self._town_restock_waiting_for = ()
            self._town_restock_rechecked.clear()
            self._town_restock_waited_turns = 0
            self._town_restock_last_wait_turn = None
        elif town_changed:
            # Inn travel keeps the surface floor key at (0, 0, 0), but it is a
            # new town visit with different stores and routes.  Carrying the
            # previous town's cycle debt made the first ordinary shopping pass
            # in the destination look like a second repetition offense.
            self._town_travel_state = None
            self._town_travel_fallback = None
            self._town_hunt_target = None
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
            self._town_wander_streak = 0
            self._town_cycle_pending = False
            self._town_cycle_breaks = 0
            self._town_blocked_reason = None
            self._town_restock_suppressed = False
            self._town_suppression_claim_stores.clear()
            self._town_errand_plan = None
            self._terminal_pack_space_signature = None
            self._town_restock_wait_until = None
            self._town_restock_waiting_for = ()
            self._town_restock_rechecked.clear()
            self._town_restock_waited_turns = 0
            self._town_restock_last_wait_turn = None
            self._town_store_attempted.clear()
            self._shopping_stuck = False
            self._shop_approach_stuck_count = 0
            self._shop_approach_stuck_store = None
            self._shop_approach_previous_origin = None
            self._staged_shop_approach = None
            self._pending_shop_approach = None
            self._shopping_abandoned = False
        # Count consecutive "stuck" turns on a dungeon floor — searching, probing,
        # breaking out or wandering, but never actually exploring a frontier or
        # fighting (reset by any such progress, or by reaching town) — so a
        # walled-off level triggers a Word-of-Recall escape instead of trapping
        # the bot forever.
        if not snapshot.in_town and self.last_reason in STUCK_FAMILY_REASONS:
            self._stuck_escape_streak += 1
        elif self.last_reason in STUCK_NEUTRAL_REASONS and not snapshot.in_town:
            pass  # upkeep between searches — hold the streak, do not reset it
        else:
            self._stuck_escape_streak = 0
        # Town circuit breaker (see TOWN_WANDER_LIMIT): count the mirror-image
        # streak for town. Any other reason, or leaving town, resets it — the
        # latch below only fires on a genuinely unbroken run of dead-end turns.
        if snapshot.in_town and self.last_reason in TOWN_WANDER_REASONS:
            self._town_wander_streak += 1
        else:
            self._town_wander_streak = 0
        # Generic town-repetition detector (see TOWN_CYCLE_WINDOW): record the
        # previous decision's signature; any real progress (gold, pack or
        # equipment change) resets the window.
        if snapshot.in_town:
            plan = self._town_errand_plan
            marker = (
                snapshot.player.gold,
                len(snapshot.inventory),
                len(snapshot.equipment),
                self._identification_need,
                self._equipment_catalog.home_scan_complete,
                tuple(plan.completed_this_visit) if plan is not None else (),
                tuple(plan.blocked_this_visit) if plan is not None else (),
            )
            if marker != self._town_progress_marker:
                had_marker = self._town_progress_marker is not None
                self._town_progress_marker = marker
                self._town_signature_history.clear()
                self._town_no_progress_count = 0
                self._town_visit_ledger.passes_since_progress = 0
                if had_marker:
                    # Completing an identification/home-scan/errand stage is
                    # real workflow progress even when gold and pack counts do
                    # not change. Do not carry an earlier entrance-wait offense
                    # across that boundary and mislabel the next store visit as
                    # a second town cycle.
                    self._town_cycle_pending = False
                    self._town_cycle_breaks = 0
            if (
                self.last_reason
                and not any(
                    self.last_reason == ignored
                    or self.last_reason.startswith(f"{ignored}:")
                    for ignored in TOWN_CYCLE_IGNORED_REASONS
                )
                and self.last_reason not in HOME_PLAN_OWNED_PROCESSING_REASONS
            ):
                position = snapshot.player.position
                self._town_signature_history.append(
                    (self.last_reason, position.y, position.x)
                )
                self._town_no_progress_count += 1
                self._town_visit_ledger.passes_since_progress += 1
                if (
                    self._town_cycle_detected()
                    or self._town_no_progress_count >= TOWN_NO_PROGRESS_LIMIT
                ):
                    self._town_cycle_pending = True
                    self._town_signature_history.clear()
                    self._town_no_progress_count = 0
        else:
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
        if (
            snapshot.in_town
            and self._town_wander_streak >= TOWN_WANDER_LIMIT
            and not self._town_cycle_pending
        ):
            # A long but spatially varied wander will not satisfy the generic
            # repeated-signature detector.  Feed it into the same bounded
            # repair path anyway: the first offense suppresses errands and
            # forces departure, while a second offense stops visibly.
            self._town_cycle_pending = True
        # Track how long we have been stuck in town wielding only a pickaxe: the pre-recall
        # weapon check blocks a dive until we re-arm, and this backstop lets us dive anyway
        # if we simply own no combat weapon. Only in-town decisions count — a digger worn
        # for legitimate mining (in the dungeon) must not trip it.
        if snapshot.in_town and self._equipped_digging_tool(snapshot) is not None:
            self._weapon_block_streak += 1
        else:
            self._weapon_block_streak = 0
        if not snapshot.in_town:
            # Away from town, clear the "Home is full" latch so the next visit
            # re-checks (the bot may have withdrawn items or a later Home differs).
            self._home_deposit_abandoned = False
            self._home_rejected_deposits.clear()
            self._device_identify_watch = None
            self._device_identify_fail_streak = 0
        if snapshot.in_town:
            self._unidentifiable_sigs.clear()
            self._identify_watch = None
            self._identify_fail_streak = 0
            # A store latched into _town_store_attempted (nothing to buy/sell on
            # that visit) would otherwise stay skipped for the rest of an
            # abnormally long town stay, even though real time (game turns) has
            # passed and it may have restocked. Expire each latch on its own
            # schedule so supplies bought there are periodically re-checked
            # instead of draining unnoticed forever (see STORE_RETRY_TURNS).
            expired_stores = [
                store_type
                for store_type, latched_at in self._town_store_attempted.items()
                if snapshot.turn - latched_at >= STORE_RETRY_TURNS
            ]
            for store_type in expired_stores:
                del self._town_store_attempted[store_type]
                if store_type == STORE_HOME:
                    self._home_latch_active = None
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.level >= 2
        ):
            # A process restart loses the in-memory deepest-floor watermark.
            # A developed strict-mode character must not regress to the depth-1
            # shopping plan and enter without the depth-2 lantern/escape kit.
            self._deepest_level = max(self._deepest_level, 1)
        # recall_depth is the save-backed deepest level reached in the recall
        # target dungeon (where Word of Recall lands). Unlike the in-memory
        # watermark it survives a restart, so seed from it — otherwise a resumed
        # bot forgets it has been to 5F+ and walks in from the entrance instead of
        # recalling, re-descending the very floors recall exists to skip.
        self._deepest_level = max(self._deepest_level, snapshot.recall_depth)
        if snapshot.dungeon_level > 0:
            self._deepest_level = max(self._deepest_level, snapshot.dungeon_level)

        if snapshot.angband_recall_unlocked:
            self._target_dungeon_id = DUNGEON_ANGBAND
            self._rumor_unlock_pending = False
        elif (
            (quest_14 := snapshot.quests.get(14)) is not None
            and quest_14.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}
        ):
            self._rumor_unlock_pending = True
        if (
            self._town_travel_rumor_pending is not None
            and snapshot.visited_town_ids is not None
            and self._town_travel_rumor_pending in snapshot.visited_town_ids
        ):
            self._town_travel_rumor_pending = None

        # --- Over-extension: recall into a level-appropriate dungeon when the main
        # one is too deep to loot. On each dive of the recall target, track both the
        # loot grabbed and the emergency escapes forced; a dive that came back with
        # almost nothing AND had to bail out repeatedly (see OVEREXTEND_* limits) is
        # judged over-extended. A run of them means the dungeon is beyond the
        # character's ability, so switch to a shallower already-unlocked dungeon
        # whose landing depth satisfies the required abilities. ---
        prev_dungeon = previous_floor[0] if previous_floor else 0
        if not snapshot.in_town:
            if prev_dungeon == 0:  # descended from town: a fresh dive begins
                self._dive_dungeon = snapshot.floor_key[0]
                self._dive_start_recall_depth = snapshot.dungeon_recall_depths.get(
                    self._dive_dungeon,
                    snapshot.recall_depth
                    if snapshot.recall_dungeon_id == self._dive_dungeon
                    else snapshot.dungeon_level,
                )
                self._dive_loot = 0
                self._dive_emergencies = 0
            if self.last_reason in PICKUP_REASONS:
                self._dive_loot += 1
            elif self.last_reason in EMERGENCY_ESCAPE_REASONS:
                self._dive_emergencies += 1
        elif prev_dungeon != 0 and self._dive_dungeon is not None:
            # A dive just ended. Judge only normal dives of the recall target —
            # fundraising mining of the Yeek Cave is a separate mode, not a dive.
            if (
                self._dive_dungeon == self._target_dungeon_id
                and self._fundraising_mode not in {"prepare", "mine", "scavenge"}
            ):
                start_depth = self._dive_start_recall_depth or 0
                end_depth = snapshot.dungeon_recall_depths.get(
                    self._dive_dungeon,
                    snapshot.recall_depth
                    if snapshot.recall_dungeon_id == self._dive_dungeon
                    else start_depth,
                )
                dungeon_info = self._dungeon_knowledge.get(self._dive_dungeon)
                can_descend_further = (
                    dungeon_info is not None
                    and dungeon_info.max_depth > 0
                    and start_depth < dungeon_info.max_depth
                )
                if end_depth > start_depth:
                    self._no_depth_progress_dives = 0
                elif can_descend_further:
                    self._no_depth_progress_dives += 1
                if self._dive_loot > OVEREXTEND_LOOT_MAX:
                    # A real haul proves the character can handle this depth.
                    self._target_empty_dives = 0
                elif self._dive_emergencies >= OVEREXTEND_EMERGENCY_MIN:
                    # Unproductive AND forced to bail out repeatedly = over-extended.
                    self._target_empty_dives += 1
                elif self._last_return_trigger == "guardian-kit-insufficient":
                    # A guardian we cannot yet beat recalls us straight back with
                    # no real dive. Uncounted, it flip-flops town<->guardian
                    # forever, burning ~2 recall scrolls a round trip until the
                    # character is stranded at depth with zero escape scrolls
                    # (live: Labyrinth, recall 9 -> 0). Count it as over-extension
                    # so the approved empty-dive valve releases the conquest latch
                    # and switches to a productive dungeon; the latch may
                    # re-select the guardian later once the kit can beat it.
                    self._target_empty_dives += 1
                # else: unproductive but no real danger (found nothing, or a single
                # scare) — HOLD the streak. Weak evidence must not ADVANCE the count,
                # but a lone quiet dive between genuinely bad ones must not RESET it
                # to zero either, or the switch could never accumulate. Only a
                # profitable dive clears the suspicion.
            self._dive_dungeon = None
            self._dive_start_recall_depth = None
        conquered_now = set(snapshot.conquered_dungeon_ids)
        first_observation = previous_floor is None
        if first_observation:
            # A resumed process sees historical conquests as its baseline.
            self._conquered_seen |= conquered_now
            if snapshot.yeek_cave_conquered:
                self._yeek_conquest_processed = True
        newly_conquered = conquered_now - self._conquered_seen
        if newly_conquered:
            # A guardian clear ends the current over-extension diversion. Let
            # ordinary target selection choose the next conquest/default dive.
            self._alternate_dungeon = None
            self._last_overextended_depth = 0
        if snapshot.in_town and self._target_empty_dives >= EMPTY_DIVE_LIMIT:
            self._last_overextended_depth = snapshot.recall_depth
            alt = self._pick_alternate_dungeon(snapshot)
            if alt is not None:
                self._alternate_dungeon = alt
                # The safety valve must demote even a latched conquest target.
                # It may be selected again after the existing alternate period,
                # but must not immediately override the alternate below.
                self._conquest_committed = None
            self._target_empty_dives = 0
        if (
            snapshot.in_town
            and self._alternate_dungeon is None
            and self._no_depth_progress_dives >= NO_DEPTH_PROGRESS_DIVE_LIMIT
        ):
            # Five complete expeditions without increasing the saved Recall
            # depth is a lack of strategic progress even when they recovered
            # miscellaneous loot.  Farm the deepest already-unlocked safe
            # alternative below the blocked landing depth instead of repeating
            # the same Angband floor indefinitely.
            blocked_depth = max(1, snapshot.recall_depth)
            self._last_overextended_depth = blocked_depth
            alt = self._pick_alternate_dungeon(
                snapshot,
                max_entry_depth=max(1, blocked_depth - 1),
                prefer_deepest=True,
            )
            if alt is not None:
                self._alternate_dungeon = alt
                self._conquest_committed = None
            self._no_depth_progress_dives = 0
        # A switched target overrides the ordinary selection until its lifecycle
        # ends through conquest, loadout-fallback completion, or replacement.
        if self._alternate_dungeon is not None:
            if self._alternate_dungeon in snapshot.entered_dungeon_ids:
                self._target_dungeon_id = self._alternate_dungeon

        # HIGHEST PRIORITY target: clear an unconquered dungeon whose bottom is within
        # our resistance limit, for the final guardian's gear. It normally overrides
        # Angband, but the over-extension safety valve temporarily demotes it while
        # the existing alternate lifecycle is active.
        conquest = (
            self._conquest_target(snapshot)
            if self._alternate_dungeon is None
            else None
        )
        if conquest is not None:
            self._target_dungeon_id = conquest
            # Fundraising is only superseded when the conquest expedition can
            # actually leave town.  In particular, poverty plus a supply gap is
            # still a fundraising problem even when the guardian fight itself is
            # viable.  Remember successful clears by target so observe cannot
            # repeatedly undo a mode re-established by decide.
            if (
                snapshot.in_town
                and conquest != self._fundraising_cleared_for_conquest
                and self._conquest_departure_ready(snapshot)
            ):
                self._fundraising_mode = None
                self._planned_mining_runs = None
                self._fundraising_cleared_for_conquest = conquest

        # Fresh conquest: the char just killed a dungeon's final guardian while
        # standing in it. Latch it so the loot phase grabs the drop before recalling
        # out (the user flagged the Yeek Cave reward being left behind). Cleared on
        # reaching town.
        current_dungeon = snapshot.floor_key[0]
        if (
            not snapshot.in_town
            and current_dungeon != DUNGEON_YEEK_CAVE
            and current_dungeon in newly_conquered
        ):
            self._victory_loot_dungeon = current_dungeon
        self._conquered_seen |= conquered_now
        if snapshot.in_town:
            self._victory_loot_dungeon = None

        self._track_idle_items(snapshot, previous_floor)

        if not snapshot.in_town:
            self._startup_town_recall = False
            # Left town for the dungeon: re-arm the pre-dive character dump so the
            # next town departure writes a fresh sheet, and clear the shopping-stuck
            # latch so a fresh town visit re-tries the stores.
            self._char_dump_done_this_visit = False
            self._shopping_stuck = False
            self._shop_approach_stuck_count = 0
            self._shop_approach_stuck_store = None
            self._shop_approach_previous_origin = None
            self._staged_shop_approach = None
            self._pending_shop_approach = None
            self._home_processing_seen_pages.clear()
            self._home_digger_seen_pages.clear()
            self._home_pending_batch.clear()
            getattr(self, "_home_pending_quantities", {}).clear()
            self._home_procurement_batch_active = False
            self._home_batch_review_items.clear()
            self._home_active_from_batch = False
            self._home_atomic_withdraw_pending = None
            self._home_identify_staff_sale_pending = False
            self._home_identify_staff_sold_this_magic_visit = False
            self._home_digger_withdraw_pending = False
            self._equipment_transaction_failed_items.clear()
            self._equipment_retired_worn_item_ids = frozenset()
            getattr(self, "_priority_body_rearm_attempted_ids", set()).clear()
            self._equipment_quarantine_second_chance_ids.clear()
            self._equipment_quarantine_burned_ids.clear()

        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and DUNGEON_YEEK_CAVE in newly_conquered
            and self._fundraising_mode is None
            and not self._yeek_conquest_processed
        ):
            self._yeek_victory_loot = True

        returned_from_fundraising = (
            snapshot.in_town
            and previous_floor is not None
            and previous_floor[0] == DUNGEON_YEEK_CAVE
            and previous_floor[1] == 1
            and self._fundraising_mode in {"mine", "scavenge"}
        )
        if returned_from_fundraising:
            if self._fundraising_mode == "mine":
                self._mining_runs_completed += 1
            else:
                self._sell_scavenged_consumables = True
            self._mining_scroll_used_floor = None
            self._mining_detection_centers.clear()
            self._town_store_attempted.clear()
            # A completed mining trip is the user-approved retry boundary for
            # postponed Home identification: gear parked in _processed_home_items
            # is only *temporarily* skipped, so re-arm it and force the equipment
            # optimizer to re-plan against a fresh Home scan. The deferred
            # Home/device sets are re-armed by the fresh-town reset just below (it
            # always fires on this dungeon->town floor change); _processed_home_
            # items has no other clear site, so it is cleared here. It is
            # intentionally NOT cleared in the generic fresh-town reset: a quick
            # restock stop between unrelated dives must not force re-withdrawing
            # and re-examining every stored item, and the mining trip is the only
            # boundary the user approved for the identification retry. The
            # identification fundraising driver guarantees this boundary arrives
            # whenever a Home-identification deadlock is what blocks departure.
            self._processed_home_items.clear()
            self._equipment_optimization_signature = None
            self._equipment_optimization_preparation = None

        if snapshot.in_town:
            self._returning_to_town = False
            if snapshot.floor_key != self._floor_key:
                # A fresh town visit retries the store: an earlier give-up (e.g.
                # an unaffordable lantern) must not block buying the rations this
                # return trip is for. The in-store bail-outs re-bound any retry.
                # Destruction failures are likewise scoped to one expedition;
                # preserving the watch during the visit lets unchanged attempts
                # reach their retry limit instead of being resent forever.
                self._undestroyable_sigs.clear()
                self._destroy_watch = None
                self._destroy_fail_streak = 0
                self._shopping_abandoned = False
                self._town_store_attempted.clear()
                self._digger_home_withdraw_failures = 0
                self._digger_fallback_bought_this_visit = False
                self._home_procurement_withdraw_failure = None
                self._unsellable_items.clear()
                self._store_sale_refused.clear()
                self._store_sell_attempt = None
                self._batch_sell_pending = None
                self._home_candidate_waiting = True
                self._deferred_home_items.clear()
                self._retried_deferred_home_items.clear()
                getattr(self, "_deferred_home_item_sites", {}).clear()
                getattr(self, "_home_pending_quantities", {}).clear()
                self._home_procurement_batch_active = False
                self._town_unidentifiable_carried_sigs.clear()
                self._town_supplier_stock_observations.clear()
                self._deferred_device_items.clear()
                self._retried_home_identification_items.clear()

            if snapshot.yeek_cave_conquered and self._yeek_victory_loot:
                self._yeek_victory_loot = False
                self._yeek_conquest_processed = True

        if snapshot.floor_key != self._floor_key:
            # Bind before clearing per-floor policy state: on a real transition
            # the ledger still references the old counters and must flush them
            # before it creates the fresh current-floor state.
            self._exploration_ledger.bind(snapshot)
            self._emergency_return_active = False
            self._q2_reconnect_recovery_floor = (
                snapshot.floor_key
                if previous_floor is None and snapshot.floor_key[2] == 2
                else None
            )
            self._equipment_optimization_timed_out_this_visit = False
            self._pending_recall_dungeon_id = None
            self._town_recall_issue_watch = None
            self._town_visit_purchases.clear()
            self._town_visit_sale_signatures.clear()
            self.town_visit_report = None
            self._quest_light_attempted.clear()
            self._q2_phase_light_attempted.clear()
            self._q2_phase_visited_goals.clear()
            self._q2_phase_route_targets.clear()
            self._q2_phase_last_move = None
            self._q2_phase_step_failures.clear()
            self._q2_phase_blocked_steps.clear()
            self._q2_speed_attempted.clear()
            self._q2_surveyed_placements.clear()
            self._q2_residual_surveyed_races.clear()
            self._q2_final_patrol_visited.clear()
            self._q2_final_patrol_target = None
            self._q2_breeder_last_seen = None
            self._q2_breeder_last_seen_floor = None
            self._q2_cleared_races.clear()
            self._q2_breach_attempts = 0
            self._q2_breach_complete = False
            self._q2_blue_recovery_complete = False
            self._q2_blue_recovery_perceived.clear()
            self._launcher_enchant_attempted.clear()
            self._launcher_enchant_watch = None
            self._visit_counts.clear()
            self._recent.clear()
            self._osc_positions.clear()
            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            self._pending_one_step_explore = None
            self._one_step_explore_failures.clear()
            self._one_step_explore_signatures.clear()
            self._unenterable_explore_goals.clear()
            self._window_edge_goals.clear()
            self._window_edge_fallback_pending = False
            self._engagement_avoid_cells.clear()
            self._engagement_owned_avoid_cells.clear()
            self._warning_refused_cells.clear()
            self._warning_step_pending = None
            self._probe_counts.clear()
            self._dark_goal_counts.clear()
            self._clear_dark_route()
            self._floor_trap_disarm_attempts.clear()
            self._door_attempts.clear()
            self._blocked_doors.clear()
            self._blocked_unknown.clear()
            self._dig_attempts.clear()
            self._blocked_rubble.clear()
            self._search_counts.clear()
            self._wall_search_counts.clear()
            self._visit_counts = self._exploration_ledger.visit_counts
            self._probed_frontiers = self._exploration_ledger.probed_frontiers
            self._search_counts = self._exploration_ledger.search_counts
            self._wall_search_counts = self._exploration_ledger.wall_search_counts
            self._blocked_unknown = self._exploration_ledger.blocked_unknown
            self._fruitless_disengage_marked_high = (
                self._exploration_ledger.marked_high
            )
            self._escape_state.release()
            self._remembered_floor_t.clear()
            self._remembered_door_t.clear()
            self._remembered_rubble_t.clear()
            self._remembered_wall_t.clear()
            self._remembered_known_t.clear()
            self._remembered_marked_t.clear()
            self._remembered_downstairs.clear()
            self._remembered_upstairs.clear()
            self._remembered_entrances.clear()
            self._pending_stair_command = None
            self._stair_rejection_strikes.clear()
            self._unverified_stairs.clear()
            self._known_treasure.clear()
            self._treasure_target = None
            self._mining_mark_bumps.clear()
            self._mining_unmarkable_grids.clear()
            self._mining_detection_centers.clear()
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_navigation_visits.clear()
            self._mining_oscillation_retargets = 0
            self._mining_sweep_done = False
            self._mining_viability_pending_floor = None
            self._mining_sweep_steps = 0
            self._mining_sweep_no_progress = 0
            self._mining_sweep_revealed_grids = 0
            self._mining_sweep_goal = None
            self._mining_sweep_goal_distance = None
            self._mining_sweep_escape_pairs.clear()
            self._mining_swept_dead_targets.clear()
            self._mining_grids_at_sweep_done = 0
            self._mining_dropped_veins.clear()
            self._mining_veins_collected = 0
            self._mining_veins_dropped = 0
            self._mining_target_distance = None
            self._mining_target_revealed_grids = 0
            self._mining_target_collected = 0
            self._chest_position = None
            self._chest_phase_counts = {}
            self._chest_drop_origin = None
            self._chest_collecting = False
            self._chest_preopen_objects = None
            self._processed_chest_positions.clear()
            self._known_loot.clear()
            self._loot_target = None
            self._deferred_loot.clear()
            self._loot_defer_blocker = None
            self._remembered_paralyzers.clear()
            self._pending_loot_pickup = None
            self._multiplier_target = None
            self._multiplier_target_grace = 0
            if (
                self._choke_engagement_plan is not None
                and self._choke_engagement_plan.floor != snapshot.floor_key
            ):
                self._release_choke_plan("floor-change")
            self._clear_unseen_retreat()
            self._breeder_breakthrough_floor = None
            self._breeder_engagement_start_count = None
            self._breeder_engagement_start_turn = None
            self._breeder_kills = 0
            self._breeder_previous_exp = None
            self._breeder_previous_indices.clear()
            # A blocked-town/fundraising reason latches a permanent WAIT (which
            # then trips the loop-detector and stops the bot). Several of those
            # conditions are transient (a shop temporarily out of food, the inn
            # not yet in view, home briefly full); clear the latch on any floor
            # change so a fresh visit re-attempts instead of ending the run.
            self._town_blocked_reason = None
            self._floor_key = snapshot.floor_key
            self._last_position = None
            self._rest_count = 0
            self._last_hp = None  # HP is not comparable across floors
            # R1: navigation progress accounting is per floor visit.
            self._nav_ledger.reset()
            self._nav_stall_count = 0
            self._nav_exhausted = False
            self._nav_escape_steps = 0
            self._nav_known_high = 0
            self._nav_progress_marker = None
            self._oscillation_outcome_marker = None
            self._choke_outcome_floor = snapshot.floor_key
            self._choke_outcome_budgets.clear()
            self._breeder_choke_attempt_ended_floor = None

        if self._descent_block_countdown > 0:
            self._descent_block_countdown -= 1

        # Attribute an HP drop only when the game names a hidden monster's blow.
        hp = snapshot.player.hp
        self._took_damage = self._last_hp is not None and hp < self._last_hp
        self._unseen_attack_evidence = next(
            (
                message
                for message in snapshot.messages
                if self._took_damage and self._is_unseen_attack_message(message)
            ),
            None,
        )
        self._took_curse_damage = self._took_damage and any(
            " drains HP from you!" in message
            or " drains life from you!" in message
            or "あなたの体力を吸収した" in message
            for message in snapshot.messages
        )
        self._took_trap_or_terrain_damage = self._took_damage and any(
            message in {
                "トラップが作動してしまいました！",
                "トラップを作動させてしまった！",
                "You set off a trap!",
                "熱で火傷した！",
                "The heat burns you!",
                "冷気に覆われた！",
                "The cold engulfs you!",
                "電撃を受けた！",
                "The electricity shocks you!",
                "酸が飛び散った！",
                "The acid melts you!",
                "毒気を吸い込んだ！",
                "The gas poisons you!",
                "溺れている！",
                "You are drowning!",
            }
            or "を作動させてしまった！" in message
            or message.startswith("You set off the ")
            or "で火傷した！" in message
            or " burns you!" in message
            or "に凍えた！" in message
            or " frostbites you!" in message
            or "に感電した！" in message
            or " shocks you!" in message
            or "に溶かされた！" in message
            or " melts you!" in message
            or "に毒された！" in message
            or " poisons you!" in message
            for message in snapshot.messages
        )
        self._last_damage_amount = (
            self._last_hp - hp if self._took_damage and self._last_hp is not None else 0
        )
        self._last_hp = hp

        position = snapshot.player.position
        self._observe_one_step_explore(snapshot)
        self._position_changed = (
            self._last_position is not None and position != self._last_position
        )
        if position != self._last_position:
            self._visit_counts[position] += 1
            self._last_position = position
        self._recent.append(position)
        self._settle_shopping_approach(snapshot)

        if self._pending_loot_pickup is not None:
            pickup_floor, pickup_position, pickup_count = self._pending_loot_pickup
            if pickup_floor == snapshot.floor_key:
                pickup_grid = snapshot.grid_at(pickup_position)
                if pickup_grid is not None and pickup_grid.object_count >= pickup_count:
                    self._deferred_loot.add(pickup_position)
                    if self._loot_target == pickup_position:
                        self._loot_target = None
            self._pending_loot_pickup = None

        treasure_before_observation = set(self._known_treasure)
        for grid in snapshot.grids.values():
            if grid.has_gold:
                self._known_treasure.add(grid.position)
            elif (
                grid.position in self._known_treasure
                and position.distance_to(grid.position) <= 1
            ):
                # Gold gone with us standing next to it: we mined/picked it.
                self._known_treasure.discard(grid.position)
                self._mining_dropped_veins.discard(grid.position)
                self._mining_veins_collected += 1
                if self._treasure_target == grid.position:
                    self._treasure_target = None
            # CAVE_UNSAFE means trap detection has not covered this grid.  The
            # bot already traverses such grids during ordinary exploration, so
            # it must not make otherwise reachable floor loot invisible.
            if grid.object_count > 0:
                self._known_loot.add(grid.position)
            elif grid.position in self._known_loot and (
                position.distance_to(grid.position) <= 1
            ):
                self._known_loot.discard(grid.position)
                self._deferred_loot.discard(grid.position)
                if (
                    self._loot_defer_blocker == "navigation-ledger:loot"
                    and not self._deferred_loot
                ):
                    self._loot_defer_blocker = None
                if (
                    self._loot_defer_blocker == "paralyzer-ring"
                    and not (self._deferred_loot & self._paralyzer_avoid_cells)
                ):
                    self._loot_defer_blocker = None
                if self._loot_target == grid.position:
                    self._loot_target = None
        if self._known_treasure - treasure_before_observation:
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_oscillation_retargets = 0

    def _current_pinned_identities(
        self, snapshot: Snapshot
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (item.slot, equipment_identity(item))
                for item in snapshot.equipment
                if item.is_equipment and item.is_cursed
            )
        )

    def _resolve_observed_uncomposable_stop(self, snapshot: Snapshot) -> bool:
        """Advance an observed stop whose one-shot command cannot be composed."""
        store_type = (
            self._shop_observation[0].store_type
            if self._shop_observation is not None
            else self._shopping_approach_store_type
        )
        plan = self._town_errand_plan
        if (
            store_type is None
            or snapshot.store is not None
            or plan is None
            or plan.index >= len(plan.stops)
            or plan.stops[plan.index] != store_type
        ):
            return False
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.store_number != store_type:
            return False
        if store_type == STORE_HOME:
            observed = bool(
                self._equipment_catalog.home_scan_complete
                and self._home_knowledge_current
                and self._home_candidate_waiting
                and self._home_pending_item is None
                and not self._home_pending_batch
                and self._equipment_transaction_session is None
            )
        else:
            observed = bool(
                self._shop_observation is not None
                and self._shop_observation[0].store_type == store_type
            )
        if not observed:
            return False
        if store_type != STORE_HOME and self._wanted_purchase_is_home_first_refused(
            snapshot, store_type
        ):
            # The supplier page was observed, but Home-first arbitration
            # refused to ask the shop for the selected item.  Preserve both
            # the page and plan stop so this pass cannot become durable
            # evidence that the supplier had no actionable stock.
            observation_generation = (
                self._shop_observation[1]
                if self._shop_observation is not None
                else self._decision_sequence
            )
            if observation_generation == self._decision_sequence:
                return True
            plan.current_stop_passes = 0
            plan.index += 1
            self._shop_observation = None
            self._close_store_visit("home-first-yield")
            return False
        plan.blocked_this_visit.append(store_type)
        plan.current_stop_passes = 0
        plan.index += 1
        self._set_town_store_attempted(store_type, snapshot.turn, "observed-operation-uncomposable")
        if store_type == STORE_HOME:
            self._release_blocked_store_latches(store_type)
        else:
            self._town_visit_ledger.nonhome_attempted_without_effect[
                store_type
            ] = self._town_observable_effect_state(snapshot)
            self._shop_observation = None
        self.last_reason = "shop:observed-operation-uncomposable"
        return True

    @staticmethod
    def _strategy_force_for_snapshot(
        snapshot: Snapshot, profile: StrategyProfile
    ) -> dict[str, object]:
        force: dict[str, object] = dict(profile.required_force)
        tiers = force.get("defensive_tiers", ())
        if not isinstance(tiers, list):
            return force
        eligible = [
            tier for tier in tiers
            if isinstance(tier, dict)
            and snapshot.player.ac >= int(tier.get("min_ac", 0))
        ]
        if not eligible:
            return force
        tier = max(eligible, key=lambda item: int(item.get("min_ac", 0)))
        for name in ("min_hp", "heal_potions"):
            if name in tier:
                force[name] = int(tier[name])
        return force

    def _missing_required_abilities(self, snapshot: Snapshot, depth: int) -> frozenset:
        missing = set(required_depth_gates(depth) - snapshot.player.abilities)
        if DESTRUCTION_GATE_LABEL in missing and self._has_destruction_method(snapshot):
            missing.discard(DESTRUCTION_GATE_LABEL)
        if SPEED_GATE_LABEL in missing and snapshot.player.speed >= SPEED_GATE_MINIMUM:
            # player.speed includes temporary boosts; a hasted check at the
            # stairs slightly over-trusts, which is acceptable for this gate.
            missing.discard(SPEED_GATE_LABEL)
        return frozenset(missing)

    def _refresh_warning_avoidance(self, snapshot: Snapshot) -> None:
        """Keep warning-refused grids at lethal-danger navigation weight.

        Injected into (or withdrawn from) the shared avoid set once per
        decision so every BFS — loot, exploration, flee, hunt, stairs —
        prices them identically to a lethal-danger cell.  While supplies
        remain, a destination only reachable through one is simply
        unreachable by walking and the existing danger/escape machinery owns
        the situation; only the entirely-exhausted ledger withdraws the
        avoidance so the user-sanctioned forced walk can route through."""
        cells = self._warning_refused_cells
        if not cells:
            return
        if self._warning_supplies_exhausted(snapshot):
            # Withdraw ONLY the warning owner's contribution: a coordinate the
            # engagement/status-threat owner also claims stays avoided — the
            # forced-walk permission must never erase another owner's
            # lethal-danger weight.
            self._engagement_avoid_cells -= (
                cells - self._engagement_owned_avoid_cells
            )
        else:
            self._engagement_avoid_cells |= cells
            if any(step in cells for step in self._explore_path):
                # A committed exploration path replays without re-planning;
                # drop it rather than march the tail back into the grid.
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
