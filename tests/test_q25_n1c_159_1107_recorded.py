"""Quest 25 on n1-c life-159 (2026-11-07 15:31-15:32), recorded.

Recorded: tests/fixtures/q25-mass-n1c-159-1107.json.gz (tests/extract_q25_mass_1107_fixture.py),
every board of the floor from the arrival to the corpse masses beside the player on [1,18], with
the recorded reason and key.  One policy decides the boards in order (``replay``); it cannot change
the boards after the first key that differs from the recording.  The absorbed power lists are not on
the boards, so the Magic-Eater's device shots come out as other keys in the replay: the rows the
tests read are the ones the replay reproduces.

Where a test sets the phase plan's memory on a recorded board (``at_phase``), it says so: the
recording held on [1,18] in the ambush (phase 1); the owner's corpse-mass rule of 2026-11-07 holds
in every phase.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_geometry as geo, quest_room_sweep, resist_potion
from hengbot.model import _parse_items, parse_snapshot
from hengbot.quest_find_exit import HOLD_REASON, MELEE_REASON
from tests import test_q25_haunted_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "q25-mass-n1c-159-1107.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BY_SEQUENCE = {row["sequence"]: (board, row) for board, row in zip(CASE["boards"], CASE["recorded"])}
# [1,18], 死体の塊 on [1,17] beside the player, the recording's hold.
MASS_BESIDE = 425
WEST = "4"
# [10,1] at full HP (766/766), 幽体ティラノサウルス (705) alone in view on [9,1]: the first
# Scroll of Teleportation the Resistance potion's leave read.
TYRANNOSAUR_ALONE = 276
SPECTRAL_T = 705
# The arrival on [13,1]: nothing in view, 18 monsters detected out of sight, 啓蒙の薬 carried.
ARRIVAL = 191
# [11,1] with one hostile in view.
ONE_IN_VIEW = 193
SV_POTION_ENLIGHTENMENT = 56


def new_policy(first):
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    first = copy.deepcopy(first)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    policy.consume_home_knowledge(tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
    return policy


def replay():
    """sequence -> (key, reason): one policy deciding every recorded board in order."""
    policy = new_policy(CASE["boards"][0])
    answers = {}
    for raw, row in zip(CASE["boards"], CASE["recorded"]):
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        answers[row["sequence"]] = (key, policy.last_reason)
        policy.confirm_key_posted(key)
    return answers


ANSWERS = {}


def answer(sequence):
    if not ANSWERS:
        ANSWERS.update(replay())
    return ANSWERS[sequence]


def choose(policy, raw):
    return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))


def at_phase(policy, raw, name, **fields):
    """CONSTRUCTED memory: the phase plan set to ``name`` on a recorded board."""
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    record = battle._memory(quest_room_sweep._navigator(policy, snapshot, geo.QUEST_ID))
    record.__dict__.update(battle.Battle(phase=battle.PHASE_NAMES.index(name), ready=True,
                                         **fields).__dict__)
    return record


def memory_of(policy, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    return battle._memory(quest_room_sweep._navigator(policy, snapshot, geo.QUEST_ID))


def phase_of(policy, raw):
    return battle.describe(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))["phase"]


def beside(raw):
    here = raw["player"]
    return [(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]
            if max(abs(m["y"] - here["y"]), abs(m["x"] - here["x"])) <= 1]


class Q25MassBesideTest(unittest.TestCase):
    """Owner 2026-11-07 「隣に来たら倒す」, widened the same day 「全部の段に広げる」: 「第1段から最後の段
    まで、隣のマスの死体の塊は殴るか撃って倒す。離れた塊は今のまま相手にしない。」"""

    def setUp(self):
        self.raw, self.recorded = copy.deepcopy(BY_SEQUENCE[MASS_BESIDE][0]), BY_SEQUENCE[MASS_BESIDE][1]
        self.assertEqual((self.raw["player"]["y"], self.raw["player"]["x"]), (1, 18))
        self.assertEqual(beside(self.raw), [(geo.MASS, 1, 17)])
        self.assertEqual((self.recorded["key"], self.recorded["reason"]), ("5", HOLD_REASON))

    def test_in_every_phase_the_mass_beside_is_struck(self):
        for name in battle.PHASE_NAMES:
            with self.subTest(phase=name):
                policy = new_policy(self.raw)
                at_phase(policy, self.raw, name, style="melee")   # CONSTRUCTED memory
                policy._player_hasted = lambda snapshot: True
                key = choose(policy, self.raw)
                self.assertEqual((key, policy.last_reason), (WEST, MELEE_REASON))

    def test_a_mass_farther_off_in_the_line_of_fire_is_shot(self):
        # Owner 2026-11-08 「射線にいれば範囲で撃つ」 replaces 「離れた塊は今のまま相手にしない」:
        # 「どの段でも、もっと危ない敵が動いていなければ、射線にいる増える敵を撃つ。」
        raw = copy.deepcopy(self.raw)
        raw["visible_monsters"] = [m for m in raw["visible_monsters"] if (m["y"], m["x"]) != (1, 17)]
        self.assertEqual(beside(raw), [])
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", style="melee")   # CONSTRUCTED memory
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertEqual(policy.last_reason, battle.SHOT_REASON, key)
        self.assertEqual(phase_of(policy, raw), "dreadmaster")

    def test_the_recorded_ambush_hold_beside_the_mass_strikes_it(self):
        # The replay itself (no memory set): the recording held on [1,18] in the ambush from 384
        # on; from 425 a mass stood beside it on [1,17], and every one of those boards strikes it.
        rows = [row for row in CASE["recorded"] if 384 <= row["sequence"] <= 431]
        self.assertTrue(all(row["reason"] == HOLD_REASON for row in rows if row["sequence"] >= 400))
        besides = [row["sequence"] for row in rows if beside(BY_SEQUENCE[row["sequence"]][0])
                   and all(race == geo.MASS for race, _y, _x in beside(BY_SEQUENCE[row["sequence"]][0]))]
        self.assertEqual(besides, list(range(425, 432)))
        for sequence in besides:
            with self.subTest(sequence=sequence):
                self.assertEqual(BY_SEQUENCE[sequence][1]["key"], "5")
                self.assertEqual(answer(sequence), (WEST, MELEE_REASON))


class Q25NoChanceLeaveTest(unittest.TestCase):
    """Owner 2026-11-07: 「Q25内部でのテレポートの優先度を下げる。少なくとも幽体ティラノサウルスとの
    単独戦闘から逃げることは避けなければ絶対にクリアできない」."""

    LEAVES = [row["sequence"] for row in CASE["recorded"] if row["reason"] == resist_potion.LEAVE_REASON]

    def test_the_recording_read_six_scrolls_the_first_one_on_one_with_the_tyrannosaur(self):
        self.assertEqual(self.LEAVES, [276, 289, 310, 321, 355, 359])
        raw = BY_SEQUENCE[TYRANNOSAUR_ALONE][0]
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (10, 1))
        self.assertEqual(raw["player"]["hp"], raw["player"]["max_hp"])
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]], [(SPECTRAL_T, 9, 1)])

    def test_one_on_one_with_the_tyrannosaur_the_phase_fights_it(self):
        self.assertEqual(answer(TYRANNOSAUR_ALONE), ("8", MELEE_REASON))

    def test_no_recorded_leave_board_reads_the_scroll(self):
        for sequence in self.LEAVES:
            with self.subTest(sequence=sequence):
                self.assertNotEqual(answer(sequence)[1], resist_potion.LEAVE_REASON)

    def test_control_the_rule_still_says_leave_and_answers_below_the_phase(self):
        raw = BY_SEQUENCE[TYRANNOSAUR_ALONE][0]
        policy = new_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertIsNone(resist_potion.drink_key(policy, snapshot))
        self.assertEqual(resist_potion.key(policy, snapshot)[:1], "r")
        self.assertEqual(policy.last_reason, resist_potion.LEAVE_REASON)
        policy = new_policy(raw)
        with patch.object(battle, "_phase_key", lambda policy, snapshot: None):
            key = choose(policy, raw)
        self.assertEqual((key[:1], policy.last_reason), ("r", resist_potion.LEAVE_REASON))


def enlightenment_letter(raw):
    return next(chr(ord("a") + index) for index, item in enumerate(raw["inventory"])
                if item["tval"] == 75 and item["sval"] == SV_POTION_ENLIGHTENMENT)


class Q25AmbushEnlightenmentTest(unittest.TestCase):
    """Owner 2026-11-07 「Q25の段階1、待ち伏せ中に安全で啓蒙の薬を持っているなら飲むを追加」; 安全:
    「攻撃が届く範囲に=視界内に敵がいない」."""

    def test_the_arrival_with_none_in_view_drinks_it(self):
        raw = BY_SEQUENCE[ARRIVAL][0]
        self.assertEqual((len(raw["visible_monsters"]), len(raw["detected_monsters"])), (0, 18))
        self.assertEqual(BY_SEQUENCE[ARRIVAL][1]["reason"], battle.WALK_REASON)   # the recording walked on
        self.assertEqual(answer(ARRIVAL), ("q" + enlightenment_letter(raw), battle.ENLIGHTEN_REASON))

    def test_it_is_drunk_once_on_the_floor(self):
        # The recording never drank it, so every later board still carries it.
        self.assertTrue(all(any(item["tval"] == 75 and item["sval"] == SV_POTION_ENLIGHTENMENT
                                for item in board["inventory"]) for board in CASE["boards"]))
        answer(ARRIVAL)
        drunk = [sequence for sequence, (_key, reason) in ANSWERS.items() if reason == battle.ENLIGHTEN_REASON]
        self.assertEqual(drunk, [ARRIVAL])

    def test_with_a_hostile_in_view_it_is_not_drunk(self):
        raw = BY_SEQUENCE[ONE_IN_VIEW][0]
        self.assertEqual(len(raw["visible_monsters"]), 1)
        policy = new_policy(raw)
        at_phase(policy, raw, "ambush")   # CONSTRUCTED memory: the ambush, nothing drunk yet
        choose(policy, raw)
        self.assertNotEqual(policy.last_reason, battle.ENLIGHTEN_REASON)
        self.assertFalse(memory_of(policy, raw).enlightened)


if __name__ == "__main__":
    unittest.main()
