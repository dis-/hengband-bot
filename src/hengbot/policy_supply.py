from __future__ import annotations

from collections import deque
from dataclasses import replace

from hengbot.model import (
    STORE_ALCHEMIST, STORE_HOME, STORE_MAGIC, STORE_WEAPON,
    SV_LITE_FEANOR, SV_LITE_LANTERN, SV_LITE_TORCH,
    SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE,
    SV_STAFF_IDENTIFY, SV_WAND_STONE_TO_MUD, SV_WAND_TELEPORT_AWAY,
    TVAL_ARROW, TVAL_BOLT, TVAL_DIGGING, TVAL_FOOD, TVAL_LITE,
    TVAL_SCROLL, TVAL_SHOT, TVAL_STAFF, TVAL_WAND,
    InventoryItem, MonsterState, Position, Snapshot, StoreItem,
)
from hengbot.policy_constants import (
    BREEDER_CONTAINMENT_WINDOW, CURE_CRITICAL_REQUIRED_DEPTH,
    DOWN_STAIRS_KEY, EAT_KEY, FOOD_MIN_SVAL, FOOD_STOCK_TARGET,
    FOOD_TYPE_MANA, IDENTIFY_CHARGE_FLOOR, IDENTIFY_STAFF_LEVEL,
    LANTERN_DIM_WARNING_FUEL, LANTERN_REFILL_FUEL, LEAVE_STORE_KEY,
    MANA_FOOD_CHARGE_TARGET, MANA_FOOD_DEVICE_TARGET, OIL_TARGET,
    PACK_CAPACITY, QUEST_STATUS_UNTAKEN, STAFF_IDENTIFY_MAX_COUNT,
    STAFF_IDENTIFY_MIN_CHARGES, STAFF_IDENTIFY_MIN_DEPTH,
    SUMMONER_CHOKE_NEIGHBORS, SUPPLY_STORES, TELEPORT_REQUIRED_DEPTH,
    TORCH_REFILL_FUEL, UP_STAIRS_KEY, USE_DEVICE_MIN, WAIT_KEY,
)
from hengbot.policy_types import SupplyStatus
from hengbot.quest_strategies import StrategyProfile


class SupplyMixin:

    def _owns_usable_permanent_light(self, snapshot: Snapshot) -> bool:
        """Return whether carried gear or the known Home catalog has permanent light."""
        if any(
            item.tval == TVAL_LITE
            and item.sval >= SV_LITE_FEANOR
            and not item.is_cursed
            and not item.is_broken
            for item in (*snapshot.inventory, *snapshot.equipment)
        ):
            return True
        return any(
            owned.item.tval == TVAL_LITE
            and owned.item.sval >= SV_LITE_FEANOR
            and owned.exploration_legal
            for owned in self._equipment_catalog.items
        )

    def _light_refill_item(self, snapshot: Snapshot) -> InventoryItem | None:
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is None:
            return None
        # Fuel is only reported for identified lights.  For an unidentified
        # lantern, use actual illumination of the player's square as the empty
        # signal: this avoids wasting oil while it still burns, but recovers
        # once the redacted-fuel lantern really goes dark.
        if not equipped.known:
            here = snapshot.grid_at(snapshot.player.position)
            if (
                not equipped.is_lantern
                or snapshot.dungeon_level < 1
                or snapshot.player.blind
            ):
                return None
            if here is None:
                if not snapshot.grids_observed:
                    return None
            elif here.lit:
                return None
            return self._first_item(snapshot, lambda it: it.is_oil and it.fuel > 0)
        if equipped.is_lantern:
            if equipped.fuel > LANTERN_REFILL_FUEL:
                return None
            return self._first_item(snapshot, lambda it: it.is_oil and it.fuel > 0)
        if equipped.sval == 0:
            if equipped.fuel > TORCH_REFILL_FUEL:
                return None
            return self._first_item(
                snapshot,
                lambda it: it.is_light and it.sval == 0 and it.fuel > 0,
            )
        return None

    def _unknown_light_last_resort(self, snapshot: Snapshot) -> bool:
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is None:
            return True
        if snapshot.in_town or not equipped.known:
            return False
        if equipped.sval > SV_LITE_LANTERN:
            return False
        if equipped.fuel > LANTERN_DIM_WARNING_FUEL:
            return False
        if self._light_refill_item(snapshot) is not None:
            return False
        return self._find_light(snapshot, include_unknown=False) is None

    def _supply_ledger(self, snapshot: Snapshot, depth: int) -> dict[str, SupplyStatus]:
        """Compute counts, thresholds and present-town obtainability once.

        An unvisited supplier has unknown stock/price and is optimistically
        obtainable.  When currently inside that supplier we have exact shelf
        and price knowledge, so only an affordable matching ware counts.
        """
        mana_food = snapshot.player.food_type == FOOD_TYPE_MANA
        counts = {
            "recall": self._count_recall_scrolls(snapshot),
            "teleport": self._count_teleport_scrolls(snapshot),
            "cure": self._count_cure_critical_potions(snapshot),
            "oil": self._oil_departure_count(snapshot),
            "food": (
                min(
                    self._count_mana_food_uses(snapshot),
                    MANA_FOOD_CHARGE_TARGET
                    if self._count_mana_food_devices(snapshot) >= MANA_FOOD_DEVICE_TARGET
                    else MANA_FOOD_CHARGE_TARGET - 1,
                )
                if mana_food
                else self._count_food(snapshot)
            ),
        }
        statuses: dict[str, SupplyStatus] = {}
        supplier_pages = dict(getattr(self, "_town_supplier_stock", {}))
        if snapshot.store is not None and snapshot.store.store_type != STORE_HOME:
            supplier_pages[snapshot.store.store_type] = snapshot.store
        for kind, count_value in counts.items():
            stores = (
                (STORE_MAGIC,)
                if kind == "food" and mana_food
                else SUPPLY_STORES[kind]
            )
            candidates = [
                supplier
                for supplier in stores
                if supplier not in self._town_store_attempted
                and supplier not in supplier_pages
            ]
            evidenced_stores = [
                supplier
                for supplier in stores
                if supplier in supplier_pages
                and any(
                    (
                        item.tval in {TVAL_WAND, TVAL_STAFF} and item.pval > 0
                        if kind == "food" and mana_food
                        else self._store_item_is_supply(item, kind)
                    )
                    and (
                        supplier not in self._town_store_attempted
                        or item.price <= snapshot.player.gold
                    )
                    for item in supplier_pages[supplier].items
                )
            ]
            home_has_supply = bool(
                self._home_knowledge_current
                and any(
                    (
                        item.tval in {TVAL_WAND, TVAL_STAFF} and item.pval > 0
                        if kind == "food" and mana_food
                        else self._store_item_is_supply(item, kind)
                    )
                    for item in self._home_knowledge_items
                )
            )
            status_stores = tuple(dict.fromkeys(
                ((STORE_HOME,) if home_has_supply else ()) + tuple(stores)
            ))
            obtainable = bool(home_has_supply or evidenced_stores or candidates)
            threshold_depth = max(depth, self._planned_depth()) if kind == "teleport" else depth
            if kind == "recall":
                required_return = required_departure = (
                    0
                    if self._fundraising_mode in {"mine", "scavenge"}
                    else self._recall_required_target(snapshot)
                )
            else:
                required_return = self._supply_threshold(
                    kind, "return", threshold_depth
                )
                required_departure = self._supply_threshold(
                    kind, "departure", threshold_depth
                )
            if kind == "oil" and self._owns_usable_permanent_light(snapshot):
                # Permanent lights consume no fuel. Oil therefore stops being
                # expedition stock as soon as a usable permanent light is owned,
                # including one already catalogued in Home during this visit.
                required_return = required_departure = 0
            elif kind == "food" and mana_food:
                required_return = required_departure = MANA_FOOD_CHARGE_TARGET
            statuses[kind] = SupplyStatus(
                kind, count_value, required_return, required_departure,
                obtainable, status_stores,
            )
        return statuses

    def _count_mana_food_uses(self, snapshot: Snapshot) -> int:
        carried_charges = sum(
            self._stack_charges(it)
            for it in snapshot.inventory
            if it.known and it.is_wand_staff and it.charges > 0
        )
        home_charges = sum(
            self._stack_charges(it)
            for it in self._home_knowledge_items
            if self._home_knowledge_current
            and it.known
            and InventoryItem.is_wand_staff.fget(it)
            and it.charges > 0
            and self._item_signature(it) not in self._deferred_home_items
        )
        known_charges = carried_charges + home_charges
        if snapshot.player.food_state in {"weak", "fainting"}:
            return known_charges
        identify_charges = sum(
            self._stack_charges(it)
            for it in snapshot.inventory
            if it.known
            and it.tval == TVAL_STAFF
            and it.sval == SV_STAFF_IDENTIFY
            and it.charges > 0
        )
        return known_charges - min(IDENTIFY_CHARGE_FLOOR, identify_charges)

    def _count_mana_food_devices(self, snapshot: Snapshot) -> int:
        carried = sum(
            it.count
            for it in snapshot.inventory
            if it.known and it.is_wand_staff and it.charges > 0
        )
        home = sum(
            it.count
            for it in self._home_knowledge_items
            if self._home_knowledge_current
            and it.known
            and InventoryItem.is_wand_staff.fget(it)
            and it.charges > 0
            and self._item_signature(it) not in self._deferred_home_items
        )
        return carried + home

    def _light_ready(self, snapshot: Snapshot) -> bool:
        if self._planned_depth() >= 2 and not self._owns_lantern(snapshot):
            return False
        if self._owns_usable_permanent_light(snapshot):
            return True
        lanterns = [
            item
            for item in (*snapshot.inventory, *snapshot.equipment)
            if item.is_lantern
        ]
        if any(item.known for item in lanterns):
            return (
                self._count_oil(snapshot) >= OIL_TARGET
                or any(item.fuel > LANTERN_REFILL_FUEL for item in lanterns)
            )
        if lanterns:
            return not self._oil_below_departure_target(snapshot)
        return self._count_usable_torches(snapshot) >= FOOD_STOCK_TARGET

    def _expedition_light_ready(self, snapshot: Snapshot) -> bool:
        equipped = next((item for item in snapshot.equipment if item.is_light), None)
        if equipped is None:
            return False
        if equipped.sval > SV_LITE_LANTERN:
            return True
        if not equipped.known:
            return (
                equipped.is_lantern
                and not self._oil_below_departure_target(snapshot)
            )
        # Normal lights warn below 100 fuel at ten-step marks
        # (src/object/lite-processor.cpp:73).
        if equipped.fuel >= LANTERN_DIM_WARNING_FUEL:
            return True
        return self._light_refill_item(snapshot) is not None

    def _identify_staff_ready(self, snapshot: Snapshot) -> bool:
        # A loot-collecting quest (its reviewed profile opts in with
        # carry_identify_staff) needs a carried Identify staff regardless of the
        # planned depth: it lets the in-quest sweep identify unknown drops and
        # free pack slots instead of abandoning collectible loot on a full pack.
        strategy = self._carry_procurement_strategy(snapshot)
        quest_requires_identify = (
            strategy is not None
            and bool(strategy.engagement_plan.get("carry_identify_staff"))
        )
        if (
            self._planned_depth() < STAFF_IDENTIFY_MIN_DEPTH
            and not quest_requires_identify
        ):
            return True
        charges = self._total_identify_staff_charges(snapshot)
        if charges >= STAFF_IDENTIFY_MIN_CHARGES:
            return True
        # Twenty charges is the preferred 10F+ departure stock, not a reason to
        # wait indefinitely for shop turnover. After checking the Magic shop,
        # a still-usable staff is the safe minimum for this town visit.
        return charges > 0 and STORE_MAGIC in self._town_store_attempted

    def procurement_requirements(self, snapshot: Snapshot) -> list[dict[str, int | str]]:
        """Return currently unmet item targets for logs and the policy viewer."""
        requirements: list[dict[str, int | str]] = []
        ledger = self._supply_ledger(snapshot, self._planned_depth())

        def require(item: str, current: int, target: int) -> None:
            if current < target:
                requirements.append(
                    {
                        "item": item,
                        "current": current,
                        "target": target,
                        "missing": target - current,
                    }
                )

        require(
            "Word of Recall scrolls",
            ledger["recall"].count,
            ledger["recall"].required_departure,
        )
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            require(
                "Device charges for food",
                ledger["food"].count,
                ledger["food"].required_departure,
            )
        else:
            require(
                "Food rations",
                ledger["food"].count,
                ledger["food"].required_departure,
            )

        if self._planned_depth() >= 2:
            require("Brass lantern", int(self._owns_lantern(snapshot)), 1)
            require(
                "Flasks of oil",
                ledger["oil"].count,
                ledger["oil"].required_departure,
            )
        elif self._owns_lantern(snapshot):
            require(
                "Flasks of oil",
                ledger["oil"].count,
                ledger["oil"].required_departure,
            )
        else:
            require(
                "Usable light sources",
                self._count_usable_torches(snapshot),
                FOOD_STOCK_TARGET,
            )

        if self._planned_depth() >= TELEPORT_REQUIRED_DEPTH:
            require(
                "Teleport scrolls",
                ledger["teleport"].count,
                ledger["teleport"].required_departure,
            )
        if self._planned_depth() >= CURE_CRITICAL_REQUIRED_DEPTH:
            require(
                "Cure Critical Wounds potions",
                ledger["cure"].count,
                ledger["cure"].required_departure,
            )

        mining_requirements = self._fundraising_mining_requirements(snapshot)
        if mining_requirements is not None:
            detection_target, digger_target = mining_requirements
            require(
                "Treasure Detection scrolls",
                self._count_treasure_detection_scrolls(snapshot),
                detection_target,
            )
            require(
                "Digging tool",
                self._digging_tool_count(snapshot),
                digger_target,
            )

        if self._identification_need is not None:
            full = self._identification_need == "full"
            current = int(
                self._find_identification_source(
                    snapshot,
                    full=full,
                    reliable_only=self._identification_requires_reliable_source(
                        snapshot
                    ),
                )
                is not None
            )
            require("*Identify* source" if full else "Identify source", current, 1)

        if self._planned_depth() >= STAFF_IDENTIFY_MIN_DEPTH:
            require(
                "Identify staff charges",
                self._total_identify_staff_charges(snapshot),
                STAFF_IDENTIFY_MIN_CHARGES,
            )

        strategy = self._carry_procurement_strategy(snapshot)
        if strategy is not None:
            labels = {
                "launcher": "Quest launcher",
                "throwing_items.lit_torch": "Quest throwing torches",
                "throwing_items.shot": "Quest shots",
                "throwing_items.arrow": "Quest arrows",
                "throwing_items.bolt": "Quest bolts",
                "throwing_items.launcher_ammo": "Quest launcher ammunition",
                "required_scrolls.light": "Quest Light scrolls",
                "required_scrolls.teleport": "Quest Teleport scrolls",
                "utility_tools.wall_breach": "Quest wall-breach tools",
            }
            for name, status in self._quest_carry_status(
                snapshot, strategy.required_force
            ).items():
                if name in self._abandoned_quest_carry_requirements:
                    continue
                require(
                    labels.get(name, f"Quest carry: {name}"),
                    int(status["measured"]),
                    int(status["required"]),
                )

        supply_labels = {
            "Word of Recall scrolls": "recall",
            "Food rations": "food",
            "Device charges for food": "food",
            "Flasks of oil": "oil",
            "Teleport scrolls": "teleport",
            "Cure Critical Wounds potions": "cure",
        }
        for requirement in requirements:
            kind = supply_labels.get(str(requirement["item"]))
            if kind is not None and not ledger[kind].obtainable:
                requirement["blocked_reason"] = "no-actionable-supplier"

        return requirements

    def _find_surplus_identify_staff(
        self, snapshot: Snapshot, *, pending_home_sale: bool = False
    ) -> InventoryItem | None:
        staffs = [
            item
            for item in snapshot.inventory
            if item.known
            and item.tval == TVAL_STAFF
            and item.sval == SV_STAFF_IDENTIFY
        ]
        if (
            not pending_home_sale
            and sum(item.count for item in staffs) <= STAFF_IDENTIFY_MAX_COUNT
        ):
            return None

        # Preserve the MANA-food reserve when another staff can be sold. A
        # single stacked slot may itself exceed the cap, so it remains eligible.
        reserve_slot = self._device_food_reserve_slot(snapshot)
        candidates = [item for item in staffs if item.slot != reserve_slot]
        if not candidates:
            candidates = staffs
        candidates = [
            item
            for item in candidates
            if self._item_signature(item) not in self._town_visit_purchases
            and self._retention_surplus(snapshot, item) >= item.count
        ]
        if not candidates:
            return None
        total_identify_charges = sum(self._stack_charges(item) for item in staffs)

        def preserves_identify(item: InventoryItem) -> bool:
            return (
                total_identify_charges - self._stack_charges(item)
                >= STAFF_IDENTIFY_MIN_CHARGES
            )

        candidates = [item for item in candidates if preserves_identify(item)]
        if not candidates:
            return None
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            total_food_charges = sum(
                self._stack_charges(item)
                for item in snapshot.inventory
                if item.known and item.is_wand_staff and item.charges > 0
            )
            total_devices = self._count_mana_food_devices(snapshot)
            required_food = self._supply_ledger(
                snapshot, self._planned_depth()
            )["food"].required_departure

            def remains_restocked(item: InventoryItem) -> bool:
                stack_charges = self._stack_charges(item)
                identify_charges = total_identify_charges - stack_charges
                food_charges = total_food_charges - stack_charges
                edible_charges = food_charges - min(
                    IDENTIFY_CHARGE_FLOOR, identify_charges
                )
                return (
                    identify_charges >= STAFF_IDENTIFY_MIN_CHARGES
                    and edible_charges >= required_food
                    and total_devices - item.count >= MANA_FOOD_DEVICE_TARGET
                )

            candidates = [item for item in candidates if remains_restocked(item)]
            if not candidates:
                return None
        return min(
            candidates,
            key=lambda item: (
                item.charges,
                self._stack_charges(item),
                item.slot,
            ),
        )

    def _identify_staff_success_rate(self, snapshot: Snapshot) -> float:
        """Model a carried Staff of Identify's activation chance (0..1).

        Mirrors use-execution.cpp: chance = skill_dev - item_level, and the use
        fails when chance < USE_DEVICE or randint1(chance) < USE_DEVICE, so the
        success probability is (chance - 2) / chance.  Town identification is
        never confused, so the confusion halving is omitted.
        """
        chance = snapshot.player.device_skill - IDENTIFY_STAFF_LEVEL
        if chance < USE_DEVICE_MIN:
            return 0.0
        return (chance - 2) / chance

    def _mana_food_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_MAGIC:
            return None
        if (
            self._home_identify_staff_sold_this_magic_visit
            and not snapshot.player.hungry
        ):
            # Do not buy a replacement device in the same visit that is
            # liquidating Home's legacy Identify-staff hoard. Starvation remains
            # the sole exception; an immediately edible charge outranks cleanup.
            return None
        candidates = [
            it for it in store.items
            if it.tval in {TVAL_WAND, TVAL_STAFF}
            and it.price <= snapshot.player.gold
        ]
        if not candidates:
            return None
        identify_slots = sum(
            1
            for item in snapshot.inventory
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
        )
        compliant = [
            item
            for item in candidates
            if not (
                item.tval == TVAL_STAFF
                and item.sval == SV_STAFF_IDENTIFY
                and identify_slots >= 2
            )
        ]
        if compliant:
            candidates = compliant
        elif snapshot.player.food_state not in {"weak", "fainting"}:
            # Preserve the explicit two-slot ceiling.  A weak/fainting character
            # may cross it only when the shelf has no compliant charged device.
            return None
        food = self._supply_ledger(snapshot, self._planned_depth())["food"]
        shortage = max(1, food.required_departure - food.count)

        def utility_rank(item: StoreItem) -> int:
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY:
                return 0
            if (
                item.tval == TVAL_WAND
                and item.sval in {SV_WAND_STONE_TO_MUD, SV_WAND_TELEPORT_AWAY}
            ):
                return 1
            return 2

        def charge_count(item: StoreItem) -> int:
            # Full Home/Museum item JSON and older fixtures expose pval; ordinary
            # store parsing populates both fields from the visible name.
            return max(1, item.charges, item.pval)

        # User directive (2026-07-17): pack slots beat small gold savings.
        # Minimize devices/slots first (highest charges), prefer a device the
        # policy can actually use when slot-equivalent, and compare price last.
        # Ordinary-store JSON used to omit charges; a name without a parseable
        # count remains visible and purchasable with a conservative estimate.
        return min(
            candidates,
            key=lambda it: (
                (shortage + charge_count(it) - 1) // charge_count(it),
                utility_rank(it),
                -charge_count(it),
                it.price,
                it.letter,
            ),
        )

    @staticmethod
    def _procurement_class(item: StoreItem | InventoryItem) -> tuple[int, int]:
        """Stable requested ware marker; matching follows consumer equivalence."""
        return (item.tval, item.sval)

    @staticmethod
    def _procurement_class_matches(
        item: StoreItem | InventoryItem, item_class: tuple[int, int]
    ) -> bool:
        """Match the same need category used by the eventual consumer."""
        tval, sval = item_class
        if tval == TVAL_FOOD and sval >= FOOD_MIN_SVAL:
            return item.tval == TVAL_FOOD and item.sval >= FOOD_MIN_SVAL
        if tval in {TVAL_WAND, TVAL_STAFF}:
            return item.is_wand_staff
        if tval in {TVAL_SHOT, TVAL_ARROW, TVAL_BOLT}:
            return item.tval == tval
        if tval == TVAL_DIGGING:
            return item.tval == TVAL_DIGGING
        if tval == TVAL_SCROLL and sval == SV_SCROLL_REMOVE_CURSE:
            return item.tval == TVAL_SCROLL and item.sval in {
                SV_SCROLL_REMOVE_CURSE,
                SV_SCROLL_STAR_REMOVE_CURSE,
            }
        return (item.tval, item.sval) == item_class

    @staticmethod
    def _procurement_equivalence(item_class: tuple[int, int]) -> str:
        tval, sval = item_class
        if tval == TVAL_FOOD and sval >= FOOD_MIN_SVAL:
            return "food:tval-food+sval-gte-min"
        if tval in {TVAL_WAND, TVAL_STAFF}:
            return "device:is-wand-staff"
        if tval in {TVAL_SHOT, TVAL_ARROW, TVAL_BOLT}:
            return "ammo:exact-tval-any-sval"
        if tval == TVAL_DIGGING:
            return "digger:exact-tval-any-sval"
        if tval == TVAL_SCROLL and sval == SV_SCROLL_REMOVE_CURSE:
            return "remove-curse:normal-or-star"
        return "item:exact-tval-sval"

    def _procurement_missing_amount(
        self, snapshot: Snapshot, item: StoreItem
    ) -> int:
        """Return the unmet amount from the same ledgers that drive procurement."""
        item_class = self._procurement_class(item)
        strategy = self._carry_procurement_strategy(snapshot)
        target = self._quest_carry_target_for_item(
            snapshot, item, strategy.required_force if strategy is not None else {}
        )
        if target is not None:
            return max(0, target[2] - target[1])
        kind = next(
            (name for name in SUPPLY_STORES if self._store_item_is_supply(item, name)),
            None,
        )
        if (
            kind is None
            and snapshot.player.food_type == FOOD_TYPE_MANA
            and item.tval in {TVAL_WAND, TVAL_STAFF}
            and item.pval > 0
        ):
            kind = "food"
        if kind is not None:
            status = self._supply_ledger(snapshot, self._planned_depth())[kind]
            return max(0, status.required_departure - status.count)
        if item_class == (TVAL_LITE, SV_LITE_TORCH):
            return max(0, FOOD_STOCK_TARGET - self._count_usable_torches(snapshot))
        if item.is_treasure_detection_scroll:
            requirements = self._fundraising_mining_requirements(snapshot)
            if requirements is None:
                return 0
            return max(
                0,
                requirements[0]
                - self._count_treasure_detection_scrolls(snapshot),
            )
        if item.is_digging_tool:
            requirements = self._fundraising_mining_requirements(snapshot)
            if requirements is None:
                return 0
            return max(0, requirements[1] - self._digging_tool_count(snapshot))
        return 1

    def _carry_procurement_strategy(self, snapshot: Snapshot) -> StrategyProfile | None:
        """Return the level-shaped torch mandate or next-quest requirements."""
        if not snapshot.in_town:
            return None
        quest = self._fixed_quest_head(snapshot)
        if snapshot.player.level >= 10:
            if (
                quest is None
                or quest.id == 1
                or quest.status != QUEST_STATUS_UNTAKEN
            ):
                return None
            profile = self.approved_quest_strategy(quest.id)
        else:
            profile = (
                self.approved_quest_strategy(quest.id)
                if quest is not None and quest.status == QUEST_STATUS_UNTAKEN
                else self._quest_strategy_for_errand_or_floor(snapshot)
            )
        selected = (
            replace(
                profile,
                required_force=self._strategy_force_for_snapshot(snapshot, profile),
            )
            if isinstance(profile, StrategyProfile)
            else None
        )
        if profile is not None and selected is None:
            return profile
        if snapshot.player.level < 10:
            opening = self.approved_quest_strategy(1)
            if opening is not None:
                opening_force = self._strategy_force_for_snapshot(snapshot, opening)
                opening_torches = int(
                    opening_force.get("throwing_items", {}).get("lit_torch", 0)
                )
                base = selected or opening
                force = dict(base.required_force)
                throwing = dict(force.get("throwing_items", {}))
                throwing["lit_torch"] = max(
                    opening_torches, int(throwing.get("lit_torch", 0))
                )
                force["throwing_items"] = throwing
                selected = replace(base, required_force=force)
        return selected

    def _mana_food_loot_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Recover visible device food before stairs or an ordinary return."""
        if (
            snapshot.in_town
            or snapshot.floor_key[2] != 0
            or snapshot.player.food_type != FOOD_TYPE_MANA
            or len(snapshot.inventory) >= PACK_CAPACITY
            or (
                self._count_mana_food_devices(snapshot) >= MANA_FOOD_DEVICE_TARGET
                and self._count_mana_food_uses(snapshot) >= MANA_FOOD_CHARGE_TARGET
            )
            or self._loot_block_reason(snapshot, hostiles) is not None
        ):
            return None

        candidates = {
            grid.position
            for grid in snapshot.grids.values()
            if grid.object_count > 0
            and grid.passable
            and (
                not grid.object_tvals
                or any(tval in {TVAL_WAND, TVAL_STAFF} for tval in grid.object_tvals)
            )
        }
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.position in candidates:
            return self._current_floor_item_key(
                snapshot,
                pickup_reason="mana-food:pickup-device",
                trigger_reason="mana-food:trigger-autodestroy",
            )

        step = self._nearest_position_step(snapshot, candidates)
        if step is None:
            return None
        self.last_reason = "mana-food:seek-device"
        return self._step_toward(snapshot, step)

    def _find_edible(self, snapshot: Snapshot) -> InventoryItem | None:
        # Race-dependent: MANA races (undead/constructs) drain wand/staff charges
        # for hunger; everyone else eats food. Eat with the same 'E' command.
        # The emitter hides `charges` until an item is identified, so also try
        # unidentified devices (the game allows eating any wand/staff; a known
        # empty one is skipped, an unknown one is worth the attempt) — but prefer
        # a device we know still has charges.
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            charged = [
                it
                for it in snapshot.inventory
                if it.is_wand_staff and it.known and it.charges > 0
            ]
            non_utility = [it for it in charged if not self._is_useful_device(it)]
            if non_utility:
                return min(non_utility, key=lambda it: (-it.count, -it.charges, it.slot))

            utility = [
                it
                for it in charged
                if not (
                    it.tval == TVAL_STAFF
                    and it.sval == SV_STAFF_IDENTIFY
                )
            ]
            if utility:
                return min(utility, key=lambda it: (-it.count, -it.charges, it.slot))

            identify = [
                it
                for it in charged
                if it.tval == TVAL_STAFF and it.sval == SV_STAFF_IDENTIFY
            ]
            identify_total = sum(self._stack_charges(it) for it in identify)
            if identify and (
                snapshot.player.food_state in {"weak", "fainting"}
                or identify_total > IDENTIFY_CHARGE_FLOOR
            ):
                return min(
                    identify,
                    key=lambda it: (self._stack_charges(it), it.charges, it.slot),
                )
            return self._first_item(
                snapshot, lambda it: it.is_wand_staff and not it.known
            )
        return self._first_item(
            snapshot, lambda it: it.is_food and it.aware and it.sval >= FOOD_MIN_SVAL
        )

    def _survival_gate_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Starvation safety, independent of mode and objective (R1).

        Hungry with something edible: eat now (the old step-7 eat was dead
        whenever a descent target was known, because step 6 returned first).
        Hungry with NOTHING edible: the expedition is over no matter what the
        current objective thinks — latch the town return and route home. Quest
        exit locks are respected via _return_to_town_key's own guards.
        """
        player = snapshot.player
        if not player.hungry:
            return None
        # Only a NEARBY threat defers the gate: a monster merely visible across
        # the floor may never engage at all, and waiting on it indefinitely is
        # how eating gets starved out of the schedule.
        near_hostiles = [
            monster for monster in hostiles if monster.distance <= 4
        ]
        food = self._find_edible(snapshot)
        if snapshot.in_town:
            if food is not None:
                self.last_reason = "town:eat-before-travel"
                return EAT_KEY + food.slot
            step = self._shopping_approach_step(snapshot)
            if step is not None:
                self.last_reason = "survival:shop-approach"
                return self._shopping_approach_key(
                    snapshot, step, "survival:shop-travel"
                )
            return None
        if food is not None:
            # Mid-fight, finishing the threat comes first — unless already
            # fainting, where one more fighting turn may be one too many.
            if near_hostiles and not player.fainting:
                return None
            self.last_reason = "survival:eat"
            return EAT_KEY + food.slot
        if near_hostiles:
            return None  # fight/flee first; re-fires on the next quiet decision
        key = self._return_to_town_key(snapshot, hostiles)
        if key is not None:
            return key
        # A quest exit lock refused the ordinary return. While merely "hungry"
        # the quest may still be finished first, but weak-or-worse means
        # starvation (paralysis death with full HP) is now closer than any
        # kill count: leave via the exit stairs and take the visible loss.
        if player.food_state not in {"weak", "fainting"}:
            return None
        here = snapshot.grid_at(player.position)
        exit_reason = (
            "survival:stairs-quest-fail"
            if self._quest_exit_would_fail(snapshot)
            else "survival:ascend"
        )
        if here is not None and self._is_upstairs_target(here):
            self._defer_descent(snapshot)
            self.last_reason = exit_reason
            return UP_STAIRS_KEY
        step = self._nearest_goal_step(snapshot, self._is_upstairs_target)
        if step is not None:
            self.last_reason = "survival:seek-exit"
            return self._step_toward(snapshot, step)
        return None

    def _mana_food_survival_override_key(self, snapshot: Snapshot) -> str | None:
        """Hard weak/fainting MANA-food acquisition and absorption owner.

        This owner sits above every ordinary town/dungeon wait producer.  A
        MANA race receives no nutrition from TVAL_FOOD: only a wand/staff
        charge is an eligible route.  Store purchase retains the established
        observe/re-enter one-shot contract by delegating an open Magic-shop
        page to ``_shop``.
        """
        if (
            snapshot.player.food_type != FOOD_TYPE_MANA
            or not snapshot.player.hungry
        ):
            return None

        edible = self._find_edible(snapshot)
        if edible is not None:
            self._home_procurement_probe = None
            self.last_reason = "survival:mana-absorb"
            return EAT_KEY + edible.slot

        # Home is the universal first supplier.  Stale knowledge means "scan",
        # never absence; only a current complete catalogue may release a buy.
        home_device = self._home_mana_food_candidate()
        self._home_procurement_fallthrough_equivalence = "device:is-wand-staff"
        home_needed = not self._home_knowledge_current or home_device is not None
        if not home_needed:
            self._home_procurement_probe = None
            self._home_procurement_fallthrough = "fresh-catalogue-absence"
        home_bearing_town = self._current_town_has_home(snapshot)
        if home_needed and home_bearing_town and self._home_available(snapshot):
            self._home_procurement_probe = (-1, -1)
            if home_device is not None:
                identity = self._item_signature(home_device)
                self._home_pending_item = identity
                self._home_pending_quantity = 1
            self._rearm_town_store_for_new_work(
                STORE_HOME, release_visit_bound=True
            )
            filed = self._ensure_home_visit_request(snapshot)
            step = (
                self._shopping_approach_step(snapshot, STORE_HOME)
                if filed else None
            )
            self._home_procurement_approach_state = {
                "home_available": True,
                "home_visit_filed": filed,
                "home_approach_step_is_none": step is None,
            }
            if filed and step is not None:
                self.last_reason = "survival:mana-home-approach"
                return self._shopping_approach_key(
                    snapshot, step, "survival:mana-home-travel"
                )
            self._home_procurement_probe = None
            self.last_reason = "town:blocked:survival-mana-no-charges"
            return WAIT_KEY
        elif home_needed and home_bearing_town:
            self._home_procurement_approach_state = {
                "home_available": False,
                "home_visit_filed": False,
                "home_approach_step_is_none": True,
            }
            self._home_procurement_probe = None
            self.last_reason = "town:blocked:survival-mana-no-charges"
            return WAIT_KEY
        elif home_needed:
            self._home_procurement_probe = None
            self._home_procurement_fallthrough = "town-without-home"

        if snapshot.store is not None:
            if snapshot.store.store_type in {
                STORE_MAGIC, STORE_ALCHEMIST, STORE_WEAPON
            }:
                return None
            self.last_reason = "survival:mana-leave-wrong-store"
            return LEAVE_STORE_KEY

        if (
            self._mana_survival_device_price is not None
            and snapshot.player.gold < self._mana_survival_device_price
        ):
            for sale_store in (STORE_ALCHEMIST, STORE_WEAPON):
                if self._mana_survival_sale_candidate(snapshot, sale_store) is None:
                    continue
                step = self._shopping_approach_step(snapshot, sale_store)
                if step is not None:
                    self.last_reason = "survival:mana-sale-approach"
                    return self._shopping_approach_key(
                        snapshot, step, "survival:mana-sale-travel"
                    )

        if STORE_MAGIC not in self._town_store_attempted:
            step = self._shopping_approach_step(snapshot, STORE_MAGIC)
            if step is not None:
                self.last_reason = "survival:mana-shop-approach"
                return self._shopping_approach_key(
                    snapshot, step, "survival:mana-shop-travel"
                )

        floor_key = self._mana_food_floor_pickup_key(snapshot)
        if floor_key is not None:
            return floor_key

        self.last_reason = "town:blocked:survival-mana-no-charges"
        return WAIT_KEY

    def _mana_food_floor_pickup_key(self, snapshot: Snapshot) -> str | None:
        """Use the existing mana-food pickup owner without dungeon-only gates."""
        candidates = {
            grid.position
            for grid in snapshot.grids.values()
            if grid.object_count > 0
            and grid.passable
            and (
                not grid.object_tvals
                or any(tval in {TVAL_WAND, TVAL_STAFF} for tval in grid.object_tvals)
            )
        }
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.position in candidates:
            return self._current_floor_item_key(
                snapshot,
                pickup_reason="mana-food:pickup-device",
                trigger_reason="mana-food:trigger-autodestroy",
            )
        step = self._nearest_position_step(snapshot, candidates)
        if step is None:
            return None
        self.last_reason = "mana-food:seek-device"
        return self._step_toward(snapshot, step)

    def _wilderness_survival_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str:
        """Reach a town through local and global wilderness without fighting.

        The bot only reaches here by straying off a town border, so it is likely
        under-levelled for whatever roams this tile. Nearby monsters are fled;
        when safe, '<' opens the global map and a road-biased route reaches town.
        stall trips the loop detector, which stops the bot for investigation —
        far better than marching deeper or trading blows with an out-of-depth
        monster).
        """
        player = snapshot.player
        global_map = self._wilderness_map
        if self._on_global_wilderness_map(snapshot):
            key = global_map.next_key_to_town(player.position.y, player.position.x)
            if key == DOWN_STAIRS_KEY:
                self.last_reason = "wilderness:enter-town"
                return key
            if key is not None:
                self.last_reason = "wilderness:global-travel"
                return key
            self.last_reason = "wilderness:no-safe-route"
            return WAIT_KEY

        nearby_hostiles = [
            monster
            for monster in hostiles
            if not monster.asleep and monster.distance <= 20
        ]
        if nearby_hostiles:
            step = self._flee_step(snapshot, nearby_hostiles)
            if step is not None:
                self.last_reason = "wilderness:flee"
                return self._step_toward(snapshot, step)
            if not player.blind and not player.confused:
                scroll = self._escape_scroll(snapshot)
                if scroll is not None:
                    self.last_reason = "wilderness:escape-scroll"
                    return self._read_key(snapshot, scroll)
        self.last_reason = "wilderness:enter-global"
        return UP_STAIRS_KEY

    def _unseen_reverse_choke_step(self, snapshot: Snapshot) -> Position | None:
        origin = snapshot.player.position
        direction = self._unseen_retreat_direction
        if direction is None:
            return self._least_visited_neighbor(snapshot)
        reverse_dy, reverse_dx = direction

        def projection(position: Position) -> int:
            return (
                (position.y - origin.y) * reverse_dy
                + (position.x - origin.x) * reverse_dx
            )

        first_steps = sorted(
            (
                neighbor
                for neighbor in self._walkable_neighbors(snapshot, origin)
                if projection(neighbor) > 0
            ),
            key=lambda position: (
                -projection(position),
                self._visit_counts[position],
            ),
        )
        queue: deque[tuple[Position, Position]] = deque(
            (position, position) for position in first_steps
        )
        seen = {origin, *first_steps}
        while queue:
            position, first_step = queue.popleft()
            if self._open_neighbor_count(snapshot, position) <= (
                SUMMONER_CHOKE_NEIGHBORS - 1
            ):
                self._unseen_retreat_target = position
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, position):
                if neighbor in seen or projection(neighbor) <= 0:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, first_step))
        self._unseen_retreat_target = None
        return first_steps[0] if first_steps else None

    def _unseen_retreat_intercept_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        if (
            self._unseen_retreat_floor != snapshot.floor_key
            or self._unseen_choke_position != snapshot.player.position
            or self._unseen_wait_remaining <= 0
            or not hostiles
        ):
            return None
        self._unseen_wait_intercepted = True
        if adjacent and not snapshot.player.afraid:
            self.last_reason = "melee:choke"
            return self._direction_key(
                snapshot.player.position, self._weakest(adjacent).position
            )
        self.last_reason = "melee:choke-hold"
        return WAIT_KEY

    def _unseen_retreat_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        eligible_hit = (
            self._took_damage
            and self._unseen_attack_evidence is not None
            and not self._took_curse_damage
            and not self._took_trap_or_terrain_damage
            and not snapshot.visible_monsters
            and not player.poisoned
            and not player.cut
        )
        active = self._unseen_retreat_floor == snapshot.floor_key
        if not eligible_hit and not active:
            return None

        if not active:
            self._unseen_retreat_floor = snapshot.floor_key
            self._unseen_retreat_direction = self._recent_reverse_direction(
                player.position
            )
            self._unseen_retreat_target = None
            self._unseen_choke_position = None
            self._unseen_wait_remaining = 0
            self._unseen_wait_intercepted = False
            self._escape_state.enter("unseen", "unseen:reverse-choke")

        if self._unseen_wait_intercepted and not hostiles:
            self._unseen_wait_intercepted = False
            self._unseen_wait_remaining = BREEDER_CONTAINMENT_WINDOW

        if self._unseen_choke_position is not None:
            if eligible_hit:
                self._unseen_choke_position = None
                self._unseen_wait_remaining = 0
                self._unseen_retreat_target = None
            elif player.position == self._unseen_choke_position:
                if self._unseen_wait_remaining > 0:
                    self._unseen_wait_remaining -= 1
                    self.last_reason = "unseen:choke-wait"
                    return WAIT_KEY
                self._clear_unseen_retreat()
                return None
            else:
                self._clear_unseen_retreat()
                return None

        at_target = (
            self._unseen_retreat_target == player.position
            and self._open_neighbor_count(snapshot, player.position)
            <= SUMMONER_CHOKE_NEIGHBORS - 1
        )
        if at_target and not self._took_damage:
            self._unseen_choke_position = player.position
            self._unseen_wait_remaining = BREEDER_CONTAINMENT_WINDOW - 1
            self.last_reason = "unseen:choke-wait"
            return WAIT_KEY
        if at_target:
            self._unseen_retreat_target = None

        step = None
        if self._unseen_retreat_target is not None:
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.position == self._unseen_retreat_target,
            )
        if step is None:
            step = self._unseen_reverse_choke_step(snapshot)
        if step is not None:
            self.last_reason = "unseen:reverse-choke"
            return self._step_toward(snapshot, step)
        return None

    def _nearest_goal_step(self, snapshot: Snapshot, predicate) -> Position | None:
        """Uniform-cost BFS returning the first step toward the nearest goal.

        The start tile is allowed to be the goal's neighbour; goal tiles are
        matched by ``predicate`` and may themselves be non-walkable (e.g. a
        downstairs is walkable, but a "tile adjacent to a monster" goal lands on
        a normal floor).
        """
        start = snapshot.player.position
        entrance_cells = self._town_entrance_cells(snapshot)
        entrance_cells.difference_update(
            pos
            for pos, grid in snapshot.grids.items()
            if predicate(grid)
        )
        entrance_cells.discard(start)
        for blocked_entrances in (entrance_cells, set()):
            for allow_damaging in (False, True):
                seen = {start}
                queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
                while queue:
                    pos, first_step = queue.popleft()
                    grid = snapshot.grids.get(pos)
                    if pos != start and grid is not None and predicate(grid):
                        return first_step
                    for neighbor in self._walkable_neighbors(
                        snapshot, pos, allow_damaging=allow_damaging, goal=predicate
                    ):
                        if (
                            neighbor in seen
                            or neighbor in self._engagement_avoid_cells
                            or neighbor in blocked_entrances
                        ):
                            continue
                        seen.add(neighbor)
                        queue.append(
                            (neighbor, neighbor if first_step is None else first_step)
                        )
        return None

    def _nearest_goal_and_step(
        self, snapshot: Snapshot, predicate
    ) -> tuple[Position, Position] | None:
        """Return both the selected BFS goal and its first approach step."""
        start = snapshot.player.position
        for allow_damaging in (False, True):
            seen = {start}
            queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
            while queue:
                pos, first_step = queue.popleft()
                grid = snapshot.grids.get(pos)
                if pos != start and grid is not None and predicate(grid):
                    assert first_step is not None
                    return pos, first_step
                for neighbor in self._walkable_neighbors(
                    snapshot, pos, allow_damaging=allow_damaging, goal=predicate
                ):
                    if neighbor in seen or neighbor in self._engagement_avoid_cells:
                        continue
                    seen.add(neighbor)
                    queue.append(
                        (neighbor, neighbor if first_step is None else first_step)
                    )
        return None
