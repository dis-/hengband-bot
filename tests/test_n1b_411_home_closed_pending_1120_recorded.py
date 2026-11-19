"""n1-b life-411 2026-11-20 03:33:27, town:blocked:unmet:home_pending_item_clear (bot main b77b2b7c68).

The Magic-Eater (Lv50) came home to a Home of 240 stacks.  At the Alchemist (row 93) the Potion of
Resistance purchase found the potion at Home and queued its take first (the home-first purchase
gate, row 94: ``_home_pending_item``).  The walk to Home met the equipment transaction instead:
it shelved the replaced Short Bow of Accuracy (rows 97-99), which filled the Home (240/240), and
the Home pass closed unsatisfied (the town ledger: Home blocked, one unsatisfied pass).  The
purchase then bought the potion (row 101: ten carried, the retention's ten), but the Home take
stayed queued.  No Home page would serve it again this visit, and the departure's Home-settle
rescue walks back only while Home was not tried (departure_rescues ``_home_settle``): the visit
stopped on the pending take's leaf.

Now a queued take behind a Home closed for the visit is deferred for the visit
(policy_home ``_release_unservable_home_latches``), as a deferred take always was: what it was
for is the supply leaves' (here already met) or the next visit's.

Recorded: the stop's town-arrival checkpoint and all 106 journal rows
(tests/extract_n1b_411_home_closed_pending_1120_fixture.py).  Rows 0-95 are decided through the
public choose_key and compared with the record up to row 17 (see MATCHED); rows 17-104 post the recorded keys (the replay
leaves the record at row 96, on main b77b2b7c68 alike: the live Home census answer was still in
flight).

DECLARED CONSTRUCTED: on row 105's board, the Home closure the live town ledger shows at the
stop (Home in the blocked stores, attempted, one unsatisfied pass).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import _configure_in_store_shop_ops
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import STORE_HOME
from hengbot.policy import HengbotPolicy
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-home-closed-pending-1120"
MATCHED, STOP_ROW = 17, 105
# Rows 17-23 sold the carried Potion of Restore Life Levels, a kind the consumable table keeps at
# Home: since owner 2026-11-20 (item_fate.supply_kept, tests/test_n1b_411_restore_mana_keep_
# 1120_recorded) no relief sells it, and the replay leaves the record there (it matched up to
# row 96 before); the later rows post the recorded keys.
POTION = ("耐性の薬 {@2}", 75, 60)


class N1b411HomeClosedPending1120RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, cls.journal, steps = load(FIXTURE, scratch)
        with contextlib.redirect_stderr(io.StringIO()):
            _configure_in_store_shop_ops(policy, SimpleNamespace(
                in_store_shop_ops=True, decision_log=scratch / "bot-decisions.jsonl"))
        cls.replayed = []
        for row, (recorded, supply) in enumerate(steps[:STOP_ROW]):
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            if row < MATCHED:
                cls.replayed.append(((key, policy.last_reason),
                                     (recorded["key"], recorded["reason"])))
            post(policy, board, recorded["key"], before)
        cls.board = steps[STOP_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)
        cls.history = policy._home_disposal.history_path
        cls.history_bytes = cls.history.read_bytes() if cls.history.exists() else None

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        if self.history_bytes is not None:
            self.history.write_bytes(self.history_bytes)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def close_home(self):
        policy, board = self.policy, self.board
        ledger = policy._town_visit_ledger
        ledger.blocked_stores.add(STORE_HOME)
        ledger.unsatisfied_passes[STORE_HOME] = 1
        policy._set_town_store_attempted(STORE_HOME, board.turn, "home-pass-closed")

    def test_the_recorded_rows(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[STOP_ROW]["reason"],
                         "town:blocked:unmet:home_pending_item_clear")
        self.assertEqual(self.journal[99]["reason"], "equipment-transaction:deposit-home-full")

    def test_the_take_queued_behind_a_closed_home_is_deferred(self):
        policy, board = self.policy, self.board
        self.assertEqual(policy._home_pending_item, POTION)
        # The potion was bought meanwhile: the retention's ten are carried.
        self.assertEqual(sum(item.count for item in board.inventory
                             if policy._item_signature(item) == POTION), 10)
        self.close_home()
        self.assertTrue(policy._town_store_blocked_under_applicable_bound(STORE_HOME))
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "town:blocked:unmet:home_pending_item_clear")
        # The release runs on every town decision that routes the next store
        # (_next_required_store_type); this board's decision may be another owner's first.
        policy._release_unservable_home_latches()
        self.assertIsNone(policy._home_pending_item)
        self.assertIn(POTION, policy._deferred_home_items)
        self.assertTrue(policy._town_departure_ready(board))
        self.assertTrue(key)

    def test_an_open_home_keeps_the_take(self):
        policy = self.policy
        # The same board with Home open: the take stays queued for the Home page.
        policy._release_unservable_home_latches()
        self.assertEqual(policy._home_pending_item, POTION)


if __name__ == "__main__":
    unittest.main()
