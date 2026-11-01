"""town-mining-dive-yield-1102: the n1-a life-464 town stop (2026-11-02 05:49).

Owner 2026-11-02 「満たせなければ採掘を1サイクル行い再度トライ。条件未達の出発は
拒否する。」.  n1-a life-464 (warrior Lv38, 41,715 gold, build bot-10ac9173a)
ended its Outpost visit with four departure conditions unmet; the town end
started one mining cycle (decision 5453, ``town:end-mining-cycle``, the
fundraising set in preparation mode).  The cycle's kit was short (Treasure
Detection 0/1, a second digger 1/2), but on the next board (decision 5454)
nothing bought it: the preparation's shop needs are planned only while
``fundraising_active``, which a character above FUNDRAISING_GOLD_TARGET
(15,000) meets only through the time-pass runs listed there, and the town
end's cycle was not one of them.  With no town claim left, the dive
departure's judgment (policy_town ``_town_special_key``) read the unmet
recall conditions again and stopped on ``town:blocked:departure-unsatisfiable``.

The town end's cycle now plans its kit at any gold, like the other
time-pass runs, and while the cycle is open the dive departure's judgment
yields: the cycle's departure is the mining walk-in, which keeps its own
gates (town_end_mining); a kit that cannot be had ends in the town end's
named stop.

Fixture: tests/fixtures/town-mining-dive-yield-1102.json.gz
(tests/extract_town_mining_dive_yield_1102_fixture.py).  The decision is the
public ``choose_key`` and its key goes through the production executor port.
DECLARED RECONSTRUCTED: the cycle is started by the production
``town_end_mining.start`` on the recorded start board with the checkpoint's
unmet conditions and visit epoch, the visit's departure record names the
recorded cause (departure-unsatisfiable), and the visit ledger's store
visits and need attempts are the stop row's ``departure_block.town_ledger``.
Not reconstructed: the visit's closed routes (the recorded stop row has no
live town claim); the new process still routes its own Home need first, so
the drive pins the cycle's kit needs on the stop board, not the stop itself.
DECLARED CONSTRUCTED: the replies to the knowledge re-requests ('~f', '~9')
are the visit's recorded skill and Home rows; the executor's board after the
posted key is the stop board ten game turns later.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import town_end_mining
from hengbot.model import _parse_items, parse_snapshot
from tests import test_d57_nav_depth_1101_recorded as nav
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_surface_map_walks import _town_maps


FIXTURE = Path(__file__).with_name("fixtures") / "town-mining-dive-yield-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
START, STOP = CASE["boards"]
STOP_REASON = "town:blocked:departure-unsatisfiable"
CAUSE = "departure-unsatisfiable"
KIT_NEEDS = {"fundraising-detection", "mining-detection"}


def recorded(sequence):
    return next(row for row in CASE["decisions"] if row["decision_sequence"] == sequence)


class TownEndMiningCycleRecordedTest(nav.RecordedDrive):
    def test_recorded_rows_start_the_cycle_then_stop(self):
        start, stop = recorded(5453), recorded(5454)
        self.assertEqual(start["reason"], "town:entrance-step-off:town:end-mining-cycle")
        self.assertEqual(stop["reason"], STOP_REASON)
        self.assertEqual(stop["fundraising"]["mode"], "prepare")
        self.assertEqual(stop["departure_block"]["town_claims"], [])
        self.assertEqual(tuple(stop["departure_block"]["failed"]), tuple(CASE["cycle"]["unmet"]))
        self.assertGreater(STOP["player"]["gold"], 15000)
        missing = {row["item"] for row in stop["procurement_requirements"]}
        self.assertIn("Treasure Detection scrolls", missing)

    def new_policy(self):
        policy = loops.new_policy(dict(boards=[START], home=CASE["home"]), CASE["skill"],
                                  monraces={})
        policy._town_maps = _town_maps()
        policy._town_map = policy._town_maps[0]
        ledger = recorded(5454)["departure_block"]["town_ledger"]
        policy._town_visit_ledger.store_visits.update(
            {int(store): count for store, count in ledger["store_visits"].items()})
        policy._town_visit_ledger.need_attempts.update(ledger["need_attempts"])
        policy._town_visit_epoch = CASE["visit_epoch"]
        policy._visit_departure_recorded.add(CAUSE)
        board = parse_snapshot(copy.deepcopy(START), policy._monrace_knowledge)
        town_end_mining.start(policy, board, tuple(CASE["cycle"]["unmet"]))
        policy._town_blocked_reason = None  # force_visit_departure after the start
        return policy

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        for _ in range(3):
            key = str(policy.choose_key(board))
            if key.startswith("~f"):
                policy.consume_skill_knowledge(dict(copy.deepcopy(CASE["skill"]), turn=raw["turn"]))
            elif key.startswith("~9"):
                policy.consume_home_knowledge(
                    tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
            else:
                return key
        return key

    def test_the_cycle_plans_its_kit_instead_of_stopping(self):
        policy = self.new_policy()
        self.assertTrue(town_end_mining.outstanding(policy))
        key = self.decide(policy, STOP)
        self.assertNotEqual(policy.last_reason, STOP_REASON)
        self.assertFalse(policy.last_reason.startswith("town:blocked:"), policy.last_reason)
        board = parse_snapshot(copy.deepcopy(STOP), policy._monrace_knowledge)
        needs = {need.category for need in policy._town_need_candidates(board)}
        self.assertTrue(KIT_NEEDS <= needs, needs)
        following = dict(copy.deepcopy(STOP), turn=STOP["turn"] + 10, messages=[])
        self.send(policy, STOP, key, following, {})
        self.assertTrue(town_end_mining.outstanding(policy))


if __name__ == "__main__":
    unittest.main()
