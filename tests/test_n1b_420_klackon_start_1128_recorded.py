"""A new character no digger can be had for leaves its first town; food comes first (n1-b life-420).

Recorded (tests/extract_n1b_420_klackon_start_1128_fixture.py, ``n1b-420-klackon-start-1128``): the
town-arrival checkpoint of the new character's first board (2026-11-28 08:31:26, Klackon
Magic-Eater Lv1, speed +0, food_type RATION, 100 gold, 4 Rations and 4 torches).

* Row 13 (General Store, Q34 opening): 16 torches for 48 gold, the Q34 carry (quest-throwing-items)
  first on the departure order (policy_shop ``_mandatory_purchase``).  The opening then released
  the character (quest_opening_readiness ``strategy-force:dps``) and the poverty set opened
  (52 < FUNDRAISING_START_GOLD).
* Row 18 (Alchemist): 3 Treasure Detection for 18 gold; the set became ``mine`` with 3 runs.
  The General page of row 13 had a Pick at 155 and no digger for 34 gold.
* Rows 20-23 observed the Black Market and the Temple; the General store was not walked again
  (its shelf evidence) and Home not at all, so the mining departure's own fallback
  (``_fundraising_departure_ready``: Home and General attempted in this set) never came.
* Row 24 stepped off the Temple entrance (fundraise:departure-blocked-step-off) and row 25 stopped
  as town:blocked:unmet:food_ready: the town end's waived departure (food 4 of 5 is a TOP_UP above
  one trip's 2) was refused by the forced departure's minimum (one Teleportation scroll, 66 gold),
  and its 1F mining give-way does not start over an open mining set.

Now the open set no digger can be had for scavenges 1F (``_settle_diggerless_scavenge``, owner
2026-10-23), and an ordinary eater short of one trip's food buys it before the quest carries and
the mining kit's reserve.

Every row is decided by the public ``choose_key`` of the restored arrival policy and the recorded
key is posted.  Rows 9 (one more Magic-Eater power page on the record) and 15 (Magic before
Alchemist; the same stores are walked) differ from the record on the current build with or
without this fix; they are listed, not asserted.

DECLARED CONSTRUCTED: the below-trip test removes the carried Rations from the row-13 General
Store board and sets the gold to 34 (and 100).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import food_supply, town_terminal
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import STORE_GENERAL, TVAL_FOOD
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import FOOD_TYPE_RATION
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-420-klackon-start-1128"
GENERAL_ROW = 13
STEP_OFF_ROW = 24
STOP_ROW = 25
UNREPRODUCED = {9, 15}
GENERAL_RECORDED = ("ph16\r\r", "shop:in-store-buy")
STEP_OFF = ("1", "fundraise:departure-blocked-step-off")
STOP = ("5", "town:blocked:unmet:food_ready")
SV_RATION = 35


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


def without_food(board, gold):
    return dataclasses.replace(
        board, inventory=tuple(item for item in board.inventory if item.tval != TVAL_FOOD),
        player=dataclasses.replace(board.player, gold=gold))


class KlackonStart420RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.recorded = {row: (journal[row]["key"], journal[row]["reason"])
                        for row in (GENERAL_ROW, STEP_OFF_ROW, STOP_ROW)}
        cls.replayed, cls.boards, cls.checkpoints = [], {}, {}
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row in (GENERAL_ROW, STEP_OFF_ROW, STOP_ROW):
                cls.boards[row], cls.checkpoints[row] = board, checkpoint_bytes(policy)
            key, reason, _ = decide(policy, board)
            cls.replayed.append(((key, reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def restored(self, row):
        return restore_checkpoint_bytes(HengbotPolicy, self.checkpoints[row])

    def test_the_record_is_the_stop(self):
        self.assertEqual(self.recorded[GENERAL_ROW], GENERAL_RECORDED)
        self.assertEqual(self.recorded[STEP_OFF_ROW], STEP_OFF)
        self.assertEqual(self.recorded[STOP_ROW], STOP)

    def test_the_replay_follows_the_record_to_the_step_off(self):
        unmatched = {row for row, (decided, recorded) in enumerate(self.replayed[:STEP_OFF_ROW])
                     if decided != recorded}
        self.assertTrue(unmatched <= UNREPRODUCED, unmatched)
        self.assertEqual(self.replayed[GENERAL_ROW][0], GENERAL_RECORDED)

    def test_the_stop_board(self):
        board = self.boards[STOP_ROW]
        player = board.player
        self.assertEqual((player.level, player.gold, player.food_type, player.food_state),
                         (1, 34, FOOD_TYPE_RATION, "normal"))
        self.assertEqual(food_supply.carried_rations(board.inventory), 4)
        self.assertEqual(food_supply.trip_rations(player), 2)
        self.assertFalse(food_supply.below_trip(player, board.inventory))
        general = self.boards[GENERAL_ROW].store
        self.assertEqual(general.store_type, STORE_GENERAL)
        ration = next(item for item in general.items if (item.tval, item.sval) == (TVAL_FOOD, SV_RATION))
        self.assertEqual(ration.price, 4)
        self.assertFalse(any(item.is_digging_tool and item.price <= player.gold
                             for item in general.items))
        policy = self.restored(STOP_ROW)
        self.assertEqual(policy._count_treasure_detection_scrolls(board), 3)
        self.assertFalse(policy._has_digging_tool(board))
        self.assertTrue(policy._diggerless_scavenge_allowed(board))

    def test_the_step_off_board_scavenges_instead(self):
        policy = self.restored(STEP_OFF_ROW)
        self.assertEqual(policy._fundraising_mode, "mine")
        key, reason, _ = decide(policy, self.boards[STEP_OFF_ROW])
        self.assertNotEqual((key, reason), STEP_OFF)
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertEqual(reason, "town:travel-entrance")

    def test_the_stop_board_departs(self):
        policy = self.restored(STOP_ROW)
        key, reason, _ = decide(policy, self.boards[STOP_ROW])
        self.assertNotEqual((key, reason), STOP)
        self.assertNotIn("blocked", reason)
        self.assertEqual(reason, "town:travel-entrance")
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertTrue(policy._fundraising_departure_ready(self.boards[STOP_ROW]))
        self.assertFalse(policy._descent_is_blocked(self.boards[STOP_ROW]))
        self.assertIsNone(policy._town_blocked_reason)

    def test_the_town_end_material_of_the_stop(self):
        # What the town end read on the recorded stop (the open set, the unaffordable Teleport).
        policy = self.restored(STOP_ROW)
        with contextlib.redirect_stdout(io.StringIO()):
            material = town_terminal.gather_town_end(policy, self.boards[STOP_ROW])
        self.assertEqual(material.unmet, ("food_ready", "teleport_ready"))
        self.assertEqual(material.survival_unmet, ("teleport_ready",))
        self.assertEqual(material.purchase_gaps, ("teleport_ready",))
        self.assertTrue(material.mining_set_open)

    def test_food_below_one_trip_is_bought_first(self):
        for gold in (34, 100):
            with self.subTest(gold=gold):
                board = without_food(self.boards[GENERAL_ROW], gold)
                self.assertTrue(food_supply.below_trip(board.player, board.inventory))
                policy = self.restored(GENERAL_ROW)
                self.assertTrue(policy._opening_q34_active(board))
                key, reason, _ = decide(policy, board)
                letter = next(item.letter for item in board.store.items
                              if (item.tval, item.sval) == (TVAL_FOOD, SV_RATION))
                self.assertEqual(reason, "shop:in-store-buy")
                self.assertEqual(key, f"p{letter}5\r\r")

    def test_one_trips_food_leaves_the_torch_order_as_it_was(self):
        policy = self.restored(GENERAL_ROW)
        self.assertEqual(decide(policy, self.boards[GENERAL_ROW])[:2], GENERAL_RECORDED)


if __name__ == "__main__":
    unittest.main()
