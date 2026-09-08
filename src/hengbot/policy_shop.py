from __future__ import annotations

from hengbot.policy_constants import AMMO_CARRY_TARGET, FUNDRAISING_START_GOLD, QUAFF_KEY, TORCH_THROW_MAX_DEPTH, TOWN_IDS_WITH_HOME, ZUL_TOWN_ID, MANA_FOOD_DEVICE_TARGET, BUY_KEY, BUY_CONFIRM_SUFFIX, FOOD_MIN_SVAL, FOOD_TYPE_RATION, FOOD_TYPE_MANA, DISPOSABLE_POTION_SVALS, DISPOSABLE_SCROLL_SVALS, FUNDRAISING_GOLD_TARGET, IDENTIFY_PURCHASE_MAX, DETECTION_SCROLL_BUFFER, LEAVE_STORE_KEY, DIGGER_WIELD_LIMIT, PACK_CAPACITY, HOME_BATCH_RESERVED_SLOTS, SELL_KEY, SELL_ATTEMPT_LIMIT, STORE_RESTOCK_WAIT_TURNS, STORE_RESTOCK_REASON_NAMES, STORE_RESTOCK_REST_GAME_TURNS, STORE_ACCEPTED_TVALS, STORE_STUCK_LIMIT, TORCH_THROW_TARGET, TOWN_TRAVEL_STORE_SYMBOLS, CROSS_TOWN_SHOPPING_RESERVE, SHOP_APPROACH_STUCK_LIMIT, WAIT_KEY
from hengbot.policy_types import StoreVisitPhase, StoreVisit, TownNeed, NeedSpec, CrossTownShoppingExpedition, ProcurementHomeGate
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY, MIN_FREE_PACK_SLOTS
from hengbot.model import PLAYER_CLASS_WARRIOR, STORE_ALCHEMIST, STORE_ARMOURY, STORE_BLACK, STORE_GENERAL, STORE_HOME, STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON, SV_LITE_TORCH, SV_POTION_SPEED, SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, RESTORE_POTION_SVAL_BY_STAT, SV_ROD_LITE, SV_SCROLL_IDENTIFY, SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE, SV_SCROLL_ENCHANT_WEAPON_TO_HIT, SV_SCROLL_ENCHANT_WEAPON_TO_DAM, SV_STAFF_IDENTIFY, SV_WAND_STONE_TO_MUD, SV_HAFTED_WIZSTAFF, TVAL_FOOD, TVAL_LITE, TVAL_POTION, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, TVAL_HAFTED, InventoryItem, MonsterState, Position, Snapshot, StoreItem
from hengbot.town_arbiter import _new_town_turn_arbiter
from math import ceil
from hengbot.equipment_optimizer import equipment_identity
from hengbot.baseitem_knowledge import item_base_cost
import re
from dataclasses import replace

class ShopMixin:
    def _arbiter_close_store_visit(self, owner: str, outcome: str) -> None:
        """Close only a visit resource owned by the yielding token family."""
        visit = self._store_visit
        if visit is None:
            return
        aliases = {
            "store-router": {"store-router"},
            "shop-buy": {"shop-handler", "shop-one-shot"},
            "shop-sell": {"shop-handler", "shop-one-shot"},
            "home-visit": {"home-one-shot"},
            "equipment-txn": {"equipment-transaction"},
        }
        if visit.owner == owner or visit.owner in aliases.get(owner, set()):
            self._close_store_visit(outcome)

    def _store_visit_arbiter_owner(self, visit: StoreVisit) -> str:
        if (
            visit.owner in {"shop-handler", "shop-one-shot", "home-one-shot"}
            and not visit.operation_posted
            and visit.phase in {StoreVisitPhase.APPROACHING, StoreVisitPhase.ENTERING}
        ):
            return "store-router"
        aliases = {
            "shop-handler": "shop-buy",
            "shop-one-shot": "shop-buy",
            "home-one-shot": "home-visit",
            "equipment-transaction": "equipment-txn",
            "town-errand": "town-plan",
        }
        return aliases.get(visit.owner, visit.owner)

    @staticmethod
    def _inventory_item_from_store_item(item: StoreItem) -> InventoryItem:
        """Project an observed Home ware onto the canonical ~9 item contract."""
        return InventoryItem(
            slot=item.letter,
            name=item.name,
            count=item.count,
            tval=item.tval,
            sval=item.sval,
            aware=item.aware,
            known=item.known,
            fully_known=item.fully_known,
            charges=item.charges,
            pval=item.pval,
            is_equipment=item.is_equipment,
            is_ego=item.is_ego,
            is_artifact=item.is_artifact,
            is_cursed=item.is_cursed,
            inscription=item.inscription,
            is_broken=item.is_broken,
            to_h=item.to_h,
            to_d=item.to_d,
            to_a=item.to_a,
            ac=item.ac,
            damage_dice_num=item.damage_dice_num,
            damage_dice_sides=item.damage_dice_sides,
            known_flags=item.known_flags,
            pseudo_feeling=item.pseudo_feeling,
            weight=item.weight,
            weapon_proficiency=item.weapon_proficiency,
        )

    def _release_invalid_store_visit(self, snapshot: Snapshot) -> None:
        """Release a visit whose lifecycle has no remaining work."""
        visit = self._store_visit
        if (
            visit is not None
            and visit.operation_posted
            and not visit.operation_released
            and snapshot.store is None
            and visit.posted_sequence is not None
            and self._decision_sequence - visit.posted_sequence
            >= STORE_STUCK_LIMIT
        ):
            self._close_store_visit("posted-entry-unobserved")
            visit = None
        plan = self._town_errand_plan
        required_store = None
        released_stores: set[int] = set()
        if plan is not None:
            released_stores = set(plan.completed_this_visit) | set(
                plan.blocked_this_visit
            )
            if plan.index < len(plan.stops):
                candidate = plan.stops[plan.index]
                if plan.need_categories.get(candidate):
                    required_store = candidate
        if visit is not None and (
            visit.phase == StoreVisitPhase.CLOSED
            or visit.operation_effect_observed
            or not snapshot.in_town
            or (
                visit.owner == "town-errand"
                and visit.phase
                in (StoreVisitPhase.APPROACHING, StoreVisitPhase.ENTERING)
                and not visit.operation_posted
                and visit.store_type in released_stores
                and required_store is not None
                and visit.store_type != required_store
            )
        ):
            outcome = (
                "required-stop-changed"
                if visit.store_type in released_stores
                and required_store is not None
                and visit.store_type != required_store
                else self._store_visit.outcome or "completed"
            )
            self._close_store_visit(outcome)

    def _find_light_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: (
                self._is_spare_lantern(snapshot, it)
                or (it.is_torch and it.count > TORCH_THROW_TARGET)
            )
            and self._retention_surplus(snapshot, it) > 0
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )

    def _cheapest_exchange_item(self, snapshot: Snapshot) -> InventoryItem | None:
        candidates = [
            item
            for item in snapshot.inventory
            if not item.is_recall_scroll
            and self._entire_stack_is_surplus(snapshot, item)
            and item_base_cost(item, self._baseitem_costs) is not None
            and self._item_signature(item) not in self._undestroyable_sigs
        ]
        return min(
            candidates,
            key=lambda item: (item_base_cost(item, self._baseitem_costs), item.slot),
            default=None,
        )

    @staticmethod
    def _store_item_is_supply(item: StoreItem, kind: str) -> bool:
        if kind == "recall":
            return item.is_recall_scroll
        if kind == "teleport":
            return item.is_teleport_scroll
        if kind == "cure":
            return item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL
        if kind == "oil":
            return item.is_oil
        if kind == "food":
            return item.tval == TVAL_FOOD and item.sval >= FOOD_MIN_SVAL
        return False

    def _release_staged_store_operation(self, snapshot: Snapshot) -> str | None:
        """Release the one bound tail after its matching store page is fresh."""
        visit = self._store_visit
        if (
            snapshot.store is None
            or visit is None
            or not visit.operation_posted
            or visit.operation_released
            or visit.operation_key is None
            or snapshot.store.store_type != visit.store_type
            or visit.posted_turn is None
            or snapshot.turn < visit.posted_turn
        ):
            return None
        visit.transition(StoreVisitPhase.OPERATING)
        visit.operation_released = True
        return visit.operation_key

    @staticmethod
    def _digging_tool_sale_quality(item: InventoryItem) -> tuple[int, int, int, int]:
        return (
            item.pval,
            int(item.is_artifact),
            int(item.is_ego),
            item.sval,
        )

    def _sale_retains_digging_tool(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> bool:
        if not item.is_digging_tool:
            return False
        quality = self._digging_tool_sale_quality(item)
        available = [
            *[it for it in snapshot.inventory if it.is_digging_tool],
            *[it for it in snapshot.equipment if it.is_digging_tool],
            *[
                owned.item
                for owned in self._equipment_catalog.items
                if owned.origin == "home"
                and owned.item.is_digging_tool
                and self._item_signature(owned.item) not in self._deferred_home_items
            ],
        ]
        better_count = sum(
            candidate.count
            for candidate in available
            if self._digging_tool_sale_quality(candidate) > quality
        )
        return better_count < 2

    def _find_book_sale(
        self, snapshot: Snapshot, store_type: int | None = None
    ) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda item: self._book_sale_store_type(item) is not None
            and (store_type is None or self._book_sale_store_type(item) == store_type)
            and (item.name, item.tval, item.sval) not in self._unsellable_items,
        )

    def _find_device_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        reserve_slot = self._device_food_reserve_slot(snapshot)
        if self._home_identify_staff_sale_pending:
            # Home compaction destroys the withdrawn object's slot identity, but
            # it must not destroy any of the ordinary sale obligations.  Reuse
            # the single surplus selector, including same-visit retention.
            return self._find_surplus_identify_staff(
                snapshot, pending_home_sale=True
            )
        surplus_identify_staff = self._find_surplus_identify_staff(snapshot)
        surplus_slot = (
            surplus_identify_staff.slot
            if surplus_identify_staff is not None
            else None
        )
        return self._first_item(
            snapshot,
            lambda item: self._retention_surplus(snapshot, item) > 0
            and item.known
            and (
                item.slot == surplus_slot
                or
                (item.tval in {TVAL_WAND, TVAL_STAFF} and not self._is_useful_device(item))
                # A Rod of Light is redundant beside the lantern; sell it too. Only
                # this sval is listed, so useful rods (e.g. Identify) are kept.
                or (item.tval == TVAL_ROD and item.sval == SV_ROD_LITE)
            )
            and (item.slot != reserve_slot or item.slot == surplus_slot)
            and (item.name, item.tval, item.sval) not in self._unsellable_items,
        )

    @staticmethod
    def _carried_restore_potion(
        snapshot: Snapshot, stat: str
    ) -> InventoryItem | None:
        sval = RESTORE_POTION_SVAL_BY_STAT.get(stat)
        if sval is None:
            return None
        # Only an AWARE potion has an emitted sval (fair-play redacts the unknown);
        # an unidentified restore potion is not yet actionable.
        return next(
            (
                item
                for item in snapshot.inventory
                if item.is_potion and item.aware and item.sval == sval
            ),
            None,
        )

    def _needs_stat_restore(self, snapshot: Snapshot) -> bool:
        # A stat is drained (cur < max, shown on the character screen) and we have
        # no restore potion in the pack for it — a reason to visit the Alchemist.
        return any(
            self._carried_restore_potion(snapshot, stat) is None
            for stat in snapshot.player.drained_stats
        )

    def _restore_potion_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None:
            return None
        gold = snapshot.player.gold
        for stat in snapshot.player.drained_stats:
            if self._carried_restore_potion(snapshot, stat) is not None:
                continue  # already carry one to quaff; do not buy a second
            sval = RESTORE_POTION_SVAL_BY_STAT.get(stat)
            item = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_POTION and it.sval == sval and it.price <= gold
                ),
                None,
            )
            if item is not None:
                return item
        return None

    def _stat_restore_quaff_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        # Undo a drained ability by quaffing its restore potion. Only when safe
        # (no hostiles) and able to act (not confused/blind); the character screen
        # is what reveals the drain, so this uses no hidden information.
        player = snapshot.player
        if hostiles or player.confused or player.blind:
            return None
        for stat in player.drained_stats:
            potion = self._carried_restore_potion(snapshot, stat)
            if potion is not None:
                self.last_reason = f"restore:quaff-{stat}"
                return QUAFF_KEY + potion.slot
        return None

    @staticmethod
    def _dominated_disposal_store(item: InventoryItem | StoreItem) -> int | None:
        for store_type in (STORE_WEAPON, STORE_ARMOURY, STORE_MAGIC, STORE_GENERAL, STORE_TEMPLE):
            if item.tval in STORE_ACCEPTED_TVALS[store_type]:
                return store_type
        return None

    def _find_low_level_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        sell_unknown = self._deepest_level < 20 or self._sell_scavenged_consumables
        return self._first_item(
            snapshot,
            lambda it: self._retention_surplus(snapshot, it) > 0 and (
                (
                    sell_unknown
                    and (it.is_potion or it.is_scroll)
                    and not it.aware
                )
                or (it.is_potion and it.aware and it.sval in DISPOSABLE_POTION_SVALS)
                or (it.is_scroll and it.aware and it.sval in DISPOSABLE_SCROLL_SVALS)
                or (it.known and it.is_ego and it.is_cursed and not it.is_artifact)
            )
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )

    def _retry_after_store_restock(
        self, snapshot: Snapshot, store_types: tuple[int, ...]
    ) -> int | None:
        """Wait for stock turnover, then make the relevant shops eligible again."""
        if self._town_restock_last_wait_turn is not None:
            self._town_restock_waited_turns += max(
                0,
                min(
                    STORE_RESTOCK_REST_GAME_TURNS,
                    snapshot.turn - self._town_restock_last_wait_turn,
                ),
            )
            self._town_restock_last_wait_turn = None
        if self._town_restock_suppressed:
            return None
        if self._town_restock_wait_until is None:
            for store_type in store_types:
                remembered = getattr(self, "_town_supplier_stock", {}).get(
                    store_type
                )
                if remembered is None:
                    continue
                purchase = self._next_purchase(replace(snapshot, store=remembered))
                if purchase is not None and purchase.price <= snapshot.player.gold:
                    self._town_store_attempted.pop(store_type, None)
                    return store_type
        self._town_restock_waiting_for = store_types
        if self._town_restock_wait_until is None:
            self._town_restock_wait_until = snapshot.turn + STORE_RESTOCK_WAIT_TURNS
            return None
        if snapshot.turn < self._town_restock_wait_until:
            return None
        self._town_restock_wait_until = None
        for store_type in store_types:
            self._town_store_attempted.pop(store_type, None)
        return store_types[0]

    def _released_restock_store_key(
        self, snapshot: Snapshot, store_types: tuple[int, ...]
    ) -> str:
        """Route to a supplier made eligible by completed stock turnover."""
        food_store = (
            STORE_MAGIC
            if snapshot.player.food_type == FOOD_TYPE_MANA
            else STORE_GENERAL
        )
        released_store_types = (
            (food_store,) if not self._food_ready(snapshot) else store_types
        )
        # Every released restock supplier must get a fresh route decision.  A
        # prior terminal otherwise short-circuits _shopping_approach_step, and
        # an inert approach to another store can retain visit ownership before
        # the known town map is consulted.  Posted operations remain
        # authoritative and are deliberately not released here.
        if self._town_blocked_reason in {
            "restock-store-unreachable",
        }:
            self._town_blocked_reason = None
        visit = self._store_visit
        if (
            visit is not None
            and visit.store_type not in released_store_types
            and visit.phase == StoreVisitPhase.APPROACHING
            and not visit.operation_posted
        ):
            self._close_store_visit("restock-reroute")
        # A completed recall-stock cycle is progress evidence, not permission
        # to starve behind the same owner.  Home has already had its normal
        # first pass before terminal restock handling.  If food is still a
        # departure shortage, release its supplier before retrying recall.
        if not self._food_ready(snapshot):
            self._town_store_attempted.pop(food_store, None)
            step = self._shopping_approach_step(snapshot, food_store)
            if step is not None:
                self.last_reason = "shop:approach"
                return self._shopping_approach_key(snapshot, step, "shop:travel")
            self._town_blocked_reason = "restock-store-unreachable"
            return self._town_blocked_key(snapshot)
        step = self._shopping_approach_step(snapshot)
        if step is not None and self._shopping_approach_store_type in store_types:
            self.last_reason = "shop:approach"
            return self._shopping_approach_key(snapshot, step, "shop:travel")
        # Another live errand can precede the released suppliers in the town
        # plan.  A restock release says nothing about that errand's route, so
        # check each released supplier itself before declaring all of them
        # unreachable.
        for store_type in self._order_town_stops(snapshot, list(store_types)):
            step = self._shopping_approach_step(snapshot, store_type)
            if step is not None:
                self.last_reason = "shop:approach"
                return self._shopping_approach_key(snapshot, step, "shop:travel")
        # Recall stock still owns departure. If the released supplier cannot be
        # routed, use the existing visible town terminal instead of descending
        # or silently arming the same wait again.
        self._town_blocked_reason = "restock-store-unreachable"
        return self._town_blocked_key(snapshot)

    def _enumerate_live_store_claims(self, snapshot: Snapshot) -> list[TownNeed]:
        """Enumerate every live owner of a store route for this decision.

        The generic need registry explicitly owns catalogue scans, queued Home
        identities, identification errands, procurement shortages, disposal,
        fundraising, curse service, sales, and optional shopping.  The two
        state-machine owners below are not NeedSpec predicates: calibration /
        optimizer work owns Home while its hard route bound remains, and an
        executable equipment transaction owns the context it was bound to.
        This is the sole input to the town-plan projection.
        """
        claims = list(self._enumerate_town_needs(snapshot))
        # Withdrawal requesters must file an exact executor request before the
        # router may act.  The legacy terminal posts this same owner expectation,
        # so an unchanged progress core suppresses the claim instead of rebuilding
        # the just-failed Home approach.
        departure_categories = {
            need.category for need in self._departure_blocking_town_needs(snapshot)
        }
        claims = [
            claim for claim in claims
            if self._owner_may_select(
                snapshot, f"home-withdrawal:{claim.category}"
            )
            # E3: an expectation refusal cannot silently erase a failing gate
            # conjunct while its supplier remains reachable.  Keep that claim
            # routable; if it later proves exhausted, the ordinary visible
            # departure-unsatisfiable terminal owns the outcome.
            or (
                claim.category in departure_categories
                and self._town_need_supplier_reachable(snapshot, claim)
            )
        ]
        if self._opening_q34_active(snapshot):
            # Q34's opening owns town until the quest clears.  Candidate
            # generation is not the claim boundary: NeedSpecs can remain true
            # outside _town_need_candidates, and the equipment state machines
            # below are independent producers.  Admit only the opening's two
            # errands here, at the final producer consumed by town routing.
            return [
                claim
                for claim in claims
                if claim.category in {"combat-weapon", "quest-throwing-items"}
            ]
        post_alchemist_home = any(
            claim.ordering_class == "post-alchemist-home"
            or claim.category == "identification-source"
            for claim in claims
        )
        if (
            self._equipment_work_home_route_available()
            and self._home_owner_goal_pending(snapshot)
            and self._owner_may_select(snapshot, "home-withdrawal:equipment-work")
            and not any(claim.category == "equipment-work" for claim in claims)
        ):
            claims.append(TownNeed(
                STORE_HOME,
                "equipment-work",
                "post-alchemist-home" if post_alchemist_home else "home-first",
            ))
        session = self._equipment_transaction_session
        if (
            session is not None
            and session.executable
            and session.required_context is not None
            and not any(claim.category == "equipment-transaction" for claim in claims)
        ):
            claims.append(TownNeed(
                STORE_HOME,
                "equipment-transaction",
                "home-first",
            ))
        return claims

    def _next_required_store_type(self, snapshot: Snapshot) -> int | None:
        self._town_plan_projection_telemetry = {
            "evaluated": False,
            "plan_rebuilt": False,
            "rebuilt_stops": [],
        }
        departure_ready: bool | None = None

        def town_departure_ready() -> bool:
            nonlocal departure_ready
            if departure_ready is None:
                departure_ready = self._town_departure_ready(snapshot)
            return departure_ready

        # An inscription is only the entry half of a two-stage sale.  Keep the
        # store that owns its pending tail ahead of freshly rebuilt purchase,
        # Home, and fundraising claims until the tagged item is observed and
        # the sale is composed.  Otherwise an unaffordable purchase can route
        # away from the sale that would fund it, leaving the batch owner alive
        # but permanently uncomposable.
        pending_sale = self._batch_sell_pending
        if (
            snapshot.in_town
            and pending_sale is not None
            and pending_sale.get("phase") in {"await-inscription", "await-sale"}
        ):
            return int(pending_sale["store_type"])

        # The queued take is an address-bearing continuation of the current
        # Home visit, not a need that may be reprioritized out of a rebuilt
        # fundraising plan (notably scavenge's [Alchemist, General] plan).
        # Keep Home first until the take posts, confirms, or its bounded
        # failure path visibly abandons it to the purchase fallback.
        if snapshot.in_town and (
            self._home_digger_withdraw_pending
            or (
                self._home_withdrawal_queued
                and self._home_pending_item is not None
            )
            or (
                getattr(self, "_home_procurement_batch_active", False)
                and self._home_pending_batch
            )
        ):
            # The departure latch is itself an authoritative Home claim.  A
            # failed/recovered boundary can lose the page-relative item
            # address before the next open Home observation recreates it; do
            # not let that transient absence strand the route behind another
            # store.  ``queued`` describes a selected address awaiting post,
            # so it must not survive once that address is gone.
            if self._home_pending_item is None and not self._home_pending_batch:
                self._home_withdrawal_queued = False
            return STORE_HOME

        if (
            snapshot.in_town
            and snapshot.player.hungry
            and self._find_edible(snapshot) is None
        ):
            food_store = (
                STORE_MAGIC
                if snapshot.player.food_type == FOOD_TYPE_MANA
                else STORE_GENERAL
            )
            return (
                None
                if food_store in self._town_store_attempted
                else food_store
            )
        opening_q34 = self._opening_q34_active(snapshot)
        opening_torch_shortage = self._opening_q34_torch_shortage(snapshot)
        if opening_q34 and opening_torch_shortage > 0 and self._fundraising_mode in {
            "prepare", "mine", "scavenge"
        }:
            # prime() can reconstruct fundraising from the scrolls left by an
            # interrupted bad opening.  Cancel that stale owner and rebuild the
            # route so resume repairs the same character instead of repeating
            # Home -> Alchemist -> Yeek Cave.
            self._fundraising_mode = None
            self._planned_mining_runs = None
            self._town_store_attempted.clear()
            self._town_restock_suppressed = False
            self._town_errand_plan = None
        if self._town_restock_suppressed:
            self._town_errand_plan = None
            return None
        if (
            opening_q34
            and opening_torch_shortage > 0
            and STORE_GENERAL in self._town_store_attempted
        ):
            self._town_restock_rechecked.discard(STORE_GENERAL)
            return self._retry_after_store_restock(snapshot, (STORE_GENERAL,))
        if (
            snapshot.store is not None
            and self._town_errand_plan is not None
            and self._town_errand_plan.index < len(self._town_errand_plan.stops)
            and self._town_errand_plan.stops[self._town_errand_plan.index]
            == snapshot.store.store_type
        ):
            return snapshot.store.store_type
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.gold < FUNDRAISING_START_GOLD
            and self._fundraising_mode is None
            and (not opening_q34 or opening_torch_shortage == 0)
        ):
            self._start_fundraising(snapshot)
        self._refresh_nonhome_effect_refusals(snapshot)
        ledger_blocked = {
            store
            for store in self._town_visit_ledger.blocked_stores
            if store == STORE_HOME
            and self._town_store_blocked_under_applicable_bound(store)
        } | {
            store
            for store, failures in self._town_visit_ledger.approach_fails.items()
            if store == STORE_HOME
            and failures >= self._town_store_visit_limit(store)
        }
        identification_home_target = any(
            owned.origin == "home"
            and self._item_signature(owned.item) == self._identification_candidate
            for owned in self._equipment_catalog.items
        )
        if (
            self._identification_need is not None
            and self._identification_need != "full"
            and self._town_blocked_reason != "repetition"
            and not self._identification_need_actionable(snapshot)
        ):
            # Retire an uncomposable identify owner before independent supply
            # claims rebuild the plan; a fresh visit/source naturally revives
            # the ordinary producer without a permanent latch.
            if identification_home_target and STORE_HOME not in ledger_blocked:
                self._rearm_town_store_for_new_work(STORE_HOME)
                return STORE_HOME
            else:
                self._town_terminal_transitions(snapshot)
        live_needs = self._enumerate_live_store_claims(snapshot)
        if self._town_blocked_reason == "repetition":
            blocking = {
                need.category
                for need in self._departure_blocking_town_needs(snapshot)
            }
            # Equipment state machines are themselves departure owners and are
            # deliberately not represented by the generic NeedSpec table.
            blocking.update({"equipment-work", "equipment-transaction"})
            live_needs = [
                need for need in live_needs if need.category in blocking
            ]
        needs = [
            need
            for need in live_needs
            if need.store_type not in ledger_blocked
            and need.store_type
            not in self._town_visit_ledger.nonhome_attempted_without_effect
        ]
        warned = set(self._town_visit_ledger.drift_warnings)
        live_pairs = {(need.store_type, need.category) for need in needs}
        for store_type, category in live_pairs:
            warning = (
                f"drift:{STORE_RESTOCK_REASON_NAMES.get(store_type, store_type)}"
                f":{category}"
            )
            if (
                (store_type, category) in self._town_visit_ledger.satisfied_needs
                and warning not in warned
            ):
                self._town_visit_ledger.drift_warnings.append(warning)
                warned.add(warning)
        self._town_visit_ledger.satisfied_needs.intersection_update(live_pairs)
        previous_plan = self._town_errand_plan
        # The plan is a disposable ordering view over this decision's claims.
        # A live claim supersedes a completed/attempted route snapshot; only the
        # ledger's unchanged hard bounds can suppress it.
        plan = self._build_town_errand_plan(snapshot, needs)
        self._town_errand_plan = plan
        self._town_plan_projection_telemetry = {
            "evaluated": True,
            "plan_rebuilt": True,
            "rebuilt_stops": list(plan.stops) if plan is not None else [],
        }
        if plan is not None:
            previous_exhausted = (
                previous_plan is None
                or previous_plan.index >= len(previous_plan.stops)
            )
            for store_type in plan.stops:
                prior_categories = (
                    set(previous_plan.need_categories.get(store_type, ()))
                    if previous_plan is not None else set()
                )
                live_categories = set(plan.need_categories.get(store_type, ()))
                post_alchemist_home = (
                    store_type == STORE_HOME
                    and any(
                        need.store_type == STORE_HOME
                        and need.ordering_class == "post-alchemist-home"
                        for need in needs
                    )
                    and STORE_ALCHEMIST in self._town_store_attempted
                )
                if (
                    previous_exhausted
                    or live_categories - prior_categories
                    or post_alchemist_home
                ):
                    self._town_store_attempted.pop(store_type, None)
                    if self._store_entry_failed_owner == store_type:
                        self._store_entry_failed_owner = None
                if store_type not in self._town_store_attempted:
                    return store_type
            return None
        plan = self._town_errand_plan
        post_alchemist_home_needed = any(
            need.ordering_class == "post-alchemist-home"
            or need.category == "identification-source"
            for need in needs
        )
        warned = set(self._town_visit_ledger.drift_warnings)
        for need in needs:
            satisfied = (need.store_type, need.category)
            warning = (
                f"drift:{STORE_RESTOCK_REASON_NAMES.get(need.store_type, need.store_type)}"
                f":{need.category}"
            )
            if (
                satisfied in self._town_visit_ledger.satisfied_needs
                and warning not in warned
            ):
                self._town_visit_ledger.drift_warnings.append(warning)
                warned.add(warning)
        if (
            self._equipment_transaction_session is not None
            and self._equipment_transaction_session.executable
            and self._equipment_transaction_session.required_context is not None
            and STORE_HOME not in self._town_store_attempted
        ):
            needs.append(TownNeed(STORE_HOME, "equipment-transaction", "home-first"))
        needed_stores = {need.store_type for need in needs}
        if plan is None:
            plan = self._build_town_errand_plan(snapshot, needs)
            self._town_errand_plan = plan
        elif plan.index >= len(plan.stops):
            # A completed plan is only a snapshot of the needs visible when it
            # was built. Completing an identification errand can expose the
            # ordinary supply shortages that it previously owned exclusively.
            # Rebuild for newly actionable stores instead of falling into the
            # legacy terminal router, whose first shortage can monopolize town
            # with an endless one-store restock cycle.
            completed = (
                set(plan.completed_this_visit)
                | set(plan.blocked_this_visit)
                | ledger_blocked
            )
            self._town_plan_projection_telemetry = {
                "evaluated": True,
                "home_attempted": STORE_HOME in self._town_store_attempted,
                "home_attempted_entry": self._town_store_attempted.get(STORE_HOME),
                "plan_completed_this_visit": list(plan.completed_this_visit),
                "plan_blocked_this_visit": list(plan.blocked_this_visit),
                "ledger_blocked": sorted(ledger_blocked),
                "plan_rebuilt": False,
                "rebuilt_stops": [],
            }
            remaining_needs = [
                need for need in needs
                if need.store_type not in completed
                or (
                    need.store_type == STORE_HOME
                    and need.ordering_class == "post-alchemist-home"
                    and STORE_HOME not in plan.blocked_this_visit
                )
            ]
            if any(
                need.store_type not in self._town_store_attempted
                or (
                    need.store_type == STORE_HOME
                    and need.ordering_class == "post-alchemist-home"
                    and STORE_HOME not in plan.blocked_this_visit
                )
                for need in remaining_needs
            ):
                # Home before and Home after an identification purchase are two
                # distinct phases of one transaction.  The first visit records
                # Home as completed/attempted when it discovers an item needing
                # an Alchemist source.  Once that source is carried, explicitly
                # re-arm the post-Alchemist withdrawal instead of treating the
                # earlier catalog pass as satisfying it too.
                if any(
                    need.store_type == STORE_HOME
                    and need.ordering_class == "post-alchemist-home"
                    for need in remaining_needs
                ):
                    self._rearm_town_store_for_new_work(STORE_HOME)
                plan = self._build_town_errand_plan(snapshot, remaining_needs)
                self._town_errand_plan = plan
                self._town_plan_projection_telemetry["plan_rebuilt"] = True
                self._town_plan_projection_telemetry["rebuilt_stops"] = (
                    list(plan.stops) if plan is not None else []
                )
        elif plan.index < len(plan.stops):
            pending = set(plan.stops[plan.index + 1 :])
            finished = (
                set(plan.completed_this_visit)
                | set(plan.blocked_this_visit)
                | ledger_blocked
            )
            additions = needed_stores - pending - finished - {plan.stops[plan.index]}
            if additions:
                current_store = plan.stops[plan.index]
                current_position = (
                    self._town_map.store_position(current_store)
                    if self._town_map_active(snapshot)
                    else snapshot.player.position
                )
                old_remaining = plan.stops[plan.index + 1 :]
                reordered = self._order_town_needs(
                    snapshot,
                    needs,
                    old_remaining + sorted(additions),
                    current_position,
                )
                plan.stops[plan.index + 1 :] = reordered
                plan.inserted_this_visit.extend(sorted(additions))

        if plan is not None:
            for store_type in needed_stores:
                plan.need_categories[store_type] = tuple(
                    need.category
                    for need in needs
                    if need.store_type == store_type
                )

        while plan is not None and plan.index < len(plan.stops):
            store_type = plan.stops[plan.index]
            if store_type not in needed_stores:
                plan.index += 1
                continue
            if store_type in self._town_store_attempted:
                if (
                    store_type == STORE_HOME
                    and post_alchemist_home_needed
                    and STORE_HOME not in plan.blocked_this_visit
                ):
                    # A plan built up-front can already contain Home twice
                    # (catalog first, withdrawal after Alchemist).  Release the
                    # first visit's latch only for that explicit second phase.
                    self._rearm_town_store_for_new_work(STORE_HOME)
                    return STORE_HOME
                plan.skipped_latched.append(store_type)
                plan.index += 1
                continue
            return store_type

        if opening_q34 and opening_torch_shortage > 0:
            # The fresh-character route has exactly one owner until all Q34
            # throwing torches are carried.  If the General Store did not have
            # enough stock, wait for its next turnover and retry that same shop;
            # falling through to the ordinary terminal router starts unrelated
            # Home/Alchemist/Magic errands and destroys the opening route.
            if STORE_GENERAL not in self._town_store_attempted:
                return STORE_GENERAL
            # Mandatory opening stock is different from an optional restock
            # attempt: keep permitting one genuine General Store re-check per
            # completed turnover until the force requirement is satisfied.
            self._town_restock_rechecked.discard(STORE_GENERAL)
            return self._retry_after_store_restock(snapshot, (STORE_GENERAL,))

        if live_needs and all(
            need.store_type != STORE_HOME
            and need.store_type
            in self._town_visit_ledger.nonhome_attempted_without_effect
            for need in live_needs
        ):
            supplier = self._departure_supplier_counterfactual(snapshot)
            if supplier is not None:
                return supplier
            self._town_blocked_reason = "departure-unsatisfiable"
            return None

        self._town_terminal_transitions(snapshot)
        refreshed_needs = self._enumerate_town_needs(snapshot)
        if refreshed_needs:
            refreshed_plan = self._build_town_errand_plan(snapshot, refreshed_needs)
            if refreshed_plan is not None:
                exhausted_stores = (
                    (
                        set(plan.completed_this_visit)
                        | set(plan.blocked_this_visit)
                    )
                    if plan is not None
                    else set()
                ) | ledger_blocked
                for store_type in refreshed_plan.stops:
                    restock_recheck = (
                        store_type in self._town_restock_rechecked
                        and store_type not in self._town_store_attempted
                    )
                    if (
                        (
                            store_type not in exhausted_stores
                            or restock_recheck
                        )
                        and store_type not in self._town_store_attempted
                    ):
                        if (
                            restock_recheck
                            and self._town_restock_waiting_for
                            and all(
                                waiting in self._town_restock_rechecked
                                for waiting in self._town_restock_waiting_for
                            )
                        ):
                            self._town_restock_waiting_for = ()
                        return store_type
        if live_needs and all(
            need.store_type != STORE_HOME
            and need.store_type
            in self._town_visit_ledger.nonhome_attempted_without_effect
            for need in live_needs
        ):
            if self._departure_supplier_counterfactual(snapshot) is None:
                self._town_blocked_reason = "departure-unsatisfiable"
        return None

    def _release_blocked_store_latches(self, store_type: int) -> None:
        """Release flow state that a blocked store can no longer service."""
        if store_type == STORE_HOME:
            self._release_identification_source_reservation()
            self._home_candidate_waiting = False
            self._home_pending_item = None
            self._home_pending_batch.clear()
            self._home_atomic_withdraw_pending = None
            self._home_random_teleport_withdrawal = None

    def _rearm_town_store_for_new_work(
        self, store_type: int, *, release_visit_bound: bool = False
    ) -> None:
        """Release a completed stop when the current stop creates new work there."""
        home_visit = getattr(self, "_home_visit", None)
        if (
            store_type == STORE_HOME
            and home_visit is not None
            and home_visit.attempts_used >= home_visit.attempt_limit
        ):
            return
        self._town_store_attempted.pop(store_type, None)
        if release_visit_bound:
            self._town_visit_ledger.blocked_stores.discard(store_type)
            self._town_visit_ledger.blocked_store_limits.pop(store_type, None)
            self._town_visit_ledger.approach_fails.pop(store_type, None)
        if (
            release_visit_bound
            and store_type == STORE_HOME
            and self._calibration_restore_signatures
        ):
            self._town_visit_ledger.need_attempts.pop(
                "calibration-restore", None
            )
        plan = self._town_errand_plan
        if plan is None:
            return
        plan.completed_this_visit[:] = [
            store for store in plan.completed_this_visit if store != store_type
        ]
        plan.blocked_this_visit[:] = [
            store for store in plan.blocked_this_visit if store != store_type
        ]
        plan.skipped_latched[:] = [
            store for store in plan.skipped_latched if store != store_type
        ]

    def cross_town_shopping_state(self) -> dict[str, object]:
        expedition = self._cross_town_shopping
        if expedition is None:
            return dict(self._cross_town_shopping_funds)
        return {
            "trigger_town_id": expedition.trigger_town_id,
            "blocking_categories": list(expedition.blocking_categories),
            "shortage_costs": dict(expedition.shortage_costs),
            "reserve": expedition.reserve,
            "required_gold": expedition.required_gold,
            "candidate_order": list(expedition.candidate_order),
            "tried_towns": list(expedition.tried_towns),
            "target_town_id": expedition.target_town_id,
        }

    def _cross_town_shopping_key(self, snapshot: Snapshot) -> str | None:
        shortages = self._cross_town_shortages(snapshot)
        unobtainable = self._cross_town_unobtainable_categories(
            snapshot, shortages
        )
        expedition = self._cross_town_shopping
        if expedition is None:
            if not unobtainable:
                return None
            costs: dict[str, int] = {}
            for category, quantity in shortages:
                observed = self._observed_departure_prices.get(category)
                if observed is None:
                    self._cross_town_shopping_funds = {
                        "trigger_town_id": self._effective_town_id(snapshot),
                        "blocking_categories": list(unobtainable),
                        "missing_price_for": category,
                        "funds_sufficient": None,
                        "candidate_order": list(
                            self._cross_town_candidate_order(snapshot)
                        ),
                        "tried_towns": [],
                    }
                    return None
                price, units = observed
                costs[category] = ceil(quantity / units) * price
            candidates = self._cross_town_candidate_order(snapshot)
            if not candidates:
                return None
            required_gold = sum(costs.values()) + CROSS_TOWN_SHOPPING_RESERVE
            self._cross_town_shopping_funds = {
                "trigger_town_id": self._effective_town_id(snapshot),
                "blocking_categories": list(unobtainable),
                "shortage_costs": dict(costs),
                "reserve": CROSS_TOWN_SHOPPING_RESERVE,
                "required_gold": required_gold,
                "gold": snapshot.player.gold,
                "funds_sufficient": snapshot.player.gold >= required_gold,
                "candidate_order": list(candidates),
                "tried_towns": [],
            }
            if snapshot.player.gold < required_gold:
                # This is intentionally the ordinary fundraising owner and
                # target; the existing mining kit/departure/walk-in rules apply.
                self._planned_mining_runs = None
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                self.last_reason = "town:cross-town-shopping-needs-funds"
                return WAIT_KEY
            expedition = CrossTownShoppingExpedition(
                trigger_town_id=self._effective_town_id(snapshot),
                blocking_categories=unobtainable,
                shortage_costs=costs,
                reserve=CROSS_TOWN_SHOPPING_RESERVE,
                required_gold=required_gold,
                candidate_order=candidates,
            )
            self._cross_town_shopping = expedition

        current = self._effective_town_id(snapshot)
        if (
            expedition.target_town_id is not None
            and current == expedition.target_town_id
        ):
            if current not in expedition.tried_towns:
                expedition.tried_towns.append(current)
            expedition.target_town_id = None
        for next_town in expedition.candidate_order:
            if next_town in expedition.tried_towns or next_town == current:
                continue
            expedition.target_town_id = next_town
            key = self._town_teleport_key(snapshot, next_town)
            if key is not None:
                self.last_reason = f"town:cross-town-shopping:travel-{next_town}"
                return key
            # A refused or unroutable trip is terminal for this visit.  Do not
            # approach another Inn destination on the following decision.
            expedition.tried_towns.extend(
                town_id for town_id in expedition.candidate_order
                if town_id not in expedition.tried_towns
            )
            expedition.target_town_id = None
            return None
        return None

    def _set_town_store_attempted(
        self, store_type: int, turn: int, site_label: str, *, if_absent: bool = False
    ) -> None:
        """Set the existing latch and retain observation-only Home provenance."""
        if if_absent and store_type in self._town_store_attempted:
            return
        self._town_store_attempted[store_type] = turn
        if store_type == STORE_HOME:
            entry = {"turn": turn, "site": site_label}
            self._home_latch_active = entry
            self._home_latch_history = [*self._home_latch_history, entry][-8:]

    def _purchase_has_fresh_home_absence(
        self, snapshot: Snapshot, item: StoreItem
    ) -> ProcurementHomeGate:
        """Release a buy only for fresh absence or a statically Home-less town."""
        evaluated = self._evaluate_purchase_home_gate(snapshot, item)
        item_class = self._procurement_class(item)
        self._home_procurement_fallthrough_equivalence = (
            self._procurement_equivalence(item_class)
        )
        if not self._home_knowledge_current:
            self._home_procurement_probe = item_class
            if not self._current_town_has_home(snapshot):
                self._home_procurement_probe = None
                self._home_procurement_fallthrough = "town-without-home"
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "wrapper-town-without-home", wrapper_fallthrough="town-without-home")
            if not self._home_available(snapshot):
                self._home_procurement_probe = None
                self._record_purchase_home_refusal(
                    "town:blocked:procurement-home-unavailable"
                )
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "wrapper-home-unavailable")
            visit = self._store_visit
            transferred_visit = getattr(
                self._town_turn_arbiter, "_transferred_visit", None
            )
            if transferred_visit is not None:
                visit = transferred_visit
            filed = self._ensure_home_visit_request(snapshot)
            if (
                filed
                and visit is not None
                and visit.store_type != STORE_HOME
            ):
                self._home_procurement_probe = None
                self._record_purchase_home_refusal(
                    "shop:home-first-yields-to-current-visit"
                )
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "wrapper-yield-current-visit")
            approach = (
                self._shopping_approach_step(snapshot, STORE_HOME) if filed else None
            )
            if not filed or approach is None:
                self._home_procurement_probe = None
                self._record_purchase_home_refusal(
                    "town:blocked:procurement-home-unroutable"
                )
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "wrapper-home-unroutable")
            return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "wrapper-stale-knowledge-route-home")
        candidate = self._home_procurement_candidate(item_class)
        failure = getattr(self, "_home_procurement_withdraw_failure", None)
        viable_class_matches = self._home_procurement_viable_class_matches(
            item_class
        )
        viable_item = self._home_procurement_viable_item(item_class)
        if (
            viable_item is not None
            and self._procurement_missing_amount(snapshot, viable_item) <= 0
        ):
            self._home_procurement_probe = None
            self._home_procurement_fallthrough = "no-procurement-need"
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                "wrapper-no-procurement-need",
                wrapper_fallthrough="no-procurement-need",
            )
        all_viable_deferred = viable_class_matches > 0 and candidate is None
        if all_viable_deferred or (
            failure is not None
            and failure.get("item_class") == self._procurement_equivalence(item_class)
            and viable_class_matches > 0
        ):
            self._home_procurement_probe = None
            self._record_purchase_home_refusal(
                "town:blocked:home-withdraw-failed-stock-present"
            )
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.BLOCKED,
                "wrapper-withdraw-failed-stock-present",
            )
        if candidate is not None:
            missing = self._procurement_missing_amount(snapshot, candidate)
            if missing <= 0:
                self._home_procurement_probe = None
                self._home_procurement_fallthrough = "no-procurement-need"
                return self._record_home_gate(
                    snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                    "wrapper-no-procurement-need",
                    wrapper_fallthrough="no-procurement-need",
                )
            identity = self._item_signature(candidate)
            self._home_procurement_probe = item_class
            self._home_pending_item = identity
            self._home_pending_quantity = min(
                candidate.count,
                max(1, missing),
            )
            if not hasattr(self, "_home_pending_quantities"):
                self._home_pending_quantities = {}
            self._home_pending_quantities[identity] = self._home_pending_quantity
            self._queue_home_procurement_batch(snapshot, candidate)
            self._home_withdrawal_queued = True
            return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "wrapper-candidate-home-first")
        self._home_procurement_probe = None
        self._home_procurement_fallthrough = "fresh-catalogue-absence"
        return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "wrapper-fresh-catalogue-absence", wrapper_fallthrough="fresh-catalogue-absence")

    def _record_purchase_home_refusal(self, reason: str) -> None:
        """Retain a probe result without publishing it as a decided stop."""
        self._shop_selector_diagnostics["composition_refusal"] = reason
        self._shop_selector_diagnostics["composition_refusal_sequence"] = (
            self._decision_sequence
        )

    def _publish_purchase_home_block(self) -> None:
        """Publish the current probe's terminal only at a decided WAIT."""
        reason = self._shop_selector_diagnostics.get("composition_refusal")
        sequence = self._shop_selector_diagnostics.get(
            "composition_refusal_sequence"
        )
        if sequence == self._decision_sequence and reason in {
            "town:blocked:home-withdraw-failed-stock-present",
            "town:blocked:procurement-home-unavailable",
            "town:blocked:procurement-home-unroutable",
        }:
            self.last_reason = reason
            if reason == "town:blocked:home-withdraw-failed-stock-present":
                self._town_blocked_reason = reason

    def _evaluate_purchase_home_gate(
        self, snapshot: Snapshot, item: StoreItem
    ) -> ProcurementHomeGate:
        """Evaluate Home-first purchase policy without changing policy state."""
        if not self._home_knowledge_current:
            if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
                town_has_home = True
                home_available = True
            else:
                visible_home = any(
                    grid.store_number == STORE_HOME for grid in snapshot.grids.values()
                )
                town_has_home = (
                    snapshot.town_id in TOWN_IDS_WITH_HOME
                    or snapshot.town_id not in {None, -1, ZUL_TOWN_ID}
                    or visible_home
                )
                home_available = bool(
                    visible_home or self._town_store_positions.get(STORE_HOME)
                )
            if not town_has_home:
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "evaluate-stale-town-without-home")
            if not home_available:
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "evaluate-stale-home-unavailable")
            visit = self._store_visit
            if visit is not None and visit.store_type != STORE_HOME:
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "evaluate-stale-current-visit")
            if self._town_blocked_reason is not None and (
                self._town_blocked_reason != "repetition"
            ):
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "evaluate-stale-town-blocked")
            if (
                STORE_HOME in self._town_store_attempted
                or STORE_HOME in self._town_visit_ledger.blocked_stores
                or self._town_visit_ledger.approach_fails[STORE_HOME]
                >= self._town_store_visit_limit(STORE_HOME)
            ):
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "evaluate-stale-home-latched")
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.store_number == STORE_HOME
            )
            if step is None and self._town_map_active(snapshot):
                step = self._town_map_goal_step(
                    snapshot, self._town_map.store_position(STORE_HOME)
                )
            home_positions = self._town_store_positions.get(STORE_HOME)
            goal = (
                min(
                    home_positions,
                    key=lambda position: snapshot.player.position.distance_to(position),
                )
                if home_positions
                else None
            )
            if goal is None and self._town_map_active(snapshot):
                goal = self._town_map.store_position(STORE_HOME)
            if (
                step is None
                and goal is not None
                and snapshot.player.position.distance_to(goal) >= 3
            ):
                step = goal
            result = ProcurementHomeGate.HOME_FIRST if step is not None else ProcurementHomeGate.BLOCKED
            return self._record_home_gate(snapshot, item, result, "evaluate-stale-route-found" if step is not None else "evaluate-stale-route-missing")
        item_class = self._procurement_class(item)
        candidate = self._home_procurement_candidate(item_class)
        failure = getattr(self, "_home_procurement_withdraw_failure", None)
        viable_class_matches = self._home_procurement_viable_class_matches(
            item_class
        )
        viable_item = self._home_procurement_viable_item(item_class)
        if (
            viable_item is not None
            and self._procurement_missing_amount(snapshot, viable_item) <= 0
        ):
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                "evaluate-no-procurement-need",
            )
        all_viable_deferred = viable_class_matches > 0 and candidate is None
        if all_viable_deferred or (
            failure is not None
            and failure.get("item_class") == self._procurement_equivalence(item_class)
            and viable_class_matches > 0
        ):
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.BLOCKED,
                "evaluate-withdraw-failed-stock-present",
            )
        if candidate is not None:
            if self._procurement_missing_amount(snapshot, candidate) <= 0:
                return self._record_home_gate(
                    snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                    "evaluate-no-procurement-need",
                )
            return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "evaluate-candidate-home-first")
        return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "evaluate-no-candidate")

    def _wanted_purchase_is_home_first_refused(
        self, snapshot: Snapshot, store_type: int
    ) -> bool:
        """Recognize an observed wanted purchase that Home-first would refuse."""
        observed_store = snapshot.store
        if observed_store is None:
            observation = self._shop_observation
            if observation is None:
                return False
            observed_store = observation[0]
        if observed_store.store_type != store_type:
            return False
        item = self._next_purchase(replace(snapshot, store=observed_store))
        return item is not None and self._evaluate_purchase_home_gate(
            snapshot, item
        ) is not ProcurementHomeGate.ALLOW_PURCHASE

    def _mana_survival_sale_candidate(
        self, snapshot: Snapshot, store_type: int
    ) -> InventoryItem | None:
        """Use only existing retention-safe, inscription-safe sale contracts."""
        if store_type == STORE_ALCHEMIST:
            return self._first_item(
                snapshot,
                lambda item: item.is_scroll
                and self._retention_surplus(snapshot, item) > 0
                and self._item_signature(item) not in self._unsellable_items,
            )
        if store_type == STORE_WEAPON:
            return self._first_item(
                snapshot,
                lambda item: item.is_ammo
                and self._retention_surplus(snapshot, item) > 0
                and self._item_signature(item) not in self._unsellable_items,
            )
        return None

    def _next_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        """Apply the cheap fundraising-kit reserve to the normal buy order."""
        item = self._next_purchase_unreserved(snapshot)
        if item is None or item.is_digging_tool or item.is_treasure_detection_scroll:
            return item
        if (
            self._opening_q34_torch_shortage(snapshot) > 0
            and item.tval == TVAL_LITE
            and item.sval == SV_LITE_TORCH
        ):
            # The fresh-character contract is Q34 first.  Reserving the entire
            # 100g mining-kit budget here made a 100g birth character visit the
            # correct store, reject every torch, and fall back to Home.
            return item
        reserve = self._fundraising_kit_reserve(snapshot)
        if reserve == 0:
            return item
        quantity = self._purchase_quantity(snapshot, item)
        if snapshot.player.gold - item.price * quantity < reserve:
            return None
        return item

    @staticmethod
    def _purchase_diagnostic_category(item: StoreItem) -> str:
        """Return a compact diagnostic label without participating in selection."""
        if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY:
            return "identify-staff"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
            return "identify"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
            return "star-identify"
        if item.is_recall_scroll:
            return "recall"
        if item.is_teleport_scroll:
            return "teleport"
        if item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            return "cure-critical"
        if item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED:
            return "speed"
        if item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING:
            return "healing"
        if item.is_treasure_detection_scroll:
            return "treasure-detection"
        if item.is_digging_tool:
            return "digging-tool"
        if item.is_ammo:
            return "ammo"
        if item.is_lantern:
            return "lantern"
        if item.is_oil:
            return "oil"
        if item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
            return "torch"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_REMOVE_CURSE:
            return "remove-curse"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_REMOVE_CURSE:
            return "star-remove-curse"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_HIT:
            return "enchant-tohit"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_DAM:
            return "enchant-todam"
        if item.tval == TVAL_FOOD:
            return "food"
        if item.tval in {TVAL_WAND, TVAL_STAFF}:
            return "device"
        return "other"

    @staticmethod
    def _shop_candidate_diagnostics(
        item: StoreItem, category: str
    ) -> dict[str, object]:
        candidate: dict[str, object] = {
            "category": category,
            "name": item.name,
            "letter": item.letter,
            "price": item.price,
            "count": item.count,
        }
        if item.tval in {TVAL_WAND, TVAL_STAFF}:
            candidate["charges"] = item.charges
        return candidate

    def _record_shop_selector_diagnostics(
        self, snapshot: Snapshot, key: str
    ) -> None:
        """Capture selector evidence after the action; gameplay never consumes it."""
        store = snapshot.store
        diagnostic_snapshot = snapshot
        if store is None and self._shop_observation is not None:
            store = self._shop_observation[0]
            diagnostic_snapshot = replace(snapshot, store=store)

        wanted_item = (
            self._next_purchase_unreserved(diagnostic_snapshot)
            if store is not None else None
        )
        wanted = None
        if wanted_item is not None:
            wanted = self._shop_candidate_diagnostics(
                wanted_item, self._purchase_diagnostic_category(wanted_item)
            )

        selected_item = None
        if (
            store is not None
            and store.store_type != STORE_HOME
            and key.startswith(BUY_KEY)
            and len(key) > 1
        ):
            selected_item = next(
                (item for item in store.items if item.letter == key[1]), None
            )

        considered_item = selected_item or wanted_item
        considered = None
        rejection_reason = (
            "observed-page-nothing-wanted"
            if store is not None else "no-store-page-observed"
        )
        if considered_item is not None:
            considered = self._shop_candidate_diagnostics(
                considered_item,
                self._purchase_diagnostic_category(considered_item),
            )
            if selected_item is not None:
                rejection_reason = "selected"
            elif wanted_item is not None:
                reserve = self._fundraising_kit_reserve(diagnostic_snapshot)
                quantity = self._purchase_quantity(diagnostic_snapshot, wanted_item)
                reserved = (
                    not wanted_item.is_digging_tool
                    and not wanted_item.is_treasure_detection_scroll
                    and not (
                        self._opening_q34_torch_shortage(snapshot) > 0
                        and wanted_item.tval == TVAL_LITE
                        and wanted_item.sval == SV_LITE_TORCH
                    )
                    and reserve > 0
                    and snapshot.player.gold
                    - wanted_item.price * quantity
                    < reserve
                )
                rejection_reason = "reserved" if reserved else "preempted"

        composition_refusal = self._shop_selector_diagnostics.get(
            "composition_refusal"
        )
        composition_refusal_sequence = self._shop_selector_diagnostics.get(
            "composition_refusal_sequence"
        )
        self._shop_selector_diagnostics = {
            "winning_rung": self.last_reason,
            "gold": snapshot.player.gold,
            "wanted_purchase": wanted,
            "considered_candidate": considered,
            "rejection_reason": rejection_reason,
        }
        if (
            composition_refusal is not None
            and composition_refusal_sequence == self._decision_sequence
        ):
            self._shop_selector_diagnostics["composition_refusal"] = (
                composition_refusal
            )
            self._shop_selector_diagnostics["composition_refusal_sequence"] = (
                composition_refusal_sequence
            )
        invariant_defect = getattr(
            self, "_town_progress_invariant_defect", {}
        )
        if invariant_defect:
            self._shop_selector_diagnostics["town_progress_invariant"] = dict(
                invariant_defect
            )
        withdrawal_defect = getattr(
            self, "_withdrawal_unfulfilled_defect", {}
        )
        if withdrawal_defect:
            self._shop_selector_diagnostics["withdrawal_unfulfilled"] = dict(
                withdrawal_defect
            )

    def _black_market_optional_purchase(
        self, snapshot: Snapshot
    ) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_BLACK:
            return None
        optional = [
            item
            for item in store.items
            if (
                (
                    item.tval == TVAL_POTION
                    and item.sval in {SV_POTION_SPEED, SV_POTION_HEALING}
                )
                or (
                    item.tval == TVAL_WAND
                    and item.sval == SV_WAND_STONE_TO_MUD
                    and item.charges > 0
                    and not self._has_charged_stone_to_mud(snapshot)
                )
            )
            and item.count > 0
            and item.price <= snapshot.player.gold
        ]
        if not optional:
            return None

        def held(item: StoreItem) -> int:
            if item.tval == TVAL_WAND:
                return int(self._has_charged_stone_to_mud(snapshot))
            return self._count_potion(snapshot, item.sval)

        def kind_rank(item: StoreItem) -> int:
            if item.tval == TVAL_WAND:
                return 2
            return int(item.sval != SV_POTION_SPEED)

        return min(optional, key=lambda item: (held(item), kind_rank(item)))

    def _live_purchase_need(
        self, snapshot: Snapshot, category: str,
    ) -> NeedSpec | None:
        return next(
            (
                need for need in self._town_need_registry()
                if need.category == category and need.produces(snapshot)
            ),
            None,
        )

    def _mandatory_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        """Select an affordable ware that closes a departure requirement."""
        store = snapshot.store
        if store is None:
            return None
        strategy = self._carry_procurement_strategy(snapshot)
        if strategy is not None:
            carry = self._quest_carry_purchase(snapshot, strategy)
            if carry is not None:
                return carry
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        if (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and ledger["food"].count < ledger["food"].required_departure
        ):
            mana_food = self._mana_food_purchase(snapshot)
            if mana_food is not None:
                return mana_food
        predicates = (
            ("recall", lambda item: item.is_recall_scroll),
            (
                "food",
                lambda item: snapshot.player.food_type != FOOD_TYPE_MANA
                and item.tval == TVAL_FOOD
                and item.sval >= FOOD_MIN_SVAL,
            ),
            ("light", lambda item: item.is_lantern),
            ("oil", lambda item: item.is_oil),
            ("teleport", lambda item: item.is_teleport_scroll),
            (
                "cure",
                lambda item: item.tval == TVAL_POTION
                and item.sval == SV_POTION_CURE_CRITICAL,
            ),
        )
        for kind, matches in predicates:
            if kind == "light":
                if self._planned_depth() < 2 or self._owns_lantern(snapshot):
                    continue
            else:
                status = ledger[kind]
                if status.count >= status.required_departure:
                    continue
            candidate = next(
                (
                    item
                    for item in store.items
                    if item.count > 0
                    and item.price <= snapshot.player.gold
                    and matches(item)
                ),
                None,
            )
            if candidate is not None:
                return candidate
        return None

    def _next_purchase_unreserved(self, snapshot: Snapshot) -> StoreItem | None:
        """The next thing to buy from the current store, or None when done."""
        store = snapshot.store
        if store is None:
            return None
        gold = snapshot.player.gold
        if snapshot.player.class_id < 0:
            if not self._owns_lantern(snapshot):
                lantern = next(
                    (it for it in store.items if it.is_lantern and it.price <= gold),
                    None,
                )
                if lantern is not None:
                    return lantern
            if self._oil_below_departure_target(snapshot):
                oil = next(
                    (it for it in store.items if it.is_oil and it.price <= gold),
                    None,
                )
                if oil is not None:
                    return oil
            if (
                snapshot.player.food_type == FOOD_TYPE_RATION
                and self._needs_food_restock(snapshot)
            ):
                food = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_FOOD
                        and it.sval >= FOOD_MIN_SVAL
                        and it.price <= gold
                    ),
                    None,
                )
                if food is not None:
                    return food
            return None
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if (
                not self._has_withdrawable_digging_tool(snapshot)
                or self._digger_buy_fallback_available(snapshot)
            ):
                digger = next(
                    (it for it in store.items if it.is_digging_tool and it.price <= gold),
                    None,
                )
                if digger is not None:
                    return digger
            if self._count_treasure_detection_scrolls(snapshot) < 1:
                detection = next(
                    (
                        it
                        for it in store.items
                        if it.is_treasure_detection_scroll and it.price <= gold
                    ),
                    None,
                )
                if detection is not None:
                    return detection
            if not self._food_ready(snapshot):
                food = None
                if snapshot.player.food_type == FOOD_TYPE_MANA:
                    food = self._mana_food_purchase(snapshot)
                elif snapshot.player.food_type == FOOD_TYPE_RATION:
                    food = next(
                        (
                            it
                            for it in store.items
                            if it.tval == TVAL_FOOD
                            and it.sval >= FOOD_MIN_SVAL
                            and it.price <= gold
                        ),
                        None,
                    )
                if food is not None:
                    return food
            scrolls_needed = (
                self._mining_detection_scroll_target(snapshot)
                + DETECTION_SCROLL_BUFFER
            )
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                detection_scroll = next(
                    (
                        it
                        for it in store.items
                        if it.is_treasure_detection_scroll and it.price <= gold
                    ),
                    None,
                )
                if detection_scroll is not None:
                    return detection_scroll
            if (
                not self._has_withdrawable_digging_tool(snapshot)
                or self._digger_buy_fallback_available(snapshot)
            ):
                digger = next(
                    (it for it in store.items if it.is_digging_tool and it.price <= gold),
                    None,
                )
                if digger is not None:
                    return digger
            if not self._fundraising_light_ready(snapshot):
                lantern = next(
                    (it for it in store.items if it.is_lantern and it.price <= gold),
                    None,
                )
                if lantern is not None:
                    return lantern
            if self._oil_below_departure_target(snapshot):
                oil = next(
                    (it for it in store.items if it.is_oil and it.price <= gold),
                    None,
                )
                if oil is not None:
                    return oil
            if (
                self._planned_depth() <= TORCH_THROW_MAX_DEPTH
                and self._matching_ammo(snapshot) is None
                and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
            ):
                # Shallow mining trips carry throwing torches (user directive);
                # this ranks BELOW the whole kit so it can never starve it.
                torch = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_LITE
                        and it.sval == SV_LITE_TORCH
                        and it.price <= gold
                    ),
                    None,
                )
                if torch is not None:
                    return torch
            if (
                self._withdrawable_digging_tool_count(snapshot) < 2
                or self._digger_buy_fallback_available(snapshot)
            ):
                digger = next(
                    (
                        item
                        for item in store.items
                        if item.is_digging_tool and item.price <= gold
                    ),
                    None,
                )
                if digger is not None:
                    return digger
            return None

        mandatory = self._mandatory_purchase(snapshot)
        if mandatory is not None:
            return mandatory

        if self._identification_need is not None:
            full = self._identification_need == "full"
            if self._find_identification_source(
                snapshot,
                full=full,
                reliable_only=self._identification_requires_reliable_source(snapshot),
            ) is None:
                # No identify source in hand yet: buy one here if this store sells
                # it. If it does not, fall through rather than abandoning the trip.
                wanted_sval = SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY
                scroll = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_SCROLL
                        and it.sval == wanted_sval
                        and it.price <= gold
                    ),
                    None,
                )
                if scroll is not None:
                    return scroll
            # We either already hold an identify source or this store does not
            # stock the scroll. Do NOT return here: fall through to the departure
            # supplies below so a single visit still buys the recall/teleport/cure
            # items the store sells. Returning early marked the Alchemist
            # 'attempted' after an identify errand, so the bot never bought the
            # teleport scrolls it also sells and stranded itself wandering town.

        restore = self._restore_potion_purchase(snapshot)
        if restore is not None:
            return restore
        strategy = self._carry_procurement_strategy(snapshot)
        if strategy is not None:
            force = strategy.required_force
            carry = self._quest_carry_purchase(snapshot, strategy)
            if carry is not None:
                return carry
            if self._exact_potion_count(snapshot, SV_POTION_SPEED) < int(force.get("speed_potions", 0)):
                speed = next((it for it in store.items if it.tval == TVAL_POTION
                              and it.sval == SV_POTION_SPEED and it.price <= gold), None)
                if speed is not None:
                    return speed
            healing = self._exact_potion_count(snapshot, SV_POTION_HEALING)
            if healing < int(force.get("heal_potions", 0)):
                heal = next((it for it in store.items if it.tval == TVAL_POTION
                             and it.sval == SV_POTION_HEALING
                             and it.price <= gold), None)
                if heal is not None:
                    return heal
        black_market_optional = self._black_market_optional_purchase(snapshot)
        if black_market_optional is not None:
            return black_market_optional
        if not self._recall_ready(snapshot):
            item = next(
                (it for it in store.items if it.is_recall_scroll and it.price <= gold),
                None,
            )
            if item is not None:
                return item
        if (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and not self._food_ready(snapshot)
        ):
            device = self._mana_food_purchase(snapshot)
            if device is not None:
                return device
        if (
            snapshot.player.food_type == FOOD_TYPE_RATION
            and self._needs_food_restock(snapshot)
        ):
            food = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_FOOD
                    and it.sval >= FOOD_MIN_SVAL
                    and it.price <= gold
                ),
                None,
            )
            if food is not None:
                return food
        if not self._owns_lantern(snapshot):
            lantern = next(
                (it for it in store.items if it.is_lantern and it.price <= gold),
                None,
            )
            if lantern is not None:
                return lantern
        if self._oil_below_departure_target(snapshot):
            oil = next(
                (it for it in store.items if it.is_oil and it.price <= gold),
                None,
            )
            if oil is not None:
                return oil
        if (
            self._planned_depth() <= TORCH_THROW_MAX_DEPTH
            and self._matching_ammo(snapshot) is None
            and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
        ):
            torch = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_LITE
                    and it.sval == SV_LITE_TORCH
                    and it.price <= gold
                ),
                None,
            )
            if torch is not None:
                return torch
        if not self._teleport_ready(snapshot):
            teleport = next(
                (it for it in store.items if it.is_teleport_scroll and it.price <= gold),
                None,
            )
            if teleport is not None:
                return teleport
        if not self._cure_critical_ready(snapshot):
            cure = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_POTION
                    and it.sval == SV_POTION_CURE_CRITICAL
                    and it.price <= gold
                ),
                None,
            )
            if cure is not None:
                return cure
        launcher = self._equipped_launcher(snapshot)
        if (
            launcher is not None
            and self._count_matching_ammo(snapshot) < AMMO_CARRY_TARGET
        ):
            ammo = next(
                (
                    it
                    for it in store.items
                    if it.tval == launcher.ammo_tval and it.price <= gold
                ),
                None,
            )
            if ammo is not None:
                return ammo
        if not self._identify_staff_ready(snapshot):
            identify = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_STAFF
                    and it.sval == SV_STAFF_IDENTIFY
                    and it.price <= gold
                ),
                None,
            )
            if identify is not None:
                return identify
        if (
            self._has_normal_remove_curse_target(snapshot)
            and self._find_remove_curse_scroll(snapshot) is None
        ):
            remove_curse = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_SCROLL
                    and it.sval in {SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE}
                    and it.price <= gold
                ),
                None,
            )
            if remove_curse is not None:
                return remove_curse
        star_remove_curse = self._affordable_star_remove_curse(snapshot)
        if star_remove_curse is not None:
            return star_remove_curse
        launcher_enchant = self._launcher_enchant_purchase(snapshot)
        if launcher_enchant is not None:
            return launcher_enchant
        return None

    def _purchase_quantity(self, snapshot: Snapshot, item: StoreItem) -> int:
        """Buy this ware's complete shortage in one transaction."""
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        strategy = (
            self._carry_procurement_strategy(snapshot)
            or self._quest_strategy_for_errand_or_floor(snapshot)
        )
        quest_needed = 0
        if strategy is not None:
            target = self._quest_carry_target_for_item(
                snapshot, item, strategy.required_force
            )
            if target is not None:
                _, current, required = target
                quest_needed = required - current
        if item.is_recall_scroll:
            needed = ledger["recall"].required_departure - ledger["recall"].count
        elif item.tval == TVAL_FOOD:
            needed = ledger["food"].required_departure - ledger["food"].count
        elif (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and item.tval in {TVAL_WAND, TVAL_STAFF}
        ):
            charge_needed = max(0, ledger["food"].required_departure - ledger["food"].count)
            device_needed = max(
                0, MANA_FOOD_DEVICE_TARGET - self._count_mana_food_devices(snapshot)
            )
            per_device = max(1, item.pval)
            needed = max(
                device_needed, (charge_needed + per_device - 1) // per_device
            )
        elif item.is_oil:
            needed = ledger["oil"].required_departure - ledger["oil"].count
        elif item.is_teleport_scroll:
            needed = ledger["teleport"].required_departure - ledger["teleport"].count
        elif item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            needed = ledger["cure"].required_departure - ledger["cure"].count
        elif item.is_treasure_detection_scroll:
            target = (
                self._mining_detection_scroll_target(snapshot)
                + DETECTION_SCROLL_BUFFER
            )
            needed = target - self._count_treasure_detection_scrolls(snapshot)
        elif item.is_ammo:
            needed = AMMO_CARRY_TARGET - self._count_matching_ammo(snapshot)
        elif item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
            target = TORCH_THROW_TARGET
            if strategy is not None:
                target = max(target, int(
                    strategy.required_force.get("throwing_items", {}).get("lit_torch", 0)
                ))
            needed = target - self._count_throwing_torches(snapshot)
        elif item.tval == TVAL_SCROLL and item.sval in {
            SV_SCROLL_IDENTIFY,
            SV_SCROLL_STAR_IDENTIFY,
        }:
            # Cover every outstanding item of this tier in one purchase (capped,
            # so one unusually large Home batch cannot empty the wallet).
            full = item.sval == SV_SCROLL_STAR_IDENTIFY
            needed = min(
                IDENTIFY_PURCHASE_MAX,
                self._outstanding_identification_count(snapshot, full=full),
            )
        elif item.tval == TVAL_POTION and item.sval in {
            SV_POTION_SPEED,
            SV_POTION_HEALING,
        }:
            # Re-evaluate after every bottle so the two capped field stocks stay
            # balanced and the other type can use the remaining gold.
            needed = 1
        else:
            needed = 1
        needed = max(needed, quest_needed)
        affordable = snapshot.player.gold // item.price if item.price > 0 else item.count
        return max(1, min(item.count, affordable, max(1, needed)))

    @staticmethod
    def _store_accepts_sale(store_type: int, item: InventoryItem) -> bool:
        """Conservative tval gate mirroring Hengband's store_will_buy switch."""
        if store_type in {STORE_HOME, STORE_BLACK}:
            return True
        if (
            store_type == STORE_WEAPON
            and item.tval == TVAL_HAFTED
            and item.sval == SV_HAFTED_WIZSTAFF
        ):
            return False
        return item.tval in STORE_ACCEPTED_TVALS.get(store_type, frozenset())

    def _store_sell_key(
        self,
        snapshot: Snapshot,
        item: InventoryItem,
        reason: str,
        *,
        rejected_reason: str = "shop:unsellable-leave",
    ) -> str:
        store = snapshot.store
        current = next(
            (
                candidate for candidate in snapshot.inventory
                if candidate.slot == item.slot
                and self._item_signature(candidate) == self._item_signature(item)
            ),
            None,
        )
        if current is None:
            # A sale candidate can outlive the inventory board that supplied
            # its letter after an earlier sale removes or reorders the pack.
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        item = current
        if self._sale_retains_digging_tool(snapshot, item):
            self._batch_sell_pending = None
            self.last_reason = "shop:retain-standing-digging-tool"
            return LEAVE_STORE_KEY
        if store is None or not self._store_accepts_sale(store.store_type, item):
            # 'd' can be rejected before opening an item prompt.  Never attach
            # Return/yes tail keys unless the C++ store tval gate says the prompt
            # exists; otherwise those keys execute raw in the store command loop.
            self._unsellable_items.add(self._item_signature(item))
            if store is not None:
                self._set_town_store_attempted(store.store_type, snapshot.turn, "sell-no-item")
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        if (
            self._item_signature(item) in self._unsellable_items
            or store.store_type in self._store_sale_refused
        ):
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY

        item_signature = self._item_signature(item)
        attempts = 1
        if self._store_sell_attempt is not None:
            previous_signature, previous_count, previous_attempts = (
                self._store_sell_attempt
            )
            if previous_signature == item_signature and item.count >= previous_count:
                attempts = previous_attempts + 1
        self._store_sell_attempt = (item_signature, item.count, attempts)

        pack_state = tuple(
            (it.slot, self._item_signature(it), it.count, it.charges)
            for it in snapshot.inventory
        )
        store_state = tuple(
            (it.letter, it.name, it.tval, it.sval, it.count, it.price)
            for it in store.items
        )
        sig = (
            snapshot.turn,
            store.store_type,
            pack_state,
            store_state,
            snapshot.player.gold,
        )
        if sig == self._last_sell_sig:
            self._store_sell_stuck_count += 1
        else:
            self._last_sell_sig = sig
            self._store_sell_stuck_count = 0
        # One already-emitted attempt followed by a byte-distinct snapshot whose
        # store/pack/gold state is unchanged proves the sale was rejected. Leave
        # now instead of
        # re-emitting the multi-key sell — a second emit lands its trailing keys
        # in the store command loop after the "no room" message ("そのコマンドは
        # 店の中では使えません"), the desync the user observed.
        if self._store_sell_stuck_count >= 1:
            self._unsellable_items.add(self._item_signature(item))
            self._set_town_store_attempted(store.store_type, snapshot.turn, "sell-stuck")
            # The store accepts this item's type (it passed _store_accepts_sale)
            # yet rejected the sale: it is FULL. Latch it so the withdraw/route
            # logic stops feeding more spares to a store with no room.
            self._store_sale_refused.add(store.store_type)
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        # Three cross-snapshot attempts are enough to prove that the prompt
        # chain is not completing; continuing risks leaking tail keys.
        if attempts >= SELL_ATTEMPT_LIMIT:
            self._unsellable_items.add(item_signature)
            self._set_town_store_attempted(store.store_type, snapshot.turn, "sell-attempt-limit")
            self._store_sale_refused.add(store.store_type)
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self._store_sell_attempt = None
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        # Even specialized disposal paths use the same inscription-observed
        # transaction; this helper never composes an item-letter sale key.
        key = self._batch_sell_key(snapshot, [item])
        if key is None:
            self.last_reason = "shop:sale-requires-inscription-leave"
            return LEAVE_STORE_KEY
        return key

    def _current_store_sale_candidates(self, snapshot: Snapshot) -> list[InventoryItem]:
        """Enumerate sale finders in normal shop priority, without mutating policy."""
        store = snapshot.store
        if store is None:
            return []
        remaining = list(snapshot.inventory)
        result: list[InventoryItem] = []
        while remaining:
            view = replace(snapshot, inventory=remaining)
            sale = self._find_book_sale(view, store.store_type)
            if sale is None and store.store_type == STORE_ALCHEMIST:
                sale = self._find_low_level_sale(view)
            if sale is None and store.store_type == STORE_MAGIC:
                sale = self._find_device_sale(view)
            if sale is None and store.store_type == STORE_WEAPON:
                sale = self._find_weapon_sale(view)
            if sale is None and store.store_type == STORE_GENERAL:
                if snapshot.player.food_type == FOOD_TYPE_MANA:
                    sale = self._first_item(
                        view,
                        lambda item: item.tval == TVAL_FOOD
                        and self._retention_surplus(snapshot, item) > 0
                        and self._item_signature(item) not in self._unsellable_items,
                    )
                if sale is None:
                    sale = self._find_light_sale(view)
            if sale is None:
                break
            if not self._equipment_transaction_owns_item(sale):
                result.append(sale)
            remaining = [item for item in remaining if item.slot != sale.slot]
        if not result:
            organization = self._find_town_organization_surplus(snapshot)
            if (
                organization is not None
                and self._next_purchase(snapshot) is None
                and self._store_accepts_sale(store.store_type, organization)
                and store.store_type
                == self._town_organization_sale_store(snapshot, organization)
            ):
                if not self._equipment_transaction_owns_item(organization):
                    result.append(organization)
        return result

    def _batch_sell_key(
        self,
        snapshot: Snapshot,
        candidates: list[InventoryItem] | None = None,
    ) -> str | None:
        """Advance the mandatory inscription-bound sale transaction."""
        store = snapshot.store
        if store is None:
            return None

        pending = self._batch_sell_pending
        if pending is not None and pending["store_type"] == store.store_type:
            entries = pending["entries"]
            if pending["phase"] == "await-inscription":
                def observed_tagged(entry):
                    return next((
                        current for current in snapshot.inventory
                        if self._sale_item_identity(current) == entry["signature"]
                        and self._item_has_sale_tag(current, str(entry["tag"]))
                    ), None)
                observed = all(
                    observed_tagged(entry) is not None
                    for entry in entries
                )
                if not observed:
                    for entry in entries:
                        self._unsellable_items.add(entry["signature"])
                    self._store_sale_refused.add(store.store_type)
                    self._batch_sell_pending = None
                    self.last_reason = "shop:sale-inscription-unobserved-leave"
                    return LEAVE_STORE_KEY
                if any(
                    self._sale_retains_digging_tool(snapshot, observed_tagged(entry))
                    for entry in entries
                ):
                    self._batch_sell_pending = None
                    self.last_reason = "shop:retain-standing-digging-tool"
                    return LEAVE_STORE_KEY
                # Inscribing can merge identical pack items.  Compose each
                # prompt chain from the item in this observed snapshot, not
                # from the pre-inscription candidate cached in the plan.
                for entry in entries:
                    item = observed_tagged(entry)
                    if item is None:
                        continue
                    if not self._sale_tag_is_unique(
                        snapshot, item, str(entry["tag"])
                    ):
                        self._unsellable_items.add(entry["signature"])
                        self._store_sale_refused.add(store.store_type)
                        self._batch_sell_pending = None
                        self.last_reason = "shop:sale-inscription-ambiguous-leave"
                        return LEAVE_STORE_KEY
                    sale = self._batch_sale_entry(snapshot, item, entry["tag"])
                    if sale is None:
                        self._batch_sell_pending = None
                        return ""
                    entry.update(sale)
                pending["phase"] = "await-sale"
                self.last_reason = "shop:one-shot-sale-compose"
                return "".join(entry["sell"] for entry in entries)

            # Exactly one post-sale snapshot verifies every tagged item.  Any
            # survivor advances the ordinary attempt record and is then handled
            # by a fresh inscription-bound transaction if policy still wants it.
            confirmed = snapshot.player.gold > pending["before_gold"]
            for entry in entries:
                survivor = next((
                    current for current in snapshot.inventory
                    if self._sale_item_identity(current) == entry["signature"]
                    and self._item_has_sale_tag(current, str(entry["tag"]))
                ), None)
                expected = entry["count"] - entry["quantity"]
                if survivor is None or survivor.count <= expected:
                    confirmed = True
                if survivor is not None and survivor.count > expected:
                    attempts = 1
                    if self._store_sell_attempt is not None:
                        sig, previous_count, previous_attempts = self._store_sell_attempt
                        if sig == entry["signature"] and survivor.count >= previous_count:
                            attempts = previous_attempts + 1
                    self._store_sell_attempt = (entry["signature"], survivor.count, attempts)
            self._batch_sell_pending = None
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            if confirmed and self._store_visit is not None:
                self._store_visit.operation_posted = False
                self._store_visit.operation_effect_observed = True
            if confirmed:
                self._town_visit_sale_signatures.update(
                    (int(entry["signature"][1]), int(entry["signature"][2]))
                    for entry in entries
                )
            elif not confirmed:
                self._close_store_visit("one-shot-sale-unconfirmed")
            # A completed batch can compact every following inventory slot.
            # Leave before starting another transaction from a snapshot that
            # may still reflect the pre-sale inventory layout.
            self.last_reason = "shop:one-shot-sale-observed"
            return LEAVE_STORE_KEY

        candidates = (
            self._current_store_sale_candidates(snapshot)
            if candidates is None
            else candidates
        )
        if not candidates:
            return None

        entries: list[dict[str, object]] = []
        inscribe_parts: list[str] = []
        for item in candidates[:1]:
            if self._sale_retains_digging_tool(snapshot, item):
                self.last_reason = "shop:retain-standing-digging-tool"
                return LEAVE_STORE_KEY
            digit = self._unique_sale_tag(snapshot, item)
            if digit is None:
                self._unsellable_items.add(self._item_signature(item))
                self._store_sale_refused.add(store.store_type)
                self._batch_sell_pending = None
                self.last_reason = "shop:sale-inscription-ambiguous-leave"
                return LEAVE_STORE_KEY
            exact_tag = f"@{digit}"
            has_exact_tag = self._item_has_sale_tag(item, digit)
            # Other @ inscriptions may be command bindings owned outside sale
            # policy.  Never overwrite them merely to make a batch possible.
            has_numeric_tag = any(
                self._item_has_sale_tag(item, value)
                for value in "0123456789"
            )
            if "@" in item.inscription and not has_exact_tag and not has_numeric_tag:
                continue
            if not has_exact_tag:
                inscribe_parts.append("{" + item.slot + exact_tag + "\r")
            sale = self._batch_sale_entry(snapshot, item, digit)
            if sale is None:
                self._batch_sell_pending = None
                return ""
            entries.append({
                "signature": self._sale_item_identity(item),
                "tag": digit,
                **sale,
            })
        if not entries:
            self.last_reason = "shop:sale-inscription-unavailable-leave"
            return LEAVE_STORE_KEY
        phase = "await-inscription" if inscribe_parts else "await-sale"
        self._batch_sell_pending = {
            "store_type": store.store_type,
            "phase": phase,
            "entries": entries,
            "before_gold": snapshot.player.gold,
            "wait_count": 0,
        }
        self.last_reason = (
            "shop:batch-inscribe"
            if inscribe_parts
            else "shop:one-shot-sale-compose"
        )
        return "".join(inscribe_parts) if inscribe_parts else "".join(
            entry["sell"] for entry in entries
        )

    def _sale_tag_is_unique(
        self, snapshot: Snapshot, intended: InventoryItem, tag: str
    ) -> bool:
        """Match Hengband's numeric-tag resolver over store-eligible pack items."""
        matches = [
            item for item in snapshot.inventory
            if self._store_accepts_sale(snapshot.store.store_type, item)
            and self._item_has_sale_tag(item, tag)
        ]
        return (
            len(matches) == 1
            and self._sale_item_identity(matches[0]) == self._sale_item_identity(intended)
        )

    @staticmethod
    def _sale_inscription_text(item: InventoryItem) -> str:
        """Return the inscription even when the emitter only decorates ``name``."""
        return item.inscription or item.name

    @classmethod
    def _item_has_sale_tag(cls, item: InventoryItem, tag: str) -> bool:
        return re.search(
            rf"@{re.escape(tag)}(?!\d)", cls._sale_inscription_text(item)
        ) is not None

    @staticmethod
    def _sale_item_identity(item: InventoryItem) -> tuple[str, int, int]:
        # Live snapshots currently expose inscription=None while appending the
        # inscription to the display name.  Inscribing must not change the
        # identity owned by the pending two-stage sale.
        name = re.sub(r"\s+\{[^{}]*\}\s*$", "", item.name)
        return (name, item.tval, item.sval)

    def _batch_sale_entry(
        self, snapshot: Snapshot, item: InventoryItem, tag: str
    ) -> dict[str, object] | None:
        """Classify one tagged sale from the snapshot being composed."""
        signature = self._sale_item_identity(item)
        item = next((
            current for current in snapshot.inventory
            if self._sale_item_identity(current) == signature
            and (
                current.inscription == item.inscription
                or (
                    not current.inscription
                    and self._item_has_sale_tag(current, tag)
                )
            )
        ), None)
        if item is None:
            self.last_reason = "shop:batch-sale-signature-unobserved"
            return None
        surplus = self._retention_surplus(snapshot, item)
        quantity = item.count if surplus <= 0 else min(item.count, surplus)
        amount = "99" if quantity == item.count else str(quantity)
        # The store always asks for the offered-price confirmation.  A stack
        # first asks for a quantity; a singleton does not.
        quantity_answer = "" if item.count == 1 else amount + "\r"
        return {
            "count": item.count,
            "quantity": quantity,
            "sell": SELL_KEY + tag + quantity_answer + "y",
        }

    def _shop(self, snapshot: Snapshot) -> str:
        store = snapshot.store
        self._observe_star_remove_curse_reserve_inflight(snapshot)
        if store is None:
            self.last_reason = "shop:invalid"
            return LEAVE_STORE_KEY
        if (
            store.store_type == STORE_TEMPLE
            and self._star_remove_curse_reserve_buy_inflight is not None
        ):
            self.last_reason = "shop:await-star-remove-curse-purchase"
            return LEAVE_STORE_KEY
        if (
            store.store_type == STORE_MAGIC
            and not self._last_snapshot_was_store
            and not self._home_identify_staff_sale_pending
        ):
            self._home_identify_staff_sold_this_magic_visit = False

        # A hungry character with no edible pack item has exactly one town job.
        # Do not sell gear or buy optional supplies while starvation advances.
        if snapshot.player.hungry and self._find_edible(snapshot) is None:
            if (
                snapshot.player.food_type == FOOD_TYPE_MANA
                and self._mana_survival_device_price is not None
                and snapshot.player.gold >= self._mana_survival_device_price
            ):
                self._town_store_attempted.pop(STORE_MAGIC, None)
            if (
                snapshot.player.food_type == FOOD_TYPE_MANA
                and self._mana_survival_device_price is not None
                and snapshot.player.gold < self._mana_survival_device_price
                and store.store_type in {STORE_ALCHEMIST, STORE_WEAPON}
            ):
                sale = self._mana_survival_sale_candidate(
                    snapshot, store.store_type
                )
                if sale is not None:
                    return self._store_sell_key(
                        snapshot, sale, "survival:mana-sell-to-afford"
                    )
            food_store = (
                STORE_MAGIC
                if snapshot.player.food_type == FOOD_TYPE_MANA
                else STORE_GENERAL
            )
            if store.store_type != food_store:
                self.last_reason = "survival:leave-wrong-store"
                return LEAVE_STORE_KEY
            if snapshot.player.food_type == FOOD_TYPE_MANA:
                self._home_procurement_fallthrough_equivalence = (
                    "device:is-wand-staff"
                )
                if not self._home_knowledge_current:
                    self._home_procurement_probe = (-1, -1)
                    if not self._current_town_has_home(snapshot):
                        self._home_procurement_probe = None
                        self._home_procurement_fallthrough = "town-without-home"
                    elif (
                        not self._home_available(snapshot)
                        or not self._ensure_home_visit_request(snapshot)
                        or self._shopping_approach_step(snapshot, STORE_HOME) is None
                    ):
                        self._home_procurement_probe = None
                        self.last_reason = "survival:mana-home-route-defect"
                        return LEAVE_STORE_KEY
                    else:
                        self.last_reason = "survival:mana-home-scan-before-purchase"
                        return LEAVE_STORE_KEY
                home_food = self._home_mana_food_candidate()
                if home_food is not None:
                    self._home_pending_item = self._item_signature(home_food)
                    self._home_pending_quantity = 1
                    self._home_procurement_probe = (-1, -1)
                    self.last_reason = "survival:mana-home-before-purchase"
                    return LEAVE_STORE_KEY
                food_item = self._mana_food_purchase(snapshot)
            elif snapshot.player.food_type == FOOD_TYPE_RATION:
                food_item = next(
                    (
                        it for it in store.items
                        if it.tval == TVAL_FOOD
                        and it.sval >= FOOD_MIN_SVAL
                        and it.price <= snapshot.player.gold
                    ),
                    None,
                )
                if food_item is not None:
                    home_gate = self._purchase_has_fresh_home_absence(
                        snapshot, food_item
                    )
                    if home_gate is ProcurementHomeGate.BLOCKED:
                        self._publish_purchase_home_block()
                        return WAIT_KEY
                    if home_gate is ProcurementHomeGate.HOME_FIRST:
                        self._rearm_town_store_for_new_work(
                            STORE_HOME, release_visit_bound=True
                        )
                        self.last_reason = "survival:ration-home-before-purchase"
                        return LEAVE_STORE_KEY
            else:
                food_item = None
            if food_item is not None:
                quantity = self._purchase_quantity(snapshot, food_item)
                suffix = (
                    f"{quantity}\r\r"
                    if food_item.count > 1
                    else BUY_CONFIRM_SUFFIX
                )
                self.last_reason = "survival:buy-food"
                return BUY_KEY + food_item.letter + suffix
            self._set_town_store_attempted(store.store_type, snapshot.turn, "survival-food-unavailable")
            if snapshot.player.food_type == FOOD_TYPE_MANA:
                prices = [
                    item.price for item in store.items
                    if item.tval in {TVAL_WAND, TVAL_STAFF}
                ]
                self._mana_survival_device_price = min(prices) if prices else None
                if self._mana_survival_device_price is not None:
                    for sale_store in (STORE_ALCHEMIST, STORE_WEAPON):
                        if self._mana_survival_sale_candidate(snapshot, sale_store):
                            self._town_store_attempted.pop(sale_store, None)
                            self.last_reason = "survival:mana-sell-to-afford"
                            return LEAVE_STORE_KEY
                self.last_reason = "town:blocked:survival-mana-no-charges"
                return WAIT_KEY
            self.last_reason = "survival:no-affordable-food"
            return LEAVE_STORE_KEY

        suppress_random_teleport = self._town_random_teleport_suppression_key(
            snapshot
        )
        if suppress_random_teleport is not None:
            return suppress_random_teleport

        if store.store_type == STORE_HOME:
            morivant_home_key = self._morivant_home_item_key(snapshot)
            if morivant_home_key is not None:
                return morivant_home_key
            reserve = next(
                (
                    item
                    for item in store.items
                    if item.tval == TVAL_SCROLL
                    and item.sval == SV_SCROLL_STAR_REMOVE_CURSE
                ),
                None,
            )
            if (
                reserve is not None
                and self._has_unremovable_curse_target(snapshot)
                and not self._recall_departure_shortage(snapshot)
            ):
                self._star_remove_curse_reserve_withdraw_pending = True
                self._home_pending_item = self._item_signature(reserve)
                self.last_reason = "home:queue-star-remove-curse-withdraw"
                return LEAVE_STORE_KEY
            # An active transaction session OWNS the Home visit: its town-side
            # dispatcher keeps walking back in while it has Home work, so a
            # disposal leave that preempts it just bounces the bot in and out of
            # Home (store snapshots reset the harness loop guard, so nothing
            # stops the bounce). Run the session first; when it completes or is
            # abandoned it returns None and the disposal leave proceeds.
            transaction_key = self._equipment_transaction_home_key(snapshot)
            if transaction_key is not None:
                return transaction_key
            quest_launcher = self._home_quest_launcher_key(snapshot)
            if quest_launcher is not None:
                return quest_launcher
            dominated_disposal = self._home_dominated_disposal_key(snapshot)
            if dominated_disposal is not None:
                return dominated_disposal
            disposal_key = self._home_disposal_home_key(snapshot)
            if disposal_key is not None:
                return disposal_key

        if (
            self._pending_disposal_item is not None
        ):
            target = self._pending_disposal(snapshot)
            if target is None:
                self._clear_pending_disposal()
                self.last_reason = "equipment:sale-complete"
                return LEAVE_STORE_KEY
            if store.store_type != self._dominated_disposal_store(target):
                return None
            key = self._store_sell_key(
                snapshot, target, "equipment:sell-dominated",
                rejected_reason="equipment:sale-refused",
            )
            if key == LEAVE_STORE_KEY:
                self._disposal_store_attempts.add(store.store_type)
            return key

        if self._home_disposal_pending is not None:
            signature, decision = self._home_disposal_pending
            target = self._home_disposal_inventory_item(snapshot)
            if (
                decision == "sell"
                and target is not None
                and target.known
                and store.store_type == self._home_disposal_store(signature)
            ):
                self._home_disposal_pending = None
                return self._store_sell_key(
                    snapshot, target, "home-disposal:sell-approved",
                    rejected_reason="home-disposal:sale-refused",
                )

        if store.store_type == STORE_HOME:
            rearm = self._home_rearm_key(snapshot)
            if rearm is not None:
                return rearm

            if self._home_atomic_withdraw_pending is not None:
                self.last_reason = "home:leave-after-one-operation"
                return LEAVE_STORE_KEY

            # Prefer owned Identify charges to buying another staff.  Once the
            # carried departure reserve is ready, drain legacy Home hoards one
            # staff at a time through the Magic shop.  Charged devices are not
            # Home-deposit candidates, so the withdrawn staff cannot bounce back.
            stored_identify = [
                item
                for item in store.items
                if item.tval == TVAL_STAFF
                and item.sval == SV_STAFF_IDENTIFY
                and item.charges > 0
            ]
            queued_withdrawals = set(self._home_pending_batch)
            queued_withdrawals.update(self._calibration_restore_signatures)
            if self._home_pending_item is not None:
                queued_withdrawals.add(self._home_pending_item)
            stored_identify = [
                item for item in stored_identify
                if self._item_signature(item) not in queued_withdrawals
            ]
            if (
                stored_identify
                and PACK_CAPACITY - len(snapshot.inventory)
                > max(HOME_BATCH_RESERVED_SLOTS, MIN_FREE_PACK_SLOTS)
            ):
                if not self._identify_staff_ready(snapshot):
                    candidate = max(
                        stored_identify,
                        key=lambda item: (
                            item.charges * max(1, item.count),
                            item.charges,
                            item.letter,
                        ),
                    )
                    reason = "home:withdraw-identify-staff-reserve"
                else:
                    candidate = min(
                        stored_identify,
                        key=lambda item: (
                            item.charges,
                            item.charges * max(1, item.count),
                            item.letter,
                        ),
                    )
                    self._home_identify_staff_sale_pending = True
                    self._rearm_town_store_for_new_work(STORE_MAGIC)
                    reason = "home:withdraw-surplus-identify-staff"
                signature = self._item_signature(candidate)
                self._home_pending_item = signature
                self._home_withdrawal_queued = True
                self.last_reason = reason.replace("withdraw", "queue-withdraw")
                return LEAVE_STORE_KEY

            additional_home_digger = next(
                (
                    item
                    for item in store.items
                    if item.is_digging_tool
                    and self._item_signature(item)
                    not in self._deferred_home_items
                ),
                None,
            )
            if (
                self._home_digger_withdraw_pending
                and self._has_digging_tool(snapshot)
                and (
                    self._digging_tool_count(snapshot) >= 2
                    or additional_home_digger is None
                )
            ):
                self._home_digger_withdraw_pending = False
                self.last_reason = "home:leave-with-digging-tool"
                return LEAVE_STORE_KEY

            # Resolve an equipment withdrawal before the fundraising fast-exit.
            # A failed quest-launcher command can leave _home_pending_item set
            # after its inflight retry is exhausted.  If mining supplies are
            # already complete, letting that branch leave first makes the town
            # planner request Home again forever without ever reaching this
            # cleanup.  Successful withdrawals also need to advance the Home
            # stop before the normal deposit pass can put the item back.
            if self._home_pending_item is not None:
                if self._pending_inventory_item(snapshot) is not None:
                    self._report_town_stop_pass(
                        snapshot, STORE_HOME, goal_satisfied=True
                    )
                    self.last_reason = "home:leave-with-item"
                    return LEAVE_STORE_KEY
                self._defer_home_item(
                    self._home_pending_item, "home-open-page-item-unavailable"
                )
                self._release_identification_source_reservation(
                    self._home_pending_item
                )
                self._home_pending_item = None
                self._home_pending_slot = None
                self._identification_need = None
                self._identification_candidate = None
                self._home_candidate_waiting = True
                self.last_reason = "home:withdraw-failed-deferred"
                return LEAVE_STORE_KEY

            standing_digger = self._queue_standing_home_digger(snapshot)
            if standing_digger is not None:
                return standing_digger

            # A partly identified ego/artifact/random-resistance item must not
            # ride into a deep mining floor where theft or inventory damage can
            # erase it before its hidden traits are known. Deposit it before the
            # mining-supply branch is allowed to leave Home.
            if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
                # Deep fundraising deliberately routes Home after a pack-full
                # return so loot and equipment candidates can be secured before
                # the next run.  The mining-kit fast-exit below used to preempt
                # the ordinary deposit owner even though the errand plan still
                # had a live Home deposit need, producing an endless
                # enter/leave/re-enter cycle.  Retention rules inside
                # _find_home_deposit preserve the digger and consumable kit.
                deposit = self._find_home_deposit(snapshot)
                if deposit is not None and self._home_entry_operation_posted:
                    return self._home_deposit_key(snapshot, deposit)
                required_scrolls = self._mining_detection_scroll_target(snapshot)
                scrolls_needed = required_scrolls + DETECTION_SCROLL_BUFFER
                scrolls_missing = max(
                    0,
                    scrolls_needed
                    - self._count_treasure_detection_scrolls(snapshot),
                )
                required_scrolls_missing = (
                    self._count_treasure_detection_scrolls(snapshot)
                    < required_scrolls
                )
                stored_scrolls = next(
                    (
                        item
                        for item in store.items
                        if item.is_treasure_detection_scroll
                    ),
                    None,
                )
                if scrolls_missing and stored_scrolls is not None:
                    self._home_digger_seen_pages.clear()
                    signature = self._item_signature(stored_scrolls)
                    quantity = min(scrolls_missing, stored_scrolls.count)
                    self._home_pending_item = signature
                    self._home_pending_quantity = quantity
                    self.last_reason = "home:queue-treasure-detection-withdraw"
                    return LEAVE_STORE_KEY

                withdrawable_digger_missing = (
                    self._digging_tool_count(snapshot) < 2
                    and any(
                        owned.origin == "home" and owned.item.is_digging_tool
                        for owned in self._equipment_catalog.items
                    )
                )
                if (
                    required_scrolls_missing
                    or not self._has_digging_tool(snapshot)
                    or withdrawable_digger_missing
                ):
                    page = tuple(
                        (item.letter, item.name, item.tval, item.sval)
                        for item in store.items
                    )
                    if page not in self._home_digger_seen_pages:
                        self._home_digger_seen_pages.add(page)
                        self.last_reason = (
                            "home:seek-treasure-detection-page"
                            if required_scrolls_missing
                            else "home:seek-digging-tool-page"
                        )
                        return " "
                    self._home_digger_seen_pages.clear()
                    self._home_digger_withdraw_pending = False
                    self._set_town_store_attempted(STORE_HOME, snapshot.turn, "digger-withdraw-complete")
                    self.last_reason = (
                        "home:no-treasure-detection"
                        if required_scrolls_missing
                        else "home:no-digging-tool"
                    )
                    return LEAVE_STORE_KEY

                self._home_digger_seen_pages.clear()
                catalog_work_pending = (
                    snapshot.player.class_id == PLAYER_CLASS_WARRIOR
                    and (
                        not self._equipment_catalog.home_scan_complete
                        or self._has_actionable_incomplete_home_item(snapshot)
                    )
                    and bool(self._equipment_catalog.items)
                )
                disposal_work_pending = self._home_disposal_pass
                if catalog_work_pending or disposal_work_pending:
                    # The town router entered Home to finish the equipment
                    # catalog or idle-consumable disposal pass. Mining supplies
                    # being complete does not satisfy either separate owner:
                    # fall through to the normal Home page processor instead of
                    # escaping and immediately routing back through the door
                    # forever.
                    pass
                else:
                    # This Home stop is complete for the current town visit.
                    # Without the latch, the errand plan keeps its pinned Home
                    # stop and walks straight back through the door after Escape.
                    self._report_town_stop_pass(
                        snapshot, STORE_HOME, goal_satisfied=True
                    )
                    self._set_town_store_attempted(STORE_HOME, snapshot.turn, "home-stop-complete")
                    self.last_reason = "home:leave-with-mining-supplies"
                    return LEAVE_STORE_KEY

            # High-level spellbooks are sale loot, not Home reserves. Older
            # runs could deposit them before the sale rule existed, so recover
            # them during the normal Home page scan and hand them to the
            # realm-appropriate shop routing. Leave immediately after a
            # withdrawal so the deposit pass cannot put the book straight back.
            if self._find_book_sale(snapshot) is not None:
                self.last_reason = "home:leave-with-book-sale"
                return LEAVE_STORE_KEY
            stored_book = next(
                (item for item in store.items if self._is_high_value_book(item)),
                None,
            )
            if stored_book is not None:
                self._home_pending_item = self._item_signature(stored_book)
                self.last_reason = "home:queue-book-sale-withdraw"
                return LEAVE_STORE_KEY

            deposit = self._find_home_deposit(snapshot)
            if deposit is not None and self._home_entry_operation_posted:
                return self._home_deposit_key(snapshot, deposit)

            if (
                self._equipped_weapon_high_grade(snapshot)
                # Stop pulling spares once the Weapon Smith is full this visit:
                # they could not be sold, and re-opening its sale route (below)
                # would only churn futile trips to a store with no room. This
                # also suppresses the route re-open, since the pop lives here.
                and STORE_WEAPON not in self._store_sale_refused
                # Never pull spares past the batch reserve: an unguarded pull
                # filled the pack to zero free every Home visit, and a full pack
                # blocks town departure (MIN_FREE_PACK_SLOTS).
                and PACK_CAPACITY - len(snapshot.inventory) > HOME_BATCH_RESERVED_SLOTS
            ):
                inferior = next(
                    (
                        it
                        for it in store.items
                        if self._weapon_is_inferior(it)
                        and self._can_add_item_without_overweight(snapshot, it)
                        # Do not withdraw a spare the Weapon Smith already refused
                        # (it would clog the pack with something no sale can clear).
                        and (it.name, it.tval, it.sval) not in self._unsellable_items
                    ),
                    None,
                )
                if inferior is not None:
                    # Pull a stored good/average spare weapon back out (no pending
                    # processing) so it can be sold at the Weapon Smith; the
                    # deposit filter keeps it from being re-stored on the way.
                    # Re-open the Weapon Smith sale route for this freshly withdrawn
                    # spare. Without it, a second Home visit that pulls a new batch
                    # after the smith was already visited leaves the pack clogged
                    # with unsold weapons (STORE_WEAPON stays latched until
                    # STORE_RETRY_TURNS) and town departure stalls until self-stop.
                    self._town_store_attempted.pop(STORE_WEAPON, None)
                    self._home_pending_item = self._item_signature(inferior)
                    self.last_reason = "home:queue-inferior-weapon-withdraw"
                    return LEAVE_STORE_KEY

            candidate = self._find_home_candidate(snapshot)
            if candidate is not None:
                needs_normal = (
                    not candidate.known
                    and candidate.pseudo_feeling != "average"
                )
                needs_full = (
                    candidate.known
                    and self._identification_flow_candidate(candidate)
                )
                if needs_normal and self._find_identification_source(
                    snapshot,
                    full=False,
                    reliable_only=True,
                    reservation_target=self._item_signature(candidate),
                ) is None:
                    signature = self._item_signature(candidate)
                    self._request_identification("normal")
                    self._identification_candidate = signature
                    self._reserve_next_identification_source(
                        snapshot, signature, full=False
                    )
                    self._home_candidate_waiting = True
                    self.last_reason = "home:need-identify"
                    return LEAVE_STORE_KEY
                if needs_full and self._find_identification_source(
                    snapshot,
                    full=True,
                    reservation_target=self._item_signature(candidate),
                ) is None:
                    signature = self._item_signature(candidate)
                    self._unbuyable_full_identify_sigs.add(signature)
                    self._request_identification("full")
                    self._identification_candidate = signature
                    self._reserve_next_identification_source(
                        snapshot, signature, full=True
                    )
                    self._home_candidate_waiting = True
                    self.last_reason = "home:need-full-identify"
                    return LEAVE_STORE_KEY

                free_slots = PACK_CAPACITY - len(snapshot.inventory)
                if free_slots <= HOME_BATCH_RESERVED_SLOTS:
                    # This candidate cannot be withdrawn until carried gear is
                    # identified/sold/deposited.  Keeping candidate_waiting set
                    # makes Home outrank those space-making errands and creates
                    # an enter/leave loop on the same full pack. Defer only this
                    # signature for the town visit and release its identify
                    # request so carried candidates can be processed first.
                    signature = self._item_signature(candidate)
                    self._defer_home_item(signature, "home-equipment-processing-deferred")
                    self._release_identification_source_reservation(signature)
                    if self._identification_candidate == signature:
                        self._identification_candidate = None
                    self._identification_need = None
                    self._home_candidate_waiting = False
                    self.last_reason = "home:defer-capacity"
                    return LEAVE_STORE_KEY

                signature = self._item_signature(candidate)
                self._home_pending_batch.append(signature)
                self._home_candidate_waiting = False
                self.last_reason = "home:queue-batch-withdraw"
                return LEAVE_STORE_KEY

            if (
                self._home_pending_batch
                and PACK_CAPACITY - len(snapshot.inventory)
                <= HOME_BATCH_RESERVED_SLOTS
            ):
                self._home_candidate_waiting = False
                self.last_reason = "home:leave-with-batch"
                return LEAVE_STORE_KEY

            page = tuple(
                (item.letter, item.name, item.tval, item.sval)
                for item in store.items
            )

            self._home_processing_seen_pages.clear()
            self._home_candidate_waiting = False
            self._report_town_stop_pass(
                snapshot,
                STORE_HOME,
                goal_satisfied=self._equipment_catalog.home_scan_complete,
            )
            self.last_reason = (
                "home:leave-with-batch"
                if self._home_pending_batch
                else "home:processing-complete"
            )
            return LEAVE_STORE_KEY

        batch_key = self._batch_sell_key(snapshot)
        if batch_key is not None:
            return batch_key

        organization = self._find_town_organization_surplus(snapshot)
        ordinary_sale = self._find_book_sale(snapshot, store.store_type)
        if ordinary_sale is None and store.store_type == STORE_ALCHEMIST:
            ordinary_sale = self._find_low_level_sale(snapshot)
        if ordinary_sale is None and store.store_type == STORE_MAGIC:
            ordinary_sale = self._find_device_sale(snapshot)
        if ordinary_sale is None and store.store_type == STORE_WEAPON:
            ordinary_sale = self._find_weapon_sale(snapshot)
        if ordinary_sale is None and store.store_type == STORE_GENERAL:
            ordinary_sale = self._find_light_sale(snapshot)
        if (
            organization is not None
            and ordinary_sale is None
            and self._next_purchase(snapshot) is None
            and self._store_accepts_sale(store.store_type, organization)
            and store.store_type
            == self._town_organization_sale_store(snapshot, organization)
        ):
            return self._store_sell_key(
                snapshot, organization, "shop:sell-town-surplus"
            )

        book_sale = self._find_book_sale(snapshot, store.store_type)
        if book_sale is not None:
            return self._store_sell_key(
                snapshot, book_sale, "shop:sell-high-value-book",
                rejected_reason="shop:unsellable-book-leave",
            )

        if store.store_type == STORE_ALCHEMIST:
            sale = self._find_low_level_sale(snapshot)
            if sale is not None:
                return self._store_sell_key(
                    snapshot, sale, "shop:sell-low-value-consumable"
                )

        if store.store_type == STORE_MAGIC:
            sale = self._find_device_sale(snapshot)
            if sale is not None:
                if (
                    self._home_identify_staff_sale_pending
                    and sale.tval == TVAL_STAFF
                    and sale.sval == SV_STAFF_IDENTIFY
                ):
                    self._home_identify_staff_sale_pending = False
                    self._home_identify_staff_sold_this_magic_visit = True
                    self._rearm_town_store_for_new_work(STORE_HOME)
                return self._store_sell_key(
                    snapshot, sale, "shop:sell-device",
                    rejected_reason="shop:unsellable-device-leave",
                )

        if store.store_type == STORE_WEAPON:
            sale = self._find_weapon_sale(snapshot)
            if sale is not None:
                reason = (
                    "shop:sell-no-teleport-weapon"
                    if self._blocks_teleport(sale)
                    else "shop:sell-inferior-weapon"
                )
                return self._store_sell_key(
                    snapshot, sale, reason,
                    rejected_reason="shop:unsellable-weapon-leave",
                )

        if store.store_type == STORE_GENERAL:
            if snapshot.player.food_type == FOOD_TYPE_MANA:
                sale = self._first_item(
                    snapshot,
                    lambda item: item.tval == TVAL_FOOD
                    and self._retention_surplus(snapshot, item) > 0
                    and self._item_signature(item) not in self._unsellable_items,
                )
                if sale is not None:
                    return self._store_sell_key(
                        snapshot, sale, "shop:sell-mana-race-food"
                    )
            sale = self._find_light_sale(snapshot)
            if sale is not None:
                reason = (
                    "shop:sell-surplus-torches"
                    if sale.is_torch
                    else "shop:sell-spare-lantern"
                )
                return self._store_sell_key(
                    snapshot, sale, reason,
                    rejected_reason="shop:unsellable-light-leave",
                )

        item = self._next_purchase(snapshot)
        if item is not None:
            if (item.tval, item.sval) in self._town_visit_sale_signatures:
                self.town_visit_report = (
                    f"town-visit:sell-rebuy-churn:{item.tval}:{item.sval}"
                )
                self.last_reason = "shop:sell-rebuy-churn-defect"
                return LEAVE_STORE_KEY
            home_gate = self._purchase_has_fresh_home_absence(snapshot, item)
            if home_gate is not ProcurementHomeGate.ALLOW_PURCHASE:
                if home_gate is ProcurementHomeGate.BLOCKED:
                    self._publish_purchase_home_block()
                    return WAIT_KEY
                self._rearm_town_store_for_new_work(
                    STORE_HOME, release_visit_bound=True
                )
                self.last_reason = "shop:home-first-before-purchase"
                return LEAVE_STORE_KEY
            signature = self._item_signature(item)
            # Bail out of a purchase that never takes effect. A registered buy
            # drops our gold (so the signature changes and the counter resets);
            # if we keep asking to buy the same item at the same gold, the macro
            # is not landing (e.g. an out-of-page letter, or a flushed prompt key)
            # and there is no loop-detector inside a store to save us.
            sig = (item.letter, snapshot.player.gold)
            if sig == self._last_buy_sig:
                self._store_stuck_count += 1
            else:
                self._last_buy_sig = sig
                self._store_stuck_count = 0
            if self._store_stuck_count >= STORE_STUCK_LIMIT:
                self._shopping_abandoned = True
                self._set_town_store_attempted(store.store_type, snapshot.turn, "buy-stuck-leave")
                self._store_stuck_count = 0
                self._last_buy_sig = None
                self.last_reason = "shop:stuck-leave"
                return LEAVE_STORE_KEY
            remaining = self._purchase_quantity(snapshot, item)
            progress_sig = (item.letter, remaining, snapshot.player.gold)
            if self._last_buy_progress_sig is not None:
                old_letter, old_remaining, old_gold = self._last_buy_progress_sig
                if (
                    item.letter == old_letter
                    and remaining == old_remaining
                    and snapshot.player.gold < old_gold
                ):
                    self._store_buy_no_progress_count += 1
                elif item.letter != old_letter or remaining != old_remaining:
                    self._store_buy_no_progress_count = 0
            self._last_buy_progress_sig = progress_sig
            if self._store_buy_no_progress_count >= STORE_STUCK_LIMIT:
                self._shopping_abandoned = True
                self._set_town_store_attempted(store.store_type, snapshot.turn, "buy-no-progress")
                self._store_buy_no_progress_count = 0
                self._last_buy_progress_sig = None
                self.last_reason = "shop:defective-target-leave"
                return LEAVE_STORE_KEY
            if item.is_lantern:
                self.last_reason = "shop:buy-lantern"
            elif item.is_oil:
                self.last_reason = "shop:buy-oil"
            elif item.is_recall_scroll:
                self.last_reason = "shop:buy-recall"
            elif item.is_teleport_scroll:
                self.last_reason = "shop:buy-teleport"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
                self.last_reason = "shop:buy-cure-critical"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED:
                self.last_reason = "shop:buy-speed"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING:
                self.last_reason = "shop:buy-healing"
            elif item.is_treasure_detection_scroll:
                self.last_reason = "shop:buy-treasure-detection"
            elif item.is_digging_tool:
                fallback_purchase = self._digger_buy_fallback_available(snapshot)
                self.last_reason = (
                    "shop:buy-digging-tool:home-withdraw-failed-fallback"
                    if fallback_purchase
                    else "shop:buy-digging-tool"
                )
            elif item.is_ammo:
                self.last_reason = "shop:buy-ammo"
            elif item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
                self.last_reason = "shop:buy-torch"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
                self.last_reason = "shop:buy-identify"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
                self.last_reason = "shop:buy-star-identify"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_REMOVE_CURSE:
                self.last_reason = "shop:buy-remove-curse"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_REMOVE_CURSE:
                if (
                    not self._has_unremovable_curse_target(snapshot)
                    and self._star_remove_curse_reserve_purchase_needed(snapshot)
                ):
                    self._star_remove_curse_reserve_deposit_pending = True
                    signature = self._item_signature(item)
                    self._star_remove_curse_reserve_buy_inflight = (
                        signature,
                        self._inventory_signature_count(snapshot, signature),
                    )
                self.last_reason = "shop:buy-star-remove-curse"
            elif (
                item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_HIT
            ):
                self.last_reason = "shop:buy-enchant-tohit"
            elif (
                item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_DAM
            ):
                self.last_reason = "shop:buy-enchant-todam"
            elif (
                snapshot.player.food_type == FOOD_TYPE_MANA
                and item.tval in {TVAL_WAND, TVAL_STAFF}
            ):
                self.last_reason = "shop:buy-device-food"
            else:
                self.last_reason = "shop:buy-food"
            quantity = remaining
            # Unlike a speculative sell, this purchase names a ware from the
            # current emitted store page and _next_purchase has rechecked its
            # price/quantity.  Thus 'p' has a live selectable precondition; the
            # remaining Returns are prompt defaults and a final confirmation,
            # not an unchecked tail after a possibly unsupported command.
            suffix = f"{quantity}\r\r" if item.count > 1 else BUY_CONFIRM_SUFFIX
            self._store_buy_inflight = (
                store.store_type,
                signature,
                self._inventory_signature_count(snapshot, signature),
                snapshot.player.gold,
                0,
                self._decision_sequence,
            )
            if item.is_digging_tool and fallback_purchase:
                self._digger_fallback_bought_this_visit = True
            return BUY_KEY + item.letter + suffix

        self._store_buy_inflight = None
        self._last_buy_sig = None
        self._last_buy_progress_sig = None
        self._store_buy_no_progress_count = 0
        self._last_sell_sig = None
        self._store_stuck_count = 0
        self._store_sell_stuck_count = 0
        self._set_town_store_attempted(store.store_type, snapshot.turn, "shop-observed-complete")
        if store.store_type == STORE_ALCHEMIST and self._find_low_level_sale(snapshot) is None:
            self._sell_scavenged_consumables = False
            if self._fundraising_mode == "scavenge" and snapshot.in_town:
                self._fundraising_mode = "prepare"
                # Re-check the latched stores only when the scavenge pass
                # actually raised gold — that is what could have changed their
                # verdict. A blanket clear with UNCHANGED gold re-routed the
                # bot into the same out-of-stock stores forever: the
                # Alchemist<->Magic travel ping-pong, invisible to the loop
                # guard because store snapshots reset it and travel keeps the
                # position moving.
                if snapshot.player.gold > self._scavenge_entry_gold:
                    self._town_store_attempted.clear()
        if (
            snapshot.player.class_id < 0
            and store.store_type == STORE_GENERAL
            and not self._owns_lantern(snapshot)
        ):
            self._shopping_abandoned = True
        self.last_reason = "shop:leave"
        return LEAVE_STORE_KEY

    def _shopping_approach_step(
        self, snapshot: Snapshot, store_type: int | None = None
    ) -> Position | None:
        equipment_home_route = (
            self._equipment_transaction_session is not None
            and self._equipment_transaction_session.required_context == "home"
            and not self._town_store_blocked_under_applicable_bound(STORE_HOME)
            and self._town_visit_ledger.unsatisfied_passes[STORE_HOME]
            < self._town_store_visit_limit(STORE_HOME)
        )
        if not snapshot.in_town or (
            self._town_blocked_reason is not None
            and self._town_blocked_reason != "repetition"
            and not equipment_home_route
        ):
            return None
        if self._shopping_stuck:
            # The failed store was recorded in _town_store_attempted when the
            # approach limit fired. This latch must not suppress the alternate
            # store (or the restock wait) selected on the following turn.
            self._shopping_stuck = False
        if store_type is None:
            store_type = self._next_required_store_type(snapshot)
        if store_type is None:
            self._shop_approach_stuck_count = 0
            return None
        plan = self._town_errand_plan
        home_categories = (
            set(plan.need_categories.get(STORE_HOME, ()))
            if plan is not None else set()
        )
        if (
            store_type == STORE_HOME
            and "identification-withdrawal" in home_categories
            and home_categories <= {"identification-withdrawal"}
            and (
                not self._home_errand.active
                or self._home_errand.request is None
            )
        ):
            # Keep the staged post-Alchemist stop in the disposable plan, but
            # do not turn it into movement until its requester has filed the
            # executor's exact withdrawal request.
            return None
        if store_type == STORE_HOME:
            if not self._ensure_home_visit_request(snapshot):
                self._set_town_store_attempted(STORE_HOME, snapshot.turn, "home-request-unavailable")
                self._shopping_approach_store_type = None
                self._shopping_approach_goal = None
                return None
        equipment_owner = (
            store_type == STORE_HOME
            and self._equipment_transaction_session is not None
        )
        arbiter = self._town_turn_arbiter
        if arbiter is None:
            arbiter = _new_town_turn_arbiter()
            self._town_turn_arbiter = arbiter
        requested_owner = (
            "equipment-transaction" if equipment_owner else "town-errand"
        )
        existing_visit = (
            arbiter.store_visit if hasattr(arbiter, "store_visit") else None
        )
        visit = arbiter.acquire_store_visit(
            store_type=store_type,
            owner=requested_owner,
            purpose=("equipment-work" if equipment_owner else "shopping"),
            opened_sequence=self._decision_sequence,
            close_visit=self._close_store_visit,
        )
        self._acquire_store_visit_attempt = {
            "acquire_store_visit_called": True,
            "requested_owner": requested_owner,
            "requested_store": store_type,
            "acquire_result": (
                "refused"
                if visit is None
                else "granted-existing"
                if visit is existing_visit
                else "granted-new"
            ),
        }
        if visit is None:
            return None
        if (
            store_type == STORE_HOME
            and self._town_visit_ledger.approach_fails[store_type]
            >= self._town_store_visit_limit(store_type)
        ):
            self._set_town_store_attempted(store_type, snapshot.turn, "approach-fails-limit")
            self._shop_approach_stuck_count = 0
            return None
        self._shopping_approach_store_type = store_type
        if self._town_map_active(snapshot):
            self._shopping_approach_goal = self._town_map.store_position(store_type)
        if self._shopping_approach_goal is None:
            visible_goals = [
                grid.position
                for grid in snapshot.grids.values()
                if grid.store_number == store_type
            ]
            if visible_goals:
                self._shopping_approach_goal = min(
                    visible_goals,
                    key=lambda pos: snapshot.player.position.distance_to(pos),
                )
        mandatory_home_rescan = (
            store_type == STORE_HOME
            and snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and not self._equipment_catalog.home_scan_complete
            and bool(self._equipment_catalog.items)
        )
        here = snapshot.grid_at(snapshot.player.position)
        entrance_step_off = getattr(self, "_store_entrance_step_off", None)
        if (
            entrance_step_off is not None
            and (
                snapshot.turn != entrance_step_off[1]
                or snapshot.player.position != entrance_step_off[2]
            )
        ):
            self._store_entrance_step_off = None
        if here is not None and here.store_number == store_type:
            pending_store_transaction = (
                self._town_visit_ledger.pending_store_transaction
            )
            if (
                pending_store_transaction is not None
                and pending_store_transaction[0] == store_type
                and self._town_visit_ledger.pending_store_context_waits
                < STORE_STUCK_LIMIT
            ):
                # A null surface page at the unchanged entrance does not prove
                # that the preceding store command failed or that the visit
                # ended.  Wait for the confirming store generation.  The
                # visit ledger grants only the existing bounded retry window;
                # after it expires the ordinary step-off/re-entry path remains
                # available for genuinely outstanding NeedSpec work.
                self._town_visit_ledger.pending_store_context_waits += 1
                return snapshot.player.position
            # A player-turn snapshot is emitted on the entrance before the
            # queued SPECIAL_KEY_STORE opens the UI. Do not mistake that for a
            # completed store visit and immediately step back off the entrance.
            # A native town-travel command can also finish on the entrance
            # without queuing SPECIAL_KEY_STORE, however. Wait for one snapshot,
            # then step off and back on if the store still did not open.
            if (
                not self._last_snapshot_was_store
                and not self.last_reason.endswith(":await-entry")
            ):
                return snapshot.player.position
            # Standing on the store entrance in town (we just left it) — stepping
            # on it is what re-enters, so hop to an adjacent tile first, then the
            # next approach walks back on and opens the store.
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self._store_entrance_step_off = (
                    self._decision_sequence,
                    snapshot.turn,
                    snapshot.player.position,
                )
            return neighbors[0] if neighbors else None
        # NO _least_visited_neighbor oscillation-breakout here. Breaking out
        # toward the "least-visited" tile would march the bot to the town's edge
        # and across the border into the open wilderness (an out-of-depth Cyclops
        # killed a clvl-4 bot exactly this way). If the store is unreachable,
        # return None and let safer logic handle it rather than wandering outward.
        step = self._nearest_goal_step(snapshot, lambda g: g.store_number == store_type)
        if step is None and self._town_map_active(snapshot):
            # At night the store entrance is unlit, so it is absent from the emitted
            # grids and the flag-based scan above finds nothing. Route to the store's
            # remembered position from the static town map instead — the layout is
            # prior knowledge a returning player already has.
            step = self._town_map_goal_step(
                snapshot, self._town_map.store_position(store_type)
            )
        if (
            step is None
            and self._shopping_approach_goal is not None
            and snapshot.player.position.distance_to(self._shopping_approach_goal) >= 3
        ):
            # A freshly resumed bot can know the distant store landmark without
            # yet remembering the intervening floor. This synthetic step is
            # consumed by native store travel, not as a raw movement direction.
            step = self._shopping_approach_goal
        if step is None:
            self._shop_approach_stuck_count = 0
            return None
        # A few bounces on the way in are fine (the store is usually a tile or two
        # on), but a store approach that keeps oscillating WITHOUT arriving means the
        # entrance is effectively unreachable (blocked, or the static-map route and
        # the live grid disagree). After SHOP_APPROACH_STUCK_LIMIT such turns, give
        # up SHOPPING for this visit and let the recall dive with what we have —
        # before the loop guard fires. Never wander outward (we return the store
        # step until then, never a least-visited edge tile).
        if self._is_oscillating():
            self._shop_approach_stuck_count += 1
        else:
            self._shop_approach_stuck_count = 0
        if self._shop_approach_stuck_count >= SHOP_APPROACH_STUCK_LIMIT:
            equipment_work_at_home = (
                store_type == STORE_HOME and self._outstanding_equipment_work()
            )
            self._shop_approach_stuck_count = 0
            if equipment_work_at_home:
                # The equipment transaction charges every issued Home approach
                # to its existing pass ceiling. The detector therefore keeps
                # returning the known route step without maintaining a second
                # route bound. A None above still distinctly means that map
                # routing found no step at all.
                return step
            self._shopping_stuck = True
            self._set_town_store_attempted(store_type, snapshot.turn, "shopping-stuck")
            self._town_visit_ledger.approach_fails[store_type] += 1
            return None
        return step

    def _shopping_approach_key(
        self, snapshot: Snapshot, step: Position, travel_reason: str
    ) -> str:
        """Ride native town travel toward the store, walking only as fallback.

        In the original-keyset travel point selector, shifted number-row symbols
        are direct store landmarks; ``.`` selects the landmark. ``n`` first
        declines Hengband's "continue previous travel?" prompt after an
        interrupted route. When there is no such prompt, point selection simply
        ignores that non-direction key. Native travel advances without waiting
        for a bot snapshot after every tile, which removes most town round-trip
        cost; an interruption mid-route is re-issued as long as it made
        progress (see _town_travel_key)."""
        if (
            self._equipment_transaction_owns_town_relocation(snapshot)
            and self._shopping_approach_store_type != STORE_HOME
        ):
            # Every store route, including candidate probes and one-step
            # fallbacks, converges here.  Refusal is deliberately pure: only
            # the transaction executor may mutate or abandon its session.
            return WAIT_KEY
        entry_failed_here = (
            self._store_entry_failed_owner == self._shopping_approach_store_type
        )
        if not entry_failed_here:
            if self._shopping_approach_store_type == STORE_HOME:
                self._bind_catalogued_home_identification_withdrawal(snapshot)
            atomic_shop = self._atomic_shop_transaction_key(snapshot)
            if atomic_shop is not None:
                return atomic_shop
            atomic_withdrawal = self._atomic_home_withdraw_key(snapshot, step)
            if atomic_withdrawal is not None:
                return atomic_withdrawal
            atomic_deposit = self._atomic_home_deposit_key(snapshot, step)
            if atomic_deposit is not None:
                return atomic_deposit
            # This is one observed-uncomposable-stop rule with two entry
            # points: Home is observed through the ~9 knowledge scan and has
            # no _shop_observation, while ordinary shops must consume their
            # observed page inside _atomic_shop_transaction_key.
            if (
                self._shopping_approach_store_type == STORE_HOME
                and self._resolve_observed_uncomposable_stop(snapshot)
            ):
                return WAIT_KEY
        elif step == snapshot.player.position:
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            self.last_reason = "store:entry-failed-step-off"
            return self._step_toward(snapshot, neighbors[0]) if neighbors else ""
        here = snapshot.grid_at(snapshot.player.position)
        if (
            step == snapshot.player.position
            and here is not None
            and here.store_number == self._shopping_approach_store_type
        ):
            self.last_reason = f"{travel_reason}:await-entry"
            self._store_entry_wait_owner = self._shopping_approach_store_type
            self._store_entry_wait_key = WAIT_KEY
            return WAIT_KEY
        if not self._has_light_equipped(snapshot):
            return self._step_toward(snapshot, step)
        goal = self._shopping_approach_goal
        clear_traveler = self._town_clear_traveler_key(snapshot, goal)
        if clear_traveler is not None:
            return clear_traveler
        store_type = self._shopping_approach_store_type
        if goal is None or store_type is None:
            return self._step_toward(snapshot, step)
        # A leading Escape dismisses a lingering -more- or prompt before the
        # backtick opens native travel; at the command loop it is a harmless
        # no-op. Without it, the prompt can eat ` and leave (notably) % to open
        # the visuals screen instead of selecting a store travel point.
        travel = self._town_travel_key(
            snapshot,
            goal,
            f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[store_type]}.",
            travel_reason,
        )
        if travel is not None:
            if not self._owner_may_select(snapshot, travel_reason):
                self._town_travel_fallback = goal
                self._town_travel_state = None
                self.last_reason = "shop:approach"
                return self._step_toward(snapshot, step)
            self._post_owner_expectation(
                snapshot, travel_reason, "position", "store_type"
            )
            # Native travel runs to completion without an intermediate bot
            # snapshot and may therefore perform the final movement onto the
            # shop tile itself.  Own that possible entry exactly like the
            # disclosed one-step entrance path below: the next surface page is
            # the documented lagged observation, not permission to compose a
            # store command across the entry flush.
            self._store_entry_wait_owner = store_type
            self._store_entry_wait_key = travel
            return travel
        return self._step_toward(snapshot, step)

    def _atomic_shop_transaction_key(self, snapshot: Snapshot) -> str | None:
        """Compose one transaction from the latest observed page, outside."""
        observation = self._shop_observation
        if (
            observation is None
            or snapshot.store is not None
            or observation[0].store_type == STORE_HOME
        ):
            return None
        # Bind the one-shot to the page that was actually observed, not the
        # mutable town-plan cursor.  The ordinary shop handler advances that
        # cursor while producing the observe-and-leave result; using it here
        # made the adjacent outside handoff reject the target store and travel
        # to the following stop without composing the purchase.
        store_type = observation[0].store_type
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.store_number != store_type:
            return None

        observed_store, generation = observation
        # Store item letters are relative to page zero.  Ordinary shops reset
        # to that page on every entry, so a non-zero observation is stale or
        # malformed and must never be used to compose an atomic transaction.
        if observed_store.page_top not in (None, 0):
            self._shop_observation = None
            self.last_reason = "shop:one-shot-page-not-zero"
            return None
        # Current inventory/gold are paired with exactly this latest page at
        # the composition boundary; no cached item candidate is trusted.
        reason_before_composition = self.last_reason
        inner = self._shop(replace(snapshot, store=observed_store))
        if inner.startswith((BUY_KEY, SELL_KEY)):
            operation_key = inner + LEAVE_STORE_KEY
            key = WAIT_KEY
            self._shop_observation = None
            self._town_visit_ledger.pending_store_transaction = (
                observed_store.store_type,
                self._decision_sequence,
            )
            self._town_visit_ledger.pending_store_context_waits = 0
            self.last_reason = (
                "shop:one-shot-buy"
                if inner.startswith(BUY_KEY)
                else "shop:one-shot-sell"
            )
            if self._store_visit is not None:
                self._store_visit.operation_posted = True
                self._store_visit.operation_key = operation_key
                self._store_visit.operation_released = False
                self._store_visit.composed_key = key
                self._store_visit.posted_sequence = generation
                self._store_visit.posted_turn = snapshot.turn
                self._store_entry_wait_owner = observed_store.store_type
                self._store_entry_wait_key = key
            self._shop_selector_diagnostics.pop("composition_refusal", None)
            self._shop_selector_diagnostics.pop(
                "composition_refusal_sequence", None
            )
            return key
        if inner.startswith("{"):
            # Inscription is an outside pack operation.  Retain this page while
            # the next outside snapshot re-resolves the newly tagged item.
            return inner
        composition_refusal = self.last_reason
        if self._shop_selector_diagnostics.get(
            "composition_refusal_sequence"
        ) == self._decision_sequence:
            composition_refusal = self._shop_selector_diagnostics.get(
                "composition_refusal"
            )
        star_remove_curse_shelf_seen = self._star_remove_curse_shelf_seen
        self._record_shop_selector_diagnostics(
            replace(snapshot, store=observed_store), inner
        )
        self._star_remove_curse_shelf_seen = star_remove_curse_shelf_seen
        self._shop_selector_diagnostics["composition_refusal"] = composition_refusal
        self._shop_selector_diagnostics["composition_refusal_sequence"] = (
            self._decision_sequence
        )
        if composition_refusal == "shop:home-first-yields-to-current-visit":
            # This supplier was observed, but stale Home knowledge owns the
            # purchase.  Retire only this pass so the next router decision can
            # file and approach the Home refresh instead of re-entering here.
            plan = self._town_errand_plan
            if (
                plan is not None
                and plan.index < len(plan.stops)
                and plan.stops[plan.index] == store_type
            ):
                plan.current_stop_passes = 0
                plan.index += 1
            self._shop_observation = None
            self._close_store_visit("home-first-yield")
            self.last_reason = reason_before_composition
            return None
        if composition_refusal == "town:blocked:home-withdraw-failed-stock-present":
            # This is the deliberate terminal produced by a refreshed Home
            # census, not an ordinary uncomposable supplier pass.  Keep the
            # observed page and publish the stop at the consumed WAIT boundary.
            self._town_visit_ledger.pending_store_transaction = None
            self._town_visit_ledger.pending_store_context_waits = 0
            self._publish_purchase_home_block()
            return WAIT_KEY
        # Decide the observed no-op while this page is still current, then
        # consume it exactly as the pre-composition contract did.  A later
        # pack/gold change must re-observe the shelf before using its letters.
        if self._resolve_observed_uncomposable_stop(snapshot):
            return WAIT_KEY
        if composition_refusal in {
            "town:blocked:procurement-home-unavailable",
            "town:blocked:procurement-home-unroutable",
        }:
            self.last_reason = reason_before_composition
        self._shop_observation = None
        return None

    def _star_remove_curse_reserve_purchase_needed(
        self, snapshot: Snapshot
    ) -> bool:
        return (
            snapshot.player.gold >= FUNDRAISING_GOLD_TARGET
            and not self._recall_departure_shortage(snapshot)
            and self._home_star_remove_curse_count == 0
            and self._carried_star_remove_curse_count(snapshot) == 0
            and not self._star_remove_curse_reserve_deposit_pending
        )

    def _restore_mining_combat_hand_key(
        self, snapshot: Snapshot, reason: str
    ) -> str | None:
        """Restore each combat hand displaced by the temporary mining loadout."""
        main_hand = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"),
            None,
        )
        for target_slot, remembered_name, remembered_identity, optimal_known in (
            (
                "main_hand",
                self._normal_weapon_name,
                self._normal_weapon_identity,
                self._normal_weapon_is_optimal,
            ),
            (
                "sub_hand",
                self._normal_sub_hand_name,
                self._normal_sub_hand_identity,
                self._normal_sub_hand_is_optimal,
            ),
        ):
            equipped = next(
                (item for item in snapshot.equipment if item.slot == target_slot),
                None,
            )
            if equipped is None or not equipped.is_digging_tool:
                continue
            if target_slot == "sub_hand" and optimal_known and remembered_name is None:
                if main_hand is not None and not main_hand.is_digging_tool:
                    self._digger_wield_attempts = 0
                    key = self._equipment_takeoff(
                        snapshot, "combat-loadout", EQUIPMENT_SLOT_KEY[target_slot]
                    )
                    if key is not None:
                        self.last_reason = reason
                    return key
                continue
            replacement = self._first_item(
                snapshot,
                lambda item: item.is_equipment
                and not item.is_digging_tool
                and item.known
                and not item.is_cursed
                and not item.is_broken
                and not self._blocks_teleport(item)
                and (
                    equipment_identity(item) == remembered_identity
                    if remembered_identity is not None
                    else item.name == remembered_name
                    if remembered_name is not None
                    else (
                        item.is_melee_weapon
                        if target_slot == "main_hand"
                        else item.tval == 34 or item.is_melee_weapon
                    )
                ),
            )
            if replacement is None:
                if (
                    target_slot == "sub_hand"
                    and main_hand is not None
                    and not main_hand.is_digging_tool
                ):
                    self._digger_wield_attempts = 0
                    key = self._equipment_takeoff(
                        snapshot, "combat-loadout", EQUIPMENT_SLOT_KEY[target_slot]
                    )
                    if key is not None:
                        self.last_reason = reason
                    return key
                continue
            self._digger_wield_attempts += 1
            if self._digger_wield_attempts >= DIGGER_WIELD_LIMIT:
                self._digger_wield_attempts = 0
                self.last_reason = f"{reason}:abandon-unconfirmed-equip"
                return None
            key = self._equipment_wield(
                snapshot, "combat-loadout", replacement, target_slot
            )
            if key is not None:
                self.last_reason = reason
            return key
        self._digger_wield_attempts = 0
        self._mining_combat_loadout_remembered = False
        return None
