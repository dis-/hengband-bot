"""n1-a life-535: the Magic shop's Identify staff, wanted by the planner, refused by the page (2026-11-22 16:44).

n1-a life-535 (Lv25 warrior, bot-8e57c07f2) stopped on ``town:blocked:stage-deadline:buy``.  The
visit bought two *鑑定* scrolls (5,016 gold of 6,689), the 1,673 gold left opened the fundraising
set (``prepare``), and only ``identify_staff_ready`` (15 of 20 charges) held the departure.  The
planner filed the Magic shop's 鑑定の杖 (16回分, 904 gold) for it
(``_fundraising_identify_staff_only_block``); on the shop page the selector, reading the same
block, saw nothing wanted (``shop:observe-and-leave``), and the walk re-entered the shop 17 times.

The two readers asked the departure gate at different points of one decision.  Home held a
鑑定の巻物 (deposited at row 10), so the observation re-armed ``_home_candidate_waiting`` on every
board (``_home_identification_candidate_pending``: an Identify source at Home); the town key
releases that latch as stale (no pending take, no identification need, the Home scan complete)
just before the departure gate.  The planner read the gate after the release
(``home_candidate_resolved`` true, the block held); the store page's selector read it before
the release (unresolved, the block failed, the set's purchase order reached no staff).

Fix: the gate's ``home_candidate_resolved`` answers a latch the release would drop as resolved
on every read (``_home_candidate_waiting_stale``, the release's own predicate), so the page buys
what the planner walked to.

Recorded (tests/extract_n1a_535_identify_staff_buy_1122_fixture.py): the stop's incident
capture's town-arrival checkpoint and the journal's rows 0-29, replayed through the public
``choose_key`` (recorded keys posted).  Rows 0-28 decide as recorded; row 29 is the first Magic
shop page after the set opened.

DECLARED CONSTRUCTED:

* the character dump: the replay cannot receive the game's ``C-f`` file, so after each recorded
  ``periodic:character-dump`` the arrival's dump bytes are written again (as
  tests/test_n1a_534_light_flipflop_1122_recorded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.policy  # noqa: F401 -- import order (circular import when run alone)
from hengbot.model import STORE_MAGIC, SV_STAFF_IDENTIFY, TVAL_STAFF
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-535-identify-staff-buy-1122"
PAGE_ROW = 29
STAFF = "鑑定の杖 (16回分)"


def _quiet(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args, **kwargs)


class IdentifyStaffBuyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        policy, journal, steps = _quiet(load, FIXTURE, Path(cls.scratch.name))
        cls.addClassCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        dump = Path(policy._character_dump_path).read_bytes()
        cls.decided = []
        for recorded, supply in steps[:PAGE_ROW]:
            board = supply()
            key = _quiet(policy.choose_key, board)
            cls.decided.append((recorded["row"], policy.last_reason, key))
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
            if recorded["reason"] == "periodic:character-dump":
                # DECLARED CONSTRUCTED (module docstring): the game writes the dump.
                Path(policy._character_dump_path).write_bytes(dump)
        cls.policy, cls.journal = policy, journal
        cls.page = steps[PAGE_ROW][1]()

    def test_recorded_rows(self):
        reasons = [entry["reason"] for entry in self.journal]
        self.assertEqual(reasons[20:22], ["shop:in-store-buy", "shop:in-store-buy"])
        self.assertEqual(reasons[27:30], [
            "home:leave-after-one-operation", "shop:travel", "shop:observe-and-leave"])
        self.assertEqual(self.page.store.store_type, STORE_MAGIC)
        self.assertEqual(self.page.player.gold, 1673)
        self.assertIn(STAFF, [item.name for item in self.page.store.items])
        self.assertEqual(sum(item.charges for item in self.page.inventory
                             if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY), 15)

    def test_rows_before_the_page_decide_as_recorded(self):
        self.assertEqual([(row, reason, key) for row, reason, key in self.decided],
                         [(entry["row"], entry["reason"], entry["key"])
                          for entry in ({"row": row, **self.journal[row]} for row in range(PAGE_ROW))])

    def test_the_stale_latch_is_resolved_before_the_release(self):
        """Home's 鑑定の巻物 re-arms the latch on the page; the gate already answers resolved."""
        policy, page = self.policy, self.page
        held = policy._home_candidate_waiting
        try:
            policy._home_candidate_waiting = True  # as the page's observation leaves it
            self.assertTrue(policy._home_candidate_waiting_stale(page))
            failed = {name for name, ready in
                      policy._recall_town_departure_conjuncts(page, commit=False).items() if not ready}
            self.assertEqual(failed, {"identify_staff_ready"})
            self.assertTrue(policy._fundraising_identify_staff_only_block(page))
        finally:
            policy._home_candidate_waiting = held

    def test_the_page_buys_the_staff_the_planner_walked_to(self):
        """Row 29: bot-8e57c07f2 left the page here (``shop:observe-and-leave``, nothing wanted)."""
        key = _quiet(self.policy.choose_key, self.page)
        self.assertEqual(self.policy._fundraising_mode, "prepare")
        self.assertEqual((self.policy.last_reason, key), ("shop:in-store-buy", "pj\r"))
        bought = next(item for item in self.page.store.items if item.letter == "j")
        self.assertEqual(bought.name, STAFF)


if __name__ == "__main__":
    unittest.main()
