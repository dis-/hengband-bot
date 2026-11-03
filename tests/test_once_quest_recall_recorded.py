"""Recorded Q31 board: no emergency recall above the abort line (once-quest-recall-1103).

Owner 2026-11-03: 「回復の手段がある間は回復か休憩を選び、帰還は作戦の撤退の線以下か、
逃げ手段が尽きた時だけにします。」

Source: tests/fixtures/once-quest-recall-20261103.json.gz (n1-c life-116,
tests/extract_once_quest_recall_fixture.py).  Decision 4142 (turn 1986976) read
Word of Recall at HP 174/354 with no enemy in view and 12 Teleport scrolls; the
placement sweep's walk reached the low-HP walk gate, whose only heal candidates
were 9 Cure Critical (not a heal kind on Q31).  The recall failed the ONCE quest.

Boards, knowledge and decision rows are measured.  DECLARED CONSTRUCTED: the
HP of the abort-line board and the removed scrolls of the exhausted board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy_constants import REST_MACRO
from hengbot.quest_knowledge import load_quest_knowledge
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "once-quest-recall-20261103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
INCIDENT = CASE["boards"][0]
RECALL_READ = ("re", "emergency:recall")
TELEPORT_SVALS = {8, 9}  # Phase Door, Teleportation
TVAL_SCROLL = 70


def decide(board):
    # Primed on the board itself: no hit observed, as on the recorded board.
    policy = loops.new_policy(dict(CASE, boards=[board]), CASE["skill"], monraces=CASE["monraces"])
    policy._quest_knowledge[31] = load_quest_knowledge(Path("C:/hengband/lib/edit/quests"))[31]
    key = str(policy.choose_key(parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)))
    return key, policy.last_reason


class OnceQuestRecallRecordedTest(unittest.TestCase):
    def test_no_enemy_above_the_abort_line_rests_instead_of_recalling(self):
        recorded = {row["turn"]: (row["key"], row["reason"]) for row in CASE["decisions"]}
        self.assertEqual(recorded[INCIDENT["turn"]], RECALL_READ)
        self.assertEqual(INCIDENT["visible_monsters"], [])
        self.assertEqual(decide(INCIDENT), (REST_MACRO, "rest"))

        at_abort_line = copy.deepcopy(INCIDENT)
        at_abort_line["player"]["hp"] = at_abort_line["player"]["max_hp"] // 4
        self.assertEqual(decide(at_abort_line), RECALL_READ)

        exhausted = copy.deepcopy(INCIDENT)
        exhausted["inventory"] = [
            item for item in exhausted["inventory"]
            if not (item["tval"] == TVAL_SCROLL and item["sval"] in TELEPORT_SVALS)]
        self.assertEqual(decide(exhausted)[1], RECALL_READ[1])


if __name__ == "__main__":
    unittest.main()
