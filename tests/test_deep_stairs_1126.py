"""An explored 50F+ dead-end floor is left by its stairs, not Word of Recall (1126).

Owner 2026-11-26 (verbatim): 「…いずれも、ゲーム内選択に関して私の以前の指示を破ることを許可する。」
-- the 2026-11-17 rule 「探索が済んだら帰還する」 and 2026-11-22 Q1 「今のまま帰還」 (explored_floor)
give way to the stairs on every explored dead-end floor of 50F and deeper (deep_stairs; its
docstring has the record: 49% of the no-descend floors' returns were this one, one level a trip).

Recorded boards: tests/fixtures/deep-efficiency-1117-explored-floor.jsonl.gz (n1-c life-216's
Angband 80F, a Magic-Eater, the last 15 boards of the visit the record ended by the up stairs it
stands on at the last board; tests/test_explored_floor_1117_recorded.py), driven through
``choose_key``.  80F is a dead end there: 81F asks the speed the character lacks.  DECLARED
CONSTRUCTED, as in that test: the absorbed *Destruction* list row and the stalled growth window
before the last board, its found items dropped.  DECLARED CONSTRUCTED here: Angband's recall
depth raised from 80 to 95 for the finale's 95F exploration (finale_farm's case, folded in), a
kept Home census holding every finale count, the trip's stair floors already left, the floor's
exits locked (a quest), the return refused by a depth gate, Angband 99F, the expedition.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import angband_finale, deep_stairs, explored_floor, fled_floor_stairs, me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import UP_STAIRS_KEY
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "deep-efficiency-1117-explored-floor.jsonl.gz"
LAST = 5555864


class DeepStairs1126Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, *, depth=None, floors=0, stocked=False, patch=None):
        """The boards in order; the last one with the stalled window.  ``depth``: Angband's
        recall depth (None: the record's 80); ``floors``: the explored floors this trip already
        left by the stairs; ``stocked``: a kept Home census holding every finale count;
        ``patch``: called with the policy before the boards."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)

        def board_of(raw):
            raw = copy.deepcopy(raw)
            if depth is not None:
                raw["progress"]["dungeon_recall_depths"]["1"] = depth  # DECLARED CONSTRUCTED
            return policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))

        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        if stocked:
            angband_finale.memory(policy).home_counts = {
                kind: 99 for kind in (*angband_finale.CARRY, angband_finale.RESTORE_MANA,
                                      angband_finale.RECHARGING)}
        setattr(policy, deep_stairs.FLOORS, floors)
        if patch is not None:
            patch(policy)
        rows = {}
        for raw in self.boards:
            if raw["turn"] == LAST:
                raw = copy.deepcopy(raw)
                for field in ("found_items", "found_item_names", "found_item_ids"):
                    raw["grid_map"][field] = []
                policy._known_loot.clear()
            board = board_of(raw)
            if board.turn == LAST:
                known = len(policy._remembered_known_t)
                setattr(policy, explored_floor.MEMORY, {
                    "floor": board.floor_key, "counts": (known,) * explored_floor.WINDOW})
            key = policy.choose_key(board)
            rows[board.turn] = (key, policy.last_reason, policy._last_return_trigger, board)
            if key:
                policy.confirm_key_posted(key)
        return policy, rows

    def assert_stairs(self, policy, rows):
        key, reason, trigger, board = rows[LAST]
        # Before: return:recall under explored-dead-end-floor (Word of Recall read).
        self.assertEqual((key, reason), (UP_STAIRS_KEY, deep_stairs.ASCEND_REASON), rows[LAST][:3])
        self.assertNotEqual(trigger, explored_floor.TRIGGER)
        self.assertFalse(policy._returning_to_town)
        self.assertEqual(deep_stairs.floors(policy), 1)
        self.assertTrue(getattr(policy, deep_stairs.COUNTED))
        # The down stair it lands on leads back to this explored level: recorded, no cooldown.
        self.assertEqual(getattr(policy, fled_floor_stairs.PENDING), (board.floor_key, 80))
        self.assertFalse(policy._descent_is_blocked(board))

    def assert_recall(self, rows):
        key, reason, trigger, _board = rows[LAST]
        self.assertEqual(reason, explored_floor.REASON, rows[LAST][:3])
        self.assertEqual(trigger, explored_floor.TRIGGER)
        self.assertTrue(key.startswith("r"), key)

    def test_the_80f_depth_gate_floor_is_left_by_its_stairs(self):
        policy, rows = self.replay()
        board = rows[LAST][3]
        self.assertFalse(angband_finale.preparing(board))
        self.assertTrue(explored_floor.dead_end(policy, board))
        self.assertTrue(deep_stairs.applies(policy, board))
        self.assert_stairs(policy, rows)

    def test_the_95f_finale_exploration_is_left_by_its_stairs(self):
        # finale_farm's case, with or without a Black Market shortage: one rule.
        for stocked in (False, True):
            with self.subTest(stocked=stocked):
                policy, rows = self.replay(depth=95, stocked=stocked)
                self.assertTrue(angband_finale.preparing(rows[LAST][3]))
                self.assert_stairs(policy, rows)

    def test_the_trip_reads_recall_after_its_stair_floors(self):
        _policy, rows = self.replay(floors=deep_stairs.EXTRA_FLOORS)
        self.assert_recall(rows)

    def test_a_quest_floor_reads_recall_as_before(self):
        def locked(policy):
            policy._floor_navigation_exit_locked = lambda snapshot: True
        policy, rows = self.replay(patch=locked)
        self.assertFalse(deep_stairs.applies(policy, rows[LAST][3]))

    def test_a_return_the_depth_gate_refuses_reads_recall_as_before(self):
        # The stair back down to 80F asks an ability the character no longer has.
        def gated(policy):
            missing = policy._missing_required_abilities
            policy._missing_required_abilities = (
                lambda snapshot, depth: ("speed",) if depth == 80 else missing(snapshot, depth))
        _policy, rows = self.replay(patch=gated)
        self.assertNotEqual(rows[LAST][1], deep_stairs.ASCEND_REASON, rows[LAST][:3])
        self.assertFalse(deep_stairs.applies(_policy, rows[LAST][3]))

    def test_shallow_finale_and_expedition_floors_are_not_left_so(self):
        from hengbot import finale_prep
        policy, rows = self.replay()
        board = rows[LAST][3]
        raw = copy.deepcopy(self.boards[-1])
        self.assertTrue(deep_stairs.applies(policy, board))
        for level in (49, 99, 100):
            shifted = copy.deepcopy(raw)
            shifted["floor"]["level"] = level
            self.assertFalse(deep_stairs.applies(policy, parse_snapshot(shifted, self.monrace)),
                             level)
        finale_prep.phase(policy).lifted = True  # the expedition: its own rules
        self.assertFalse(deep_stairs.applies(policy, board))

    def test_a_town_board_starts_the_count_again(self):
        policy, rows = self.replay()
        self.assertEqual(deep_stairs.floors(policy), 1)
        policy.observe_town_visit_epoch(True, rows[LAST][3].turn + 10)
        self.assertEqual(deep_stairs.floors(policy), 0)


if __name__ == "__main__":
    unittest.main()
