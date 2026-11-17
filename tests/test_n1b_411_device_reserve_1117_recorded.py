"""n1-b life-411 2026-11-17: a table device at the Black Market keeps the departure reserve.

After the Castle-dive fix (b795de32c) the character was resumed at 13:37:19 and mined the Yeek
cave 1F instead of recalling to the Castle.  No no-safe-destination set was open: the restored
policy held no fundraising (``_fundraising_mode`` None, ``_no_safe_destination_set`` False).  The
character held 2,000 gold, under the 3,000 poverty line (FUNDRAISING_START_GOLD), so the
ordinary poverty fundraising opened on row 5 (policy_shop._next_required_store_type ->
_start_fundraising) and row 10 walked to the Yeek cave stairs.

The gold went at the Black Market of the 13:08 visit: the device policy table's rung
(me-device:policy, owner 2026-10-31 「2本目以降も買う」) bought 衝撃の魔法棒 (31,808) and 力の杖
(31,015), leaving 1,721 against a full departure resupply of 5,244.  Its only gold check was
me_staff_sequence.spare_gold (the unmet supplies), not owner 2026-10-08 「必需品1回分の補充代を
残す」, which the Black Market's own optional picks keep (_black_market_optional_reserve_cap);
owner 2026-11-16 reads this rung as 「余った資金で ... 買う」.  Now a table device at the Black
Market leaves the reserve (me_device_policy._black_market_reserve_kept): the 力の杖 is not bought,
32,736 gold stay, and the visit's departure reaches the unsafe-recall fallback's Castle dive
(test_n1b_411_castle_dive_1117_recorded).

Recorded: the 13:08:41 checkpoint (tests/fixtures/n1b-411-castle-dive-1117, rows 0-18) and the
13:37:21 resumed checkpoint (tests/extract_n1b_411_resume_poverty_1117_fixture.py, rows 0-10),
both replayed through the public choose_key with the recorded keys posted.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import FUNDRAISING_START_GOLD
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
VISIT_1308 = FIXTURES / "n1b-411-castle-dive-1117"
RESUMED = FIXTURES / "n1b-411-resume-poverty-1117"
STAFF_ROW = 18  # recorded 'pD\r' shop:in-store-buy, 力の杖 (3回分) at 31,015
SHOCK_ROW = 17  # recorded 'pA\r' shop:in-store-buy, 衝撃の魔法棒 (4回分) at 31,808


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def replay(fixture, scratch, rows):
    policy, journal, steps = load(fixture, scratch)
    decided = []
    for recorded, supply in steps[:rows]:
        board = supply()
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        decided.append(((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                         board, policy._fundraising_mode, policy._no_safe_destination_set))
        post(policy, recorded["key"])
    return policy, journal, decided


class N1b411DeviceReserveRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        root = Path(cls.scratch.name)
        cls.visit, _journal, cls.visit_rows = replay(VISIT_1308, root / "visit", STAFF_ROW + 1)
        cls.resumed, cls.resumed_journal, cls.resumed_rows = replay(RESUMED, root / "resumed", 11)

    @classmethod
    def tearDownClass(cls):
        for policy in (cls.visit, cls.resumed):
            policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_a_the_resumed_board_fundraises_for_poverty_not_a_stale_set(self):
        for row, (decided, recorded, *_rest) in enumerate(self.resumed_rows):
            self.assertEqual(decided, recorded, row)
        first = self.resumed_rows[0]
        self.assertEqual(first[2].player.gold, 2000)
        self.assertLess(first[2].player.gold, FUNDRAISING_START_GOLD)
        self.assertEqual(first[3:], (None, False))  # no fundraising open on the arrival
        self.assertEqual(self.resumed_rows[5][3:], ("prepare", False))  # the poverty set
        self.assertEqual(self.resumed_journal[10]["reason"], "seek-downstairs")

    def test_b_the_shock_wand_still_leaves_the_reserve(self):
        decided, recorded, board, *_rest = self.visit_rows[SHOCK_ROW]
        self.assertEqual(decided, recorded)
        reserve = self.visit._full_departure_resupply_reserve(board)
        self.assertEqual(reserve, 5244)
        self.assertGreaterEqual(board.player.gold - 31808, reserve)

    def test_c_the_staff_that_spends_the_reserve_is_not_bought(self):
        decided, recorded, board, *_rest = self.visit_rows[STAFF_ROW]
        self.assertEqual(recorded, ("pD\r", "shop:in-store-buy"))
        self.assertEqual(board.player.gold, 32736)
        self.assertNotEqual(decided, recorded)
        self.assertEqual(decided, ("\x1b", "shop:in-store-done"))


if __name__ == "__main__":
    unittest.main()
