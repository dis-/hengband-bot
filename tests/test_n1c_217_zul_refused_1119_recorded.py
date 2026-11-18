"""In Zul a '<' refused for an unseen monster waits a turn instead of stopping (n1-c life-217).

n1-c life-217 (Magic-Eater Lv35, build bot-febdf2f35) walked from the Outpost to Zul for its
mutation (owner 2026-11-07, zul_trip), had it cured at the Chaos Tower and pressed '<' for the
global map at (21,68) at night.  The game refused it (「敵がすぐ近くにいるときは広域マップに
入れない！」, change_wild_mode: an awake hostile within MAX_PLAYER_SIGHT, seen or not) with
nothing in view or sensed.  The trip left that board to the other owners; the Magic-Eater staff
sequence's leg back to the Outpost is an inn teleport, and Zul has no inn, so it stopped the bot
(2026-11-19 01:14:29, quest:blocked:me-staff, failure
``return-outpost-unavailable:town:zul:enter-global``).  The stop was not about a quest or the
staffs: the quest readiness on the board (Q18) and quest_ranged_force played no part.

Fix (zul_trip ``_wait_refused_key``): in Zul the refused board waits one turn (the board stands
on the Tower's entrance, so the wait is the town's step off it) and '<' is tried again on the
next board; eight waits on one cell end it as before.

Recorded (tests/extract_n1c_217_zul_refused_1119_fixture.py): the policy of the visit's
town-arrival checkpoint (the Outpost, 01:13:42) after its first row, and the stop board itself.
DECLARED RECONSTRUCTED: the Zul trip's state is the stop's (incident policy-state.json
``_zul_trip``: active, start town 3, mutation 33 cured, returning); the walk through the global
map in between had no checkpoint.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence, zul_trip
from hengbot.model import parse_snapshot
from hengbot.policy_constants import STORE_STUCK_LIMIT, UP_STAIRS_KEY, ZUL_TOWN_ID
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-zul-refused-1119"
REFUSED = "敵がすぐ近くにいるときは広域マップに入れない！"


class N1c217ZulRefused1119RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory(prefix="n1c-217-zul-")
        self.addCleanup(scratch.cleanup)
        self.policy, _journal, rows = load(FIXTURE, Path(scratch.name))
        for recorded, supply in rows:
            self.policy.choose_key(supply())
            self.policy.confirm_key_posted(recorded["key"])
        self.raw = json.loads(lzma.decompress((FIXTURE / "stop-board.json.xz").read_bytes()))
        # The stop's trip (policy-state.json ``_zul_trip``).
        self.policy._zul_trip = zul_trip.ZulTrip(
            active=True, start_town=3, curable=(33,), price=5000, cured=1, returning=True)

    def decide(self, raw):
        board = self.policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge))
        return board, self.policy.choose_key(board), self.policy.last_reason

    def test_the_refused_board_waits_instead_of_stopping(self):
        board, key, reason = self.decide(self.raw)
        self.assertEqual(self.policy._effective_town_id(board), ZUL_TOWN_ID)
        self.assertEqual(board.messages, (REFUSED,))
        self.assertEqual((list(board.visible_monsters), list(board.detected_monsters)), ([], []))
        # Before: ('', 'quest:blocked:me-staff'), failure return-outpost-unavailable.
        self.assertTrue(reason.endswith(zul_trip.WAIT_REFUSED_REASON), reason)
        self.assertTrue(key)
        self.assertIsNone(me_staff_sequence.state(self.policy).failure)

    def test_the_next_board_tries_the_global_map_again(self):
        self.decide(self.raw)
        quiet = copy.deepcopy(self.raw)
        quiet["messages"] = []
        _board, key, reason = self.decide(quiet)
        self.assertEqual((key, reason), (UP_STAIRS_KEY, zul_trip.ENTER_GLOBAL_REASON))

    def test_eight_waits_on_one_cell_end_it_as_before(self):
        for _ in range(STORE_STUCK_LIMIT - 1):
            _board, _key, reason = self.decide(self.raw)
            self.assertTrue(reason.endswith(zul_trip.WAIT_REFUSED_REASON), reason)
        _board, key, reason = self.decide(self.raw)
        self.assertEqual((key, reason), ("", me_staff_sequence.STOP_REASON))


if __name__ == "__main__":
    unittest.main()
