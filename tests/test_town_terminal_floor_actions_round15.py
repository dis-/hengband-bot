"""Last eight rungs: floor actions pass; recall uses the existing town gate."""
import tests  # noqa: F401

from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import (
    DUNGEON_YEEK_CAVE, Position,
    SV_SCROLL_WORD_OF_RECALL, TVAL_CHEST, TVAL_SCROLL,
)
from hengbot.policy_constants import PACK_CAPACITY, QUEST_STATUS_TAKEN, RECALL_MIN_DEPTH, STUCK_ESCAPE_LIMIT
from policy_fixtures import grid, item
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on
import test_policy_identification as identification_fixtures
import test_policy_town as town_fixtures
from test_loot_triage import full_snapshot


NON_ERRANDS = (
    "_chest_processing_key#1", "_chest_processing_key#2",
    "_normal_loot_key#1", "_normal_loot_key#2",
    "_kill_quest_floor_recovery_key", "_start_kill_quest_regeneration",
)


class FloorActionAdmissionTest(unittest.TestCase):
    def test_non_errands_have_explicit_reasons_and_allow_the_actual_floor_actions(self):
        for rung in NON_ERRANDS:
            decl = tt.TERMINALS[rung]
            self.assertEqual(decl.mode, tt.NO_REFUSAL, rung)
            self.assertTrue(decl.no_refusal_reason.startswith("not a town errand: "), rung)
            self.assertNotIn(rung, tt.SHADOW_RUNGS)
            if rung.startswith("_chest"):
                snap = identification_fixtures.ChestProcessingTest()._snap(inventory=[
                    item("c", TVAL_CHEST, 1, name="small wooden chest")])
                name, args, expected = "_chest_processing_key", ([],), "dc"
                policy = policy_on(snap)
            elif rung.startswith("_normal"):
                snap = replace(board(), town_flag=False, floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
                    inventory=[], grids={Position(10, 10): grid(10, 10, objects=1)},
                    player=replace(board().player, position=Position(10, 10)))
                name, args, expected = "_normal_loot_key", ([],), "g"
                policy = policy_on(snap)
                policy._position_changed = True
            else:
                depth = 6 if rung == "_kill_quest_floor_recovery_key" else 5
                policy, snap = town_fixtures.TownRecallReturnTest()._exhausted_q14_floor(QUEST_STATUS_TAKEN, depth)
                policy._build_grid_index(snap)
                policy._begin_map_predicate_cache(snap)
                name, args, expected = rung, (), "<"
            terminal = tt.rung_terminal(policy, rung, snap)
            self.assertEqual(terminal.terminal_id, tt.NO_REFUSAL)
            key = policy._town_producer_entry(rung, lambda: getattr(policy, name)(snap, *args), board=snap)
            self.assertEqual(key, expected, rung)
            self.assertEqual(policy._decision_terminal_admissions, [])

    def test_floor_exit_dispatchers_do_not_preempt_stairs_or_loot(self):
        for rung in ("_finish_mining_floor", "_victory_loot_key"):
            snap = replace(board(), inventory=[],
                player=replace(board().player, position=Position(10, 10)),
                grids={Position(10, 10): grid(10, 10, upstairs=True, objects=1)})
            policy = policy_on(snap)
            policy._yeek_victory_loot = True
            policy._position_changed = True
            if rung == "_victory_loot_key":
                snap = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, 0, 0))
                policy = policy_on(snap)
                policy._yeek_victory_loot = True
                policy._position_changed = True
            self.assertEqual(tt.TERMINALS[rung].mode, tt.ENFORCE)
            self.assertEqual(tt.rung_terminal(policy, rung, snap).terminal_id, tt.NO_REFUSAL)
            with patch.object(policy, "_recall_town_departure_conjuncts",
                              side_effect=AssertionError("non-read branch asked departure")):
                key = policy._town_producer_entry(
                    rung, lambda: getattr(policy, rung)(snap), board=snap,
                    family="fundraising" if rung == "_finish_mining_floor" else None)
            self.assertEqual(key, "g" if rung == "_victory_loot_key" else "<")
            self.assertEqual(policy._decision_terminal_admissions, [])

    def test_both_mining_reads_ask_the_acting_town_board_before_composing_recall(self):
        for depth in (0, RECALL_MIN_DEPTH):
            for mode in (tt.SHADOW, tt.ENFORCE):
                recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
                snap = replace(board(), inventory=[recall], floor_key=(DUNGEON_YEEK_CAVE, depth, 0),
                    player=replace(board().player, position=Position(10, 10)),
                    grids={Position(10, 10): grid(10, 10)})
                policy = policy_on(snap)
                policy._fundraising_mode = "mine"
                policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
                # Simulate a newer argument board after the last observed dungeon board.
                policy._map_predicate_snapshot = replace(snap, town_flag=False, floor_key=(2, 1, 0))
                with patch.dict(tt.TERMINALS, {"_read_dungeon_recall_scroll_key":
                        tt.TERMINALS["_read_dungeon_recall_scroll_key"]._replace(mode=mode)}), \
                        patch.object(policy, "_recall_town_departure_conjuncts",
                                     return_value={"combat_weapon_ready": False}), \
                        patch.object(policy, "_read_key", wraps=policy._read_key) as read:
                    key = policy._finish_mining_floor(snap)
                self.assertEqual(key, "rr" if mode == tt.SHADOW else None, (depth, mode))
                self.assertEqual(read.call_count, int(mode == tt.SHADOW))
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["rung"], "_read_dungeon_recall_scroll_key")
                self.assertEqual(row["codes"], ["departure:combat_weapon_ready"])

    def test_mining_dungeon_reads_keep_keys_reasons_and_confirmation_state(self):
        for depth in (1, RECALL_MIN_DEPTH):
            recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
            snap = replace(board(), town_flag=False, inventory=[recall],
                floor_key=(DUNGEON_YEEK_CAVE, depth, 0),
                player=replace(board().player, position=Position(10, 10)),
                grids={Position(10, 10): grid(10, 10)})
            policy = policy_on(snap)
            policy._fundraising_mode = "mine"
            policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
            with patch.object(policy, "_recall_town_departure_conjuncts",
                              side_effect=AssertionError("dungeon read asked town gate")):
                self.assertEqual(policy._finish_mining_floor(snap), "rr")
            self.assertEqual(policy.last_reason,
                "fundraise:recall" if depth >= RECALL_MIN_DEPTH else "fundraise:recall-stuck")
            self.assertIsNone(policy._dungeon_recall_issue_watch)
            self.assertEqual(policy._decision_terminal_admissions, [])

    def test_full_pack_victory_relief_delegates_recall_to_the_existing_child_entry(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = full_snapshot([recall] + [item(chr(65 + i), 23, 1, known=True,
            fully_known=True, name="sword", is_equipment=True) for i in range(PACK_CAPACITY - 1)],
            object_count=0)
        policy = policy_on(snap)
        policy._yeek_victory_loot = True
        policy._map_predicate_snapshot = board()
        calls = []
        entry = policy._town_producer_entry

        def observe(rung, call, **kwargs):
            calls.append((rung, tt.rung_terminal(policy, rung, snap)))
            return entry(rung, call, **kwargs)

        with patch.object(policy, "_town_producer_entry", side_effect=observe), \
                patch.object(policy, "_recall_town_departure_conjuncts",
                             side_effect=AssertionError("dungeon relief asked town gate")):
            key = policy._victory_loot_key(snap)
        self.assertEqual(key, "rr")
        self.assertIn(("_read_dungeon_recall_scroll_key", None), calls)
        self.assertEqual(policy._dungeon_recall_issue_watch[0], snap.floor_key)
        self.assertEqual(policy._decision_terminal_admissions, [])


if __name__ == "__main__":
    unittest.main()
