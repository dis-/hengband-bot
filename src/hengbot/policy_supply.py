from __future__ import annotations
from hengbot import combat_answer, destruction_use, goal_route, lamp_fuel, me_capability, me_staff_sequence, random_quest_reserve, unseen_strike, wilderness_exit
from hengbot import heroism_potion, quest_force_rows, torch_release, town_pack_headroom
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import (
    PLAYER_CLASS_MAGIC_EATER, awaiting_absorption, is_mana_food_ware, is_staple_food, mana_food_devices,
    staple_charges, staple_food,
)

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace

from hengbot.town_arbiter import ClaimOwner, claims
from hengbot.equipment_optimizer import q34_item_tagged
from hengbot.model import (
    STORE_ALCHEMIST, STORE_BLACK, STORE_HOME, STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON,
    SV_LITE_FEANOR, SV_LITE_LANTERN, SV_LITE_TORCH, lights_nothing,
    SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE,
    SV_STAFF_IDENTIFY, SV_WAND_STONE_TO_MUD, SV_WAND_TELEPORT_AWAY,
    SV_POTION_HEALING, SV_POTION_SPEED, TVAL_ARROW, TVAL_BOLT,
    TVAL_DIGGING, TVAL_FOOD, TVAL_LITE, TVAL_POTION, TVAL_SCROLL,
    TVAL_SHOT, TVAL_STAFF, TVAL_WAND, DUNGEON_YEEK_CAVE,
    InventoryItem, MonsterState, Position, Snapshot, StoreItem,
)
from hengbot.policy_constants import (
    CHOKE_ENGAGEMENT_MIN_DAMAGE_RATIO, CURE_CRITICAL_REQUIRED_DEPTH,
    DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
    DOWN_STAIRS_KEY, EAT_KEY, FOOD_MIN_SVAL, FOOD_STOCK_TARGET,
    FOOD_TYPE_MANA, IDENTIFY_CHARGE_FLOOR, IDENTIFY_STAFF_LEVEL,
    EMERGENCY_POTION_CARRY_TARGET, LANTERN_DIM_WARNING_FUEL,
    LANTERN_REFILL_FUEL, LEAVE_STORE_KEY, MANA_FOOD_CHARGE_TARGET,
    MANA_FOOD_DEVICE_TARGET, OIL_TARGET,
    PACK_CAPACITY, QUEST_STATUS_TAKEN, QUEST_STATUS_UNTAKEN, STAFF_IDENTIFY_MAX_COUNT,
    STAFF_IDENTIFY_MIN_CHARGES, STAFF_IDENTIFY_MIN_DEPTH,
    STARVING_FOOD_STATES, SUMMONER_CHOKE_NEIGHBORS, SUPPLY_LABEL_KINDS, SUPPLY_STORES,
    TELEPORT_REQUIRED_DEPTH,
    TORCH_REFILL_FUEL, TORCH_THROW_TARGET, UP_STAIRS_KEY, USE_DEVICE_MIN,
    WAIT_KEY, HOME_KNOWLEDGE_MACRO,
    permitted_dive_depth, required_destruction_uses,
)
from hengbot.policy_types import SupplyStatus, TownMapRoute
from hengbot.quest_strategies import StrategyProfile
from hengbot.town_hold import standing_claim


# Decision-row telemetry (cli._capture_decision_facts) evaluates the supply
# ledger hundreds of times per town decision with one board and one policy
# state.  While such an observer capture runs, this holds its private memo of
# ledger results; outside a capture it is None and every call recomputes.
_SUPPLY_LEDGER_OBSERVER_MEMO: ContextVar[dict | None] = ContextVar(
    "_SUPPLY_LEDGER_OBSERVER_MEMO", default=None
)


@dataclass(frozen=True)
class LightJudgment:
    """光源の問いへの一つの答え（光源と燃料の ROOT-FIX、#47）。

    worn: 装備中の光源。fuel_using: 燃料を使う光源（ランタン・たいまつ）。
    faint: 鑑定済みの燃料を使う光源の燃料が LANTERN_DIM_WARNING_FUEL 未満
    （ゲームの「明かりが微かになってきている」、lite-processor.cpp:71）。
    refill: 所持の補給品。swap: 付け替えられる光源。oil: 所持の油の数。
    """

    worn: InventoryItem | None
    fuel_using: bool
    faint: bool
    refill: InventoryItem | None
    swap: InventoryItem | None
    oil: int
    owns_lantern: bool
    owns_fuelless_light: bool

    @property
    def faint_without_refill(self) -> bool:
        return self.faint and self.refill is None

    @property
    def releases_one_shot_quest(self) -> bool:
        """USER DECISION 2026-10-25「油を持って入り、微かなら帰る」の B。

        微かで補給も付け替えもできなければ、一度きりのクエストの出口の鍵を解く。
        """
        return self.faint and self.refill is None and self.swap is None

    @property
    def one_shot_quest_entry_ready(self) -> bool:
        """Entry uses an oil-refillable lantern or an owned fuel-less light."""
        return self.one_shot_quest_entry_reject_reason is None

    @property
    def one_shot_quest_entry_reject_reason(self) -> str | None:
        """USER DECISION 2026-10-25 round 2: torches alone stay outside."""
        if self.owns_fuelless_light or not self.fuel_using:
            return None
        if not self.owns_lantern:
            return "light-torch-only"
        if self.oil < OIL_TARGET:
            return "light-oil"
        return None


@contextmanager
def supply_ledger_observer_memo():
    """Reuse supply-ledger results for the duration of one observer capture.

    Only for a pure observer (cli._PolicyObserverScope).  Results are keyed by
    the policy and board object identities, the depth argument and the ledger
    inputs the observer itself can write (_supply_ledger_observer_inputs), and
    the memo is dropped when the block exits: nothing carries across
    decisions or observations.  A read-only scan of one decision (the junk
    predicate's gates, the Home-full junk scan, #95) uses the same block; a
    nested block shares the outer one's memo.
    """
    if _SUPPLY_LEDGER_OBSERVER_MEMO.get() is not None:
        yield
        return
    token = _SUPPLY_LEDGER_OBSERVER_MEMO.set({})
    try:
        yield
    finally:
        _SUPPLY_LEDGER_OBSERVER_MEMO.reset(token)


class SupplyMixin:

    def _required_remove_curse_kind(self, snapshot: Snapshot) -> str | None:
        """Choose a cure for worn gear; failed strong removal proves permanence.

        Class 16 with the absorbed Remove Curse power needs no scroll: its
        Powerful Activation (me_powerful_activation) serves every curse, the
        *Remove Curse* scroll's (me_capability.REPLACES).
        """
        if me_capability.replaced_by_absorbed(
                self, snapshot, (TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE)):
            return None
        targets = [item for item in snapshot.equipment if item.is_cursed
                   and self._item_signature(item) not in
                   getattr(self, "_permanent_cursed_items", set())]
        if not targets:
            return None
        return ("star-remove-curse" if any(self._curse_unremovable(item)
                                          for item in targets)
                else "remove-curse")

    def _usable_remove_curse_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        kind = self._required_remove_curse_kind(snapshot)
        if kind is None:
            return None
        compatible = [item for item in snapshot.inventory
                      if item.aware and self._store_item_is_supply(item, kind)]
        # Preserve the existing carried-scroll preference when both kinds are
        # present; heavy curses still admit only the stronger kind.
        return next((item for item in compatible
                     if item.sval == SV_SCROLL_STAR_REMOVE_CURSE),
                    next(iter(compatible), None))

    def _home_remove_curse_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        kind = self._required_remove_curse_kind(snapshot)
        if kind is None or not self._home_knowledge_current:
            return None
        return next((item for item in self._home_knowledge_items[
                        :self._home_knowledge_valid_before]
                     if item.count > 0 and self._store_item_is_supply(item, kind)
                     and self._item_signature(item) not in self._deferred_home_items), None)

    def _remove_curse_service_available(self, snapshot: Snapshot) -> bool:
        """A concrete cure takes priority over starting an income trip."""
        kind = self._required_remove_curse_kind(snapshot)
        if kind is None:
            return False
        if (self._usable_remove_curse_scroll(snapshot) is not None
                or self._home_remove_curse_scroll(snapshot) is not None):
            return True
        pages = dict(self._town_supplier_stock)
        if snapshot.store is not None and snapshot.store.store_type != STORE_HOME:
            pages[snapshot.store.store_type] = snapshot.store
        return any(self._store_item_is_supply(item, kind)
                   and item.count > 0 and item.price <= snapshot.player.gold
                   for page in pages.values() for item in page.items)

    @staticmethod
    def _worn_light(snapshot: Snapshot) -> InventoryItem | None:
        """The worn light source, or None when none lights the player.

        A worn dark light (``lights_nothing``: ★火消しライター) fills the slot
        but lights nothing; every light rule treats it as no light (n1-b
        life-321 kept it, radius 0, and could not read in the dark).
        """
        worn = next((it for it in snapshot.equipment if it.is_light), None)
        return None if worn is None or lights_nothing(worn) else worn

    def _owns_usable_permanent_light(self, snapshot: Snapshot) -> bool:
        """Return whether a usable permanent light is in hand (worn or carried).

        A lamp catalogued only in Home lights nothing on the next floor: it
        counts once it is equipped or withdrawn (#82: oil was waived for a
        Home lamp the optimizer kept there, and the lantern ran dry).
        """
        return any(
            item.tval == TVAL_LITE
            and item.sval >= SV_LITE_FEANOR
            and not item.is_cursed
            and not item.is_broken
            and not lights_nothing(item)
            for item in (*snapshot.inventory, *snapshot.equipment)
        )

    def _light_refill_item(self, snapshot: Snapshot) -> InventoryItem | None:
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is None:
            return None
        # Fuel is only reported for identified lights.  An unidentified
        # lantern is refilled once the player sees it no longer lights them
        # and has not been told it is still full (lamp_fuel): this avoids
        # wasting oil while it still burns, but recovers once it goes dark.
        if not equipped.known:
            if (
                not equipped.is_lantern
                or snapshot.player.blind
                or lamp_fuel.refill_known_unneeded(self, snapshot)
            ):
                return None
            out = lamp_fuel.unidentified_lantern_out(snapshot)
            if out is None:
                # The own grid's lighting says nothing about the lantern in a
                # daylit town.  The light facts do (light_radius is the
                # player's own light, torch.cpp update_lite_radius): n1-b
                # life-330 stood in town with the Q34 lantern out and four
                # flasks of oil while a torch and the lantern swapped places.
                if snapshot.dungeon_level < 1:
                    return None
                # Older boards export neither light fact: the own grid's lighting.
                here = snapshot.grid_at(snapshot.player.position)
                out = snapshot.grids_observed if here is None else not here.lit
            if not out:
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

    def _town_light_out(self, snapshot: Snapshot) -> bool:
        """In town, the player's own light lights nothing (exported radius 0).

        torch.cpp update_lite_radius: a lantern or torch without fuel adds no
        radius.  Where the street is unlit the game then refuses every travel
        step (travel-execution.cpp decide_travel_step_dir: blind or
        ``no_lite`` 「目が見えない！」) and every scroll read.
        """
        return (snapshot.in_town and snapshot.light_radius == 0
                and not snapshot.player.blind)

    def _town_light_restore_key(self, snapshot: Snapshot) -> str | None:
        """Restore the light in town before any errand travels.

        n1-b life-343 (2026-11-08 04:54, Lv9, 50,284 gold): the lantern's last
        flask was poured on the floor, the lantern went out in town and the
        Magic-Eater staff sequence sent its inn travel from the lit Magic shop
        entrance; the game refused the next step in the dark street, the town
        progress invariant walked back to the shop and the travel went out
        again until town:blocked:owner-retired-burst.  The light rules already
        said the light was not ready (the supply ledger's oil row); the class
        sequences ahead of the shopping never let it be bought.

        Refuel from the pack, else a carried torch, else the walk to the
        supply ledger's oil store, ahead of the travels.
        """
        if snapshot.store is not None or not self._town_light_out(snapshot):
            return None
        refill = self._light_refill_item(snapshot)
        if refill is not None:
            self.last_reason = "refill-light"
            return reserved_item_command(self, snapshot, "refill", refill)
        torch = self._darkness_torch(snapshot)
        if torch is not None:
            self.last_reason = "wield-light"
            return self._equipment_wield(snapshot, "light-loadout", torch, "light")
        # The supply ledger's oil row names the store (the General Store); the
        # class sequences' travels wait until the walk has restored the light.
        oil = self._supply_ledger(snapshot, self._planned_depth()).get("oil")
        if (oil is None or not oil.obtainable or not oil.stores
                or oil.count >= oil.required_departure):
            return None
        if town_pack_headroom.organizing(self, snapshot):
            # The shelf refused the light buy for a slot and started the
            # inventory pass (make_room_for_refused_purchase): its shelving
            # walk goes first, or the walk re-enters the shop that refuses
            # (n1-c life-172 2026-11-08 20:12, town:blocked:owner-retired-burst).
            relief = town_pack_headroom.key(self, snapshot)
            if relief is not None:
                return relief
        step = self._shopping_approach_step(snapshot, oil.stores[0], requester="survival")
        if step is None:
            return None
        self.last_reason = "shop:approach"
        return self._shopping_approach_key(snapshot, step, "shop:travel")

    def _unknown_light_last_resort(self, snapshot: Snapshot) -> bool:
        if snapshot.in_town:
            return self._town_q34_lantern(snapshot) is not None
        equipped = self._worn_light(snapshot)
        if equipped is None:
            return True
        if not equipped.known:
            return False
        if equipped.sval > SV_LITE_LANTERN:
            return False
        if equipped.fuel > LANTERN_DIM_WARNING_FUEL:
            return False
        if self._light_refill_item(snapshot) is not None:
            return False
        return self._find_light(snapshot, include_unknown=False) is None

    def _town_q34_lantern(self, snapshot: Snapshot) -> InventoryItem | None:
        """The unidentified Q34 lantern to wear in town once the light burned out.

        Owner 2026-10-31 「Q34習得品も付けて良い」, and 2026-11-06 「町でも付けてよい」:
        n1-c life-141 stood in town with its torch at 0 turns beside the Q34
        lantern until town:blocked:survival:recall_departure_ready.  Only a
        light with nothing left to give is replaced: no worn light, or a worn
        torch or lantern known to be at 0 turns, and no known light or refill
        to take instead.
        """
        worn = self._worn_light(snapshot)
        if worn is not None and not (
                worn.known and worn.sval <= SV_LITE_LANTERN and worn.fuel <= 0):
            return None
        if (self._light_refill_item(snapshot) is not None
                or self._find_light(snapshot, include_unknown=False) is not None):
            return None
        return next((item for item in snapshot.inventory
                     if item.is_lantern and not item.known and not item.is_cursed
                     and q34_item_tagged(item)), None)

    def _supply_ledger(self, snapshot: Snapshot, depth: int) -> dict[str, SupplyStatus]:
        memo = _SUPPLY_LEDGER_OBSERVER_MEMO.get()
        if memo is None:
            return self._compute_supply_ledger(snapshot, depth)
        key = (id(self), id(snapshot), depth, self._supply_ledger_observer_inputs())
        hit = memo.get(key)
        if hit is not None and hit[0] is self and hit[1] is snapshot:
            return dict(hit[2])
        statuses = self._compute_supply_ledger(snapshot, depth)
        # The entry holds the policy and board so their ids cannot be reused.
        memo[key] = (self, snapshot, statuses)
        return dict(statuses)

    def _supply_ledger_observer_inputs(self) -> tuple:
        """The ledger inputs an observer capture itself can change.

        The facts evaluators write private copies of policy state, and a few of
        those writes reach state the ledger reads (a temporary fundraising-mode
        swap, the equipment-optimization depth, and deferred Home curse cures).
        Freeze the deferral set so in-place changes cannot mutate an old key.
        Keying
        the memo on them means such a write is a miss, never a stale hit.
        tests/test_supply_ledger_observer_memo.py pins this list against a
        static scan of what the capture writes and the ledger reads.
        """
        return (
            self._fundraising_mode,
            self._equipment_optimization_last_depth,
            frozenset(self._deferred_home_items),
            frozenset(self._town_store_attempted),
        )

    def _supply_store_obtainable(
        self, snapshot: Snapshot, kind: str, stores, supplier_pages=None,
    ) -> bool:
        """Whether a store (not Home) of ``stores`` may still supply ``kind``.

        A store neither attempted this visit nor seen is optimistically a
        supplier; a seen page is one when it evidences the ware
        (``_supply_page_offers``).  ``supplier_pages`` defaults to the visit's
        pages and the open store page, as the ledger reads them.
        """
        if supplier_pages is None:
            supplier_pages = dict(getattr(self, "_town_supplier_stock", {}))
            if snapshot.store is not None and snapshot.store.store_type != STORE_HOME:
                supplier_pages[snapshot.store.store_type] = snapshot.store
        return any(
            (
                supplier not in self._town_store_attempted
                and supplier not in supplier_pages
            )
            or (
                supplier in supplier_pages
                and self._supply_page_offers(
                    snapshot, kind, supplier, supplier_pages[supplier]
                )
            )
            for supplier in stores
        )

    def _supply_page_offers(
        self, snapshot: Snapshot, kind: str, store_type: int, page
    ) -> bool:
        """Whether ``page`` of ``store_type`` evidences a ``kind`` supplier.

        The ledger's one predicate for a known shelf, shared with the town
        planner's supply needs: a ware that supplies ``kind`` (for a MANA
        eater's food, a wand or staff with charges) that is either within
        the carried gold or on a store not yet attempted this visit.  A ware
        whose class the sell-rebuy churn guard refuses this visit
        (``_purchase_churn_rejected``) is no supplier: the purchase selector
        will not buy it however long the bot waits for restock (issue #68).
        """
        return any(
            self._supply_ware(snapshot, kind, store_type, item)
            and (
                store_type not in self._town_store_attempted
                or item.price <= snapshot.player.gold
            )
            for item in page.items
        )

    def _supply_ware(self, snapshot: Snapshot, kind: str, store_type: int, item) -> bool:
        """A ware of ``store_type`` that supplies ``kind`` at any price."""
        mana_food = (
            kind == "food"
            and snapshot.player.food_type == FOOD_TYPE_MANA
        )
        return (
            (
                is_mana_food_ware(self, snapshot, item) and item.pval > 0
                if mana_food
                else self._store_item_is_supply(item, kind)
            )
            and not self._purchase_churn_rejected(store_type, item)
        )

    def _visit_supplier_pages(self, snapshot: Snapshot) -> dict[int, object]:
        """The supplier pages seen this town visit (and the open page).

        The observations are reset at every fresh town arrival, so a page
        remembered from an earlier visit is not this visit's evidence.
        """
        town = self._effective_town_id(snapshot)
        observations = getattr(self, "_town_supplier_stock_observations", {})
        pages = {store_type: page
                 for store_type, page in getattr(self, "_town_supplier_stock", {}).items()
                 if (observed := observations.get(store_type)) is not None
                 and observed[0] == town}
        if snapshot.store is not None and snapshot.store.store_type != STORE_HOME:
            pages[snapshot.store.store_type] = snapshot.store
        return pages

    def _supply_purchase_gap(self, snapshot: Snapshot, kind: str) -> bool:
        """The ``kind`` shortage is a purchase gap the town end mines for.

        Home holds none, and either the supplier shelves seen sell the ware
        only above the carried gold, or (owner 2026-11-02 「品切れも採掘に回す」)
        every supplier was visited this visit and none sells it within the
        gold.  A supplier not yet visited this visit is the shopping's to
        visit first, so it keeps the shortage out of the gaps -- unless the
        shopping skips it on a shelf observed within its restock window
        (``_shelf_stop_tried``): n1-c life-112 (2026-11-03 00:35) found the
        Alchemist out of Cure Critical Wounds, the plan skipped the Temple on
        its earlier page, and the unvisited Temple kept the stockout out of
        the gaps, so the town end stopped instead of mining.
        """
        from hengbot.town_terminal import SUPPLY_KIND_BY_CATEGORY
        status = self._supply_ledger(snapshot, self._planned_depth()).get(kind)
        if (status is None or status.count >= status.required_departure
                or STORE_HOME in status.stores):
            return False
        pages = dict(getattr(self, "_town_supplier_stock", {}))
        if snapshot.store is not None:
            pages[snapshot.store.store_type] = snapshot.store
        prices = [item.price for store_type in status.stores if store_type in pages
                  for item in pages[store_type].items
                  if self._supply_ware(snapshot, kind, store_type, item)]
        if prices and min(prices) > snapshot.player.gold:
            return True
        visited = self._visit_supplier_pages(snapshot)
        category = next((category for category, each in SUPPLY_KIND_BY_CATEGORY.items()
                         if each == kind), kind)
        for store_type in status.stores:
            page = visited.get(store_type)
            if page is None and not self._shelf_stop_tried(snapshot, store_type, category):
                return False
            if page is not None and any(
                    self._supply_ware(snapshot, kind, store_type, item)
                    and item.price <= snapshot.player.gold for item in page.items):
                return False
        return True

    def _identify_staff_purchase_gap(self, snapshot: Snapshot) -> bool:
        """The Identify staff shortage is a purchase gap: the shelves seen sell
        it above the gold, or every supplier this visit is out of a staff
        that helps (``_identify_staff_unbuyable``, 「品切れも採掘に回す」)."""
        prices = [item.price for page in self._identify_staff_offer_pages(snapshot)
                  for item in page.items
                  if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY]
        if self._identify_staff_ready(snapshot):
            return False
        return ((bool(prices) and min(prices) > snapshot.player.gold)
                or self._identify_staff_unbuyable(snapshot))

    def _compute_supply_ledger(
        self, snapshot: Snapshot, depth: int
    ) -> dict[str, SupplyStatus]:
        """Compute counts, thresholds and present-town obtainability once.

        An unvisited supplier has unknown stock/price and is optimistically
        obtainable.  When currently inside that supplier we have exact shelf
        and price knowledge, so only an affordable matching ware counts.
        """
        mana_food = snapshot.player.food_type == FOOD_TYPE_MANA
        # Owner 2026-11-07 「普段より多くの食料を確保する」: the Zul trip's
        # round trip, doubled, on top of the usual departure amount.
        from hengbot import zul_trip
        trip_food = zul_trip.extra_food_items(self, snapshot)
        counts = {
            "recall": self._count_recall_means(snapshot),
            "teleport": self._count_teleport_scrolls(snapshot),
            "cure": self._count_cure_critical_potions(snapshot),
            "oil": self._oil_departure_count(snapshot),
            "food": (
                min(
                    self._count_mana_food_uses(snapshot),
                    MANA_FOOD_CHARGE_TARGET + trip_food
                    if self._count_mana_food_devices(snapshot)
                    >= self._mana_food_device_target(snapshot)
                    else MANA_FOOD_CHARGE_TARGET + trip_food - 1,
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
            store_obtainable = self._supply_store_obtainable(
                snapshot, kind, stores, supplier_pages)
            home_has_supply = bool(
                self._home_knowledge_current
                and any(
                    (
                        is_mana_food_ware(self, snapshot, item) and item.pval > 0
                        if kind == "food" and mana_food
                        else self._store_item_is_supply(item, kind)
                    )
                    for item in self._home_knowledge_items
                )
            )
            status_stores = tuple(dict.fromkeys(
                ((STORE_HOME,) if home_has_supply else ()) + tuple(stores)
            ))
            obtainable = bool(home_has_supply or store_obtainable)
            threshold_depth = max(depth, self._planned_depth()) if kind == "teleport" else depth
            if kind == "recall":
                required_return = (
                    0
                    if self._fundraising_mode in {"mine", "scavenge"}
                    else self._recall_required_target(snapshot)
                )
                required_departure = required_return
                if (
                    required_departure
                    and snapshot.in_town
                    and not snapshot.player.recalling
                    and self._fundraising_mode is None
                    # A destination refused for its landing (blocked guardian
                    # or depth gates) still reads a recall, to the switched
                    # landing.  Home retention and the departure board must
                    # agree on this scroll (user 2026-09-20: buy target + the
                    # one read at departure), before and after the switch.
                    and self._town_recall_destination(
                        snapshot, guardian_gate=False, safety_gate=False
                    )[0] is not None
                ):
                    # The departure action consumes one scroll before dungeon
                    # entry observes the standing expedition stock.  This is
                    # action input, not a change to the standing recall target.
                    required_departure += 1
            else:
                required_return = self._supply_threshold(
                    kind, "return", threshold_depth
                )
                required_departure = self._supply_threshold(
                    kind, "departure", threshold_depth
                )
            if kind == "teleport":
                required_departure = max(
                    required_departure,
                    random_quest_reserve.departure_requirement(self, snapshot),
                )
            if kind == "oil" and self._owns_usable_permanent_light(snapshot):
                # Permanent lights consume no fuel. Oil therefore stops being
                # expedition stock as soon as a usable permanent light is in
                # hand; one left in Home does not light the dungeon (#82).
                required_return = required_departure = 0
            elif kind == "food" and mana_food:
                required_return = required_departure = MANA_FOOD_CHARGE_TARGET
            if kind == "food":
                required_departure += trip_food
            statuses[kind] = SupplyStatus(
                kind, count_value, required_return, required_departure,
                obtainable, status_stores,
            )
        curse_kind = self._required_remove_curse_kind(snapshot)
        if curse_kind is not None:
            # Temple can sell the stronger scroll; ordinary Remove Curse is
            # supplied by the Alchemist.
            stores = (STORE_ALCHEMIST, STORE_TEMPLE, STORE_MAGIC, STORE_BLACK)
            home = self._home_remove_curse_scroll(snapshot)
            obtainable = home is not None or any(
                self._supply_page_offers(snapshot, curse_kind, store, supplier_pages[store])
                if store in supplier_pages else store not in self._town_store_attempted
                for store in stores
            )
            count = sum(item.count for item in snapshot.inventory
                        if item.aware and self._store_item_is_supply(item, curse_kind))
            statuses[curse_kind] = SupplyStatus(
                curse_kind, count, 0, 1, obtainable,
                (STORE_HOME,) if home is not None else stores,
            )
        return statuses

    def _count_mana_food_uses(self, snapshot: Snapshot) -> int:
        if staple_food(snapshot) is not None:
            # Owner 2026-10-30: the Wand of Wonder is the staple; its charges
            # alone are the food (a wand stack's pval is already its total).
            return staple_charges(snapshot)
        devices = mana_food_devices(self, snapshot)
        carried_charges = sum(self._stack_charges(it) for it in devices)
        # Home stock is a supplier, never food carried into the dungeon.
        if snapshot.player.food_state in {"weak", "fainting"}:
            return carried_charges
        identify_charges = sum(
            self._stack_charges(it)
            for it in devices
            if it.tval == TVAL_STAFF and it.sval == SV_STAFF_IDENTIFY
        )
        return carried_charges - min(IDENTIFY_CHARGE_FLOOR, identify_charges)

    def _count_mana_food_devices(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in mana_food_devices(self, snapshot))

    @staticmethod
    def _mana_food_device_target(snapshot: Snapshot) -> int:
        """Devices the food ledger wants: the staple ignores the elements.

        The second device guards food against elemental inventory damage; the
        Wand of Wonder (IGNORE_ACID/ELEC/FIRE/COLD) needs no such spare.
        """
        return 1 if staple_food(snapshot) is not None else MANA_FOOD_DEVICE_TARGET

    def _departure_oil_short(self, snapshot: Snapshot) -> bool:
        """Oil below the departure's five flasks, unless the worn Q34 lantern shows
        fuel (lamp_fuel.q34_worn_lantern_lit, owner 2026-11-06); the town and the
        floor ask the same question."""
        return (self._oil_below_departure_target(snapshot)
                and not lamp_fuel.q34_worn_lantern_lit(self, snapshot))

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
            return not self._departure_oil_short(snapshot)
        return self._count_usable_torches(snapshot) >= FOOD_STOCK_TARGET

    def _light_judgment(self, snapshot: Snapshot) -> LightJudgment:
        """光源の問い（使えるか・微かか・補給・付け替え・油）の一つの答え。

        出発の確認、一度きりのクエストの入場と出口の鍵、ダンジョンでの
        light-low の帰還と暗がりの歩きは、これを通して答える
        （tests/test_light_judgment_census.py が列挙した箇所を確かめる）。
        """
        worn = self._worn_light(snapshot)
        fuel_using = worn is not None and worn.sval <= SV_LITE_LANTERN
        # Normal lights warn below 100 fuel at ten-step marks
        # (src/object/lite-processor.cpp:71).
        faint = (
            fuel_using and worn.known and worn.fuel < LANTERN_DIM_WARNING_FUEL
        )
        refill = self._light_refill_item(snapshot)
        swap = None
        if faint and refill is None:
            swap = (
                self._darkness_torch(snapshot)
                or self._empty_lantern_to_restore(snapshot)
                or self._light_to_wield(snapshot)
            )
        return LightJudgment(
            worn=worn,
            fuel_using=fuel_using,
            faint=faint,
            refill=refill,
            swap=swap,
            oil=self._count_oil(snapshot),
            owns_lantern=any(
                item.is_lantern for item in (*snapshot.inventory, *snapshot.equipment)
            ),
            owns_fuelless_light=self._owns_usable_permanent_light(snapshot),
        )

    def _expedition_light_ready(self, snapshot: Snapshot) -> bool:
        equipped = self._worn_light(snapshot)
        if equipped is None:
            return False
        if equipped.sval > SV_LITE_LANTERN:
            return True
        judgment = self._light_judgment(snapshot)
        if not equipped.known:
            return (
                equipped.is_lantern
                and not self._departure_oil_short(snapshot)
            )
        return not judgment.faint_without_refill

    def _identify_staff_absorbed(self, snapshot: Snapshot) -> bool:
        """Whether an absorbed power stands in for the carried Identify staff.

        「以降、鑑定と財宝感知は取り込みで賄う」: the absorbed power is the
        Magic-Eater's Identify staff (it regenerates and refills);
        「鑑定の杖を21回取り込んだあとは…持ち物の要求からも外す」 also from the
        displayed list alone (the me_capability.REPLACES rows of the staff).
        The ordinary departure gate and the forced departure's minimum read
        this one rule.
        """
        return me_capability.replaced_by_absorbed(self, snapshot, (TVAL_STAFF, SV_STAFF_IDENTIFY))

    def _identify_staff_ready(self, snapshot: Snapshot, *, cache_fixed_quest_head=True) -> bool:
        # A loot-collecting quest (its reviewed profile opts in with
        # carry_identify_staff) needs a carried Identify staff regardless of the
        # planned depth: it lets the in-quest sweep identify unknown drops and
        # free pack slots instead of abandoning collectible loot on a full pack.
        strategy = (self._carry_procurement_strategy(snapshot)
                    if cache_fixed_quest_head else self._carry_procurement_strategy(
                        snapshot, cache_fixed_quest_head=False))
        quest_requires_identify = (
            strategy is not None
            and bool(strategy.engagement_plan.get("carry_identify_staff"))
        )
        charges = self._total_identify_staff_charges(snapshot)
        if self._identify_staff_absorbed(snapshot):
            return True
        if self._planned_depth() < STAFF_IDENTIFY_MIN_DEPTH:
            if not quest_requires_identify:
                return True
            return charges >= STAFF_IDENTIFY_MIN_CHARGES or (
                charges > 0 and STORE_MAGIC in self._town_store_attempted
            )
        return charges >= STAFF_IDENTIFY_MIN_CHARGES

    def _intended_dive_depth(self, snapshot: Snapshot) -> int:
        """The floor this departure intends to land on: the objective's recall
        arrival depth, and nothing else (user 2026-09-23
        「帰還先の到着階だけ（推奨）」).

        Not ``_planned_depth``: ``divable_depth`` caps that band at 49 while no
        *Destruction* method is carried, so keying the requirement on the band
        would be circular — the gate the purchase exists to open would hold the
        depth below the gate.  The live 2026-09-23 stop refused Angband's 50
        with the band still at 49, and the arrival depth is what it refused.

        Nor the deeper of the two: once one use is carried the band widens to
        the 50-80 rung, and taking the maximum would raise a 50F errand's
        requirement from 5 to 20 the moment the first scroll was bought.
        Going to 50F means 5 uses; going to 60F means 10.

        The answer is finally clamped by ``permitted_dive_depth``.  An
        objective the 50F+ rule forbids is not an intent anybody may act on:
        leaving it unclamped published a 5-use shortage for a depth the gate
        would refuse, which is what stopped the live bot at 22:49 on
        2026-09-23.  Clamping here, on the one helper the whole *Destruction*
        owner reads, keeps the requirement, the purchase, the Home-first
        withdrawal and the retention reservation all consistent with the rule --
        and all of them come back for a character holding the means.
        """
        holds_means = lambda: destruction_use.holds_means(self, snapshot)
        target = self._target_dungeon_id
        if target is None:
            return permitted_dive_depth(self._planned_depth(), holds_means)
        return permitted_dive_depth(
            self._dungeon_entry_depth(snapshot, target, via_recall=True), holds_means
        )

    def _required_destruction_uses(self, snapshot: Snapshot) -> int:
        return required_destruction_uses(self._intended_dive_depth(snapshot))

    def _missing_destruction_uses(self, snapshot: Snapshot) -> int:
        return max(
            0,
            self._required_destruction_uses(snapshot)
            - self._total_destruction_uses(snapshot),
        )

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

        curse_kind = self._required_remove_curse_kind(snapshot)
        if curse_kind is not None:
            status = ledger[curse_kind]
            require("*Remove Curse* scrolls" if curse_kind == "star-remove-curse"
                    else "Remove Curse scrolls", status.count, status.required_departure)

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

        destruction_target = self._required_destruction_uses(snapshot)
        if destruction_target:
            require(
                "*Destruction* uses",
                self._total_destruction_uses(snapshot),
                destruction_target,
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

        for requirement in requirements:
            kind = SUPPLY_LABEL_KINDS.get(str(requirement["item"]))
            if kind is not None and not ledger[kind].obtainable:
                requirement["blocked_reason"] = "no-actionable-supplier"

        return requirements

    @staticmethod
    def _carried_identify_staves(snapshot: Snapshot) -> list[InventoryItem]:
        """Known carried Identify staves; a stack's ``charges`` is per staff.

        Hengband stacks staves only when their charges are equal and keeps
        ``pval`` per staff (item-entity.cpp STAFF similarity; use-execution.cpp
        "You unstack your staff"), so a stack of N holds N * charges.
        """
        return [
            item
            for item in snapshot.inventory
            if item.known
            and item.tval == TVAL_STAFF
            and item.sval == SV_STAFF_IDENTIFY
        ]

    def _identify_staff_offer_pages(self, snapshot: Snapshot) -> list[object]:
        """Observed Identify-staff supplier pages of the current town."""
        return [page for store_type, page in self._visit_supplier_pages(snapshot).items()
                if store_type in {STORE_MAGIC, STORE_BLACK}]

    def _identify_staff_store_offer_charges(self, snapshot: Snapshot) -> int:
        """Most per-staff charges of an affordable observed shelf staff (0: none)."""
        return max(
            (
                max(item.charges, item.pval)
                for page in self._identify_staff_offer_pages(snapshot)
                for item in page.items
                if item.tval == TVAL_STAFF
                and item.sval == SV_STAFF_IDENTIFY
                and item.price <= snapshot.player.gold
            ),
            default=0,
        )

    def _identify_staff_acquisition_worthwhile(
        self, snapshot: Snapshot, charges: int
    ) -> bool:
        """Whether taking one more staff with ``charges`` helps under the cap.

        User 2026-10-03: at most STAFF_IDENTIFY_MAX_COUNT staves; 「20回分に
        届かない時は、回数の一番少ない杖を手放して店の回数の多い杖に買い替える」.
        A staff helps only when the charges kept after the release plan rises:
        at the cap only a staff fuller than the emptiest carried one does; a
        staff that fills the cap below 20 charges while a fuller affordable
        shelf staff is observed is itself the emptiest, so the swap would
        release it again at once (Home 3-charge staff, 2026-10-03 07:47).
        """
        if charges <= 0:
            return False
        staves = self._carried_identify_staves(snapshot)
        if sum(item.count for item in staves) + 1 < STAFF_IDENTIFY_MAX_COUNT:
            return True
        if staves and charges <= min(item.charges for item in staves):
            return False
        acquired = replace(
            staves[0], slot="identify-staff-acquisition", count=1,
            charges=charges, pval=charges,
        )
        after = replace(snapshot, inventory=[*snapshot.inventory, acquired])

        def kept_charges(board: Snapshot) -> int:
            # The plan is applied until it releases nothing more: an excess
            # release can leave four staves that the swap then thins again.
            for _ in range(len(board.inventory) + 1):
                release = self._identify_staff_release_plan(board)
                if not release:
                    break
                board = replace(board, inventory=[
                    replace(item, count=item.count - release[item.slot])
                    if item.slot in release else item
                    for item in board.inventory
                    if item.count > release.get(item.slot, 0)
                ])
            return sum(
                item.charges * item.count
                for item in self._carried_identify_staves(board)
            )

        return kept_charges(after) > kept_charges(snapshot)

    def _identify_staff_release_plan(self, snapshot: Snapshot) -> dict[str, int]:
        """Per-slot quantity of carried Identify staves to release (sell/Home).

        User 2026-10-03 (swap the emptiest staff for a fuller one): above
        STAFF_IDENTIFY_MAX_COUNT the excess goes fewest-charges first, even
        when the remaining charges fall below STAFF_IDENTIFY_MIN_CHARGES.  At
        the cap, below the charge requirement, the emptiest staff is released
        only when an affordable observed shelf staff has more charges, so the
        swap always raises the total.  Ties keep the MANA-food reserve slot.
        """
        staves = self._carried_identify_staves(snapshot)
        total = sum(item.count for item in staves)
        if not staves or total < STAFF_IDENTIFY_MAX_COUNT:
            return {}
        if total == STAFF_IDENTIFY_MAX_COUNT and not snapshot.in_town:
            # The swap is a town transaction against an observed shelf.
            return {}
        reserve_slot = self._device_food_reserve_slot(snapshot)
        if total > STAFF_IDENTIFY_MAX_COUNT:
            purchased = getattr(self, "_town_visit_purchases", set())
            # A staff bought this visit is kept first so the cap never sells
            # back what was just bought; then the fullest staves stay.
            keep_order = sorted(
                staves,
                key=lambda item: (
                    self._item_signature(item) not in purchased,
                    -item.charges,
                    item.slot != reserve_slot,
                    item.slot,
                ),
            )
            remaining = STAFF_IDENTIFY_MAX_COUNT
            release: dict[str, int] = {}
            for item in keep_order:
                kept = min(item.count, remaining)
                remaining -= kept
                if item.count > kept:
                    release[item.slot] = item.count - kept
            return release
        if self._identify_staff_ready(snapshot):
            return {}
        emptiest = min(
            staves,
            key=lambda item: (item.charges, item.slot == reserve_slot, item.slot),
        )
        offered = self._identify_staff_store_offer_charges(snapshot)
        if offered <= emptiest.charges:
            return {}
        # The swap's buy is a staff of other charges: one more slot, less the
        # one this sale frees only when it empties the stack.  Selling one of
        # two stacked staves before a buy the pack budget refuses only lost
        # charges (n1-b life-276 2026-10-31, 11 -> 9 before the stop).
        from hengbot.town_pack_budget import permits
        if permits(snapshot, 1 - (emptiest.count == 1)):
            return {emptiest.slot: 1}
        # Where only the whole stack leaves room for the buy, it goes while the
        # swap still raises the charges (n1-a life-487 19:14: 7, 6 and 2x3 with
        # 4x18 on the shelf and four free slots, the stop at 19 of 20).
        if permits(snapshot, 0) and offered > emptiest.charges * emptiest.count:
            return {emptiest.slot: emptiest.count}
        return {}

    def _home_full_relief_take_blocks_identify(
        self, snapshot: Snapshot, item: InventoryItem | StoreItem, quantity: int,
    ) -> bool:
        """Reserve Identify capacity against charged Home relief takes only."""
        if (item.tval != TVAL_STAFF or item.sval != SV_STAFF_IDENTIFY
                or max(item.charges, item.pval) <= 0
                or self._identify_staff_ready(snapshot)):
            return False
        carried = sum(staff.count for staff in self._carried_identify_staves(snapshot))
        return carried + quantity >= STAFF_IDENTIFY_MAX_COUNT

    def _find_surplus_identify_staff(
        self, snapshot: Snapshot, *, pending_home_sale: bool = False,
        for_weight_overload: bool = False,
    ) -> InventoryItem | None:
        staffs = self._carried_identify_staves(snapshot)
        release = self._identify_staff_release_plan(snapshot)
        if release:
            return self._find_capped_identify_staff_release(
                snapshot, staffs, release
            )
        if (
            not (pending_home_sale or for_weight_overload)
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
            if (for_weight_overload
                or self._item_signature(item) not in self._town_visit_purchases)
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
                    and total_devices - item.count
                    >= self._mana_food_device_target(snapshot)
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

    def _find_capped_identify_staff_release(
        self,
        snapshot: Snapshot,
        staffs: list[InventoryItem],
        release: dict[str, int],
    ) -> InventoryItem | None:
        """The next staff of the cap/swap release plan, fewest charges first.

        The released quantity is the plan's, carried by the retention
        reservation, so a sale or Home deposit moves only that many staves of
        a stack.  The MANA-food reserve slot goes last.  The user's cap
        (2026-10-03) outranks the old rule that kept staves for MANA food:
        any food shortfall is the ordinary departure shortage, restocked by
        ``_mana_food_purchase`` (which never buys a fifth Identify staff).
        """
        reserve_slot = self._device_food_reserve_slot(snapshot)
        candidates = [
            item
            for item in staffs
            if release.get(item.slot, 0) > 0
            and self._retention_surplus(snapshot, item) > 0
        ]
        return min(
            candidates,
            key=lambda item: (item.charges, item.slot == reserve_slot, item.slot),
            default=None,
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

    def _mana_food_purchase(
        self, snapshot: Snapshot, *, excluded_classes=frozenset(), budget_admits=None,
    ) -> StoreItem | None:
        """The charged device bought for a MANA eater's food.

        ``budget_admits`` narrows the shelf further (a mining set's food budget,
        fundraising_survival)."""
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
            if is_mana_food_ware(self, snapshot, it)
            and it.price <= snapshot.player.gold
            and ((it.tval, it.sval) not in excluded_classes
                 or self._identify_staff_swap_purchase(it))
            and (budget_admits is None or budget_admits(it))
        ]
        if not candidates:
            return None
        identify_slots = sum(
            1
            for item in snapshot.inventory
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
        )
        identify_staves = sum(
            item.count
            for item in snapshot.inventory
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
        )
        compliant = [
            item
            for item in candidates
            if not (
                item.tval == TVAL_STAFF
                and item.sval == SV_STAFF_IDENTIFY
                and (
                    identify_slots >= 2
                    # User 2026-10-03: never above four carried staves.
                    or identify_staves >= STAFF_IDENTIFY_MAX_COUNT
                )
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
        # Owner 2026-10-30: the Wand of Wonder becomes the staple once
        # secured, so the Magic shop's one is the food bought first.
        return min(
            candidates,
            key=lambda it: (
                not (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
                     and is_staple_food(it)),
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
            return item.is_wand_staff and item.charges > 0
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
        curse_kind = self._required_remove_curse_kind(snapshot)
        if curse_kind is not None and self._store_item_is_supply(item, curse_kind):
            status = self._supply_ledger(snapshot, self._planned_depth())[curse_kind]
            return max(0, status.required_departure - status.count)
        launcher = self._equipped_launcher(snapshot)
        if item.is_ammo and launcher is not None and item.tval == launcher.ammo_tval:
            return max(0, self._ammo_procurement_target(snapshot, item)
                       - self._count_matching_ammo(snapshot))
        if self._is_destruction_item(item):
            # Home-first: a stored *Destruction* item is withdrawn before the
            # shop purchase, and the shortage is the same one the departure
            # requirement publishes.
            return self._missing_destruction_uses(snapshot)
        strategy = self._carry_procurement_strategy(snapshot)
        if item_class == (TVAL_LITE, SV_LITE_TORCH):
            target, carried = self._torch_carry_requirement(snapshot, item, strategy)
            return max(0, target - carried)
        target = self._quest_carry_target_for_item(
            snapshot, item, strategy.required_force if strategy is not None else {}
        )
        if target is not None:
            return max(0, target[2] - target[1])
        potion_target = self._carry_strategy_potion_target(snapshot, item, strategy)
        if potion_target is not None:
            carried = sum(
                candidate.count
                for candidate in snapshot.inventory
                if candidate.tval == item.tval and candidate.sval == item.sval
            )
            return max(0, potion_target[0] - carried)
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
            missing = max(0, status.required_departure - status.count)
            if kind == "recall" and item.is_recall_rod:
                # One rod is the departure's read; a second adds nothing.
                return min(missing, int(self._carried_recall_rod(snapshot) is None))
            return missing
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

    def _torch_carry_requirement(
        self, snapshot: Snapshot, item: InventoryItem | StoreItem,
        strategy: StrategyProfile | None,
    ) -> tuple[int, int]:
        """The Home withdrawal and pack retention target for usable torches."""
        if torch_release.released(self, snapshot):
            # Owner 2026-11-12: the worn light crossbow sends every torch Home.
            return 0, self._count_usable_torches(snapshot)
        quest = self._quest_carry_target_for_item(
            snapshot, item, strategy.required_force if strategy is not None else {}
        )
        if quest is not None:
            return quest[2], quest[1]
        if self._matching_ammo(snapshot) is None:
            return TORCH_THROW_TARGET, self._count_throwing_torches(snapshot)
        if self._owns_usable_permanent_light(snapshot):
            # Spare torches only back up a fuelled light; with a permanent
            # light they are obsolete like its lamp oil (#69: five torch
            # stacks held the pack below its free-slot minimum).
            return 0, self._count_usable_torches(snapshot)
        return FOOD_STOCK_TARGET, self._count_usable_torches(snapshot)

    def _carry_strategy_potion_target(
        self,
        snapshot: Snapshot,
        item: InventoryItem | StoreItem,
        strategy: StrategyProfile | None = None,
    ) -> tuple[int, str] | None:
        """Return the shared retention/procurement target for capped potions."""
        if item.tval != TVAL_POTION:
            return None
        if heroism_potion.is_heroism(item):
            # Owner 2026-11-11 「持ち歩く数は仮に15服」: without a lasting fear resistance the
            # carried stock is procured (a stored one taken out first) and kept up to 15; with
            # one, none is.
            target = heroism_potion.carry_target(snapshot)
            return (target, heroism_potion.RETENTION_BRANCH) if target > 0 else None
        if item.sval == SV_POTION_SPEED:
            force_key = "speed_potions"
            label = "speed-potions"
        elif item.sval == SV_POTION_HEALING:
            force_key = "heal_potions"
            label = "heal-potions"
        else:
            return None
        target = EMERGENCY_POTION_CARRY_TARGET
        if strategy is not None:
            # A strategy asking more than the emergency carry keeps its own count (QUEST_18's
            # twelve Speed potions, owner 2026-11-12 「加速手段を十分数確保することを必須に
            # する。」): kept below it, the withdrawal and the departure would ask for different
            # counts.  Below the emergency carry nothing changes.
            target = max(target, int(strategy.required_force.get(force_key, 0)))
            return target, f"carry-strategy:{label}"
        return target, f"emergency-potion:{label.removesuffix('-potions')}"

    def _taken_departs_with_speed(self, quest) -> bool:
        """A taken quest whose entry asks its Speed doses (quest_force_rows.DEPART_FLAG): its
        kit is still procured, or the refused entry would wait for doses nobody buys."""
        if quest.status != QUEST_STATUS_TAKEN:
            return False
        profile = self.approved_quest_strategy(quest.id)
        return profile is not None and bool(
            profile.required_force.get(quest_force_rows.DEPART_FLAG))

    def _carry_procurement_strategy(
        self, snapshot: Snapshot, *, cache_fixed_quest_head: bool = True
    ) -> StrategyProfile | None:
        """Return the level-shaped torch mandate or next-quest requirements."""
        if self._opening_q1_active(snapshot):
            profile = self.approved_quest_strategy(1)
            return replace(profile, required_force=self._strategy_force_for_snapshot(snapshot, profile))
        if not snapshot.in_town:
            return None
        quest = (
            self._fixed_quest_head(snapshot)
            if cache_fixed_quest_head
            else self._uncached_fixed_quest_head(snapshot)
        )
        if snapshot.player.level >= 10:
            if quest is None or (quest.status != QUEST_STATUS_UNTAKEN
                                 and not self._taken_departs_with_speed(quest)):
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

    @claims(ClaimOwner.SURVIVAL)
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
                self._count_mana_food_devices(snapshot)
                >= self._mana_food_device_target(snapshot)
                and self._count_mana_food_uses(snapshot) >= MANA_FOOD_CHARGE_TARGET
            )
            # A floor device other than the staple never moves the staple's
            # food count; its shortage is the Tower's recharge.
            or staple_food(snapshot) is not None
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

        self._claim_target_capture = []
        try:
            step = self._nearest_position_step(snapshot, candidates)
        finally:
            step_target = self._take_claim_target()
        if step is None:
            return None
        self.last_reason = "mana-food:seek-device"
        self._declare_reach(step_target)
        return self._step_toward(snapshot, step)

    def _find_edible(self, snapshot: Snapshot) -> InventoryItem | None:
        # Race-dependent: MANA races (undead/constructs) drain wand/staff charges
        # for hunger; everyone else eats food. Eat with the same 'E' command.
        # The emitter hides `charges` until an item is identified, so also try
        # unidentified devices (the game allows eating any wand/staff; a known
        # empty one is skipped, an unknown one is worth the attempt) — but prefer
        # a device we know still has charges.
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            staple = staple_food(snapshot)
            if staple is not None:
                # Owner 2026-10-30: the staple is what is eaten.
                if staple.charges > 0:
                    return staple
                # Drained, the carried charged devices are the food (owner
                # 2026-11-12 「食べられる代替の食料も持っている」, n1-c life-203:
                # a Staff of Light beside two empty Wands of Wonder); an
                # unknown one is tried only when weak (below).
            charged = [it for it in snapshot.inventory
                       if it.known and it.is_wand_staff and it.charges > 0
                       and not is_staple_food(it)
                       and not awaiting_absorption(self, it)] if staple is not None else (
                mana_food_devices(self, snapshot))
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
            if staple is not None and snapshot.player.food_state not in {"weak", "fainting"}:
                return None
            # One the game marked empty ({空}) is no attempt: eating it again only repeats
            # 「この魔法棒にはもう魔力が残っていない」 (n1-a life-507 Angband 12F, 2026-11-10 18:57:
            # 「ブリキの魔法棒 {空}」 eaten ~40 times until the loop detector).
            return self._first_item(
                snapshot, lambda it: it.is_wand_staff and not it.known and not it.known_empty
            )
        return self._first_item(
            snapshot, lambda it: it.is_food and it.aware and it.sval >= FOOD_MIN_SVAL
        )

    @claims(ClaimOwner.SURVIVAL)
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
        # A one-shot quest floor whose faint light cannot be refilled or
        # swapped is left by the same ordinary return (#47); the quest
        # navigator owns the floor and would otherwise sweep on until the
        # light is gone.
        light_exit = not player.hungry
        if light_exit and not self._light_releases_quest_exit(snapshot):
            return None
        # Only a NEARBY threat defers the gate: a monster merely visible across
        # the floor may never engage at all, and waiting on it indefinitely is
        # how eating gets starved out of the schedule.
        near_hostiles = self._starvation_near_hostiles(hostiles)
        food = None if light_exit else self._find_edible(snapshot)
        if snapshot.in_town:
            if food is not None:
                self.last_reason = "town:eat-before-travel"
                key = reserved_item_command(self, snapshot, "eat", food)
                self._offer_execution(
                    key, producer="survival", work_id="town:eat",
                    next_step="survival.eat",
                    arguments=(self._item_signature(food),),
                    expected_effect="hunger-relieved",
                )
                return key
            step = self._shopping_approach_step(
                snapshot, requester="survival"
            )
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
            return reserved_item_command(self, snapshot, "eat", food)
        if near_hostiles:
            return None  # fight/flee first; re-fires on the next quiet decision
        key = self._return_to_town_key(snapshot, hostiles)
        if key is not None:
            return key
        # A quest exit lock refused the ordinary return. While merely "hungry"
        # the quest may still be finished first (_starvation_lets_quest_finish),
        # but weak-or-worse means starvation (paralysis death with full HP) is
        # now closer than any kill count: leave via the exit stairs and take
        # the visible loss.
        if player.food_state not in STARVING_FOOD_STATES:
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
        self._claim_target_capture = []
        try:
            step = self._nearest_goal_step(snapshot, self._is_upstairs_target)
        finally:
            step_target = self._take_claim_target()
        if step is not None:
            self.last_reason = "survival:seek-exit"
            self._declare_reach(step_target)
            return self._step_toward(snapshot, step)
        return None

    @staticmethod
    def _starvation_near_hostiles(hostiles: list[MonsterState]) -> list[MonsterState]:
        """The hostiles that defer the starvation gate's eat (a fight comes first)."""
        return [monster for monster in hostiles if monster.distance <= 4]

    def _hunger_meal_due(self, snapshot: Snapshot) -> bool:
        """The dungeon starvation gate eats on this board (``_survival_gate_key``'s eat).

        Hungry, something edible, and no hostile near unless already fainting.  A floor
        plan that returns above the gate steps aside for it (quest_find_exit
        .steps_aside_for_food).
        """
        player = snapshot.player
        if snapshot.in_town or not player.hungry:
            return False
        if (self._starvation_near_hostiles(self._physical_hostiles(snapshot))
                and not player.fainting):
            return False
        return self._find_edible(snapshot) is not None

    def _starvation_lets_quest_finish(self, snapshot: Snapshot) -> bool:
        """Nothing edible, yet a one-shot quest that locks the exit is finished first.

        The starvation gate's rule (``_survival_gate_key``): while merely
        hungry the quest owner keeps the floor; weak-or-worse leaves by the
        exit stairs.  n1-a life-471 (2026-11-03 11:14, Q2 final patrol): the
        mana eater turned hungry with no charge, the gate deferred to the
        quest, and the mana override stopped the bot instead (three restarts,
        new character) under town:blocked:survival-mana-no-charges.
        """
        return (snapshot.player.food_state not in STARVING_FOOD_STATES
                and self._return_exit_locked(snapshot))

    def _mana_food_survival_override_key(self, snapshot: Snapshot) -> str | None:
        """Hungry MANA-food absorption, survival return and town acquisition.

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
            key = reserved_item_command(self, snapshot, "eat", edible)
            self._offer_execution(
                key, producer="survival", work_id="survival:mana-absorb",
                next_step="survival.absorb-mana-food",
                arguments=(self._item_signature(edible),),
                expected_effect="hunger-relieved",
            )
            return key

        if not snapshot.in_town:
            hostiles = self._strategic_hostiles(snapshot)
            if snapshot.dungeon_level == 0:
                return self._wilderness_survival_key(snapshot, hostiles)
            floor_key = self._mana_food_loot_key(snapshot, hostiles)
            if floor_key is not None:
                return floor_key
            key = self._return_to_town_key(snapshot, hostiles)
            if key is None:
                # Preserve the existing weak/fainting quest-exit escape too.
                key = self._survival_gate_key(snapshot, hostiles)
            if key is not None and self.last_reason != "return:wait":
                return key
            if key is None and self._starvation_lets_quest_finish(snapshot):
                return None
            self.last_reason = "town:blocked:survival-mana-no-charges"
            return WAIT_KEY

        if me_staff_sequence.tower_feeds_staple(self, snapshot):
            return self._mana_food_tower_key(snapshot)

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
            if (home_device is not None and self._home_pending_item is None
                    and not self._home_errand.active):
                # Preserve the A21 queued-item contract when no other errand
                # owns this slot. Existing work is never overwritten.
                self._home_pending_item = self._item_signature(home_device)
                self._home_pending_quantity = 1
            # Posted input cannot be preempted. Wait for its existing bounded
            # observer rather than declaring the reachable Home unavailable.
            if (self._home_atomic_deposit_pending is not None
                    or self._home_atomic_withdraw_pending is not None
                    or getattr(getattr(self, "_home_visit", None), "entry_pending", False)):
                holder = standing_claim(self)
                execution = getattr(holder, "execution", None)
                if (holder is not None and holder.is_open and execution is not None
                        and execution.state == "awaiting"
                        and (execution.operation_ref or "").startswith("decision:")
                        and holder.goal.source in {"store-operation", "transaction"}
                        and holder.owner.value in {"home-visit", "home-errand", "equipment-txn"}):
                    # The sent operation retains its one registered observer.
                    # Survival takes over after that bounded observer releases it.
                    self.last_reason = (
                        "equipment-transaction:await-confirmation"
                        if holder.owner.value == "equipment-txn"
                        else "home:atomic-withdraw-await-confirmation"
                        if holder.owner.value == "home-errand"
                        else "home:atomic-deposit-await-confirmation"
                    )
                    self._offer_execution(
                        WAIT_KEY, producer=holder.owner.value,
                        work_id=execution.work_id,
                        next_step="home.operation.observe",
                        expected_effect=execution.expected_effect,
                        continuation=execution.continuation,
                        budget_ref=execution.budget_ref,
                    )
                    return WAIT_KEY
                self.last_reason = "survival:mana-home-await-operation"
                self._offer_execution(
                    WAIT_KEY, producer="survival", work_id="survival:mana-home",
                    next_step="home.operation.observe",
                    expected_effect="home-inventory-effect",
                    continuation="survival.mana-home.resume",
                    budget_ref="home-operation-existing-budget",
                )
                return WAIT_KEY
            self._rearm_town_store_for_new_work(
                STORE_HOME, release_visit_bound=True
            )
            filed = self._ensure_home_visit_request(snapshot)
            if filed and not self._home_knowledge_current:
                if snapshot.store is not None:
                    self.last_reason = "survival:mana-leave-wrong-store"
                    return LEAVE_STORE_KEY
                self.last_reason = "survival:mana-home-scan"
                if self._home_knowledge_scan_inflight:
                    self._offer_execution(
                        WAIT_KEY, producer="survival",
                        work_id=f"home-knowledge:{self._town_visit_epoch}",
                        next_step="home.knowledge.observe",
                        expected_effect="catalogue-adopted",
                        continuation="survival.mana-home.resume",
                        budget_ref="home-knowledge-existing-epoch",
                    )
                    return WAIT_KEY
                self._offer_home_knowledge_request(producer="survival")
                return HOME_KNOWLEDGE_MACRO
            step = (
                self._shopping_approach_step(
                    snapshot, STORE_HOME, requester="survival"
                )
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
                step = self._shopping_approach_step(
                    snapshot, sale_store, requester="survival"
                )
                if step is not None:
                    self.last_reason = "survival:mana-sale-approach"
                    return self._shopping_approach_key(
                        snapshot, step, "survival:mana-sale-travel"
                    )

        if STORE_MAGIC not in self._town_store_attempted:
            step = self._shopping_approach_step(
                snapshot, STORE_MAGIC, requester="survival"
            )
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

    def _mana_food_tower_key(self, snapshot: Snapshot) -> str | None:
        """The empty staple's one supplier, on the staff sequence's own legs.

        The sequence asks here because the Home and shop routes below serve only
        what ``_find_edible`` would eat.  ``None`` (its adjacent-hostile and
        fundraising boards) hands the board to the owners below this override.
        """
        self._home_procurement_probe = None
        if snapshot.store is not None:
            self.last_reason = "survival:mana-leave-wrong-store"
            return LEAVE_STORE_KEY
        return me_staff_sequence.town_key(self, snapshot, self._strategic_hostiles(snapshot))

    @claims(ClaimOwner.SURVIVAL)
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
        self._claim_target_capture = []
        try:
            step = self._nearest_position_step(snapshot, candidates)
        finally:
            step_target = self._take_claim_target()
        if step is None:
            return None
        self.last_reason = "mana-food:seek-device"
        self._declare_reach(step_target)
        return self._step_toward(snapshot, step)

    def _wilderness_survival_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Reach a town through local and global wilderness.

        On a local tile '<' opens the global map and a road-biased route
        reaches town.  An awake monster in view is left to the ordinary
        combat rules (None); a refused '<' walks off the tile's edge.
        """
        player = snapshot.player
        global_map = self._wilderness_map
        if self._on_global_wilderness_map(snapshot):
            self._wilderness_global_refused = False
            self._wilderness_edge_tries = {}
            key = global_map.next_key_to_town(player.position.y, player.position.x)
            if key == DOWN_STAIRS_KEY:
                # The global-map walk's own arrival test: a town is underfoot.
                self._complete_claim_goal(
                    "wilderness-town-reached", owners=(ClaimOwner.STORE_ROUTER,)
                )
                self.last_reason = "wilderness:enter-town"
                return key
            if key is not None:
                self.last_reason = "wilderness:global-travel"
                self._declare_place("wilderness:nearest-town")
                return key
            self.last_reason = "wilderness:no-safe-route"
            self._offer_execution(
                WAIT_KEY, producer="departure",
                work_id="wilderness:no-safe-route",
                next_step="departure.wait-for-safe-route",
                expected_effect="safe-route-available",
            )
            return WAIT_KEY

        # Owner 2026-11-08 (replaces 10-31 「帰還を読む」, whose premise was
        # wrong: Recall on the surface goes to a dungeon, spells-world.cpp
        # recall_player): 「近くの敵を倒すか、敵から離れて荒野の端へ歩き、全体
        # 地図へ出る（Zul の旅の「ふつうに戦い全体地図へ戻る」と同じ）。帰還は
        # 命が危ない時だけ、条件を満たす帰還先へ読む。」  An awake monster in
        # view is the ordinary combat rules' (None; the emergency ladder above
        # keeps the survival escapes, Recall among them).  A refused '<'
        # (change_wild_mode: an awake hostile within MAX_PLAYER_SIGHT, seen or
        # not) walks away from the detected monsters off the nearest edge to
        # the next tile, then '<' again.
        if any(not monster.asleep and monster.distance <= 20 for monster in hostiles):
            # MAX_PLAYER_SIGHT, the range change_wild_mode refuses for.
            return None
        if player.recalling:
            self.last_reason = "wilderness:wait-recall"
            return WAIT_KEY
        here = player.position
        last = self._wilderness_edge_last_position
        if last is not None and max(abs(last.y - here.y), abs(last.x - here.x)) > 1:
            # movement-execution.cpp: the border step placed the player on
            # the next tile's opposite edge.
            self._wilderness_global_refused = False
            self._wilderness_edge_tries = {}
        self._wilderness_edge_last_position = here
        if wilderness_exit.global_map_refused(snapshot):
            self._wilderness_global_refused = True
        if not self._wilderness_global_refused:
            self.last_reason = "wilderness:enter-global"
            return UP_STAIRS_KEY
        return self._wilderness_edge_key(snapshot)

    def _wilderness_edge_key(self, snapshot: Snapshot) -> str | None:
        """One step toward the map edge, away from the detected awake monsters.

        The border step itself changes the wilderness tile.  Unseen ground
        (the tile is mostly unexplored) is walked by heading: the orthogonal
        directions ordered by the awake detected hostiles each one walks
        toward, then by the distance to that edge; a step that left the
        player where it was tries the next heading.  None when no heading is
        left (the ordinary rules have the board).
        """
        height, width = snapshot.height, snapshot.width
        here = snapshot.player.position

        def on_edge(position: Position) -> bool:
            return position.y in (0, height - 1) or position.x in (0, width - 1)

        if not on_edge(here):
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                border = Position(here.y + dy, here.x + dx)
                grid = snapshot.grid_at(border)
                if on_edge(border) and (grid is None or not grid.known or grid.passable):
                    self.last_reason = "wilderness:edge-exit"
                    return self._direction_key(here, border)
        awake = [monster.position for monster in snapshot.detected_monsters
                 if monster.hostile and not monster.asleep]
        headings = sorted(
            ((sum(1 for spot in awake if (spot.y - here.y) * dy + (spot.x - here.x) * dx > 0),
              distance, (dy, dx))
             for distance, (dy, dx) in (
                 (here.y, (-1, 0)), (height - 1 - here.y, (1, 0)),
                 (here.x, (0, -1)), (width - 1 - here.x, (0, 1)))),
            key=lambda entry: (entry[0], entry[1]))
        usable = []
        for _toward, _distance, (dy, dx) in headings:
            cell = Position(here.y + dy, here.x + dx)
            grid = snapshot.grid_at(cell)
            if grid is None or (grid.known and not grid.passable) or grid.has_monster:
                continue
            usable.append(cell)
        attempt = self._wilderness_edge_tries.get(here, 0)
        if attempt >= len(usable):
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.passable and not on_edge(grid.position) and (
                    grid.position.y in (1, height - 2) or grid.position.x in (1, width - 2)))
            if step is not None:
                self.last_reason = "wilderness:edge-route"
                return self._step_toward(snapshot, step)
            # No way toward an edge is known: wait for the monsters to come
            # (fought by the combat rules) or to leave, then '<' again.  Never
            # the ordinary rules' stuck escapes, which read Recall here.
            self._wilderness_global_refused = False
            self._wilderness_edge_tries.pop(here, None)
            self.last_reason = "wilderness:edge-blocked"
            return WAIT_KEY
        self._wilderness_edge_tries[here] = attempt + 1
        self.last_reason = "wilderness:edge-walk"
        return self._direction_key(here, usable[attempt])

    def _wilderness_recall_selection(self, snapshot: Snapshot) -> str | None:
        """The choose_dungeon letter a wilderness Recall read answers.

        On the surface spells-world.cpp recall_player asks which dungeon to
        recall *to*; world-movement-processor.cpp execute_recall then lands
        the player on that dungeon's recall floor.  The established
        destination answers when it is safe (D22).  When its landing fails
        the depth gates, the departure read point's rule applies: the safe
        fallback landing (``_activate_safe_recall_fallback``, the deepest
        entered dungeon below the refused landing).  With no such landing the
        owner's no-safe-destination place answers (USER DECISION 2026-10-02
        「帰還先が全部条件不足の時は止めず ... イークの洞穴へ」): the Yeek cave,
        when entered and its own landing passes the same gates.
        n1-c life-166 2026-11-08 09:35: on the Zul trip the levitation ring
        and the mining shovels had replaced the resist-chaos ring and
        Gungnir, Angband 80 and every fallback failed their gates, the read
        carried no letter and the executor cancelled the chooser three times
        (stuck-prompt:wilderness:recall).  None leaves that named stop.
        """
        letter = self._surface_recall_selection(snapshot)
        if letter is not None:
            return letter
        destination, dungeon_id = self._town_recall_destination(
            snapshot, guardian_gate=False, safety_gate=False)
        if destination is not None:
            depth = self._dungeon_entry_depth(snapshot, dungeon_id, via_recall=True)
            fallback = self._activate_safe_recall_fallback(snapshot, depth)
            if fallback is not None:
                return self._recall_selection_key(snapshot, fallback)
        if (DUNGEON_YEEK_CAVE in (snapshot.entered_dungeon_ids or ())
                and self._recall_destination_safe(snapshot, DUNGEON_YEEK_CAVE)):
            return self._recall_selection_key(snapshot, DUNGEON_YEEK_CAVE)
        return None

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

        # A cell the weapon warning already refused is walked as WAIT -> no
        # key (Angband 30F 2026-10-20 04:01:22/34), and a cell another owner
        # vetoes (the shared avoid set: an immobile summoner's line of fire,
        # a paralyzer ring) is the one that owner just stepped out of
        # (n1-a life-469 鉄獄26/30階 2026-11-03: explore:avoid-immobile-summoner
        # and this walk alternated until the loop detector).  The same
        # avoidance explore and loot apply.
        refused = self._warning_refused_cells | self._engagement_avoid_cells
        first_steps = sorted(
            (
                neighbor
                for neighbor in self._walkable_neighbors(snapshot, origin)
                if projection(neighbor) > 0
                and neighbor not in refused
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
                if (
                    neighbor in seen
                    or projection(neighbor) <= 0
                    or neighbor in refused
                ):
                    continue
                seen.add(neighbor)
                queue.append((neighbor, first_step))
        self._unseen_retreat_target = None
        return first_steps[0] if first_steps else None

    def _unseen_choke_hold_active(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        """Both wait producers spend one episode, never a producer's counter.

        A nonempty hostile list can be a remote monster with zero
        reachable damage. Judge the same open-ground damage as other choke
        holds, including while blind. A sighting may authorize combat but
        never gives the unseen producer a new 50-turn budget.
        """
        start = self._unseen_choke_started_turn
        if start is None:
            self._unseen_choke_started_turn = start = snapshot.turn
        if (
            self._choke_predicted_damage(snapshot, hostiles)
            < snapshot.player.hp * CHOKE_ENGAGEMENT_MIN_DAMAGE_RATIO
            or (
                not any(not m.pet and not m.friendly
                        for m in snapshot.visible_monsters)
                and snapshot.turn - start >= DETECTED_THREAT_HOLD_MAX_GAME_TURNS
            )
        ):
            self._clear_unseen_retreat()
            return False
        return True

    @claims(ClaimOwner.POSITIONING)
    def _unseen_retreat_intercept_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        if (
            self._unseen_retreat_floor != snapshot.floor_key
            or self._unseen_choke_position != snapshot.player.position
            or not hostiles
        ):
            return None
        if not self._unseen_choke_hold_active(snapshot, hostiles):
            return None
        if (answer := combat_answer.adjacent_attack(self, snapshot, adjacent, "melee:choke")) is not None:
            return answer.key
        self.last_reason = "melee:choke-hold"
        return WAIT_KEY

    @claims(ClaimOwner.ESCAPE)
    def _unseen_retreat_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        # A hit observed on an earlier board of this floor whose decision a
        # higher rung (the emergency cure) took; consumed here either way.
        pending_hit = (
            getattr(self, "_unseen_hit_pending_floor", None) == snapshot.floor_key
        )
        pending_blind = pending_hit and getattr(self, "_unseen_hit_pending_blind", False)
        self._unseen_hit_pending_floor = None
        eligible_hit = (
            (
                pending_hit
                or (
                    self._took_damage
                    and self._unseen_attack_evidence is not None
                    and not self._took_curse_damage
                    and not self._took_trap_or_terrain_damage
                )
            )
            and not snapshot.visible_monsters
            and not player.poisoned
            and not player.cut
        )
        active = self._unseen_retreat_floor == snapshot.floor_key
        if not eligible_hit and not active:
            return None
        # A hit taken blind is 「何か」 only because the player could not see:
        # effect_player_lite / effect_player_dark print 「何かで攻撃された！」 to a
        # blind player (effect-player-resist-hurt.cpp:407 and 441), and the next
        # flash breath after sight returns blinds it again for 3-7 ticks
        # (:411-412).  A retreat that only such hits armed is no longer one from
        # attackers the player cannot see once sight shows the hostiles: they
        # belong to the combat ladder, as a hit on a sighted board with a
        # visible monster never arms this retreat (``eligible_hit``).  n1-c
        # life-195 (2026-11-11 17:26, オークの洞窟23階): light hounds blinded it
        # again after each return of sight, and every sighted board went to a
        # reverse-choke step between (12, 176) and (16, 176) with the hounds in
        # view, not to the ladder's answer for them, until the loop detector.
        # The observation rewrites the pending hit (and its blindness) on every
        # board with unseen-attack evidence, so it describes this board's hit too.
        blind_hit = pending_blind
        if (
            active
            and not eligible_hit
            and getattr(self, "_unseen_retreat_blind_only", False)
            and not player.blind
            and any(not monster.pet and not monster.friendly
                    for monster in snapshot.visible_monsters)
        ):
            self._clear_unseen_retreat()
            return None
        # The retreat is for attackers the player cannot see.  A visible
        # hostile that is adjacent, or that this turn's messages name, belongs
        # to the ordinary combat/survival ladder: walking on donated free
        # blows (Forest 32F 2026-10-03 03:46:28-37, サーベル・タイガー adjacent
        # for 25 reverse-choke steps, HP 599 -> 257).
        if any(
            monster.position.distance_to(player.position) <= 1
            or (
                monster.name
                and any(
                    message.startswith(monster.name)
                    for message in snapshot.messages
                )
            )
            for monster in hostiles
        ):
            return None
        # A melee blow is struck back; spell and missile evidence is walked
        # out of (owner 2026-11-01, unseen_strike).
        if (strike := unseen_strike.key(
                self, snapshot, hostiles, unseen_strike.RETREAT_REASON)) is not None:
            return strike

        if not active:
            self._unseen_retreat_floor = snapshot.floor_key
            direction = self._recent_reverse_direction(player.position)
            if direction is None:
                # Nothing walked to reverse yet (hit on the landing cell of
                # the player's own teleport, or before the first step on a
                # floor).  Fix one heading now: without one every board took
                # an unaimed step, never set a choke target, and the retreat
                # neither waited nor retired until the floor changed.
                first_step = self._least_visited_neighbor(snapshot)
                if first_step is not None:
                    direction = (
                        first_step.y - player.position.y,
                        first_step.x - player.position.x,
                    )
            self._unseen_retreat_direction = direction
            self._unseen_retreat_target = None
            self._unseen_choke_position = None
            self._unseen_choke_started_turn = None
            self._escape_state.enter("unseen", "unseen:reverse-choke")
            self._unseen_retreat_blind_only = eligible_hit and blind_hit
        elif eligible_hit and not blind_hit:
            self._unseen_retreat_blind_only = False
        if eligible_hit:
            self._record_unseen_attack(snapshot)

        if self._unseen_choke_position is not None:
            if eligible_hit:
                self._unseen_choke_position = None
                self._unseen_choke_started_turn = None
                self._unseen_retreat_target = None
            elif player.position == self._unseen_choke_position:
                if self._unseen_choke_hold_active(snapshot, hostiles):
                    self.last_reason = "unseen:choke-wait"
                    return WAIT_KEY
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
            self._unseen_choke_started_turn = snapshot.turn
            if not self._unseen_choke_hold_active(snapshot, hostiles):
                return None
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
        # The reverse route is exhausted without reaching a choke: the retreat
        # retires here, as it does when its choke wait ends.  Left armed it
        # takes back every board a lower owner moves it off this cell
        # (Forest 32F 2026-10-03 11:11:23: dead end (1, 196), seek-loot '4'
        # and unseen:reverse-choke '6' alternated until the loop detector).
        self._clear_unseen_retreat()
        return None

    def _nearest_goal_step(self, snapshot: Snapshot, predicate) -> Position | None:
        """Uniform-cost BFS returning the first step toward the nearest goal.

        The start tile is allowed to be the goal's neighbour; goal tiles are
        matched by ``predicate`` and may themselves be non-walkable (e.g. a
        downstairs is walkable, but a "tile adjacent to a monster" goal lands on
        a normal floor).
        """
        route = self._nearest_goal_route(snapshot, predicate)
        # For the town hold (rev 9.3 R2): a claim site that asked for it receives
        # the target this route chose, so it declares the far target rather
        # than the first step.  Only an armed capture is written, so a pure
        # caller's state is untouched.
        capture = self.__dict__.get("_claim_target_capture")
        if capture is not None:
            capture.append(route.target if route is not None else None)
        return route.first_step if route is not None else None

    def _nearest_goal_route(self, snapshot: Snapshot, predicate) -> TownMapRoute | None:
        """Return the goal, first step and remaining edges of the goal walk.

        The nearest goal by BFS, unless the route this goal kind committed to
        on an earlier board is still valid (``goal_route``)."""
        entrance_cells = self._town_entrance_cells(snapshot)
        entrance_cells.difference_update(
            pos
            for pos, grid in snapshot.grids.items()
            if predicate(grid)
        )
        entrance_cells.discard(snapshot.player.position)
        found = goal_route.nearest_goal_path(self, snapshot, predicate, entrance_cells)
        if found is None:
            goal_route.forget(self, predicate)
            return None
        return goal_route.follow(self, snapshot, predicate, *found, entrance_cells)

    def _nearest_goal_and_step(
        self, snapshot: Snapshot, predicate
    ) -> tuple[Position, Position] | None:
        """Return both the selected BFS goal and its first approach step."""
        # Every walker's one veto (policy _walk_veto, owner 2026-11-09 「退却・逃げ・狩り以外を揃える」).
        walk_veto = self._walk_veto(snapshot)
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
                    if neighbor in seen or neighbor in walk_veto:
                        continue
                    seen.add(neighbor)
                    queue.append(
                        (neighbor, neighbor if first_step is None else first_step)
                    )
        return None
