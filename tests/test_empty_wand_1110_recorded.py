"""n1-a life-507 / life-508 (Zombie Warrior), 2026-11-10 / 11: the hungry wand.

Recorded: tests/fixtures/n1a-508-1111/empty-wand-1857.json.gz (tests/extract_n1a_508_1111_fixtures.py,
which also writes the fixtures of tests/test_unseen_descent_1111_recorded.py and
tests/test_quest_search_nodetect_1111_recorded.py; the helpers below serve all three).

life-507 18:57 (Angband 12F, RANDOM quest 43): hungry, it ate 「ブリキの魔法棒 {空}」 (``E j``) ~40
times until the loop detector: the game marks a wand eaten at 0 charges EMPTY and leaves it
unidentified (cmd-item/cmd-eat.cpp:165-169), and the bot's unidentified-device fallback
(policy_supply ``_find_edible``) took it again.  Every decision is the public ``choose_key`` of one
fresh policy fed the recorded boards in order.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import gzip
import json
import unittest
from pathlib import Path

from hengbot.exploration_ledger import ExplorationLedger
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.test_dungeon_1031_recorded import skill
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURES = Path(__file__).with_name("fixtures") / "n1a-508-1111"
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def case(name):
    with gzip.open(FIXTURES / f"{name}.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


def recorded(fixture):
    rows = {}
    for row in fixture["decisions"]:
        rows.setdefault(row["turn"], (row["key"], row["reason"]))
    return rows


def fresh(fixture):
    races = knowledge(fixture)
    policy = HengbotPolicy(monrace_knowledge=races)
    first = copy.deepcopy(fixture["rows"][0])
    board = parse_snapshot(first, races)
    ledger = ExplorationLedger(None)
    ledger.bind(board)
    policy._exploration_ledger = ledger
    policy.prime(board)
    skill(policy, first)
    return policy, races


def decide(policy, races, raw):
    key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), races))
    key = "" if key is None else str(key)
    if key:
        policy.confirm_key_posted(key)
    return key


def replay(fixture, until=None):
    """The decisions of one fresh policy on the recorded boards up to ``until`` (all by default)."""
    policy, races = fresh(fixture)
    decisions = {}
    for raw in fixture["rows"]:
        decisions.setdefault(raw["turn"], (decide(policy, races, raw), policy.last_reason))
        if raw["turn"] == until:
            return policy, races, raw, decisions
    if until is not None:
        raise AssertionError(f"board {until} not recorded")
    return policy, races, raw, decisions


class EmptyWandRecordedTest(unittest.TestCase):
    """2. life-507 18:57, Angband 12F: 「ブリキの魔法棒 {空}」 eaten again and again."""

    @classmethod
    def setUpClass(cls):
        cls.case = case("empty-wand-1857")

    def test_recorded_scene(self):
        last = self.case["rows"][-1]
        self.assertEqual(last["player"]["food_state"], "hungry")
        names = {item["slot"]: item["name"] for item in last["inventory"]}
        self.assertEqual(names["j"], "ブリキの魔法棒 {空}")
        self.assertEqual(names["k"], "金の魔法棒")
        rows = [row for row in self.case["decisions"] if row["key"]]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual((row["key"], row["reason"]), ("Ej", "survival:mana-absorb"))
            self.assertTrue(any("もう魔力が残っていない" in message for message in row["messages"]))

    def test_the_empty_wand_is_not_eaten_the_next_unknown_one_is(self):
        _, _, _, decisions = replay(self.case)
        keys = [key for key, _ in decisions.values()]
        self.assertNotIn("Ej", keys)
        self.assertEqual(set(keys), {"Ek"})
        self.assertEqual({reason for _, reason in decisions.values()}, {"survival:mana-absorb"})

    def test_known_empty_reads_the_games_feeling(self):
        races = knowledge(self.case)
        board = parse_snapshot(copy.deepcopy(self.case["rows"][-1]), races)
        items = {item.slot: item for item in board.inventory}
        self.assertTrue(items["j"].known_empty)
        self.assertFalse(items["k"].known_empty)
        self.assertFalse(items["i"].known_empty)  # 岩石溶解の魔法棒 (0回分): identified
        english = dataclasses.replace(items["j"], name="a Tin Wand {empty}")
        both = dataclasses.replace(items["j"], name="ブリキの魔法棒 {空, @a1}")
        inscribed = dataclasses.replace(items["k"], name="金の魔法棒 {@空}")
        self.assertTrue(english.known_empty)
        self.assertTrue(both.known_empty)
        self.assertFalse(inscribed.known_empty)


if __name__ == "__main__":
    unittest.main()
