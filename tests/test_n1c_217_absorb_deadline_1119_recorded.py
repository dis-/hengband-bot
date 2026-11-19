"""n1-c life-217 2026-11-19 17:53:43, town:blocked:stage-deadline:quest (bot main 00a79d9dc0).

The Magic-Eater came home with fifteen Home devices its table absorbs (item_fate ABSORB, owner
2026-11-19 「魔法道具を自宅にため込んでいる。魔道具術師の処理ルールに従って処分」).  Two faults stopped
the visit after twelve absorptions:

1. One stack per Home trip: take ('5pS'), absorb ('Gi'), wait, a Home census ('~9'), leave,
   the next take.  me_device_policy.home_absorb_takes gave nothing while a carried copy waited,
   so the absorption came between the takes.  Now the takes come first, one after another while
   the pack and its weight limit take them, the last shelf slot first so no census is needed
   between them (``next_home_absorb_take``), and the town absorbs the carried copies once no
   more is taken (``town_absorb_candidate``).
2. The stage deadlines (town_visit_plan): each absorption (magic_eater.absorb_key, the quest
   stage) changed the pack, but its board was seen after the next wait (an interrupt), so the
   restart of the stage whose decision showed new work never reached the quest count: 12, the
   quest deadline.  Now while the absorption is open (me_device_policy.absorb_errand_open) each
   observed new work state restarts its stages' counts (``ABSORB_STAGES``); an absorption that
   shows no new work still spends them.

Recorded: the stop's town-arrival checkpoint and all 65 journal rows
(tests/extract_n1c_217_absorb_deadline_1119_fixture.py).  Rows 0-2 are decided through the public
choose_key and compared with the record (row 2 the first take).  The deadline accounting is run
over the recorded rows themselves, as the live bot counted them.

DECLARED CONSTRUCTED: after row 2, the boards the game would show: each take's stack added to the
pack, each absorbed stack removed (the pack relettered), the turn advanced; and for the stall,
every board from row 5 on a repeat of the one before it; row 64 asked as the absorption the stop
replaced.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import item_fate, me_device_policy, town_visit_plan
from hengbot.town_visit import town_visit
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-absorb-deadline-1119"
FIRST_TAKE, STOP_ROW = 2, 64
TAKE, ABSORB = "home:atomic-withdraw", "magic-eater:absorb"
# Row 64's decision the stop replaced: the absorption of the stack row 63 took.
ABSORB_DECISION = ("Gi", ABSORB)


def absorbing(policy, board):
    """A carried copy waits for the town's absorption, or a Home stack's fate is ABSORB."""
    return (any(me_device_policy.absorbed_in_town(policy, board, item) for item in board.inventory)
            or any(item_fate.fate(policy, board, item, item_fate.SHELF) == item_fate.ABSORB
                   for item in policy._home_knowledge_items))


def accounting(fixture_rows, policy, *, stall_from=None):
    """The stage deadline over the recorded rows; (stop row, stop)."""
    previous = None
    for row, (recorded, supply) in enumerate(fixture_rows):
        board = supply()
        if stall_from is not None and row >= stall_from:
            board = previous
        previous = board
        town_visit_plan.note_observed_progress(policy, board)
        key, reason = ABSORB_DECISION if row == STOP_ROW else (recorded["key"], recorded["reason"])
        policy.last_reason = reason
        stop = town_visit_plan.stage_deadline_stop(policy, board, key)
        if stop is not None or row == STOP_ROW:
            return row, stop
        town_visit_plan.note_decision(policy, board, key)
    return None, None


class N1c217AbsorbDeadline1119RecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, self.journal, self.steps = load(FIXTURE, Path(self.scratch.name))

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_recorded_visit_stopped_at_the_quest_deadline(self):
        self.assertEqual(self.journal[STOP_ROW]["reason"], "town:blocked:stage-deadline:quest")
        self.assertEqual(town_visit_plan.STAGE_DEADLINES["quest"], 12)
        self.assertEqual(sum(row["reason"] == ABSORB for row in self.journal), 12)

    def test_an_absorption_that_keeps_going_spends_no_deadline(self):
        self.assertEqual(accounting(self.steps, self.policy), (STOP_ROW, None))

    def test_an_absorption_that_shows_no_new_work_still_stops(self):
        row, stop = accounting(self.steps, self.policy, stall_from=5)
        self.assertIsNotNone(stop)
        self.assertLess(row, STOP_ROW)

    def run_visit(self):
        """Rows 0-2 as recorded, then the constructed boards; [(key, reason)] after row 2."""
        policy = self.policy
        for row, (recorded, supply) in enumerate(self.steps[:FIRST_TAKE + 1]):
            board = supply()
            before = copy.copy(policy._store_visit)
            self.assertEqual((policy.choose_key(board), policy.last_reason),
                             (recorded["key"], recorded["reason"]), row)
            post(policy, board, recorded["key"], before)
        board = self.steps[FIRST_TAKE + 1][1]()
        decided = []
        self.taken = [self.journal_take_name(board)]
        for _ in range(60):
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            reason = policy.last_reason
            taken = policy._home_pending_item or (policy._home_atomic_withdraw_pending or (None,))[0]
            decided.append((key, reason))
            post(policy, board, key, before)
            inventory = board.inventory
            if reason == TAKE:
                item = next(item for item in policy._home_knowledge_items
                            if policy._item_signature(item) == taken)
                inventory = (*inventory, item)
                self.taken.append(item.name)
            elif reason == ABSORB:
                inventory = tuple(item for item in inventory if item.slot != key[1])
            board = replace(board, turn=board.turn + 10, inventory=tuple(
                replace(item, slot=chr(ord("a") + index)) for index, item in enumerate(inventory)))
            if not absorbing(policy, board):
                break
        return board, decided

    def journal_take_name(self, board):
        """Row 2's take, carried on row 3's board: the Staff of Earthquakes."""
        return next(item.name for item in board.inventory if item.name.startswith("地震の杖"))

    def test_the_takes_come_one_after_another_then_the_absorptions(self):
        board, decided = self.run_visit()
        reasons = [reason for _, reason in decided]
        # The first take is followed by the next take, not by the absorption or a census.
        self.assertEqual(reasons[0], TAKE)
        first_absorb = reasons.index(ABSORB)
        self.assertGreaterEqual(reasons[:first_absorb].count(TAKE), 9)
        self.assertNotIn("home:request-knowledge-scan", reasons[:first_absorb])
        # Every Home device the table absorbs is taken and absorbed (the recorded first take,
        # the 地震の杖, and fourteen more), with no stage deadline on the way.
        self.assertEqual(reasons.count(TAKE) + 1, 15)
        self.assertEqual(reasons.count(ABSORB), 15)
        self.assertFalse(any(reason.startswith(town_visit_plan.STAGE_DEADLINE_STOP_PREFIX)
                             for reason in reasons))
        policy = self.policy
        self.assertFalse(absorbing(policy, board))
        self.assertLess(town_visit(policy).stage_decisions.get("quest", 0),
                        town_visit_plan.STAGE_DEADLINES["quest"])


if __name__ == "__main__":
    unittest.main()
