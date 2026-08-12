from __future__ import annotations

import gzip
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.cli import _rewind_if_truncated
from hengbot.flight_recorder import (
    FlightRecorder,
    append_session_marker,
    policy_state,
    render_remembered_map,
    safe_filename_component,
)
from hengbot.model import Position


class FlightRecorderTest(unittest.TestCase):
    def test_diagnostic_filename_components_are_windows_safe(self):
        component = safe_filename_component(
            'posting-contract:bad<name>"/\\|?*\x00. '
        )
        self.assertTrue(component.startswith("posting-contract-bad-name"))
        self.assertFalse(any(char in '<>:"/\\|?*' for char in component))
        self.assertFalse(component.endswith((".", " ")))

    def policy(self):
        return SimpleNamespace(
            _remembered_known_t={(1, 1), (1, 2), (2, 2), (3, 3)},
            _remembered_floor_t={(1, 1), (1, 2), (2, 2)},
            _remembered_wall_t={(3, 3)},
            _remembered_door_t={(2, 3)},
            _remembered_rubble_t={(3, 2)},
            _remembered_downstairs={Position(2, 2)},
            _remembered_upstairs={Position(1, 1)},
            _remembered_entrances={Position(4, 1)},
            _visit_counts=Counter({Position(1, 1): 3}),
            _explore_goal_identity=SimpleNamespace(
                kind="frontier", position=Position(2, 3)
            ),
            _explore_path=[Position(1, 2), Position(2, 2)],
            _explore_path_outcome="advancing",
            _nav_ledger=SimpleNamespace(descent_target=Position(2, 2)),
            _escape_state=SimpleNamespace(rung="teleport"),
            _unseen_retreat_target=Position(3, 4),
            _unseen_retreat_direction=(-1, 1),
            _unseen_retreat_floor=(1, 5, 0),
            _unseen_choke_position=Position(2, 3),
            _unseen_wait_remaining=42,
            _unseen_wait_intercepted=False,
            _unseen_attack_evidence="何かに殴られた。",
            _engagement_avoid_cells={Position(4, 4)},
            _probed_frontiers={Position(5, 5)},
            _unenterable_explore_goals={Position(6, 6)},
            _window_edge_goals={Position(7, 7)},
            _descent_target_goal=Position(2, 2),
            _descent_blocked=True,
            _descent_block_countdown=2,
            _descent_refusal_reason="descent-cooldown",
            _fundraising_mode="mine",
            _town_restock_suppressed=False,
            _abandoned_quest_carry_requirements={
                "launcher": "all-suppliers-visited-without-affordable-stock"
            },
            last_reason="explore",
        )

    def snapshot(self):
        return SimpleNamespace(
            turn=123,
            floor_key=(1, 5, 0),
            player=SimpleNamespace(position=Position(1, 2)),
        )

    def test_session_start_appends_and_cli_has_no_truncating_wipe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            path.write_text('{"old":true}\n', encoding="utf-8")
            append_session_marker(
                path,
                ["first"],
                input_delays={
                    "input_key_delay": 0.0,
                    "input_item_prompt_delay": 0.5,
                    "input_tunnel_prompt_delay": 2.0,
                    "input_travel_prompt_delay": 0.5,
                },
            )
            append_session_marker(path, ["second"])
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(lines[0]), {"old": True})
            self.assertEqual(json.loads(lines[-2])["kind"], "session-start")
            self.assertEqual(
                json.loads(lines[-2])["input_delays"]["input_key_delay"],
                0.0,
            )
            self.assertEqual(json.loads(lines[-1])["argv"], ["second"])
        cli_source = (
            Path(__file__).parents[1] / "src" / "hengbot" / "cli.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('decision_log.write_text("", encoding="utf-8")', cli_source)

    def test_snapshot_ring_survives_emitter_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            emitter = root / "emitter.jsonl"
            emitter.write_text("one\ntwo\n", encoding="utf-8")
            recorder = FlightRecorder(root / "jsonlog", root / "incidents")
            with emitter.open("r", encoding="utf-8") as stream:
                recorder.record_snapshot_lines(stream.read().splitlines())
                emitter.write_text("x\n", encoding="utf-8")
                self.assertTrue(_rewind_if_truncated(stream, emitter))
                recorder.record_snapshot_lines(stream.read().splitlines())
            with gzip.open(recorder.snapshot_path, "rt", encoding="utf-8") as file:
                self.assertEqual(file.read().splitlines(), ["one", "two", "x"])

    def test_loop_incident_contains_all_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "jsonlog" / "decisions.jsonl"
            log.parent.mkdir()
            log.write_text('{"reason":"loop-detected"}\n', encoding="utf-8")
            recorder = FlightRecorder(log.parent, root / "incident-captures")
            recorder.record_snapshot_lines(['{"turn":123}'])
            capture = recorder.freeze(
                "loop-detected",
                self.policy(),
                self.snapshot(),
                log,
                ["explore", "loop-detected"],
            )
            self.assertIsNotNone(capture)
            for relative in (
                "decision-tail.jsonl",
                "snapshots",
                "policy-state.json",
                "remembered-map.txt",
                "meta.json",
                "README.md",
            ):
                self.assertTrue((capture / relative).exists(), relative)

    def test_marker_kind_is_sanitized_without_losing_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = FlightRecorder(root / "jsonlog", root / "incidents")
            kind = "posting-contract:identical-repost-unobserved"
            capture = recorder.freeze(
                kind, self.policy(), self.snapshot(), None, ["shop:travel"]
            )
            self.assertIsNotNone(capture)
            self.assertNotIn(":", capture.name)
            meta = json.loads((capture / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["kind"], kind)

    def test_policy_state_retains_commitment_and_downstairs_and_map_renders(self):
        state = json.loads(json.dumps(policy_state(self.policy(), self.snapshot())))
        self.assertEqual(
            state["state"]["_remembered_downstairs"], [[2, 2]]
        )
        self.assertEqual(
            state["state"]["_explore_goal_identity"]["position"], [2, 3]
        )
        self.assertEqual(state["state"]["_unseen_retreat_target"], [3, 4])
        self.assertEqual(state["state"]["_unseen_retreat_direction"], [-1, 1])
        self.assertIn("_shop_selector_diagnostics", state["state"])
        self.assertIn("_identification_source_reservation", state["state"])
        self.assertEqual(state["state"]["_unseen_retreat_floor"], [1, 5, 0])
        self.assertEqual(state["state"]["_unseen_choke_position"], [2, 3])
        self.assertEqual(state["state"]["_unseen_wait_remaining"], 42)
        self.assertEqual(
            state["modes_and_latches"]["_abandoned_quest_carry_requirements"],
            {"launcher": "all-suppliers-visited-without-affordable-stock"},
        )
        self.assertEqual(
            state["state"]["_unseen_attack_evidence"], "何かに殴られた。"
        )
        rendered = render_remembered_map(self.policy(), self.snapshot())
        self.assertIn("@", rendered)
        self.assertIn(">", rendered)
        self.assertIn("#", rendered)
        self.assertIn("E", rendered)

    def test_policy_state_retains_town_blocked_latch_under_historical_name(self):
        class PolicyWithTownBlockedProperty:
            @property
            def _town_blocked_reason(self):
                return self._town_blocked_reason_value

        policy = PolicyWithTownBlockedProperty()
        policy.__dict__.update(vars(self.policy()))
        policy._town_blocked_reason_value = "no-safe-recall-destination"

        state = policy_state(policy, self.snapshot())

        self.assertEqual(
            state["state"]["_town_blocked_reason"],
            "no-safe-recall-destination",
        )

    def test_policy_state_excludes_latch_capture_ring_and_stays_small(self):
        policy = self.policy()
        policy._latch_capture_previous = {
            "predecision_policy_checkpoint_pickle_b64": "x" * 1_000_000,
            "snapshot_pickle_b64": "y" * 500_000,
        }
        policy._latch_capture_assignment = {"caller_chain": ["z" * 10_000]}
        policy._latch_capture_remaining = 2

        encoded = json.dumps(policy_state(policy, self.snapshot()))

        self.assertNotIn("_latch_capture_", encoded)
        self.assertLess(len(encoded), 50_000)

    def test_budget_prunes_oldest_snapshot_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = FlightRecorder(
                root / "jsonlog", root / "incident-captures", budget_bytes=12
            )
            recorder.snapshot_dir.mkdir(parents=True)
            oldest = recorder.snapshot_dir / "snapshots-1.jsonl.gz"
            newest = recorder.snapshot_dir / "snapshots-2.jsonl.gz"
            live = recorder.snapshot_path
            for index, path in enumerate((oldest, newest, live), 1):
                path.write_bytes(b"x" * 8)
                os.utime(path, (index, index))
            incident = recorder.incident_root / "kept"
            incident.mkdir(parents=True)
            (incident / "meta.json").write_bytes(b"x" * 8)
            decision = recorder.root / "decisions.jsonl"
            decision.write_bytes(b"x" * 8)
            recorder.prune_budget()
            self.assertFalse(oldest.exists())
            self.assertTrue(live.exists())
            self.assertTrue(decision.exists())
            self.assertTrue(incident.exists())

    def test_repeated_snapshot_appends_walk_budget_far_less_often(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = FlightRecorder(
                root / "jsonlog",
                root / "incidents",
                budget_bytes=1_000_000,
                snapshot_generation_bytes=1_000_000,
            )
            with patch.object(recorder, "prune_budget") as prune_budget:
                for turn in range(20):
                    recorder.record_snapshot_lines([json.dumps({"turn": turn})])

            self.assertEqual(prune_budget.call_count, 1)

    def test_snapshot_archive_uses_fast_gzip_level(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = FlightRecorder(root / "jsonlog", root / "incidents")

            recorder.record_snapshot_lines(["snapshot payload"])

            # Gzip's XFL byte is 4 for the compressor's fastest level.
            self.assertEqual(recorder.snapshot_path.read_bytes()[8], 4)

    def test_recording_past_budget_prunes_old_rotated_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = FlightRecorder(
                root / "jsonlog",
                root / "incidents",
                budget_bytes=80,
                snapshot_generation_bytes=1,
            )
            recorder.record_snapshot_lines(["first" * 100])
            recorder.record_snapshot_lines(["second" * 100])

            self.assertEqual(
                [
                    path
                    for path in recorder.snapshot_dir.glob("snapshots-*.jsonl.gz")
                    if path != recorder.snapshot_path
                ],
                [],
            )
            self.assertTrue(recorder.snapshot_path.exists())


if __name__ == "__main__":
    unittest.main()
