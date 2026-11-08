"""n1-b (Magic-Eater) life-348 2026-11-08: a town stop and a dungeon loop.

Recorded: tests/fixtures/n1b-348-stops-1108/ (tests/extract_n1b_348_stops_1108_fixtures.py),
build bot-206702cc9.  Every decision is the public ``choose_key``; the asserted keys go
through the production executor port.

A, 15:16 town:blocked:owner-retired-burst: the Magic-Eater's spare *Identify* filed a Home
take of 耐電のアミュレット (me_powerful_activation ``_home_take_key``, the catalogue take of
home_identification) on an earlier visit.  The item's name then changed: Home and the
equipment catalogue list 耐電のアミュレット {r電} x9, fully known.  The take stayed filed
(home_identification ``release_stale_take`` kept a take with no other candidate), so the
open Home page handed it off to the entrance (policy.py home:leave-for-pending-withdraw,
``_bound_home_take_signatures``), the entrance found it unobserved and stepped off
(policy_home ``_atomic_home_withdraw_dispatch_key`` home-errand:target-unobserved), the
wait re-entered Home, until the owner-retired burst.  Now a take whose name nothing in the
catalogue or the current Home catalogue carries gives way at once.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import itertools
import json
import lzma
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.home_errand import HomeErrandState
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST)
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-348-stops-1108"
STALE_TAKE = ("耐電のアミュレット", 40, 30)
SHELVED = ("耐電のアミュレット {r電}", 40, 30)


class StaleCatalogueTakeRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        for name in ("runtime-env", "history-env", "runtime"):
            (self.scratch / name).mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)

    def visit(self):
        """The fixture as a town-arrival directory replay_town_arrival reads."""
        source, visit = FIXTURES / "a", self.scratch / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((source / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((source / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        return visit

    def arrival(self):
        """The arrival policy and its journalled boards (as replay_town_arrival.replay)."""
        visit, runtime = self.visit(), self.scratch / "runtime"
        policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if calibration.is_file():
            adopt_calibration(policy, calibration, runtime)
        return policy, decisions(policy, visit, runtime), journal(visit)

    def test_recorded_arrival_carries_a_take_whose_item_was_renamed(self):
        policy, _rows, _journal = self.arrival()
        errand = policy._home_errand
        self.assertEqual(errand.state, HomeErrandState.COMPOSABLE)
        self.assertEqual(errand.request.signature, STALE_TAKE)
        self.assertEqual(errand.request.purpose, "identification-catalog")
        catalogued = {policy._item_signature(owned.item): owned
                      for owned in policy._equipment_catalog.items}
        self.assertNotIn(STALE_TAKE, catalogued)
        self.assertTrue(catalogued[SHELVED].item.fully_known)
        self.assertIn(SHELVED, {policy._item_signature(item)
                                for item in policy._home_knowledge_items})

    def test_the_renamed_take_gives_way_and_no_home_hand_off_holds_it(self):
        policy, rows, entries = self.arrival()
        # Rows 0-2 (travel home, deposit, leave) decide as recorded.
        result = replay_window("n1b-348-a", policy, itertools.islice(rows, 3))
        self.assertEqual((result.matched_rows, result.first_divergence), (3, None))
        recorded, supply = next(rows)
        board = supply()
        key = policy.choose_key(board)
        # Recorded row 3 saved the game with the take still filed; the visit then
        # alternated Home and its entrance for it until the owner-retired burst.
        self.assertEqual(recorded["reason"], "periodic:game-save")
        self.assertFalse(policy._home_errand.active)
        self.assertNotIn(STALE_TAKE, policy._bound_home_take_signatures())
        self.assertFalse(policy.last_reason.startswith(("home:", "home-errand:")), policy.last_reason)
        raw = json.loads(entries[3]["line"] or entries[3]["inputs"][-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)


if __name__ == "__main__":
    unittest.main()
