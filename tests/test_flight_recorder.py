from __future__ import annotations

import gzip
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from hengbot.cli import _rewind_if_truncated
from hengbot.flight_recorder import (
    FlightRecorder,
    append_session_marker,
    policy_state,
    render_remembered_map,
)
from hengbot.model import Position


class FlightRecorderTest(unittest.TestCase):
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
            _descent_blocked_at_level=10,
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
            append_session_marker(path, ["first"])
            append_session_marker(path, ["second"])
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(lines[0]), {"old": True})
            self.assertEqual(json.loads(lines[-2])["kind"], "session-start")
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


if __name__ == "__main__":
    unittest.main()
