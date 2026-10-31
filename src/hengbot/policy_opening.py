"""The Q34 reward -> mining kit -> Q1 transaction.

Shelf observations and the existing quest contract are the only price/count sources.
The route retains its kit choice across purchases and checkpoints.
"""
from hengbot.model import (
    STORE_GENERAL, STORE_WEAPON, STORE_BLACK, STORE_ALCHEMIST, STORE_TEMPLE,
    StoreState,
    SV_POTION_HEALING, SV_POTION_SPEED, TVAL_POTION,
)
from hengbot.policy_types import TownNeed
from hengbot.policy_constants import (
    STORE_STUCK_LIMIT, REST_MACRO,
    FUNDRAISING_DIGGER_BASE_PRICE, FUNDRAISING_DETECTION_BASE_PRICE,
    QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN, QUEST_STATUS_REWARDED,
    QUEST_STATUS_FINISHED,
)
from hengbot.item_reservation import decision_memo
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.quest_strategies import acceptance_dps_floor, acceptance_hp_floor, carry_floor
from hengbot.claim_register import ClaimOwner, claims
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY


# Requirement category -> the required_force carry it counts (carry_floor).
Q1_CARRIES = {"quest-throwing-items": "lit_torch", "quest-healing": "heal_potions",
              "quest-speed": "speed_potions"}


def _q1_offer(matches, item):
    """A shelf row that serves a requirement (a torch only with fuel)."""
    return item.count > 0 and matches(item) and not (item.is_torch and item.fuel <= 0)


def _q1_reserve(requirements, offers):
    """(gold to buy every missing unit, first purchase, unstocked category)."""
    reserve, first = 0, None
    for category, target, current, matches in requirements:
        missing = max(0, target - current)
        for store, item in sorted(offers, key=lambda row: row[1].price):
            if not missing or not _q1_offer(matches, item):
                continue
            quantity = min(missing, item.count)
            reserve += quantity * item.price
            missing -= quantity
            if first is None:
                first = (category, store, item, quantity)
        if missing:
            return reserve, first, category
    return reserve, first, None


def _q1_affordable_targets(requirements, offers, gold, floor):
    """carry name -> lowered target: the floor, then what the rest of ``gold`` buys.

    Owner 2026-10-31 「Q1の要求値を下げ、受注可能にする」: each category is
    first bought up to its floor (``carry_floor``, never above its full
    target); the gold left then buys further units toward the full targets in
    requirement order, cheapest first.  None when the floors cost more than
    ``gold``.
    """
    left = {id(item): item.count for _, item in offers}
    rows = sorted(offers, key=lambda row: row[1].price)

    def buy(matches, units, budget):
        bought = spent = 0
        for _, item in rows:
            while (bought < units and left[id(item)] > 0 and _q1_offer(matches, item)
                   and (budget is None or spent + item.price <= budget)):
                left[id(item)] -= 1
                bought, spent = bought + 1, spent + item.price
        return bought, spent

    targets, budget = {}, gold
    for category, target, current, matches in requirements:
        name = Q1_CARRIES[category]
        lowest = min(target, floor.get(name, target))
        bought, spent = buy(matches, max(0, lowest - current), None)
        targets[name], budget = current + bought, budget - spent
        if targets[name] < lowest:
            return None
    if budget < 0:
        return None
    for category, target, current, matches in requirements:
        name = Q1_CARRIES[category]
        bought, spent = buy(matches, max(0, target - targets[name]), budget)
        targets[name] += bought
        budget -= spent
    return targets


class OpeningRouteMixin:
    def _opening_q1_active(self, snapshot):
        # The transaction needs protocol-3 stock/skill/light observations.
        # Legacy checkpoints retain their existing, independent town owners.
        if (getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) < PROTOCOL_SCREEN_PARITY
                or not getattr(snapshot, "quests", None)):
            return False
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
        """The Q1 carries, at the counts the route lowered them to (if it did)."""
        full = self._opening_q1_full_requirements(snapshot)
        carry = getattr(self, "_quest_carry_lowered", None)
        if carry is None or carry[0] != 1:
            return full
        return tuple((category, min(target, carry[1].get(Q1_CARRIES[category], target)),
                      current, matches)
                     for category, target, current, matches in full)

    def _opening_q1_full_requirements(self, snapshot):
        return decision_memo(
            self, "opening-q1-requirements", snapshot, (),
            lambda: self._opening_q1_requirements_uncached(snapshot),
        )

    def _opening_q1_requirements_uncached(self, snapshot):
        profile = self.approved_quest_strategy(1)
        force = self._strategy_force_for_snapshot(snapshot, profile, lowered=False)
        # Ask the same DPS/HP calculation as readiness. Carries may still fail;
        # its measurements are nevertheless populated before that rejection.
        previous = self._fixed_quest_readiness
        self._fixed_quest_readiness = {}
        try:
            self._approved_strategy_force_ready(snapshot, profile)
            measured = self._fixed_quest_readiness["strategy_force"]
        finally:
            self._fixed_quest_readiness = previous
        # The same class-resolved tier floors as readiness (QUEST_1 class 16).
        tier = force.get("no_healing_tier", {})
        class_id = snapshot.player.class_id
        no_heal = bool(tier and snapshot.player.max_hp >= acceptance_hp_floor(tier, class_id)
                       and measured["dps"]["measured"] >= acceptance_dps_floor(tier, class_id))
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

    @claims(ClaimOwner.SHOP_BUY, census_only=True)
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
        # Acceptance commits the optional kit shopping. Mandatory quest
        # reserves still get replenished if they become short before entry.
        quest = self._known_fixed_quests(snapshot).get(1)
        accepted = quest is not None and quest.status == QUEST_STATUS_TAKEN
        requirements = self._opening_q1_full_requirements(snapshot)
        pages = self._opening_q1_pages(snapshot)
        suppliers = []
        if requirements[0][1] > requirements[0][2]:
            suppliers.append((STORE_GENERAL, "quest-throwing-items"))
        # Optional kit surveys must never displace Q1 on an empty purse.
        # Known offers take precedence over the existing base-price estimates.
        if (not accepted and not getattr(self, "_opening_q1_kit_bought", False)
                and not any(target > current for _, target, current, _ in requirements)):
            for store, category, floor in (
                (STORE_GENERAL, "fundraising-digger", FUNDRAISING_DIGGER_BASE_PRICE),
                (STORE_WEAPON, "fundraising-digger", FUNDRAISING_DIGGER_BASE_PRICE),
                (STORE_BLACK, "fundraising-digger", FUNDRAISING_DIGGER_BASE_PRICE),
                (STORE_ALCHEMIST, "fundraising-detection", FUNDRAISING_DETECTION_BASE_PRICE),
            ):
                if (store in pages or snapshot.player.gold >= floor):
                    suppliers.append((store, category))
        if requirements[1][1] > requirements[1][2]:
            suppliers.append((STORE_TEMPLE, "quest-healing"))
            suppliers.append((STORE_BLACK, "quest-healing"))
        if requirements[2][1] > requirements[2][2]:
            suppliers.append((STORE_BLACK, "quest-speed"))
        reachable = [(store, category) for store, category in suppliers
                     if self._town_need_supplier_reachable(snapshot, TownNeed(store, category, "normal"))]
        for store, category in reachable:
            if store not in pages:
                return "observe:" + category, store, None, 0, 0
        offers = [(store, item) for store, _ in reachable
                  for item in pages[store].items if item.count > 0]
        diggers = [(store, item) for store, item in offers
                   if item.is_digging_tool and not self._equip_blocked_by_identification(item)]
        owned = [item for item in (*snapshot.inventory, *snapshot.equipment)
                 if item.is_digging_tool and not self._equip_blocked_by_identification(item)]
        reserve, first, unstocked = _q1_reserve(requirements, offers)
        if unstocked is not None:
            return "stop:stock:" + unstocked, None, None, 0, 0
        self._quest_carry_lowered = None
        if reserve > snapshot.player.gold:
            # 「Q1の要求値を下げ、受注可能にする」 (owner 2026-10-31): buy what the
            # gold allows down to the strategy's carry floor; readiness and
            # entry read the same lowered counts (_strategy_force_for_snapshot).
            lowered = _q1_affordable_targets(
                requirements, offers, snapshot.player.gold,
                carry_floor(self.approved_quest_strategy(1).required_force,
                            snapshot.player.class_id))
            if lowered is None:
                return ("stop:unaffordable-quest-reserve", None, None, 0,
                        reserve - snapshot.player.gold)
            self._quest_carry_lowered = (1, lowered)
            reserve, first, _ = _q1_reserve(self._opening_q1_requirements(snapshot), offers)
        if first is not None:
            category, store, item, quantity = first
            return category, store, item, quantity, 0
        if not getattr(self, "_opening_q1_kit_bought", False):
            affordable = [(store, item) for store, item in diggers
                          if item.price <= snapshot.player.gold]
            if affordable:
                store, item = max(affordable, key=lambda row: self._digging_tool_sale_quality(row[1]))
                if not owned or self._digging_tool_sale_quality(item) > max(
                        self._digging_tool_sale_quality(it) for it in owned):
                    return "fundraising-digger", store, item, 1, 0
            second = self._opening_q1_second_digger(snapshot, diggers, owned, offers)
            if second is not None:
                store, item = second
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

    def _opening_q1_second_digger(self, snapshot, diggers, owned, offers):
        """A Magic-Eater's second kit digger, or None.

        Digging power counts each wielded TR_TUNNEL pval*20 and each hand's
        non-heavy weapon weight/10 (calc_skill_dig), so mining wields a
        digger in both hands (fundraise:wield-digger).  The Q1 reserves are
        already met before the kit is considered; the second digger keeps
        the price of one Treasure Detection scroll for the minimum kit.  An
        unaffordable second digger is left to the next town visit (the
        fundraising two-digger target).  Owner 2026-10-30: one shovel made
        the Magic-Eater's first mining run slow.
        """
        if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
            return None
        carried = sum(max(1, item.count) for item in owned)
        if carried != 1:
            return None
        reserve = 0
        if self._count_treasure_detection_scrolls(snapshot) <= 0:
            prices = [item.price for _, item in offers if item.is_treasure_detection_scroll]
            if not prices:
                return None
            reserve = min(prices)
        affordable = [(store, item) for store, item in diggers
                      if item.price + reserve <= snapshot.player.gold]
        if not affordable:
            return None
        return max(affordable, key=lambda row: (self._digging_tool_sale_quality(row[1]),
                                                -row[1].price))

    def _opening_q1_purchase(self, snapshot):
        if snapshot.store is None:
            return None
        _, store, ware, _, _ = self._opening_q1_plan(snapshot)
        if store != snapshot.store.store_type:
            return None
        # A cached letter is never an address on a different observed page.
        return next((item for item in snapshot.store.items if item == ware), None)

    @claims(ClaimOwner.QUEST_REQUEST, census_only=True)
    def _opening_q1_stop(self, detail):
        self._opening_q1_failure = detail
        self.last_reason = "quest:blocked:opening-route"
        # An empty envelope cannot activate a building beneath the player.
        return ""

    @claims(ClaimOwner.QUEST_REQUEST, census_only=True)
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
            if key is not None:
                return key
            # A completed pickup clears the latch and yields no key of its
            # own; the purchases for Q1 continue on this same board.
            if self._fixed_quest_reward_pending is not None:
                return self._opening_q1_stop("reward-unavailable")
        head = self._fixed_quest_head(snapshot)
        if head is not None and head.id != 1:
            return self._opening_q1_stop("competing-quest:" + str(head.id))
        self._opening_q1_funding = None
        self._opening_q1_funding_left = False
        self._supply_stockout_gold_target = None
        self._fundraising_mode = None
        self._planned_mining_runs = None
        stage, store, ware, quantity, debt = self._opening_q1_plan(snapshot)
        if stage.startswith("stop:"):
            return self._opening_q1_stop(stage)
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
        # Settle town combat before shopping travel can pull us away again.
        # Otherwise the shop step and mob approach undo one another forever.
        if store is not None or self._physical_adjacent_hostiles(snapshot):
            combat = self._town_kill_mob_key(snapshot)
            if combat is not None:
                return combat
            adjacent = [monster for monster in hostiles
                        if snapshot.player.position.distance_to(monster.position) <= 1
                        and not self._step_raises_unintended_confirm(snapshot, monster.position)]
            if adjacent and self._can_fight_in_dungeon(0):
                self.last_reason = "melee"
                return self._direction_key(snapshot.player.position, self._weakest(adjacent).position)
        if store is not None:
            step = self._shopping_approach_step(snapshot, store_type=store,
                                                requester="quest-request")
            if step is None:
                return self._opening_q1_stop("supplier-route-unavailable:" + stage)
            self.last_reason = "shop:approach"
            key = self._shopping_approach_key(snapshot, step, "shop:travel")
            return key if key is not None else self._opening_q1_stop("supplier-operation-unavailable:" + stage)
        self._opening_q1_kit_bought = True
        light = self._light_judgment(snapshot)
        fuel_required = self._q1_visit_light_fuel(snapshot)
        if (not light.one_shot_quest_entry_ready
                and not (light.worn is not None and light.worn.known
                         and light.worn.fuel >= fuel_required)):
            torch_reserve = self._opening_q1_requirements(snapshot)[0][1]
            candidates = [item for item in snapshot.inventory
                          if item.is_light and item.known and item.fuel >= fuel_required
                          and not item.is_cursed and not item.is_broken
                          and (not item.is_torch
                               or self._count_throwing_torches(snapshot) > torch_reserve)]
            if candidates:
                item = max(candidates, key=lambda item: item.fuel)
                self.last_reason = "opening-q1:equip-light"
                key = self._equipment_wield(snapshot, "light-loadout", item, "light")
                return key if key is not None else self._opening_q1_stop("light-equip-unavailable")
        if snapshot.player.hp < snapshot.player.max_hp:
            if hostiles:
                combat = self._town_kill_mob_key(snapshot)
                if combat is not None:
                    return combat
                adjacent = [monster for monster in hostiles
                            if snapshot.player.position.distance_to(monster.position) <= 1
                            and not self._step_raises_unintended_confirm(snapshot, monster.position)]
                if adjacent:
                    if not self._can_fight_in_dungeon(0):
                        return self._opening_q1_stop("recovery-hostile-unreachable")
                    self.last_reason = "melee"
                    return self._direction_key(snapshot.player.position, self._weakest(adjacent).position)
                return self._opening_q1_stop("recovery-hostile-unreachable")
            self.last_reason = "town:recover"
            return REST_MACRO
        # Taken quests are checked at the entrance by the same safety gate,
        # rather than rebuilding their combat model on every town step.
        if (head is None or head.status != QUEST_STATUS_TAKEN) and not self._fixed_quest_ready(snapshot, 1):
            return self._opening_q1_stop("readiness:" + str(self._fixed_quest_readiness))
        key = self._fixed_quest_key(snapshot, hostiles)
        if key is not None:
            return key
        operation = "quest-entry-unavailable" if head is not None and head.status == QUEST_STATUS_TAKEN else "quest-request-unavailable"
        return self._opening_q1_stop(operation)
