"""The worn unidentified Q34 lantern is judged alike in town and on the floor.

n1-b lives 326-328 (2026-11-06 19:27-19:40) and n1-c lives 148/152: the town let
the mining run leave on the lit Q34 lantern with fewer than five flasks (owner
2026-11-06 「燃料があれば出発してよい」, e5576fc910), but on Yeek cave 1F the
same lantern counted as an unidentified one short of oil, so every run left by
the arrival stair under fundraising-run-exhausted until fundraise-limit stopped
the bot as quest:blocked:me-staff.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_fundraising import (
    FundraisingPurpose, FundraisingPurposeRecord, FundraisingTransportChild,
)
from tests.support.recorded import EDIT


CAPTURE = Path(__file__).parent / "fixtures" / "crossarea-holder-silent.states.jsonl.gz"
PURPOSE = FundraisingPurpose(29, "mine", True)


def _boards():
    with gzip.open(CAPTURE, "rt", encoding="utf-8") as source:
        return [json.loads(row) for row in source]


def q34_lantern_worn(raw, light_radius):
    """DECLARED CONSTRUCTED from the captured town / Yeek cave 1F pair: the
    unidentified Q34 lantern in the light slot (no fuel figure), no oil and no
    spare light in the pack, and ``light_radius`` the player's light
    (torch.cpp update_lite_radius: an empty lantern adds none).  The asleep
    unique of the captured 1F is left out so the run's own light question
    decides the board."""
    board = copy.deepcopy(raw)
    light = next(item for item in board["equipment"] if item["slot"] == "light")
    light.update(known=False, fully_known=False, light_turns=0, known_flags=[],
                 name="真鍮のランタン {高級品, Q34}", inscription="Q34")
    board["inventory"] = [item for item in board["inventory"] if item["tval"] not in {39, 77}]
    for index, item in enumerate(board["inventory"]):
        item["slot"] = chr(ord("a") + index)
    board["player"]["light_radius"] = light_radius
    board["visible_monsters"] = [monster for monster in board["visible_monsters"]
                                 if "『" not in monster["name"]]
    return board


class Q34LanternFloorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town, cls.floor = _boards()
        cls.knowledge = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def view(self, raw, light_radius):
        return parse_snapshot(q34_lantern_worn(raw, light_radius), self.knowledge)

    def mining_run(self):
        """A mining run the town sent off (its departure child complete)."""
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        policy._fundraising_run_purpose = PURPOSE
        policy._fundraising_purpose_record = replace(
            FundraisingPurposeRecord(PURPOSE),
            child=FundraisingTransportChild(PURPOSE.identity, "depart", (0, 0, 0), 29,
                                            state="complete"))
        # DECLARED CONSTRUCTED: the run's first departure (its food waiver) and a
        # known skill list, so neither food nor bookkeeping takes the board.
        policy._fundraising_runs_started = 1
        policy._skill_exp_request_key = lambda _snapshot: None
        return policy

    def test_the_lit_lantern_the_town_departed_on_keeps_the_run_going(self):
        policy = self.mining_run()
        self.assertTrue(policy._fundraising_light_ready(self.view(self.town, 2)))
        board = self.view(self.floor, 2)
        self.assertTrue(policy._fundraising_light_ready(board))
        key = policy.choose_key(board)
        # Live: ('<', 'fundraise:ascend') under fundraising-run-exhausted.
        self.assertNotEqual(policy._last_return_trigger, "fundraising-run-exhausted")
        self.assertNotEqual((key, policy.last_reason), ("<", "fundraise:ascend"))
        self.assertFalse(policy._returning_to_town)

    def test_a_lantern_seen_out_still_ends_the_run(self):
        policy = self.mining_run()
        self.assertFalse(policy._fundraising_light_ready(self.view(self.town, 0)))
        key = policy.choose_key(self.view(self.floor, 0))
        self.assertEqual((key, policy.last_reason), ("<", "fundraise:ascend"))
        self.assertEqual(policy._last_return_trigger, "fundraising-run-exhausted")


if __name__ == "__main__":
    unittest.main()
