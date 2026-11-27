"""A load that costs no speed departs when no relief ever opened (n1-a life-545, MAINTAINABILITY.md
2-3).

Recorded (tests/extract_n1a_545_weight_ready_1128_fixture.py, ``n1a-545-weight-ready-1128``): the
town-arrival checkpoint of 2026-11-28 05:06:42 (Amberite Rogue CL39, Sorcery, arrival turn 6841644,
the resume on build bot-3d71cd43b).  Row 6 took four empty *Destruction* staffs (5.0 lb each) from
Home (the six carried became ten, 158.9 -> 178.9 lb), rows 9 and 12 bought ten potions and one
Word of Recall scroll (181.4 lb), row 14 stepped off the entrance and row 15 stopped as
town:blocked:survival:inventory_weight_ready.

The weight's facts: the limit is 160.0 lb (adj_str_wgt x 50, player-status.cpp:2556-2563) and the
slowdown (weight - limit) / (limit / 5) (player-speed.cpp:43-51) is 0 up to 191.9 lb
(overweight_departure ``tolerated_weight``).  Every carried stack is a retention reservation's
(the relief's route ``retained-only``), so no relief state was filed and ``give_way`` -- asked only
inside the open relief -- was never reached; the purchase deposit found no item held only by this
visit's purchase.  The town end's last rescue of the leaf is now the weight's one answer
(overweight_departure ``relief_spent_key``).

Every row before row 15 is replayed through the public ``choose_key`` and compared with the record
(the town-arrival checkpoint, its journal and sidecars).  The revert test takes the new rescue out
of the leaf's row and gets the recorded stop back.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import departure_rescues, overweight_departure
from hengbot.angband_finale import slowdown
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-weight-ready-1128"
STOP_ROW = 15
STOP = ("5", "town:blocked:survival:inventory_weight_ready")


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        key = policy.choose_key(board)
    return key, policy.last_reason, out.getvalue()


class WeightReady545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.recorded = (journal[STOP_ROW]["key"], journal[STOP_ROW]["reason"])
        cls.replayed = []
        for row, (recorded, supply) in enumerate(steps[:STOP_ROW + 1]):
            board = supply()
            if row == STOP_ROW:
                cls.stop_board, cls.stop_checkpoint = board, checkpoint_bytes(policy)
                break
            key, reason, _ = decide(policy, board)
            cls.replayed.append(((key, reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def restored(self):
        return restore_checkpoint_bytes(HengbotPolicy, self.stop_checkpoint)

    def test_the_replay_follows_the_record_to_the_stop(self):
        self.assertEqual(self.recorded, STOP)
        self.assertEqual([row for row, (decided, recorded) in enumerate(self.replayed)
                          if decided != recorded], [])

    def test_the_load_costs_no_speed_and_every_stack_is_retained(self):
        policy, board = self.restored(), self.stop_board
        weight, limit = policy._inventory_weight(board), policy._inventory_weight_limit(board)
        self.assertEqual((weight, limit), (1814, 1600))
        self.assertEqual(overweight_departure.tolerated_weight(limit), 1919)
        self.assertEqual(slowdown(weight, limit), 0)
        self.assertTrue(policy._inventory_overweight(board))
        relief = policy._weight_relief_selection(board)
        self.assertEqual((relief.route, relief.surplus, relief.deposits), ("retained-only", (), ()))
        self.assertIsNone(policy._overweight_surplus_disposal)
        minimum = policy._departure_minimum(board, policy._planned_depth())
        self.assertEqual(minimum["failed"], ["inventory_weight_ready"])

    def test_the_stop_board_departs_with_the_waiver_recorded(self):
        policy = self.restored()
        key, reason, out = decide(policy, self.stop_board)
        self.assertNotEqual((key, reason), STOP)
        self.assertNotIn("blocked", reason)
        self.assertEqual(reason, "town:repetition-depart:recall")
        self.assertTrue(key.startswith("r"), key)
        self.assertIn("<overweight-departure-waived> cause=town-end-relief-spent weight=1814 "
                      "limit=1600 allowed=1919 forced=False", out)
        held = getattr(policy, overweight_departure.NAME)
        self.assertEqual((held["allowed"], held["cause"]), (1919, "town-end-relief-spent"))
        self.assertFalse(policy._inventory_overweight(self.stop_board))
        records = policy._overweight_surplus_record_path.read_text(encoding="utf8")
        self.assertIn('"reason": "town:overweight-departure-waived"', records)

    def test_revert_without_the_give_way_rescue_the_visit_stops(self):
        row = departure_rescues.RESCUES["inventory_weight_ready"]
        reverted = departure_rescues.Rescue(
            tuple(action for action in row.actions if action != "overweight-give-way"))
        policy = self.restored()
        with mock.patch.dict(departure_rescues.RESCUES, {"inventory_weight_ready": reverted}), \
                mock.patch("hengbot.departure_leaf_classes.safer_fallback", return_value=False):
            key, reason, _ = decide(policy, self.stop_board)
        self.assertEqual((key, reason), STOP)

    def test_without_the_give_way_the_class_fallback_mines_instead_of_stopping(self):
        row = departure_rescues.RESCUES["inventory_weight_ready"]
        reverted = departure_rescues.Rescue(
            tuple(action for action in row.actions if action != "overweight-give-way"))
        policy = self.restored()
        with mock.patch.dict(departure_rescues.RESCUES, {"inventory_weight_ready": reverted}):
            key, reason, out = decide(policy, self.stop_board)
        self.assertEqual(reason, "town:end-mining-cycle")
        self.assertIn("<town-end-safer> inventory_weight_ready", out)


if __name__ == "__main__":
    unittest.main()
