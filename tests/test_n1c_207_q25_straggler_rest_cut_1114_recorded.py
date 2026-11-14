"""Quest 25 on n1-c life-207 (2026-11-14 20:49-21:24): the stragglers' endless hold on [5,1], recorded.

The chain (jsonlog/bot-decisions of ~/hengbot-soak/n1-c/life-207 and the stop's capture
20261114-212431-stall-floor-dwell-quest-strategy-hold):

 * 20:49, the battle record restored at the 17:54 save's turn (q25-memory-loss-1114): the
   wall-passers' phase killed five shadow demons on [7,1], the Ipsissimus' phase all three from
   [5,1], and the stragglers' phase (phase 3, its stand [5,1], ``wait_limits.quiet_actions``)
   began with the recharge rest (``R100``, turn 8011366).  The next board was turn 8011374: the
   rest was cut, a shadow demon sensed (ESP) and moving, so ``battle.rest_cut`` (``_note_rest_cut``).
 * Owner 2026-11-09 「持ち場へ歩き静まれば休む」: while such a mover is sensed the preparation waits
   and the phase's step runs as with a hostile in view (``_prepare``).  A shadow demon stayed
   sensed on [11,4] (and the never-moving druj on [11,18]); the phase was never ready, and its
   wait counted only when ready (``_observe``), so it held '5' on [5,1] from 20:49:41 to the stall
   stop at 21:24:31 (stall:floor-dwell:quest-strategy:hold).

The rule (quest25_battle ``_observe``): while the preparation waits for a sensed mover that cut the
rest, the phase's wait counts on its stand as when ready -- a straggler that never comes is an
arrival that does not come (owner 2026-11-06 「50回来なければ終える」).

Recorded: tests/fixtures/n1c-207-q25-straggler-rest-cut-1114.json.gz
(tests/extract_n1c_207_q25_straggler_rest_cut_1114_fixture.py): the stop's 109 boards, the battle
record and the warning record after it.  A fresh policy restores both records through the real
paths and decides the boards in order through the public ``choose_key``; each key is posted through
the production executor, the game then showing the next recorded board.

DECLARED CONSTRUCTED: the records' turns are set to the first board's
(tests/test_n1c_207_q25_wallpasser_hold_1114_recorded ``new_policy``, whose skill record of the
same life it takes); the boards carry no magic-eater lists, so the policy holds none (the phases
after the stragglers' are not asserted: with no area attack held the quylthulgs' ends at once).
The control drops the sensed shadow demon from every board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from hengbot.model import parse_snapshot
from tests import test_n1c_207_q25_wallpasser_hold_1114_recorded as hold

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-207-q25-straggler-rest-cut-1114.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

STAND = battle.geo.STRAGGLER_STAND
STRAGGLERS = battle.phase_index("stragglers")
WAIT = 50   # QUEST_25 wait_limits.quiet_actions (owner 2026-11-06 「50回来なければ終える」)
DRUJ = 748


def boards() -> list[dict]:
    base = CASE["hold"]["base"]
    return [dict(copy.deepcopy(base), **copy.deepcopy(change)) for change in CASE["hold"]["changes"]]


def without_demon(raw: dict) -> dict:
    board = copy.deepcopy(raw)
    board["detected_monsters"] = [monster for monster in board["detected_monsters"]
                                  if monster["race_id"] != battle.geo.SHADOW]
    return board


class _Drive(hold._Hold):

    def drive(self, shape=lambda raw: raw):
        """[(index, key, reason, phase, ready, quiet, rest_cut)] of the boards in order, to the
        stragglers' end or the first key whose screens this harness does not show."""
        recorded = [shape(raw) for raw in boards()]
        answers = []
        with TemporaryDirectory() as directory:
            policy = hold.new_policy(Path(directory), recorded[0], CASE["warning_record"],
                                     CASE["battle_record"])
            for index, raw in enumerate(recorded):
                key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
                fight = policy._quest_navigators[battle.geo.QUEST_ID].phase_battle
                answers.append((index, key, policy.last_reason, fight.phase, fight.ready, fight.quiet,
                                fight.rest_cut))
                if fight.phase != STRAGGLERS or not hold.replay._shown(key) or index + 1 == len(recorded):
                    break
                self.post(policy, raw, key, recorded[index + 1])
        return answers


class TheRecordingTest(unittest.TestCase):

    def test_the_stop_held_on_the_stand_with_a_demon_sensed(self):
        record = CASE["battle_record"]["battle"]
        self.assertEqual((record["phase"], record["ready"], record["quiet"], record["rest_cut"]),
                         (STRAGGLERS, False, 0, True))
        rows = CASE["hold"]["recorded"]
        self.assertEqual(len(rows), 109)
        self.assertTrue(all((row["key"], row["reason"]) == ("5", battle.HOLD_REASON) for row in rows))
        for raw in boards():
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), STAND)
            self.assertEqual(raw["visible_monsters"], [])
            self.assertEqual(sorted((monster["race_id"], monster["y"], monster["x"], monster["asleep"])
                                    for monster in raw["detected_monsters"]),
                             [(battle.geo.SHADOW, 11, 4, False), (DRUJ, 11, 18, False)])


class TheStragglersWaitTest(_Drive):

    def test_the_wait_counts_while_the_rest_waits_for_the_sensed_mover(self):
        answers = self.drive()
        held = answers[:-1]
        self.assertEqual(len(held), WAIT - 1, answers)
        self.assertTrue(all(row[1:5] == ("5", battle.HOLD_REASON, STRAGGLERS, False) and row[6]
                            for row in held), held)
        self.assertEqual([row[5] for row in held], list(range(1, WAIT)))
        self.assertGreater(answers[-1][3], STRAGGLERS, answers[-1])

    def test_none_sensed_the_recharge_rest_goes_on(self):
        # Control (DECLARED CONSTRUCTED): with no sensed mover the cut rest is lifted and the
        # preparation goes on, as before (no magic-eater list held: nothing to recharge, ready).
        answers = self.drive(without_demon)
        self.assertEqual(answers[0][4:7], (True, 0, False), answers[0])
        self.assertGreater(answers[-1][3], STRAGGLERS, answers[-1])


if __name__ == "__main__":
    unittest.main()
