"""n1-c life-112 2026-11-03 01:12:32 quest:blocked:me-staff (no-progress:travel).

Back from Angband 16F the Magic-Eater sold, bought and dumped its
character, then read Word of Recall to Angband (decision 4720 ``rea``),
stepped off the entrance (4721) and waited for the recall on (36, 90)
(4722-4728 ``town:wait-recall``).  The staff sequence was in its travel
phase (to the Tower of Sorcery in Morivant) and yielded every one of those
boards (its town leg returns None, _travel), but it still counted each one
on its standstill guard: the eighth board on the cell stopped the bot as
``no-progress:travel`` (4729), and the record's failure stopped the
restarted process twice more until it escalated to a new character.

Pinned through the public choose_key: the yielded boards are not counted,
the recall wait goes on, and its key goes through the production executor.
Fixture: tests/extract_n1c_staff_travel_wait_1103_fixture.py (build
476464048, before c2164a576; the guard is unchanged on main 38c599427).
DECLARED RECONSTRUCTED: the staff sequence record is the stop's
policy-state record without its failure, progress and cell counts.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_staff_sequence as sequence
from tests import test_me_nokey_1031_recorded as _test_me_nokey_1031_recorded
import test_hourly_0700_1102_recorded as _test_hourly_0700_1102_recorded


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-staff-travel-wait-1103.json.gz"
STEP_OFF, STOP = 1287066, 1287139


def _case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class StaffTravelYieldedWaitTest(_test_hourly_0700_1102_recorded.RecordedTownPolicy, _test_me_nokey_1031_recorded.PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.case = _case()

    def policy(self):
        case = self.case
        start = next(raw for raw in case["boards"] if raw["turn"] == STEP_OFF)
        policy = self.primed(start, case["home"]["knowledge"]["items"], case["skill"])
        recorded = case["sequence"]
        record = sequence.state(policy)
        record.absorbed = dict(recorded["absorbed"])
        record.bought = frozenset(recorded["bought"])
        record.stage = recorded["stage"]
        record.powers_read = True
        return policy

    def test_recorded_stop(self):
        rows = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual((rows[4720]["reason"], rows[4720]["key"]),
                         ("town:recall-to-angband", "rea"))
        self.assertEqual({rows[sequence_]["reason"] for sequence_ in range(4722, 4729)},
                         {"town:wait-recall"})
        self.assertEqual((rows[4729]["reason"], rows[4729]["key"]),
                         ("quest:blocked:me-staff", ""))
        recorded = self.case["sequence"]
        self.assertEqual((recorded["failure"], recorded["positions"]["[36, 90]"]),
                         ("no-progress:travel", 8))
        self.assertTrue(all(raw["player"]["recalling"] for raw in self.case["boards"]
                            if raw["turn"] >= STEP_OFF))

    def test_yielded_recall_wait_is_not_the_sequence_standstill(self):
        policy = self.policy()
        answers = {}
        for raw in self.case["boards"]:
            if raw["turn"] < STEP_OFF:
                continue
            board = self.board(policy, raw)
            key = policy.choose_key(board)
            answers[raw["turn"]] = (key, policy.last_reason)
            policy.confirm_key_posted(key)
        self.assertIsNone(sequence.state(policy).failure)
        self.assertEqual(answers[STOP], ("5", "town:wait-recall"))
        stop = next(raw for raw in self.case["boards"] if raw["turn"] == STOP)
        self.post(policy, stop, answers[STOP][0])


if __name__ == "__main__":
    unittest.main()
