"""The Black Markets' Restore Mana circuit: the lap's night and the circuit's own time (n1-b life-416).

Owner rules: 2026-11-23 「闇市を回って買い足す — 4つの町の闇市を巡回して買い足し、目標に届くまで99Fへは
行かない。闇市に無ければ巡回をくり返す。」 and 2026-11-20 「一周する毎に宿屋で一泊する」 (finale_bm_tour);
2026-11-13 「段の期限は測った最大の2倍」 (town_visit_plan's stage deadlines).

Recorded (tests/extract_finale_bm_fix_1123_fixture.py, ``n1b-416-finale-bm-fix-1123``): the
town-arrival checkpoint of 23:39:18 (turn 4313051, decision 160).  The circuit started at row 46
(decision 207); its first lap ended in Angwil (town 3) and the walk to the inn went out at rows
119-123 (``depart:inn-refill:finale-bm:approach``).  Row 124 was a periodic browse
(``periodic:magic-eater-powers``) on the board the stay's key had been chosen for, and row 125
(the same game turn, 4315210) began lap 2 without the night (``shop:travel``): every later lap did
the same, so no market restocked, and at row 263 (decision 424) the visit stopped under
``town:blocked:stage-deadline:buy``, each market's leave counted to the buy stage.  Rows 0-124 are
decided through the public ``choose_key`` and each row posts the recorded key (row 124 is the stay
now).

DECLARED CONSTRUCTED: ``test_a_new_market_restarts_the_buy_deadline`` sets the buy stage's count
to its deadline and the lap to a fresh one (no town seen), then decides row 126's board, the Black
Market of Angwil.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import finale_bm_tour, town_visit_plan
from hengbot.model import STORE_BLACK
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_visit import town_visit
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-bm-fix-1123"
PERIODIC_ROW = 124
MARKET_ROW = 126


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleBlackMarketFix1123RecordedTest(unittest.TestCase):
    def replay(self, rows):
        """(policy, [(row, recorded, decided)], the boards' suppliers) after ``rows`` rows."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        decided = []
        for row, (recorded, supply) in enumerate(steps[:rows]):
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(supply())
            decided.append((row, (recorded["key"], recorded["reason"]), (key, policy.last_reason)))
            post(policy, recorded["key"])
        return policy, decided, steps

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def test_the_lap_waits_for_its_night(self):
        # The rows replayed are not compared with the record: a purchase rule changed since
        # (the optional purchases gated while the Restore Mana is short, finale_bm_tour
        # ``restore_mana_first``) decides some of the circuit's market rows otherwise, while the
        # recorded keys keep the boards as they were.
        policy, _decided, steps = self.replay(PERIODIC_ROW)
        tour = finale_bm_tour.record(policy)
        self.assertEqual((tour.lap, tour.seen, tour.night.due), (1, [0, 1, 2, 3], True))
        # Row 124: the stay (test_the_stays_key_is_not_replaced_by_its_refresh), its key taken
        # by another owner's decision and never posted (the recorded browse took it).  Row 125's
        # board is that browse's answer, so the same turn is decided again on row 124's board.
        board = steps[PERIODIC_ROW][1]()
        self.decide(policy, board)
        self.assertEqual(board.turn, tour.night.stay.posted_turn)

        key, reason = self.decide(policy, board)

        # Recorded: ("\x1b`n'.", 'shop:travel'), lap 2 without the night.
        # The stay is asked again, and nothing replaces it now (the browse that took row 124 was
        # the stay's own refresh request, me_inn_refill ``_stay_key``).
        self.assertEqual(reason, "depart:inn-refill:finale-bm:rest")
        self.assertTrue(key)
        self.assertEqual(tour.night.stay.posted_turn, board.turn)
        self.assertEqual((tour.lap, tour.night.nights, tour.night.due), (1, 0, True))

    def test_the_stays_key_is_not_replaced_by_its_refresh(self):
        policy, _decided, steps = self.replay(PERIODIC_ROW)
        key, reason = self.decide(policy, steps[PERIODIC_ROW][1]())
        # Recorded: ('bA', 'periodic:magic-eater-powers'), the stay's own refresh request.
        self.assertEqual(reason, "depart:inn-refill:finale-bm:rest")
        self.assertTrue(key)

    def test_a_new_market_restarts_the_buy_deadline(self):
        policy, _decided, steps = self.replay(MARKET_ROW)
        board = steps[MARKET_ROW][1]()
        self.assertEqual(board.store.store_type, STORE_BLACK)
        # DECLARED CONSTRUCTED (module docstring): the buy stage at its deadline, a fresh lap.
        town_visit(policy).stage_decisions["buy"] = town_visit_plan.STAGE_DEADLINES["buy"]
        tour = finale_bm_tour.record(policy)
        tour.seen, tour.night.due = [], False

        key, reason = self.decide(policy, board)

        # The market of a town not yet seen in the lap is the circuit's progress.
        self.assertNotEqual(reason, "town:blocked:stage-deadline:buy")
        self.assertEqual(tour.seen, [3])
        self.assertLess(town_visit(policy).stage_decisions.get("buy", 0),
                        town_visit_plan.STAGE_DEADLINES["buy"])


if __name__ == "__main__":
    unittest.main()
