"""An explored 95F floor is left by its stairs while a Black Market finale supply is short (1126).

Owner 2026-11-26 (verbatim): 「n1-cはこのままゾンビ魔道具術師で勝率と時間効率改善を進める。…いずれも、
ゲーム内選択に関して私の以前の指示を破ることを許可する。」 -- the 2026-11-17 rule 「探索が済んだら帰還
する」 (explored_floor) gives way to the stairs while finale_farm ``farming``.  n1-c life-222
(2026-11-26 10:05-12:58): 50 one-floor 95F trips for the Black Market's Restore Mana, 17 of them
ended by ``explored-dead-end-floor`` with pack slots free (finale_farm's docstring has the record).

Recorded boards: tests/fixtures/deep-efficiency-1117-explored-floor.jsonl.gz (n1-c life-216's
Angband 80F, a Magic-Eater, the last 15 boards of the visit the record ended by the up stairs it
stands on at the last board; tests/test_explored_floor_1117_recorded.py), driven through
``choose_key``.  DECLARED CONSTRUCTED, as in that test: the absorbed *Destruction* list row and the
stalled growth window before the last board, its found items dropped.  DECLARED CONSTRUCTED here:
Angband's recall depth raised from 80 to 95 on every board (the 95F exploration of the finale,
angband_finale ``preparing``; 81F stays refused for the speed it asks, so the floor is a dead end
as before), no Home census (the finale's Black Market supplies are short: only the pack counts),
or a kept census holding every count (none short).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import angband_finale, explored_floor, finale_bm_tour, finale_farm, me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import UP_STAIRS_KEY
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "deep-efficiency-1117-explored-floor.jsonl.gz"
LAST = 5555864


class FinaleFarm1126Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, *, depth=95, floors=0, stocked=False, town_first=False):
        """The boards in order; the last one with the stalled window.  ``floors``: the explored
        floors this trip already left by the stairs; ``stocked``: a kept Home census holding
        every finale count."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)

        def board_of(raw):
            raw = copy.deepcopy(raw)
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
        setattr(policy, finale_farm.FLOORS, floors)
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

    def test_the_farming_board(self):
        policy, rows = self.replay()
        board = rows[LAST][3]
        self.assertTrue(angband_finale.preparing(board))
        self.assertTrue(explored_floor.dead_end(policy, board))
        self.assertGreater(finale_bm_tour.shortage(policy, board), 0)
        self.assertTrue(finale_farm.farming(policy, board))

    def test_an_explored_floor_is_left_by_its_stairs(self):
        policy, rows = self.replay()
        key, reason, trigger, _board = rows[LAST]

        # Before: return:recall under explored-dead-end-floor (Word of Recall read).
        self.assertEqual((key, reason), (UP_STAIRS_KEY, finale_farm.ASCEND_REASON), rows[LAST][:3])
        self.assertNotEqual(trigger, explored_floor.TRIGGER)
        self.assertFalse(policy._returning_to_town)
        self.assertEqual(finale_farm.floors(policy), 1)
        self.assertTrue(getattr(policy, finale_farm.COUNTED))

    def test_the_trip_reads_recall_after_its_stair_floors(self):
        policy, rows = self.replay(floors=finale_farm.FARM_STAIR_FLOORS)
        key, reason, trigger, _board = rows[LAST]
        self.assertEqual(reason, explored_floor.REASON, rows[LAST][:3])
        self.assertEqual(trigger, explored_floor.TRIGGER)
        self.assertTrue(key.startswith("r"), key)

    def test_no_shortage_reads_recall_as_before(self):
        policy, rows = self.replay(stocked=True)
        board = rows[LAST][3]
        self.assertEqual(finale_bm_tour.shortage(policy, board), 0)
        self.assertFalse(finale_farm.farming(policy, board))
        self.assertEqual(rows[LAST][1], explored_floor.REASON, rows[LAST][:3])
        self.assertEqual(rows[LAST][2], explored_floor.TRIGGER)

    def test_a_character_short_of_the_95f_exploration_reads_recall_as_before(self):
        policy, rows = self.replay(depth=80)
        board = rows[LAST][3]
        self.assertFalse(angband_finale.preparing(board))
        self.assertFalse(finale_farm.farming(policy, board))
        self.assertEqual(rows[LAST][1], explored_floor.REASON, rows[LAST][:3])

    def test_the_lifted_cap_reads_recall_as_before(self):
        from hengbot import finale_prep
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        raw = copy.deepcopy(self.boards[-1])
        raw["progress"]["dungeon_recall_depths"]["1"] = 95
        board = parse_snapshot(raw, self.monrace)
        policy.prime(board)
        self.assertTrue(finale_farm.farming(policy, board))
        finale_prep.phase(policy).lifted = True  # the expedition: its own rules
        self.assertFalse(finale_farm.farming(policy, board))

    def test_a_town_board_starts_the_count_again(self):
        policy, rows = self.replay()
        self.assertEqual(finale_farm.floors(policy), 1)
        town = copy.deepcopy(self.boards[-1])
        town["floor"].update(dungeon_id=0, level=0, in_town=True)
        board = parse_snapshot(town, self.monrace)
        self.assertTrue(board.in_town)
        angband_finale.observe(policy, board)
        self.assertEqual(finale_farm.floors(policy), 0)


if __name__ == "__main__":
    unittest.main()
