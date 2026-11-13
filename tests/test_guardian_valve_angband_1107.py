"""Owner 2026-11-07: the guardian valve takes Angband first when its landing passes.

「鉄獄の帰還の階が条件を満たすなら鉄獄へ行き、だめな時だけほかのダンジョンから
選ぶ。」  The viewing n1-c life-159 (Lv38) pursued the Castle; at 12:57 its recall
was refused as a guardian bounce and ``_activate_safe_recall_fallback`` (reason
``guardian_valve``) chose the shallowest other entered dungeon whose landing
passed, the Orc cave 23F.  Angband was only taken once every entered alternate
was exhausted (owner 2026-10-27).  Now the guardian valve asks Angband first:
its recall landing must not be a guardian floor the kit cannot pass, must have
the required abilities for that depth, must be a dungeon the character can
fight in, and must not be shut by the random-quest hold.  Only otherwise is the
old choice among the other entered dungeons made.  The over-extension,
no-depth-progress and safe-fallback switches are unchanged.

Substrate: DECLARED CONSTRUCTED.  The life-159 state log is not available to
this checkout, so the board is built after test_top_stops_guardian's projected
town scene (quiet town, inn two steps east, supplies complete for the
departure, equipment optimization done):
- a Lv38 warrior with every resistance the table asks at 65F, a reliable Staff
  of *Destruction* (the 50F+ means) and speed 110 (so 81F+ is missing
  ``speed+25``);
- entered Angband, the Orc cave (conquered, landing 23) and the Castle, whose
  recall landing 65 is its guardian floor (Castle max depth 65, guardian 882;
  owner 2026-11-11 C2 「能力的には64Fから成果を得るのに十分である。」: 64F is explored,
  only 65F is the guardian floor)
  and whose guardian the kit cannot beat, so the Castle recall is refused for
  the guardian only, and the Dark cave at 65 (added 2026-11-13: the old choice
  must land at the fallback depth floor, the deepest reached minus 20);
- Angband's saved recall depth is 50 (passes every check; 40 before the floor)
  or 85 (missing ``speed+25``), the only difference between the first two pins.
Every pin decides through ``HengbotPolicy.choose_key``.
"""

import tests  # noqa: F401
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import (
    DUNGEON_ANGBAND, PLAYER_CLASS_WARRIOR, Position, QuestState, Snapshot,
    SV_LITE_LANTERN, SV_POTION_CURE_CRITICAL, SV_SCROLL_TELEPORT,
    SV_SCROLL_WORD_OF_RECALL, SV_STAFF_DESTRUCTION, SV_STAFF_IDENTIFY,
    TVAL_FLASK, TVAL_FOOD, TVAL_LITE, TVAL_POTION, TVAL_SCROLL, TVAL_STAFF,
    TVAL_SWORD)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    DESTRUCTION_GATE_LABEL, EMPTY_DIVE_LIMIT, QUEST_STATUS_FINISHED,
    required_depth_gates)
from policy_fixtures import grid, item, player, set_completed_equipment_optimization

EDIT = Path("C:/hengband/lib/edit")
ORC_CAVE = 3
CASTLE = 12
CASTLE_LANDING = 65  # Castle max depth 65: its guardian floor (64F is explored since C2)
ORC_CAVE_LANDING = 23
# Owner 2026-11-13 「フォールバックは最新到達-20Fまでにする。」: the Castle 65 is reached, so the
# fallback floor is 45 (65 with Angband 85).  Angband's acceptable landing is 50 (40 before the
# floor), and the Dark cave at 65 is the other entered dungeon the old choice takes: the Orc
# cave 23 is under every floor here.
DARK_CAVE = 19
DARK_CAVE_LANDING = 65  # Dark cave 55-72: not its guardian floor
ANGBAND_ACCEPTABLE = 50
ANGBAND_NEEDS_SPEED = 85  # 81F+ asks speed+25 of a speed-110 character


def scene(angband_landing, *, target=CASTLE):
    y, x = 31, 77
    abilities = (
        frozenset(required_depth_gates(CASTLE_LANDING)) - {DESTRUCTION_GATE_LABEL}
    ) | {"see_invisible", "resist_fear"}
    actor = replace(
        player(y, x, level=38, hp=500, max_hp=500, gold=50000,
               class_id=PLAYER_CLASS_WARRIOR, abilities=abilities),
        device_skill=120,  # the Staff of *Destruction* is a reliable means
    )
    terrain = {
        Position(y, column): grid(y, column, building_type=0 if column == x + 2 else -1)
        for column in range(x, x + 3)
    }
    board = Snapshot(
        actor, terrain, [], turn=500000, town_flag=True, town_id=0,
        recall_dungeon_id=target,
        recall_depth=CASTLE_LANDING if target == CASTLE else angband_landing,
        entered_dungeon_ids=(DUNGEON_ANGBAND, ORC_CAVE, CASTLE, DARK_CAVE),
        dungeon_recall_depths={DUNGEON_ANGBAND: angband_landing,
                               ORC_CAVE: ORC_CAVE_LANDING, CASTLE: CASTLE_LANDING,
                               DARK_CAVE: DARK_CAVE_LANDING},
        angband_recall_unlocked=True,
        conquered_dungeon_ids=(ORC_CAVE,),
        quests={34: QuestState(34, status=QUEST_STATUS_FINISHED),
                2: QuestState(2, status=QUEST_STATUS_FINISHED)},
        inventory=[item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=15),
                   item("b", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                   item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=15),
                   item("d", TVAL_FOOD, 35, count=10),
                   item("e", TVAL_FLASK, 0, count=5),
                   item("f", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20),
                   item("g", TVAL_STAFF, SV_STAFF_DESTRUCTION, charges=30, known=True)],
        equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True),
                   item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7500, is_equipment=True)],
    )
    policy = HengbotPolicy(
        dungeon_knowledge=load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc"))
    policy.prime(board)
    policy.consume_home_knowledge(())
    policy.consume_skill_knowledge({"player": {"level": 38}, "knowledge": {
        "skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]}})
    set_completed_equipment_optimization(policy)
    policy._equipment_optimization_last_depth = CASTLE_LANDING
    policy._char_dump_done_this_visit = True
    policy._town_store_attempted[6] = board.turn
    policy._target_dungeon_id = target
    if target == CASTLE:
        # The latched conquest target (policy_quest._conquest_target).
        policy._conquest_committed = CASTLE
    return policy, board


class GuardianValveAngbandFirstTest(unittest.TestCase):
    def test_castle_bounce_goes_to_angband_when_its_landing_passes(self):
        policy, board = scene(ANGBAND_ACCEPTABLE)
        self.assertTrue(policy._recall_refused_only_for_guardian(board, CASTLE))
        self.assertTrue(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertEqual(
            (policy._alternate_dungeon, policy._alternate_dungeon_reason,
             policy._target_dungeon_id),
            (DUNGEON_ANGBAND, "guardian_valve", DUNGEON_ANGBAND))
        self.assertFalse(policy._rumor_unlock_pending)

    def test_castle_bounce_keeps_the_old_choice_when_angband_lacks_an_ability(self):
        policy, board = scene(ANGBAND_NEEDS_SPEED)
        self.assertTrue(policy._recall_refused_only_for_guardian(board, CASTLE))
        self.assertEqual(
            policy._missing_required_abilities(board, ANGBAND_NEEDS_SPEED),
            frozenset({"speed+25"}))
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertEqual(
            (policy._alternate_dungeon, policy._alternate_dungeon_reason,
             policy._target_dungeon_id),
            (DARK_CAVE, "guardian_valve", DARK_CAVE))

    def test_bounce_off_angband_itself_keeps_the_old_choice(self):
        # DECLARED CONSTRUCTED: the observation's guardian-bounce valve just
        # before it judges a guardian-only streak pursued in Angband (whose
        # landing would itself pass); the bounced dungeon is never re-picked.
        policy, board = scene(ANGBAND_ACCEPTABLE, target=DUNGEON_ANGBAND)
        policy._target_empty_dives = EMPTY_DIVE_LIMIT
        policy._guardian_bounce_dives = EMPTY_DIVE_LIMIT
        policy._last_return_trigger = "guardian-kit-insufficient"
        policy.choose_key(board)
        self.assertEqual(
            (policy._alternate_dungeon, policy._alternate_dungeon_reason),
            (DARK_CAVE, "guardian_bounce_valve"))

    def test_the_orc_cave_under_the_floor_is_no_old_choice(self):
        """Owner 2026-11-13: without the Dark cave the old choice was the Orc cave 23, under
        the floor 65 (Angband 85 reached); nothing qualifies and the bounce stops visibly."""
        policy, board = scene(ANGBAND_NEEDS_SPEED)
        board = replace(board, entered_dungeon_ids=(DUNGEON_ANGBAND, ORC_CAVE, CASTLE))
        self.assertIsNone(policy._pick_alternate_dungeon(board, guardian_bounced_dungeon=CASTLE))
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")
        self.assertIsNone(policy._alternate_dungeon)


if __name__ == "__main__":
    unittest.main()
