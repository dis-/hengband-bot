"""The Home *Remove Curse* take waits for pack room; the sales free it first.

n1-a life-532 (Warrior Lv24) stopped 2026-11-22 14:37-14:39 three times as
town:blocked:stage-deadline:home and retired.  The worn 耐電のアミュレット {呪われている,
HEAVY_CURSE} needed the Home's *Remove Curse* (owner 2026-11-03: a worn curse is removed with the
Home reserve first).  The pack held 22 of 23: the take did not fit (town_pack_budget.permits, the
read-at-once take may use one reserve slot only).  Still

* the town plan registered ``home-star-remove-curse-use`` Home first (policy_town
  ``_town_need_candidates``), so every plan after the Alchemist purchase (row 27) was [7, 0, 5];
* the binder (policy_home ``_bind_home_star_remove_curse_withdrawal``) cleared Home's visited
  mark before asking whether the take fits, took nothing, and Home was entered, left
  (home:route-claim-unfulfilled) and re-armed again: 32 round trips per run, the sales that free
  the pack never reached;
* the swap's ``pack-space-required:4`` (a swap Home does not serve: nothing is shelved before it)
  counted as outstanding equipment work and widened Home's bound to 300.

Owner 2026-11-03 「取り置きを使ってよい・そのために売ったり仕舞ったりしない・それより詰まっていたら
待つ」 and owner 2026-11-13 (round trips are fixed by the owner registered in the mechanism, no
counters): Home is due only while the take fits, the binder keeps Home's mark when it does not,
and a pack-space-only swap Home does not relieve keeps the ordinary Home bound.

Recorded: n1-a life-532's town-arrival checkpoint (tests/fixtures/n1a-532-home-curse-take-1122,
rows 0-28), decided through the public ``choose_key`` with the recorded keys posted.

DECLARED CONSTRUCTED: the character calibration adopted at row 7 (the dump the live bot read
after row 6's ``C-f`` is not in the checkpoint): the arrival's own calibration with its pinned
identity moved to the amulet as inscribed at row 5 (fixture
``character-calibration-lv24-heavy-curse.json``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_target
from hengbot.model import STORE_HOME
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import TOWN_STOP_PASS_LIMIT
from hengbot.town_pack_budget import home_take_fits
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-532-home-curse-take-1122"
CALIBRATION_ROW = 7
PURCHASE_DONE_ROW = 27
BOARD_ROW = 28
SALE_STORES = {0, 5}


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def _decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        return policy.choose_key(board)


class HomeCurseTakeWaitsRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        with contextlib.redirect_stdout(io.StringIO()):
            policy, cls.journal, steps = load(FIXTURE, scratch)
        cls.replayed = {}
        for recorded, supply in steps[:BOARD_ROW]:
            board = supply()
            if recorded["row"] == CALIBRATION_ROW:
                # DECLARED CONSTRUCTED (module docstring): row 6's dump, read live after its post.
                adopt_calibration(
                    policy, FIXTURE / "character-calibration-lv24-heavy-curse.json", scratch)
                policy._calibration_rejection = None
                policy._calibration_unavailable_reason = None
                equipment_target.invalidate_loadout_search(policy)
            key = _decide(policy, board)
            cls.replayed[recorded["row"]] = ((key, policy.last_reason),
                                             (recorded["key"], recorded["reason"]))
            _post(policy, recorded["key"])
        cls.policy = policy
        cls.board = steps[BOARD_ROW][1]()
        cls.reserve = policy._home_remove_curse_scroll(cls.board)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.needs = [(need.store_type, need.category)
                         for need in policy._town_need_candidates(cls.board)]
        cls.home_limit = policy._town_store_visit_limit(STORE_HOME)
        cls.key = _decide(policy, cls.board)
        cls.reason = policy.last_reason
        plan = policy._town_errand_plan
        cls.plan = (tuple(plan.stops), plan.index) if plan is not None else None

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_record(self):
        # Rows 0-5 and 9-27 replay as recorded; rows 6-8 now head for the Alchemist at once
        # (Home is no longer the plan's first stop; the record went Home, then there).
        for row, (decided, recorded) in self.replayed.items():
            if not 6 <= row <= 8:
                self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[PURCHASE_DONE_ROW]["reason"], "shop:in-store-done")
        self.assertEqual((self.journal[BOARD_ROW]["key"], self.journal[BOARD_ROW]["reason"]),
                         ("9", "shop:approach"))

    def test_the_home_reserve_does_not_fit_the_pack(self):
        self.assertEqual(len(self.board.inventory), 22)
        self.assertIsNotNone(self.reserve)
        self.assertEqual(self.reserve.name.split("の巻物")[0], "*解呪*")
        self.assertFalse(home_take_fits(self.board, self.reserve, 1, policy=self.policy))
        cursed = [item for item in self.board.equipment if item.is_cursed]
        self.assertEqual([item.slot for item in cursed], ["neck"])

    def test_home_is_not_due_and_the_sales_lead(self):
        # Before: (7, 'home-star-remove-curse-use') first, the plan [7, 0, 5].
        self.assertNotIn((STORE_HOME, "home-star-remove-curse-use"), self.needs)
        self.assertIn((5, "organization-sale"), self.needs)
        self.assertEqual(self.reason, "shop:approach")
        stops, index = self.plan
        self.assertNotIn(STORE_HOME, stops[index:])
        self.assertIn(stops[index], SALE_STORES)

    def test_a_pack_space_only_swap_keeps_the_ordinary_home_bound(self):
        # Before: 300 (CALIBRATION_HOME_VISIT_LIMIT) for pack-space-required:4.
        preparation = equipment_target.loadout_target(self.policy)
        self.assertEqual(tuple(preparation.blockers), ("pack-space-required:4",))
        self.assertEqual(self.home_limit, TOWN_STOP_PASS_LIMIT)

    def test_the_binder_keeps_homes_mark_while_the_take_does_not_fit(self):
        # Before: _rearm_town_store_for_new_work(STORE_HOME) ran first and dropped the mark.
        policy = self.policy
        saved_plan, saved_attempted = policy._town_errand_plan, dict(policy._town_store_attempted)
        try:
            policy._town_errand_plan = None
            policy._town_store_attempted[STORE_HOME] = self.board.turn
            policy._bind_home_star_remove_curse_withdrawal(self.board)
            self.assertEqual(policy._town_store_attempted.get(STORE_HOME), self.board.turn)
            self.assertIsNone(policy._home_pending_item)
        finally:
            policy._town_errand_plan = saved_plan
            policy._town_store_attempted.clear()
            policy._town_store_attempted.update(saved_attempted)


if __name__ == "__main__":
    unittest.main()
