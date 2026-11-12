"""KILL_ALL quests whose plan ended unwon, and Q25's spent balls, recorded (n1-b life-378, 2026-11-13).

n1-b life-378 (Magic-Eater Lv37) on Quest 25, 01:45:05-01:45:48:
 * from [5,2] the quylthulgs' phase aimed balls at [7,14] (for [9,13]) 68 times (decisions
   5551-5618): the absorbed rods of Acid Ball and Thunder Ball, the wands of Ice Ball, Acid Ball and
   Stinking Cloud, until none had a charge.  With no ball usable the phase counted as 「範囲攻撃が
   無ければ 1) をとばして」 (owner 2026-11-06 phase3) and ended; the six 'R100' recharge rests that
   followed (5622-5642, the tome's preparation) refilled them -- the balls were spent, not missing
   (hpmp/hp-mp-regenerator.cpp regenmagic: the Magic-Eater's wands regain charges and its rods
   recharge, twice as fast resting).  Owner 2026-11-13: 「範囲攻撃がないというのは本当か？休憩すれば
   回復するとかでもなく？」.
 * the sweep's third detection failed (5884 'mCg', 「呪文をうまく唱えられなかった！」 on 5885) and was read as
   a detection that showed nothing: the sweep ended with both quylthulgs alive, then the stairway and
   the druj, then nothing (the loop stops of 01:47).

Owner 2026-11-13: 「全滅クエストで作戦を完了しても終了しない場合、周回して敵を探す。感知を持っていれば
感知して敵を探す。」 -- kill_all_patrol, for every KILL_ALL quest.

Recorded: tests/fixtures/n1b-378-q25-spent-balls-1113.json.gz
(tests/extract_n1b_378_q25_spent_balls_1113_fixture.py): decisions 5540-5900 of that process and
the absorbed powers of the character dump read at 01:33.  The other KILL_ALL quest is Quest 31
『柳じじい』: the recorded n1-c board of tests/fixtures/once-quest-recall-20261103.json.gz
(``q25_house.BASE``).

DECLARED CONSTRUCTED: the magic-eater lists (the boards do not carry them) are the dump's powers
with every charge full, or with the area attacks spent where said (wands at 0, rods charging); the
battle of the Q25 policy is put on the phase each test names (the process's own battle came from
earlier processes); the Q31 plan's end is ``_quest_execute_key`` answering None; HP is set full
where said.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import kill_all_patrol, me_device_attacks, quest25_battle as battle
from hengbot.model import parse_snapshot
from tests.support import q25_house as q25

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-378-q25-spent-balls-1113.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

SHOT_AT_QUYL = range(5551, 5619)
AFTER_SHOTS = 5622                 # [5,2]: the first recharge rest, the quylthulgs' phase over
FAILED_DETECT_BOARD = 5885         # the board after the failed 'mCg'
AREA = {name for (kind, sval), power in me_device_attacks.POWERS.items()
        if power.shape in me_device_attacks.TARGETABLE_SHAPES
        for name in __import__("hengbot.me_capability", fromlist=["names"]).names(kind, sval)}


def lists(*, spent=False, without_area=False):
    """DECLARED CONSTRUCTED: the dump's absorbed powers as the executor's list rows."""
    found = {}
    for kind, rows in CASE["absorbed"].items():
        made = []
        for name, count in rows:
            area = name in AREA
            if area and without_area:
                continue
            row = {"name": name, "fail": 5, "success": 95, "max": count}
            if kind == "rod":
                row["charging"] = count if (spent and area) else 0
            else:
                row["current"] = 0 if (spent and area) else count
            made.append(row)
        found[kind] = (0, tuple(made))
    return found


def board(sequence):
    for raw, row in zip(CASE["boards"], CASE["recorded"]):
        if row["sequence"] == sequence:
            return copy.deepcopy(raw), row
    raise KeyError(sequence)


def q25_policy(raw, phase, *, device_lists):
    policy = q25.new_policy(raw)
    policy._me_device_lists = device_lists
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    fight = battle._ctx(policy, snapshot).battle
    fight.phase, fight.ready = battle.phase_index(phase), True
    fight.browsed = frozenset({"staff", "wand", "rod"})   # the lists just read
    return policy, fight


def decide(policy, raw):
    raw = copy.deepcopy(raw)
    key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
    if key is not None:
        policy.confirm_key_posted(key)
    return key, policy.last_reason


class TheRecordingTest(unittest.TestCase):

    def test_the_balls_were_spent_then_rested_for(self):
        keys = [board(sequence)[1]["key"] for sequence in SHOT_AT_QUYL]
        self.assertTrue(all(key.endswith("@7,14") for key in keys), keys)
        self.assertEqual({key[:3] for key in keys}, {"mCy", "mCz", "mBx", "mBu", "mBo"})
        rests = [row["key"] for raw, row in zip(CASE["boards"], CASE["recorded"])
                 if AFTER_SHOTS <= row["sequence"] <= 5645 and row["reason"] == battle.RECHARGE_REASON]
        self.assertEqual(len(rests), 6)
        raw, _row = board(AFTER_SHOTS)
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (5, 2))
        self.assertEqual(board(5646)[1]["reason"], battle.WALK_REASON)   # then on to the tome

    def test_the_failed_detection(self):
        self.assertEqual(board(5884)[1]["key"], "mCg")
        self.assertIn("呪文をうまく唱えられなかった！", board(FAILED_DETECT_BOARD)[0]["messages"])

    def test_the_dump_holds_area_attacks(self):
        held = {name for rows in CASE["absorbed"].values() for name, _count in rows} & AREA
        self.assertTrue({"アシッド・ボール", "アイス・ボール", "悪臭雲", "サンダー・ボール",
                         "ドラゴンの火炎", "ドラゴンの冷気"} <= held, held)


class SpentBallsTest(unittest.TestCase):
    """Spent is not missing: the quylthulgs' phase rests to refill them, then shoots."""

    def test_spent_balls_rest_in_the_phase(self):
        raw, _row = board(AFTER_SHOTS)
        policy, fight = q25_policy(raw, "quylthulgs", device_lists=lists(spent=True))
        key, reason = decide(policy, raw)
        self.assertEqual(fight.phase, battle.phase_index("quylthulgs"))
        self.assertEqual((key, reason), (battle.RECHARGE_REST_KEY, battle.RECHARGE_REASON))

    def test_refilled_balls_are_shot_at_the_quylthulg(self):
        raw, _row = board(AFTER_SHOTS)
        policy, fight = q25_policy(raw, "quylthulgs", device_lists=lists())
        key, reason = decide(policy, raw)
        self.assertEqual(fight.phase, battle.phase_index("quylthulgs"))
        self.assertEqual(reason, "ranged:magic-eater-device")
        self.assertTrue(key.startswith("m") and "@" in key, key)

    def test_no_area_attack_at_all_still_skips(self):
        raw, _row = board(AFTER_SHOTS)
        policy, fight = q25_policy(raw, "quylthulgs", device_lists=lists(without_area=True))
        decide(policy, raw)
        self.assertGreater(fight.phase, battle.phase_index("quylthulgs"))

    def test_control_spent_read_as_missing_skips_as_recorded(self):
        raw, _row = board(AFTER_SHOTS)
        policy, fight = q25_policy(raw, "quylthulgs", device_lists=lists(spent=True))
        with patch.object(battle, "_recharging_area_attack", lambda _ctx: False):
            decide(policy, raw)
        self.assertGreater(fight.phase, battle.phase_index("quylthulgs"))


class FailedDetectionTest(unittest.TestCase):
    """The sweep's failed cast is cast again, not read as nothing shown."""

    def _sweep(self):
        raw, _row = board(FAILED_DETECT_BOARD)
        policy, fight = q25_policy(raw, "sweep", device_lists=lists())
        fight.detect_turn = board(5884)[1]["turn"]
        fight.kills = {race: count for race, count in __import__(
            "hengbot.quest25_geometry", fromlist=["ROSTER"]).ROSTER.items()
            if race not in {480, 439, 748}}   # every race but the quylthulgs, stairway, druj
        return policy, fight, raw

    def test_the_failed_cast_is_cast_again(self):
        policy, fight, raw = self._sweep()
        key, reason = decide(policy, raw)
        self.assertIsNone(fight.detected)
        self.assertEqual(fight.phase, battle.phase_index("sweep"))
        self.assertTrue(reason.startswith(battle.DETECT_REASON), (key, reason))

    def test_control_the_failed_cast_read_as_nothing_ends_the_sweep(self):
        policy, fight, raw = self._sweep()
        with patch.object(battle, "_detection_failed", lambda _ctx: False):
            decide(policy, raw)
        self.assertEqual(fight.detected, ())


class KillAllPatrolTest(unittest.TestCase):
    """Another KILL_ALL quest (Q31) whose plan has no step: detect, then the round."""

    def _q31(self, *, device_lists=None):
        raw = copy.deepcopy(q25.BASE)
        raw["player"]["hp"] = raw["player"]["max_hp"]
        policy = q25.new_policy(raw)
        if device_lists is not None:
            policy._me_device_lists = device_lists
        return policy, raw

    def _walk(self, policy, raw, count):
        answers = []
        with patch.object(type(policy), "_quest_execute_key", lambda _self, *_args: None):
            for _ in range(count):
                key = q25.choose(policy, raw)
                answers.append((key, policy.last_reason, (raw["player"]["y"], raw["player"]["x"])))
                step = kill_all_patrol_step(key)
                if step is not None and policy.last_reason == kill_all_patrol.WALK_REASON:
                    raw["player"]["y"] += step[0]
                    raw["player"]["x"] += step[1]
        return answers

    def test_the_board_is_a_kill_all_quest(self):
        policy, raw = self._q31()
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(snapshot.floor_key[2], 31)
        self.assertTrue(kill_all_patrol.applies(policy, snapshot))

    def test_the_detection_first_then_the_round(self):
        policy, raw = self._q31(device_lists=lists())
        answers = self._walk(policy, raw, 8)
        self.assertEqual(answers[0][1], kill_all_patrol.DETECT_REASON)
        self.assertTrue(answers[0][0].startswith("mC"), answers[0])   # the absorbed 全感知 rod
        self.assertTrue(all(reason == kill_all_patrol.WALK_REASON for _key, reason, _cell in answers[1:]))
        cells = [cell for _key, _reason, cell in answers[1:]]
        self.assertEqual(len(cells), len(set(cells)))

    def test_without_detection_the_round_is_walked(self):
        policy, raw = self._q31()
        answers = self._walk(policy, raw, 6)
        self.assertEqual({reason for _key, reason, _cell in answers}, {kill_all_patrol.WALK_REASON})

    def test_control_without_the_patrol_it_blocks(self):
        policy, raw = self._q31()
        with patch.object(kill_all_patrol, "key", lambda *_args: None):
            answers = self._walk(policy, raw, 2)
        self.assertEqual({reason for _key, reason, _cell in answers}, {"quest:blocked:execute"})


def kill_all_patrol_step(key):
    return {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1),
            "8": (-1, 0), "9": (-1, 1)}.get(key)


if __name__ == "__main__":
    unittest.main()
