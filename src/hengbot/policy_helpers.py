from __future__ import annotations

from dataclasses import replace

from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.equipment_optimizer import Loadout
from hengbot.model import (
    DUNGEON_ANGBAND, DUNGEON_CHAMELEON_CAVE, DUNGEON_YEEK_CAVE,
    GridState, InventoryItem, MonsterState, Position, Snapshot, StoreItem,
    SV_LITE_TORCH, SV_ROD_LITE, SV_SCROLL_STAR_DESTRUCTION, SV_STAFF_DESTRUCTION,
    TVAL_AMULET, TVAL_ARROW, TVAL_BOOTS, TVAL_BOLT, TVAL_BOW, TVAL_CLOAK,
    TVAL_CROWN, TVAL_DIGGING, TVAL_DRAG_ARMOR, TVAL_FOOD, TVAL_GLOVES,
    TVAL_HAFTED, TVAL_HARD_ARMOR, TVAL_HELM, TVAL_LITE, TVAL_POLEARM,
    TVAL_RING, TVAL_ROD, TVAL_SCROLL, TVAL_SHIELD, TVAL_SHOT, TVAL_SOFT_ARMOR,
    TVAL_STAFF, TVAL_SWORD,
)
from hengbot.policy_constants import (
    DISPOSABLE_POTION_SVALS, DISPOSABLE_SCROLL_SVALS, ExplorationPathOutcome,
    FOOD_TYPE_MANA, HEAVY_CURSE_TAG, SPEED_ENERGY_90, WAIT_KEY,
)


class PolicyHelpersMixin:
    def _transaction_retain_identities(
        self, snapshot: Snapshot, current: Loadout, target: Loadout
    ) -> frozenset[str]:
        """Project displaced worn items through takeoff before asking retention."""
        if not isinstance(current, Loadout) or not isinstance(target, Loadout):
            return frozenset()
        current_slots = dict(current.slots)
        target_slots = dict(target.slots)
        displaced_slots = {
            slot
            for slot, owned in current_slots.items()
            if target_slots.get(slot) is None or target_slots[slot].id != owned.id
        }
        if not displaced_slots:
            return frozenset()
        displaced = tuple(
            owned.item for slot, owned in current_slots.items() if slot in displaced_slots
        )
        # Match object_sort_comp's ordering decisions that are represented on
        # InventoryItem (object-sort.cpp:40-107, 126-154): tval descending,
        # sval ascending, artifact/ego rank ascending, ammo bonuses ascending,
        # then calc_price descending.  Equal keys deliberately stay in input
        # order: inven_carry inserts the displaced item after equal existing
        # stock (inventory-object.cpp:307-313), and reorder_pack is stable.
        def pack_sort_key(item: InventoryItem) -> tuple:
            rank = 3 if item.is_artifact else 1 if item.is_ego else 0
            ammo_bonus = item.to_h + item.to_d if item.is_ammo else 0
            # For equal tval/sval/rank, base cost is equal.  These are the
            # represented variable calc_price terms from object-value.cpp:
            # 160-205.  In particular DIGGING and other weapons add
            # (to_h + to_d + to_a) * 100; lights have no fuel term.
            if item.tval in {
                TVAL_BOW, TVAL_DIGGING, TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD,
            }:
                price_adjustment = (
                    item.to_h + item.to_d + item.to_a
                ) * 100
            elif item.tval in {TVAL_RING, TVAL_AMULET}:
                price_adjustment = (
                    item.to_h + item.to_d + item.to_a
                ) * 200
            elif item.tval in {
                TVAL_BOOTS, TVAL_GLOVES, TVAL_CLOAK, TVAL_CROWN, TVAL_HELM,
                TVAL_SHIELD, TVAL_SOFT_ARMOR, TVAL_HARD_ARMOR, TVAL_DRAG_ARMOR,
            }:
                price_adjustment = (item.to_h + item.to_d) * 200 + item.to_a * 100
            else:
                price_adjustment = 0
            return (
                -item.tval,
                not item.aware,
                item.sval,
                not item.known,
                rank,
                ammo_bonus,
                -price_adjustment,
            )

        projected_inventory = sorted(
            tuple(snapshot.inventory) + displaced, key=pack_sort_key
        )
        projected = replace(
            snapshot,
            inventory=tuple(
                replace(item, slot=chr(ord("a") + index))
                for index, item in enumerate(projected_inventory)
            ),
            equipment=tuple(
                item for item in snapshot.equipment if item.slot not in displaced_slots
            ),
        )
        return self._home_visit_retention(projected)[1]
    def _refuse_no_progress_cycle(self, snapshot: Snapshot, key: str) -> str:
        """Refuse a repeated transition after an equivalent-state cycle.

        Equivalence deliberately includes floor and position (physical place),
        store type (command-language context), and the complete ordered-neutral
        pack/equipment projections (the resources and worn state store work can
        change).  Gold, HP, messages and policy-owner latches are excluded: they
        neither make a store transition effective nor permit owners to define
        different versions of progress.  A recurrence is ineffective when game
        turns advanced less than policy decisions across its own decision span.
        """
        state = self._emission_state(snapshot)
        previous = self._emission_occurrences.get(state)
        sequence = self._decision_sequence
        turn = getattr(snapshot, "turn", 0)
        if previous is not None:
            previous_sequence, previous_turn, previous_key = previous
            decision_span = sequence - previous_sequence
            turn_span = max(0, turn - previous_turn)
            returned_through_other_state = self._emission_previous_state != state
            owner_boundary_decision = any(
                marker in (self.last_reason or "")
                for marker in (
                    "approach", "entry", "store-context-exit",
                    "entrance-step-off", "abandon-blocked-home",
                    "abandon-blocked",
                    "scan-address-burst",
                )
            )
            if (
                key
                and key == previous_key
                and decision_span > 1
                and returned_through_other_state
                and turn_span < decision_span
                and (self._store_visit is not None or state.store_type is not None)
                and owner_boundary_decision
            ):
                visit = self._store_visit
                if visit is not None:
                    self._close_store_visit("refused-with-evidence")
                self.last_reason = "livelock:exhausted"
                self._emission_previous_state = state
                return WAIT_KEY
        self._emission_occurrences[state] = (sequence, turn, key)
        self._emission_previous_state = state
        return key
    def consume_look(self, data: dict[str, object]) -> None:
        """Record the floor identities returned by the existing look channel."""
        from hengbot.model import _parse_items

        look = data.get("look")
        if not isinstance(look, dict):
            return
        records: dict[Position, tuple[InventoryItem, ...]] = {}
        for grid_data in look.get("grids", []):
            if not isinstance(grid_data, dict):
                continue
            try:
                position = Position(int(grid_data["y"]), int(grid_data["x"]))
            except (KeyError, TypeError, ValueError):
                continue
            records[position] = tuple(_parse_items(grid_data.get("items", [])))
        self._look_floor_items = records
        self._look_probe_inflight = False
    def _periodic_filler_is_safe(self, snapshot: Snapshot) -> bool:
        visit = self._store_visit
        if (
            self._store_entry_wait_owner is not None
            or self._store_entry_posted_owner is not None
            or (
                visit is not None
                and visit.operation_posted
                and not visit.operation_released
            )
        ):
            return False
        safe_exploration = self.last_reason in {
            "explore",
            "fundraise:sweep-explore",
        }
        safe_q2_patrol = (
            (
                self.last_reason.startswith("quest-strategy:q2-residual-")
                or self.last_reason.startswith("quest-strategy:q2-final-patrol")
            )
            and not self._physical_hostiles(snapshot)
        )
        safe_town = (
            snapshot.in_town
            and snapshot.store is None
            and not self._physical_hostiles(snapshot)
            and not snapshot.player.blind
            and not snapshot.player.confused
        )
        return (
            (safe_exploration or safe_q2_patrol or safe_town)
            and snapshot.store is None
            and not snapshot.player.recalling
            and not self._physical_adjacent_hostiles(snapshot)
        )
    def _evaluate_cross_decision_latches(self, snapshot: Snapshot) -> None:
        """Run every declared release evaluator before decision routing."""
        for latch in self._cross_decision_latches.values():
            getattr(self, latch.release_evaluator)(snapshot)
    def _weakest(self, monsters: list[MonsterState]) -> MonsterState:
        # Remove adjacent summoners before their minions multiply; otherwise use
        # the visible health band and status to choose a finishing target.
        return min(
            monsters,
            key=lambda m: (not m.can_summon, m.hp, not m.asleep, m.distance),
        )
    def _first_item(self, snapshot: Snapshot, predicate) -> InventoryItem | None:
        for item in snapshot.inventory:
            if item.slot and predicate(item):
                return item
        return None
    def _is_disposable_item(
        self, item: InventoryItem, *, food_type: int = 0
    ) -> bool:
        # A bounty target (wanted monster's corpse) is worth gold at the Hunter's
        # Office, and an item the game already refused to destroy this expedition
        # must not be re-selected, or the full-pack disposal loops forever.
        if item.is_bounty or self._item_signature(item) in self._undestroyable_sigs:
            return False
        return (
            # MANA races cannot digest ordinary food.  Treat it as junk so a
            # mistaken/live legacy purchase can be sold or dropped instead of
            # occupying a pack slot forever. WATER/OIL/BLOOD retain the normal
            # food fallback intentionally.
            (food_type == FOOD_TYPE_MANA and item.tval == TVAL_FOOD)
            or (item.is_potion and item.aware and item.sval in DISPOSABLE_POTION_SVALS)
            or (item.is_scroll and item.aware and item.sval in DISPOSABLE_SCROLL_SVALS)
            # A brass lantern already lights radius 2, so a Rod of Light is dead
            # weight — shed it like any other junk device.
            or (item.tval == TVAL_ROD and item.sval == SV_ROD_LITE and item.aware)
            or (
                item.tval == TVAL_LITE
                and item.sval == SV_LITE_TORCH
                and item.known
                and item.fuel == 0
            )
            or item.pseudo_feeling in {"average", "cursed"}
            # Empty bottles are the worthless junk a quaffed potion leaves behind;
            # no shop buys them, so shed them rather than let them fill the pack.
            or item.is_empty_bottle
            # Opened or smashed chests have no remaining contents or utility.
            or (
                item.is_chest
                and any(
                    marker in item.name for marker in ("(empty)", "(空)", "壊れた")
                )
            )
            # Unidentified mushrooms (unaware food; rations are always aware) are a
            # poison gamble worth almost nothing — shed them instead of hoarding.
            or (item.is_food and not item.aware)
        )
    def _find_disposable_item(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: self._entire_stack_is_surplus(snapshot, it)
            and (
                self._is_disposable_item(it, food_type=snapshot.player.food_type)
                or self._is_spare_lantern(snapshot, it)
                # Fundraising needs one digging tool, never four. At pack pressure,
                # discard every tool except the strongest before spending Recall.
                or self._is_surplus_digging_tool(snapshot, it)
                # Ammo has no use without a launcher. Keep it whenever any bow is
                # carried or equipped; otherwise free the slot before town departure.
                or (
                    it.tval in {TVAL_SHOT, TVAL_ARROW, TVAL_BOLT}
                    and not any(
                        candidate.tval == TVAL_BOW
                        for candidate in (*snapshot.inventory, *snapshot.equipment)
                    )
                )
            ),
        )
    @staticmethod
    def _inventory_weight(snapshot: Snapshot) -> int:
        return sum(
            max(0, item.weight) * max(1, item.count)
            for item in (*snapshot.inventory, *snapshot.equipment)
        )
    def _inventory_signature_count(
        self, snapshot: Snapshot, signature: tuple[str, int, int]
    ) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if self._item_signature(item) == signature
        )
    def _is_active_dungeon_entrance(self, grid: GridState) -> bool:
        return (
            grid.has_entrance
            and grid.entrance_dungeon_id == self._active_dungeon_target()
        )
    def _curse_unremovable(self, item: InventoryItem | StoreItem) -> bool:
        """Single authority for confirmed heavy/permanent curse status."""
        return (
            HEAVY_CURSE_TAG in item.inscription
            or self._item_signature(item) in self._heavy_cursed_items
        )
    @staticmethod
    def _profile_resistance_name(name: str) -> str:
        aliases = {
            "acid": "resist_acid", "electricity": "resist_elec",
            "fire": "resist_fire", "cold": "resist_cold",
            "poison": "resist_pois", "confusion": "resist_conf",
            "blindness": "resist_blind", "fear": "resist_fear",
            "nether": "resist_neth", "chaos": "resist_chaos",
        }
        return aliases.get(name, name)
    def _pick_alternate_dungeon(
        self,
        snapshot: Snapshot,
        *,
        max_entry_depth: int | None = None,
        prefer_deepest: bool = False,
        allow_yeek_cave: bool = False,
    ) -> int | None:
        """Choose the shallowest safe dungeon already available to Recall."""
        # The deepest already-unlocked dungeon — excluding the over-deep main one
        # and the Yeek Cave reserved for fundraising — whose floor is SHALLOWER
        # than the depth we could not loot at. Deepest-that-still-fits is the most
        # rewarding available fallback;
        # re-running after another empty streak (with _last_overextended_depth now
        # the switched dungeon's depth) steps down to a shallower one.
        best: DungeonInfo | None = None
        for did in snapshot.entered_dungeon_ids:
            info = self._dungeon_knowledge.get(did)
            if info is None or did in (
                DUNGEON_ANGBAND,
                DUNGEON_CHAMELEON_CAVE,
            ):
                continue
            if did == DUNGEON_YEEK_CAVE and not allow_yeek_cave:
                continue
            if (
                did in snapshot.conquered_dungeon_ids
                and {"MAZE", "FORGET"}.issubset(info.flags)
            ):
                # A forgetting maze has high navigation cost, and its guardian
                # reward is gone after conquest. Never choose it as a farming
                # fallback merely because its recall floor is shallow.
                continue
            if did == self._alternate_dungeon:
                continue  # the one we are leaving — never re-pick it, always step down
            landing_depth = snapshot.dungeon_recall_depths.get(did, info.min_depth)
            if max_entry_depth is None:
                if landing_depth >= self._last_overextended_depth:
                    continue
            elif landing_depth > max_entry_depth:
                continue
            # Its entry floor must be within our RESISTANCE safe band, or we just
            # trade one under-resisted dungeon for another. The character lacking
            # confusion resistance was sent to the Mountain (25F needs it), swarmed,
            # and returned with zero loot after a very short dive; steer it instead
            # to a dungeon whose landing depth its resistances actually cover
            # (e.g. a sub-20F Forest / Orc cave with no resistance requirement).
            if self._missing_required_abilities(snapshot, landing_depth):
                continue
            if best is None:
                best = info
                continue
            best_landing_depth = snapshot.dungeon_recall_depths.get(
                best.id, best.min_depth
            )
            better = (
                landing_depth > best_landing_depth
                if prefer_deepest
                else landing_depth < best_landing_depth
            )
            if better or (
                landing_depth == best_landing_depth and info.id < best.id
            ):
                best = info
        return best.id if best is not None else None
    def _is_completed_forgetting_maze(self, snapshot: Snapshot) -> bool:
        """Whether this forgetting maze no longer has a guardian objective."""
        if not self._is_forgetting_maze(snapshot):
            return False
        info = self._dungeon_knowledge.get(snapshot.floor_key[0])
        return (
            snapshot.floor_key[0] in snapshot.conquered_dungeon_ids
            or (info is not None and info.guardian_id <= 0)
        )
    @staticmethod
    def _speed_energy(speed: int) -> int:
        if speed < 90:
            return 3  # conservative upper bound for very slow actors
        if speed >= 200:
            return 49
        return SPEED_ENERGY_90[speed - 90]
    @staticmethod
    def _has_destruction_method(snapshot: Snapshot) -> bool:
        """A *Destruction* scroll or a staff with charges left (the AGENTS.md 50F+
        gate). sval is emitted only for AWARE items and charges only for KNOWN
        ones (fair play), so an untried staff conservatively does not count."""
        for it in snapshot.inventory:
            if it.tval == TVAL_SCROLL and it.sval == SV_SCROLL_STAR_DESTRUCTION:
                return True
            if it.tval == TVAL_STAFF and it.sval == SV_STAFF_DESTRUCTION and it.charges > 0:
                return True
        return False
    def _latch_warning_refusal(self, target: Position) -> None:
        self._warning_refused_cells.add(target)
        self._engagement_avoid_cells.add(target)
        if self._loot_target == target:
            self._loot_target = None
        if target in self._explore_path:
            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
