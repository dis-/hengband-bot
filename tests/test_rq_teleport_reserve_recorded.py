"""#47 (2026-10-31): the recorded n1-a life-451 random-quest teleport death.

Fixture: tests/fixtures/rq-teleport-reserve-1101.json.gz
(tests/extract_rq_teleport_reserve_fixture.py).  Every decision goes through
the public choose_key and the posted key through the production executor port.

On 鉄獄38階, random quest 45 (『カルバノグの殺人兎』, race 1347, never seen),
fourteen emergency teleports each latched the town return, and the quest exit
lock cancelled it every time; the lock released only when the last scroll was
gone, and the character died waiting for Recall.  Owner 2026-11-01
「テレポートが残り少なくなったら帰る」「5本」: below five scrolls the lock
releases and the return reads Recall (random_quest_reserve).  At exactly five
the 07-26 rule stands and the floor stays locked.

DECLARED CONSTRUCTED: the captures hold no ~f reply, so the skill knowledge is
supplied before each decision.  The executor reply is the same board ten
turns later.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.random_quest_reserve import RANDOM_QUEST_TELEPORT_RESERVE, RETURN_TRIGGER
from tests.support import recorded as executor_pins
from tests.support.recorded import READ_PROMPT, decide
from tests.support import recorded as _dungeon_support
from tests.test_town_decision_speed_caches import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "rq-teleport-reserve-1101.json.gz"
QUEST_ID = 45
QUEST_TARGET_RACE = 1347


class RandomQuestTeleportReserveRecordedTest(_dungeon_support.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, name):
        """Decide every board but the last; return the policy and that board."""
        boards = self.boards(name)
        policy = HengbotPolicy(monrace_knowledge=dict(self.monraces))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge))
        for raw in boards[:-1]:
            decide(policy, raw)
        return policy, boards[-1]

    def test_recorded_rows(self):
        rows = self.cases["reserve-reached"]["decisions"]
        self.assertEqual([(row["decision_sequence"], row["reason"], row["key"])
                          for row in rows[1:]],
                         [(594, "emergency:teleport", "rc"), (595, "seek-loot", "7")])
        for name in ("reserve-reached", "reserve-held"):
            for raw in self.boards(name):
                self.assertEqual(raw["floor"]["quest_id"], QUEST_ID)
                seen = raw["visible_monsters"] + raw["detected_monsters"]
                self.assertNotIn(QUEST_TARGET_RACE, [m.get("race_id") for m in seen])

    def test_below_the_reserve_the_return_reads_recall(self):
        policy, raw = self.replay("reserve-reached")
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(policy._active_kill_quest_id(board), QUEST_ID)
        self.assertEqual(policy._count_teleport_scrolls(board),
                         RANDOM_QUEST_TELEPORT_RESERVE - 1)
        self.assertFalse(board.player.recalling)
        key = decide(policy, copy.deepcopy(raw))
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertEqual(policy._last_return_trigger, RETURN_TRIGGER)
        self.assertEqual(policy.last_reason, "return:recall")
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot)
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(READ_PROMPT)],
                                   self.later(raw)), ["r", recall.slot])

    def test_at_the_reserve_the_quest_floor_stays_locked(self):
        policy, raw = self.replay("reserve-held")
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(policy._count_teleport_scrolls(board), RANDOM_QUEST_TELEPORT_RESERVE)
        decide(policy, copy.deepcopy(raw))
        self.assertTrue(policy._quest_floor_exit_locked(board))
        self.assertFalse(policy._should_start_town_return(board))
        self.assertNotEqual(policy.last_reason, "return:recall")


if __name__ == "__main__":
    import unittest

    unittest.main()
