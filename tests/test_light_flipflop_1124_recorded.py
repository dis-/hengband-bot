"""A process started in town reads the absorbed-power lists before the visit's loadout (n1-c life-221).

n1-c life-221 2026-11-24 04:54-04:58 (build 5a0bd46c0, a process started in town): the visit's
first loadout search (04:55:12, ``visit-start``) ran with no absorbed-power list read, so
me_capability ``reliable`` read the absorbed *Destruction* (64 charges, 97%) as no means; the
target took ★パランティアの石 and a Ring of Speed off for ★飛行石 and the Ring of Extra Attacks.
The periodic browse (``bA``, row 36) then showed the power, the visit decided again on
``destruction-means-gained`` and put both back (04:55:32), and the 99F/100F preparation phase's
own swap (04:58:37, its loadout step: owner 2026-11-20 Q9) took ★飛行石 again: the third change of
the light stopped the bot as ``town:blocked:equipment-slot-flipflop:light``.  Owner 2026-11-22 Q1
(verbatim) 「全部位を決め直す。鑑定するイベントは1回なのに往復するほうがおかしい」: one visit, one
verdict per slot.  The turn-free read of a restarted process's missing lists
(me_powers_refresh ``resume_read_key``) was asked on dungeon boards only.

Recorded (tests/extract_light_flipflop_1124_fixture.py, ``n1c-221-light-flipflop-1124``): the
town-arrival checkpoint of 04:54:53 (turn 5554134).  Row 0 is decided as recorded; row 1 now
browses the staff list first.

DECLARED CONSTRUCTED: each browse's answer is the recorded board of the next row with the list
the game showed for that kind later in the same visit (the boards of rows 37, 40 and 43, the
answers of the recorded browses ``bA``, ``bB``, ``bC``) put on it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_means, equipment_target
from hengbot.me_powers_refresh import REFRESH_REASON
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

TOWN = Path(__file__).with_name("fixtures") / "n1c-221-light-flipflop-1124"
ANSWERS = {"A": 37, "B": 40, "C": 43}  # the recorded browses' answer rows: staff, wand, rod


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class LightFlipflop1124RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, _journal, self.steps = load(TOWN, Path(scratch.name))
        self.lists = {letter: self.steps[row][1]().magic_eater_power_list
                      for letter, row in ANSWERS.items()}

    def decide(self, board):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.policy.choose_key(board), self.policy.last_reason

    def test_the_lists_are_read_before_the_visit_decides(self):
        recorded, supply = self.steps[0]
        self.assertEqual(self.decide(supply()), (recorded["key"], recorded["reason"]))
        post(self.policy, recorded["key"])
        # Recorded: ('~9\x1b\x1b', 'home:request-knowledge-scan'), the lists unread until row 36.
        self.assertEqual(self.decide(self.steps[1][1]()), ("bA", REFRESH_REASON))
        self.assertIsNone(equipment_target.loadout_target_result(self.policy))  # no search yet

    def test_the_visit_keeps_the_worn_light_and_rings(self):
        row, answer, board, target = 0, None, None, None
        for _ in range(12):
            board = self.steps[row][1]()
            if answer is not None:
                board = dataclasses.replace(board, magic_eater_power_list=self.lists[answer])
                answer = None
            key, reason = self.decide(board)
            if reason == REFRESH_REASON:
                answer = key[1]
                post(self.policy, key)
                continue
            target = getattr(getattr(equipment_target.loadout_target(self.policy), "result", None),
                             "best", None)
            if target is not None:
                break
            post(self.policy, self.steps[row][0]["key"])
            row += 1
        self.assertIsNotNone(target)
        self.assertTrue(destruction_means.Means(self.policy, board).optimizer_without_gear())
        chosen = dict(target.loadout.slots)
        # Recorded 04:55:12: the light and the main ring from the Home (★飛行石, the Ring of Extra
        # Attacks), put back at 04:55:32 once the list was read.
        for slot in ("light", "main_ring", "sub_ring"):
            with self.subTest(slot=slot):
                self.assertEqual(chosen[slot].origin, "equipped")


if __name__ == "__main__":
    unittest.main()
