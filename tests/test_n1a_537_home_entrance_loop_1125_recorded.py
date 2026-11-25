"""A Home take the town pack budget refuses is not bound (n1-a life-537, 2026-11-25 23:09-23:10).

Owner rule 2026-11-13 (pingpong-root-1113): a loop of two owners stepping opposite ways is fixed at
its root.  n1-a life-537 (Lv48 Zombie Warrior) came back from Q33.  The town need enumeration bound
a Home take of plain クロスボウの矢 for the carried (+6,+3) stack (``_queue_home_ammo_top_up``,
row 6, 4 free slots); the Q33 reward pickup (row 25) left 3 free, the terminal reserve.  The
outside composer refused the take at the Home entrance (store_item_key: home_take_fits), the
open page released it (``_keep_home_takes_within_pack_budget``) and left as
home:route-claim-unfulfilled, and the next need enumeration bound it again: shop:approach stepped
'9' off the Home entrance (45,123) and '1' back on, 26 rounds to
town:blocked:stage-deadline:home.

The binder asks the composer's question (``home_take_fits``) before it binds, so a refused take
never holds Home as the plan's stop; the headroom pass makes room if a stack can be shelved.

Recorded (tests/extract_n1a_537_home_entrance_loop_1125_fixture.py,
``n1a-537-home-entrance-loop-1125``): the town-arrival checkpoint of 23:09:16 (turn 4329817) and
its first 40 journal rows, replayed open-loop through the public ``choose_key`` (each row posts
the recorded key, so the boards stay the live ones).  Revert of the binder check: row 36 steps
'1' onto the Home entrance again, and the refused ammo take stays bound from row 26 on.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import STORE_HOME, Position
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_pack_budget import home_take_fits
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-537-home-entrance-loop-1125"
HOME_ENTRANCE = Position(45, 123)
BESIDE = Position(44, 124)
REWARD_PICKED = 26  # the first board after the Q33 reward pickup: 3 free slots
LOOP_ROW = 36  # (44,124): recorded shop:approach '1' back onto the Home entrance
OFFSETS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
           "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def refused_bound_take(policy, board):
    """The bound Home take (queued item or batch) the town pack budget refuses, if any."""
    stocked = {policy._item_signature(item): item for item in policy._home_knowledge_items}
    for signature in (policy._home_pending_item, *policy._home_pending_batch):
        item = stocked.get(signature)
        if item is None:
            continue
        quantity = policy._home_pending_quantities.get(
            signature, policy._home_pending_quantity or 1)
        if not home_take_fits(board, item, quantity, policy=policy):
            return signature
    return None


class HomeEntranceLoop1125RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        cls.rows = []
        for index, (recorded, supply) in enumerate(steps):
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            here = board.player.position
            offset = OFFSETS.get(key) if board.store is None else None
            to = None if offset is None else Position(here.y + offset[0], here.x + offset[1])
            refused = refused_bound_take(policy, board) if board.store is None else None
            cls.rows.append((index, recorded["key"], recorded["reason"], key, policy.last_reason,
                             here, to, len(board.inventory), refused, board))
            post(policy, recorded["key"])

    def test_the_recorded_loop_is_in_the_fixture(self):
        index, recorded, reason, *_rest, here, _to, _carried, _refused, board = self.rows[LOOP_ROW]
        self.assertEqual((recorded, reason, here), ("1", "shop:approach", BESIDE))
        self.assertEqual(board.grid_at(HOME_ENTRANCE).store_number, STORE_HOME)
        self.assertEqual(self.rows[LOOP_ROW + 1][2], "home:route-claim-unfulfilled")
        self.assertEqual([row[1] for row in self.rows[35:40]], ["9", "1", "\x1b", "9", "1"])
        self.assertEqual(self.rows[REWARD_PICKED - 1][2], "fixedquest:reward-pickup")
        self.assertEqual(self.rows[REWARD_PICKED][7], 20)  # 3 free of 23: the terminal reserve

    def test_no_refused_home_take_stays_bound(self):
        for index, *_rest, refused, _board in self.rows[REWARD_PICKED:LOOP_ROW + 1]:
            with self.subTest(row=index):
                self.assertIsNone(refused)

    def test_the_approach_does_not_step_back_onto_the_home_entrance(self):
        _index, _recorded, _reason, key, reason, here, to, *_rest = self.rows[LOOP_ROW]
        self.assertEqual(here, BESIDE)
        self.assertNotEqual(to, HOME_ENTRANCE, (key, reason))


if __name__ == "__main__":
    unittest.main()
