import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from hengbot.model import Position, Snapshot
from hengbot.policy import HengbotPolicy, QUEST_STATUS_COMPLETED, QUEST_STATUS_TAKEN
from hengbot.quest_knowledge import QuestBattlefield, QuestInfo
from hengbot.quest_navigator import DOOR_SEARCH_BUDGET, QuestFloorNavigator, QuestPhase
from hengbot.quest_strategies import load_quest_strategies
from test_policy import grid, hostile, player
from hengbot.model import QuestState


def q1_battlefield():
    # Real 001_ThievesHideout start room: rows 5-8, columns 1-3; its two
    # sealed doors are at (5,4)/(8,4), and '<' is at (8,1).
    terrain = {(y, x): "wall" for y in range(10) for x in range(15)}
    for y in range(5, 9):
        for x in range(1, 8):
            terrain[y, x] = "floor"
    terrain[(5, 4)] = terrain[(8, 4)] = "door"
    terrain[(8, 1)] = "exit"
    return QuestBattlefield(
        terrain=terrain, player_start=(8, 1), entrance=(8, 1), exit=(8, 1),
        searchable=((5, 4), (8, 4)),
    )


def grids_for(battlefield, *, door_state="closed", loot=None, loot_count=1):
    result = {}
    for (y, x), kind in battlefield.terrain.items():
        if kind == "wall":
            continue
        if kind == "door" and door_state == "hidden":
            continue
        closed = kind == "door" and door_state == "closed"
        result[Position(y, x)] = grid(
            y, x, closed_door=closed,
            open_door=kind == "door" and door_state == "open",
            upstairs=kind == "exit", has_quest_exit=kind == "exit",
            quest_id=1 if kind == "exit" else 0,
            objects=loot_count if loot == (y, x) else 0,
        )
    return result


class QuestFloorNavigatorTest(unittest.TestCase):
    def setUp(self):
        self.battlefield = q1_battlefield()
        self.profile = load_quest_strategies(Path("strategy/quests"))[1]
        self.info = QuestInfo(1, "Thieves Hideout", 6, 5, 6, battlefield=self.battlefield)
        self.policy = HengbotPolicy(quest_knowledge={1: self.info}, quest_strategies={1: self.profile})

    def snapshot(
        self, y, x, *, status=QUEST_STATUS_TAKEN, monsters=(), loot=None,
        loot_count=1, door_state="closed",
    ):
        return Snapshot(
            player(y, x, hp=100, max_hp=100),
            grids_for(
                self.battlefield, door_state=door_state, loot=loot,
                loot_count=loot_count,
            ),
            list(monsters), floor_key=(0, 5, 1),
            quests={1: QuestState(1, status=status, fixed=True)},
        )

    def test_execute_holds_and_hold_budget_blocks_loudly(self):
        snap = self.snapshot(8, 3)
        self.assertEqual(self.policy.choose_key(snap), "5")
        self.assertEqual(self.policy.last_reason, "quest-strategy:hold")
        navigator = self.policy._quest_navigators[1]
        navigator.hold_turns = navigator._hold_budget(self.policy)
        self.assertEqual(self.policy.choose_key(snap), "5")
        self.assertEqual(self.policy.last_reason, "quest:blocked:hold")

    def test_completed_adjacent_hostile_is_cleared_before_exit(self):
        enemy = hostile(1, 8, 4)
        snap = self.snapshot(8, 3, status=QUEST_STATUS_COMPLETED, monsters=[enemy])
        self.assertEqual(self.policy.choose_key(snap), "6")
        self.assertEqual(self.policy.last_reason, "quest-strategy:melee")

    def test_survival_gate_preempts_navigator(self):
        hungry = replace(
            self.snapshot(8, 3).player,
            food_state="weak",
        )
        snap = replace(self.snapshot(8, 3), player=hungry)
        self.policy._survival_gate_key = lambda _snapshot, _hostiles: "SURVIVE"
        self.assertEqual(self.policy.choose_key(snap), "SURVIVE")

    def test_enter_approach_does_not_append_confirmation_to_movement(self):
        entrance = Position(8, 2)
        owner = SimpleNamespace(last_reason=None)
        owner._fixed_quest_entrance_positions = lambda _snapshot, _quest_id: {entrance}
        owner._nearest_goal_step = lambda _snapshot, _predicate: entrance
        owner._step_toward = lambda _snapshot, _step: "6"
        action = QuestFloorNavigator.enter_from_town(owner, self.snapshot(8, 1), 1)
        self.assertEqual(action, "6")
        self.assertEqual(owner.last_reason, "quest:enter:approach")
        action = QuestFloorNavigator.enter_from_town(owner, self.snapshot(8, 2), 1)
        self.assertEqual(action, ">y")
        self.assertEqual(owner.last_reason, "quest:enter")

    def test_phase_bound_fallbacks_have_in_code_rationales(self):
        source = Path("src/hengbot/quest_navigator.py").read_text(encoding="utf-8")
        self.assertIn("Phase bound fallback", source)
        self.assertIn("Phase bound prevents", source)

    def test_sweep_pickup_handles_multiple_objects(self):
        loot = self.snapshot(
            8, 6, status=QUEST_STATUS_COMPLETED, loot=(8, 6), loot_count=3,
            door_state="hidden",
        )
        self.assertEqual(self.policy.choose_key(loot), "gaaa")

    def test_sweep_collects_then_exit_searches_sealed_door_and_ascends(self):
        loot = self.snapshot(
            8, 6, status=QUEST_STATUS_COMPLETED, loot=(8, 6), door_state="hidden"
        )
        self.assertEqual(self.policy.choose_key(loot), "g")
        self.assertEqual(self.policy.last_reason, "quest:sweep:pickup")
        cleared = self.snapshot(
            8, 6, status=QUEST_STATUS_COMPLETED, loot=None, door_state="hidden"
        )
        self.assertEqual(cleared.grid_at(Position(8, 6)).object_count, 0)
        self.assertEqual(self.policy.choose_key(cleared), "4")
        at_door = self.snapshot(8, 5, status=QUEST_STATUS_COMPLETED, door_state="hidden")
        self.assertEqual(self.policy.choose_key(at_door), "s")
        self.assertEqual(self.policy.last_reason, "quest:exit:search-door")
        revealed = self.snapshot(8, 5, status=QUEST_STATUS_COMPLETED, door_state="closed")
        self.assertEqual(self.policy.choose_key(revealed), "o4")
        opened = self.snapshot(8, 5, status=QUEST_STATUS_COMPLETED, door_state="open")
        self.assertEqual(self.policy.choose_key(opened), "4")
        at_exit = self.snapshot(8, 1, status=QUEST_STATUS_COMPLETED, door_state="open")
        self.assertEqual(self.policy.choose_key(at_exit), "<")
        self.assertEqual(self.policy.last_reason, "quest:exit")

    def test_sealed_door_search_is_bounded(self):
        snap = self.snapshot(8, 5, status=QUEST_STATUS_COMPLETED, door_state="hidden")
        reasons = []
        for _ in range(DOOR_SEARCH_BUDGET + 1):
            self.policy.choose_key(snap)
            reasons.append(self.policy.last_reason)
        self.assertEqual(reasons[-1], "quest:blocked:exit")

    def test_full_floor_episode_never_emits_a_generic_reason(self):
        episode = [
            (self.snapshot(8, 1, door_state="hidden"), None),
            (self.snapshot(8, 2, door_state="hidden"), None),
            (self.snapshot(8, 3, door_state="hidden"), None),
            (self.snapshot(8, 3, monsters=[hostile(1, 8, 4)], door_state="hidden"), None),
            (self.snapshot(8, 5, status=QUEST_STATUS_COMPLETED, door_state="hidden"), "s"),
            (self.snapshot(8, 5, status=QUEST_STATUS_COMPLETED, door_state="closed"), "o4"),
            (self.snapshot(8, 5, status=QUEST_STATUS_COMPLETED, door_state="open"), "4"),
            (self.snapshot(8, 4, status=QUEST_STATUS_COMPLETED, door_state="open"), "4"),
            (self.snapshot(8, 3, status=QUEST_STATUS_COMPLETED, door_state="open"), "4"),
            (self.snapshot(8, 2, status=QUEST_STATUS_COMPLETED, door_state="open"), "4"),
            (self.snapshot(8, 1, status=QUEST_STATUS_COMPLETED, door_state="open"), "<"),
        ]
        forbidden = {"search", "breakout", "explore", "stuck", "wander"}
        for snap, expected_action in episode:
            action = self.policy.choose_key(snap)
            if expected_action is not None:
                self.assertEqual(action, expected_action)
            self.assertFalse(
                self.policy.last_reason in forbidden
                or self.policy.last_reason.startswith(("breakout:", "stuck:"))
                or self.policy.last_reason.endswith((":explore", ":wander")),
                self.policy.last_reason,
            )
        navigator = self.policy._quest_navigators[1]
        self.assertEqual(navigator.door_searches[(8, 4)], 1)


if __name__ == "__main__":
    unittest.main()
