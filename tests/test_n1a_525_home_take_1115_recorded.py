"""A Home take whose outside board keeps the posting turn is still settled (n1-a life-525).

n1-a life-525 (Lv37 Warrior, build 3b52c43f0, 2026-11-15 13:40:36) crashed in town with
``ValueError: Home errand is not composable``.  Home's full relief had filed its errand for
the オークスレイヤーのパイク (a Home-full sale) and row 18 posted the take
``5  pO<ESC>`` from Home's entrance on game turn 8552723.  The game took it (the Home page
went 219 -> 218, the pack 11 -> 12) and the next outside board came on the same turn
8552723: the game emits a board before every command while the player's energy lasts
(core/player-processor.cpp, a command's energy is ``randnor(100, 25)``).  The take's
reconciliation read only a later turn as the outcome, so the take was left unsettled; item
processing then dropped the pending take with the pike in the pack, the errand stayed
posted, its take was composed again and ``HomeErrandExecutor.post`` raised.

Fix: the outside board is the take's outcome once the pack holds it, whatever its turn
(policy._observe_home_atomic_withdrawal_outside); item processing settles the errand of a
take it drops (policy_town._town_item_processing_dispatch_key).

Recorded: the incident capture's town-arrival checkpoint and whole journal (19 rows,
tests/extract_n1a_525_stops_1115_fixtures.py), rows 0-18 decided through the public
choose_key and compared with the record; the crash board is the last of the six response
records after row 18 in the capture's snapshot tail, delivered as the CLI delivers them.

DECLARED CONSTRUCTED: row 1's character dump wrote a calibration the journal does not hold;
the arrival calibration is re-adopted with its observed turn moved to row 1's board (the
same character, level and stats; without it the equipment transaction of row 4 does not
open).  The item-processing case leaves the store visit's operation unreleased.  The
*Destruction* means bonus (equipment_utility, owner 2026-11-15 「深さに関係なく持っていく」, later
than this visit) is held at 0: with it row 8's transaction wears the gear that makes the Home's
staves reliable, a different set from the record's, and the take of row 18 is not reached.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import equipment_utility
from hengbot.cli import _consume_response_sequence
from hengbot.home_errand import HomeErrandState
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-stops-1115" / "home-take"
DUMP_ROW = 1
TAKE_ROW = 18
PIKE = (22, 8)
TURN = 8552723


class N1a525HomeTake1115RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # DECLARED CONSTRUCTED (module docstring): the visit before the 11-15 bonus.
        cls.bonus = mock.patch.object(equipment_utility, "DESTRUCTION_MEANS_BONUS", 0.0)
        cls.bonus.start()
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, cls.journal, steps = load(FIXTURE, scratch)
        calibration = json.loads(
            (scratch / "town-arrival" / "sidecars" / "_character_calibration_path")
            .read_text(encoding="utf-8"))
        cls.replayed = []
        for recorded, supply in steps:
            board = supply()
            key = policy.choose_key(board)
            cls.replayed.append((recorded["row"], (key, policy.last_reason),
                                 (recorded["key"], recorded["reason"])))
            policy.confirm_key_posted(recorded["key"])
            if recorded["row"] == DUMP_ROW:
                # DECLARED CONSTRUCTED (module docstring): the dump's calibration.
                calibration["observed_turn"] = board.turn
                dumped = scratch / "calibration-after-dump.json"
                dumped.write_text(json.dumps(calibration), encoding="utf-8")
                adopt_calibration(policy, dumped, scratch / "runtime")
        cls.checkpoint = checkpoint_bytes(policy)
        cls.after_take = [json.loads(line) for line in lzma.decompress(
            (FIXTURE / "after-take.jsonl.xz").read_bytes()).decode("utf-8").splitlines()
            if line]
        cls.knowledge_ledger = scratch / "knowledge.jsonl"

    @classmethod
    def tearDownClass(cls):
        cls.bonus.stop()
        cls.scratch.cleanup()

    def setUp(self):
        for row, decided, recorded in self.replayed:
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.addCleanup(lambda: self.policy._home_disposal.history_path.unlink(missing_ok=True))

    def crash_board(self):
        policy = self.policy
        _consume_response_sequence(
            [json.dumps(record, ensure_ascii=False) + "\n" for record in self.after_take],
            policy, lambda _key: True, policy._monrace_knowledge, parse_snapshots=False,
            knowledge_ledger_path=self.knowledge_ledger)
        return parse_snapshot(json.loads(json.dumps(self.after_take[-1])),
                              policy._monrace_knowledge)

    def test_the_recorded_take_is_posted_and_taken_on_one_turn(self):
        self.assertEqual(self.journal[TAKE_ROW]["reason"],
                         "home-errand:atomic-withdraw:full-home-sale")
        policy = self.policy
        self.assertEqual(policy._home_errand.state, HomeErrandState.POSTED)
        self.assertEqual(policy._home_atomic_withdraw_posted_turn, TURN)
        self.assertEqual([record["type"] for record in self.after_take],
                         ["player_turn", "store", "store", "store", "store", "player_turn"])
        self.assertEqual({record["turn"] for record in self.after_take}, {TURN})
        self.assertEqual(self.after_take[-2]["store"]["stock_num"],
                         self.after_take[1]["store"]["stock_num"] - 1)
        before = sum(item["count"] for item in self.after_take[0]["inventory"]
                     if (item["tval"], item["sval"]) == PIKE)
        after = sum(item["count"] for item in self.after_take[-1]["inventory"]
                    if (item["tval"], item["sval"]) == PIKE)
        self.assertEqual((before, after), (0, 1))

    def test_the_same_turn_outside_board_settles_the_take(self):
        policy = self.policy
        board = self.crash_board()

        key = policy.choose_key(board)

        self.assertIsInstance(key, str)
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertNotEqual(policy._home_errand.state, HomeErrandState.POSTED)
        self.assertFalse(policy.last_reason.startswith("home-errand:atomic-withdraw"),
                         (key, policy.last_reason))

    def test_item_processing_settles_the_errand_of_the_take_it_drops(self):
        # DECLARED CONSTRUCTED: the store visit's operation left unreleased, so the
        # outside reconciliation does not read the board and item processing, which
        # finds the pike in the pack, drops the pending take (the live crash's path).
        policy = self.policy
        policy._store_visit.operation_released = False
        board = self.crash_board()

        policy.choose_key(board)

        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertNotEqual(policy._home_errand.state, HomeErrandState.POSTED)

    def test_a_same_turn_board_without_the_take_is_not_its_outcome(self):
        # The stay key's entrance board (the first record): the take is still queued.
        policy = self.policy
        board = parse_snapshot(json.loads(json.dumps(self.after_take[0])),
                               policy._monrace_knowledge)

        policy._observe_home_atomic_withdrawal_outside(board)

        self.assertIsNotNone(policy._home_atomic_withdraw_pending)
        self.assertEqual(policy._home_errand.state, HomeErrandState.POSTED)


if __name__ == "__main__":
    unittest.main()
