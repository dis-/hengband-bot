"""n1-a life-538 (Anti-magic cave 47F, 2026-11-26 11:24): ``o3`` after six searches killed the warrior.

The warrior (Lv42, HP 1048/1048, skill_srh 16) worked the 大きな鉄の箱 it had dropped at [27,5]
from [26,4]: six ``s`` (decisions 10134-10139), two ``D3`` that answered 「トラップが見あたらない。」
(the chest was not known: src/action/open-close-execution.cpp:232), then ``o3`` (decision 10142).
Six searches at 16% a press miss a trap 35% of the time (0.84^6).  The chest's trap fired on the
opening and its summons (アイアン・リッチ, 古代万色ドラゴン, サイバーデーモン ...) killed the
character before the next board; the fire breath shattered the carried Speed and Cure potions,
whose shatter effect (object-broken.cpp potion_smash_effect) hasted and healed the crowd.

Owner 2026-11-26 「探す回数を増やし、外せない罠は開けない」 (every depth, every chest kind): the chest
is searched until a hidden trap is left about 3% of the time (20 presses at skill 16); it is opened
only when a disarm press answered that the trap is gone or absent, or that no trap is known after
every search found none; a found trap the disarm presses did not remove leaves the chest shut.

The boards are the capture's snapshot rows of decisions 10134-10142 (turns 2341414-2341480).
DECLARED CONSTRUCTED: the chest claim restored at [27,5] with empty phase counts (the step-off
of decision 10133 set it); the boards after the capture's nine are the last board again with the
turn advanced and the game's answer to the press put in its messages.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.support import recorded

ROOT = Path(__file__).parents[1]
RACES = load_monrace_knowledge(
    find_monrace_definitions(ROOT, None) or recorded.EDIT / "MonraceDefinitions.jsonc")

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-538-chest-trap-1126.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CHEST = Position(27, 5)
UNSEEN = "トラップが見あたらない。"
FOUND = "箱に仕掛けられたトラップを発見した！"
FAILED = "箱のトラップ解除に失敗した。"
DISARMED = "箱に仕掛けられていたトラップを解除した。"


def later(step: int, *messages: str) -> dict:
    """DECLARED CONSTRUCTED: the capture's last board ``step`` presses later, with ``messages``."""
    raw = copy.deepcopy(CASE["boards"][-1])
    raw["turn"] += 10 * step
    raw["messages"] = list(messages)
    return raw


class ChestTrapRecordedTest(unittest.TestCase):
    def policy(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return recorded._policy(Path(directory.name), RACES)

    def decide(self, policy, raw):
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        if policy._chest_position is None and not policy._processed_chest_positions:
            policy._observe(policy._with_grid_memory(snapshot))
            # DECLARED CONSTRUCTED: the claim decision 10133's step-off left.
            policy._chest_position = CHEST
            policy._chest_phase_counts = {}
        # The capture has no checkpoint: the producer the live ladder reached (rung
        # _chest_processing_key#2) is asked with the production hostile filter.
        policy.last_reason = None
        key = policy._chest_processing_key(snapshot, policy._physical_hostiles(snapshot))
        return key, policy.last_reason

    def test_capture_is_the_open_after_six_searches(self):
        first, last = CASE["boards"][0], CASE["boards"][-1]
        self.assertEqual((first["player"]["y"], first["player"]["x"]), (26, 4))
        self.assertIn([27, 5, 1, 7], last["grid_map"]["found_items"])
        self.assertEqual(last["player"]["skill_ratings"]["searching"]["value"], 16)
        self.assertEqual(last["player"]["hp"], 1048)
        self.assertEqual([b["messages"] for b in CASE["boards"][-2:]],
                         [[UNSEEN], [UNSEEN + " <x2>"]])
        keys = [(row["reason"], row["key"]) for row in CASE["decision_tail"][2:]]
        self.assertEqual(keys, [("chest:search", "s")] * 6 + [("chest:disarm", "D3")] * 2
                         + [("chest:open", "o3")])

    def test_recorded_boards_keep_searching_and_never_open(self):
        policy = self.policy()
        decided = [self.decide(policy, raw) for raw in CASE["boards"]]
        self.assertNotIn(("o3", "chest:open"), decided)
        self.assertEqual(decided, [("s", "chest:search")] * len(CASE["boards"]))

    def test_unfound_trap_after_every_search_is_opened_as_untrapped(self):
        from hengbot.policy_constants import chest_search_presses

        presses = chest_search_presses(16)
        self.assertEqual(presses, 20)
        policy = self.policy()
        keys = [self.decide(policy, raw)[0] for raw in CASE["boards"]]
        step = 0
        while len(keys) < presses:
            step += 1
            keys.append(self.decide(policy, later(step))[0])
        self.assertEqual(keys, ["s"] * presses)
        self.assertEqual(self.decide(policy, later(step + 1)), ("D3", "chest:disarm"))
        self.assertEqual(self.decide(policy, later(step + 2, UNSEEN)), ("o3", "chest:open"))

    def test_found_trap_the_disarm_did_not_remove_stays_shut(self):
        policy = self.policy()
        self.assertEqual(self.decide(policy, CASE["boards"][0]), ("s", "chest:search"))
        self.assertEqual(self.decide(policy, later(1, FOUND)), ("D3", "chest:disarm"))
        self.assertEqual(self.decide(policy, later(2, FAILED)), ("D3", "chest:disarm"))
        key, reason = self.decide(policy, later(3, FAILED))
        self.assertFalse(str(key).startswith(("o", "D", "s")), (key, reason))
        self.assertIsNone(policy._chest_position)
        self.assertIn(CHEST, policy._processed_chest_positions)
        # The shut chest is no loot to pick up and work again.
        snapshot = parse_snapshot(later(4), policy._monrace_knowledge)
        self.assertTrue(policy._floor_pile_is_junk(snapshot, snapshot.grid_at(CHEST)))

    def test_found_trap_opens_after_the_disarm_answer(self):
        policy = self.policy()
        self.assertEqual(self.decide(policy, CASE["boards"][0]), ("s", "chest:search"))
        self.assertEqual(self.decide(policy, later(1, FOUND)), ("D3", "chest:disarm"))
        self.assertEqual(self.decide(policy, later(2, DISARMED)), ("o3", "chest:open"))


if __name__ == "__main__":
    unittest.main()
