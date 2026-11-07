"""D61: the 2026-11-01 21:01 n1-c life-098 Outpost visit (Magic-Eater Lv26, bot-64e63b6cf).

Every town visit from 21:01 on ended the same way (decisions 22938-23131):
home:route-claim-unfulfilled -> town-progress-invariant:boxed-breakout-travel
-> shop:observe-and-leave / breakout:least-visited -> stuck:wander (x31,
x46, x60 ...), town:cycle-break, town:repetition-required-shopping, and the
visit left only through town:repetition-depart:recall.  Departure failed
home_candidate_resolved alone.

The catalogued-withdrawal binder (policy_home
_bind_catalogued_home_identification_withdrawal, 407ea7bae 「魔法道具も自宅
に預ける」) filed a home-errand take of an unknown staff shelved at Home
(identification-catalog; the absorbed Identify power is the carried source).
Every arrival at Home is inside the store: the travel command and a step
onto the entrance both enter it.  The open Home page handed off only the
queued item, batch and posted atomic take to the outside composer, so the
errand's take was never composed; the page closed as
home:route-claim-unfulfilled, Home was marked attempted and its approach
dropped, while the errand kept the Home candidate latch open.

The test attaches the recorded board to the established static-game policy
helper (tests/test_unid_deposit_recorded.py, DECLARED RECONSTRUCTED: the
arrival board primes it and the visit's observed pages and Home answers are
consumed through the production response consumer).  Fixture:
tests/extract_n1c_town_wander_1101_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_capability, me_staff_sequence
from hengbot.model import TVAL_STAFF
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.test_esp_threat_rest_recorded import EDIT
import tests.test_unid_deposit_recorded as recorded


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-town-wander-1101.json.gz"
# The shelved unknown staff the errand takes (Home item H of the ~9 answer).
SHELVED_STAFF = (TVAL_STAFF, 2)
LOOP = ("home:route-claim-unfulfilled", "stuck:wander", "breakout:")


class TownWanderRecordedTest(recorded.UnidentifiedDepositRecordedTest):
    """The open Home page hands the filed errand's take to the entrance."""

    board_name = "left-home"

    # The inherited life-427 scenarios belong to their own fixture.
    test_recorded_stop = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.recorded_case = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        case = self.recorded_case
        board = case["boards"][self.board_name]
        # The boundary consumes the visit's answers observed before the board.
        self.case = dict(case, board=board, observations=[
            row for row in case["observations"] if row["turn"] < board["turn"]])
        super().setUp()
        # The replies answer a later entry with the page that pass observed.
        for row in case["observations"]:
            if row["type"] == "store":
                self.pages.setdefault(row["store"]["store_type"], copy.deepcopy(row["store"]))

    def boundary(self):
        policy, raw = super().boundary()
        # DECLARED RECONSTRUCTED from the life's 20:02 policy-state.json: the
        # staff sequence's absorption record and the power list read in this
        # process.  The carried Stone to Mud wands are recorded as absorbed:
        # the visit made no staff-sequence (Tower) decision, which with the
        # wand not absorbed it would have (me_device_policy charge_first; since
        # owner 2026-11-07 also with the kind absorbed below the count cap, so
        # the count is declared at the cap).
        sequence = self.case["me_staff_sequence"]
        record = me_staff_sequence.state(policy)
        record.absorbed = {int(sval): count for sval, count in sequence["absorbed"].items()}
        record.absorbed[me_capability.record_key("wand", 6)] = 99
        record.stage = sequence["stage"]
        record.powers_read = True
        return policy, raw

    def test_recorded_loop(self):
        decisions = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual(decisions[22938]["reason"], "home:route-claim-unfulfilled")
        self.assertEqual(decisions[22938]["claim"]["visit_requester"], "home-errand")
        wander = decisions[22962]
        self.assertEqual(wander["reason"], "stuck:wander")
        self.assertEqual(wander["departure_block"]["failed"], ["home_candidate_resolved"])
        self.assertTrue(wander["home_candidate_waiting"])
        self.assertFalse(self.shelved_staff()["known"])

    def shelved_staff(self):
        return next(item for item in self.case["home_answer"]["knowledge"]["items"]
                    if (item["tval"], item["sval"]) == SHELVED_STAFF)

    def test_errand_take_is_composed_at_the_entrance_and_the_visit_departs(self):
        policy, raw = self.boundary()
        raw, reasons = self.drive(policy, raw, limit=30,
                                  done=lambda reason, key: reason.startswith(recorded.DEPARTURE))
        self.assertFalse([reason for reason in reasons if reason.startswith(LOOP)], reasons)
        self.assertIn("home:leave-for-pending-withdraw", reasons)
        self.assertIn("home-errand:atomic-withdraw:identification-catalog", reasons)
        withdrawn = [name for kind, name in self.events if kind == "withdraw"]
        self.assertEqual(withdrawn, [self.shelved_staff()["name"]], self.events)
        self.assertEqual(self.events[self.events.index(("withdraw", withdrawn[0])) + 1],
                         ("identify", withdrawn[0]))


if __name__ == "__main__":
    import unittest
    unittest.main()
