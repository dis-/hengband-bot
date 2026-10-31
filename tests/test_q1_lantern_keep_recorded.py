"""D48: the Q1 opening keeps the worn lantern instead of swapping in a torch.

n1-c life-069 (2026-10-31 19:42:02, turn 83151, Outpost, Lv6 zombie
Magic-Eater, 4 gold): after the Q1 purchases the opening posted
opening-q1:equip-light 'we' and wore a torch in place of the burning
真鍮のランタン {並, Q34} (light radius 2 -> 1).  Owner 2026-10-31:
「Q1の段階でランタンを松明に持ち替えているのを観測した」; earlier
「そもそもなぜ松明を装備する？直したはずだが」.

The board, knowledge and monster races are the recorded ones
(tests/extract_q1_lantern_keep_fixture.py).  Only replies to newly posted
keys are constructed; every decision goes through the public chooser and the
production executor.
"""
import tests  # noqa: F401

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "q1-lantern-keep-1031.json.gz"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


class Q1LanternKeepRecordedTest(executor_harness.ProductionHarness):
    post = lv7.Lv7TownStopRecordedTest.post
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def boundary(self):
        # DECLARED RECONSTRUCTED: decisions 806-808 of the same life bought
        # the Q1 carry and left the shop on the board before; the in-memory
        # mark that the opening's purchases are done is set accordingly.
        return lv7.Lv7TownStopRecordedTest().boundary(self.case, kit_bought=True)

    def test_recorded_rows_pin_the_swap(self):
        rows = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual((rows[809]["reason"], rows[809]["key"], rows[809]["light_radius"]),
                         ("opening-q1:equip-light", "we", 2))
        self.assertEqual(rows[810]["light_radius"], 1)
        board = self.case["snapshot"]
        worn = next(item for item in board["equipment"] if item["slot"] == "light")
        self.assertEqual((worn["name"], worn["known"], worn["pseudo_feeling"]),
                         ("真鍮のランタン {並, Q34}", False, "average"))
        self.assertTrue(self.case["next_light"][0]["name"].startswith("松明"))
        self.assertEqual(board["player"]["gold"], 4)
        self.assertFalse(any(item["tval"] == 77 for item in board["inventory"]))

    def test_worn_lantern_is_kept_and_q1_is_requested(self):
        policy, raw = self.boundary()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        # The carried torches satisfy Q1's light gate with the lantern worn.
        self.assertTrue(policy._fixed_quest_ready(board, 1), policy.fixed_quest_readiness_state())
        key = str(policy.choose_key(board))
        # Unfixed: ('we', 'opening-q1:equip-light') -- the recorded swap.
        self.assertEqual(policy.last_reason, "fixedquest:request:approach", key)
        self.assertIn(key, DIRECTIONS)
        # DECLARED CONSTRUCTED: the engine moves the player one step.
        following = copy.deepcopy(raw)
        dy, dx = DIRECTIONS[key]
        following["player"]["y"] += dy
        following["player"]["x"] += dx
        following["turn"] += 1
        self.post(policy, raw, key, following)
        key = str(policy.choose_key(parse_snapshot(following, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, "fixedquest:request:approach", key)
        worn = next(item for item in following["equipment"] if item["slot"] == "light")
        self.assertEqual(worn["name"], "真鍮のランタン {並, Q34}")
