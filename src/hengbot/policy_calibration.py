from __future__ import annotations

from collections import Counter
import json

from hengbot.equipment_optimizer import (
    SLOT_MAIN_HAND,
    SLOT_MAIN_RING,
    SLOT_SUB_HAND,
    SLOT_SUB_RING,
    equipment_identity,
    slot_for,
)
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    EquipmentTransaction,
    EquipmentTransactionPlan,
    _EQUIP_ORDER as EQUIP_ORDER,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    RESTORE_POTION_SVAL_BY_STAT,
    STORE_ALCHEMIST,
    STORE_HOME,
    TVAL_CAPTURE,
    TVAL_CARD,
    TVAL_DIGGING,
    TVAL_HAFTED,
    TVAL_POLEARM,
    TVAL_RING,
    TVAL_SHIELD,
    TVAL_SWORD,
    InventoryItem,
    Snapshot,
)
from hengbot.policy_constants import (
    CHARACTER_DUMP_MACRO,
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    PACK_CAPACITY,
    STORE_STUCK_LIMIT,
    WAIT_KEY,
)
from hengbot.warrior_optimization import (
    CharacterCalibration,
    calibrate_character_constants,
    load_character_calibration,
    save_character_calibration,
)


class CalibrationMixin:
    def _validated_character_calibration(
        self, snapshot: Snapshot
    ) -> CharacterCalibration | None:
        if (
            not self._character_calibration_loaded
            and self._character_calibration is None
            and self._character_calibration_path is not None
        ):
            self._character_calibration = load_character_calibration(
                self._character_calibration_path
            )
        self._character_calibration_loaded = True
        calibration = self._character_calibration
        if calibration is None:
            return None
        reason = calibration.stale_reason(
            snapshot.player,
            self._current_pinned_identities(snapshot),
            mutation_signature=self._mutation_signature,
        )
        if reason is not None:
            self._character_calibration = None
            return None
        return calibration

    def _calibration_active(self) -> bool:
        return (
            self._calibration_phase is not None
            or self._calibration_suspended_phase is not None
        )

    def _persist_calibration_redress_obligation(self) -> None:
        """Store the strip debt in the existing calibration record."""
        path = self._character_calibration_path
        if path is None:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if self._calibration_stripped_unrestored and self._calibration_worn_before:
            data["redress_obligation"] = [
                [slot, identity] for slot, identity in self._calibration_worn_before
            ]
        else:
            data.pop("redress_obligation", None)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            return

    def _legacy_calibration_redress_obligation(
        self, snapshot: Snapshot
    ) -> tuple[tuple[str, str], ...]:
        """Recover a pre-fix strip debt from the last confirmed worn set."""
        calibration = self._validated_character_calibration(snapshot)
        record = self._validated_confirmed_loadout()
        if calibration is None or record is None:
            return ()
        worn = [item for item in snapshot.equipment if item.is_equipment]
        if self._current_pinned_identities(snapshot) != calibration.pinned_identities:
            return ()
        confirmed_identities = {
            parts[1]
            for item_id in record.item_ids
            if len(parts := item_id.split(":")) == 3 and parts[0] == "equipped"
        }
        worn_identities = {equipment_identity(item) for item in worn}
        missing = [
            item
            for item in snapshot.inventory
            if item.is_equipment
            and equipment_identity(item) in confirmed_identities - worn_identities
        ]
        if not missing or any(
            not item.is_cursed
            and equipment_identity(item) not in confirmed_identities
            for item in worn
        ):
            return ()
        occupied = {item.slot for item in worn}
        recovered = []
        for item in missing:
            slot = slot_for(item)
            if item.tval == TVAL_RING:
                slot = next(
                    (candidate for candidate in (SLOT_MAIN_RING, SLOT_SUB_RING)
                     if candidate not in occupied),
                    None,
                )
            elif item.tval in {TVAL_SHIELD, TVAL_CAPTURE, TVAL_CARD}:
                slot = SLOT_SUB_HAND
            elif item.tval in {TVAL_DIGGING, TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD}:
                slot = next(
                    (candidate for candidate in (SLOT_MAIN_HAND, SLOT_SUB_HAND)
                     if candidate not in occupied),
                    None,
                )
            if slot is None or slot in occupied:
                continue
            occupied.add(slot)
            recovered.append((slot, equipment_identity(item)))
        return tuple(recovered)

    def _restore_calibration_redress_obligation(self, snapshot: Snapshot) -> None:
        if self._calibration_redress_loaded:
            return
        self._calibration_redress_loaded = True
        path = self._character_calibration_path
        data = {}
        if path is not None:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        entries = data.get("redress_obligation", ())
        try:
            obligation = tuple(
                (str(slot), str(identity)) for slot, identity in entries
            )
        except (TypeError, ValueError):
            obligation = ()
        if not obligation:
            obligation = self._legacy_calibration_redress_obligation(snapshot)
        if obligation:
            self._calibration_worn_before = obligation
            self._calibration_stripped_unrestored = True
            self._persist_calibration_redress_obligation()

    def _calibration_session_owned(self) -> bool:
        session = self._equipment_transaction_session
        return (
            session is not None
            and self._calibration_session_target is not None
            and session.target_loadout_id == self._calibration_session_target
        )

    def _calibration_preconditions_met(self, snapshot: Snapshot) -> bool:
        player = snapshot.player
        return (
            snapshot.in_town
            and self._temporary_status_clear(snapshot)
            and player.hp >= player.max_hp
            and not any(
                monster.hostile for monster in snapshot.visible_monsters
            )
        )

    def _calibration_removable_worn(
        self, snapshot: Snapshot
    ) -> list[InventoryItem]:
        return [
            item
            for item in snapshot.equipment
            if item.is_equipment and not item.is_cursed
        ]

    def _home_stat_restore_candidate(
        self, snapshot: Snapshot
    ) -> InventoryItem | None:
        """Return a currently addressable Home potion for a drained stat."""
        if (
            not self._home_knowledge_current
            or not self._home_available_for_probe(snapshot)
        ):
            return None
        addressable = self._home_knowledge_items[
            : self._home_knowledge_valid_before
        ]
        for stat in snapshot.player.drained_stats:
            sval = RESTORE_POTION_SVAL_BY_STAT.get(stat)
            candidate = next(
                (
                    item
                    for item in addressable
                    if item.is_potion
                    and item.aware
                    and item.sval == sval
                    and item.count > 0
                    and self._item_signature(item) not in self._deferred_home_items
                ),
                None,
            )
            if candidate is not None:
                return candidate
        return None

    def _stat_restore_purchase_actionable(
        self, snapshot: Snapshot, stat: str
    ) -> bool:
        """Return whether the ordinary Alchemist route can restore ``stat``."""
        if snapshot.player.gold <= 0:
            return False
        category = f"stat-restore:{stat}"
        observed = self._town_visit_ledger.shelf_observations.get(
            (STORE_ALCHEMIST, category)
        )
        if observed is not None:
            return any(
                price <= snapshot.player.gold for price, _units in observed
            )
        if (
            STORE_ALCHEMIST in self._town_store_attempted
            or STORE_ALCHEMIST in self._town_visit_ledger.blocked_stores
        ):
            return False
        if (
            self._town_map_active(snapshot)
            and self._town_map.store_position(STORE_ALCHEMIST) is None
        ):
            return False
        # The existing stat-restore NeedSpec owns one exploratory Alchemist
        # visit.  Until that visit supplies negative shelf evidence, it is an
        # actionable route; the observed branch above retires it immediately
        # on stock-out or unaffordability.
        return True

    def _calibration_actionable_invalidator(
        self, snapshot: Snapshot
    ) -> str | None:
        """Name a known invalidator whose existing town action can clear it."""
        if snapshot.player.drained_stats:
            if any(
                self._carried_restore_potion(snapshot, stat) is not None
                for stat in snapshot.player.drained_stats
            ):
                return "actionable-invalidator:stat_cur"
            if self._home_stat_restore_candidate(snapshot) is not None:
                return "actionable-invalidator:stat_cur"
            if any(
                self._stat_restore_purchase_actionable(snapshot, stat)
                for stat in snapshot.player.drained_stats
            ):
                return "actionable-invalidator:stat_cur"
        if self._normal_remove_curse_actionable_this_visit(snapshot):
            return "actionable-invalidator:pinned-set"
        return None

    def _queue_home_stat_restore(self, snapshot: Snapshot) -> None:
        """Give an addressable Home restore potion to the existing executor."""
        if (
            self._home_pending_item is not None
            or self._home_atomic_withdraw_pending is not None
        ):
            return
        candidate = self._home_stat_restore_candidate(snapshot)
        if candidate is None:
            return
        signature = self._item_signature(candidate)
        self._home_pending_item = signature
        self._home_pending_quantity = 1
        self._home_pending_quantities[signature] = 1
        self._home_withdrawal_queued = True

    def _begin_character_calibration(self, snapshot: Snapshot) -> None:
        self._calibration_phase = "deposit"
        self._calibration_suspended_phase = None
        self._calibration_home_rearm_eligible = False
        self._calibration_home_rearm_queue = None
        self._calibration_worn_before = tuple(
            (item.slot, equipment_identity(item))
            for item in snapshot.equipment
            if item.is_equipment and not item.is_cursed
        )
        self._calibration_restore_seen_pages.clear()
        self._calibration_naked_dump_prepared = False
        self._calibration_naked_dump_requested = False
        self._calibration_naked_dump_inflight = False
        self._calibration_naked_flags = None

    def _abort_character_calibration(self, snapshot: Snapshot, reason: str) -> None:
        """Suspend observation, preserving its progress, and redress."""
        self._calibration_aborts_this_visit += 1
        self._calibration_last_abort = f"calibration:abort:{reason}"
        if reason == "precondition" and self._calibration_suspended_phase is None:
            self._calibration_suspended_phase = self._calibration_phase
        if (
            reason == "capture-invalid"
            or self._calibration_aborts_this_visit >= STORE_STUCK_LIMIT
        ):
            self._calibration_blocked_this_visit = True
        if self._calibration_session_owned():
            self._equipment_transaction_session = None
        self._calibration_session_target = None
        self.last_reason = self._calibration_last_abort
        if self._calibration_blocked_this_visit:
            self._calibration_suspended_phase = None
            # The failure budget is spent: no more session cycling.  Converge
            # or stop visibly instead of aborting in a loop.
            self._calibration_restore_exhausted(snapshot)
            return
        if not self._install_calibration_restore_session(snapshot):
            self._calibration_phase = (
                "restore-supplies"
                if self._calibration_restore_signatures
                else None
            )

    def _calibration_restore_exhausted(self, snapshot: Snapshot) -> None:
        """Exhausted-budget regime: hand recovery to redress-mode.

        Two DIFFERENT precondition sets govern this phase.  The strict calm /
        full-HP / no-hostile set belongs to the calibration OBSERVATION only —
        a naked capture is worthless if a buff or damage contaminates it.
        Putting the clothes back on needs none of that: wearing an item is
        one key, available under threat, at any HP, with statuses active.

        So when the session budget is spent: if the character happens to be
        fully naked with the observation preconditions intact, finish the
        capture on the spot (the optimizer then owns dressing).  In every
        other case enter REDRESS-MODE — the phase ends, but the recorded
        stripped loadout (_calibration_worn_before) and the departure guard
        remain, and the ordinary equipment machinery plus the unconditional
        _calibration_redress_key dress the character one item per decision
        with no preconditions and no session/confirmation machinery at all.
        When every recorded item is observed worn again (or observed lost),
        the guard clears; the visit's calibration budget stays spent.
        """
        self._calibration_session_target = None
        self._calibration_suspended_phase = None
        if (
            not self._calibration_removable_worn(snapshot)
            and self._calibration_preconditions_met(snapshot)
            and self._capture_character_calibration(snapshot)
        ):
            return
        self._calibration_phase = (
            "restore-supplies"
            if self._calibration_restore_signatures
            else None
        )
        self.last_reason = "calibration:redress-mode"

    def _calibration_redress_accounting(
        self, snapshot: Snapshot
    ) -> tuple[
        list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]
    ]:
        """Match recorded (slot, identity) entries against copies by COUNT.

        ``equipment_identity`` deliberately collapses physically identical
        duplicates into one digest (the same property the quarantine work
        handles as digest + occurrence), so set membership must never stand
        in for satisfaction: each recorded entry CONSUMES one occurrence.
        Worn copies are consumed first — slot-matched entries before
        displaced ones, so a copy worn at its own recorded slot never
        satisfies a different entry — then pack copies mark entries as
        outstanding (a wear edge exists); entries with no copy left anywhere
        are lost.  Returns (satisfied, outstanding, lost).
        """
        worn_counts = Counter(
            equipment_identity(item)
            for item in snapshot.equipment
            if item.is_equipment
        )
        worn_slots = {
            (item.slot, equipment_identity(item))
            for item in snapshot.equipment
            if item.is_equipment
        }
        pack_counts = Counter(
            equipment_identity(item)
            for item in snapshot.inventory
            if item.is_equipment
        )
        satisfied: dict[tuple[str, str], None] = {}
        remainder: list[tuple[str, str]] = []
        for slot, identity in self._calibration_worn_before:
            if (slot, identity) in worn_slots and worn_counts[identity] > 0:
                worn_counts[identity] -= 1
                satisfied[(slot, identity)] = None
            else:
                remainder.append((slot, identity))
        outstanding: list[tuple[str, str]] = []
        lost: list[tuple[str, str]] = []
        for slot, identity in remainder:
            if worn_counts[identity] > 0:
                worn_counts[identity] -= 1
                satisfied[(slot, identity)] = None
            elif pack_counts[identity] > 0:
                pack_counts[identity] -= 1
                outstanding.append((slot, identity))
            else:
                lost.append((slot, identity))
        return list(satisfied), outstanding, lost

    def _calibration_redress_items(
        self, snapshot: Snapshot
    ) -> list[tuple[str, str]]:
        """Recorded stripped entries not yet back on, with a pack copy left."""
        if not (
            self._calibration_stripped_unrestored
            and self._calibration_worn_before
        ):
            return []
        if self._calibration_phase not in (None, "restore-supplies"):
            return []
        _, outstanding, _ = self._calibration_redress_accounting(snapshot)
        ordered = list(outstanding)
        main_index = next(
            (index for index, entry in enumerate(ordered) if entry[0] == SLOT_MAIN_HAND),
            None,
        )
        sub_index = next(
            (index for index, entry in enumerate(ordered) if entry[0] == SLOT_SUB_HAND),
            None,
        )
        if main_index is not None and sub_index is not None and sub_index < main_index:
            ordered[main_index], ordered[sub_index] = (
                ordered[sub_index], ordered[main_index]
            )
        return ordered

    def _calibration_redress_key(self, snapshot: Snapshot) -> str | None:
        """Dress a calibration-stripped character UNCONDITIONALLY.

        Re-dressing has no preconditions: it runs under threat, at any HP,
        with temporary statuses active — only genuine emergencies and combat
        responses above it in the ladder may preempt a single wear key.  It
        deliberately uses the ordinary fire-and-observe equip path (like the
        weapon re-arm and light-wield owners), not the session machinery
        whose stall budget got the phase here.
        """
        if not snapshot.in_town or snapshot.store is not None:
            return None
        abandonment = getattr(self, "_calibration_redress_abandonment", None)
        if abandonment is not None:
            self.last_reason = abandonment
            self._calibration_redress_abandonment = None
            return WAIT_KEY
        for slot, identity in self._calibration_redress_items(snapshot):
            obligation = (slot, identity)
            if self._calibration_redress_attempts.get(obligation, 0) >= STORE_STUCK_LIMIT:
                worn_before = list(self._calibration_worn_before)
                worn_before.remove(obligation)
                self._calibration_worn_before = tuple(worn_before)
                self._calibration_redress_attempts.pop(obligation, None)
                self._persist_calibration_redress_obligation()
                continue
            target = next(
                (
                    item
                    for item in snapshot.inventory
                    if item.is_equipment
                    and equipment_identity(item) == identity
                ),
                None,
            )
            if target is None:
                continue
            if self._equip_blocked_by_identification(target):
                worn_before = list(self._calibration_worn_before)
                worn_before.remove(obligation)
                self._calibration_worn_before = tuple(worn_before)
                self._calibration_redress_attempts.pop(obligation, None)
                self._persist_calibration_redress_obligation()
                self.last_reason = "calibration:redress-skip-identify-first"
                continue
            macro = self._equipment_wield(
                snapshot, "calibration-redress", target, slot
            )
            if macro is None:
                # A visible executor refusal is still a real attempt.  Charge
                # it so STORE_STUCK_LIMIT remains a bot-reachable release.
                if self._equipment_mutation_result.report is not None:
                    self._calibration_redress_attempts[obligation] = (
                        self._calibration_redress_attempts.get(obligation, 0) + 1
                    )
                continue
            self._calibration_redress_attempts[obligation] = (
                self._calibration_redress_attempts.get(obligation, 0) + 1
            )
            self.last_reason = "calibration:redress"
            return macro
        return None
    def _calibration_redress_observe(self, snapshot: Snapshot) -> None:
        """Clear the stripped guard once every recorded item is accounted for.

        The guard clears only after every recorded identity is observed worn
        again.  A phase ending, another transaction completing, or an item
        disappearing is not evidence that the character was redressed.
        """
        if not (
            self._calibration_stripped_unrestored
            and self._calibration_worn_before
        ):
            return
        if self._calibration_phase not in (None, "restore-supplies"):
            return
        if not snapshot.in_town:
            return
        satisfied, outstanding, lost = self._calibration_redress_accounting(
            snapshot
        )
        if lost and self._equipment_catalog.home_scan_complete:
            home_by_identity = {
                equipment_identity(item): self._item_signature(item)
                for item in self._home_knowledge_items
                if item.is_equipment
            }
            restore = [
                home_by_identity[identity]
                for _slot, identity in lost
                if identity in home_by_identity
                and home_by_identity[identity]
                not in self._calibration_restore_signatures
            ]
            if restore:
                # Durable redress debt outranks a newly planned optimizer
                # transaction.  Otherwise that session owns Home first and a
                # bounded HomeVisitExecutor can spend its entire epoch before
                # the calibration item is ever filed.
                if not self._calibration_session_owned():
                    self._equipment_transaction_session = None
                self._calibration_restore_signatures.extend(restore)
                self._calibration_phase = "restore-supplies"
                self._rearm_town_store_for_new_work(
                    STORE_HOME, release_visit_bound=True
                )
                self.last_reason = "calibration:redress-home-restore-filed"
                return
            # A complete Home catalogue plus pack/equipment accounting is a
            # closed world for the recorded identity.  Keeping an impossible
            # debt can never dress the character; release it explicitly.
            lost_set = set(lost)
            self._calibration_worn_before = tuple(
                obligation
                for obligation in self._calibration_worn_before
                if obligation not in lost_set
            )
            self._calibration_redress_abandonment = (
                "calibration:redress-abandoned:item-unavailable"
            )
            self._persist_calibration_redress_obligation()
            satisfied, outstanding, lost = self._calibration_redress_accounting(
                snapshot
            )
        pending = set(outstanding) | set(lost)
        self._calibration_redress_attempts = {
            obligation: attempts
            for obligation, attempts in self._calibration_redress_attempts.items()
            if obligation in pending
        }
        if outstanding or lost or len(satisfied) != len(self._calibration_worn_before):
            return
        self._calibration_worn_before = ()
        self._calibration_stripped_unrestored = False
        self._persist_calibration_redress_obligation()
        # Deliberately NOT re-armed: _calibration_blocked_this_visit and the
        # abort count stay spent.  Recovery must reopen DEPARTURE (the guard),
        # never the calibration budget — resetting it here re-armed an
        # indefinitely repeatable same-town strip/fail/redress cycle.
        # Calibration retries on a later visit via the fresh-visit reset.
        self.last_reason = "calibration:redressed"

    def _install_calibration_strip_session(self, snapshot: Snapshot) -> bool:
        removable = sorted(
            self._calibration_removable_worn(snapshot),
            key=lambda item: (-EQUIP_ORDER.get(item.slot, 1_000), item.slot),
        )
        if not removable:
            self._calibration_phase = "capture"
            return True
        if (
            PACK_CAPACITY - len(snapshot.inventory) < len(removable)
            or self._equipment_transaction_session is not None
        ):
            return False
        actions = tuple(
            EquipmentTransaction(
                PHASE_EQUIP,
                "takeoff",
                f"calibration:{item.slot}",
                item.slot,
                equipment_identity(item),
            )
            for item in removable
        )
        plan = EquipmentTransactionPlan(
            actions, (), len(snapshot.inventory) + len(actions)
        )
        session = EquipmentTransactionSession(
            plan,
            max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
        )
        self._equipment_transaction_session = session
        self._calibration_session_target = session.target_loadout_id
        self._calibration_phase = "strip"
        self._calibration_stripped_unrestored = True
        self._persist_calibration_redress_obligation()
        return True

    def _install_calibration_restore_session(self, snapshot: Snapshot) -> bool:
        """Re-wear everything recorded at strip start that is now in the pack."""
        worn_now = {
            item.slot
            for item in snapshot.equipment
            if item.is_equipment
        }
        pack_identities = {
            equipment_identity(item)
            for item in snapshot.inventory
            if item.is_equipment
        }
        missing = [
            (slot, identity)
            for slot, identity in self._calibration_worn_before
            if slot not in worn_now and identity in pack_identities
        ]
        if not missing or self._equipment_transaction_session is not None:
            return False
        actions = tuple(
            EquipmentTransaction(
                PHASE_EQUIP,
                "equip",
                f"calibration-restore:{slot}",
                slot,
                identity,
            )
            for slot, identity in sorted(
                missing, key=lambda entry: EQUIP_ORDER.get(entry[0], 1_000)
            )
        )
        plan = EquipmentTransactionPlan(actions, (), len(snapshot.inventory))
        session = EquipmentTransactionSession(
            plan,
            max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
        )
        self._equipment_transaction_session = session
        self._calibration_session_target = session.target_loadout_id
        self._calibration_phase = "restore-equip"
        return True

    def _capture_character_calibration(self, snapshot: Snapshot) -> bool:
        calibration = calibrate_character_constants(
            snapshot,
            mutation_signature=self._mutation_signature,
            intrinsic_tr_flags=self._calibration_naked_flags or frozenset(),
        )
        if calibration is None:
            return False
        self._character_calibration = calibration
        if self._character_calibration_path is not None:
            save_character_calibration(
                self._character_calibration_path, calibration
            )
            self._persist_calibration_redress_obligation()
        self._calibration_phase = (
            "restore-supplies" if self._calibration_restore_signatures else None
        )
        self._calibration_session_target = None
        # Recompute optimization after the new constants, independently of the
        # unconditional recorded-loadout redress owner.
        self._equipment_optimization_signature = None
        self._equipment_optimization_preparation = None
        self._rearm_town_store_for_new_work(
            STORE_HOME,
            release_visit_bound=bool(self._calibration_restore_signatures),
        )
        self.last_reason = "calibration:captured"
        return True

    def _calibration_observe(self, snapshot: Snapshot) -> None:
        """Advance the calibration state machine from each new snapshot."""
        self._restore_calibration_redress_obligation(snapshot)
        phase = self._calibration_phase
        if (
            phase is not None
            and self._equipment_transaction_session is not None
            and not self._calibration_session_owned()
        ):
            # A foreign equipment plan owns the current errand.  Calibration
            # resumes after it finishes instead of stripping items named by
            # that plan between its approach and Home operation.
            return None
        self._calibration_redress_observe(snapshot)
        if phase is None:
            return
        if not snapshot.in_town:
            # The floor changed under a live phase (death reload, forced move):
            # drop the phase; the calibration cache itself stays untouched and
            # the next town visit re-runs the phase from the start.
            self._calibration_phase = None
            self._calibration_restore_signatures.clear()
            if self._calibration_session_owned():
                self._equipment_transaction_session = None
            self._calibration_session_target = None
            return
        if phase in {"deposit", "strip"}:
            if any(monster.hostile for monster in snapshot.visible_monsters):
                self._abort_character_calibration(snapshot, "precondition")
                return
        if phase == "capture" and not self._calibration_preconditions_met(snapshot):
            self._abort_character_calibration(snapshot, "precondition")
            return
        if phase == "strip":
            if self._calibration_session_owned():
                if self._equipment_transaction_session.complete:
                    self._equipment_transaction_session = None
                    self._calibration_session_target = None
                    self._calibration_phase = "capture"
                    phase = "capture"
            elif not self._calibration_removable_worn(snapshot):
                self._calibration_session_target = None
                self._calibration_phase = "capture"
                phase = "capture"
            else:
                # The strip session was abandoned (stall bound) out from under
                # the phase: treat as interruption and restore.
                self._abort_character_calibration(snapshot, "session-lost")
                return
        if phase == "capture" and snapshot.store is None:
            if not self._calibration_naked_dump_requested:
                # The town key posts the naked `C` first; its characteristics
                # and mutation set belong in the captured constants.
                return
            if (
                self._calibration_naked_dump_inflight
                and self._calibration_naked_flags is None
            ):
                # One ordinary board snapshot without the response: clear the
                # observation and capture without characteristics on the next
                # snapshot (bounded by observations, never a wait loop).
                self._calibration_naked_dump_inflight = False
                return
            if not self._capture_character_calibration(snapshot):
                self._abort_character_calibration(snapshot, "capture-invalid")
            return
        if phase == "restore-equip":
            if self._calibration_session_owned():
                if self._equipment_transaction_session.complete:
                    # Every recorded item is back on: release the stripped
                    # guard along with the phase.
                    self._calibration_stripped_unrestored = False
                    if self._calibration_suspended_phase is None:
                        self._calibration_worn_before = ()
                    self._persist_calibration_redress_obligation()
                    self._equipment_transaction_session = None
                    self._calibration_session_target = None
                    self._calibration_phase = None
            else:
                # A LIVE session that vanished was abandoned by the stall
                # bound; only that consumes the per-visit failure budget — an
                # unbounded restore -> stall -> abandon -> restore cycle is
                # exactly the absorbing state this phase must never create.
                # A dormant park (no session) spends nothing and simply
                # re-enters the exhausted regime with each observation.
                if self._calibration_session_target is not None:
                    self._calibration_session_target = None
                    self._calibration_aborts_this_visit += 1
                    if self._calibration_aborts_this_visit >= STORE_STUCK_LIMIT:
                        self._calibration_blocked_this_visit = True
                if not self._calibration_blocked_this_visit:
                    if not self._install_calibration_restore_session(snapshot):
                        self._calibration_phase = (
                            "restore-supplies"
                            if self._calibration_restore_signatures
                            else None
                        )
                else:
                    self._calibration_restore_exhausted(snapshot)
            return
        if phase == "restore-supplies":
            if not self._calibration_restore_signatures:
                self._calibration_restore_signatures.clear()
                self._calibration_phase = None
                self._calibration_home_rearm_eligible = False
            elif STORE_HOME in self._town_visit_ledger.blocked_stores:
                if (
                    self._calibration_home_rearm_eligible
                ):
                    # The fresh-entry edge armed this before the blocking
                    # leave.  Consume it once; the raising leave itself cannot
                    # recreate it, and an unchanged restore queue prevents the
                    # next entry from arming another release.
                    self._calibration_home_rearm_eligible = False
                    self._rearm_town_store_for_new_work(
                        STORE_HOME, release_visit_bound=True
                    )
                else:
                    # The physical Home owner has spent its bounded contract.
                    # Release only identities that are still absent from pack
                    # and equipment; carried redress work remains actionable.
                    _, _, lost = self._calibration_redress_accounting(snapshot)
                    if lost:
                        lost_set = set(lost)
                        self._calibration_worn_before = tuple(
                            obligation
                            for obligation in self._calibration_worn_before
                            if obligation not in lost_set
                        )
                        self._calibration_redress_abandonment = (
                            "calibration:redress-abandoned:home-visit-exhausted"
                        )
                        self._persist_calibration_redress_obligation()
                    self._calibration_restore_signatures.clear()
                    self._calibration_phase = None
                    self._calibration_home_rearm_eligible = False
            elif STORE_HOME in self._town_store_attempted:
                self._rearm_town_store_for_new_work(STORE_HOME)
            return
        if phase == "deposit":
            if STORE_HOME in self._town_store_attempted and (
                self._find_home_deposit(snapshot) is not None
            ):
                self._rearm_town_store_for_new_work(STORE_HOME)

    def _calibration_town_key(self, snapshot: Snapshot) -> str | None:
        """Own the calibration phase while outside stores in town."""
        if (
            not snapshot.in_town
            or snapshot.store is not None
            or snapshot.player.class_id != PLAYER_CLASS_WARRIOR
        ):
            return None
        phase = self._calibration_phase
        if (
            phase is not None
            and self._equipment_transaction_session is not None
            and not self._calibration_session_owned()
        ):
            return None
        if phase is None:
            if self._calibration_suspended_phase is not None:
                suspended = self._calibration_suspended_phase
                if (
                    self._calibration_blocked_this_visit
                    or any(
                        monster.hostile
                        for monster in snapshot.visible_monsters
                    )
                    or (
                        suspended == "capture"
                        and not self._calibration_preconditions_met(snapshot)
                    )
                ):
                    return None
                phase = suspended
                self._calibration_suspended_phase = None
                self._calibration_phase = phase
                # Redressing made a suspended strip/capture non-naked again.
                # Re-strip the removable items that are actually still worn;
                # the original worn-before record remains authoritative.
                if phase in {"strip", "capture"}:
                    if self._install_calibration_strip_session(snapshot):
                        self.last_reason = "calibration:strip-resumed"
                        return WAIT_KEY
                    self._abort_character_calibration(snapshot, "no-pack-space")
                    return WAIT_KEY
            entry_blocker = self.calibration_entry_state(snapshot)[
                "entry_blocker"
            ]
            self._calibration_entry_refusal = (
                self._decision_sequence,
                entry_blocker,
            )
            if entry_blocker == "actionable-invalidator:stat_cur":
                self._queue_home_stat_restore(snapshot)
            if (
                self._calibration_blocked_this_visit
                or self._calibration_restore_signatures
                # The phase runs 装備最適化前: it starts only once the Home
                # scan (the other optimizer prerequisite) is complete and the
                # identification / Home processing flows are idle, so it can
                # never race their withdrawals.
                or not self._equipment_catalog.home_scan_complete
                or self._validated_character_calibration(snapshot) is not None
                or any(
                    monster.hostile for monster in snapshot.visible_monsters
                )
                or not self._home_available(snapshot)
                or self._equipment_transaction_session is not None
                or self._identification_need_actionable(snapshot)
                or self._home_pending_item is not None
                or self._home_pending_batch
                or self._home_atomic_withdraw_pending is not None
                or self._calibration_actionable_invalidator(snapshot) is not None
            ):
                return None
            self._begin_character_calibration(snapshot)
            phase = "deposit"
        if phase == "deposit":
            if self._home_atomic_deposit_pending is not None:
                return None
            if self._find_home_deposit(snapshot) is None:
                # Pack drained as far as Home accepts; strip if the takeoffs
                # fit, otherwise the observation cannot be made this visit.
                if self._install_calibration_strip_session(snapshot):
                    self.last_reason = "calibration:strip-installed"
                    return WAIT_KEY
                self._abort_character_calibration(snapshot, "no-pack-space")
                return WAIT_KEY
            # Deposits ride the ordinary Home routing (atomic entry deposit,
            # one operation per entry); nothing to post from here.
            return None
        if phase == "capture":
            if (
                not self._calibration_naked_dump_requested
                and not self._calibration_naked_dump_prepared
                # Confirmed-outside gate: this snapshot AND the previous one
                # are outside any store, and no store leave is in flight, so
                # the status-screen keys cannot land in a store command loop.
                and self._store_leave_inflight is None
                and not self._last_snapshot_was_store
            ):
                # The character is naked: post `C` so the capture records the
                # characteristics table (permanent vulnerabilities,
                # immunities, sustains, ...) and the mutation set — the
                # user-approved acquisition, one key inside a phase that
                # already exists.  The posting-time latch in
                # confirm_key_posted owns the request.
                self._calibration_naked_dump_prepared = True
                self.last_reason = "calibration:request-naked-character"
                return CHARACTER_DUMP_MACRO
            self.last_reason = "calibration:await-capture"
            return WAIT_KEY
        return None
