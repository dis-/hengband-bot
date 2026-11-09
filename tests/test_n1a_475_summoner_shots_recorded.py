"""Recorded replay of the n1-a life-475 summoner shots of 2026-11-04 02:25 (城49階).

Source: tests/fixtures/death-n1a-475-1104.json.gz
(tests/extract_n1a_475_summoner_shots_fixture.py): the Lv39 warrior's boards of
turns 2038869-2039042 after the second emergency teleport.  From a corridor
mouth it fired ``*t5`` for 25 boards as ``summoner:ranged-kill``: the rule names
a <ナーグル>の疫病人間 (110 HP, three shots), but ``*t`` accepts the game's nearest
target (target-sorter.cpp), and the bolt stops at the first body on its path.
The arrows hit the ghouls, ants and mummies beside the player.

The rule is owner 11-01 survival2 question 2 「3発以内」: a shot that cannot
reach the summoner is not that kill, so the next rung answers the board.
DECLARED CONSTRUCTED: AimedRecordedTest takes the body off the bolt path of the
recorded board, so the named summoner has a clear shot past an adjacent hostile.
Owner 2026-11-09 C 「T1では撃たず離れる」: at the recorded HP 843 that engagement reads T1
and is left (flee:scroll), so the aim is checked with the HP raised to 1500 (DECLARED
CONSTRUCTED), where it is no T1 and the shots stand as before.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1a-475-1104.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

GHOUL_BESIDE = 2038896   # 食屍鬼 at (-1, 0), the plague men behind it
CROWDED = 2038970        # a plague man at (-2, -1), a corpse at (-1, 0)
RECORDED_SHOT = "fj*t5\x1b"


def replay(*, until, change=None):
    """The answers up to ``until``; ``change`` edits that board."""
    policy = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
    for raw in CASE["boards"]:
        raw = copy.deepcopy(raw)
        if raw["turn"] == until and change is not None:
            change(raw)
        key = d57.loops.decide(policy, raw)
        if raw["turn"] == until:
            return raw, key, policy.last_reason
        policy.confirm_key_posted(key)
    raise AssertionError(until)


def without_body_at(dy, dx):
    def change(raw):
        here = raw["player"]
        raw["visible_monsters"] = [
            monster for monster in raw["visible_monsters"]
            if (monster["y"] - here["y"], monster["x"] - here["x"]) != (dy, dx)]
    return change


class SummonerShotRecordedTest(unittest.TestCase):
    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[GHOUL_BESIDE], ("summoner:ranged-kill", RECORDED_SHOT))
        hits = [message for raw in CASE["boards"] for message in raw["messages"]
                if "に命中した。" in message]
        self.assertTrue(any("食屍鬼に命中した" in message for message in hits))
        self.assertFalse(any("疫病人間に命中した" in message for message in hits))

    def test_body_on_the_bolt_path_refuses_the_shot(self):
        _raw, key, reason = replay(until=GHOUL_BESIDE)
        self.assertEqual((key, reason), ("8", "melee"))  # the ghoul beside the player


def sturdier(change):
    def changed(raw):
        change(raw)
        raw["player"]["hp"] = raw["player"]["max_hp"] = 1500
    return changed


class AimedRecordedTest(unittest.TestCase):
    def test_a_t1_engagement_leaves_instead_of_aiming(self):
        raw, key, reason = replay(until=CROWDED, change=without_body_at(-1, 0))
        self.assertEqual(reason, "flee:scroll")

    def test_clear_summoner_is_aimed_past_the_nearer_hostile(self):
        raw, key, reason = replay(until=CROWDED, change=sturdier(without_body_at(-1, 0)))
        self.assertEqual(reason, "summoner:ranged-kill")
        self.assertRegex(key, r"^f.\*p[1-9]+t5\x1b$")
        cursor = key[key.index("p") + 1:key.index("t")]
        y, x = raw["player"]["y"], raw["player"]["x"]
        for digit in cursor:
            y += {"7": -1, "8": -1, "9": -1, "1": 1, "2": 1, "3": 1}.get(digit, 0)
            x += {"7": -1, "4": -1, "1": -1, "9": 1, "6": 1, "3": 1}.get(digit, 0)
        target = next(monster for monster in raw["visible_monsters"]
                      if (monster["y"], monster["x"]) == (y, x))
        self.assertEqual(target["name"], "<ナーグル>の疫病人間")


if __name__ == "__main__":
    unittest.main()
