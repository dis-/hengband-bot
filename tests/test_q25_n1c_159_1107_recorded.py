"""Quest 25 on n1-c life-159 (2026-11-07 15:31-15:32), recorded.

Recorded: tests/fixtures/q25-mass-n1c-159-1107.json.gz (tests/extract_q25_mass_1107_fixture.py),
every board of the floor from the arrival to the corpse masses beside the player on [1,18], with
the recorded reason and key.  One policy decides the boards in order (``replay``); it cannot change
the boards after the first key that differs from the recording.  The absorbed power lists are not on
the boards, so the Magic-Eater's device shots come out as other keys in the replay: the rows the
tests read are the ones the replay reproduces.

Where a test sets the phase plan's memory on a recorded board (``at_phase``), it says so: the
recording held on [1,18] in the ambush (phase 1), and the owner's corpse-mass rule of 2026-11-07
is for phase 5 on.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_geometry as geo, quest_room_sweep
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


def choose(policy, raw):
    return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))


def at_phase(policy, raw, name, **fields):
    """CONSTRUCTED memory: the phase plan set to ``name`` on a recorded board."""
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    record = battle._memory(quest_room_sweep._navigator(policy, snapshot, geo.QUEST_ID))
    record.__dict__.update(battle.Battle(phase=battle.PHASE_NAMES.index(name), ready=True,
                                         **fields).__dict__)
    return record


def phase_of(policy, raw):
    return battle.describe(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))["phase"]


def beside(raw):
    here = raw["player"]
    return [(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]
            if max(abs(m["y"] - here["y"]), abs(m["x"] - here["x"])) <= 1]


class Q25MassBesideTest(unittest.TestCase):
    """Owner 2026-11-07 「隣に来たら倒す」: 「第5段以降でも、隣のマスの死体の塊は殴るか撃って倒す。
    離れた所の死体の塊は今のまま相手にしない。」"""

    def setUp(self):
        self.raw, self.recorded = copy.deepcopy(BY_SEQUENCE[MASS_BESIDE][0]), BY_SEQUENCE[MASS_BESIDE][1]
        self.assertEqual((self.raw["player"]["y"], self.raw["player"]["x"]), (1, 18))
        self.assertEqual(beside(self.raw), [(geo.MASS, 1, 17)])
        self.assertEqual((self.recorded["key"], self.recorded["reason"]), ("5", HOLD_REASON))

    def test_from_phase_5_on_the_mass_beside_is_struck(self):
        for name in battle.PHASE_NAMES[battle.PHASE_NAMES.index("dreadmaster"):]:
            with self.subTest(phase=name):
                policy = new_policy(self.raw)
                at_phase(policy, self.raw, name, style="melee")   # CONSTRUCTED memory
                policy._player_hasted = lambda snapshot: True
                key = choose(policy, self.raw)
                self.assertEqual((key, policy.last_reason), (WEST, MELEE_REASON))

    def test_a_mass_farther_off_is_still_left_alone(self):
        raw = copy.deepcopy(self.raw)
        raw["visible_monsters"] = [m for m in raw["visible_monsters"] if (m["y"], m["x"]) != (1, 17)]
        self.assertEqual(beside(raw), [])
        policy = new_policy(raw)
        at_phase(policy, raw, "dreadmaster", style="melee")   # CONSTRUCTED memory
        policy._player_hasted = lambda snapshot: True
        key = choose(policy, raw)
        self.assertNotEqual(policy.last_reason, MELEE_REASON, key)
        self.assertNotIn(battle.SHOT_REASON, policy.last_reason or "")

    def test_the_corpse_mass_phase_and_earlier_are_unchanged(self):
        # The recording itself: phase 1 (the ambush) held beside the mass, and still does.
        policy = new_policy(self.raw)
        at_phase(policy, self.raw, "ambush", style="melee")   # CONSTRUCTED memory, the replay's phase
        self.assertEqual((choose(policy, self.raw), policy.last_reason), ("5", HOLD_REASON))


if __name__ == "__main__":
    unittest.main()
