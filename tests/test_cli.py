import json
import inspect
import os
import argparse
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.cli import (
    COMMAND_RESPONSE_GRACE,
    CHEST_MOVE_RESPONSE_SECONDS,
    DECISION_WATCHDOG_SECONDS,
    DUMP_INTERVAL_SECONDS,
    EXTENDED_STUCK_WINDOW,
    LOOK_BARRIER_TIMEOUT_SECONDS,
    EconomyLedger,
    LOOP_WINDOW,
    STATIONARY_EXEMPT_REASONS,
    MULTI_KEY_DELAY_SECONDS,
    MULTIPLIER_COMBAT_LOOP_WINDOW,
    MODAL_RECOVERY_ROUNDS,
    PostingContract,
    POLICY_FINAL_STOP_REASONS,
    REST_STALL_GRACE,
    STORE_ITEM_PROMPT_DELAY_SECONDS,
    STORE_QUANTITY_DIGIT_DELAY_SECONDS,
    STATIONARY_REASONS,
    STALLED_COMMAND_STATE_LIMIT,
    TERMINAL_NUDGE_LIMIT,
    TUNNEL_PROMPT_DELAY_SECONDS,
    TUNNEL_MACRO_TRIGGERS,
    TRAVEL_MACRO_TRIGGERS,
    TRAVEL_PROMPT_DELAY_SECONDS,
    _add_input_delay_arguments,
    _advance_town_blocked_iteration,
    _advance_repeating_reason_iteration,
    _run_follow,
    _advance_stalled_command_count,
    _arm_decision_watchdog,
    _cell_loop_guard_applies,
    _command_response_grace,
    _modal_recovery_action,
    _silent_game_incident,
    _uses_multiplier_combat_grace,
    _delay_after_macro_key,
    _delay_spec_after_macro_key,
    _intentional_action_wait_category,
    _input_delay_values,
    _decision_record,
    _capture_decision_facts,
    _write_decision,
    _town_stall_report,
    _town_stall_report_terminates_named_block,
    _duplicate_snapshot_ready,
    _direction_desynchronized,
    _decode_response_lines,
    _dispatch_response_lines,
    _look_barrier_allows_decision,
    _look_barrier_release,
    _look_barrier_timed_release,
    _chest_movement_response_pending,
    _movement_command_needs_ack,
    _open_game_prompt,
    _posting_effect_signature,
    _fundraising_state,
    _floor_transition_needs_prompt_clear,
    _deduplicate_consecutive,
    _is_looping,
    _newest_snapshot,
    _newest_snapshot_entry,
    _read_last_line,
    _record_atomic_home_page,
    _retained_home_page,
    _run_follow,
    _request_due_dump,
    _rewind_if_truncated,
    _send_new_decision_key,
    _send_stall_recovery_nudge,
    _last_activity_after_read,
    _stall_recovery_key,
    _stall_recovery_action,
    _split_complete_lines,
    _transport_key,
    _write_posted_character,
    _write_posting_contract_incident,
    _freeze_incident_safely,
    _bot_play_macros_ready,
    _build_argument_parser,
    _configure_policy_output_paths,
    _valid_bot_play_macro_pref,
)
from hengbot.policy import (
    ESCAPE_BUDGETED_WAIT_LIMITS,
    HUNT_RANGE,
    HengbotPolicy,
    TOWN_TRAVEL_STALL_LIMIT,
)
from hengbot.equipment_mutation import progress_core
from hengbot.cli import _game_process_alive
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.model import MissingMonraceKnowledgeError, Position, parse_snapshot


class CaptureAndPollDefaultsTest(unittest.TestCase):
    def _args(self, *extra):
        return _build_argument_parser().parse_args(
            ["--state-file", "state.jsonl", "--decision-log", "decisions.jsonl", *extra]
        )

    def _policy(self):
        return SimpleNamespace(
            _home_entry_capture=None,
            _latch_capture_path=None,
            _loadout_report_path=None,
            _character_calibration_path=None,
            _confirmed_loadout_path=None,
        )

    def test_default_argv_disables_captures_and_keeps_confirmed_loadout_path(self):
        policy = self._policy()

        capture = _configure_policy_output_paths(policy, self._args())

        self.assertIsNone(capture)
        self.assertIsNone(policy._home_entry_capture)
        self.assertIsNone(policy._latch_capture_path)
        self.assertEqual(policy._loadout_report_path, Path("loadout-report.jsonl"))
        self.assertEqual(
            policy._character_calibration_path, Path("character-calibration.json")
        )
        self.assertEqual(
            policy._confirmed_loadout_path, Path("confirmed-loadout.json")
        )

    def test_home_entry_flag_enables_only_home_entry_capture(self):
        policy = self._policy()

        capture = _configure_policy_output_paths(
            policy, self._args("--capture-home-entry")
        )

        self.assertIs(capture, policy._home_entry_capture)
        self.assertEqual(capture.path, Path("home-entry-capture.jsonl"))
        self.assertEqual(capture.generations, self._args().recorder_log_generations)
        self.assertIsNone(policy._latch_capture_path)

    def test_latch_onset_flag_enables_only_latch_onset_capture(self):
        policy = self._policy()

        capture = _configure_policy_output_paths(
            policy, self._args("--capture-latch-onset")
        )

        self.assertIsNone(capture)
        self.assertIsNone(policy._home_entry_capture)
        self.assertEqual(policy._latch_capture_path, Path("latch-onset.jsonl"))
        self.assertEqual(
            policy._latch_capture_generations,
            self._args().recorder_log_generations,
        )

    def test_poll_interval_default_is_point_zero_two_seconds(self):
        self.assertEqual(self._args().poll_interval, 0.02)


class AbilitySourceParsingTest(unittest.TestCase):
    def _player(self, abilities):
        data = json.loads(_snap_line(100, 5, 5))
        data["player"]["abilities"] = abilities
        return parse_snapshot(data, {}).player

    def test_per_source_all_false_is_not_granted(self):
        player = self._player({"free_action": {
            "equipment": False, "permanent": False, "temporary": False,
        }})
        self.assertNotIn("free_action", player.abilities)
        self.assertEqual(player.ability_sources["free_action"], frozenset())

    def test_each_true_source_grants_the_ability(self):
        for source in ("equipment", "permanent", "temporary"):
            with self.subTest(source=source):
                player = self._player({"resist_fire": {
                    "equipment": source == "equipment",
                    "permanent": source == "permanent",
                    "temporary": source == "temporary",
                }})
                self.assertEqual(player.abilities, frozenset({"resist_fire"}))
                self.assertEqual(
                    player.ability_sources["resist_fire"], frozenset({source})
                )

    def test_flat_booleans_keep_legacy_meaning_without_source_detail(self):
        player = self._player({"resist_fire": True, "resist_chaos": False})
        self.assertEqual(player.abilities, frozenset({"resist_fire"}))
        self.assertEqual(player.ability_sources, {})


class PostedCharacterRecordTest(unittest.TestCase):
    def test_records_each_posted_character_with_composed_key_and_decision_join(self):
        decision = {
            "sequence": 41,
            "turn": 3024785,
            "reason": "home:atomic-deposit",
            "key": "5da8\r\x1b",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "posted.jsonl"
            for index, character in enumerate(decision["key"]):
                _write_posted_character(
                    path, character, decision["key"], index, decision
                )
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([record["character"] for record in records], list(decision["key"]))
        self.assertEqual([record["character_index"] for record in records], list(range(6)))
        self.assertTrue(all(record["composed_key"] == decision["key"] for record in records))
        self.assertTrue(all(record["decision"] == decision for record in records))


class PersistentInputStateClosureTest(unittest.TestCase):
    @staticmethod
    def _consume_home_viewer(keys):
        """Minimal transcription of the two source input loops."""
        state = "command"
        movements = []
        iterator = iter(keys)
        for key in iterator:
            if state == "command" and key == "~":
                state = "knowledge"
            elif state == "knowledge" and key == "9":
                state = "home-viewer"
            elif state == "home-viewer" and key in {"\x1b", "<", "q"}:
                state = "knowledge"
            elif state == "knowledge" and key == "\x1b":
                state = "command"
            elif state == "command" and key in "12346789":
                movements.append(key)
        return state, movements

    def test_actual_home_scan_bytes_close_viewer_before_another_owner_can_post(self):
        # 13:22:25 posted exactly ``~9`` before the claim owner's first ``9``.
        self.assertEqual(
            self._consume_home_viewer("~9" + "9"),
            ("home-viewer", []),
        )
        closed = _transport_key("~9\x1b\x1b", False)
        self.assertEqual(closed, "~9\x1b\x1b")
        policy = SimpleNamespace(_home_knowledge_scan_inflight=True)
        policy.consume_home_knowledge = lambda _items: True
        closure = []
        _dispatch_response_lines(
            [json.dumps({
                "type": "knowledge",
                "knowledge": {"category": "home", "menu_key": "9", "items": []},
            })],
            policy,
            closure.append,
        )
        self.assertEqual(closure, [])
        self.assertEqual(
            self._consume_home_viewer(closed + "".join(closure) + "9"),
            ("command", ["9"]),
        )

    def test_normal_movement_and_sweep_pickup_sequences_are_byte_identical(self):
        for key in ("9", "ga", "gq", "gA"):
            with self.subTest(key=key):
                self.assertEqual(_transport_key(key, False), key)


class UniversalPostingContractTest(unittest.TestCase):
    """Pins the sender contract extracted from the two 2026-08-10 incidents."""

    @staticmethod
    def snapshot(*, turn=4020825, recalling=False, messages=(), count=1):
        carried = SimpleNamespace(
            slot="b", tval=75, sval=6, name="Potion of Resist Heat",
            count=count, charges=0, inscription="@0", known=True,
            fully_known=True, is_equipment=False,
        )
        return SimpleNamespace(
            turn=turn,
            floor_key=(0, 0, 0),
            messages=messages,
            inventory=[carried],
            equipment=[],
            store=None,
            player=SimpleNamespace(
                position=SimpleNamespace(y=38, x=106), gold=1113,
                recalling=recalling,
            ),
        )

    def test_preserved_double_recall_shape_refuses_until_recalling_changes(self):
        contract = PostingContract()
        first = self.snapshot(turn=4020825, recalling=False)
        posted = []
        decision = {"reason": "town:repetition-depart:recall"}
        sent, posted_line = _send_new_decision_key(
            lambda key, **_kwargs: posted.append(key) or True,
            "recall-first", "rha", None, set(), in_store=False,
            decision=decision, snapshot=first, posting_contract=contract,
        )
        self.assertTrue(sent)

        sent, _ = _send_new_decision_key(
            lambda key, **_kwargs: posted.append(key) or True,
            "recall-second", "rha", posted_line, set(), in_store=False,
            decision=decision,
            snapshot=self.snapshot(turn=4020833, recalling=False),
            posting_contract=contract,
        )
        self.assertFalse(sent)
        self.assertEqual(posted, ["rha"])
        self.assertEqual(
            contract.last_incident["marker"],
            "posting-contract:identical-repost-unobserved",
        )
        self.assertTrue(contract.allow(
            self.snapshot(turn=4020833, recalling=True),
            "rha", "town:repetition-depart:recall",
        ))

    def test_turn_advance_acknowledges_wait_and_mining_repetition(self):
        for owner, key in (("wait", "."), ("fundraise:dig-to-treasure", "T6")):
            with self.subTest(owner=owner):
                contract = PostingContract()
                contract.posted(self.snapshot(turn=10), key, owner)
                self.assertTrue(contract.allow(self.snapshot(turn=11), key, owner))

    def test_unobserved_volley_recovers_through_identity_breaking_probe(self):
        owner = "ranged:fire"
        key = "\x1bfa8"
        contract = PostingContract()
        unchanged = self.snapshot(turn=2963992, count=12)
        unchanged.inventory[0].slot = "a"
        contract.posted(unchanged, key, owner)

        self.assertFalse(contract.allow(unchanged, key, owner))
        self.assertEqual(
            contract.last_incident["marker"],
            "posting-contract:identical-repost-unobserved",
        )

        # The standard A11r2 refusal recovery posts a look/ESC observation
        # barrier under the refusing owner.  A fresh snapshot can then
        # recompose the volley without granting a blanket duplicate exemption.
        probe = "l\x1b"
        contract.posted(unchanged, probe, owner)
        fresh = self.snapshot(turn=2963992, count=12)
        fresh.inventory[0].slot = "a"
        self.assertTrue(contract.allow(fresh, key, owner))

    def test_unchanged_wield_effect_without_prompt_does_not_own_input(self):
        contract = PostingContract()
        posted = self.snapshot(turn=20)
        contract.posted(posted, "wg", "fundraise:wield-digging-tool")

        self.assertTrue(contract.allow(posted, "rc", "fundraise:detect-treasure"))
        self.assertIsNone(contract.last_incident)
        self.assertTrue(
            contract.allow(
                self.snapshot(turn=21), "rc", "fundraise:detect-treasure"
            )
        )

    def test_completed_dual_wield_prompt_history_is_not_an_open_owner(self):
        """04:46 capture: win completed before the prompt entered history."""
        history = (
            "二刀流で戦いますか？[y/n]",
            "Sword (i)を装備した。",
            "Jackal hits you.",
        )
        self.assertIsNone(_open_game_prompt(history))

        contract = PostingContract()
        posted = self.snapshot(turn=2191793)
        contract.posted(posted, "win", "melee:restore-weapon")
        completed = self.snapshot(turn=2191803, messages=history)
        self.assertTrue(contract.allow(completed, "2", "melee"))
        self.assertIsNone(contract.last_incident)

    def test_newest_serialized_prompt_still_owns_input(self):
        prompt = "Sell for $17? [Y/n]"
        self.assertEqual(_open_game_prompt(("older", prompt)), prompt)

    def test_repeated_informational_message_is_not_an_open_prompt(self):
        message = "59個の 鉄弾 (1d3) (+0,+0)がある。 <x44>"
        self.assertIsNone(_open_game_prompt((message,)))

    def test_default_quantity_prompt_is_open_input(self):
        prompt = "いくつですか (1-59): "
        self.assertEqual(_open_game_prompt((prompt,)), prompt)

    def test_ledger_120x_wield_restore_read_order_is_serialized(self):
        """Posted-ledger rows 94685-94733, turns 926205-926303: ta/wgy/wfa."""
        policy = HengbotPolicy()
        contract = PostingContract()
        yeek_before = self.snapshot(turn=926205)
        sword = SimpleNamespace(
            slot="main_hand", tval=23, sval=1, name="Sword", count=1,
            charges=0, inscription="", known=True, fully_known=True,
            is_equipment=True, is_melee_weapon=True, is_digging_tool=False,
        )
        shovel = SimpleNamespace(
            slot="g", tval=20, sval=1, name="Shovel", count=1,
            charges=0, inscription="", known=True, fully_known=True,
            is_equipment=True, is_melee_weapon=False, is_digging_tool=True,
        )
        yeek_before.equipment = [sword]
        yeek_before.inventory = [shovel]
        wield = policy._equipment_takeoff(
            yeek_before, "mining-loadout", "a"
        )
        self.assertEqual(wield, "ta")
        self.assertTrue(policy.confirm_key_posted(wield))

        # Wield prompts are not snapshot messages and therefore cannot establish
        # open input ownership without a recognized serialized prompt.
        owned = self.snapshot(turn=926206)
        contract.posted(owned, "wgy", "fundraise:wield-digging-tool")
        self.assertTrue(contract.allow(owned, "rc", "fundraise:detect-treasure"))
        self.assertIsNone(contract.last_incident)

        occupied = self.snapshot(turn=926222)
        occupied.equipment = [sword]
        occupied.inventory = [shovel]
        policy = HengbotPolicy()
        wield = policy._equipment_wield(
            occupied, "mining-loadout", shovel, "sub_hand"
        )
        self.assertEqual(wield, "wgy")
        self.assertTrue(policy.confirm_key_posted(wield))
        refused = policy._equipment_wield(
            occupied, "combat-loadout", sword, "main_hand"
        )
        self.assertIsNone(refused)
        self.assertEqual(
            policy.last_reason, "posting-contract:equipment-mutation-unobserved"
        )

        final = self.snapshot(turn=926303)
        final.equipment = [
            sword,
            SimpleNamespace(**{**sword.__dict__, "slot": "sub_hand", "name": "Dagger"}),
        ]
        final.inventory = [SimpleNamespace(**{**shovel.__dict__, "slot": "f"})]
        policy = HengbotPolicy()
        self.assertEqual(
            policy._equipment_wield(
                final, "mining-loadout", final.inventory[0], "main_hand"
            ),
            "wfa",
        )

    def test_preserved_sale_prompt_rejects_foreign_escape_owner(self):
        contract = PostingContract()
        sale = self.snapshot(turn=4020002)
        contract.posted(sale, "d0y", "shop:batch-sell")
        prompt = self.snapshot(
            turn=4020002,
            messages=(
                "Sell Potion of Resist Heat (b).",
                "Sell for $17? [Y/n]",
            ),
        )

        sent, _ = _send_new_decision_key(
            lambda _key, **_kwargs: True,
            "sale-prompt", "\x1b", None, set(), in_store=True,
            decision={"reason": "shop:batch-verify-leave"},
            snapshot=prompt, posting_contract=contract,
        )
        self.assertFalse(sent)
        self.assertEqual(
            contract.last_incident["marker"],
            "posting-contract:prompt-owner-mismatch",
        )

    def test_prompt_owner_handoff_clears_before_the_next_decision(self):
        contract = PostingContract()
        raised = self.snapshot(turn=3264100)
        contract.posted(raised, "6", "seek-loot")
        prompt = self.snapshot(
            turn=3264100,
            messages=("トラベルを継続しますか？[y/n]",),
        )
        policy = HengbotPolicy()
        policy.prompt_owner_handoff = "seek-loot"
        self.assertTrue(contract.allow(
            prompt,
            "g",
            "pickup",
            prompt_owner_handoff=policy.prompt_owner_handoff,
        ))
        self.assertIsNone(contract.last_incident)

        next_snapshot_data = json.loads(_snap_line(3264101, 5, 7))
        next_snapshot_data["floor"] = {
            "dungeon_id": 0,
            "level": 0,
            "in_town": True,
        }
        policy.choose_key(parse_snapshot(next_snapshot_data, {}))

        self.assertFalse(contract.allow(
            prompt,
            ".",
            "wait",
            prompt_owner_handoff=policy.prompt_owner_handoff,
        ))
        self.assertEqual(
            contract.last_incident["marker"],
            "posting-contract:prompt-owner-mismatch",
        )

    def test_prompt_owner_handoff_must_claim_actual_owner(self):
        contract = PostingContract()
        raised = self.snapshot(turn=4020002)
        contract.posted(raised, "d0y", "shop:batch-sell")
        prompt = self.snapshot(turn=4020002, messages=("Sell for $17? [Y/n]",))

        self.assertFalse(contract.allow(
            prompt,
            "g",
            "pickup",
            prompt_owner_handoff="seek-loot",
        ))
        self.assertEqual(
            contract.last_incident["marker"],
            "posting-contract:prompt-owner-mismatch",
        )

    def test_departure_blocked_handoff_accepts_its_standing_prompt(self):
        contract = PostingContract()
        raised = self.snapshot(turn=3264322)
        contract.posted(raised, "5", "town:blocked:departure-no-light")
        prompt = self.snapshot(
            turn=3264322,
            messages=("トラベルを継続しますか？[y/n]",),
        )

        self.assertTrue(contract.allow(
            prompt,
            "5",
            "fundraise:departure-blocked",
            prompt_owner_handoff="town:blocked:departure-no-light",
        ))

    def test_both_watchdog_incidents_write_visible_marker_records(self):
        incidents = (
            {"marker": "posting-contract:identical-repost-unobserved"},
            {"marker": "posting-contract:prompt-owner-mismatch"},
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            for incident in incidents:
                _write_posting_contract_incident(path, self.snapshot(), incident)
            records = [json.loads(line) for line in path.read_text(
                encoding="utf-8"
            ).splitlines()]

        self.assertEqual(
            [record["reason"] for record in records],
            [incident["marker"] for incident in incidents],
        )

    def test_freeze_oserror_is_nonfatal_and_choose_key_remains_operational(self):
        policy = SimpleNamespace(
            last_reason="shop:travel",
            choose_key=unittest.mock.Mock(return_value="6"),
        )
        recorder = unittest.mock.Mock()
        recorder.freeze.side_effect = OSError(267, "invalid directory")
        snapshot = self.snapshot()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            with patch("sys.stderr"):
                self.assertIsNone(_freeze_incident_safely(
                    recorder,
                    "posting-contract:identical-repost-unobserved",
                    policy,
                    snapshot,
                    path,
                    ["shop:travel"],
                ))
            self.assertEqual(policy.choose_key(snapshot), "6")
            records = [json.loads(line) for line in path.read_text(
                encoding="utf-8"
            ).splitlines()]
        self.assertEqual(records[-1]["reason"], "instrument:incident-freeze-failed")


class DecisionWatchdogTest(unittest.TestCase):
    @patch("hengbot.cli.faulthandler.dump_traceback_later")
    @patch("hengbot.cli.faulthandler.cancel_dump_traceback_later")
    def test_rearms_for_each_decision_iteration(self, cancel, dump):
        _arm_decision_watchdog()
        _arm_decision_watchdog()

        self.assertEqual(cancel.call_count, 2)
        self.assertEqual(dump.call_count, 2)
        for call in dump.call_args_list:
            self.assertEqual(call.args, (DECISION_WATCHDOG_SECONDS,))
            self.assertGreater(DECISION_WATCHDOG_SECONDS, 60)
            self.assertTrue(call.kwargs["repeat"])
            self.assertIsNotNone(call.kwargs["file"])


class DecisionTimingTest(unittest.TestCase):
    def test_home_page_retention_has_only_structural_clear_boundaries(self):
        home_data = json.loads(_snap_line(10, 5, 5))
        home_data["store"] = {
            "store_type": 7, "stock_num": 1, "page_top": 0, "page_size": 12,
            "items": [{"letter": "a", "name": "Pick", "count": 1}],
        }
        home = parse_snapshot(home_data, {})
        retained = _retained_home_page(None, home, floor_changed=False)
        town = parse_snapshot(json.loads(_snap_line(11, 5, 5)), {})

        self.assertIs(_retained_home_page(
            retained, town, floor_changed=False
        ), retained)
        self.assertIsNone(_retained_home_page(
            retained, town, floor_changed=True
        ))

        shop_data = json.loads(_snap_line(12, 5, 5))
        shop_data["store"] = {
            "store_type": 1, "stock_num": 0, "page_top": 0,
            "page_size": 12, "items": [],
        }
        shop = parse_snapshot(shop_data, {})
        self.assertIsNone(_retained_home_page(
            retained, shop, floor_changed=False
        ))

    def test_follow_records_batch_spans_posted_key_and_inflight_knowledge(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            batch_path = root / "read-batches.jsonl"
            knowledge_path = root / "knowledge-responses.jsonl"
            state_path = root / "state.jsonl"
            decision_path = root / "decisions.jsonl"
            initial_line = _snap_line(1, 5, 5)
            decision_line = _snap_line(2, 5, 5)
            stop_line = _snap_line(3, 5, 5)
            knowledge_items = [
                {"slot": "a", "name": "Shovel", "count": 1, "tval": 20, "sval": 1},
                {"slot": "b", "name": "Pick", "count": 1, "tval": 20, "sval": 4},
                {"slot": "c", "name": "Mattock", "count": 1, "tval": 20, "sval": 7},
            ]
            knowledge_line = json.dumps({
                "type": "knowledge", "turn": 2,
                "knowledge": {"category": "home", "menu_key": "9", "items": knowledge_items},
            }) + "\n"
            state_path.write_text(initial_line, encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path),
                "--decision-log", str(decision_path),
                "--poll-interval", "0.001",
            ])
            args.wait_telemetry = unittest.mock.Mock()
            policy = HengbotPolicy()

            def choose(snapshot):
                if snapshot.turn == 3:
                    policy.last_reason = "equipment-transaction:restore-blocked-terminal"
                    return ""
                policy.last_reason = "home:request-knowledge-scan"
                policy._home_knowledge_scan_requested = True
                policy._home_page_size = 2
                policy._decision_sequence += 1
                return "~9\x1b\x1b"

            policy.choose_key = unittest.mock.Mock(side_effect=choose)
            sent = []

            def append_snapshots():
                time.sleep(0.5)
                with state_path.open("a", encoding="utf-8") as stream:
                    stream.write(decision_line)
                    stream.flush()
                    # Keep the decision record in a distinct follow poll on
                    # Windows hosts whose scheduler coalesces 50 ms sleeps.
                    time.sleep(0.5)
                    stream.write(knowledge_line)
                    stream.flush()
                    time.sleep(0.5)
                    stream.write(stop_line)
                    stream.flush()

            writer = threading.Thread(target=append_snapshots)
            writer.start()
            try:
                with (
                    patch("hengbot.cli.READ_BATCH_LEDGER_PATH", batch_path),
                    patch("hengbot.cli.KNOWLEDGE_RESPONSE_LEDGER_PATH", knowledge_path),
                ):
                    result = _run_follow(
                        args, policy,
                        lambda key, **_kwargs: sent.append(key) or True,
                        {},
                    )
            finally:
                writer.join()

            rows = [
                json.loads(line)
                for line in decision_path.read_text(encoding="utf-8").splitlines()
            ]
            row = next(record for record in rows if record["reason"] == "home:request-knowledge-scan")
            timing = row["timing"]
            phase_keys = {
                "record_snapshot_lines_ms", "decode_ms", "parse_snapshot_ms",
                "choose_key_ms", "send_ms",
            }
            gap_keys = {"read_ms", "batch_bytes", "poll_wait_ms"}

            self.assertEqual(result, 0)
            self.assertEqual(sent, ["~9\x1b\x1b"])
            self.assertTrue(phase_keys.issubset(timing))
            self.assertTrue(gap_keys.issubset(timing))
            self.assertTrue(all(timing[name] >= 0 for name in phase_keys))
            self.assertTrue(all(timing[name] >= 0 for name in gap_keys))
            self.assertLessEqual(sum(timing[name] for name in phase_keys), timing["total_ms"])
            self.assertEqual(timing["batch_bytes"], len(decision_line))
            self.assertEqual(timing["snapshot_bytes"], len(decision_line.encode("utf-8")))
            self.assertEqual(
                timing["nearby_grids"],
                len(json.loads(decision_line).get("nearby_grids", ())),
            )
            batch_rows = [
                json.loads(line) for line in batch_path.read_text().splitlines()
            ]
            knowledge_rows = [
                json.loads(line) for line in knowledge_path.read_text().splitlines()
            ]
            self.assertEqual([item["line_count"] for item in batch_rows], [1, 1, 1])
            self.assertEqual(batch_rows[0]["line_turns"], [2])
            self.assertEqual(batch_rows[0]["posted_key"], "~9\x1b\x1b")
            self.assertTrue(batch_rows[0]["decided"])
            self.assertEqual(batch_rows[1]["line_types"], ["knowledge"])
            self.assertFalse(batch_rows[1]["decided"])
            self.assertTrue(knowledge_rows[0]["accepted"])
            self.assertTrue(knowledge_rows[0]["inflight_at_arrival"])
            self.assertEqual(
                knowledge_rows[0]["items"],
                [
                    {"letter": "a", "name": "Shovel", "page": 0, "index": 0, "composer_letter": "a"},
                    {"letter": "b", "name": "Pick", "page": 0, "index": 1, "composer_letter": "b"},
                    {"letter": "c", "name": "Mattock", "page": 1, "index": 2, "composer_letter": "a"},
                ],
            )
            self.assertEqual(knowledge_path.parent, root)

    def test_run_follow_passes_captured_facts_to_decision_writer(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.jsonl"
            decision_path = root / "decisions.jsonl"
            state_path.write_text(_snap_line(1, 5, 5), encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path),
                "--decision-log", str(decision_path),
                "--poll-interval", "0.001",
            ])
            args.wait_telemetry = unittest.mock.Mock()
            policy = HengbotPolicy()

            def choose(snapshot):
                policy.last_reason = "equipment-transaction:restore-blocked-terminal"
                return ""

            policy.choose_key = unittest.mock.Mock(side_effect=choose)
            writer_active = False
            writer_telemetry_calls = []
            real_write_decision = _write_decision

            def observe_writer(*write_args, **write_kwargs):
                nonlocal writer_active
                writer_active = True
                try:
                    return real_write_decision(*write_args, **write_kwargs)
                finally:
                    writer_active = False

            def telemetry(name, value):
                def observe(*_args, **_kwargs):
                    if writer_active:
                        writer_telemetry_calls.append(name)
                    return value
                return observe

            telemetry_patches = (
                patch.object(policy, "procurement_requirements", telemetry("procurement_requirements", [])),
                patch.object(policy, "threat_prediction", telemetry("threat_prediction", {})),
                patch.object(policy, "equipment_optimization_state", telemetry("equipment_optimization_state", {})),
                patch.object(policy, "loot_state", telemetry("loot_state", {})),
                patch.object(policy, "departure_block_state", telemetry("departure_block_state", {})),
                patch.object(policy, "cross_town_shopping_state", telemetry("cross_town_shopping_state", {})),
            )

            def append_snapshot():
                # Let _run_follow seed the recorder and seek the state stream
                # before making the one decision snapshot visible.
                time.sleep(0.5)
                with state_path.open("a", encoding="utf-8") as stream:
                    stream.write(_snap_line(2, 5, 5))
                    stream.flush()

            producer = threading.Thread(target=append_snapshot)
            producer.start()
            for mocked in telemetry_patches:
                mocked.start()
            try:
                with (
                    patch("hengbot.cli._write_decision", side_effect=observe_writer),
                    patch("hengbot.cli._append_capture_ledger"),
                    patch("hengbot.cli._freeze_incident_safely"),
                ):
                    result = _run_follow(args, policy, lambda *_a, **_k: True, {})
            finally:
                for mocked in reversed(telemetry_patches):
                    mocked.stop()
                producer.join()

            self.assertEqual(result, 0)
            self.assertTrue(decision_path.is_file())
            self.assertEqual(writer_telemetry_calls, [])

    def test_run_follow_recaptures_facts_after_posting_refusal(self):
        class RefuseFirstPosting:
            def __init__(self):
                self.last_incident = None
                self.calls = 0

            def allow(self, _snapshot, key, owner):
                self.calls += 1
                if self.calls == 1:
                    self.last_incident = {
                        "marker": "posting-contract:identical-repost-unobserved",
                        "owner": owner,
                        "key": key,
                    }
                    return False
                self.last_incident = None
                return True

            def posted(self, *_args):
                pass

        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.jsonl"
            decision_path = root / "decisions.jsonl"
            state_path.write_text(_snap_line(1, 5, 5), encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path),
                "--decision-log", str(decision_path),
                "--poll-interval", "0.001",
            ])
            args.wait_telemetry = unittest.mock.Mock()
            policy = HengbotPolicy()
            second_decided = threading.Event()
            choices = iter((
                ("first-decision", "5"),
                ("second-decision", "6"),
                ("equipment-transaction:restore-blocked-terminal", ""),
            ))

            def choose(_snapshot):
                policy.last_reason, key = next(choices)
                if policy.last_reason == "second-decision":
                    second_decided.set()
                return key

            policy.choose_key = unittest.mock.Mock(side_effect=choose)
            real_capture = _capture_decision_facts
            real_write_decision = _write_decision
            written_fact_reasons = []

            def capture(snapshot, active_policy):
                facts = real_capture(snapshot, active_policy)
                facts["captured_reason"] = active_policy.last_reason
                return facts

            def write(*write_args, **write_kwargs):
                written_fact_reasons.append(
                    write_kwargs["decision_facts"]["captured_reason"]
                )
                return real_write_decision(*write_args, **write_kwargs)

            def append_snapshot():
                time.sleep(0.5)
                with state_path.open("a", encoding="utf-8") as stream:
                    stream.write(_snap_line(2, 5, 5))
                    stream.flush()
                    self.assertTrue(second_decided.wait(5))
                    stream.write(_snap_line(3, 5, 6))
                    stream.flush()

            producer = threading.Thread(target=append_snapshot)
            producer.start()
            try:
                with (
                    # TEST_FAKERY_LINT_ALLOW: collaborator-wall: capture and persistence are process-bound collaborators; the real follow/retry loop and posting contract remain under test
                    patch("hengbot.cli._capture_decision_facts", side_effect=capture),
                    patch("hengbot.cli._write_decision", side_effect=write),
                    patch("hengbot.cli._append_capture_ledger"),
                    patch("hengbot.cli._freeze_incident_safely"),
                ):
                    result = _run_follow(
                        args, policy, lambda *_a, **_k: True, {},
                        posting_contract=RefuseFirstPosting(),
                    )
            finally:
                producer.join()

            self.assertEqual(result, 0)
            self.assertEqual(
                written_fact_reasons,
                [
                    "first-decision", "second-decision",
                    "equipment-transaction:restore-blocked-terminal",
                ],
            )

    def test_follow_records_atomic_withdraw_observed_home_page(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.jsonl"
            decision_path = root / "decisions.jsonl"
            ledger_path = root / "capture-ledger" / "knowledge-responses.jsonl"
            page = json.loads(_snap_line(2, 5, 5))
            page["store"] = {
                "store_type": 7, "stock_num": 14, "page_top": 12, "page_size": 12,
                "items": [
                    {"letter": "a", "name": "Shovel", "count": 1, "tval": 20, "sval": 1},
                    {"letter": "b", "name": "Pick", "count": 1, "tval": 20, "sval": 4},
                ],
            }
            initial_page = dict(page)
            initial_page["turn"] = 1
            initial = json.dumps(initial_page) + "\n"
            page_line = _snap_line(2, 5, 5)
            decision_line = _snap_line(3, 5, 5)
            stop_line = _snap_line(4, 5, 5)
            state_path.write_text(initial, encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path), "--decision-log", str(decision_path),
                "--poll-interval", "0.001",
            ])
            args.wait_telemetry = unittest.mock.Mock()
            policy = HengbotPolicy()
            turn_decided = {2: threading.Event(), 3: threading.Event()}

            def choose(snapshot):
                if snapshot.turn == 4:
                    policy.last_reason = "equipment-transaction:restore-blocked-terminal"
                    return ""
                policy.last_reason = "home:atomic-withdraw-target-unobserved"
                turn_decided[snapshot.turn].set()
                return ""

            policy.choose_key = unittest.mock.Mock(side_effect=choose)

            def append_snapshots():
                time.sleep(0.5)
                with state_path.open("a", encoding="utf-8") as stream:
                    stream.write(page_line)
                    stream.flush()
                    self.assertTrue(turn_decided[2].wait(5))
                    stream.write(decision_line)
                    stream.flush()
                    self.assertTrue(turn_decided[3].wait(5))
                    stream.write(stop_line)
                    stream.flush()

            writer = threading.Thread(target=append_snapshots)
            writer.start()
            try:
                with patch("hengbot.cli.KNOWLEDGE_RESPONSE_LEDGER_PATH", ledger_path):
                    self.assertEqual(_run_follow(args, policy, lambda *_a, **_k: True, {}), 0)
            finally:
                writer.join()

            rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all(row["turn"] in {2, 3} for row in rows))
            self.assertTrue(all(row["observed_turn"] == 1 for row in rows))
            self.assertTrue(all(row["page_top"] == 12 for row in rows))
            self.assertTrue(all(row["page_size"] == 12 for row in rows))
            self.assertTrue(all(
                row["items"] == [
                    {
                        "letter": "a", "name": "Shovel", "page": 1,
                        "index": 12, "composer_letter": "a",
                    },
                    {
                        "letter": "b", "name": "Pick", "page": 1,
                        "index": 13, "composer_letter": "b",
                    },
                ]
                for row in rows
            ))

    def test_decision_row_shape_is_byte_identical_when_capture_writer_runs(self):
        snapshot = parse_snapshot(json.loads(_snap_line(7, 5, 6)), {})
        timing = {
            "read_ms": 0.01,
            "batch_bytes": 456,
            "poll_wait_ms": 1.5,
            "record_snapshot_lines_ms": 0.1,
            "decode_ms": 0.2,
            "parse_snapshot_ms": 0.3,
            "choose_key_ms": 0.4,
            "send_ms": 0.5,
            "total_ms": 2.0,
            "snapshot_bytes": 123,
            "nearby_grids": 4,
        }

        with patch("hengbot.cli.time.strftime", return_value="fixed-decision-time"):
            original = _decision_record(snapshot, "6", "timing:test")
            before = _decision_record(
                snapshot, "6", "timing:test", timing=timing
            )
            with TemporaryDirectory() as directory:
                capture = Path(directory) / "capture-ledger" / "knowledge-responses.jsonl"
                policy = HengbotPolicy()
                policy.last_reason = "home:atomic-withdraw-target-unobserved"
                before_bytes = json.dumps(before, ensure_ascii=False, separators=(",", ":")).encode()
                _record_atomic_home_page(policy, snapshot, path=capture)
                after = _decision_record(snapshot, "6", "timing:test", timing=timing)
                after_bytes = json.dumps(after, ensure_ascii=False, separators=(",", ":")).encode()
                self.assertTrue(capture.read_bytes())
                self.assertEqual(before_bytes, after_bytes)

        self.assertEqual(before, after)
        self.assertEqual({key: value for key, value in before.items() if key != "timing"}, original)

    def test_follow_accounts_for_idle_gap_between_two_decision_batches(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.jsonl"
            decision_path = root / "decisions.jsonl"
            initial_line = _snap_line(1, 5, 5)
            first_line = _snap_line(2, 5, 5)
            second_line = _snap_line(3, 5, 6)
            state_path.write_text(initial_line, encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path),
                "--decision-log", str(decision_path),
                "--poll-interval", "0.001",
            ])
            args.wait_telemetry = unittest.mock.Mock()
            policy = HengbotPolicy()
            posted_at = []

            def choose(snapshot):
                policy.last_reason = f"timing:batch-{snapshot.turn}"
                return "\x1b"

            def send(key, **_kwargs):
                posted_at.append(time.perf_counter())
                return True

            def append_snapshots():
                time.sleep(0.5)
                with state_path.open("a", encoding="utf-8") as stream:
                    stream.write(first_line)
                    stream.flush()
                    time.sleep(0.1)
                    stream.write(second_line)
                    stream.flush()

            policy.choose_key = unittest.mock.Mock(side_effect=choose)
            writer = threading.Thread(target=append_snapshots)
            writer.start()
            try:
                with (
                    patch("hengbot.cli._append_capture_ledger"),
                    patch("hengbot.cli._cell_loop_guard_applies", return_value=True),
                    patch(
                        "hengbot.cli._is_looping",
                        side_effect=lambda *_args, **_kwargs: len(posted_at) >= 2,
                    ),
                ):
                    result = _run_follow(args, policy, send, {})
            finally:
                writer.join()

            rows = {
                row["reason"]: row
                for row in map(
                    json.loads,
                    decision_path.read_text(encoding="utf-8").splitlines(),
                )
            }
            second_timing = rows["timing:batch-3"]["timing"]
            accounted_ms = sum(
                second_timing[name]
                for name in ("poll_wait_ms", "read_ms", "total_ms")
            )
            wall_interval_ms = (posted_at[1] - posted_at[0]) * 1000

            self.assertEqual(result, 0)
            self.assertEqual(len(posted_at), 2)
            self.assertGreaterEqual(second_timing["poll_wait_ms"], 25.0)
            self.assertTrue(all(
                second_timing[name] >= 0
                for name in ("poll_wait_ms", "read_ms", "batch_bytes")
            ))
            self.assertEqual(second_timing["batch_bytes"], len(second_line))
            self.assertLess(abs(wall_interval_ms - accounted_ms), 5.0)


class PeriodicDumpTimerTest(unittest.TestCase):
    def test_elapsed_timer_latches_once_and_moves_deadline(self):
        policy = unittest.mock.Mock()

        deadline = _request_due_dump(policy, 100.0, 99.0)

        policy.request_character_dump.assert_called_once_with()
        policy.request_game_save.assert_called_once_with()
        self.assertEqual(deadline, 100.0 + DUMP_INTERVAL_SECONDS)
        self.assertEqual(_request_due_dump(policy, 101.0, deadline), deadline)
        policy.request_character_dump.assert_called_once_with()
        policy.request_game_save.assert_called_once_with()


class WaitClassificationTest(unittest.TestCase):
    def test_q34_convergence_failures_are_visible_final_stops(self):
        self.assertIn(
            "quest:blocked:q34-throw-point-unreachable",
            POLICY_FINAL_STOP_REASONS,
        )
        self.assertIn(
            "quest:blocked:q34-recovery-no-progress",
            POLICY_FINAL_STOP_REASONS,
        )

    def test_q34_final_stops_have_quest_specific_operator_messages(self):
        source = inspect.getsource(_run_follow)
        # TEST_FAKERY_LINT_ALLOW: source-text-only-assertions: focused CLI wiring test asserts the two operator-facing message tags emitted by the follow loop
        self.assertEqual(source.count("<q34-recovery-no-progress>"), 1)
        self.assertEqual(source.count("<q34-throw-point-unreachable>"), 1)

    def test_cli_override_changes_generic_delay_without_changing_default(self):
        parser = argparse.ArgumentParser()
        _add_input_delay_arguments(parser)

        defaults = _input_delay_values(parser.parse_args([]))
        overridden = _input_delay_values(
            parser.parse_args(["--input-key-delay", "0"])
        )

        self.assertEqual(_delay_after_macro_key("qa", 0), 0.02)
        self.assertEqual(
            _delay_after_macro_key("qa", 0, input_delays=defaults),
            0.02,
        )
        self.assertEqual(
            _delay_after_macro_key("qa", 0, input_delays=overridden),
            0.0,
        )

    def test_macro_delays_have_stable_categories(self):
        self.assertEqual(
            _delay_spec_after_macro_key("T3", 0),
            (TUNNEL_PROMPT_DELAY_SECONDS, "input:tunnel-prompt"),
        )
        travel = next(iter(TRAVEL_MACRO_TRIGGERS))
        self.assertEqual(
            _delay_spec_after_macro_key(travel, 1),
            (TRAVEL_PROMPT_DELAY_SECONDS, "input:travel-prompt"),
        )
        self.assertEqual(
            _delay_spec_after_macro_key("fa6", 0),
            (STORE_ITEM_PROMPT_DELAY_SECONDS, "input:item-prompt"),
        )
        self.assertEqual(
            _delay_spec_after_macro_key("qa", 0),
            (MULTI_KEY_DELAY_SECONDS, "input:generic-prompt"),
        )

    def test_only_deliberate_stationary_actions_are_timed(self):
        self.assertEqual(
            _intentional_action_wait_category("5", "town:wait-recall"),
            "action:town:wait-recall",
        )
        self.assertEqual(
            _intentional_action_wait_category("R&.", "town:recover"),
            "action:town:recover",
        )
        self.assertEqual(
            _intentional_action_wait_category("5", "quest-strategy:hold"),
            "action:quest-strategy:hold",
        )
        self.assertIsNone(_intentional_action_wait_category("6", "explore"))

def _snap_line(turn, y, x):
    return (
        json.dumps(
            {
                "turn": turn,
                "player": {"y": y, "x": x, "hp": 10, "max_hp": 10},
                "floor": {"dungeon_id": 0, "level": 1},
            }
        )
        + "\n"
    )


class EconomyLedgerTest(unittest.TestCase):
    @staticmethod
    def _snapshot(turn, gold):
        data = json.loads(_snap_line(turn, 5, 7))
        data["player"]["gold"] = gold
        return parse_snapshot(data, {})

    def test_records_confirmed_expense_and_income_with_causes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bot-economy.jsonl"
            ledger = EconomyLedger(path)
            before = self._snapshot(100, 1000)
            ledger.prime(before)

            self.assertIsNone(
                ledger.observe(before, "pa\r", "shop:buy-recall")
            )
            expense = ledger.observe(
                self._snapshot(101, 750), "\x1b", "shop:leave"
            )
            ledger.observe(
                self._snapshot(101, 750), "g", "fundraise:pickup"
            )
            income = ledger.observe(
                self._snapshot(102, 825), "6", "fundraise:seek-loot"
            )

            self.assertEqual(
                expense,
                {
                    **expense,
                    "kind": "expense",
                    "amount": 250,
                    "delta": -250,
                    "gold_before": 1000,
                    "gold_after": 750,
                    "cause_reason": "shop:buy-recall",
                    "cause_key": "pa\r",
                },
            )
            self.assertEqual(income["kind"], "income")
            self.assertEqual(income["amount"], 75)
            self.assertEqual(income["cause_reason"], "fundraise:pickup")
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records, [expense, income])


class NewestSnapshotTest(unittest.TestCase):
    def test_parses_detected_monsters_as_a_separate_perception_channel(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["detected_monsters"] = [
            {
                "index": 7,
                "y": 5,
                "x": 9,
                "distance": 6,
                "race_id": 44,
                "name": "detected breeder",
                "health": "unhurt",
                "friendly": False,
                "pet": False,
            }
        ]
        knowledge = {
            44: MonraceKnowledge(
                20, 110, False, False,
                max_melee_damage=3,
                can_multiply=True,
            )
        }

        snapshot = parse_snapshot(data, knowledge)

        self.assertEqual(snapshot.visible_monsters, [])
        self.assertEqual(len(snapshot.detected_monsters), 1)
        monster = snapshot.detected_monsters[0]
        self.assertEqual(monster.position, Position(5, 9))
        self.assertEqual(monster.distance, 6)
        self.assertEqual(monster.race_id, 44)
        self.assertEqual(monster.perception, "detected")

        del data["detected_monsters"]
        self.assertEqual(parse_snapshot(data, knowledge).detected_monsters, [])

    def test_parses_messages_and_defaults_missing_field_to_empty(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["messages"] = ["Your ring drains HP from you!", "second"]

        self.assertEqual(
            parse_snapshot(data, {}).messages,
            ("Your ring drains HP from you!", "second"),
        )
        del data["messages"]
        self.assertEqual(parse_snapshot(data, {}).messages, ())

    def test_parses_grid_mark_flag_and_defaults_older_snapshots_to_unmarked(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {"y": 5, "x": 6, "known": True, "flags": {"mark": True}},
            {"y": 5, "x": 7, "known": True, "flags": {"mark": False}},
            {"y": 5, "x": 8, "known": True},
        ]

        snapshot = parse_snapshot(data, {})

        self.assertTrue(snapshot.grids[Position(5, 6)].marked)
        self.assertFalse(snapshot.grids[Position(5, 7)].marked)
        self.assertFalse(snapshot.grids[Position(5, 8)].marked)

    def test_parses_equipment_optimizer_player_inputs(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["player"].update(
            {
                "class_id": 0,
                "race_id": 12,
                "personality_id": 3,
                "stats": {
                    name: {
                        "cur": 10 + index,
                        "max": 11 + index,
                        "use": 12 + index,
                        "index": 13 + index,
                    }
                    for index, name in enumerate(("str", "int", "wis", "dex", "con", "chr"))
                },
                "skills": {
                    "melee": 70,
                    "shooting": 65,
                    "saving": 40,
                    "device": 31,
                    "stealth": 2,
                    "two_weapon": 123,
                    "shield": 456,
                },
            }
        )
        data["equipment"] = [
            {
                "slot": "main_hand",
                "name": "Sword",
                "count": 1,
                "tval": 23,
                "sval": 1,
                "aware": True,
                "known": True,
                "fully_known": True,
                "is_equipment": True,
                "weight": 120,
                "weapon_proficiency": 3456,
            }
        ]
        data["store"] = {
            "store_type": 7,
            "items": [
                {
                    "letter": "a",
                    "name": "Light Crossbow",
                    "count": 1,
                    "tval": 19,
                    "sval": 23,
                    "aware": True,
                    "known": True,
                    "fully_known": True,
                    "is_equipment": True,
                    "weapon_proficiency": 2345,
                }
            ],
        }
        snapshot = parse_snapshot(data, {})
        self.assertEqual(snapshot.player.race_id, 12)
        self.assertEqual(snapshot.player.personality_id, 3)
        self.assertEqual(snapshot.player.stat_cur, (10, 11, 12, 13, 14, 15))
        self.assertEqual(snapshot.player.stat_index, (13, 14, 15, 16, 17, 18))
        self.assertEqual(snapshot.player.two_weapon_skill, 123)
        self.assertEqual(snapshot.player.shield_skill, 456)
        self.assertEqual(snapshot.player.shooting_skill, 65)
        self.assertEqual(snapshot.equipment[0].weight, 120)
        self.assertEqual(snapshot.equipment[0].weapon_proficiency, 3456)
        self.assertEqual(snapshot.store.items[0].weapon_proficiency, 2345)

    def test_returns_only_the_latest_of_a_batch(self):
        # A fast monster can emit several prompts before we read; we must act on
        # the newest board, not replay the stale ones (which desyncs our keys).
        batch = [_snap_line(100, 5, 5), _snap_line(110, 5, 6), _snap_line(120, 6, 6)]
        snap = _newest_snapshot(batch)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.turn, 120)
        self.assertEqual((snap.player.position.y, snap.player.position.x), (6, 6))

    def test_skips_a_malformed_trailing_line(self):
        batch = [_snap_line(100, 5, 5), '{"turn": 110, "player":\n']
        snap = _newest_snapshot(batch)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.turn, 100)

    def test_returns_none_for_empty_or_all_blank(self):
        self.assertIsNone(_newest_snapshot([]))
        self.assertIsNone(_newest_snapshot(["\n", "   \n"]))

    def test_one_read_decodes_each_line_once_for_all_consumers(self):
        lines = [
            _snap_line(100, 5, 5),
            json.dumps({"type": "knowledge", "knowledge": {}}) + "\n",
            json.dumps({"type": "look", "look": {}}) + "\n",
            json.dumps({"type": "character", "character": {}}) + "\n",
            _snap_line(120, 6, 6),
        ]
        policy = SimpleNamespace(
            _home_knowledge_scan_inflight=False,
            _look_probe_inflight=False,
            observe_character_snapshot=lambda _character: None,
        )
        real_loads = json.loads
        with patch("hengbot.cli.json.loads", wraps=real_loads) as loads:
            decoded = _decode_response_lines(lines)
            _dispatch_response_lines(
                lines, policy, lambda _key: None, decoded_lines=decoded
            )
            eligible, _ = _look_barrier_release(lines, decoded_lines=decoded)
            eligible_decoded = decoded[-len(eligible) :] if eligible else []
            _newest_snapshot_entry(
                eligible, {}, decoded_lines=eligible_decoded
            )

        self.assertEqual(loads.call_count, len(lines))

    def test_mixed_response_batch_preserves_dispatch_and_newest_line(self):
        player_turn = _snap_line(120, 6, 6)
        lines = [
            _snap_line(100, 5, 5),
            player_turn,
            json.dumps({"type": "knowledge", "knowledge": {}}) + "\n",
            json.dumps({"type": "look", "look": {"cursor": [1, 2]}}) + "\n",
            json.dumps({"type": "character", "character": {"mutations": [7]}}) + "\n",
        ]
        observed = []
        policy = SimpleNamespace(
            _home_knowledge_scan_inflight=False,
            _look_probe_inflight=True,
            consume_look=lambda data: observed.append(("look", data)),
            observe_character_snapshot=lambda data: observed.append(
                ("character", data)
            ),
        )
        sent = []
        decoded = _decode_response_lines(lines)

        consumed = _dispatch_response_lines(
            lines, policy, sent.append, decoded_lines=decoded
        )
        entry = _newest_snapshot_entry(lines, {}, decoded_lines=decoded)

        self.assertEqual(consumed, 3)
        self.assertEqual(sent, [])
        self.assertEqual([kind for kind, _ in observed], ["look", "character"])
        self.assertEqual(entry[0].turn, 120)
        self.assertEqual(entry[1].encode("utf-8"), player_turn.encode("utf-8"))

    def test_parses_visible_grid_lighting_for_quest_area_setup(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "monster_index": 0,
                "terrain": {"move": True},
                "flags": {"lite": True},
            }
        ]

        snapshot = parse_snapshot(data, {})

        self.assertTrue(snapshot.grid_at(Position(5, 6)).lit)

    def test_derives_summoning_from_race_id_not_snapshot_capabilities(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "monster_index": 1,
                "terrain": {"move": True},
            },
            {
                "y": 5,
                "x": 7,
                "known": True,
                "monster_index": 2,
                "terrain": {"move": True},
            },
        ]
        data["visible_monsters"] = [
            {
                "index": 1,
                "race_id": 124,
                "can_summon": False,
                "hp": 1,
                "max_hp": 1,
                "speed": 999,
                "health": "badly_wounded",
                "confused": True,
            },
            {
                "index": 2,
                "race_id": 125,
                "can_summon": True,
            },
        ]
        knowledge = {
            124: MonraceKnowledge(100, 115, True, False),
            125: MonraceKnowledge(20, 110, False, False),
        }
        snapshot = _newest_snapshot(
            [json.dumps(data) + "\n"], knowledge
        )
        self.assertTrue(snapshot.visible_monsters[0].can_summon)
        self.assertFalse(snapshot.visible_monsters[1].can_summon)
        self.assertEqual(snapshot.visible_monsters[0].hp, 24)
        self.assertEqual(snapshot.visible_monsters[0].max_hp, 100)
        self.assertEqual(snapshot.visible_monsters[0].speed, 115)
        self.assertTrue(snapshot.visible_monsters[0].confused)
        self.assertEqual(snapshot.visible_monsters[0].position.x, 6)

    def test_rejects_a_visible_monster_missing_from_static_knowledge(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "monster_index": 1,
                "terrain": {"move": True},
            }
        ]
        data["visible_monsters"] = [{"index": 1, "race_id": 9999}]
        with self.assertRaisesRegex(MissingMonraceKnowledgeError, "race_id=9999"):
            parse_snapshot(data, {})

        with self.assertRaises(MissingMonraceKnowledgeError):
            _newest_snapshot([json.dumps(data) + "\n"], {})

    def test_hallucinated_monster_is_a_positional_threat_without_identity(self):
        # While hallucinating, the emitter reports the tile a monster occupies but
        # redacts its identity/health. The bot must still register a hostile at
        # that position — and must NOT raise for the absent race_id.
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "monster_index": 1,
                "terrain": {"move": True},
            }
        ]
        data["visible_monsters"] = [
            {"index": 1, "hallucinated": True, "friendly": False, "pet": False}
        ]
        snapshot = parse_snapshot(data, {})  # empty knowledge must not raise
        monster = snapshot.visible_monsters[0]
        self.assertTrue(monster.hostile)
        self.assertEqual((monster.position.y, monster.position.x), (5, 6))
        self.assertEqual(monster.race_id, 0)
        self.assertFalse(monster.can_summon)

    def test_hallucinated_pet_is_not_treated_as_hostile(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {"y": 5, "x": 6, "known": True, "monster_index": 1, "terrain": {"move": True}}
        ]
        data["visible_monsters"] = [
            {"index": 1, "hallucinated": True, "friendly": True, "pet": True}
        ]
        monster = parse_snapshot(data, {}).visible_monsters[0]
        self.assertFalse(monster.hostile)

    def test_parses_redacted_unidentified_item_details(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["inventory"] = [
            {
                "slot": "h",
                "name": "an unknown scroll",
                "count": 1,
                "tval": 70,
                "aware": False,
                "known": False,
                "pseudo_feeling": "average",
                "inscription": "keep HEAVY_CURSE",
            }
        ]

        item = parse_snapshot(data, {}).inventory[0]

        self.assertEqual(item.sval, -1)
        self.assertEqual(item.charges, 0)
        self.assertEqual(item.fuel, 0)
        self.assertFalse(item.aware)
        self.assertFalse(item.known)
        self.assertFalse(item.fully_known)
        self.assertEqual(item.pseudo_feeling, "average")
        self.assertEqual(item.inscription, "keep HEAVY_CURSE")

    def test_parses_the_in_town_flag(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["floor"]["level"] = 0
        data["floor"]["in_town"] = False  # on the open wilderness surface
        snap = parse_snapshot(data, {})
        self.assertFalse(snap.in_town)
        self.assertTrue(snap.on_open_wilderness)
        data["floor"]["in_town"] = True
        town = parse_snapshot(data, {})
        self.assertTrue(town.in_town)
        self.assertFalse(town.on_open_wilderness)

    def test_parses_visible_floor_object_classes(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "object_count": 2,
                "object_tvals": [65, 55],
                "terrain": {"move": True},
            }
        ]

        floor_grid = parse_snapshot(data, {}).grids[Position(5, 6)]
        self.assertEqual(floor_grid.object_count, 2)
        self.assertEqual(floor_grid.object_tvals, (65, 55))

    def test_parses_terrain_id_and_defaults_for_older_emitters(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {"y": 5, "x": 6, "known": True, "terrain_id": 85,
             "terrain": {"move": True}},
            {"y": 5, "x": 7, "known": True, "terrain": {"move": True}},
        ]

        grids = parse_snapshot(data, {}).grids
        self.assertEqual(grids[Position(5, 6)].terrain_id, 85)
        self.assertEqual(grids[Position(5, 7)].terrain_id, -1)

    def test_parses_walkable_line_of_fire_blocker(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "terrain": {"move": True, "los": False},
            }
        ]

        floor_grid = parse_snapshot(data, {}).grids[Position(5, 6)]
        self.assertTrue(floor_grid.passable)
        self.assertFalse(floor_grid.allows_los)

    def test_parses_fixed_quest_progress_and_visible_quest_grids(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["floor"].update({"level": 0, "in_town": True, "town_id": 0, "town_index": 1})
        data["progress"] = {
            "quests": [
                {
                    "id": 1,
                    "name": "Thieves Hideout",
                    "status": 1,
                    "type": 6,
                    "level": 5,
                    "dungeon_id": 0,
                    "r_idx": 0,
                    "cur_num": 0,
                    "max_num": 0,
                    "num_mon": 0,
                    "flags": 6,
                    "complev": 0,
                    "comptime": 0,
                    "fixed": True,
                    "has_reward": True,
                    "reward_artifact_id": None,
                    "reward_baseitem_id": 42,
                    "reward_instant_artifact": False,
                }
            ]
        }
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "terrain": {"move": True, "quest_enter": True, "quest_exit": False},
                "quest_id": 1,
            },
            {
                "y": 5,
                "x": 7,
                "known": True,
                "terrain": {"move": True, "building": True},
                "building_type": 1,
                "building_special": 1,
            },
        ]

        snap = parse_snapshot(data, {})

        self.assertEqual(snap.town_id, 0)
        self.assertIsNone(snap.visited_town_ids)
        self.assertEqual(snap.town_index, 1)
        self.assertIn(1, snap.quests)
        self.assertEqual(snap.quests[1].status, 1)
        self.assertTrue(snap.quests[1].fixed)
        self.assertEqual(snap.quests[1].reward_baseitem_id, 42)
        self.assertTrue(snap.grids[Position(5, 6)].has_quest_enter)
        self.assertEqual(snap.grids[Position(5, 6)].quest_id, 1)
        self.assertEqual(snap.grids[Position(5, 7)].building_special, 1)

        data["progress"]["visited_town_ids"] = [0, 1]
        with_towns = parse_snapshot(data, {})
        self.assertEqual(with_towns.visited_town_ids, (0, 1))

    def test_omitted_quest_fields_are_undisclosed_not_zero_or_false(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["progress"] = {
            "quests": [{
                "id": 28,
                "name": "Single target",
                "status": 1,
                "type": 1,
                "level": 70,
                "fixed": True,
            }]
        }

        quest = parse_snapshot(data, {}).quests[28]

        for field in (
            "dungeon_id", "r_idx", "cur_num", "max_num", "num_mon",
            "flags", "complev", "comptime", "has_reward",
            "reward_artifact_id", "reward_baseitem_id",
            "reward_instant_artifact",
        ):
            with self.subTest(field=field):
                self.assertIsNone(getattr(quest, field))

    def test_parses_entered_dungeon_ids_for_recall_selection(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["progress"] = {
            "recall_dungeon_id": 2,
            "entered_dungeon_ids": [1, 2, 5],
            "dungeon_recall_depths": {"1": 20, "2": 13, "5": 31},
        }

        snap = parse_snapshot(data, {})

        self.assertEqual(snap.entered_dungeon_ids, (1, 2, 5))
        self.assertEqual(snap.dungeon_recall_depths, {1: 20, 2: 13, 5: 31})

    def test_ignores_legacy_exact_food_and_recall_counters(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["player"]["food"] = 1
        data["player"]["word_recall"] = 17

        player = parse_snapshot(data, {}).player

        self.assertEqual(player.food_state, "unknown")
        self.assertFalse(player.recalling)

    def test_parses_redacted_home_item_without_hidden_kind_or_price(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["store"] = {
            "store_type": 7,
            "items": [
                {
                    "letter": "a",
                    "name": "an unknown ring",
                    "count": 1,
                    "tval": 45,
                    "aware": False,
                    "known": False,
                    "fully_known": False,
                }
            ],
        }

        stored = parse_snapshot(data, {}).store.items[0]

        self.assertEqual(stored.sval, -1)
        self.assertEqual(stored.price, 0)
        self.assertFalse(stored.aware)
        self.assertFalse(stored.known)
        self.assertFalse(stored.fully_known)

    def test_parses_store_device_charges_from_japanese_names(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["store"] = {
            "store_type": 5,
            "items": [
                {"letter": "a", "name": "鑑定の杖 (12回分)", "count": 1,
                 "tval": 55, "sval": 5, "price": 500},
                {"letter": "b", "name": "岩石溶解の魔法棒（27回分）", "count": 3,
                 "tval": 65, "sval": 6, "price": 100},
            ],
        }

        staff, wand = parse_snapshot(data, {}).store.items

        self.assertEqual((staff.charges, staff.pval), (12, 12))
        self.assertEqual((wand.charges, wand.pval), (27, 27))

    def test_store_device_explicit_pval_remains_authoritative(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["store"] = {
            "store_type": 7,
            "items": [{"letter": "a", "name": "鑑定の杖 (12回分)", "count": 1,
                       "tval": 55, "sval": 5, "pval": 19}],
        }

        stored = parse_snapshot(data, {}).store.items[0]

        self.assertEqual((stored.charges, stored.pval), (19, 19))

    def test_parses_visible_progress_grid_and_known_item_details(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["player"].update(
            {
                "class_id": 0,
                "ac": 42,
                "melee": {
                    "main_hand_blows": 200,
                    "sub_hand_blows": 0,
                    "main_hand_to_h": 12,
                    "sub_hand_to_h": 0,
                    "main_hand_to_d": 7,
                    "sub_hand_to_d": 0,
                },
            }
        )
        data["progress"] = {
            "recall_dungeon_id": 1,
            "yeek_cave_conquered": True,
            "angband_recall_unlocked": True,
        }
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "terrain": {
                    "move": False,
                    "wall": True,
                    # Hengband veins are TUNNEL terrain but do not carry the
                    # narrower CAN_DIG flag currently emitted as `can_dig`.
                    "can_dig": False,
                    "tunnel": True,
                    "permanent": False,
                    "has_gold": True,
                    "entrance": False,
                },
            },
            {
                "y": 5,
                "x": 7,
                "known": True,
                "terrain": {"move": True, "entrance": True},
                "entrance_dungeon_id": 2,
            },
        ]
        data["inventory"] = [
            {
                "slot": "a",
                "name": "known sword",
                "count": 1,
                "tval": 23,
                "sval": 1,
                "aware": True,
                "known": True,
                "fully_known": True,
                "is_equipment": True,
                "is_ego": True,
                "is_artifact": False,
                "is_cursed": False,
                "is_broken": False,
                "to_h": 3,
                "to_d": 4,
                "to_a": 0,
                "ac": 0,
                "damage_dice": {"num": 2, "sides": 5},
                "known_flags": [12, 34],
                "pval": 2,
                "timeout": 3,
            }
        ]

        snapshot = parse_snapshot(data, {})

        self.assertEqual(snapshot.player.class_id, 0)
        self.assertEqual(snapshot.player.ac, 42)
        self.assertEqual(snapshot.player.main_hand_blows, 200)
        self.assertTrue(snapshot.yeek_cave_conquered)
        self.assertTrue(snapshot.angband_recall_unlocked)
        self.assertTrue(snapshot.grids[Position(5, 6)].has_gold)
        self.assertTrue(snapshot.grids[Position(5, 6)].can_dig)
        self.assertTrue(snapshot.grids[Position(5, 6)].tunnel)
        self.assertFalse(snapshot.grids[Position(5, 6)].permanent)
        self.assertFalse(snapshot.grids[Position(5, 7)].tunnel)
        self.assertFalse(snapshot.grids[Position(5, 7)].permanent)
        self.assertEqual(snapshot.grids[Position(5, 7)].entrance_dungeon_id, 2)
        self.assertTrue(snapshot.inventory[0].is_ego)
        self.assertEqual(snapshot.inventory[0].known_flags, frozenset({12, 34}))
        self.assertEqual(snapshot.inventory[0].pval, 2)
        self.assertEqual(snapshot.inventory[0].timeout, 3)


class DecisionRecordTest(unittest.TestCase):
    @staticmethod
    def _town_snapshot():
        data = json.loads(_snap_line(123, 5, 7))
        data["floor"] = {"dungeon_id": 0, "level": 0, "in_town": True}
        return parse_snapshot(data, {})

    @staticmethod
    def _q34_town_snapshot():
        data = json.loads(_snap_line(123, 26, 97))
        data["floor"] = {"dungeon_id": 0, "level": 0, "in_town": True}
        data["nearby_grids"] = [{
            "y": 26,
            "x": 98,
            "known": True,
            "terrain": {"move": True, "building": True},
            "building_type": 0,
            "building_special": 34,
        }]
        return parse_snapshot(data, {})

    def test_prompt_owner_handoff_is_visible_in_decision_record(self):
        policy = HengbotPolicy()
        policy.prompt_owner_handoff = "seek-loot"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            _write_decision(path, self._town_snapshot(), "g", "pickup", policy)
            row = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(row["prompt_owner_handoff"], "seek-loot")

    def test_choose_key_mutation_reports_survive_reason_fallthrough(self):
        snapshot = self._town_snapshot()
        cases = (
            ("posting-contract:equipment-mutation-unobserved", 0, None),
            ("posting-contract:equipment-mutation-released", TERMINAL_NUDGE_LIMIT - 1, None),
            ("goal-already-superseded", 0, "combat-loadout"),
        )
        for expected, refusals, opposing_goal in cases:
            with self.subTest(report=expected), TemporaryDirectory() as directory:
                policy = HengbotPolicy()
                executor = policy._equipment_mutation
                hunt_data = json.loads(_snap_line(124, 10, 10))
                hunt_data["floor"] = {
                    "dungeon_id": 2, "level": 1, "in_town": False,
                }
                hunt_data["nearby_grids"] = [
                    {"y": 10, "x": x, "known": True,
                     "monster_index": 7 if x == 14 else 0,
                     "terrain": {"move": True}}
                    for x in range(10, 15)
                ]
                hunt_data["visible_monsters"] = [{"index": 7, "race_id": 35}]
                hunt_snapshot = parse_snapshot(
                    hunt_data, {35: MonraceKnowledge(8, 110, False, False)}
                )
                hunt_monster = hunt_snapshot.visible_monsters[0]
                if opposing_goal is None:
                    prepared = executor.request_takeoff(
                        snapshot, "mining-loadout", "a"
                    )
                    executor.bind_post_snapshot(snapshot)
                    executor.confirm_posted(prepared.key)
                    executor.refusals = refusals
                else:
                    executor.last_posted_goal = opposing_goal
                    executor.last_posted_core = progress_core(snapshot)

                def fallthrough(_snapshot):
                    mutation_key = policy._equipment_takeoff(
                        snapshot, "mining-loadout", "a"
                    )
                    policy._hunt_step(hunt_snapshot, [hunt_monster])
                    hunt_identity = policy._hunt_target_identities[7]
                    progress = policy._hunt_progress[hunt_identity]
                    progress["steps"] = HUNT_RANGE - 1
                    progress["decision"] -= 1
                    policy._hunt_step(hunt_snapshot, [hunt_monster])
                    policy.last_reason = "explore:fallthrough"
                    return mutation_key

                with patch.object(
                    policy, "_choose_key_with_latch_capture", side_effect=fallthrough
                ):
                    key = policy.choose_key(snapshot)
                path = Path(directory) / "decisions.jsonl"
                _write_decision(path, snapshot, key, policy.last_reason, policy)
                row = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(row["reason"], "explore:fallthrough")
                self.assertEqual(row["equipment_mutation_report"], expected)
                self.assertEqual(
                    row["hunt_report"], "hunt:abandoned-no-damage-no-closure"
                )

    def test_captured_facts_keep_town_and_dungeon_rows_identical(self):
        timing = {"read_ms": 1.0, "choose_key_ms": 2.0, "total_ms": 3.0}
        snapshots = (
            self._q34_town_snapshot(),
            parse_snapshot(json.loads(_snap_line(124, 6, 7)), {}),
        )
        for snapshot in snapshots:
            with self.subTest(floor=snapshot.floor_key), TemporaryDirectory() as directory:
                policy = HengbotPolicy()
                policy.prime(snapshot)
                key = policy.choose_key(snapshot)
                if snapshot.in_town:
                    policy._town_errand_plan = SimpleNamespace(
                        stops=[0, 7], index=0, inserted_this_visit=[7],
                        skipped_latched=[],
                    )
                facts = _capture_decision_facts(snapshot, policy)
                if snapshot.in_town:
                    self.assertEqual(
                        facts["town_plan"]["stops"], ["General Store", "Home"]
                    )
                old_path = Path(directory) / "old.jsonl"
                new_path = Path(directory) / "new.jsonl"
                _write_decision(
                    old_path, snapshot, key, policy.last_reason, policy, timing=timing,
                )
                _write_decision(
                    new_path, snapshot, key, policy.last_reason, policy, timing=timing,
                    decision_facts=facts,
                )
                old = json.loads(old_path.read_text(encoding="utf-8"))
                new = json.loads(new_path.read_text(encoding="utf-8"))
                old["time"] = new["time"] = "masked"
                self.assertEqual(set(old["timing"]), set(new["timing"]))
                old["timing"] = new["timing"] = "masked"
                self.assertEqual(old, new)

    def test_home_procurement_fallthrough_is_consumed_after_one_row(self):
        snapshot = self._town_snapshot()
        policy = HengbotPolicy()
        policy._home_procurement_fallthrough = "fresh-catalogue-absence"
        policy._home_procurement_fallthrough_equivalence = (
            "ammo:exact-tval-any-sval"
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            _write_decision(path, snapshot, "p", "shop:buy", policy)
            _write_decision(path, snapshot, "6", "explore", policy)
            rows = [json.loads(line) for line in path.read_text().splitlines()]

        self.assertEqual(
            rows[0]["home_procurement_fallthrough"],
            {
                "case": "fresh-catalogue-absence",
                "classification": "legal-fresh-catalogue-absence",
                "need_equivalence": "ammo:exact-tval-any-sval",
            },
        )
        self.assertNotIn("home_procurement_fallthrough", rows[1])

    def test_captured_writer_does_not_recompute_policy_telemetry(self):
        snapshot = self._town_snapshot()
        policy = HengbotPolicy()
        policy.prime(snapshot)
        key = policy.choose_key(snapshot)
        facts = _capture_decision_facts(snapshot, policy)
        expensive = (
            "procurement_requirements", "threat_prediction",
            "equipment_optimization_state", "loot_state",
            "departure_block_state", "cross_town_shopping_state",
        )
        with TemporaryDirectory() as directory:
            patches = [
                patch.object(policy, name, side_effect=AssertionError(name))
                for name in expensive
            ]
            for mocked in patches:
                mocked.start()
            try:
                _write_decision(
                    Path(directory) / "decision.jsonl", snapshot, key,
                    policy.last_reason, policy, decision_facts=facts,
                )
            finally:
                for mocked in reversed(patches):
                    mocked.stop()
            self.assertTrue((Path(directory) / "decision.jsonl").is_file())

    def test_writer_treats_only_none_as_missing_decision_facts(self):
        class FalsyFacts(dict):
            def __bool__(self):
                return False

        snapshot = self._town_snapshot()
        policy = HengbotPolicy()
        policy.prime(snapshot)
        key = policy.choose_key(snapshot)
        facts = FalsyFacts(_capture_decision_facts(snapshot, policy))
        with TemporaryDirectory() as directory, patch(
            "hengbot.cli._capture_decision_facts",
            side_effect=AssertionError("falsy facts were recomputed"),
        ):
            path = Path(directory) / "decision.jsonl"
            _write_decision(
                path, snapshot, key, policy.last_reason, policy,
                decision_facts=facts,
            )
            self.assertTrue(path.is_file())

    @staticmethod
    def _town_stall_policy(passes=24):
        action = SimpleNamespace(
            phase="withdraw", kind="withdraw", item_id="sword", target_slot=None
        )
        session = SimpleNamespace(
            target_loadout_id="loadout-1",
            index=1,
            complete=False,
            blockers=["await-home"],
            required_context="home",
            current_action=action,
            pending_action=None,
        )
        ledger = SimpleNamespace(
            store_visits={7: 3},
            need_attempts={"deposit": 4},
            approach_fails={7: 1},
            unsatisfied_passes={7: 2},
            blocked_stores=set(),
            passes_since_progress=passes,
        )
        return SimpleNamespace(
            _town_claim_categories=("deposit", "equipment-work"),
            _town_visit_ledger=ledger,
            _store_visit=SimpleNamespace(
                owner="deposit", store_type=7, opened_sequence=91
            ),
            _town_blocked_reason="owner-returned-none",
            _town_errand_plan=SimpleNamespace(stops=[7], index=0),
            _equipment_transaction_session=session,
            _equipment_transaction_owned_items=[("weapon-1", "main_hand")],
            _calibration_phase="deposit",
            _shop_selector_diagnostics={
                "winning_rung": "town:blocked:repetition",
                "wanted_purchase": {
                    "category": "recall",
                    "name": "Word of Recall",
                    "letter": "i",
                    "price": 227,
                    "count": 20,
                },
                "considered_candidate": None,
                "rejection_reason": "preempted",
            },
            choke_engagement_state=lambda: {
                "phase": "release", "release_cause": "no-progress"
            },
        )

    def test_town_claim_fallback_stall_records_accumulated_policy_state(self):
        snapshot = self._town_snapshot()
        policy = self._town_stall_policy()

        report = _town_stall_report(snapshot, policy, "stuck:wander")
        record = _decision_record(
            snapshot, "6", "stuck:wander", town_stall_report=report
        )

        self.assertEqual(report["store_visit"], {
            "owner": "deposit", "store": 7, "opened_sequence": 91
        })
        self.assertEqual(report["town_blocked_reason"], "owner-returned-none")
        self.assertEqual(report["town_plan"], {"stops": [7], "index": 0})
        self.assertEqual(report["visit_ledger"]["passes_since_progress"], 24)
        self.assertEqual(report["equipment_transaction"]["target_loadout_id"], "loadout-1")
        self.assertEqual(
            report["equipment_transaction_owned_items"],
            [["weapon-1", "main_hand"]],
        )
        self.assertEqual(report["calibration_phase"], "deposit")
        self.assertEqual(report["choke_engagement"]["release_cause"], "no-progress")
        self.assertEqual(record["town_stall_report"], report)

    def test_ordinary_town_decision_has_no_stall_report_or_changed_key(self):
        snapshot = self._town_snapshot()
        policy = self._town_stall_policy()

        report = _town_stall_report(snapshot, policy, "shop:travel")
        record = _decision_record(
            snapshot, "_", "shop:travel", town_stall_report=report
        )

        self.assertIsNone(report)
        self.assertNotIn("town_stall_report", record)
        self.assertEqual(record["key"], "_")

    def test_town_stall_report_repeats_only_at_existing_window_cadence(self):
        snapshot = self._town_snapshot()

        emitted = [
            passes
            for passes in range(1, 73)
            if _town_stall_report(
                snapshot, self._town_stall_policy(passes), "breakout:seek-frontier"
            ) is not None
        ]

        self.assertEqual(emitted, [24, 48, 72])

    def test_repeating_named_town_block_reports_reason_count_and_candidate(self):
        snapshot = self._town_snapshot()
        policy = self._town_stall_policy()

        report = _town_stall_report(
            snapshot,
            policy,
            "town:blocked:repetition",
            repeating_reason_count=24,
        )

        block = report["repeating_named_block"]
        self.assertEqual(block["reason"], "town:blocked:repetition")
        self.assertEqual(block["consecutive_decisions"], 24)
        self.assertEqual(
            block["out_ranked_candidate"],
            policy._shop_selector_diagnostics["wanted_purchase"],
        )
        self.assertEqual(
            block["shop_selector"]["winning_rung"],
            "town:blocked:repetition",
        )

    def test_isolated_named_town_block_emits_no_stall_report(self):
        report = _town_stall_report(
            self._town_snapshot(),
            self._town_stall_policy(passes=1),
            "town:blocked:repetition",
            repeating_reason_count=1,
        )

        self.assertIsNone(report)

    def test_named_block_becomes_terminal_at_existing_report_cadence(self):
        snapshot = self._town_snapshot()
        policy = self._town_stall_policy()
        reason = "town:blocked:repetition"

        before = _town_stall_report(
            snapshot, policy, reason,
            repeating_reason_count=EXTENDED_STUCK_WINDOW - 1,
        )
        due = _town_stall_report(
            snapshot, policy, reason,
            repeating_reason_count=EXTENDED_STUCK_WINDOW,
        )

        self.assertFalse(_town_stall_report_terminates_named_block(before, reason))
        self.assertTrue(_town_stall_report_terminates_named_block(due, reason))

    def test_live_town_stall_repeating_reason_wiring_counts_and_reports(self):
        snapshot = self._town_snapshot()
        policy = self._town_stall_policy()
        policy.last_reason = "town:blocked:repetition"
        previous_reason = None
        repeating_reason_count = 0
        report = None

        for _ in range(24):
            previous_reason, repeating_reason_count, report = (
                _advance_repeating_reason_iteration(
                    snapshot,
                    policy,
                    previous_reason,
                    repeating_reason_count,
                )
            )

        self.assertEqual(repeating_reason_count, 24)
        self.assertEqual(
            report["repeating_named_block"]["consecutive_decisions"], 24
        )

    def test_live_town_stall_repeating_reason_wiring_resets_after_interruption(self):
        snapshot = self._town_snapshot()
        policy = self._town_stall_policy()
        previous_reason = None
        repeating_reason_count = 0

        for reason in (
            ["town:blocked:repetition"] * 23
            + ["shop:travel"]
            + ["town:blocked:repetition"] * 23
        ):
            policy.last_reason = reason
            previous_reason, repeating_reason_count, report = (
                _advance_repeating_reason_iteration(
                    snapshot,
                    policy,
                    previous_reason,
                    repeating_reason_count,
                )
            )

        self.assertEqual(repeating_reason_count, 23)
        self.assertIsNone(report)

    def test_measured_named_block_shape_reports_before_thirty_blocks(self):
        snapshot = self._town_snapshot()
        policy = self._town_stall_policy(passes=1)
        previous_reason = None
        repeating_reason_count = 0
        blocked_decisions = 0
        reports_at = []

        reasons = []
        for run in (7, 20, 2, 22):
            reasons.extend(["town:blocked:repetition"] * run)
            if run in (7, 22):
                reasons.append("periodic:character-dump")
        for reason in reasons:
            policy.last_reason = reason
            previous_reason, repeating_reason_count, report = (
                _advance_repeating_reason_iteration(
                    snapshot, policy, previous_reason, repeating_reason_count
                )
            )
            if reason == "town:blocked:repetition":
                blocked_decisions += 1
            if report is not None:
                reports_at.append(blocked_decisions)
            if blocked_decisions == 30:
                break

        self.assertEqual(reports_at, [24])

        previous_reason = None
        repeating_reason_count = 0
        for reason in (
            ["town:blocked:repetition"] * (EXTENDED_STUCK_WINDOW - 1)
            + ["shop:travel"]
            + ["town:blocked:repetition"] * (EXTENDED_STUCK_WINDOW - 1)
        ):
            policy.last_reason = reason
            previous_reason, repeating_reason_count, report = (
                _advance_repeating_reason_iteration(
                    snapshot, policy, previous_reason, repeating_reason_count
                )
            )
            self.assertIsNone(report)

    def test_stopping_town_block_always_builds_report_before_periodic_window(self):
        report = _town_stall_report(
            self._town_snapshot(),
            self._town_stall_policy(passes=1),
            "town:blocked:no-safe-recall-destination",
            repeating_reason_count=1,
            stopping=True,
        )

        record = _decision_record(
            self._town_snapshot(), "_", "loop-detected", town_stall_report=report
        )
        self.assertEqual(
            record["town_stall_report"]["town_blocked_reason"],
            "owner-returned-none",
        )

    def test_records_snapshot_messages_with_repeat_counter(self):
        snapshot = parse_snapshot(
            {
                "type": "player_turn",
                "turn": 41,
                "floor": {"dungeon_id": 0, "level": 0, "in_town": True},
                "player": {"y": 5, "x": 7, "hp": 10, "max_hp": 10},
                "messages": ["That command does not work in stores. <x8>"],
            },
            {},
        )

        record = _decision_record(snapshot, " ", "home-disposal:seek-page")

        self.assertEqual(
            record["messages"],
            ["That command does not work in stores. <x8>"],
        )

    def test_in_store_record_carries_shop_selector_evidence(self):
        data = json.loads(_snap_line(123, 5, 7))
        snapshot = parse_snapshot(data, {})
        evidence = {
            "winning_rung": "shop:sell-device",
            "gold": 9193,
            "wanted_purchase": {
                "category": "identify-staff",
                "name": "Staff of Identify",
                "letter": "g",
                "price": 950,
                "count": 4,
                "charges": 19,
            },
            "considered_candidate": {
                "category": "identify-staff",
                "name": "Staff of Identify",
                "letter": "g",
                "price": 950,
                "count": 4,
                "charges": 19,
            },
            "rejection_reason": "preempted",
        }

        record = _decision_record(
            snapshot,
            "s",
            "shop:sell-device",
            shop_selector=evidence,
        )

        self.assertEqual(record["shop_selector"], evidence)

    def test_decision_record_carries_identification_source_reservation(self):
        snapshot = parse_snapshot(json.loads(_snap_line(123, 5, 7)), {})
        reservation = {
            "target": ["unknown sword", 23, -1],
            "kind": "normal",
            "source": {
                "signature": ["Identify", 70, 12],
                "slot": "c",
            },
            "state": "acquired",
        }

        record = _decision_record(
            snapshot,
            "6",
            "shop:travel",
            identification_source_reservation=reservation,
        )

        self.assertEqual(
            record["identification_source_reservation"], reservation
        )

    def test_decision_record_carries_read_binding_telemetry(self):
        snapshot = parse_snapshot(json.loads(_snap_line(123, 5, 7)), {})
        telemetry = {
            "key": "rh",
            "letter": "h",
            "resolved": {"tval": 70, "sval": 26, "name": "Detect Treasure"},
            "intended": {"tval": 70, "sval": 26, "name": "Detect Treasure"},
        }

        record = _decision_record(
            snapshot, "rh", "fundraise:detect-treasure", read=telemetry
        )

        self.assertEqual(record["read"], telemetry)

    def test_decision_record_carries_calibration_entry_diagnostics(self):
        snapshot = parse_snapshot(json.loads(_snap_line(2940289, 45, 123)), {})
        equipment = {
            "blockers": ["calibration-required"],
            "calibration": {
                "phase": None,
                "entry_blocker": "home-unavailable",
            },
            "equipment_transaction": {
                "context": None,
                "entry_blocker": "no-session",
            },
        }

        record = _decision_record(
            snapshot,
            "9",
            "town:blocked:no-safe-recall-destination",
            equipment_optimization=equipment,
        )

        self.assertEqual(record["equipment_optimization"], equipment)

    def test_records_policy_reason_and_observable_state(self):
        data = json.loads(_snap_line(123, 5, 7))
        data["floor"]["quest_id"] = 40
        snapshot = parse_snapshot(data, {})

        requirements = [
            {"item": "Food rations", "current": 2, "target": 5, "missing": 3}
        ]
        record = _decision_record(snapshot, "6", "seek-loot", requirements)

        self.assertEqual(record["turn"], 123)
        self.assertEqual(record["objective"], "Collect visible floor items")
        self.assertEqual(record["reason"], "seek-loot")
        self.assertEqual(record["key"], "6")
        self.assertEqual(
            record["floor"], {"dungeon_id": 0, "level": 1, "quest_id": 40}
        )
        self.assertEqual(record["position"], {"y": 5, "x": 7})
        self.assertEqual(record["inventory"], {"used": 0, "free": 23})
        self.assertEqual(record["procurement_requirements"], requirements)
        abandoned = {
            "launcher": "all-suppliers-visited-without-affordable-stock"
        }
        record = _decision_record(
            snapshot,
            "6",
            "seek-loot",
            requirements,
            abandoned_quest_carry_requirements=abandoned,
        )
        self.assertEqual(
            record["abandoned_quest_carry_requirements"], abandoned
        )
        self.assertEqual(record["visible_hostiles"], 0)
        self.assertEqual(record["threat_prediction"], {})
        self.assertEqual(record["loot"], {})

    def test_records_loot_telemetry(self):
        snapshot = parse_snapshot(json.loads(_snap_line(123, 5, 7)), {})
        loot = {
            "visible": [{"position": {"y": 5, "x": 8}, "count": 1}],
            "known": [{"y": 5, "x": 8}],
            "target": {"y": 5, "x": 8},
            "blocker": None,
        }

        record = _decision_record(
            snapshot, "6", "seek-loot", loot=loot
        )

        self.assertEqual(record["loot"], loot)

    def test_records_fundraising_telemetry(self):
        data = json.loads(_snap_line(123, 5, 7))
        data["floor"]["dungeon_id"] = 0
        data["floor"]["level"] = 0
        data["player"]["class_id"] = 0
        data["player"]["gold"] = 100
        snapshot = parse_snapshot(data, {})

        class Policy:
            _fundraising_mode = "prepare"
            _planned_mining_runs = 2

            def _fundraising_kit_secured(self, snapshot):
                return False

        fundraising = _fundraising_state(snapshot, Policy())
        record = _decision_record(
            snapshot, "6", "fundraise:prepare", fundraising=fundraising
        )

        self.assertEqual(
            record["fundraising"],
            {
                "mode": "prepare",
                "planned_runs": 2,
                "kit_secured": False,
                "gold_trigger": True,
            },
        )


class DuplicateSnapshotThrottleTest(unittest.TestCase):
    def test_sent_nudge_releases_real_captured_descend_key(self):
        # Live turn 1839609: the first >y was swallowed after travel while the
        # emitter kept returning this byte-identical board. A sent Escape
        # permits exactly one fresh policy posting on that same board.
        line = _snap_line(1839609, 31, 150)
        posted = []
        posted_line = None
        posted_keys = set()

        _, posted_line = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            line, ">y", posted_line, posted_keys, in_store=False,
        )
        self.assertTrue(
            _send_stall_recovery_nudge(
                lambda value: posted.append(value) or True,
                "\x1b",
                posted_keys,
            )
        )
        _, posted_line = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            line, ">y", posted_line, posted_keys, in_store=False,
        )

        self.assertEqual(posted, [">y", "\x1b", ">y"])

    def test_unsent_nudge_keeps_same_board_key_suppressed(self):
        line = _snap_line(1839609, 31, 150)
        posted = []
        posted_line = None
        posted_keys = set()

        _, posted_line = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            line, ">y", posted_line, posted_keys, in_store=False,
        )
        self.assertFalse(
            _send_stall_recovery_nudge(lambda _value: False, "\x1b", posted_keys)
        )
        _, posted_line = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            line, ">y", posted_line, posted_keys, in_store=False,
        )

        self.assertEqual(posted, [">y"])

    def test_store_leave_suppression_survives_sent_nudge(self):
        line = _snap_line(1099751, 45, 123)
        posted = []
        posted_line = None
        posted_keys = {"\r"}

        self.assertTrue(
            _send_stall_recovery_nudge(
                lambda value: posted.append(value) or True,
                "\x1b",
                posted_keys,
            )
        )
        _, posted_line = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            line, "\r", posted_line, posted_keys, in_store=True, suppress=True,
        )

        self.assertEqual(posted, ["\x1b"])

    def test_aborted_one_shot_allows_one_bounded_stall_escape(self):
        """The old in-store d0y owner is gone; recovery may clear an abort."""
        posted = []
        posted_keys = {"d0y"}

        sent = _send_stall_recovery_nudge(
            lambda value: posted.append(value) or True,
            "\x1b",
            posted_keys,
            in_store=True,
        )

        self.assertTrue(sent)
        self.assertEqual(posted, ["\x1b"])
        self.assertEqual(posted_keys, set())

    def test_store_recovery_waits_fresh_then_escapes_once_at_stall_bound(self):
        timeout = 1.5
        self.assertEqual(
            _stall_recovery_action(1.49, timeout, in_store=True), "wait"
        )
        self.assertEqual(
            _stall_recovery_action(1.51, timeout, in_store=True),
            "store-escape",
        )
        self.assertEqual(
            _stall_recovery_action(
                10.0, timeout, in_store=True, recovery_attempts=1
            ),
            "wait",
        )
        self.assertEqual(
            _stall_recovery_action(1.51, timeout, in_store=False), "nudge"
        )

    def test_failed_window_send_still_reaches_terminal_attempt_bound(self):
        attempts = 0
        for _ in range(20):
            if _stall_recovery_action(2.0, 1.5, in_store=False) == "nudge":
                _send_stall_recovery_nudge(
                    lambda _value: False, "\x1b", set(), in_store=False
                )
                attempts += 1
        self.assertGreaterEqual(attempts, 20)

    def test_failed_window_send_reaches_terminal_attempt_bound_in_store(self):
        """9f05878 froze at recovery_attempts=1: every later action was wait."""
        attempts = 0
        send_failed = False
        while attempts < TERMINAL_NUDGE_LIMIT:
            action = _stall_recovery_action(
                2.0, 1.5, in_store=True, recovery_attempts=attempts,
                send_failed=send_failed,
            )
            self.assertIn(action, {"store-escape", "nudge"})
            sent = _send_stall_recovery_nudge(
                lambda _value: False, "\x1b", set(), in_store=True
            )
            send_failed = not sent
            attempts += 1

    def test_silent_modal_recovery_is_finite_and_restart_bounded(self):
        actions = [
            _modal_recovery_action(attempt)
            for attempt in range(TERMINAL_NUDGE_LIMIT + 1 + MODAL_RECOVERY_ROUNDS + 1)
        ]
        self.assertEqual(actions.count("esc-look"), MODAL_RECOVERY_ROUNDS)
        self.assertEqual(actions[-1], "stop")
        self.assertEqual(_modal_recovery_action(0), "nudge")

    def test_loop_modal_escalation_prioritizes_dead_and_live_outcomes(self):
        for alive, expected in ((False, "player-death"), (True, "stuck-prompt")):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                state = root / "state.jsonl"
                state.write_text(_snap_line(1, 5, 5), encoding="utf-8")
                args = _build_argument_parser().parse_args([
                    "--state-file", str(state),
                    "--decision-log", str(root / "decisions.jsonl"),
                    "--poll-interval", "0.001", "--stall-timeout", "0.001",
                    "--send-to-window", "--window-pid", "123",
                ])
                args.wait_telemetry = unittest.mock.Mock()
                policy = HengbotPolicy()
                policy.choose_key = unittest.mock.Mock(return_value=None)
                policy.last_reason = "test:silent"
                sent = []
                incidents = []

                clock = iter(float(value) for value in range(10000))
                with (
                    patch("hengbot.cli.time.monotonic", side_effect=lambda: next(clock)),
                    patch("hengbot.cli.time.sleep"),
                    patch(
                        "hengbot.cli._game_process_alive",
                        side_effect=([True, True] if alive else [True, False]),
                    ),
                    patch(
                        "hengbot.cli._freeze_incident_safely",
                        side_effect=lambda _recorder, kind, *_args: incidents.append(kind),
                    ),
                    patch("hengbot.cli._append_capture_ledger"),
                ):
                    self.assertEqual(
                        _run_follow(
                            args, policy,
                            lambda key, **_kwargs: sent.append(key) or True,
                            {},
                        ),
                        0,
                    )
                probes = [key for key in sent if key == "\x1bl\x1b"]
                self.assertEqual(len(probes), 1)
                self.assertEqual(incidents, [expected])

    def test_captured_home_leave_posts_nothing_until_context_confirms(self):
        # Live turn 1099751: Esc left Home, but the next stale store decision's
        # Enter must not reach the command loop. After confirmation, the
        # captured identify macro must be posted normally.
        line = _snap_line(1099751, 45, 123)
        posted = []
        posted_line = None
        posted_keys = set()

        for key, suppress in (
            ("\x1b", False),
            ("\r", True),
            ("rgn" + "\x1b" * 8, False),
        ):
            _, posted_line = _send_new_decision_key(
                lambda value, **_kwargs: posted.append(value) or True,
                line,
                key,
                posted_line,
                posted_keys,
                in_store=False,
                suppress=suppress,
            )

        self.assertEqual(posted, ["\x1b", "rgn" + "\x1b" * 8])

    def test_suppressed_store_leave_decisions_still_reach_bounded_stop(self):
        line = _snap_line(1099751, 45, 123)
        posted = []
        posted_line = None
        posted_keys = set()
        count = 0
        previous_signature = None

        for _ in range(STALLED_COMMAND_STATE_LIMIT + 1):
            signature = (line, "shop:await-leave-confirmation", "\r")
            count = _advance_stalled_command_count(
                count,
                signature=signature,
                previous_signature=previous_signature,
            )
            previous_signature = signature
            _, posted_line = _send_new_decision_key(
                lambda value, **_kwargs: posted.append(value) or True,
                line,
                "\r",
                posted_line,
                posted_keys,
                in_store=True,
                suppress=True,
            )

        self.assertGreaterEqual(count, STALLED_COMMAND_STATE_LIMIT)
        self.assertEqual(posted, [])

    def test_real_rejected_shop_approach_keeps_deciding_without_resending(self):
        # Live turn 1099696 at (45, 123): shop:approach "9" was silently
        # rejected, then the byte-identical line (empty messages, same turn)
        # repeated. Decisions must continue while the posted key stays unique.
        line = _snap_line(1099696, 45, 123)
        decisions = []
        posted = []
        posted_line = None
        posted_keys = set()

        for _ in range(4):
            self.assertTrue(
                _duplicate_snapshot_ready(line, line, "shop:approach")
            )
            decisions.append("9")
            _, posted_line = _send_new_decision_key(
                lambda key, **_kwargs: posted.append(key) or True,
                line,
                "9",
                posted_line,
                posted_keys,
                in_store=False,
            )

        self.assertEqual(decisions, ["9", "9", "9", "9"])
        self.assertEqual(posted, ["9"])

    def test_real_fundraising_board_posts_each_key_at_most_once(self):
        # The captured 1 1 T3 9 9 failure cannot be reproduced: repeated
        # decisions are recorded, but duplicate sends on one board are not.
        line = _snap_line(1021819, 16, 8)
        posted = []
        posted_line = None
        posted_keys = set()
        for key in ("1", "1", "T3", "9", "9"):
            _, posted_line = _send_new_decision_key(
                lambda value, **_kwargs: posted.append(value) or True,
                line,
                key,
                posted_line,
                posted_keys,
                in_store=False,
            )

        self.assertEqual(posted, ["1", "T3", "9"])

    def test_different_key_on_repeated_board_is_sent(self):
        line = _snap_line(1099696, 45, 123)
        posted = []
        posted_line = None
        posted_keys = set()
        for key in ("9", "9", "7"):
            _, posted_line = _send_new_decision_key(
                lambda value, **_kwargs: posted.append(value) or True,
                line,
                key,
                posted_line,
                posted_keys,
                in_store=False,
            )

        self.assertEqual(posted, ["9", "7"])

    def test_repeated_board_can_reach_existing_stalled_command_stop(self):
        line = _snap_line(1099696, 45, 123)
        count = 0
        previous_signature = None
        for _ in range(STALLED_COMMAND_STATE_LIMIT + 1):
            self.assertTrue(
                _duplicate_snapshot_ready(line, line, "shop:approach")
            )
            signature = (line, "shop:approach", "9")
            count = _advance_stalled_command_count(
                count,
                signature=signature,
                previous_signature=previous_signature,
            )
            previous_signature = signature

        self.assertEqual(count, STALLED_COMMAND_STATE_LIMIT)

    def test_acts_immediately_when_snapshot_state_changes(self):
        previous = _snap_line(100, 5, 5)
        current = _snap_line(110, 5, 6)

        self.assertTrue(_duplicate_snapshot_ready(current, previous))

    def test_wall_bump_message_makes_rejected_command_actionable(self):
        previous = _snap_line(1021819, 16, 8)
        data = json.loads(previous)
        data["messages"] = ["花崗岩の壁が行く手をはばんでいる。"]
        rejected = json.dumps(data, ensure_ascii=False) + "\n"

        self.assertTrue(_duplicate_snapshot_ready(rejected, previous))

    def test_emits_one_purchase_until_a_new_store_snapshot_arrives(self):
        line = _snap_line(2068969, 31, 91)
        emitted = []
        previous_line = None
        previous_reason = None

        for _elapsed in (0.0, 2.0):
            if _duplicate_snapshot_ready(
                line, previous_line, previous_reason
            ):
                emitted.append("ph30\r\r")
                previous_line = line
                previous_reason = "shop:buy-ammo"

        self.assertEqual(emitted, ["ph30\r\r"])
        changed_data = json.loads(line)
        changed_data["player"]["gold"] = 970
        changed = json.dumps(changed_data) + "\n"
        self.assertTrue(
            _duplicate_snapshot_ready(changed, previous_line, previous_reason)
        )


class InputDesynchronizationTest(unittest.TestCase):
    @staticmethod
    def _snapshot(turn, y, x, *, floor=1, messages=()):
        data = json.loads(_snap_line(turn, y, x))
        data["floor"]["level"] = floor
        data["messages"] = list(messages)
        return parse_snapshot(data, {})

    def test_real_orbit_tangential_move_is_desynchronized(self):
        # Capture turn 968097: policy aimed northeast toward the stationary
        # adjacent Lurker, but the queued previous key moved east instead.
        before = self._snapshot(968097, 27, 180, floor=16)
        after = self._snapshot(968108, 27, 181, floor=16)

        self.assertTrue(_direction_desynchronized(before, "9", after))

    def test_zero_displacement_attack_wall_and_door_are_not_desync(self):
        before = self._snapshot(10, 5, 5)
        for message in ("You hit the Lurker.", "There is a wall.", "The door is stuck."):
            with self.subTest(message=message):
                after = self._snapshot(11, 5, 5, messages=(message,))
                self.assertFalse(_direction_desynchronized(before, "6", after))

    def test_floor_change_and_teleport_are_not_desync(self):
        before = self._snapshot(10, 5, 5, floor=16)
        floor_change = self._snapshot(11, 7, 9, floor=17)
        teleport = self._snapshot(11, 20, 30, floor=16)

        self.assertFalse(_direction_desynchronized(before, "6", floor_change))
        self.assertFalse(_direction_desynchronized(before, "6", teleport))

    def test_matching_direction_and_non_direction_are_not_desync(self):
        before = self._snapshot(10, 5, 5)
        after = self._snapshot(11, 5, 6)

        self.assertFalse(_direction_desynchronized(before, "6", after))
        self.assertFalse(_direction_desynchronized(before, "T6", after))

    def test_look_barrier_resumes_only_at_following_ordinary_snapshot(self):
        look = json.dumps({"type": "look", "look": {}}) + "\n"
        board = _snap_line(11, 5, 6)

        self.assertFalse(_look_barrier_allows_decision([look]))
        self.assertTrue(_look_barrier_allows_decision([look, board]))

    def test_look_barrier_discards_ordinary_board_before_look(self):
        before = _snap_line(10, 5, 5)
        look = json.dumps({"type": "look", "look": {}}) + "\n"
        after = _snap_line(11, 5, 6)

        eligible, look_seen = _look_barrier_release([before, look, after])

        self.assertTrue(look_seen)
        self.assertEqual(eligible, [after])

    def test_look_barrier_waits_across_batches_after_look(self):
        before = _snap_line(10, 5, 5)
        look = json.dumps({"type": "look", "look": {}}) + "\n"
        after = _snap_line(11, 5, 6)

        eligible, look_seen = _look_barrier_release([before, look])
        self.assertEqual(eligible, [])
        self.assertTrue(look_seen)
        self.assertEqual(_look_barrier_release([after], look_seen)[0], [after])

    def test_look_barrier_discards_board_until_look_arrives_later(self):
        surplus_board = _snap_line(10, 5, 5)
        look = json.dumps({"type": "look", "look": {}}) + "\n"
        current_board = _snap_line(11, 5, 6)

        eligible, look_seen, timed_out = _look_barrier_timed_release(
            [surplus_board], False, 0.5
        )
        self.assertEqual(eligible, [])
        self.assertFalse(look_seen)
        self.assertFalse(timed_out)

        eligible, look_seen, timed_out = _look_barrier_timed_release(
            [look, current_board], look_seen, 1.0
        )
        self.assertEqual(eligible, [current_board])
        self.assertTrue(look_seen)
        self.assertFalse(timed_out)

    def test_missing_look_response_escapes_only_after_existing_bound(self):
        board = _snap_line(11, 5, 6)

        self.assertEqual(
            _look_barrier_timed_release(
                [board], False, LOOK_BARRIER_TIMEOUT_SECONDS - 0.01
            ),
            ([], False, False),
        )
        with patch("builtins.print") as print_mock:
            self.assertEqual(
                _look_barrier_timed_release(
                    [board], False, LOOK_BARRIER_TIMEOUT_SECONDS
                ),
                ([board], False, True),
            )
        print_mock.assert_called_once_with(
            "<look-barrier:timeout>", flush=True
        )

    def test_missing_look_response_makes_progress_without_reprobe(self):
        self.assertTrue(_look_barrier_allows_decision([_snap_line(11, 5, 6)]))


class ChestMovementAcknowledgementTest(unittest.TestCase):
    def _snapshot(self, position, floor_key=(0, 0, 0)):
        return SimpleNamespace(
            floor_key=floor_key,
            player=SimpleNamespace(position=position),
        )

    def test_holds_duplicate_move_while_position_is_unchanged(self):
        position = Position(35, 119)
        pending = ((0, 0, 0), position, Position(35, 118), 10.0)

        self.assertTrue(
            _chest_movement_response_pending(
                pending, self._snapshot(position), 10.5
            )
        )
        self.assertFalse(
            _chest_movement_response_pending(
                pending,
                self._snapshot(position),
                10.0 + CHEST_MOVE_RESPONSE_SECONDS,
            )
        )

    def test_position_change_acknowledges_move_immediately(self):
        pending = (
            (0, 0, 0),
            Position(35, 119),
            Position(34, 118),
            10.0,
        )

        self.assertFalse(
            _chest_movement_response_pending(
                pending, self._snapshot(Position(34, 118)), 10.1
            )
        )

    def test_unrelated_stale_move_does_not_acknowledge_current_command(self):
        pending = (
            (0, 0, 0),
            Position(35, 119),
            Position(35, 118),
            10.0,
        )

        self.assertTrue(
            _chest_movement_response_pending(
                pending, self._snapshot(Position(34, 119)), 10.1
            )
        )

    def test_fundraising_loot_move_waits_for_position_acknowledgement(self):
        self.assertTrue(
            _movement_command_needs_ack("4", "fundraise:seek-loot")
        )

    def test_melee_direction_does_not_wait_for_position_change(self):
        self.assertFalse(_movement_command_needs_ack("4", "melee"))


class LoopDetectionTest(unittest.TestCase):
    FLOOR = (2, 1, 0)

    def test_flags_a_two_tile_oscillation(self):
        # The live failure: bouncing between exactly two tiles on one floor.
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertTrue(_is_looping(cells))

    def test_flags_live_six_cell_random_quest_cycle(self):
        from collections import deque

        cycle = (
            (3, 26), (4, 26), (3, 27),
            (4, 28), (5, 28), (5, 27),
        )
        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            y, x = cycle[i % len(cycle)]
            cells.append((self.FLOOR, y, x))

        self.assertTrue(_is_looping(cells))

    def test_ignores_a_healthy_sweep(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 10, 10 + i))  # marching down a corridor
        self.assertFalse(_is_looping(cells))

    def test_does_not_flag_before_the_window_fills(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW - 1):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertFalse(_is_looping(cells))

    def test_multiplier_combat_uses_a_larger_finite_window(self):
        from collections import deque

        cells = deque(maxlen=MULTIPLIER_COMBAT_LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertFalse(
            _is_looping(cells, window=MULTIPLIER_COMBAT_LOOP_WINDOW)
        )

        for i in range(LOOP_WINDOW, MULTIPLIER_COMBAT_LOOP_WINDOW):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertTrue(
            _is_looping(cells, window=MULTIPLIER_COMBAT_LOOP_WINDOW)
        )

    def test_floor_change_resets_the_signal(self):
        # Confined tiles but spread across two floors is descent, not a loop.
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            floor = (2, 1, 0) if i < LOOP_WINDOW // 2 else (2, 2, 0)
            cells.append((floor, 15, 43))
        self.assertFalse(_is_looping(cells))

    def test_flags_a_two_floor_stair_ping_pong(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            if i % 2:
                cells.append(((2, 10, 0), 7, 16))
            else:
                cells.append(((2, 9, 0), 13, 54))
        self.assertTrue(_is_looping(cells))


class DeduplicateConsecutiveTest(unittest.TestCase):
    def test_drops_only_consecutive_duplicate_snapshots(self):
        lines = ["first\n", "first\n", "second\n", "first\n"]

        self.assertEqual(
            list(_deduplicate_consecutive(lines)),
            ["first\n", "second\n", "first\n"],
        )


class CompleteLineTest(unittest.TestCase):
    def test_buffers_an_incomplete_line(self):
        complete, pending = _split_complete_lines('first\n{"turn":')
        self.assertEqual(complete, ["first\n"])
        self.assertEqual(pending, '{"turn":')

        complete, pending = _split_complete_lines(pending + "1}\n")
        self.assertEqual(complete, ['{"turn":1}\n'])
        self.assertEqual(pending, "")

    def test_once_ignores_an_incomplete_trailing_line(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.jsonl"
            path.write_text('{"turn":1}\n{"turn":', encoding="utf-8")

            self.assertEqual(list(_read_last_line(path)), ['{"turn":1}'])


class RolloverTest(unittest.TestCase):
    def test_rewinds_an_open_reader_after_emitter_truncation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.jsonl"
            path.write_text("old snapshot\n" * 20, encoding="utf-8")

            with path.open("r", encoding="utf-8") as stream:
                stream.seek(0, 2)
                path.write_text("new snapshot\n", encoding="utf-8")

                self.assertTrue(_rewind_if_truncated(stream, path))
                self.assertEqual(stream.read(), "new snapshot\n")


class StallRecoveryTest(unittest.TestCase):
    def test_level_29_stall_recovery_escapes_stat_prompt_outside_store(self):
        self.assertEqual(_stall_recovery_key(0, 29, False), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(1, 29, False), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(2, 29, False), ("a", "<level-stat:a>"))
        self.assertEqual(_stall_recovery_key(3, 29, False), ("y", "<level-stat:y>"))

    def test_level_29_store_stall_never_affirms_default_y(self):
        safe_default_y_answers = {"\x1b", "n", "N"}
        for nudge_streak in range(8):
            key, _marker = _stall_recovery_key(nudge_streak, 29, True)
            self.assertIn(key, safe_default_y_answers)

    def test_floor_transition_clears_arrival_prompt_exactly_on_change(self):
        town = (0, 0, 0)
        yeek_one = (2, 1, 0)

        self.assertFalse(_floor_transition_needs_prompt_clear(None, town))
        self.assertFalse(_floor_transition_needs_prompt_clear(town, town))
        self.assertTrue(_floor_transition_needs_prompt_clear(town, yeek_one))
        self.assertTrue(_floor_transition_needs_prompt_clear(yeek_one, town))

    def test_command_response_grace_is_reserved_for_native_travel(self):
        self.assertGreater(COMMAND_RESPONSE_GRACE, 9.0)
        self.assertLess(COMMAND_RESPONSE_GRACE, REST_STALL_GRACE)
        self.assertEqual(
            _command_response_grace("\x1b`n!.", "shop:travel"),
            COMMAND_RESPONSE_GRACE / TOWN_TRAVEL_STALL_LIMIT,
        )
        self.assertEqual(
            _command_response_grace("\x1b`n>.", "town:travel-entrance"),
            COMMAND_RESPONSE_GRACE,
        )
        self.assertEqual(_command_response_grace("dj\r", "home:deposit"), 0.0)
        self.assertEqual(
            _command_response_grace("5  pc\x1b", "home:atomic-withdraw"), 0.0
        )

    def test_partial_snapshot_bytes_refresh_emitter_activity(self):
        self.assertEqual(
            _last_activity_after_read(10.0, 20.0, '{"turn":'),
            20.0,
        )
        self.assertEqual(_last_activity_after_read(10.0, 20.0, ""), 10.0)

    def test_counts_repeated_command_with_no_state_progress(self):
        signature = ((2, 1, 0), 100, 10, 20, "fundraise:mine-treasure", "T3")
        count = 0
        for _ in range(STALLED_COMMAND_STATE_LIMIT):
            count = _advance_stalled_command_count(
                count,
                signature=signature,
                previous_signature=signature,
            )
        self.assertEqual(count, STALLED_COMMAND_STATE_LIMIT)

    def test_stalled_snapshot_count_resets_on_real_progress(self):
        self.assertEqual(
            _advance_stalled_command_count(
                2,
                signature=("new",),
                previous_signature=("old",),
            ),
            0,
        )

    def test_tunnel_macro_waits_for_direction_prompt(self):
        self.assertEqual(_delay_after_macro_key("T3", 0), TUNNEL_PROMPT_DELAY_SECONDS)
        self.assertEqual(_delay_after_macro_key("T3", 1), 0.0)
        self.assertEqual(_delay_after_macro_key("rb", 0), MULTI_KEY_DELAY_SECONDS)

    def test_travel_fallback_waits_for_each_selector_redraw(self):
        key = "\x1b`n%."
        self.assertEqual(_delay_after_macro_key(key, 0), MULTI_KEY_DELAY_SECONDS)
        for index in (1, 2, 3):
            self.assertEqual(
                _delay_after_macro_key(key, index), TRAVEL_PROMPT_DELAY_SECONDS
            )
        self.assertEqual(_delay_after_macro_key(key, 4), 0.0)

    def test_loaded_tunnel_macro_replaces_each_direction_with_one_character(self):
        for direction, trigger in TUNNEL_MACRO_TRIGGERS.items():
            self.assertEqual(_transport_key(f"T{direction}", True), trigger)
            self.assertEqual(len(_transport_key(f"T{direction}", True)), 1)
        self.assertEqual(_transport_key("T1", True), "\x19")
        self.assertEqual(_transport_key("T5", True), "T5")
        self.assertEqual(_transport_key("T3", False), "T3")
        self.assertEqual(_transport_key("qf", True), "qf")

    def test_loaded_travel_macro_replaces_each_destination_with_one_character(self):
        for macro, trigger in TRAVEL_MACRO_TRIGGERS.items():
            self.assertEqual(_transport_key(macro, True), trigger)
            self.assertEqual(len(_transport_key(macro, True)), 1)
        self.assertEqual(_transport_key("\x1b`n(.", True), "\x15")
        self.assertEqual(_transport_key("\x1b`n%.", False), "\x1b`n%.")

    def test_tunnel_macros_require_pref_loaded_before_this_game_started(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            edit = root / "lib" / "edit"
            user = root / "lib" / "user"
            logs = root / "logs"
            edit.mkdir(parents=True)
            user.mkdir(parents=True)
            logs.mkdir()
            monrace = edit / "MonraceDefinitions.jsonc"
            monrace.write_text("{}", encoding="ascii")
            pref = user / "bot-test.prf"
            pref.write_text(
                "# HENGBOT_INPUT_MACROS_V4\n"
                "A:T1\nP:^Y\nA:T2\nP:^B\nA:T3\nP:^C\nA:T4\nP:^D\n"
                "A:T6\nP:^E\nA:T7\nP:^F\nA:T8\nP:^G\nA:T9\nP:^H\n"
                "A:\\e`n!.\nP:^K\nA:\\e`n\".\nP:^L\nA:\\e`n#.\nP:^N\n"
                "A:\\e`n$.\nP:^O\nA:\\e`n%.\nP:^P\nA:\\e`n&.\nP:^Q\n"
                "A:\\e`n'.\nP:^R\nA:\\e`n(.\nP:^U\nA:\\e`n>.\nP:^T\n"
                # The fast input cadence is only valid while the game stops
                # discarding queued keys, so the pref must disable it.
                "X:flush_failure\n"
                "X:command_menu\n",
                encoding="ascii",
            )
            self.assertTrue(_valid_bot_play_macro_pref(pref))
            valid_pref = pref.read_text(encoding="ascii")
            pref.write_text(
                valid_pref.replace("A:\\e`n(.\nP:^U", "A:\\e`n(.\nP:^S"),
                encoding="ascii",
            )
            self.assertFalse(_valid_bot_play_macro_pref(pref))
            pref.write_text(valid_pref, encoding="ascii")
            pref.write_text(
                valid_pref.replace("X:command_menu\n", ""), encoding="ascii"
            )
            self.assertFalse(_valid_bot_play_macro_pref(pref))
            pref.write_text(valid_pref, encoding="ascii")
            pid_file = logs / "hengband.pid"
            pid_file.write_text("1234", encoding="ascii")
            state_file = logs / "state.jsonl"
            self.assertTrue(_bot_play_macros_ready(state_file, monrace, 1234))
            self.assertFalse(_bot_play_macros_ready(state_file, monrace, 4321))

            newer = pid_file.stat().st_mtime_ns + 1_000_000_000
            os.utime(pref, ns=(newer, newer))
            self.assertFalse(_bot_play_macros_ready(state_file, monrace, 1234))

    def test_incomplete_tunnel_macro_pref_is_rejected(self):
        with TemporaryDirectory() as temp:
            pref = Path(temp) / "bot-test.prf"
            pref.write_text(
                "# HENGBOT_INPUT_MACROS_V4\nA:T1\nP:^Y\n",
                encoding="ascii",
            )
            self.assertFalse(_valid_bot_play_macro_pref(pref))

    def test_store_transaction_macros_have_no_inter_key_delay(self):
        for macro in ("dk\r", "dj99\ry", "pf10\r\r", "{x@0\r{y@1\r"):
            for index in range(len(macro)):
                self.assertEqual(
                    _delay_after_macro_key(macro, index, in_store=True),
                    0.0,
                )
        self.assertEqual(
            _delay_after_macro_key("ga\r", 0),
            STORE_ITEM_PROMPT_DELAY_SECONDS,
        )

    def test_store_delay_exemption_does_not_cover_dungeon_drop(self):
        self.assertEqual(
            _delay_after_macro_key("dk", 0),
            STORE_ITEM_PROMPT_DELAY_SECONDS,
        )

    def test_answers_the_level_ten_stat_prompt_after_escape_nudges(self):
        self.assertEqual(_stall_recovery_key(0, 9, False), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(1, 9, False), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(2, 9, False), ("a", "<level-stat:a>"))
        self.assertEqual(_stall_recovery_key(3, 9, False), ("y", "<level-stat:y>"))

    def test_keeps_retrying_the_stat_answers_if_a_key_was_lost(self):
        self.assertEqual(_stall_recovery_key(4, 9, False), ("a", "<level-stat:a>"))
        self.assertEqual(_stall_recovery_key(5, 9, False), ("y", "<level-stat:y>"))

    def test_covers_a_two_level_jump_over_the_stat_threshold(self):
        # One out-of-depth kill can jump 8→10; the last snapshot still says
        # clvl 8, and the stat screen is up all the same.
        self.assertEqual(_stall_recovery_key(2, 8, False), ("a", "<level-stat:a>"))
        self.assertEqual(_stall_recovery_key(3, 18, False), ("y", "<level-stat:y>"))

    def test_does_not_send_stat_answers_at_other_levels(self):
        self.assertEqual(_stall_recovery_key(2, 7, False), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(3, 10, False), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(2, None, False), ("\x1b", "<esc>"))


class StationaryReasonsTest(unittest.TestCase):
    def test_stationary_exemption_depends_on_observed_position(self):
        before = parse_snapshot(json.loads(_snap_line(1, 13, 104)), {})
        after_move = parse_snapshot(json.loads(_snap_line(1, 13, 105)), {})

        self.assertTrue(
            _cell_loop_guard_applies(
                after_move, "melee:choke", before.player.position
            )
        )
        self.assertFalse(
            _cell_loop_guard_applies(
                before, "melee", before.player.position
            )
        )

    def test_only_registered_budgeted_escape_waits_are_exempt(self):
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        for reason in ESCAPE_BUDGETED_WAIT_LIMITS:
            with self.subTest(reason=reason):
                self.assertIn(reason, STATIONARY_EXEMPT_REASONS)
                self.assertFalse(_cell_loop_guard_applies(dungeon, reason))

        for reason in (
            "combat:disengage-step",
            "return:wander",
            "emergency:seek-upstairs",
            "flee",
            "status-threat:retreat",
        ):
            with self.subTest(reason=reason):
                self.assertNotIn(reason, STATIONARY_EXEMPT_REASONS)
                self.assertTrue(_cell_loop_guard_applies(dungeon, reason))

    def test_escape_ladder_telemetry_is_written_to_decision_record(self):
        snapshot = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})
        telemetry = {
            "ladder": "return",
            "rung": "return:wait",
            "budget_remaining": 17,
            "reason": "return:wait",
        }

        record = _decision_record(
            snapshot, "5", "return:wait", escape_ladder=telemetry
        )

        self.assertEqual(record["escape_ladder"], telemetry)

    def test_choke_engagement_telemetry_is_written_to_decision_record(self):
        snapshot = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})
        telemetry = {
            "phase": "hold",
            "destination": {"y": 27, "x": 170},
            "trigger_hostiles": [
                {"index": 106, "last_seen": {"y": 30, "x": 168}}
            ],
            "release_cause": None,
        }

        record = _decision_record(
            snapshot, "5", "melee:choke-hold", choke_engagement=telemetry
        )

        self.assertEqual(record["choke_engagement"], telemetry)

    def test_town_uses_policy_cycle_guard_instead_of_cell_guard(self):
        town = parse_snapshot(
            json.loads(_snap_line(1, 10, 10).replace('"level": 1', '"level": 0')),
            {},
        )
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        self.assertFalse(_cell_loop_guard_applies(town, "shop:approach"))
        self.assertTrue(_cell_loop_guard_applies(dungeon, "explore"))

    def test_recall_waits_are_exempt_from_loop_detection(self):
        # Waiting out a Word of Recall countdown pins the player on one tile for
        # ~15-35 turns; if those decisions fed the detector they could stop the
        # bot mid-return. They must be exempt, alongside search and in-place melee.
        dungeon = parse_snapshot(json.loads(_snap_line(13, 9, 114)), {})
        self.assertIn("return:wait-recall", STATIONARY_REASONS)
        # Deep-fundraising uses its own reason for the same bounded recall
        # countdown. The 01:45 live run waited safely for 32 turns and was
        # otherwise misclassified as a confined six-cell exploration loop.
        self.assertIn("fundraise:wait-recall", STATIONARY_REASONS)
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "fundraise:wait-recall")
        )
        self.assertIn("town:wait-recall", STATIONARY_REASONS)
        self.assertIn("town:wait-restock", STATIONARY_REASONS)
        self.assertIn("search", STATIONARY_REASONS)
        self.assertIn("melee", STATIONARY_REASONS)
        # A breeder-containment disengage reads Recall and then waits it out on
        # one tile; the 2026-07-24 Galgals louse escape re-tripped the guard on
        # this wait because it was the only *:wait-recall reason left unexempt.
        self.assertIn("combat:disengage-wait-recall", STATIONARY_REASONS)
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "combat:disengage-wait-recall")
        )

    def test_fundraise_clear_escape_path_is_exempt_only_while_stationary(self):
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        self.assertIn("fundraise:clear-escape-path", STATIONARY_REASONS)
        self.assertFalse(
            _cell_loop_guard_applies(
                dungeon,
                "fundraise:clear-escape-path",
                previous_position=dungeon.player.position,
            )
        )
        self.assertTrue(
            _cell_loop_guard_applies(
                dungeon,
                "fundraise:clear-escape-path",
                previous_position=Position(10, 9),
            )
        )

    def test_bounded_return_wall_search_is_exempt_but_walking_is_guarded(self):
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        # The policy searches each candidate wall only SEARCH_LIMIT times.  Five
        # such holds used to fill the generic 40-decision cell window exactly
        # and stop a legitimate hidden-upstairs sweep before it could finish.
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "return:search-upstairs")
        )
        self.assertTrue(
            _cell_loop_guard_applies(dungeon, "return:seek-secret-wall")
        )

    def test_disengage_wall_search_holds_do_not_feed_the_loop_guard(self):
        from collections import deque

        recent_cells = deque(maxlen=LOOP_WINDOW)
        search_reason = "combat:disengage-search-upstairs"
        walk_reason = "combat:disengage-seek-secret-wall"
        cells = ((42, 33), (42, 34), (43, 31), (43, 32), (44, 32))

        for index, (y, x) in enumerate(cells):
            dungeon = parse_snapshot(json.loads(_snap_line(1, y, x)), {})
            for _ in range(8):
                if _cell_loop_guard_applies(dungeon, search_reason):
                    recent_cells.append((dungeon.floor_key, y, x))
                else:
                    recent_cells.clear()
                self.assertFalse(_is_looping(recent_cells))
            if index + 1 < len(cells):
                self.assertTrue(_cell_loop_guard_applies(dungeon, walk_reason))
                recent_cells.append((dungeon.floor_key, y, x))
                self.assertFalse(_is_looping(recent_cells))

    def test_mining_digs_are_exempt_from_loop_detection(self):
        # Digging breaks rock while standing on ONE tile for many turns, which the
        # position-based loop guard would read as a confined oscillation. Mining digs
        # must be exempt (the policy's MINING_STALL_LIMIT leash bounds them instead), so
        # a long tunnel-to-a-vein or dig-out is never mistaken for a stuck loop.
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})
        self.assertIn("fundraise:dig-to-treasure", STATIONARY_EXEMPT_REASONS)
        self.assertIn("fundraise:mine-treasure", STATIONARY_EXEMPT_REASONS)
        self.assertIn("fundraise:tunnel-out", STATIONARY_EXEMPT_REASONS)
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "fundraise:dig-to-treasure")
        )
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "fundraise:mine-treasure")
        )
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "breakout:dig-to-stairs")
        )
        # Walking reasons stay guardable — only in-place digging is exempt. The
        # two-phase design never tunnels toward far veins, so the old
        # tunnel-to-treasure reason no longer exists at all.
        self.assertNotIn("fundraise:seek-treasure", STATIONARY_EXEMPT_REASONS)
        self.assertTrue(
            _cell_loop_guard_applies(dungeon, "fundraise:seek-treasure")
        )
        self.assertTrue(_cell_loop_guard_applies(dungeon, "explore"))

    def test_unseen_choke_wait_is_exempt_for_full_sixty_decisions(self):
        from collections import deque

        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})
        recent_cells = deque(maxlen=LOOP_WINDOW)
        self.assertIn("unseen:choke-wait", STATIONARY_EXEMPT_REASONS)
        for _ in range(60):
            if _cell_loop_guard_applies(dungeon, "unseen:choke-wait"):
                recent_cells.append((dungeon.floor_key, 10, 10))
            else:
                recent_cells.clear()
            self.assertFalse(_is_looping(recent_cells))

    def test_fixed_quest_hold_is_exempt_from_loop_detection(self):
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        self.assertIn("quest-strategy:hold", STATIONARY_EXEMPT_REASONS)
        self.assertFalse(_cell_loop_guard_applies(dungeon, "quest-strategy:hold"))
        # Failed positioning can repeat for a real strategy defect, so only the
        # intentional at-post hold is exempt from the outer circuit breaker.
        self.assertTrue(
            _cell_loop_guard_applies(dungeon, "quest-strategy:hold-unreachable")
        )
        self.assertTrue(
            _cell_loop_guard_applies(dungeon, "quest-strategy:avoid-never-move")
        )

    def test_fixed_quest_combat_is_exempt_but_routing_is_guarded(self):
        # Q22 can require an entire wave to be fought from one defensive post.
        # Those attacks make game progress even though position does not change.
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "quest-strategy:melee")
        )
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "quest-strategy:ranged-fire")
        )
        self.assertTrue(
            _cell_loop_guard_applies(dungeon, "quest-strategy:position")
        )

    def test_fundraising_multiplier_combat_uses_grace_reason(self):
        self.assertTrue(
            _uses_multiplier_combat_grace("fundraise:eliminate-multiplier")
        )
        self.assertFalse(_uses_multiplier_combat_grace("fundraise:clear-hostile"))
        self.assertFalse(_uses_multiplier_combat_grace("fundraise:sweep-explore"))
        self.assertNotIn("fundraise:tunnel-to-treasure", STATIONARY_EXEMPT_REASONS)


if __name__ == "__main__":
    unittest.main()


class GameProcessAliveTest(unittest.TestCase):
    """The bot concluded <dead> (and exited) on ANY 8-nudge snapshot silence —
    twice abandoning a healthy full-HP character stuck at a store prompt chain.
    Death is only concluded when the game PROCESS is actually gone."""

    def test_running_process_reads_alive(self):
        import os

        self.assertTrue(_game_process_alive(os.getpid()))

    def test_exited_process_reads_dead(self):
        import subprocess
        import sys

        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        self.assertFalse(_game_process_alive(proc.pid))

    def test_unknown_pid_reads_dead(self):
        self.assertFalse(_game_process_alive(None))


class TownBlockedStreakTest(unittest.TestCase):
    """A latched town block waits in place; when it waits on a store door, the
    interleaved store snapshots reset the cell loop guard, so the visible stop
    never fired. The streak counter stops the bot regardless."""

    def test_blocked_decisions_accumulate_through_store_leaves(self):
        from hengbot.cli import _advance_town_blocked_streak

        streak = 0
        for reason in (
            "town:blocked:no-safe-recall-destination",
            "shop:leave",
            "town:blocked:no-safe-recall-destination",
            "town:blocked:no-safe-recall-destination",
        ):
            streak = _advance_town_blocked_streak(streak, reason)
        self.assertEqual(streak, 3)

    def test_no_progress_filler_preserves_the_streak(self):
        from hengbot.cli import _advance_town_blocked_streak

        streak = _advance_town_blocked_streak(
            5, "town:wait-restock:temple"
        )
        self.assertEqual(streak, 6)

    def test_observed_durable_progress_resets_the_streak(self):
        from hengbot.cli import _advance_town_blocked_streak

        streak = _advance_town_blocked_streak(
            5, "town:wait-restock:temple", durable_progress=True
        )
        self.assertEqual(streak, 0)

    def test_dungeon_decisions_clear_and_never_advance_town_streak(self):
        from hengbot.cli import _advance_town_blocked_streak

        streak = _advance_town_blocked_streak(
            1, "explore", in_town=False, floor_changed=True
        )
        for _ in range(40):
            streak = _advance_town_blocked_streak(
                streak, "explore", in_town=False
            )
        self.assertEqual(streak, 0)

    def test_floor_change_clears_town_streak(self):
        from hengbot.cli import _advance_town_blocked_streak

        self.assertEqual(
            _advance_town_blocked_streak(
                12, "town:blocked:repetition", floor_changed=True
            ),
            0,
        )

    def test_live_wiring_uses_authoritative_town_flag(self):
        from hengbot.cli import TOWN_BLOCKED_STOP_LIMIT
        from hengbot.model import PlayerState, Snapshot
        from hengbot.policy import HengbotPolicy

        policy = HengbotPolicy()
        policy.last_reason = "town:blocked:no-safe-recall-destination"
        wilderness = Snapshot(
            player=PlayerState(
                position=Position(10, 10), hp=10, max_hp=10,
                mp=0, max_mp=0, level=1,
            ),
            grids={},
            visible_monsters=[],
            floor_key=(0, 0, 0),
            town_flag=False,
        )
        town = replace(wilderness, town_flag=True)

        streak = TOWN_BLOCKED_STOP_LIMIT - 1
        state = None
        for _ in range(2):
            streak, state = _advance_town_blocked_iteration(
                policy, wilderness, streak, state
            )
        self.assertEqual(streak, 0)

        for _ in range(TOWN_BLOCKED_STOP_LIMIT):
            streak, state = _advance_town_blocked_iteration(
                policy, town, streak, state
            )
        self.assertEqual(streak, TOWN_BLOCKED_STOP_LIMIT)

    def test_live_wiring_ignores_message_churn(self):
        """Board text is not workflow progress at the live seam.

        The seam must project workflow state, not the message-bearing effect
        state: the bot's own periodic character export and wall bumps churn
        `messages` every few decisions, and treating that as progress resets
        the fuse forever (measured live: max streak 24/30, never fired).
        """
        from hengbot.cli import TOWN_BLOCKED_STOP_LIMIT
        from hengbot.model import PlayerState, Snapshot
        from hengbot.policy import HengbotPolicy

        policy = HengbotPolicy()
        policy.last_reason = "town:blocked:no-safe-recall-destination"
        quiet = Snapshot(
            player=PlayerState(
                position=Position(10, 10), hp=10, max_hp=10,
                mp=0, max_mp=0, level=1,
            ),
            grids={},
            visible_monsters=[],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        noisy = replace(quiet, messages=("キャラクタ情報のファイルへの書き出しに成功しました。",))

        streak = 0
        state = None
        for index in range(TOWN_BLOCKED_STOP_LIMIT):
            snapshot = noisy if index % 2 else quiet
            streak, state = _advance_town_blocked_iteration(
                policy, snapshot, streak, state
            )
        self.assertEqual(streak, TOWN_BLOCKED_STOP_LIMIT)

    def test_live_wiring_real_gold_progress_never_fuses(self):
        from hengbot.cli import TOWN_BLOCKED_STOP_LIMIT
        from hengbot.model import PlayerState, Snapshot
        from hengbot.policy import HengbotPolicy

        policy = HengbotPolicy()
        policy.last_reason = "town:blocked:no-safe-recall-destination"
        snapshot = Snapshot(
            player=PlayerState(
                position=Position(10, 10), hp=10, max_hp=10,
                mp=0, max_mp=0, level=1, gold=100,
            ),
            grids={},
            visible_monsters=[],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        streak = 0
        state = None
        for decision in range(TOWN_BLOCKED_STOP_LIMIT + 5):
            current = replace(
                snapshot, player=replace(snapshot.player, gold=100 + decision)
            )
            streak, state = _advance_town_blocked_iteration(
                policy, current, streak, state
            )
        self.assertEqual(streak, 1)

    def test_real_wander_capture_fuses_when_messages_are_not_progress(self):
        from hengbot.cli import (
            TOWN_BLOCKED_STOP_LIMIT,
            _advance_town_blocked_streak,
        )
        from hengbot.policy import HengbotPolicy

        quiet = SimpleNamespace(
            store=None,
            messages=(),
            inventory=(),
            equipment=(),
            player=SimpleNamespace(gold=6289),
        )
        noisy = SimpleNamespace(**{
            **vars(quiet),
            "messages": ("character dump complete",),
        })
        self.assertEqual(
            HengbotPolicy._town_workflow_progress_state(quiet),
            HengbotPolicy._town_workflow_progress_state(noisy),
        )

        fixture_path = (
            Path(__file__).parent
            / "fixtures"
            / "evidence-identify-staff-wander.jsonl"
        )
        rows = [
            json.loads(line)
            for line in fixture_path.read_text(encoding="utf-8").splitlines()
        ]
        decisions = [
            row for row in rows if row.get("decision_sequence") is not None
        ]

        def captured_snapshot(row):
            player = row.get("player") or {}
            inventory = tuple(
                SimpleNamespace(name=name, count=value)
                for name, value in sorted((row.get("inventory") or {}).items())
            )
            store_type = row.get("store_type")
            store = None if store_type is None else SimpleNamespace(
                store_type=store_type, stock_num=None, page_top=None, items=()
            )
            return SimpleNamespace(
                store=store,
                messages=tuple(row.get("messages") or ()),
                inventory=inventory,
                equipment=(),
                player=SimpleNamespace(gold=player.get("gold")),
            )

        legacy_streak = legacy_max = 0
        legacy_previous = None
        legacy_fuse = None
        for index, row in enumerate(decisions):
            current = HengbotPolicy._town_observable_effect_state(
                captured_snapshot(row)
            )
            changed = legacy_previous is not None and current != legacy_previous
            legacy_previous = current
            legacy_streak = _advance_town_blocked_streak(
                legacy_streak, f"town:blocked:{row['reason']}",
                durable_progress=changed,
            )
            legacy_max = max(legacy_max, legacy_streak)
            if legacy_streak >= TOWN_BLOCKED_STOP_LIMIT:
                legacy_fuse = index
                break

        self.assertEqual(len(decisions), 98)
        self.assertEqual((legacy_max, legacy_fuse), (24, None))

        streak = 0
        previous = None
        fused_at = None
        for index, row in enumerate(decisions):
            current = HengbotPolicy._town_workflow_progress_state(
                captured_snapshot(row)
            )
            changed = previous is not None and current != previous
            previous = current
            streak = _advance_town_blocked_streak(
                streak, f"town:blocked:{row['reason']}",
                in_town=True, durable_progress=changed,
            )
            if streak >= TOWN_BLOCKED_STOP_LIMIT:
                fused_at = index
                break

        self.assertIsNotNone(fused_at)
        self.assertLess(fused_at, len(decisions))

    def test_rederived_block_reasons_reach_the_fuse_through_fillers(self):
        from hengbot.cli import (
            TOWN_BLOCKED_STOP_LIMIT,
            _advance_town_blocked_streak,
        )

        reasons = (
            "restocked-recall-store-unreachable",
            "dominated-item-destroy-failed",
            "departure-no-light",
            "digging-tool-lost",
            "equipment-home-unavailable",
            "equipment-departure-incomplete",
        )
        for reason in reasons:
            with self.subTest(reason=reason):
                streak = 0
                for decision in range(TOWN_BLOCKED_STOP_LIMIT):
                    emitted_reason = (
                        f"town:blocked:{reason}"
                        if decision % 2 == 0
                        else "town:wait-restock:temple"
                    )
                    streak = _advance_town_blocked_streak(
                        streak, emitted_reason
                    )
                self.assertEqual(streak, TOWN_BLOCKED_STOP_LIMIT)

    def test_measured_nonwait_repetition_shape_reaches_fuse_with_report(self):
        from hengbot.cli import (
            TOWN_BLOCKED_STOP_LIMIT,
            _advance_town_blocked_streak,
            _stopping_town_stall_report,
        )

        snapshot = DecisionRecordTest._town_snapshot()
        policy = DecisionRecordTest._town_stall_policy(passes=1)
        policy.last_reason = "town:blocked:repetition"
        streak = 0
        measured_keys = ("\x1b", "7", "7")
        for decision in range(TOWN_BLOCKED_STOP_LIMIT):
            streak = _advance_town_blocked_streak(
                streak,
                policy.last_reason,
                key=measured_keys[decision % len(measured_keys)],
            )

        report = _stopping_town_stall_report(
            snapshot, policy, TOWN_BLOCKED_STOP_LIMIT, streak
        )
        record = _decision_record(
            snapshot,
            measured_keys[-1],
            policy.last_reason,
            town_stall_report=report,
        )
        self.assertEqual(streak, TOWN_BLOCKED_STOP_LIMIT)
        self.assertIn("town_stall_report", record)

    def test_wait_repetition_spends_registered_budget_and_reports_terminal(self):
        from hengbot.cli import (
            _advance_town_blocked_streak,
            _stopping_town_stall_report,
        )
        from hengbot.policy import HengbotPolicy, WAIT_KEY

        snapshot = DecisionRecordTest._town_snapshot()
        policy = HengbotPolicy()
        streak = 0
        limit = ESCAPE_BUDGETED_WAIT_LIMITS["town:blocked:repetition"]
        for _ in range(limit):
            policy.last_reason = "town:blocked:repetition"
            key = policy._bound_escape_wait(snapshot, WAIT_KEY)
            streak = _advance_town_blocked_streak(
                streak, "town:blocked:repetition", key=key
            )

        report = _stopping_town_stall_report(snapshot, policy, limit, streak)
        record = _decision_record(
            snapshot,
            key,
            policy.last_reason,
            town_stall_report=report,
        )
        self.assertEqual(streak, 0)
        self.assertEqual(policy.last_reason, "livelock:exhausted")
        self.assertIn("town_stall_report", record)


class TownResidenceStreakTest(unittest.TestCase):
    def test_counts_town_residence_and_resets_on_every_floor_change(self):
        from hengbot.cli import _advance_town_residence_streak

        town = (0, 0, 0)
        other_town_key = (0, 0, 1)
        dungeon = (1, 1, 0)
        streak = _advance_town_residence_streak(0, None, town)
        streak = _advance_town_residence_streak(streak, town, town)
        self.assertEqual(streak, 2)
        streak = _advance_town_residence_streak(streak, town, other_town_key)
        self.assertEqual(streak, 1)
        streak = _advance_town_residence_streak(streak, other_town_key, dungeon)
        self.assertEqual(streak, 0)
        streak = _advance_town_residence_streak(streak, dungeon, town)
        self.assertEqual(streak, 1)


class CharacterSnapshotDispatchTest(unittest.TestCase):
    """`C` character snapshots reach the policy through the dispatcher."""

    def test_naked_capture_characteristics_are_recorded_only_when_latched(self):
        from hengbot.cli import _dispatch_response_lines
        from hengbot.policy import HengbotPolicy

        policy = HengbotPolicy()
        policy._calibration_phase = "capture"
        policy._calibration_naked_dump_requested = True
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._calibration_naked_dump_inflight = True
        sent = []
        line = json.dumps({
            "type": "character",
            "character": {
                "mutations": [7],
                "characteristics": [
                    {"flag_id": 152, "player": False, "vulnerability": True},
                ],
            },
        })

        _dispatch_response_lines([line], policy, sent.append)

        self.assertEqual(policy._mutation_signature, (7,))
        self.assertEqual(policy._calibration_naked_flags, frozenset({152}))
        self.assertFalse(policy._calibration_naked_dump_inflight)
