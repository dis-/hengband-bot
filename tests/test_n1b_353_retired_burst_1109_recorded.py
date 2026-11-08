"""n1-b (Magic-Eater) life-353 2026-11-08 23:20-23:21: three owner-retired bursts in town.

Recorded: tests/fixtures/n1b-353-retired-burst-1109/
(tests/extract_n1b_353_retired_burst_1109_fixtures.py), the town-arrival checkpoint of the
third process (build bot-4454608e3, arrival turn 3827905).  Every decision is the public
``choose_key`` followed by the CLI's own retirement entrance (cli ``_handle_owner_retirement``,
``--owner-retired-log-only`` as the viewing bot runs); the asserted key goes through the
production executor port.

The life recalled from Angband 62F with INT drained to 7 (top 44; stat index 4, so
adj_mag_fail 99): every absorbed power lists 95% fail (row 4's power list).  The town item
processor still identified the three unknown pieces of armour with the absorbed Identify
('mAf' + slot), which answered 「呪文をうまく唱えられなかった！」 every time; no progress, four
casts per identification retirement, three retirements per process and the burst stop, in
all three processes (eleven casts in a row in the last one), five Identify scrolls carried.
The carried Staff of Identify has a floor (STAFF_IDENTIFY_MIN_SUCCESS: below it only a
reliable scroll identifies); the absorbed power that replaces the staff (owner 2026-10-30
「以降、鑑定と財宝感知は取り込みで賄う」) had none.  Now it answers to the same floor
(me_staff_sequence ``identify_power_reliable``).

DECLARED CONSTRUCTED (the continuation after row 20): the journal ends with the live casts,
so the boards after the first scroll read are the recorded row-20 board with each read
landed: the target known (its base values filled in) and the scroll stack one smaller.
DECLARED COUNTERFACTUAL (the control): the recorded row-5 board (the staff list row 4 read)
with INT at its undrained top (44) and the Identify row listed at 5% fail keeps the
absorbed Identify.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import itertools
import gzip
import json
import lzma
import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot import cli, me_capability
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_prompt_gated_decision_key
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.me_staff_sequence import (
    identify_power_available, identify_power_command, identify_power_reliable)
from hengbot.model import SV_STAFF_IDENTIFY, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST)
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_input_executor as executor_pins

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-353-retired-burst-1109"
CAST_ROW = 20
LIST_ROW = 5
SCROLL = (70, 12)          # 鑑定の巻物
BURST = "town:blocked:owner-retired-burst"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)


class AbsorbedIdentifyFloorRecordedTest(executor_pins.ProductionHarness):
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
        visit = self.scratch / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        return visit

    def arrival(self):
        visit, runtime = self.visit(), self.scratch / "runtime"
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path", runtime)
        return policy, decisions(policy, visit, runtime), journal(visit)

    @staticmethod
    def post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def decide(self, policy, board):
        """choose_key, then the CLI's retirement entrance, as the live driver."""
        key = policy.choose_key(board)
        reason = policy.last_reason
        final = cli._handle_owner_retirement(LOG_ONLY, board, key, policy)
        return key, reason, final

    def to_cast_row(self):
        """Rows 0-19 decide as recorded (the CLI forgives row 12's retirement as live)."""
        policy, rows, entries = self.arrival()
        for recorded, supply in rows:
            board = supply()
            if recorded["row"] == CAST_ROW:
                return policy, board, recorded, entries
            key, reason, final = self.decide(policy, board)
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])
            self.assertEqual(final, key, recorded["row"])
            self.post(policy, final)
        self.fail("the journal ends before the cast row")

    @staticmethod
    def unknown(board):
        return sorted(item.slot for item in board.inventory if not item.known and item.is_equipment)

    def test_recorded_drained_int_lists_every_power_at_95_percent(self):
        policy, board, recorded, _entries = self.to_cast_row()
        self.assertEqual((recorded["key"], recorded["reason"]), ("mAfn", "identify:normal"))
        self.assertEqual(board.player.stat_use[1], 7)
        self.assertEqual(board.player.stat_top[1], 44)
        row = me_capability.observed_row(policy, "staff", SV_STAFF_IDENTIFY)
        self.assertEqual((row["fail"], row["success"]), (95, 5))
        self.assertEqual(self.unknown(board), ["n", "o", "p"])
        scroll = next(item for item in board.inventory if (item.tval, item.sval) == SCROLL)
        self.assertEqual((scroll.slot, scroll.count), ("g", 5))

    def test_the_unreliable_power_gives_way_to_the_scroll_and_the_visit_goes_on(self):
        policy, board, _recorded, entries = self.to_cast_row()
        self.assertFalse(identify_power_reliable(policy, board))
        # The carried-source answer every identification consumer asks (Home shelving,
        # the dungeon equipment identify, item_fate) says the same.
        self.assertFalse(identify_power_available(policy, board))
        key, reason, final = self.decide(policy, board)
        self.assertEqual((key, reason, final), ("rgn", "identify:normal", "rgn"))
        raw = json.loads(entries[CAST_ROW]["line"] or entries[CAST_ROW]["inputs"][-1])
        chain = policy.peek_staged_prompt_chain()
        self.assertIsNotNone(chain)
        # DECLARED CONSTRUCTED: the two item questions the read asks, as the chain's gates
        # name them, with the input context the game publishes for an item question.
        source_screen, target_screen = (
            dict(executor_pins.prompt_screen(gate[1][0].rstrip()),
                 input_context={"kind": "item", "prompt": gate[1][0].rstrip()})
            for gate in chain["gates"][:2])
        source_screen["lines"][1] = "g) 5 巻の鑑定の巻物"
        target_screen["lines"][0] = "(持ち物:n-p, ESC) " + target_screen["lines"][0]
        target_screen["lines"][1] = "n) 未鑑定の鎧"
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screens = [source_screen, target_screen, executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [copy.deepcopy(raw), copy.deepcopy(raw),
                       dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
        _game, client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line, result = _send_prompt_gated_decision_key(
            port, "recorded-row-20", key, None, set(), chain,
            shadow_client=client, file=StringIO(), deadline=9999999999,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, ["r", "g", "n"])
        self.post(policy, final)
        # DECLARED CONSTRUCTED (module docstring): each read lands.
        keys, reasons = [final], [policy.last_reason]
        for _ in range(8):
            source, target = (next(item for item in raw["inventory"] if item["slot"] == slot)
                              for slot in keys[-1][1:])
            source["count"] -= 1
            for name, value in dict(charging=False, charges=0, ac=10, to_a=0, to_h=0, to_d=0,
                                    pval=0, known_flags=[],
                                    damage_dice={"num": 0, "sides": 0}).items():
                if target.get(name) is None:
                    target[name] = value
            target["known"] = True
            raw["turn"] += 10
            raw["messages"] = []
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key, reason, final = self.decide(policy, board)
            keys.append(final)
            reasons.append(policy.last_reason)
            if reason != "identify:normal":
                break
            self.post(policy, final)
        self.assertEqual(keys[:3], ["rgn", "rgo", "rgp"])
        self.assertEqual(self.unknown(board), [])
        self.assertNotIn(BURST, reasons)
        self.assertFalse(any(key.startswith("mA") for key in keys if key), keys)
        self.assertNotEqual(reasons[-1], "identify:normal", reasons)

    def test_an_undrained_int_keeps_the_absorbed_identify(self):
        policy, rows, entries = self.arrival()
        # Rows 0-4 as recorded: row 4 reads the staff list ('bA'); row 5's board shows it.
        for recorded, supply in itertools.islice(rows, LIST_ROW):
            key, reason, final = self.decide(policy, supply())
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]))
            self.post(policy, final)
        raw = json.loads(entries[LIST_ROW]["line"] or entries[LIST_ROW]["inputs"][-1])
        recorded_board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        target = next(item for item in recorded_board.inventory
                      if not item.known and item.is_equipment)
        identify = me_capability.names("staff", SV_STAFF_IDENTIFY)
        listed = next(row for row in raw["_magic_eater_power_list"]["rows"]
                      if row["name"] in identify)
        self.assertEqual((listed["fail"], listed["current"]), (95, 99))
        # DECLARED COUNTERFACTUAL (module docstring): INT at its top (44, stat index 17),
        # and the Identify row as the game lists it there (5% fail, adj_mag_fail's floor).
        raw["player"]["stats"]["int"].update(use=44, index=17, drained=False)
        listed.update(fail=5, success=95)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.decide(policy, board)
        self.assertEqual(me_capability.observed_row(policy, "staff", SV_STAFF_IDENTIFY)["success"], 95)
        self.assertTrue(identify_power_reliable(policy, board))
        self.assertEqual(identify_power_command(policy, board, target, full=False),
                         "mAf" + target.slot)
