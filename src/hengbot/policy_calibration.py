"""Equipped calibration observations and refusal of historical strip debt."""
from __future__ import annotations
import json
from pathlib import Path
from hengbot.model import Snapshot, InventoryItem, RESTORE_POTION_SVAL_BY_STAT, STORE_ALCHEMIST
from hengbot.warrior_optimization import CharacterCalibration, load_character_calibration


class LegacyCalibrationDebtError(RuntimeError):
    """Manual recovery is required before attaching an old stripped session."""


def refuse_legacy_calibration_debt(state, path: Path | None = None):
    names = [name for name in (
        "_calibration_phase", "_calibration_suspended_phase",
        "_calibration_stripped_unrestored", "_calibration_restore_signatures",
        "_calibration_restore_items", "_calibration_restore_move_identities",
        "_calibration_restore_item_ids", "_calibration_session_target",
    ) if state.get(name)]
    if path is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict) and data.get("redress_obligation"):
            names.append("redress_obligation")
    if names:
        raise LegacyCalibrationDebtError("legacy-calibration-debt:" + ",".join(names)
                                         + "; manual equipment/supply recovery required")


class CalibrationMixin:
    def _prepare_character_sheet_dump(self):
        import time
        path = self._character_dump_path
        self._calibration_dump_prepared = {"baseline": None, "started_ns": time.time_ns()}
        if path is None:
            return
        try:
            import hashlib
            raw = path.read_bytes()
            baseline = (path.stat().st_mtime_ns, hashlib.sha256(raw).hexdigest())
        except OSError:
            baseline = None
        self._calibration_dump_prepared["baseline"] = baseline

    def _consume_equipped_character_sheet(self, character, envelope):
        from hengbot.character_sheet import (CharacterSheetUnavailable, parse_character_sheet,
                                            derive_equipped_calibration)
        from hengbot.model import parse_snapshot
        from hengbot.protocol import snapshot_protocol_version
        from hengbot.warrior_optimization import save_character_calibration
        pending = self._calibration_dump_pending
        if pending is None or envelope is None or self._character_dump_path is None:
            return
        self._calibration_dump_pending = None
        try:
            if pending.get("started_ns") is None:
                raise CharacterSheetUnavailable("unprepared-character-dump")
            before = self._character_dump_path.stat().st_mtime_ns
            raw = self._character_dump_path.read_bytes()
            sheet = parse_character_sheet(raw)
            current = (self._character_dump_path.stat().st_mtime_ns, sheet.content_hash)
            if before != current[0]:
                raise CharacterSheetUnavailable("dump-file-changing")
            if pending["baseline"] == current or current[0] < pending["started_ns"]:
                raise CharacterSheetUnavailable("stale-dump-file")
            sequence = envelope.get("sequence", envelope.get("seq"))
            if sequence is None or (pending["sequence"] is not None
                                    and int(sequence) <= int(pending["sequence"])):
                raise CharacterSheetUnavailable("uncorrelated-character-response")
            snapshot = self._with_cached_skill_exp(parse_snapshot(envelope, self._monrace_knowledge))
            bars = envelope.get("player", {}).get("status_bar", [])
            if "status_bar" not in envelope.get("player", {}):
                raise CharacterSheetUnavailable("timed-effect-observation-missing")
            effects = frozenset(row["key"] for row in bars)
            calibration = derive_equipped_calibration(
                sheet, snapshot, character, effects=effects, sequence=sequence,
                protocol_version=snapshot_protocol_version(envelope),
                session_id=self._calibration_session_id,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._character_calibration = None
            reason = (str(exc) if isinstance(exc, CharacterSheetUnavailable) else
                      "dump-unreadable:" + type(exc).__name__ if isinstance(exc, OSError) else
                      "character-response-unavailable:" + type(exc).__name__)
            self._calibration_unavailable_reason = reason
            self._calibration_rejection = (pending, reason)
            self._equipment_optimization_signature = None
            return
        self._character_calibration = calibration
        self._character_calibration_loaded = True
        self._calibration_unavailable_reason = None
        self._calibration_rejection = None
        self._equipment_optimization_signature = None
        self._confirmed_loadout = None
        self._confirmed_loadout_loaded = True
        if self._character_calibration_path is not None:
            save_character_calibration(self._character_calibration_path, calibration)

    def _validated_character_calibration(self, snapshot: Snapshot) -> CharacterCalibration | None:
        refuse_legacy_calibration_debt(self.__dict__, self._character_calibration_path)
        if not self._character_calibration_loaded:
            if self._character_calibration is None and self._character_calibration_path is not None:
                value = load_character_calibration(self._character_calibration_path)
                # An old strip record is comparison evidence, never v2 input.
                self._character_calibration = (value if value and value.schema_version == 2
                                               and value.session_id == self._calibration_session_id else None)
            self._character_calibration_loaded = True
        calibration = self._character_calibration
        if calibration is None:
            return None
        if calibration.intrinsic_capabilities:
            # Preserve capabilities without fabricating TR IDs. This initial
            # evaluator envelope does not model nether immunity yet.
            self._calibration_unavailable_reason = "unsupported-intrinsic-capability:" + ",".join(
                sorted(calibration.intrinsic_capabilities))
            return None
        reason = calibration.stale_reason(snapshot.player, self._current_pinned_identities(snapshot),
                                          mutation_signature=self._mutation_signature)
        if reason is None and calibration.schema_version == 2:
            from hengbot.warrior_equipment_evaluator import modify_stat_value
            from hengbot.character_sheet import temporary_bonuses, CharacterSheetUnavailable
            effects = frozenset(snapshot.player.status_bar or ())
            try:
                temporary_bonuses(effects)
            except CharacterSheetUnavailable as exc:
                reason = str(exc)
            for index in (0, 3, 4):
                equipment = sum(item.pval for item in snapshot.equipment if index in item.known_flags)
                predicted = modify_stat_value(calibration.natural_stats[index],
                                             calibration.intrinsic_adjustments[index] + equipment
                                             + (4 if "tsuyoshi" in effects and index in (0, 4) else 0))
                shown = snapshot.player.stat_use[index]
                if (predicted < 238 if shown >= 238 else predicted != shown):
                    reason = "visible-current-changed"
                    break
        if reason is not None:
            self._character_calibration = None
            self._calibration_unavailable_reason = reason
            self._equipment_optimization_signature = None
            self.request_character_dump()
            return None
        return calibration

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
        self._requeue_home_withdrawal(signature)
        self._home_pending_quantity = 1
        self._home_pending_quantities[signature] = 1
        self._home_withdrawal_queued = True
