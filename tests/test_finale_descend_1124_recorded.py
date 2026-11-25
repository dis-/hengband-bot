"""The finale expedition goes straight down from its 95F landing (n1-c life-221, 2026-11-24).

Owner 2026-11-24 (verbatim): 「決戦装備にしたら速やかに最下層まで降りること。寄り道は不要。」

Recorded (tests/extract_finale_descend_1124_fixture.py, ``finale-descend-n1c-221-1124``): the 95F
boards of the visit after the preparation lifted the cap (16:51:52; Oberon killed, the Serpent's
100F the target).  Live decided on them: the arrival's ``explore`` (seq10964), the detected
threat's ``detected:prepare-choke`` / ``detected:hold-choke`` (11191-11192), ``explore`` and
``seek-loot`` (11434, 11454), and with the pack full (23 of 23) ``return:recall`` under
``pack-full`` (12276, 6454143).

Each window is decided open loop on a fresh policy primed on its first board: the descent's
reasons (``finale-descent:*``), the arrival's powers (me_powers FLOOR, ``me-power:*``) or the
emergency ladder above it, never the exploration, the loot, the holds or the ordinary return.

DECLARED CONSTRUCTED: the expedition's mark (finale_prep ``lifted``, step ``done``) and the
absorbed-device lists (tests/support/finale_416 ``device_lists``; the snapshot logs carry none).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import dataclasses
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import finale_descent, finale_prep
from hengbot.model import (
    DUNGEON_ANGBAND, SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, SV_POTION_STAR_HEALING,
    parse_snapshot)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import PACK_CAPACITY
from support import finale_416
from support.recorded import EDIT, _policy

BOARDS = Path(__file__).with_name("fixtures") / "finale-descend-n1c-221-1124.jsonl.gz"
WINDOWS = {
    "arrival": (6450711, 6450729),
    "choke": (6451301, 6451319),
    "explore-loot": (6451936, 6452003),
    # Up to the recorded Recall read: the boards after it show the Recall running.
    "pack-full": (6454130, 6454143),
}
PACK_FULL_RECALL_TURN = 6454143
# What live answered on these boards, none of which the expedition's way down may answer.
WANDERING = ("explore", "seek-loot", "pickup", "loot:", "detected:", "anaguma:", "return:",
             "hunt", "ranged:", "search", "identify:", "inventory:", "trigger-autodestroy")


def boards():
    with gzip.open(BOARDS, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class FinaleDescend1124RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.raws = boards()

    def drive(self, window):
        """(policy, last board, [(turn, key, reason)]) of the window's boards, open loop."""
        first_turn, last_turn = WINDOWS[window]
        raws = [raw for raw in self.raws if first_turn <= raw["turn"] <= last_turn]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raws[0]), self.monrace))
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        held = finale_prep.phase(policy)
        held.lifted, held.step = True, finale_prep.DONE
        decided, owner, board = [], None, None
        for raw in raws:
            raw = copy.deepcopy(raw)
            if owner:
                raw["_completed_operation_owner"] = owner
            board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            policy._me_device_lists = finale_416.device_lists(board.turn)
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            decided.append((board.turn, key, policy.last_reason))
            owner = policy.last_reason if key else None
            if key:
                policy.confirm_key_posted(key)
        return policy, board, decided

    def assert_descends(self, decided):
        for turn, key, reason in decided:
            with self.subTest(turn=turn):
                self.assertIsNotNone(key)
                self.assertFalse(str(reason).startswith(WANDERING), reason)
        self.assertTrue(any(str(reason).startswith(finale_descent.REASON)
                            for _turn, _key, reason in decided), decided)

    def test_the_way_down_applies_on_95f(self):
        policy, board, _decided = self.drive("arrival")
        self.assertEqual(board.floor_key, (DUNGEON_ANGBAND, 95, 0))
        self.assertEqual(finale_descent.target_depth(board), 100)
        self.assertTrue(finale_descent.applies(policy, board))

    def test_arrival_goes_for_the_stairs(self):
        _policy, _board, decided = self.drive("arrival")
        self.assert_descends(decided)

    def test_no_choke_hold(self):
        _policy, _board, decided = self.drive("choke")
        self.assert_descends(decided)

    def test_no_exploration_or_loot(self):
        _policy, _board, decided = self.drive("explore-loot")
        self.assert_descends(decided)

    def test_full_pack_keeps_descending(self):
        policy, board, decided = self.drive("pack-full")
        self.assertEqual(len(board.inventory), PACK_CAPACITY)
        self.assertFalse(policy._should_start_town_return(board))
        self.assertFalse(policy._descent_is_blocked(board))
        recorded = [entry for entry in decided if entry[0] == PACK_FULL_RECALL_TURN]
        self.assertEqual(len(recorded), 1)
        # Recorded: ('rm', 'return:recall') under the trigger pack-full.
        self.assertNotEqual(recorded[0][2], "return:recall")
        self.assertFalse(policy._returning_to_town)
        self.assert_descends(decided)

    def test_healing_potions_spent_recall(self):
        # Owner 2026-11-25 (b)-5 「回復の薬が尽きたら帰還する」: the Healing and the *Healing*.
        # DECLARED CONSTRUCTED: the recorded pack-full board (30 Healing, 15 *Healing*, 10 Cure
        # Critical Wounds) with stacks taken out.
        policy, board, _decided = self.drive("pack-full")
        self.assertTrue(finale_descent.applies(policy, board))
        self.assertFalse(policy._should_start_town_return(board))

        def without(*svals):
            return dataclasses.replace(board, inventory=[
                item for item in board.inventory
                if not (item.is_potion and item.sval in svals)])

        # The Cure Critical Wounds are not counted; one kind of the two left is enough.
        self.assertFalse(policy._should_start_town_return(without(SV_POTION_CURE_CRITICAL)))
        self.assertFalse(policy._should_start_town_return(without(SV_POTION_HEALING)))
        self.assertFalse(policy._should_start_town_return(without(SV_POTION_STAR_HEALING)))
        spent = without(SV_POTION_HEALING, SV_POTION_STAR_HEALING)
        self.assertEqual(len(spent.inventory), len(board.inventory) - 2)
        self.assertTrue(policy._should_start_town_return(spent))
        self.assertEqual(policy._last_return_trigger, finale_descent.HEALING_TRIGGER)

    def test_outside_the_expedition_unchanged(self):
        policy, board, _decided = self.drive("pack-full")
        held = finale_prep.phase(policy)
        held.lifted = False
        self.assertFalse(finale_descent.applies(policy, board))
        self.assertTrue(policy._should_start_town_return(board))


if __name__ == "__main__":
    unittest.main()
