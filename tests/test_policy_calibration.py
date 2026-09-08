import base64
import gzip
import inspect
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import hengbot.equipment_mutation as equipment_mutation_module
import hengbot.policy as policy_module
import hengbot.policy_calibration as policy_calibration_module
from hengbot.cli import POLICY_FINAL_STOP_REASONS
from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import (
    GridState,
    PLAYER_CLASS_WARRIOR,
    Position,
    STORE_ALCHEMIST,
    STORE_HOME,
    STORE_TEMPLE,
    SV_LITE_FEANOR,
    SV_LITE_LANTERN,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_RESTORE_CON,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    Snapshot,
    StoreState,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_RING,
    TVAL_SCROLL,
    TVAL_SWORD,
)
from hengbot.policy import HengbotPolicy, STORE_STUCK_LIMIT, WAIT_KEY
try:
    from policy_fixtures import grid, hostile, item, player, store_item
except ModuleNotFoundError:
    from tests.policy_fixtures import grid, hostile, item, player, store_item


class CharacterCalibrationPhaseTest(unittest.TestCase):
    """P1: the execution-layer unequipped calibration phase and its exits."""

    HOME = Position(10, 12)

    def _grids(self):
        grids = {
            Position(10, x): grid(10, x) for x in range(9, 14)
        }
        grids[self.HOME] = GridState(
            position=self.HOME, known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_HOME,
        )
        return grids

    def _snapshot(self, *, inventory=(), equipment=(), monsters=(),
                  store=None, hp=200, max_hp=200):
        base = player(
            10, 10, class_id=PLAYER_CLASS_WARRIOR, level=12,
            hp=hp, max_hp=max_hp,
        )
        base = replace(
            base,
            race_id=3, personality_id=1, ac=10,
            stat_cur=(18, 10, 10, 17, 16, 9),
            stat_use=(20, 10, 10, 18, 17, 9),
        )
        return Snapshot(
            base,
            self._grids(),
            list(monsters),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
            store=store,
        )

    def _scan_complete_policy(self):
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page([])
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        return policy

    def _live_calibration_start_snapshot(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "calibration-start-timing-live.jsonl.gz"
        )
        with gzip.open(fixture, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["decision_index"], 5095)
        self.assertEqual(row["last_reason"], "store:entry-await-observation")
        snapshot = pickle.loads(
            base64.b64decode(row["decision_snapshot_pickle_b64"])
        )
        self.assertEqual(snapshot.turn, 1571525)
        self.assertEqual(snapshot.player.drained_stats, ("con",))
        self.assertEqual(snapshot.player.gold, 4358)
        return snapshot

    def test_optimizer_fails_closed_and_never_triggers_the_phase_itself(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot()

        preparation = policy._prepare_equipment_optimization(snapshot)

        self.assertEqual(preparation.blockers, ("calibration-required",))
        self.assertIsNone(preparation.transaction)
        # The selector reports the missing input; only the execution layer may
        # start the phase.
        self.assertIsNone(policy._calibration_phase)
        self.assertFalse(policy._equipment_departure_ready(snapshot))

    def test_phase_starts_after_home_scan_without_a_hostile(self):
        worn = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        pack = item("a", TVAL_POTION, SV_POTION_CURE_CRITICAL)
        threat = hostile(1, 10, 11)

        unscanned = HengbotPolicy()
        self.assertIsNone(
            unscanned._calibration_town_key(
                self._snapshot(inventory=(pack,), equipment=(worn,))
            )
        )
        self.assertIsNone(unscanned._calibration_phase)

        threatened = self._scan_complete_policy()
        snapshot = self._snapshot(
            inventory=(pack,), equipment=(worn,), monsters=(threat,)
        )
        self.assertIsNone(threatened._calibration_town_key(snapshot))
        self.assertIsNone(threatened._calibration_phase)

        hurt = self._scan_complete_policy()
        hurt._calibration_town_key(
            self._snapshot(inventory=(pack,), equipment=(worn,), hp=150)
        )
        self.assertEqual(hurt._calibration_phase, "deposit")

        ready = self._scan_complete_policy()
        ready._calibration_town_key(
            self._snapshot(inventory=(pack,), equipment=(worn,))
        )
        self.assertEqual(ready._calibration_phase, "deposit")

    def test_live_drained_con_defers_calibration_until_restore_errand(self):
        """The captured first-cycle start must yield to its live CON errand."""
        snapshot = self._live_calibration_start_snapshot()
        policy = HengbotPolicy()
        policy.consume_home_knowledge(())

        policy.choose_key(snapshot)

        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(
            policy.equipment_optimization_state(snapshot)["calibration"],
            {
                "phase": None,
                "entry_blocker": "actionable-invalidator:stat_cur",
            },
        )

    def test_unaffordable_restore_retires_deferral_and_starts_calibration(self):
        """F1: shelf evidence retires the gate without a count or retry latch."""
        snapshot = self._live_calibration_start_snapshot()
        policy = HengbotPolicy()
        policy.consume_home_knowledge(())
        self.assertEqual(
            policy.calibration_entry_state(snapshot)["entry_blocker"],
            "actionable-invalidator:stat_cur",
        )
        expensive = store_item(
            "a",
            TVAL_POTION,
            SV_POTION_RESTORE_CON,
            price=snapshot.player.gold + 1,
            name="Restore Constitution",
        )
        alchemist = replace(
            snapshot,
            store=StoreState(STORE_ALCHEMIST, [expensive]),
        )
        # The first observation opens the town epoch; the second is retained
        # by the real shelf producer on this same policy instance.
        policy.choose_key(alchemist)
        policy.choose_key(replace(alchemist, turn=alchemist.turn + 1))

        outside = replace(snapshot, turn=snapshot.turn + 2, store=None)
        policy.choose_key(outside)

        self.assertFalse(any(
            item.sval == SV_POTION_RESTORE_CON for item in outside.inventory
        ))
        self.assertEqual(policy._home_knowledge_items, ())
        self.assertEqual(policy._calibration_phase, "deposit")
        self.assertEqual(
            policy.calibration_entry_state(outside),
            {"phase": "deposit", "entry_blocker": None},
        )

    def test_carried_restore_is_consumed_before_calibration_can_start(self):
        snapshot = self._live_calibration_start_snapshot()
        restore = item(
            "z", TVAL_POTION, SV_POTION_RESTORE_CON,
            name="Restore Constitution",
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge(())

        policy.choose_key(
            replace(snapshot, inventory=[*snapshot.inventory, restore])
        )

        self.assertEqual(policy.last_reason, "restore:quaff-con")
        self.assertIsNone(policy._calibration_phase)

    def test_home_restore_is_queued_before_calibration_can_start(self):
        snapshot = self._live_calibration_start_snapshot()
        restore = item(
            "h", TVAL_POTION, SV_POTION_RESTORE_CON, count=2,
            name="Restore Constitution",
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((restore,))

        policy.choose_key(snapshot)

        signature = policy._item_signature(restore)
        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(policy._home_pending_item, signature)
        self.assertEqual(policy._home_pending_quantities[signature], 1)
        self.assertTrue(policy._home_withdrawal_queued)
        self.assertEqual(
            policy.calibration_entry_state(snapshot)["entry_blocker"],
            "actionable-invalidator:stat_cur",
        )

    def test_actionable_remove_curse_defers_pinned_set_calibration(self):
        cursed = item(
            "main_ring", TVAL_RING, 4, name="cursed ring", known=True,
            fully_known=True, is_equipment=True, is_cursed=True,
        )
        scroll = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE,
            price=100, name="Remove Curse",
        )
        outside = self._snapshot(equipment=(cursed,))
        temple = replace(
            outside, store=StoreState(STORE_TEMPLE, [scroll])
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge(())
        policy.choose_key(temple)
        policy.choose_key(replace(temple, turn=temple.turn + 1))

        policy.choose_key(replace(outside, turn=outside.turn + 2))

        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(
            policy.calibration_entry_state(outside)["entry_blocker"],
            "actionable-invalidator:pinned-set",
        )

    def test_deposit_phase_deposits_protected_supplies_and_records_restore(self):
        policy = self._scan_complete_policy()
        cure = item(
            "a", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=5,
            name="Cure Critical Wounds",
        )
        snapshot = self._snapshot(inventory=(cure,))
        policy._calibration_phase = "deposit"

        deposit = policy._find_home_deposit(snapshot)
        self.assertIsNotNone(
            deposit,
            "the calibration deposit pass must offer even survival-kit items",
        )
        key = policy._home_deposit_key(snapshot, deposit)
        self.assertEqual(key, policy_module.SELL_KEY + "a" + "5\r")
        self.assertIn(
            policy._item_signature(cure),
            policy._calibration_restore_signatures,
        )

    def test_strip_session_takes_off_every_removable_item_but_not_cursed(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, known=True,
            fully_known=True, is_equipment=True,
        )
        cursed = item(
            "main_ring", TVAL_RING, 4, name="cursed ring", known=True,
            fully_known=True, is_equipment=True, is_cursed=True,
        )
        snapshot = self._snapshot(equipment=(sword, lantern, cursed))
        policy._calibration_phase = "deposit"
        policy._calibration_worn_before = tuple(
            (worn.slot, policy_module.equipment_identity(worn))
            for worn in (sword, lantern)
        )

        key = policy._calibration_town_key(snapshot)

        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason, "calibration:strip-installed")
        self.assertEqual(policy._calibration_phase, "strip")
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        self.assertEqual(session.required_context, "outside_home")
        actions = session.plan.actions
        self.assertEqual(
            {action.kind for action in actions}, {"takeoff"}
        )
        self.assertEqual(
            {action.target_slot for action in actions},
            {"main_hand", "light"},
            "a cursed (pinned) item must stay worn and be folded into the "
            "constants instead",
        )

    def test_capture_caches_constants_and_does_not_rerun_per_optimization(self):
        policy = self._scan_complete_policy()
        naked = self._snapshot()
        policy._calibration_phase = "capture"

        # The capture waits for the naked `C` acquisition it posted.
        policy._calibration_observe(naked)
        self.assertIsNone(policy._character_calibration)
        self.assertEqual(
            policy._calibration_town_key(naked),
            policy_module.CHARACTER_DUMP_MACRO,
        )
        self.assertEqual(
            policy.last_reason, "calibration:request-naked-character"
        )
        self.assertTrue(policy.confirm_key_posted(
            policy_module.CHARACTER_DUMP_MACRO
        ))
        policy.observe_character_snapshot({
            "mutations": [],
            "characteristics": [],
        })
        policy._calibration_observe(naked)

        self.assertIsNotNone(policy._character_calibration)
        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(
            policy._character_calibration.base_stats,
            naked.player.stat_use,
        )
        # Optimization passes now consume the cached constants; none of them
        # restarts the phase.
        for _ in range(3):
            preparation = policy._prepare_equipment_optimization(naked)
            self.assertNotIn("calibration-required", preparation.blockers)
            self.assertIsNone(policy._calibration_phase)

    def test_strip_takeoffs_reach_capture_instead_of_generic_restore(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        dressed = self._snapshot(equipment=(sword,))
        policy._begin_character_calibration(dressed)

        self.assertEqual(policy._calibration_town_key(dressed), "5")
        takeoff = policy._equipment_transaction_town_key(dressed)
        self.assertTrue(takeoff.startswith(equipment_mutation_module.TAKEOFF_KEY), takeoff)
        self.assertTrue(policy.confirm_key_posted(takeoff))

        naked = self._snapshot(inventory=(replace(sword, slot="a"),))
        key = policy.choose_key(naked)

        self.assertEqual(key, policy_module.CHARACTER_DUMP_MACRO)
        self.assertEqual(policy._calibration_phase, "capture")
        self.assertEqual(policy._equipment_transaction_owned_items, [])
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertEqual(
            policy.last_reason, "calibration:request-naked-character"
        )

    def test_capture_invalid_blocks_same_visit_and_reports_abort(self):
        policy = self._scan_complete_policy()
        policy._town_was_in_town = True
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        naked = self._snapshot(inventory=(replace(sword, slot="a"),))
        policy._calibration_phase = "capture"
        policy._calibration_naked_dump_requested = True
        policy._calibration_worn_before = (
            ("main_hand", policy_module.equipment_identity(sword)),
        )
        policy._calibration_stripped_unrestored = True

        with patch.object(
            policy_calibration_module, "calibrate_character_constants", return_value=None
        ):
            policy.choose_key(naked)

        self.assertTrue(policy._calibration_blocked_this_visit)
        self.assertEqual(policy._calibration_aborts_this_visit, 1)
        diagnostics = policy.equipment_optimization_state(naked)["calibration"]
        self.assertEqual(
            diagnostics["last_abort"],
            "calibration:abort:capture-invalid",
        )

        dressed = self._snapshot(equipment=(sword,))
        policy.choose_key(dressed)
        policy.choose_key(dressed)
        self.assertIsNone(policy._calibration_phase)
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertTrue(policy._calibration_blocked_this_visit)

    def test_successful_capture_writes_calibration_file_and_completes(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        dressed = self._snapshot(equipment=(sword,))
        policy._begin_character_calibration(dressed)
        self.assertEqual(policy._calibration_town_key(dressed), "5")
        takeoff = policy._equipment_transaction_town_key(dressed)
        self.assertTrue(policy.confirm_key_posted(takeoff))
        naked = self._snapshot(inventory=(replace(sword, slot="a"),))

        with TemporaryDirectory() as directory:
            path = Path(directory) / "character-calibration.json"
            policy._character_calibration_path = path
            self.assertEqual(
                policy.choose_key(naked), policy_module.CHARACTER_DUMP_MACRO
            )
            self.assertTrue(policy.confirm_key_posted(
                policy_module.CHARACTER_DUMP_MACRO
            ))
            policy.observe_character_snapshot({
                "mutations": [], "characteristics": [],
            })
            policy._calibration_observe(naked)

            self.assertTrue(path.is_file())
            persisted = json.loads(path.read_text(encoding="utf-8"))

        self.assertIsNotNone(policy._character_calibration)
        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(persisted["observed_turn"], naked.turn)

    def test_hostile_suspends_capture_then_resumes_without_restarting(self):
        policy = self._scan_complete_policy()
        policy._town_was_in_town = True
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(sword)
        in_pack = replace(sword, slot="a")
        threat = hostile(1, 10, 13, distance=3)
        threatened = self._snapshot(
            inventory=(in_pack,), monsters=(threat,)
        )
        policy._calibration_phase = "capture"
        policy._calibration_worn_before = (("main_hand", identity),)
        policy._calibration_stripped_unrestored = True
        policy._calibration_naked_dump_requested = False

        key = policy.choose_key(threatened)

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        self.assertEqual(policy._calibration_suspended_phase, "capture")
        self.assertEqual(policy._calibration_phase, "restore-equip")
        self.assertEqual(
            policy._calibration_worn_before, (("main_hand", identity),)
        )
        self.assertNotEqual(policy._calibration_phase, "deposit")

        restore = policy._equipment_transaction_session
        self.assertIsNotNone(restore)
        restore.dispatch(
            restore.current_action,
            policy_module.observe_equipment_transactions(threatened),
        )
        dressed = self._snapshot(equipment=(sword,))
        restore.observe(policy_module.observe_equipment_transactions(dressed))
        policy._calibration_observe(dressed)
        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(policy._calibration_suspended_phase, "capture")

        self.assertEqual(policy._calibration_town_key(dressed), "5")
        self.assertEqual(policy.last_reason, "calibration:strip-resumed")
        self.assertEqual(
            policy._calibration_worn_before, (("main_hand", identity),)
        )
        strip = policy._equipment_transaction_session
        takeoff = policy._equipment_transaction_town_key(dressed)
        self.assertTrue(policy.confirm_key_posted(takeoff))
        naked = self._snapshot(inventory=(in_pack,))
        strip.observe(policy_module.observe_equipment_transactions(naked))
        policy._town_hunt_target = None
        policy._calibration_observe(naked)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "character-calibration.json"
            policy._character_calibration_path = path
            self.assertEqual(
                policy._calibration_town_key(naked),
                policy_module.CHARACTER_DUMP_MACRO,
            )
            self.assertTrue(policy.confirm_key_posted(
                policy_module.CHARACTER_DUMP_MACRO
            ))
            policy.observe_character_snapshot({
                "mutations": [], "characteristics": [],
            })
            policy._calibration_observe(naked)
            self.assertTrue(path.is_file())

        self.assertIsNone(policy._calibration_phase)
        self.assertIsNone(policy._calibration_suspended_phase)

    def test_repeated_hostile_interruptions_spend_the_visit_budget(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(sword)
        in_pack = replace(sword, slot="a")
        threatened = self._snapshot(
            inventory=(in_pack,), monsters=(hostile(1, 10, 13, distance=3),)
        )
        for _ in range(policy_module.STORE_STUCK_LIMIT):
            policy._calibration_phase = "capture"
            policy._calibration_worn_before = (("main_hand", identity),)
            policy._calibration_stripped_unrestored = True
            policy._equipment_transaction_session = None
            policy._calibration_session_target = None
            policy._calibration_observe(threatened)
            if not policy._calibration_blocked_this_visit:
                self.assertEqual(
                    policy._calibration_suspended_phase, "capture"
                )
                policy._calibration_suspended_phase = None

        self.assertTrue(policy._calibration_blocked_this_visit)
        self.assertGreaterEqual(
            policy._calibration_aborts_this_visit,
            policy_module.STORE_STUCK_LIMIT,
        )
        self.assertIsNone(policy._calibration_suspended_phase)
        self.assertEqual(
            policy.calibration_entry_state(threatened)["last_abort"],
            "calibration:abort:precondition",
        )

    def test_interruption_restores_the_taken_off_equipment(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(sword)
        policy._calibration_phase = "strip"
        policy._calibration_worn_before = (("main_hand", identity),)
        # The strip session was abandoned (stall) and the sword is in the pack
        # when a hostile appears: the phase must re-wear it, not keep observing.
        in_pack = replace(sword, slot="c")
        threat = hostile(1, 10, 11)
        snapshot = self._snapshot(inventory=(in_pack,), monsters=(threat,))

        policy._calibration_observe(snapshot)

        self.assertEqual(policy._calibration_phase, "restore-equip")
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        self.assertEqual(
            [(action.kind, action.target_slot, action.item_identity)
             for action in session.plan.actions],
            [("equip", "main_hand", identity)],
        )
        self.assertIsNone(policy._character_calibration)

    def test_departure_waits_for_the_phase_and_the_restore_queue(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        gate = policy_module.HengbotPolicy._town_departure_conjuncts
        source = inspect.getsource(gate)
        self.assertIn("not self._calibration_active()", source)
        self.assertIn("not self._calibration_restore_signatures", source)

        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [("x", 75, 1)]
        self.assertFalse(policy._town_departure_ready(snapshot))

    def test_live_capture_batches_same_page_restore_through_public_keys(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "calibration-restore-batch-live.jsonl.gz"
        )
        with gzip.open(fixture, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        self.assertEqual([row["decision_index"] for row in rows], [5432, 5433])

        policy = restore_checkpoint(
            HengbotPolicy,
            rows[0]["predecision_policy_checkpoint_pickle_b64"],
        )
        entrance = pickle.loads(base64.b64decode(
            rows[0]["decision_snapshot_pickle_b64"]
        ))
        inside = pickle.loads(base64.b64decode(
            rows[1]["decision_snapshot_pickle_b64"]
        ))
        expected = (
            "pZ47\r"
            "pW2\r"
            "py"
            "pu2\r"
            "pq"
            "pk6\r"
            "pi30\r"
            "ph87\r"
            "pf6\r"
            "pe29\r"
            "pd"
            "pa9\r"
            "\x1b"
        )

        first = policy.choose_key(entrance)

        self.assertEqual(first, WAIT_KEY)
        self.assertEqual(policy.last_reason, "calibration:atomic-restore-withdraw")
        self.assertTrue(policy._home_procurement_batch_active)
        self.assertEqual(
            policy._home_pending_batch,
            policy._calibration_restore_signatures,
        )
        self.assertEqual(policy._store_visit.operation_key, expected)
        self.assertTrue(policy.confirm_key_posted(first))

        second = policy.choose_key(inside)

        self.assertEqual(second, expected)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")
        self.assertEqual(policy.choose_key(inside), policy_module.LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:leave-after-one-operation")

        pending = policy._home_atomic_withdraw_pending
        restored = [
            replace(withdrawn, slot=chr(ord("a") + offset))
            for offset, (
                _signature, _before_count, withdrawn, _quantity, _index
            ) in enumerate(pending[4])
        ]
        # After the captured producer and key consumer have run, isolate only
        # durable history I/O while the public outside observer reconciles
        # every batch effect.
        with patch.object(policy._home_disposal, "record") as history_record:
            policy.choose_key(replace(
                entrance,
                turn=entrance.turn + 1,
                inventory=restored,
            ))

        self.assertEqual(len(policy._calibration_restore_signatures), 2)
        self.assertEqual(len(policy._home_pending_batch), 2)
        self.assertTrue(policy._home_procurement_batch_active)
        self.assertFalse(policy._home_knowledge_current)
        self.assertEqual(history_record.call_count, 12)

    def test_live_restore_window_keeps_queue_after_confirming_home_pages(self):
        """02:57:50-53 pin: Home was just observed, but its atomic-operation
        pages could not yet establish a fresh address.  The T3 close must
        reopen that reachable Home for the remaining restore, not destroy the
        only owner of the queue.  This fixture is committed data shaped from
        the retained snapshots; it never reads jsonlog at test time.
        """
        policy = self._scan_complete_policy()
        snapshot = replace(
            self._snapshot(
                inventory=tuple(
                    item(chr(ord("a") + index), TVAL_POTION, SV_POTION_CURE_CRITICAL)
                    for index in range(11)
                ),
                equipment=(
                    item(
                        "light", TVAL_LITE, SV_LITE_FEANOR,
                        known=True, fully_known=True, is_equipment=True,
                    ),
                ),
            ),
            turn=2940289,
        )
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [("restore", 75, 1)]
        policy._home_address_scan_valid = False
        policy._calibration_home_rearm_eligible = True
        policy._calibration_home_rearm_queue = tuple(
            policy._calibration_restore_signatures
        )
        policy._town_was_in_town = True
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = (
            policy_module.TOWN_STOP_PASS_LIMIT
        )

        key = policy.choose_key(snapshot)

        self.assertEqual(len(snapshot.inventory), 11)
        self.assertEqual(len(snapshot.equipment), 1)
        self.assertEqual(policy._calibration_phase, "restore-supplies")
        self.assertEqual(
            policy._calibration_restore_signatures, [("restore", 75, 1)]
        )
        self.assertIn(snapshot.player.position, snapshot.grids)
        self.assertEqual(snapshot.grids[self.HOME].store_number, STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertFalse(policy._calibration_home_rearm_eligible)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME],
            policy_module.TOWN_STOP_PASS_LIMIT,
        )
        self.assertNotEqual(key, WAIT_KEY, "reachable Home retains a routing exit")

    def test_blocking_leave_cannot_manufacture_restore_rearm(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [("restore", 75, 1)]
        policy._last_snapshot_was_store = True
        policy._last_snapshot_store_type = STORE_HOME
        policy._calibration_blocked_this_visit = True
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = (
            policy_module.TOWN_STOP_PASS_LIMIT
        )

        policy.choose_key(snapshot)

        self.assertFalse(policy._calibration_home_rearm_eligible)
        self.assertEqual(policy._calibration_restore_signatures, [])

    def test_calibration_telemetry_names_first_failed_entry_guard(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        policy._calibration_blocked_this_visit = True
        policy._calibration_restore_signatures = [("restore", 75, 1)]

        state = policy.equipment_optimization_state(snapshot)

        self.assertEqual(
            state["calibration"],
            {"phase": None, "entry_blocker": "visit-blocked"},
        )
        self.assertEqual(
            state["equipment_transaction"],
            {"context": None, "entry_blocker": "no-session"},
        )

    def test_calibration_telemetry_keeps_the_gate_evaluated_refusal(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        policy._identification_need = "normal"

        policy._calibration_town_key(snapshot)
        policy._identification_need = None

        self.assertEqual(
            policy.calibration_entry_state(snapshot)["entry_blocker"],
            "identification-active",
        )

    def test_calibration_required_never_reports_null_phase_and_blocker(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None
        )
        policy._identification_need = "normal"

        policy._calibration_town_key(snapshot)
        state = policy.calibration_entry_state(snapshot)

        self.assertFalse(
            state["phase"] is None and state["entry_blocker"] is None,
            state,
        )

    def test_unactionable_identification_retires_and_new_source_revives(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        policy._identification_need = "normal"
        policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn

        self.assertFalse(policy._identification_need_actionable(snapshot))
        self.assertNotEqual(
            policy.calibration_entry_state(snapshot)["entry_blocker"],
            "identification-active",
        )
        policy._calibration_town_key(snapshot)
        self.assertIsNotNone(policy._calibration_phase)

        policy._calibration_phase = None
        identify = item(
            "i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Scroll of Identify"
        )
        revived = replace(snapshot, inventory=[*snapshot.inventory, identify])
        self.assertTrue(policy._identification_need_actionable(revived))

    def test_unactionable_home_identification_routes_when_home_unblocked(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        target = store_item("a", TVAL_SWORD, 1, name="Home blade")
        policy._identification_need = "normal"
        policy._identification_candidate = policy._item_signature(target)
        policy._equipment_catalog._home = {
            "target": OwnedEquipment("target", target, "home")
        }
        with patch.object(
            policy, "_identification_need_actionable", return_value=False
        ):
            store_type = policy._next_required_store_type(snapshot)

        self.assertEqual(store_type, STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

    def test_blocked_unactionable_home_identification_retires_once(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        target = store_item("a", TVAL_SWORD, 1, name="Home blade")
        policy._identification_need = "normal"
        policy._identification_candidate = policy._item_signature(target)
        policy._equipment_catalog._home = {
            "target": OwnedEquipment("target", target, "home")
        }
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy._town_store_visit_limit(STORE_HOME)
        )
        with patch.object(
            policy, "_identification_need_actionable", return_value=False
        ), patch.object(
            policy, "_town_terminal_transitions"
        ) as retire:
            store_type = policy._next_required_store_type(snapshot)

        retire.assert_called_once_with(snapshot)
        self.assertNotEqual(store_type, STORE_HOME)

    def test_live_phase_telemetry_names_blocked_home(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        policy._calibration_phase = "deposit"
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)

        state = policy.calibration_entry_state(snapshot)

        self.assertEqual(
            state, {"phase": "deposit", "entry_blocker": "home-visit-blocked"}
        )

        policy._town_visit_ledger.blocked_stores.discard(STORE_HOME)
        healthy = policy.calibration_entry_state(snapshot)

        self.assertEqual(
            healthy, {"phase": "deposit", "entry_blocker": None}
        )

    def test_entry_telemetry_does_not_change_public_decision(self):
        def fixture():
            policy = self._scan_complete_policy()
            snapshot = self._snapshot()
            policy._calibration_blocked_this_visit = True
            return policy, snapshot

        control, snapshot = fixture()
        observed, observed_snapshot = fixture()

        control_key = control.choose_key(snapshot)
        observed.calibration_entry_state(observed_snapshot)
        observed.equipment_transaction_entry_state(observed_snapshot)
        observed_key = observed.choose_key(observed_snapshot)

        self.assertEqual(observed_key, control_key)
        self.assertEqual(observed.last_reason, control.last_reason)

    def test_stalled_restore_equip_converges_to_capture_never_naked_depart(self):
        """Exhausting the restore budget while naked and calm must CONVERGE:
        capture the calibration (opening the calibration-required gate) and
        hand dressing to the optimizer — while the stripped guard keeps every
        departure path closed until a dressing pass completes.
        """
        policy = self._scan_complete_policy()
        policy._mutation_signature = (1,)
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(sword)
        in_pack = replace(sword, slot="c")
        snapshot = self._snapshot(inventory=(in_pack,))
        policy._calibration_phase = "restore-equip"
        policy._calibration_worn_before = (("main_hand", identity),)
        policy._calibration_stripped_unrestored = True

        reinstalls = 0
        for _ in range(policy_module.STORE_STUCK_LIMIT + 3):
            if policy._calibration_phase != "restore-equip":
                break
            # Simulate the confirmation stall bound abandoning the session.
            policy._equipment_transaction_session = None
            policy._calibration_observe(snapshot)
            if policy._equipment_transaction_session is not None:
                reinstalls += 1

        self.assertGreater(reinstalls, 0, "the restore must be retried at all")
        self.assertLessEqual(reinstalls, policy_module.STORE_STUCK_LIMIT)
        self.assertIsNone(policy._calibration_phase)
        # CONVERGED: the constants were captured from the naked observation,
        # so the gate the undressed state used to hold closed is now open and
        # the optimizer owns dressing.
        self.assertIsNotNone(policy._character_calibration)
        preparation = policy._prepare_equipment_optimization(snapshot)
        self.assertNotIn("calibration-required", preparation.blockers)
        # ...but departure stays unreachable until a dressing pass completes:
        # the stripped guard holds even though the calibration gate is open.
        self.assertTrue(policy._calibration_stripped_unrestored)
        self.assertFalse(policy._town_departure_ready(snapshot))
        # An unrelated optimizer completion is not evidence that the recorded
        # sword returned; the durable calibration debt remains armed.
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((), (), 0)
            )
        )
        key = policy.choose_key(snapshot)
        self.assertTrue(policy._calibration_stripped_unrestored)
        self.assertTrue(key.startswith(equipment_mutation_module.WIELD_KEY), key)

    def test_partial_strip_exhaustion_dresses_under_persistent_threat(self):
        """REVIEW-p1-calibration4 BLOCKER regression: partial strip +
        PERSISTENT hostile + exhausted restore budget.  Re-dressing has none
        of the capture preconditions — it must be attemptable under threat,
        at any HP.  This drives consecutive real decisions with the hostile
        present in EVERY snapshot (never hand-edited calm) and only simulates
        the game's response to the wear keys the bot itself emits; the bot
        must dress itself, the retained identities must never be discarded,
        and the observed recovery must clear the guard while leaving the
        visit's spent calibration budget spent.
        """
        policy = self._scan_complete_policy()
        policy._mutation_signature = (1,)
        # One continuous town visit: the fresh-visit observation is the only
        # legitimate budget re-arm and must not fire mid-test.
        policy._town_was_in_town = True
        sword = item(
            "c", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, known=True,
            fully_known=True, is_equipment=True,
        )
        sword_identity = policy_module.equipment_identity(sword)
        lantern_identity = policy_module.equipment_identity(lantern)
        threat = hostile(1, 10, 13, distance=3)

        def threatened(inventory, equipment):
            return self._snapshot(
                inventory=tuple(inventory), equipment=tuple(equipment),
                monsters=(threat,),
            )

        # PARTIAL strip: the sword came off (pack slot c), the lantern is
        # still worn, and the hostile never leaves.
        policy._calibration_phase = "restore-equip"
        policy._calibration_worn_before = (
            ("light", lantern_identity),
            ("main_hand", sword_identity),
        )
        policy._calibration_stripped_unrestored = True

        # Exhaust the restore budget entirely under threat.
        for _ in range(policy_module.STORE_STUCK_LIMIT + 3):
            if policy._equipment_transaction_session is not None:
                policy._equipment_transaction_session = None
            policy._calibration_observe(threatened([sword], [lantern]))
            if policy._calibration_blocked_this_visit:
                break
        self.assertTrue(policy._calibration_blocked_this_visit)
        # Redress-mode: identities RETAINED, no dormancy park, no session.
        self.assertEqual(
            policy._calibration_worn_before,
            (("light", lantern_identity), ("main_hand", sword_identity)),
        )
        self.assertIsNone(policy._calibration_phase)
        self.assertTrue(policy._calibration_stripped_unrestored)
        self.assertFalse(
            policy._town_departure_ready(threatened([sword], [lantern]))
        )

        # Drive real decisions with the hostile present in every snapshot.
        # Only the game's response to a wear key is simulated; nothing else
        # about the world changes and no calm is ever injected.
        inventory = [sword]
        equipment = [lantern]
        recorded = {
            sword_identity: "main_hand",
            lantern_identity: "light",
        }
        for _ in range(30):
            if not policy._calibration_stripped_unrestored:
                break
            snapshot = threatened(inventory, equipment)
            key = policy.choose_key(snapshot)
            if not key or not key.startswith(equipment_mutation_module.WIELD_KEY):
                continue
            letter = key[len(equipment_mutation_module.WIELD_KEY)]
            worn_item = next(
                (entry for entry in inventory if entry.slot == letter), None
            )
            if worn_item is None:
                continue
            inventory = [
                entry for entry in inventory if entry.slot != letter
            ]
            equipment = equipment + [
                replace(
                    worn_item,
                    slot=recorded[policy_module.equipment_identity(worn_item)],
                )
            ]

        # DRESSED: every recorded identity is worn again, proven by the
        # decisions the bot itself took under unbroken threat.
        self.assertEqual(
            {policy_module.equipment_identity(entry) for entry in equipment},
            {sword_identity, lantern_identity},
            "the bot never dressed itself under the persistent hostile",
        )
        # The observed recovery cleared the guard — the departure conjunct
        # it held closed is open again — while the visit's calibration
        # budget stays SPENT: recovery reopens departure, never a fresh
        # same-visit strip.
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertEqual(policy._calibration_worn_before, ())
        self.assertTrue(policy._calibration_blocked_this_visit)
        self.assertGreaterEqual(
            policy._calibration_aborts_this_visit,
            policy_module.STORE_STUCK_LIMIT,
        )

    def test_duplicate_identities_never_double_satisfy_the_redress(self):
        """REVIEW-p1-calibration5 BLOCKER regression: equipment_identity
        collapses physically identical copies, so the redress accounting must
        consume one OCCURRENCE per recorded entry (digest + occurrence, the
        quarantine shape) on both the wear-edge and guard-release sides.  Two
        identical recorded swords with one worn and one in the pack must
        still produce a wear edge, and the guard must release only once both
        slots are filled — never with a slot naked."""
        policy = self._scan_complete_policy()
        policy._mutation_signature = (1,)
        worn_sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        pack_sword = replace(worn_sword, slot="c")
        identity = policy_module.equipment_identity(worn_sword)
        policy._calibration_worn_before = (
            ("main_hand", identity),
            ("sub_hand", identity),
        )
        policy._calibration_stripped_unrestored = True

        partial = self._snapshot(
            inventory=(pack_sword,), equipment=(worn_sword,)
        )
        # The wear edge exists: one occurrence satisfies only ONE entry.
        outstanding = policy._calibration_redress_items(partial)
        self.assertEqual(outstanding, [("sub_hand", identity)])

        key = policy.choose_key(partial)
        # The guard must NOT release while the pack copy remains...
        self.assertTrue(
            policy._calibration_stripped_unrestored,
            "one worn duplicate falsely satisfied both recorded entries",
        )
        self.assertEqual(
            policy._calibration_worn_before,
            (("main_hand", identity), ("sub_hand", identity)),
        )
        # ...and the decision itself is the wear edge for the pack copy.
        self.assertTrue(key.startswith(equipment_mutation_module.WIELD_KEY), key)
        self.assertIn("c", key)
        self.assertEqual(policy.last_reason, "calibration:redress")

        # Both slots filled: the observed release is now correct.  (Driving
        # choose_key here would release the guard in the prologue and then
        # legitimately START a fresh calibration on the dressed calm
        # character, re-arming the flag for the new phase — so pin the
        # release mechanism itself.)
        dressed = self._snapshot(
            equipment=(worn_sword, replace(pack_sword, slot="sub_hand"))
        )
        policy._calibration_observe(dressed)
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertEqual(policy._calibration_worn_before, ())

    def test_redress_recovery_does_not_rearm_a_same_visit_strip_cycle(self):
        """REVIEW-p1-calibration6 BLOCKER regression: the observed redress
        must reopen DEPARTURE (clear the stripped guard), never the visit's
        calibration budget.  Re-arming the budget made the same calm town
        visit strip, fail, redress and strip again indefinitely.  This drives
        the whole loop through public choose_key — dressed -> strip ->
        exhaustion -> redress -> dressed — and pins that the second dressed
        observation does NOT begin a fresh strip while the guard is cleared.
        """
        policy = self._scan_complete_policy()
        policy._mutation_signature = (1,)
        policy._town_was_in_town = True
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        shovel = item(
            "sub_hand", 23, 5, name="dagger",
            known=True, fully_known=True, is_equipment=True,
        )
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, known=True,
            fully_known=True, is_equipment=True,
        )
        dressed = self._snapshot(equipment=(shovel, sword, lantern))

        # First dressed calm observation legitimately starts calibration and
        # installs the strip (empty pack -> straight to the takeoffs).
        key = policy.choose_key(dressed)
        self.assertEqual(key, "5")
        self.assertEqual(policy._calibration_phase, "strip")
        self.assertTrue(policy._calibration_stripped_unrestored)

        # Partial strip: the sword comes off, then an interruption aborts the
        # phase into restore-equip and the restore budget is exhausted.
        sword_in_pack = replace(sword, slot="c")
        shovel_in_pack = replace(shovel, slot="d")
        threat = hostile(1, 10, 13, distance=3)
        partial_threatened = self._snapshot(
            inventory=(shovel_in_pack, sword_in_pack), equipment=(lantern,),
            monsters=(threat,),
        )
        policy._calibration_observe(partial_threatened)
        self.assertEqual(policy._calibration_phase, "restore-equip")
        for _ in range(policy_module.STORE_STUCK_LIMIT + 3):
            if policy._calibration_blocked_this_visit:
                break
            policy._equipment_transaction_session = None
            policy._calibration_observe(partial_threatened)
        self.assertTrue(policy._calibration_blocked_this_visit)
        self.assertIsNone(policy._calibration_phase)

        # Redress under the ordinary machinery, still one visit.
        partial_calm = self._snapshot(
            inventory=(shovel_in_pack, sword_in_pack), equipment=(lantern,)
        )
        key = policy.choose_key(partial_calm)
        self.assertEqual(key, equipment_mutation_module.WIELD_KEY + "c")
        self.assertEqual(policy.last_reason, "calibration:redress")
        self.assertNotIn(
            ("sub_hand", policy_module.equipment_identity(shovel)),
            policy._calibration_redress_attempts,
            "main-hand ordering must avoid first refusing the reachable sub hand",
        )

        # Dressed again: the guard clears (departure conjunct reopens) and
        # the SAME calm dressed observation must NOT begin a fresh strip —
        # the visit's calibration budget stays spent.
        key = policy.choose_key(dressed)
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertEqual(policy._calibration_worn_before, ())
        self.assertNotEqual(
            policy._calibration_phase, "strip",
            "the redress recovery re-armed a same-visit strip cycle",
        )
        self.assertIsNone(policy._calibration_phase)
        self.assertTrue(policy._calibration_blocked_this_visit)
        # And once more, to pin that the loop cannot restart later either.
        policy.choose_key(dressed)
        self.assertIsNone(policy._calibration_phase)

    def test_sub_hand_only_redress_refusals_release_departure_gate(self):
        """Seq 792/793: the live producer cannot leave a refused debt forever."""
        policy = self._scan_complete_policy()
        policy._mutation_signature = (1,)
        policy._town_was_in_town = True
        sub = item(
            "sub_hand", 23, 5, name="dagger", known=True,
            fully_known=True, is_equipment=True,
        )
        main = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
            known=True, fully_known=True, is_equipment=True,
        )
        dressed = self._snapshot(equipment=(sub, main, lantern))
        self.assertEqual(policy.choose_key(dressed), "5")

        # The real calibration observer aborts the partial strip and then
        # exhausts its restore session.  Its closed-world accounting releases
        # the missing main-hand item, reproducing the captured sub-only debt.
        sub_in_pack = replace(sub, slot="c")
        threat = hostile(1, 10, 13, distance=3)
        partial = self._snapshot(
            inventory=(sub_in_pack,), equipment=(lantern,), monsters=(threat,)
        )
        policy._calibration_observe(partial)
        for _ in range(STORE_STUCK_LIMIT + 3):
            if policy._calibration_blocked_this_visit:
                break
            policy._equipment_transaction_session = None
            policy._calibration_observe(partial)
        calm = self._snapshot(inventory=(sub_in_pack,), equipment=(lantern,))

        # The lost-main producer emits its one-shot abandonment observation;
        # the following STORE_STUCK_LIMIT+2 decisions are the refusal drive.
        policy.choose_key(calm)
        charged_attempts = []
        for _ in range(STORE_STUCK_LIMIT + 2):
            policy.choose_key(calm)
            charged_attempts.append(max(
                policy._calibration_redress_attempts.values(), default=0
            ))

        self.assertGreaterEqual(max(charged_attempts), STORE_STUCK_LIMIT)
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertTrue(policy._town_departure_conjuncts(calm)[
            "calibration_loadout_restored"
        ])

    def test_restore_completion_releases_the_stripped_guard(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(sword)
        in_pack = replace(sword, slot="c")
        snapshot = self._snapshot(inventory=(in_pack,))
        policy._calibration_phase = "strip"
        policy._calibration_worn_before = (("main_hand", identity),)
        # Interruption: hostile appears mid-strip.
        threat = hostile(1, 10, 11)
        threatened = self._snapshot(inventory=(in_pack,), monsters=(threat,))
        policy._calibration_stripped_unrestored = True
        policy._calibration_observe(threatened)
        self.assertEqual(policy._calibration_phase, "restore-equip")
        self.assertTrue(policy._calibration_stripped_unrestored)
        # The restore session completing (sword back on) releases the guard.
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        dressed = self._snapshot(equipment=(sword,))
        session.dispatch(
            session.current_action,
            policy_module.observe_equipment_transactions(
                self._snapshot(inventory=(in_pack,))
            ),
        )
        session.observe(
            policy_module.observe_equipment_transactions(dressed)
        )
        self.assertTrue(session.complete)
        policy._calibration_observe(dressed)
        self.assertIsNone(policy._calibration_phase)
        self.assertFalse(policy._calibration_stripped_unrestored)

    def test_checkpoint_redress_debt_files_home_restore_ahead_of_optimizer(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(sword)
        home_sword = replace(sword, slot="a")
        policy._calibration_worn_before = (("main_hand", identity),)
        policy._calibration_stripped_unrestored = True
        policy._home_knowledge_items = [home_sword]
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((), (), 0)
            )
        )

        policy._calibration_redress_observe(self._snapshot())

        self.assertEqual(policy._calibration_phase, "restore-supplies")
        self.assertEqual(
            policy._calibration_restore_signatures,
            [policy._item_signature(home_sword)],
        )
        self.assertIsNone(policy._equipment_transaction_session)
        request = policy._derived_home_visit_request(self._snapshot())
        self.assertEqual(request.kind, policy_module.HomeVisitKind.CALIBRATION_RESTORE)
        self.assertEqual(request.requester, "calibration-restore")

    def test_unavailable_checkpoint_redress_debt_releases_visibly_once(self):
        policy = self._scan_complete_policy()
        sword = item(
            "main_hand", 23, 4, name="lost sword", known=True,
            fully_known=True, is_equipment=True,
        )
        policy._calibration_worn_before = (
            ("main_hand", policy_module.equipment_identity(sword)),
        )
        policy._calibration_stripped_unrestored = True
        snapshot = self._snapshot()

        policy._calibration_redress_observe(snapshot)
        key = policy._calibration_redress_key(snapshot)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "calibration:redress-abandoned:item-unavailable",
        )
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertEqual(policy._calibration_worn_before, ())
        self.assertIsNone(policy._calibration_redress_key(snapshot))

    def test_departure_unsatisfiable_is_an_immediate_cli_final_stop(self):
        self.assertIn(
            "town:blocked:departure-unsatisfiable", POLICY_FINAL_STOP_REASONS
        )

    def test_redress_obligation_survives_restart_and_posts_recorded_wear(self):
        sword = item(
            "main_hand", 23, 4, name="long sword", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(sword)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "character-calibration.json"
            first = self._scan_complete_policy()
            first._character_calibration_path = path
            first._calibration_worn_before = (("main_hand", identity),)
            first._calibration_phase = "deposit"
            self.assertEqual(first._calibration_town_key(
                self._snapshot(equipment=(sword,))
            ), "5")
            self.assertIn("redress_obligation", json.loads(path.read_text()))

            fresh = self._scan_complete_policy()
            fresh._character_calibration_path = path
            in_pack = replace(sword, slot="c")
            stripped = self._snapshot(inventory=(in_pack,))
            key = fresh.choose_key(stripped)
            self.assertEqual(key, equipment_mutation_module.WIELD_KEY + "c")
            self.assertEqual(fresh.last_reason, "calibration:redress")
            self.assertTrue(fresh._calibration_stripped_unrestored)

            dressed = self._snapshot(equipment=(sword,))
            fresh._calibration_observe(dressed)
            self.assertFalse(fresh._calibration_stripped_unrestored)
            self.assertNotIn(
                "redress_obligation", json.loads(path.read_text())
            )

    def test_redress_ring_uses_original_keyset_endpoint_for_empty_main_ring(self):
        policy = self._scan_complete_policy()
        ring = item(
            "e", policy_module.TVAL_RING, 43, name="ring", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(ring)
        policy._calibration_worn_before = (("main_ring", identity),)
        policy._calibration_stripped_unrestored = True

        key = policy._calibration_redress_key(self._snapshot(inventory=(ring,)))

        self.assertEqual(key, "we(")
        self.assertEqual(policy.last_reason, "calibration:redress")

    def test_six_item_redress_bounds_ring_noop_and_wears_every_later_item(self):
        policy = self._scan_complete_policy()
        packed = [
            item("e", policy_module.TVAL_RING, 43, name="ring", known=True,
                 fully_known=True, is_equipment=True),
            item("f", policy_module.TVAL_AMULET, 1, name="amulet", known=True,
                 fully_known=True, is_equipment=True),
            item("g", policy_module.TVAL_HARD_ARMOR, 1, name="body armour [24,+23]",
                 known=True, fully_known=True, is_equipment=True),
            item("h", policy_module.TVAL_CLOAK, 1, name="cloak", known=True,
                 fully_known=True, is_equipment=True),
            item("i", policy_module.TVAL_HELM, 1, name="helm", known=True,
                 fully_known=True, is_equipment=True),
            item("j", policy_module.TVAL_BOW, 1, name="sling", known=True,
                 fully_known=True, is_equipment=True),
        ]
        target_slots = ("main_ring", "neck", "body", "outer", "head", "bow")
        target_by_letter = dict(zip("efghij", target_slots))
        policy._calibration_worn_before = tuple(
            (slot, policy_module.equipment_identity(entry))
            for slot, entry in zip(target_slots, packed)
        )
        policy._calibration_stripped_unrestored = True
        equipment = []
        posted = []

        while len(equipment) < 5:
            snapshot = self._snapshot(
                inventory=tuple(packed), equipment=tuple(equipment)
            )
            key = policy._calibration_redress_key(snapshot)
            posted.append(key)
            if key == "we(":
                continue
            pack_letter = key[1]
            worn = next(entry for entry in packed if entry.slot == pack_letter)
            packed.remove(worn)
            equipment.append(replace(worn, slot=target_by_letter[pack_letter]))

        self.assertEqual(
            posted,
            ["we("] * policy_module.STORE_STUCK_LIMIT
            + ["wf", "wg", "wh", "wi", "wj"],
        )
        self.assertLessEqual(posted.count("we("), policy_module.STORE_STUCK_LIMIT)
        self.assertEqual({entry.slot for entry in equipment},
                         {"neck", "body", "outer", "head", "bow"})
        policy._calibration_redress_observe(
            self._snapshot(inventory=tuple(packed), equipment=tuple(equipment))
        )
        self.assertFalse(policy._calibration_stripped_unrestored)

    def test_legacy_cursed_only_shape_redresses_confirmed_pack_armour(self):
        cursed = item(
            "arms", policy_module.TVAL_GLOVES, 1, name="cursed gloves", known=True,
            fully_known=True, is_equipment=True, is_cursed=True,
        )
        body = item("a", policy_module.TVAL_HARD_ARMOR, 1, name="mail", known=True,
                    fully_known=True, is_equipment=True)
        outer = item("b", policy_module.TVAL_CLOAK, 1, name="cloak", known=True,
                     fully_known=True, is_equipment=True)
        head = item("c", policy_module.TVAL_HELM, 1, name="helm", known=True,
                    fully_known=True, is_equipment=True)
        neck = item("d", policy_module.TVAL_AMULET, 1, name="amulet", known=True,
                    fully_known=True, is_equipment=True)
        ring = item("e", policy_module.TVAL_RING, 1, name="ring", known=True,
                    fully_known=True, is_equipment=True)
        packed = [body, outer, head, neck, ring]
        snapshot = self._snapshot(inventory=tuple(packed), equipment=(cursed,))
        calibration = policy_module.calibrate_character_constants(snapshot)
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            calibration_path = directory / "character-calibration.json"
            confirmed_path = directory / "confirmed-loadout.json"
            policy_module.save_character_calibration(calibration_path, calibration)
            ids = frozenset(
                f"equipped:{policy_module.equipment_identity(entry)}:0"
                for entry in (*packed, cursed)
            )
            policy_module.save_confirmed_loadout(
                confirmed_path,
                policy_module.confirmed_loadout_record(ids, "0" * 64),
            )
            policy = self._scan_complete_policy()
            policy._character_calibration_path = calibration_path
            policy._confirmed_loadout_path = confirmed_path

            equipment = [cursed]
            posted = []
            for _ in range(len(packed)):
                current = self._snapshot(
                    inventory=tuple(packed), equipment=tuple(equipment)
                )
                key = policy.choose_key(current)
                posted.append(key)
                letter = key[len(equipment_mutation_module.WIELD_KEY)]
                worn = next(entry for entry in packed if entry.slot == letter)
                target_slot = {
                    identity: slot
                    for slot, identity in policy._calibration_worn_before
                }[policy_module.equipment_identity(worn)]
                packed.remove(worn)
                equipment.append(replace(worn, slot=target_slot))

            policy._calibration_observe(self._snapshot(equipment=tuple(equipment)))
            self.assertEqual(
                posted,
                [equipment_mutation_module.WIELD_KEY + letter for letter in "abcde"[:-1]]
                + [equipment_mutation_module.WIELD_KEY + "e("],
            )
            self.assertEqual(
                {entry.slot for entry in equipment},
                {"arms", "body", "outer", "head", "neck", "main_ring"},
            )
            self.assertFalse(policy._calibration_stripped_unrestored)

    def test_optimizer_completion_does_not_discharge_redress_debt(self):
        policy = self._scan_complete_policy()
        sword = item("c", 23, 4, name="sword", known=True,
                     fully_known=True, is_equipment=True)
        policy._calibration_worn_before = (
            ("main_hand", policy_module.equipment_identity(sword)),
        )
        policy._calibration_stripped_unrestored = True
        policy._equipment_transaction_session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((), (), 0)
        )
        policy.choose_key(self._snapshot(inventory=(sword,)))
        self.assertTrue(policy._calibration_stripped_unrestored)

    def test_forced_floor_change_does_not_discharge_redress_debt(self):
        policy = self._scan_complete_policy()
        sword = item("c", 23, 4, name="sword", known=True,
                     fully_known=True, is_equipment=True)
        policy._calibration_phase = "capture"
        policy._calibration_worn_before = (
            ("main_hand", policy_module.equipment_identity(sword)),
        )
        policy._calibration_stripped_unrestored = True
        policy._calibration_observe(replace(
            self._snapshot(inventory=(sword,)),
            floor_key=(1, 1, 0),
            town_flag=False,
        ))
        self.assertTrue(policy._calibration_stripped_unrestored)
        self.assertEqual(len(policy._calibration_worn_before), 1)

    def test_capture_phase_end_does_not_discharge_redress_debt(self):
        policy = self._scan_complete_policy()
        sword = item("c", 23, 4, name="sword", known=True,
                     fully_known=True, is_equipment=True)
        policy._calibration_phase = "capture"
        policy._calibration_naked_dump_requested = True
        policy._calibration_worn_before = (
            ("main_hand", policy_module.equipment_identity(sword)),
        )
        policy._calibration_stripped_unrestored = True
        policy._calibration_observe(self._snapshot(inventory=(sword,)))
        self.assertIsNone(policy._calibration_phase)
        self.assertTrue(policy._calibration_stripped_unrestored)
        self.assertEqual(len(policy._calibration_worn_before), 1)

    def test_never_stripped_character_gets_no_spurious_redress_key(self):
        policy = self._scan_complete_policy()
        armour = item("a", policy_module.TVAL_HARD_ARMOR, 1, name="mail", known=True,
                      fully_known=True, is_equipment=True)
        snapshot = self._snapshot(inventory=(armour,))
        policy._restore_calibration_redress_obligation(snapshot)
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertIsNone(policy._calibration_redress_key(snapshot))

    def test_naked_dump_is_latched_at_posting_with_no_retry_counter(self):
        """The capture-phase `C` request follows the reviewed request rules:
        offered until the transport confirms the posted key, then consumed;
        a missing response is bounded by ONE board-snapshot observation and
        the capture proceeds degraded — no counter, no wait loop."""
        policy = self._scan_complete_policy()
        naked = self._snapshot()
        policy._calibration_phase = "capture"

        # Offered until confirmed: a suppressed or replaced key must not
        # consume the request.
        self.assertEqual(
            policy._calibration_town_key(naked),
            policy_module.CHARACTER_DUMP_MACRO,
        )
        self.assertFalse(policy._calibration_naked_dump_requested)
        policy._calibration_naked_dump_prepared = False
        self.assertEqual(
            policy._calibration_town_key(naked),
            policy_module.CHARACTER_DUMP_MACRO,
        )
        self.assertTrue(policy.confirm_key_posted(
            policy_module.CHARACTER_DUMP_MACRO
        ))
        self.assertTrue(policy._calibration_naked_dump_requested)
        self.assertTrue(policy._calibration_naked_dump_inflight)
        # A periodic dump posted OUTSIDE the capture latch never converts.
        self.assertFalse(policy.confirm_key_posted(
            policy_module.CHARACTER_DUMP_MACRO
        ))

        # Missing response: one observation clears the inflight, the next
        # captures without characteristics — degraded, never absorbing.
        policy._calibration_observe(naked)
        self.assertFalse(policy._calibration_naked_dump_inflight)
        self.assertIsNone(policy._character_calibration)
        policy._calibration_observe(naked)
        self.assertIsNotNone(policy._character_calibration)
        self.assertEqual(
            policy._character_calibration.intrinsic_tr_flags, frozenset()
        )
        self.assertFalse(hasattr(policy, "_mutation_scan_retries_remaining"))

    def test_naked_dump_respects_the_confirmed_outside_gate(self):
        policy = self._scan_complete_policy()
        naked = self._snapshot()
        policy._calibration_phase = "capture"
        # Positive control first (parent-differentiating): with a clean
        # outside context the naked dump IS offered...
        self.assertEqual(
            policy._calibration_town_key(naked),
            policy_module.CHARACTER_DUMP_MACRO,
        )
        # ...and each store-context guard suppresses exactly it.
        policy._calibration_naked_dump_prepared = False
        policy._store_leave_inflight = (1, naked.turn, STORE_HOME)
        self.assertNotEqual(
            policy._calibration_town_key(naked),
            policy_module.CHARACTER_DUMP_MACRO,
        )
        policy._store_leave_inflight = None
        policy._last_snapshot_was_store = True
        self.assertNotEqual(
            policy._calibration_town_key(naked),
            policy_module.CHARACTER_DUMP_MACRO,
        )

    def test_naked_characteristics_reach_the_captured_constants(self):
        """The naked `C` response's characteristics table (permanent
        vulnerabilities and friends) becomes worn-independent search input,
        and its mutation set arms the invalidation trigger at capture."""
        policy = self._scan_complete_policy()
        naked = self._snapshot()
        policy._calibration_phase = "capture"
        self.assertEqual(
            policy._calibration_town_key(naked),
            policy_module.CHARACTER_DUMP_MACRO,
        )
        self.assertTrue(policy.confirm_key_posted(
            policy_module.CHARACTER_DUMP_MACRO
        ))
        policy.observe_character_snapshot({
            "mutations": [9, 2],
            "characteristics": [
                {"flag_id": 155, "player": False, "vulnerability": True},
                {"flag_id": 36, "player": True, "vulnerability": False},
                {"flag_id": 48, "player": False, "vulnerability": False},
            ],
        })
        self.assertFalse(policy._calibration_naked_dump_inflight)

        policy._calibration_observe(naked)

        calibration = policy._character_calibration
        self.assertIsNotNone(calibration)
        self.assertEqual(calibration.intrinsic_tr_flags, frozenset({155, 36}))
        self.assertEqual(calibration.mutation_signature, (2, 9))

    def test_periodic_character_snapshot_is_the_autonomous_trigger(self):
        """The pre-existing periodic status dump (cli DUMP_INTERVAL_SECONDS
        -> CHARACTER_DUMP_MACRO -> type:'character') refreshes the mutation
        signature during normal play with zero extra keys — the
        observation-bounded post-calibration mutation trigger.  Outside the
        capture latch it must never overwrite the calibrated flags."""
        policy = self._scan_complete_policy()

        policy.observe_character_snapshot({
            "mutations": [9, 2, 5],
            "characteristics": [
                {"flag_id": 155, "player": True},
            ],
        })

        self.assertEqual(policy._mutation_signature, (2, 5, 9))
        # Geared characteristics are worn-dependent: never recorded outside
        # the capture-phase naked-dump latch.
        self.assertIsNone(policy._calibration_naked_flags)

    def test_mutation_change_invalidates_the_cached_calibration(self):
        policy = self._scan_complete_policy()
        policy._mutation_signature = (2, 5)
        naked = self._snapshot()
        policy._calibration_phase = "capture"
        policy._calibration_naked_dump_requested = True
        policy._calibration_observe(naked)
        self.assertIsNotNone(policy._character_calibration)

        # Unchanged observation keeps the cache.
        self.assertIsNotNone(policy._validated_character_calibration(naked))

        # A gained mutation reported by the next periodic character snapshot
        # invalidates it.
        policy.observe_character_snapshot({"mutations": [2, 5, 11]})
        self.assertIsNone(policy._validated_character_calibration(naked))
        self.assertIsNone(policy._character_calibration)

    def test_abort_bound_latches_the_visit_blocked(self):
        policy = self._scan_complete_policy()
        policy._mutation_signature = (1,)
        snapshot = self._snapshot()
        for _ in range(policy_module.STORE_STUCK_LIMIT):
            policy._calibration_phase = "capture"
            policy._abort_character_calibration(snapshot, "test")

        self.assertTrue(policy._calibration_blocked_this_visit)
        self.assertIsNone(
            policy._calibration_town_key(
                self._snapshot(equipment=(
                    item(
                        "main_hand", 23, 4, name="long sword", known=True,
                        fully_known=True, is_equipment=True,
                    ),
                ))
            )
        )
        self.assertIsNone(policy._calibration_phase)
