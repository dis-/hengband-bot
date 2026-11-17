"""Every town's Black Market once per return when the gold is 100,000 or more (owner 2026-11-17).

Owner 2026-11-17, verbatim: 「併せて、資金10万以上のときはすべての町の闇市を確認する
ルーティーンもつけたい。」, 「帰還で町に戻るたび」, 「念のため。すべての町にズルは含まない。」.

Recorded: n1-c life-216's return by Word of Recall from Angband 77F on 2026-11-17 08:46
(Magic-Eater, 1,277,741 gold; tests/extract_recall_stockout_other_town_1117_fixture.py).
The visit bought at the Outpost's Black Market (rows 145-159) and read Word of Recall
on row 165 (``rfa``, ``town:recall-to-angband``) with 1,359,453 gold.  The rows are
replayed through the public chooser and the live CLI's owner-retirement entrance
(--owner-retired-log-only), each posting its recorded key.  DECLARED DIVERGENCE: rows
2-134 decide otherwise than at 08:46 (the code changed since; the code before this
change diverges on the same rows); from row 135 on every row decides as recorded.

Now row 165, the read point after every errand of the visit, takes the inn to Telmora
(town 1), the first unseen town (bm_tour); Zul (town 4, visited) is never one.

DECLARED CONSTRUCTED: row 165's board with 99,999 gold, with a third of the HP, and
with the tour's towns all seen.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import bm_tour
from hengbot.cli import _handle_owner_retirement
from hengbot.model import STORE_BLACK, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import ZUL_TOWN_ID
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "recall-stockout-other-town-1117" / "n1c-216-0846"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
READ_ROW = 165
CONVERGED = 135
BLACK_MARKET_ROWS = (145, 159)


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does; returns what was posted."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key


class BlackMarketTour1117RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Rows 0-164 posted as recorded; the policy before the read row."""
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.mismatches = []
        cls.tour_before_read = []
        for row, supply in steps[:READ_ROW]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if (key, policy.last_reason) != (entry["key"], entry["reason"]):
                cls.mismatches.append(row["row"])
            tour = bm_tour.record(policy)
            cls.tour_before_read.append(None if tour is None else tour.armed)
            post(policy, board, entry["key"], before)
        cls.before_read = policy
        cls.recorded = recorded
        cls.read_raw = json.loads(recorded[READ_ROW]["line"])

    def policy(self):
        return copy.deepcopy(self.before_read)

    def board(self, policy, **player):
        raw = copy.deepcopy(self.read_raw)
        raw["player"].update(player)
        return parse_snapshot(raw, policy._monrace_knowledge)

    def test_the_visit_replays_and_its_black_market_was_seen(self):
        self.assertTrue(all(row < CONVERGED for row in self.mismatches), self.mismatches)
        entry = self.recorded[READ_ROW]
        self.assertEqual((entry["key"], entry["reason"]), ("rfa", "town:recall-to-angband"))
        black_market_pages = [
            row for row in range(*BLACK_MARKET_ROWS)
            if (json.loads(self.recorded[row]["line"]).get("store") or {}).get("store_type")
            == STORE_BLACK]
        self.assertTrue(black_market_pages)
        tour = bm_tour.record(self.before_read)
        # The return opened the record; it is decided at the read point only.
        self.assertEqual(set(self.tour_before_read), {None})
        self.assertIsNone(tour.armed)
        self.assertEqual(tour.seen, [0])  # the Outpost's Black Market page

    def test_the_read_point_takes_the_inn_to_the_first_unseen_town(self):
        policy = self.policy()
        board = self.board(policy)
        self.assertGreaterEqual(board.player.gold, bm_tour.MIN_GOLD)
        self.assertIn(ZUL_TOWN_ID, board.visited_town_ids)
        key = policy.choose_key(board)
        self.assertIsNotNone(key)
        self.assertTrue(policy.last_reason.startswith(f"{bm_tour.TRAVEL_REASON}-1"),
                        policy.last_reason)
        tour = bm_tour.record(policy)
        self.assertEqual((tour.armed, tour.origin, tour.seen, tour.target, tour.closed),
                         (True, 0, [0], 1, None))
        self.assertTrue(bm_tour.holds_town(policy, board))

    def test_below_100000_gold_the_read_goes_on(self):
        policy = self.policy()
        key = policy.choose_key(self.board(policy, gold=bm_tour.MIN_GOLD - 1))
        entry = self.recorded[READ_ROW]
        self.assertEqual((key, policy.last_reason), (entry["key"], entry["reason"]))
        tour = bm_tour.record(policy)
        self.assertEqual((tour.armed, tour.closed), (False, "gold-below-100000"))
        # Decided once for the return: more gold on the next board does not open it.
        policy.choose_key(self.board(policy))
        self.assertFalse(policy.last_reason.startswith(bm_tour.TRAVEL_REASON), policy.last_reason)
        self.assertEqual((tour.armed, tour.closed), (False, "gold-below-100000"))

    def test_survival_comes_before_the_tour(self):
        policy = self.policy()
        board = self.board(policy, hp=self.read_raw["player"]["max_hp"] // 3)
        policy.choose_key(board)
        self.assertFalse(policy.last_reason.startswith(bm_tour.TRAVEL_REASON), policy.last_reason)
        self.assertIsNone(bm_tour.record(policy).armed)

    def test_once_per_return(self):
        policy = self.policy()
        board = self.board(policy)
        policy.choose_key(board)
        # DECLARED CONSTRUCTED: the tour came back here with every town's market seen.
        tour = bm_tour.record(policy)
        tour.seen.extend((1, 2, 3))
        entry = self.recorded[READ_ROW]
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (entry["key"], entry["reason"]))
        self.assertEqual(tour.closed, "all-towns-seen")
        # The next board (the read awaits its confirmation) does not open it again.
        policy.choose_key(board)
        self.assertFalse(policy.last_reason.startswith(bm_tour.TRAVEL_REASON), policy.last_reason)
        self.assertEqual(tour.closed, "all-towns-seen")
        self.assertNotIn(ZUL_TOWN_ID, tour.seen)
        self.assertEqual(bm_tour.facts(policy)["seen"], [0, 1, 2, 3])
        # The next return by Word of Recall opens a new record.
        bm_tour.note_recall_return(policy, board)
        self.assertIsNone(bm_tour.record(policy).armed)


if __name__ == "__main__":
    unittest.main()
