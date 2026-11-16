"""n1-c life-215 (2026-11-16 11:24, 迷宮17階): the sensed ゲイザー that later paralysed it to death.

Recorded: tests/fixtures/n1c-215-sensed-paralyzer-1116.json.xz
(tests/extract_n1c_215_sensed_paralyzer_1116_fixture.py).  The Lv25 Magic-Eater without Free
Action arrived by Word of Recall at [8,14]; the arrival's 邪悪感知 (decision 35287) showed a
sleeping ゲイザー (race 218, GAZE PARALYZE, 1_IN_8 HOLD; lib/edit MonraceDefinitions.jsonc) at
[14,22] among the sensed monsters of decision 35288's board (turn 1224013).  It was never in
view; the shallow-floor rule (owner 2026-11-09 「浅い階層で見かけたら逃げる」) read the paralysers
in view only, so the bot explored on.  Two Teleportations later (from 『ジュラルの魔王』's
shriek, then from two summoned ドラウグル・ウォーカー) it landed at [14,21] beside the gazer,
awake, and was paralysed, confused and killed (HP -5).

Owner 2026-11-16, verbatim: 「見かけたと同じに扱い階を離れる」.  A paralyser only sensed counts
as a sighted one (paralyzer_contact.shallow_sighted reads ``detected_monsters`` too); with none
in view the floor is left by the up stairs underfoot, else Word of Recall.  The recorded board
has no stairs underfoot, so the bot reads Word of Recall (slot g) and latches the return.

Every decision is the public ``choose_key`` of a fresh policy (the absorbed lists are not in the
capture; the recorded decision was me-power:new-floor:detect-traps).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot.policy import HengbotPolicy
from hengbot import paralyzer_contact
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, skill

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-215-sensed-paralyzer-1116.json.xz"
GAZER = "ゲイザー"
RECALL_KEY = "rg"
RECALL_REASON = "shallow-paralyzer:recall"
RETURN_TRIGGER = "shallow-sensed-paralyzer"


class N1c215SensedParalyzerRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def raw(self):
        return copy.deepcopy(self.payload["board"])

    def decide(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        skill(policy, raw)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.races))
        return policy, str(key)

    def test_the_recorded_board(self):
        decision, raw = self.payload["decision"], self.raw()
        self.assertEqual((decision["decision_sequence"], decision["turn"], decision["reason"]),
                         (35288, 1224013, "me-power:new-floor:detect-traps"))
        self.assertEqual((raw["floor"]["dungeon_id"], raw["floor"]["level"],
                          raw["floor"]["quest_id"]), (4, 17, 0))
        self.assertEqual(raw["visible_monsters"], [])
        gazer = next(monster for monster in raw["detected_monsters"] if monster["name"] == GAZER)
        self.assertEqual((gazer["y"], gazer["x"], gazer["asleep"]), (14, 22, True))
        self.assertFalse(any(raw["player"]["ability_sources"]["free_action"].values()))
        self.assertEqual(next(item["slot"] for item in raw["inventory"]
                              if item["name"].startswith("帰還の詔")), RECALL_KEY[1])

    def test_the_sensed_gazer_is_left_by_word_of_recall(self):
        policy, key = self.decide(self.raw())
        self.assertEqual((key, policy.last_reason),
                         (RECALL_KEY, RECALL_REASON))
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, RETURN_TRIGGER)

    def test_no_teleport_while_the_recall_counts_down(self):
        # DECLARED CONSTRUCTED: the recorded board with Word of Recall already active.  A
        # Teleportation stays on the sensed paralyser's floor, so the rule reads nothing more.
        raw = self.raw()
        raw["player"]["recalling"] = True
        policy, _key = self.decide(raw)
        self.assertFalse(policy.last_reason.startswith(
            paralyzer_contact.SHALLOW_SIGHT_REASON_PREFIX))

    def test_free_action_keeps_the_floor(self):
        # DECLARED CONSTRUCTED: the recorded board with Free Action from the equipment.
        raw = self.raw()
        raw["player"]["ability_sources"]["free_action"]["equipment"] = True
        policy, _key = self.decide(raw)
        self.assertFalse(policy.last_reason.startswith(
            paralyzer_contact.SHALLOW_SIGHT_REASON_PREFIX))


if __name__ == "__main__":
    unittest.main()
