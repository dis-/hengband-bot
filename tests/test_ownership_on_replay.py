"""Fourth ownership guard: ON decisions over frozen, bounded town windows."""

import tests  # noqa: F401 -- prohibit writes to the live runtime
from dataclasses import asdict
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ownership_on_corpus import FIXTURES, MANIFEST, read_json, run_window, sha256
from ownership_on_replay import replay_window


class OwnershipOnReplayTest(unittest.TestCase):
    def test_recorded_town_windows_have_zero_ownership_violations(self):
        self.assertEqual(sha256(MANIFEST),
                         "abc34d1afba4703989bfefb4acd3c5106546880aa79d11a001dd39724bbbbd02")
        corpus = read_json(MANIFEST)
        self.assertEqual(corpus["format"], 1)
        self.assertTrue(corpus["windows"])
        self.assertEqual(len({window["name"] for window in corpus["windows"]}), len(corpus["windows"]))
        results = []
        for window in corpus["windows"]:
            with self.subTest(window=window["name"]):
                # Only local checkpoint files are needed at test time. Backup
                # hashes are provenance, never a request to reopen the source.
                if "checkpoint_source" in window:
                    name = window["checkpoint_source"]
                    self.assertEqual(sha256(FIXTURES / name), window["sources"][name])
                with TemporaryDirectory(prefix="ownership-on-") as raw:
                    with patch.dict(os.environ, {"HENGBOT_RUNTIME_DIR": raw, "HENGBOT_HOME_HISTORY_DIR": raw}):
                        result = run_window(window, Path(raw))
                results.append(asdict(result))
                self.assertGreater(result.rows_replayed, 0)
                # A longer prefix may become possible after a future fix. The
                # fixture contains only the frozen needed rows; require explicit
                # re-extraction to extend it, never fake later effects.
                self.assertEqual(result.violations, [], json.dumps(asdict(result), ensure_ascii=False))
        destination = os.environ.get("OWNERSHIP_ON_REPLAY_RESULTS")
        if destination:
            Path(destination).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.assertGreater(sum(row["town_rows"] for row in results), 0)

    def test_first_divergence_never_delivers_the_next_board(self):
        policy = SimpleNamespace(last_reason="shop:new", decision_claim={}, choose_key=lambda board: "6")
        def forbidden():
            self.fail("counterfactual historical effect board was delivered")
        decisions = [({"row": 10, "key": "4", "reason": "shop:old"}, lambda: SimpleNamespace(in_town=True)),
                     ({"row": 11, "key": "5", "reason": "shop:later"}, forbidden)]
        result = replay_window("boundary-control", policy, decisions)
        self.assertEqual(result.rows_replayed, 1)
        self.assertEqual(result.matched_rows, 0)
        self.assertEqual(result.first_divergence["row"], 10)

    def test_divergent_terminal_still_fails_the_guard(self):
        policy = SimpleNamespace(last_reason="ownership:item-reserved:test",
                                 decision_claim={}, choose_key=lambda board: None)
        result = replay_window("violation-control", policy, [
            ({"row": 7, "key": "5", "reason": "home:deposit"}, lambda: SimpleNamespace(in_town=True))])
        self.assertEqual({row["kind"] for row in result.violations},
                         {"ownership-terminal", "item-reserved"})
        self.assertTrue(all(row["row"] == 7 for row in result.violations))
        self.assertEqual(result.rows_replayed, 1)

    def test_reason_only_difference_also_ends_the_window(self):
        policy = SimpleNamespace(last_reason="shop:new", decision_claim={}, choose_key=lambda board: "5")
        def forbidden():
            self.fail("a reason-only divergence must also stop the window")
        result = replay_window("reason-control", policy, [
            ({"row": 1, "key": "5", "reason": "shop:old"}, lambda: SimpleNamespace(in_town=True)),
            ({"row": 2, "key": "5", "reason": "shop:later"}, forbidden)])
        self.assertEqual(result.first_divergence["row"], 1)
        self.assertEqual(result.rows_replayed, 1)

if __name__ == "__main__":
    unittest.main()
