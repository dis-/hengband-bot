"""The Q34 reward -> mining kit -> Q1 transaction.

Shelf observations and the existing quest contract are the only price/count sources.
The route retains its kit choice across purchases and checkpoints.
"""
from dataclasses import replace

from hengbot.model import (
    STORE_GENERAL, STORE_WEAPON, STORE_BLACK, STORE_ALCHEMIST, STORE_TEMPLE, STORE_MAGIC,
    TVAL_FOOD, TVAL_STAFF, TVAL_WAND, StoreState,
    SV_POTION_HEALING, SV_POTION_SPEED, TVAL_POTION, DUNGEON_YEEK_CAVE,
)
from hengbot.policy_types import TownNeed
from hengbot.policy_constants import (
    ENTER_DUNGEON_MACRO, REST_MACRO, STORE_STUCK_LIMIT,
    FOOD_TYPE_MANA, FOOD_MIN_SVAL,
    QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN, QUEST_STATUS_REWARDED,
    QUEST_STATUS_FINISHED,
)
from hengbot.policy_fundraising import FundraisingPurpose
from hengbot.item_reservation import decision_memo


class OpeningRouteMixin:
    def _opening_q1_active(self, snapshot):
        quests = self._known_fixed_quests(snapshot)
        q34, q1 = quests.get(34), quests.get(1)
        return bool(
            snapshot.player.class_id >= 0
            and q34 is not None
            and q34.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}
            and q1 is not None
            and q1.status in {QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN}
            and self.approved_quest_strategy(1) is not None
        )

    def _opening_q1_shopping(self, snapshot):
        return snapshot.in_town and self._opening_q1_active(snapshot)

    def _opening_q1_requirements(self, snapshot):
        return decision_memo(
            self, "opening-q1-requirements", snapshot, (),
            lambda: self._opening_q1_requirements_uncached(snapshot),
        )

    def _opening_q1_requirements_uncached(self, snapshot):
        profile = self.approved_quest_strategy(1)
        force = self._strategy_force_for_snapshot(snapshot, profile)
        # Ask the same DPS/HP calculation as readiness. Carries may still fail;
        # its measurements are nevertheless populated before that rejection.
        previous = self._fixed_quest_readiness
        self._fixed_quest_readiness = {}
        try:
            self._approved_strategy_force_ready(snapshot, profile)
            measured = self._fixed_quest_readiness["strategy_force"]
        finally:
            self._fixed_quest_readiness = previous
        tier = force.get("no_healing_tier", {})
        no_heal = bool(tier and snapshot.player.max_hp >= tier["min_hp"]
                       and measured["dps"]["measured"] >= tier["min_expected_dps"])
        return (
            ("quest-throwing-items", int(force.get("throwing_items", {}).get("lit_torch", 0)),
             self._count_throwing_torches(snapshot), lambda item: item.is_torch),
            ("quest-healing", 0 if no_heal else int(force.get("heal_potions", 0)),
             self._exact_potion_count(snapshot, SV_POTION_HEALING),
             lambda item: item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING),
            ("quest-speed", 0 if no_heal else int(force.get("speed_potions", 0)),
             self._exact_potion_count(snapshot, SV_POTION_SPEED),
             lambda item: item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED),
        )

    def _opening_q1_pages(self, snapshot):
        pages = {}
        for store, page in self._town_supplier_stock.items():
            observed = self._town_supplier_stock_observations.get(store)
            if (observed is not None and observed[0] == self._effective_town_id(snapshot)
                    and (page.stock_num is None or page.stock_num <= len(page.items))):
                pages[store] = page
        for store, census in getattr(self, "_opening_q1_shelves", {}).items():
            if census["town"] == self._effective_town_id(snapshot) and census["complete"]:
                items = [item for top, page in sorted(census["pages"].items()) for item in page.items]
                pages[store] = StoreState(store, items)
        if (snapshot.store is not None
                and (snapshot.store.stock_num is None or snapshot.store.stock_num <= len(snapshot.store.items))):
            pages[snapshot.store.store_type] = snapshot.store
        return pages

    def _opening_q1_store_key(self, snapshot):
        """Survey every emitted shelf page before choosing the affordable kit."""
        page = snapshot.store
        if page is None or not self._opening_q1_active(snapshot):
            return None
        if page.stock_num is None or page.page_size is None or page.page_top is None:
            return None
        shelves = getattr(self, "_opening_q1_shelves", None)
        if shelves is None:
            shelves = self._opening_q1_shelves = {}
        entry = getattr(self._store_visit, "opened_sequence", self._decision_sequence)
        census = shelves.get(page.store_type)
        town = self._effective_town_id(snapshot)
        if (census is None or census["town"] != town or census["entry"] != entry
                or census["stock_num"] != page.stock_num):
            census = shelves[page.store_type] = dict(
                town=town, entry=entry, stock_num=page.stock_num, pages={}, complete=False,
                visits={},
            )
        census["pages"][page.page_top] = page
        census["complete"] = all(top in census["pages"]
                                 for top in range(0, page.stock_num, page.page_size))
        stage, store, ware, _, _ = self._opening_q1_plan(snapshot)
        needs_page = (not census["complete"] or
                      (store == page.store_type and ware is not None and ware not in page.items))
        if needs_page:
            count = census["visits"].get(page.page_top, 0) + 1
            census["visits"][page.page_top] = count
            if count >= STORE_STUCK_LIMIT:
                return self._opening_q1_stop("shelf-page-no-progress:" + str(page.store_type))
            self.last_reason = "shop:opening-route-page"
            return " "
        if store == page.store_type and ware is not None and page.page_top > 0:
            # IST and one-shot composition intentionally admit page one only.
            # Never silently buy a weaker first-page tool instead.
            return self._opening_q1_stop("purchase-requires-first-page:" + stage)
        return None

    def _opening_q1_plan(self, snapshot):
        """Return (stage, supplier, ware, quantity, missing-gold).

        A plan is a pure projection, so the router, purchase selector and
        retention can all read it without advancing the transaction.
        """
        requirements = self._opening_q1_requirements(snapshot)
        pages = self._opening_q1_pages(snapshot)
        suppliers = [(STORE_GENERAL, "quest-throwing-items"),
                     (STORE_WEAPON, "fundraising-digger"),
                     (STORE_BLACK, "fundraising-digger"),
                     (STORE_ALCHEMIST, "fundraising-detection")]
        if any(target > current for _, target, current, _ in requirements[1:]):
            suppliers.append((STORE_TEMPLE, "quest-healing"))
        funding = (getattr(self, "_opening_q1_funding", None) is not None
                   and not getattr(self, "_opening_q1_funding_left", False))
        if funding and self._find_edible(snapshot) is None and snapshot.player.food_type == FOOD_TYPE_MANA:
            suppliers.append((STORE_MAGIC, "fundraising-food"))
        reachable = [(store, category) for store, category in suppliers
                     if self._town_need_supplier_reachable(snapshot, TownNeed(store, category, "normal"))]
        for store, category in reachable:
            if store not in pages:
                return "observe:" + category, store, None, 0, 0
        offers = [(store, item) for store, _ in reachable
                  for item in pages[store].items if item.count > 0]
        if funding:
            if self._find_edible(snapshot) is None:
                food = [(store, item) for store, item in offers
                        if ((item.tval in {TVAL_STAFF, TVAL_WAND} and max(item.charges, item.pval) > 0)
                            if snapshot.player.food_type == FOOD_TYPE_MANA else
                            item.tval == TVAL_FOOD and item.sval >= FOOD_MIN_SVAL)]
                food = [(store, item) for store, item in food if item.price <= snapshot.player.gold]
                if not food:
                    return "stop:fundraising-food-unavailable", None, None, 0, 0
                store, item = min(food, key=lambda row: row[1].price)
                return "fundraising-food", store, item, 1, 0
            if not self._fundraising_light_ready(snapshot):
                lights = [(store, item) for store, item in offers
                          if item.is_lantern and item.fuel > 0 and item.price <= snapshot.player.gold]
                if not lights:
                    return "stop:fundraising-light-unavailable", None, None, 0, 0
                store, item = min(lights, key=lambda row: row[1].price)
                return "fundraising-light", store, item, 1, 0
            return "fundraising", None, None, 0, 0
        if (getattr(self, "_opening_q1_funding_left", False)
                and snapshot.player.gold <= self._opening_q1_funding):
            for store, category, finder in (
                (STORE_ALCHEMIST, "low-level-sale", self._find_low_level_sale),
                (STORE_WEAPON, "weapon-sale", self._find_weapon_sale),
                (STORE_MAGIC, "device-sale", self._find_device_sale),
                (STORE_GENERAL, "light-sale", self._find_light_sale),
            ):
                view = replace(snapshot, store=pages.get(store, StoreState(store, [])))
                if (finder(view) is not None
                        and self._town_need_supplier_reachable(snapshot, TownNeed(store, category, "normal"))):
                    return category, store, None, 0, 0
            return "stop:fundraising-no-income", None, None, 0, 0
        reserve = 0
        first = None
        for category, target, current, matches in requirements:
            missing = max(0, target - current)
            for store, item in sorted(offers, key=lambda row: row[1].price):
                if not missing or not matches(item) or (item.is_torch and item.fuel <= 0):
                    continue
                quantity = min(missing, item.count)
                reserve += quantity * item.price
                missing -= quantity
                if first is None:
                    first = (category, store, item, quantity)
            if missing:
                return "stop:stock:" + category, None, None, 0, 0
        if reserve > snapshot.player.gold:
            return "funds:reserve", None, None, 0, reserve - snapshot.player.gold
        if first is not None:
            category, store, item, quantity = first
            return category, store, item, quantity, 0
        if not getattr(self, "_opening_q1_kit_bought", False):
            diggers = [(store, item) for store, item in offers
                       if item.is_digging_tool and not self._equip_blocked_by_identification(item)]
            if not diggers and not self._has_digging_tool(snapshot):
                return "stop:no-digger", None, None, 0, 0
            owned = [item for item in (*snapshot.inventory, *snapshot.equipment)
                     if item.is_digging_tool and not self._equip_blocked_by_identification(item)]
            affordable = [(store, item) for store, item in diggers
                          if item.price <= snapshot.player.gold]
            if not owned and not affordable:
                debt = min(item.price for _, item in diggers) - snapshot.player.gold
                return "funds:digger", None, None, 0, debt
            if affordable:
                store, item = max(affordable, key=lambda row: self._digging_tool_sale_quality(row[1]))
                if not owned or self._digging_tool_sale_quality(item) > max(
                        self._digging_tool_sale_quality(it) for it in owned):
                    return "fundraising-digger", store, item, 1, 0
            detection = sorted(((store, item) for store, item in offers
                                if item.is_treasure_detection_scroll
                                and item.price <= snapshot.player.gold),
                               key=lambda row: row[1].price)
            if detection:
                store, item = detection[0]
                quantity = (snapshot.player.gold // item.price if item.price > 0 else item.count)
                return "fundraising-detection", store, item, min(item.count, quantity), 0
        return "quest", None, None, 0, 0

    def _opening_q1_needs(self, snapshot):
        stage, store, _, _, _ = self._opening_q1_plan(snapshot)
        if store is None:
            return []
        return [TownNeed(store, stage.removeprefix("observe:"), "normal")]

    def _opening_q1_purchase(self, snapshot):
        if snapshot.store is None:
            return None
        _, store, ware, _, _ = self._opening_q1_plan(snapshot)
        if store != snapshot.store.store_type:
            return None
        # A cached letter is never an address on a different observed page.
        return next((item for item in snapshot.store.items if item == ware), None)

    def _opening_q1_stop(self, detail):
        self._opening_q1_failure = detail
        self.last_reason = "quest:blocked:opening-route"
        # An empty envelope cannot activate a building beneath the player.
        return ""

    def _opening_q1_income_key(self, snapshot):
        """One existing Yeek 1F income run, with no unrelated town owner."""
        stage, store, ware, _, _ = self._opening_q1_plan(snapshot)
        if stage.startswith("stop:"):
            return self._opening_q1_stop(stage)
        if store is not None:
            step = self._shopping_approach_step(snapshot, store_type=store, requester="quest-request")
            if step is None:
                return self._opening_q1_stop("fundraising-supplier-route-unavailable:" + stage)
            self.last_reason = "shop:approach"
            key = self._shopping_approach_key(snapshot, step, "shop:travel")
            return key if key is not None else self._opening_q1_stop("fundraising-purchase-unavailable:" + stage)
        self._target_dungeon_id = DUNGEON_YEEK_CAVE
        self._target_dungeon_reason = "opening-q1-funds"
        self._planned_mining_runs = 1
        self._no_safe_destination_set = False
        self._fundraising_mode = (
            "mine" if self._fundraising_kit_secured(snapshot) else "scavenge"
        )
        if not self._fundraising_food_ready(snapshot):
            return self._opening_q1_stop("fundraising-food-unavailable")
        if not self._fundraising_light_ready(snapshot):
            return self._opening_q1_stop("fundraising-light-unavailable")
        if snapshot.player.hp < snapshot.player.max_hp:
            self.last_reason = "town:recover"
            return REST_MACRO
        if not self._fundraising_departure_ready(snapshot):
            return self._opening_q1_stop("fundraising-departure-unready")
        entrance = self._town_walk_in_entrance(snapshot)
        if entrance is None:
            return self._opening_q1_stop("fundraising-entrance-unavailable")
        if self._descent_is_blocked(snapshot):
            return self._opening_q1_stop("fundraising-descent:" + str(self._descent_refusal_reason))
        if snapshot.player.position == entrance:
            if not self._dungeon_entry_allowed(snapshot, via_recall=False, destination_depth=1):
                return self._opening_q1_stop("fundraising-entry-refused")
            if getattr(self, "_crossarea_fundraising_enforced", False):
                self._fundraising_run_purpose = FundraisingPurpose(
                    self._decision_sequence, self._fundraising_mode, False,
                )
            self.last_reason = "descend"
            return ENTER_DUNGEON_MACRO
        step = self._descent_step(snapshot)
        if step is None:
            return self._opening_q1_stop("fundraising-route-unavailable")
        travel = self._entrance_travel_key(snapshot, self._descent_target_goal)
        if travel is not None:
            return travel
        self.last_reason = "opening-q1:fundraising-approach"
        return self._step_toward(snapshot, step)

    def _opening_q1_town_key(self, snapshot, hostiles):
        if not self._opening_q1_active(snapshot) or not snapshot.in_town:
            return None
        if getattr(self, "_opening_q1_failure", None):
            return self._opening_q1_stop(self._opening_q1_failure)
        if self._effective_town_id(snapshot) != 0:
            return self._opening_q1_stop("not-in-outpost")
        # Reconstruct the same allowlisted reward latch as _fixed_quest_key
        # after a restart, before purchasing anything for the next quest.
        if self._fixed_quest_reward_pending is None and any(
                (grid := snapshot.grid_at(position)) is not None and grid.object_count > 0
                for position in self._fixed_quest_reward_positions(snapshot, 34)):
            self._fixed_quest_reward_pending = 34
        # Finish the reward pickup transaction before spending its proceeds.
        if self._fixed_quest_reward_pending is not None:
            key = self._fixed_quest_key(snapshot, hostiles)
            return key if key is not None else self._opening_q1_stop("reward-unavailable")
        head = self._fixed_quest_head(snapshot)
        if head is not None and head.id != 1:
            return self._opening_q1_stop("competing-quest:" + str(head.id))
        funding = getattr(self, "_opening_q1_funding", None)
        if funding is not None:
            if not getattr(self, "_opening_q1_funding_left", False):
                return self._opening_q1_income_key(snapshot)
            if snapshot.player.gold > funding:
                self._opening_q1_funding = None
                self._opening_q1_funding_left = False
                self._supply_stockout_gold_target = None
                self._town_store_attempted.clear()
                self._retire_town_errand_plan_for_rebuild()
        self._fundraising_mode = None
        self._planned_mining_runs = None
        stage, store, ware, quantity, debt = self._opening_q1_plan(snapshot)
        if stage.startswith("stop:"):
            return self._opening_q1_stop(stage)
        if stage.startswith("funds:"):
            self._opening_q1_funding = snapshot.player.gold
            self._opening_q1_funding_left = False
            self._supply_stockout_gold_target = snapshot.player.gold + debt
            self._start_fundraising(snapshot)
            return self._opening_q1_income_key(snapshot)
        if ware is not None and not self._store_purchase_fits_pack(snapshot, ware):
            return self._opening_q1_stop("purchase-pack-full:" + stage)
        # Count repeated visits to the same state within one economic stage.
        # No-progress purchases and multi-cell town oscillation share the
        # existing store retry bound; real inventory/gold progress resets it.
        progress = (stage, snapshot.player.gold,
                    tuple((it.slot, it.name, it.count) for it in snapshot.inventory))
        if getattr(self, "_opening_q1_progress", None) != progress:
            self._opening_q1_progress = progress
            self._opening_q1_positions = {}
        position = snapshot.player.position
        visits = self._opening_q1_positions
        visits[position] = visits.get(position, 0) + 1
        if visits[position] >= STORE_STUCK_LIMIT:
            return self._opening_q1_stop("no-progress:" + stage)
        if store is not None:
            step = self._shopping_approach_step(snapshot, store_type=store,
                                                requester="quest-request")
            if step is None:
                return self._opening_q1_stop("supplier-route-unavailable:" + stage)
            self.last_reason = "shop:approach"
            key = self._shopping_approach_key(snapshot, step, "shop:travel")
            return key if key is not None else self._opening_q1_stop("supplier-operation-unavailable:" + stage)
        self._opening_q1_kit_bought = True
        if not self._fixed_quest_ready(snapshot, 1):
            return self._opening_q1_stop("readiness:" + str(self._fixed_quest_readiness))
        key = self._fixed_quest_key(snapshot, hostiles)
        return key if key is not None else self._opening_q1_stop("quest-request-unavailable")
