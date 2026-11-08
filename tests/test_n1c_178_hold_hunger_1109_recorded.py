"""Quest 25 on n1-c life-178 (2026-11-09 07:2x, the ambush hold): hungry, the hold went on until weak.

Owner 2026-11-09 「n1-cが待機を優先して空腹を放置している」.  The Magic-Eater (MANA food: a
wand/staff charge is its meal) held the ambush cell with '5' (quest-strategy:hold); at turn
4101002 it turned hungry with the staple wand at 111 charges ('l'), and the hold went on
until weak at 4103003, where ``survival:mana-absorb`` 'El' fired (and the same at 4091006 →
4093006).  The Q25 plan rung (quest25_battle.key) returns above the emergency ladder and
stepped aside only for weak-or-worse, so neither ``_mana_food_survival_override_key`` nor the
starvation gate (``_survival_gate_key``: 「Hungry with something edible: eat now」) was asked.
Merely hungry keeps the floor only when nothing is edible (``_starvation_lets_quest_finish``),
and a hostile near still comes first.

The boards are the life's recorded boards from 4100808 (the hold, normal) through the first
three hungry boards, replayed through the public ``choose_key`` by one policy (the battle is
started afresh by it, as on a restart; it answers the recorded '5' on every normal board).
The skill list is the life's own (state.jsonl row 2, turn 4089201); the Home knowledge is the
character's town-arrival list of 4084997 (the same character, life-174/176, no town since).

DECLARED CONSTRUCTED (the non-MANA check and the near-hostile check, no such board recorded):
 * the last hungry board with food_type RATION and a Ration of Food added as slot 'n';
 * the same without the ration (nothing edible: the plan keeps the floor);
 * the recorded hungry board with an awake hostile (race 566, recorded on this floor by
   life-176) two cells away (a fight comes first: no meal).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot.model import _parse_items, parse_snapshot
from tests import test_q25_haunted_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "n1c-178-hold-hunger-1109.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

HOLD = ("5", "quest-strategy:hold")
ABSORB = ("El", "survival:mana-absorb")
FIRST_HUNGRY = 4101002
RATION = {"ac": 0, "aware": True, "charges": 0, "charging": False, "count": 5,
          "damage_dice": {"num": 1, "sides": 1}, "fully_known": True, "inscription": "",
          "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
          "is_ego": False, "is_equipment": False, "known": True, "known_flags": [],
          "name": "食料", "pval": 0, "slot": "n", "sval": 35, "to_a": 0, "to_d": 0,
          "to_h": 0, "tval": 80, "weight": 8}


def hostile_beside(raw):
    player = raw["player"]
    return {"asleep": False, "confused": False, "fast": False, "fearful": False,
            "friendly": False, "health": "unhurt", "index": 34, "invulnerable": False,
            "level": 36, "name": "モンスター", "pet": False, "race_id": 566, "slow": False,
            "stunned": False, "y": player["y"], "x": player["x"] + 2}


def replay(last=None):
    """[(turn, food_state, key, reason)] for the recorded boards; ``last`` replaces the final one."""
    boards = [copy.deepcopy(raw) for raw in CASE["boards"]]
    if last is not None:
        boards[-1] = last(boards[-1])
    answers = []
    with TemporaryDirectory() as directory:
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        policy._q25_battle_record_path = Path(directory) / "q25-battle.json"
        first = boards[0]
        policy.prime(parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge))
        policy.consume_skill_knowledge(dict(
            copy.deepcopy(CASE["skill"]), turn=first["turn"],
            player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
        policy.consume_home_knowledge(
            tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
        for raw in boards:
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            answers.append((raw["turn"], snapshot.player.food_state, key, policy.last_reason))
            policy.confirm_key_posted(key)
    return answers


def ration_eater(raw, *, ration=True):
    raw["player"]["food_type"] = 0
    if ration:
        raw["inventory"].append(dict(RATION))
    return raw


class HoldHungerTest(unittest.TestCase):

    def test_the_recording(self):
        recorded = CASE["recorded"]
        self.assertEqual({(row["key"], row["reason"]) for row in recorded}, {HOLD})
        hungry = [row["turn"] for row in recorded if row["food_state"] == "hungry"]
        self.assertEqual(hungry[0], FIRST_HUNGRY)
        raw = CASE["boards"][-1]
        self.assertEqual(raw["player"]["food_type"], 4)
        staple = [item for item in raw["inventory"] if item["slot"] == "l"][0]
        self.assertEqual((staple["tval"], staple["charges"]), (65, 111))
        self.assertEqual(raw["visible_monsters"], [])

    def test_the_hold_holds_while_fed_and_the_wand_is_absorbed_once_hungry(self):
        for turn, food, key, reason in replay():
            if food == "hungry":
                self.assertEqual((key, reason), ABSORB, turn)
            else:
                self.assertEqual((key, reason), HOLD, turn)

    def test_a_ration_eater_eats_at_hungry_too(self):
        turn, food, key, reason = replay(last=ration_eater)[-1]
        self.assertEqual((food, key, reason), ("hungry", "En", "survival:eat"), turn)

    def test_with_nothing_edible_the_plan_keeps_the_floor(self):
        turn, food, key, reason = replay(last=lambda raw: ration_eater(raw, ration=False))[-1]
        self.assertEqual((food, key, reason), ("hungry",) + HOLD, turn)

    def test_a_hostile_near_comes_first(self):
        def near(raw):
            raw["visible_monsters"] = [hostile_beside(raw)]
            return raw
        turn, food, key, reason = replay(last=near)[-1]
        self.assertEqual(food, "hungry")
        self.assertNotEqual((key, reason), ABSORB, turn)
        self.assertFalse(reason.startswith("survival:"), (turn, key, reason))


if __name__ == "__main__":
    unittest.main()
