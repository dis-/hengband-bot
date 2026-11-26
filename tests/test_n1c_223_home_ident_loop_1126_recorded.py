"""Home *Identify* takes that no *Identify* serves go out and back (n1-c life-223, 2026-11-26 19:17).

n1-c life-223 (Lv32 Zombie Magic-Eater) identifies gear with the Powerful Activation of its
absorbed Staff of Perception (me_powerful_activation, 80 charges on this visit).  Each target
gets ``ATTEMPTS_PER_TARGET`` uses.  At 18:54 the periodic save, character dump and power list
replaced the selected *Identify* key on one board after another (policy ``_decide``): every
replaced decision counted a use that never reached the game, and ☆陣笠『太陽の衣』 and
電撃の魔法を防ぐクローク reached the bound without one cast (bot-stdout.log has no such use).
On the stop visit ``_home_take_key`` filed the Home take of each in turn (it bounded the takes,
not the uses); the carried piece had no use left (``_first_open``), so nothing held it, the
deposit flow shelved it again and the other piece was taken: eleven round trips until
town:blocked:stage-deadline:home.

Fixed: the take asks the use's own bound (``_uses_left``); a use whose key a later rung replaces is
withdrawn (``withdraw_unposted_use``); and a Home take of a visit whose piece went back unprocessed
is not filed again on that visit (spare_gear ``taken_back``, every home-catalog take).

Recorded (tests/extract_n1c_223_home_ident_loop_1126_fixture.py,
``n1c-223-home-ident-loop-1126``): the town-arrival checkpoint of 19:16:41 (turn 2153829) and
all 53 journal rows, replayed open-loop through the public ``choose_key`` (each row posts the
recorded key, so the boards stay the live ones).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import me_powerful_activation as powerful
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-223-home-ident-loop-1126"
CLOAK = ("電撃の魔法を防ぐクローク [1,+4]", 35, 4)
HAT = ("☆陣笠『太陽の衣』 [4,+5] (+4赤外線視力)", 32, 4)
FIRST_TAKE = 23     # recorded: the cloak's take is filed (shop:travel to Home)
HAT_CARRIED = 30    # recorded: the hat just taken out, about to go back
SECOND_ROUND = 32   # recorded: the cloak's take filed again
TAKE_REASONS = ("home-errand:request-knowledge:identification-catalog",
                "home-errand:atomic-withdraw:identification-catalog")


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    request = policy._home_errand.request if policy._home_errand.active else None
    return key, policy.last_reason, request


def attempts(policy, signature):
    return powerful._memory(policy).attempts.get((powerful.IDENTIFY.name, signature), 0)


def forget_attempts(policy):
    """The uses the withdrawal leaves: none of the counted ones was cast (bot-stdout.log)."""
    for signature in (CLOAK, HAT):
        powerful._memory(policy).attempts.pop((powerful.IDENTIFY.name, signature), None)


def replay(scratch, *, prepare=None, stop=None, at=None):
    policy, _journal, steps = load(FIXTURE, Path(scratch))
    if prepare is not None:
        prepare(policy)
    rows = []
    for index, (recorded, supply) in enumerate(steps):
        if stop is not None and index > stop:
            break
        board = supply()
        if at is not None and index == stop:
            return policy, board, rows
        rows.append((index, recorded["key"], recorded["reason"], *decide(policy, board)))
        post(policy, recorded["key"])
    return policy, None, rows


class HomeIdentLoop1126RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.policy, _board, cls.rows = replay(scratch.name)

    def test_the_recorded_loop_is_in_the_fixture(self):
        self.assertEqual(self.rows[FIRST_TAKE][2], "shop:travel")
        self.assertEqual([row[2] for row in self.rows[25:33]],
                         [TAKE_REASONS[1], "home:atomic-deposit", "home:atomic-deposit",
                          TAKE_REASONS[0], TAKE_REASONS[1], "home:atomic-deposit",
                          "home:atomic-deposit", TAKE_REASONS[0]])
        self.assertEqual(self.rows[-1][2], "town:blocked:stage-deadline:home")
        self.assertEqual(attempts(self.policy, CLOAK), powerful.ATTEMPTS_PER_TARGET)
        self.assertEqual(attempts(self.policy, HAT), powerful.ATTEMPTS_PER_TARGET)

    def test_no_take_is_filed_for_a_piece_without_identify_uses(self):
        for index, _key, _reason, key, reason, request in self.rows:
            with self.subTest(row=index):
                self.assertNotIn(reason, TAKE_REASONS)
                self.assertIsNone(request, (key, reason))


class SourceAvailable1126RecordedTest(unittest.TestCase):
    """With the uses left that the withdrawal leaves, the take and its *Identify* still happen."""

    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.policy, cls.board, cls.rows = replay(
            scratch.name, prepare=forget_attempts, stop=HAT_CARRIED, at=True)

    def test_the_take_is_filed(self):
        _index, _key, _reason, _replayed, _why, request = self.rows[FIRST_TAKE]
        self.assertEqual(request.signature, HAT)
        self.assertEqual(request.purpose, "identification-catalog")

    def test_a_replaced_identify_is_withdrawn_and_the_next_board_casts_it(self):
        policy, board = self.policy, self.board
        self.assertTrue(any(policy._item_signature(item) == HAT for item in board.inventory))
        policy._periodic_save_requested = True  # the CLI's save timer latch
        key, reason, _request = decide(policy, board)
        self.assertEqual((key, reason), ("\x13", "periodic:game-save"))
        self.assertEqual(attempts(policy, HAT), 0)
        post(policy, key)
        key, reason, _request = decide(policy, board)
        self.assertEqual(reason, "me-powerful:identify")
        self.assertEqual(key, powerful.IDENTIFY.key + "h")
        self.assertEqual(attempts(policy, HAT), 1)


class TakenBack1126RecordedTest(unittest.TestCase):
    """A take whose own admission is wrong goes out and back at most once a visit.

    The take's use bound is put back as it was (the Home pieces are asked open) so the
    recorded takes are filed again; spare_gear ``taken_back`` is what then stops them.
    """

    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        real = powerful._uses_left
        state = {}

        def home_pieces_open(policy, effect, signature):
            carried = state.get("board") is not None and any(
                policy._item_signature(item) == signature for item in state["board"].inventory)
            return real(policy, effect, signature) if carried else True

        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        cls.rows = []
        with mock.patch.object(powerful, "_uses_left", home_pieces_open):
            for index, (recorded, supply) in enumerate(steps):
                board = state["board"] = supply()
                cls.rows.append((index, recorded["key"], recorded["reason"], *decide(policy, board)))
                post(policy, recorded["key"])

    def test_the_first_round_trip_of_each_piece_is_reproduced(self):
        self.assertEqual(self.rows[25][3:5], ("5pV\x1b", TAKE_REASONS[1]))
        self.assertEqual(self.rows[29][3:5], ("5pZ\x1b", TAKE_REASONS[1]))

    def test_no_piece_is_taken_again_on_the_visit(self):
        for index, _key, _reason, key, reason, request in self.rows[SECOND_ROUND:]:
            with self.subTest(row=index):
                self.assertNotIn(reason, TAKE_REASONS)
                self.assertIsNone(request, (key, reason))


if __name__ == "__main__":
    unittest.main()
