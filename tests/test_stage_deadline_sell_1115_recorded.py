"""A stage that keeps completing its work does not spend its deadline (owner 2026-11-15).

Recorded: n1-b life-397 (2026-11-15 00:48:40, Magic-Eater Lv47) stopped at
town:blocked:stage-deadline:sell in the middle of a run of sales: inscribe and sell, one item
after another, each sale raising the gold (rows 186-202).  The town-arrival checkpoint,
journal rows and sidecar files (tests/extract_stage_deadline_sell_1115_fixture.py) replay
through the public choose_key with the recorded keys posted.  On the stop row (203) the sell
stage, whose count restarted at each observed sale (town_visit_plan.note_observed_progress),
takes its next action instead: it leaves the store, the sales done (shop:in-store-done).

DECLARED: rows 169-185 are posted with their recorded keys.  They follow the periodic
character dump of row 164 (and the dumps of rows 170, 176 and 178), whose dump file the
game wrote on the viewing server and no capture keeps; without it the replayed calibration
stays required after each stat-restore potion, the shop-buy owner's progress vector repeats
and the arbiter retires it (town:blocked:owner-retired on row 169), on main as on this
change.  The live bot bought and quaffed there.  Rows 0-168 and 186-202 replay as recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import town_visit_plan
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "stage-deadline-sell-1115"
STOP = "town:blocked:stage-deadline:sell"
STOP_ROW = 203
DUMP_GAP = range(169, 186)
SALE_RUN = range(186, 203)


class StageDeadlineSell1115RecordedTest(unittest.TestCase):
    def test_n1b_397_sale_run_goes_on(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _recorded, steps = load(FIXTURES / "n1b397", Path(scratch.name))
        self.assertEqual(len(steps), STOP_ROW + 1)
        self.assertEqual(steps[STOP_ROW][0]["reason"], STOP)
        sell_counts = []
        for index, (row, supply) in enumerate(steps):
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(supply())
            decided = (key, policy.last_reason)
            sell_counts.append(policy._town_visit.stage_decisions.get("sell", 0))
            if index == STOP_ROW:
                break
            if index in DUMP_GAP:
                key = row["key"]
            else:
                self.assertEqual(decided, (row["key"], row["reason"]), index)
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        self.assertEqual(decided, ("\x1b", "shop:in-store-done"))
        self.assertFalse(policy.last_reason.startswith(town_visit_plan.STAGE_DEADLINE_STOP_PREFIX))
        # The visit's sell operations pass the deadline; the count since the
        # last observed sale stays far below it.
        traced = sum(segment[3] for segment in policy._town_visit.plan_segments
                     if segment[0] == "sell")
        self.assertGreaterEqual(traced, town_visit_plan.STAGE_DEADLINES["sell"])
        self.assertLessEqual(max(sell_counts[index] for index in SALE_RUN), 2)
        self.assertLess(max(sell_counts), town_visit_plan.STAGE_DEADLINES["sell"])


if __name__ == "__main__":
    unittest.main()
