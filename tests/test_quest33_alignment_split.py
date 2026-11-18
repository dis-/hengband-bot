"""QUEST_33 (クローン地獄): GOOD and EVIL summoners must never face each other (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「Q33の戦略を作って。goodとevilの召喚持ちが相対するとお互いに召喚して
収拾がつかなくなることに留意して立案すること。急いで受ける必要のあるクエストではないので戦力は過剰に
要求して良い。」

The strategy (strategy/quests/QUEST_33.jsonc) walks the floor room by room (quest_room_sweep) and
refuses every cell from which a living GOOD summoner (クイーン・アント 581) and a living EVIL one
(イット 393, ガチャピン 441, ボクルグ 489, ダゴン 595) would both act: the game processes a monster
only while the player is within its vision (monster-processor.cpp decide_process_continue), and two
monsters fight only GOOD against EVIL (monster-entity.cpp check_sub_alignments).  Acceptance asks
750 per 10 game turns against the Queen (1500 HP in two turns, quest_one_turn_kill ``turns``), read
at the speed the always-hasted force fights at (owner 2026-11-19 「攻撃力の判定を1行動あたりでは
なく、10ゲームターンあたりのダメージで評価して」).

Recorded: the town arrivals of 2026-11-19 shared with QUEST_32's tests
(tests/fixtures/quest32-one-turn-kill-1119): n1-a life-531 (warrior Lv42, +4: 578.3 an action on
the Queen, 809.7 per 10 game turns) and n1-b life-411 (Magic-Eater Lv50, +25: 415.0 melee, 280.0
devices, 1452.4) meet it -- n1-a is refused for its Light scrolls and resists, n1-b only for its HP and is accepted at
full HP; n1-c life-217 (Magic-Eater Lv36, +6: 180.6, 288.9, 469.5 at the hasted +16) is refused for
the figure, and the non-urgent quest is passed over.  Per action all three were refused.

DECLARED CONSTRUCTED: n1-a's board with 4 blows a turn instead of 7 (330.5: 462.7 at +4, 793.2
at the hasted +14) is on the hasted tier and doses before the Queen; n1-b's board at full HP;
the floor boards below put the recorded n1-b policy on the Q33 floor (floor key, the quest TAKEN,
the player's cell, the monsters and messages of the board) to drive the split's own functions.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import quest_alignment_split, quest_one_turn_kill, quest_room_sweep, summon_response
from hengbot.model import MonsterState, Position, QuestState
from hengbot.monrace_knowledge import _strip_jsonc
from hengbot.policy_constants import QUEST_STATUS_TAKEN, WAIT_KEY
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_plan_base import _navigator
from hengbot.quest_strategies import load_quest_strategies
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "quest32-one-turn-kill-1119"
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"
QUEEN, IT, GACHAPIN, BOKRUG, DAGON = 581, 393, 441, 489, 595
QUEST = 33


def quest_dir():
    return find_quest_definitions(Path(__file__).resolve())


def recorded(name):
    """(scratch, policy with the shipped strategies and this tree's quest data, the arrival board)."""
    scratch = tempfile.TemporaryDirectory()
    policy, _, steps = load(FIXTURES / name, Path(scratch.name))
    policy._quest_strategies = load_quest_strategies(STRATEGIES)
    policy._quest_knowledge = load_quest_knowledge(quest_dir())
    board = steps[0][1]()
    return scratch, policy, board


def readiness(policy, board):
    sink = []
    verdict = policy._evaluate_fixed_quest_readiness(
        board, QUEST, require_target_town=False, commit=False, telemetry_sink=sink)
    return verdict, sink[0], policy._fixed_quest_readiness.get("strategy_force", {})


def monster(policy, index, race, cell, *, asleep=False):
    knowledge = policy._monrace_knowledge[race]
    return MonsterState(index=index, position=Position(*cell), hp=knowledge.max_hp, max_hp=knowledge.max_hp,
                        distance=0, friendly=False, pet=False, asleep=asleep, name=knowledge.names[0],
                        race_id=race, can_summon=knowledge.can_summon)


def on_floor(policy, board, cell, monsters=(), messages=(), turn=1):
    """DECLARED CONSTRUCTED: the recorded board moved onto the Q33 floor."""
    quests = {**board.quests, QUEST: QuestState(id=QUEST, status=QUEST_STATUS_TAKEN, level=45, fixed=True)}
    player = replace(board.player, position=Position(*cell))
    return replace(board, floor_key=(0, 45, QUEST), quests=quests, player=player, grids={},
                   visible_monsters=list(monsters), detected_monsters=[], messages=list(messages), turn=turn)


def killed(policy, race, times):
    name = policy._monrace_knowledge[race].names[0]
    return f"{name}を葬り去った。" + (f" <x{times}>" if times > 1 else "")


class Quest33StrategyTest(unittest.TestCase):
    def test_the_shipped_strategy(self):
        profile = load_quest_strategies(STRATEGIES)[QUEST]
        self.assertTrue(profile.approved)
        self.assertIn("goodとevilの召喚持ちが相対すると", profile.approved_note)
        force = profile.required_force
        self.assertEqual(force["one_turn_kill"], {"race": QUEEN, "hit_points": 1500, "turns": 2,
                                                  "device_classes": [16]})
        self.assertTrue(force["non_urgent"])
        self.assertEqual(force["min_hp"], 1000)
        self.assertEqual(set(force["resists"]), {
            "see_invisible", "telepathy", "free_action", "confusion", "blindness", "chaos",
            "poison", "fear", "acid", "hold_exp"})
        split = profile.engagement_plan["room_sweep"]["alignment_split"]
        self.assertEqual(split["tracked_races"], [QUEEN, IT, GACHAPIN, BOKRUG, DAGON])
        self.assertEqual(split["facing_casts_to_abort"], summon_response.SUMMONS_TO_RECALL)
        self.assertEqual(profile.priority_targets[0], QUEEN)

    def test_a_malformed_split_is_not_loaded(self):
        data = json.loads(_strip_jsonc((STRATEGIES / "QUEST_33.jsonc").read_text(encoding="utf-8")))
        for broken in ({"tracked_races": [QUEEN], "facing_casts_to_abort": 0},
                       {"tracked_races": ["581"], "facing_casts_to_abort": 3}):
            data["engagement_plan"]["room_sweep"]["alignment_split"] = broken
            with tempfile.TemporaryDirectory() as temp:
                Path(temp, "QUEST_33.jsonc").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                with patch("sys.stderr"):
                    self.assertNotIn(QUEST, load_quest_strategies(Path(temp)))

    def test_a_later_phase_names_only_tracked_races(self):
        data = json.loads(_strip_jsonc((STRATEGIES / "QUEST_33.jsonc").read_text(encoding="utf-8")))
        data["engagement_plan"]["room_sweep"]["stands"][-1]["after_races_dead"] = [551]
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "QUEST_33.jsonc").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with patch("sys.stderr"):
                self.assertNotIn(QUEST, load_quest_strategies(Path(temp)))


class Quest33MapTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.info = load_quest_knowledge(quest_dir())[QUEST]

    def test_the_clones_are_placements(self):
        # "monster": {"cloneOf": id} places that race (fixed-map-generator.cpp); the six
        # {"random": true} cells place none known in advance.
        self.assertEqual(self.info.placed_monster_count, 60)
        placed = {cell for cell, race in self.info.battlefield.monster_placements if race == QUEEN}
        self.assertEqual(placed, {(20, 69), (20, 72), (22, 70)})

    def test_pits_and_lava_are_their_own_kinds(self):
        terrain = self.info.battlefield.terrain
        self.assertEqual((terrain[(17, 66)], terrain[(11, 10)], terrain[(16, 66)]), ("pit", "lava", "tree"))
        self.assertEqual(self.info.battlefield.exit, (13, 39))


class Quest33RecordedAcceptanceTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")

    def assert_refused_for_the_queen(self, name, melee, device, more=()):
        scratch, policy, board = recorded(name)
        with scratch:
            force = policy.approved_quest_strategy(QUEST).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            self.assertEqual((found["melee"], found["device"], found["tier"]), (melee, device, None))
            verdict, telemetry, strategy = readiness(policy, board)
            self.assertEqual((verdict, telemetry["reason"]), (False, "strategy-force"))
            self.assertEqual(strategy["failed"], [*more, "one_turn_kill"])
            # Not urgent: passed over in the fixed-quest order, and nothing is bought for it.
            self.assertTrue(quest_one_turn_kill.holds_back(policy, board, QUEST))
            resolved = policy._strategy_force_for_snapshot(board, policy.approved_quest_strategy(QUEST))
            self.assertEqual((resolved["heal_potions"], resolved["speed_potions"], resolved["required_scrolls"]),
                             (0, 0, {}))

    def test_n1a_warrior_meets_the_figure_and_lacks_resists(self):
        scratch, policy, board = recorded("n1a-531")
        with scratch:
            force = policy.approved_quest_strategy(QUEST).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            # Per action 578.3 < 750; per 10 game turns at +4 (energy 14) 809.7.
            self.assertEqual((found["melee"], found["per_10_game_turns"], found["tier"]),
                             (578.3, {"permanent": 809.7, "hasted": 1388.0}, "full"))
            self.assertFalse(quest_one_turn_kill.holds_back(policy, board, QUEST))
            verdict, telemetry, strategy = readiness(policy, board)
            # Short of the ten Light scrolls, resist_blind and telepathy.
            self.assertEqual((verdict, telemetry["reason"], strategy["failed"]),
                             (False, "strategy-force", ["required_scrolls.light", "resists"]))

    def test_n1a_with_four_blows_is_on_the_hasted_tier(self):
        scratch, policy, board = recorded("n1a-531")
        with scratch:
            weaker = replace(board, player=replace(board.player, main_hand_blows=4))
            force = policy.approved_quest_strategy(QUEST).required_force
            found = quest_one_turn_kill.details(policy, weaker, force)
            self.assertEqual((found["melee"], found["per_10_game_turns"], found["tier"]),
                             (330.5, {"permanent": 462.7, "hasted": 793.2}, "hasted"))
            # The force's own ten Speed doses carry the haste: no QUEST_32 haste row is merged.
            resolved = policy._strategy_force_for_snapshot(weaker, policy.approved_quest_strategy(QUEST))
            self.assertEqual((resolved["speed_potions"], resolved["speed_required_to_depart"]), (10, True))
            self.assertTrue(quest_one_turn_kill.haste_first(policy, weaker, force))

    def test_n1b_magic_eater_meets_it_and_is_accepted_at_full_hp(self):
        scratch, policy, board = recorded("n1b-411")
        with scratch:
            force = policy.approved_quest_strategy(QUEST).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            # +25 (energy 35): no dose at +10 or more, so the hasted speed is the permanent one.
            self.assertEqual((found["melee"], found["device"], found["per_10_game_turns"], found["tier"]),
                             (415.0, 280.0, {"permanent": 1452.4, "hasted": 1452.4}, "full"))
            verdict, telemetry, _ = readiness(policy, board)
            self.assertEqual((verdict, telemetry["reason"]), (False, "not-full-hp"))
            full = replace(board, player=replace(board.player, hp=board.player.max_hp))
            self.assertFalse(quest_one_turn_kill.holds_back(policy, full, QUEST))
            verdict, telemetry, strategy = readiness(policy, full)
            self.assertEqual((verdict, telemetry["reason"], strategy["failed"]), (True, "ready", []))
            # Its permanent speed (+25) stands for the ten Speed potions (the force's second row).
            resolved = policy._strategy_force_for_snapshot(full, policy.approved_quest_strategy(QUEST))
            self.assertEqual((resolved["speed_potions"], resolved["heal_potions"]), (0, 10))

    def test_n1c_magic_eater_is_refused(self):
        self.assert_refused_for_the_queen("n1c-217", 180.6, 140.4, ["resists"])
        scratch, policy, board = recorded("n1c-217")
        with scratch:
            found = quest_one_turn_kill.details(
                policy, board, policy.approved_quest_strategy(QUEST).required_force)
            self.assertEqual(found["per_10_game_turns"], {"permanent": 288.9, "hasted": 469.5})


class Quest33SplitTest(unittest.TestCase):
    """The split's own functions on DECLARED CONSTRUCTED Q33 floor boards."""

    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]

    def navigator(self, snapshot):
        return _navigator(self.policy, snapshot, QUEST)

    def contact(self, snapshot):
        navigator = self.navigator(snapshot)
        quest_alignment_split.observe(self.policy, snapshot, navigator, self.plan)
        return navigator, quest_alignment_split.contact_cells(self.policy, snapshot, navigator, self.plan)

    def test_the_start_is_quiet_and_east_of_the_doors_both_sides_act(self):
        _, contact = self.contact(on_floor(self.policy, self.board, (13, 39)))
        # The stair: every Queen beyond 30 (33, 36, 35).
        self.assertNotIn((13, 39), contact)
        # [14,42]: the Queen at [20,69] within 30 and the Its within 25.
        self.assertIn((14, 42), contact)
        # [12,42], the way north out of the doors, is 31 from that Queen.
        self.assertNotIn((12, 42), contact)

    def test_the_queen_stand_opens_once_the_its_and_dagons_are_dead(self):
        snapshot = on_floor(self.policy, self.board, (15, 38))
        _, contact = self.contact(snapshot)
        self.assertIn((14, 47), contact)
        dead = on_floor(self.policy, self.board, (15, 38), messages=(
            killed(self.policy, IT, 3), killed(self.policy, DAGON, 3)), turn=2)
        navigator, contact = self.contact(dead)
        self.assertEqual((navigator.split_kills[IT], navigator.split_kills[DAGON]), (3, 3))
        self.assertNotIn((14, 47), contact)
        # The Gachapins still sleep there (vision 10, 13 away), so the Queens come alone.
        self.assertIn((15, 57), contact)

    def test_a_board_is_read_once(self):
        snapshot = on_floor(self.policy, self.board, (15, 38), messages=(killed(self.policy, IT, 1),), turn=7)
        navigator = self.navigator(snapshot)
        for _ in range(2):
            quest_alignment_split.observe(self.policy, snapshot, navigator, self.plan)
        self.assertEqual(navigator.split_kills[IT], 1)

    def test_with_the_queens_dead_nothing_is_refused_and_the_last_phase_opens(self):
        snapshot = on_floor(self.policy, self.board, (14, 47), messages=(killed(self.policy, QUEEN, 3),))
        navigator, contact = self.contact(snapshot)
        self.assertEqual(contact, frozenset())
        later = self.plan["stands"][9]
        self.assertEqual(later["after_races_dead"], [QUEEN])
        self.assertFalse(quest_alignment_split.stop_waits(self.policy, snapshot, navigator, self.plan, later))

    def test_a_seen_summoner_stands_where_it_is_seen(self):
        # One It met in the corridor: the other two stay on their placements.
        it = monster(self.policy, 5, IT, (14, 45))
        snapshot = on_floor(self.policy, self.board, (15, 38), monsters=(it,))
        navigator = self.navigator(snapshot)
        rows = quest_alignment_split.summoners(self.policy, snapshot, navigator, self.plan)
        its = sorted(cell for mark, cell, _ in rows if mark == quest_alignment_split.EVIL
                     and cell in {(14, 45), (20, 20), (21, 22), (22, 20)})
        self.assertEqual(its, [(14, 45), (20, 20), (21, 22)])

    def test_every_stop_waiting_is_a_named_wait(self):
        # Only the Queen stand and a later-phase stand, the Dagons alive: both wait, no round spent.
        plan = {**self.plan, "stands": [self.plan["stands"][8], self.plan["stands"][9]], "last_targets": []}
        snapshot = on_floor(self.policy, self.board, (15, 38))
        navigator = self.navigator(snapshot)
        quest_alignment_split.observe(self.policy, snapshot, navigator, plan)
        key = quest_room_sweep._advance(self.policy, snapshot, navigator, plan)
        self.assertEqual((key, self.policy.last_reason), (WAIT_KEY, quest_room_sweep.SPLIT_BLOCKED_REASON))
        self.assertEqual(navigator.sweep_round, 0)

    def test_a_refused_stand_is_passed_for_the_next(self):
        # The Queen stand refused (Dagons alive), a stand of the first phase after it: walked to.
        plan = {**self.plan, "stands": [self.plan["stands"][8], self.plan["stands"][7]], "last_targets": []}
        snapshot = on_floor(self.policy, self.board, (11, 39))
        navigator = self.navigator(snapshot)
        key = quest_room_sweep._advance(self.policy, snapshot, navigator, plan)
        self.assertEqual((navigator.sweep_stage, self.policy.last_reason), (1, quest_room_sweep.WALK_REASON))
        self.assertIsNotNone(key)

    def test_a_walk_goes_round_the_contact_cells(self):
        snapshot = on_floor(self.policy, self.board, (13, 39))
        navigator = self.navigator(snapshot)
        path = quest_room_sweep._path(self.policy, navigator, self.plan, snapshot, {Position(2, 40)})
        contact = quest_alignment_split.contact_cells(self.policy, snapshot, navigator, self.plan)
        self.assertTrue(path)
        self.assertFalse({(cell.y, cell.x) for cell in path[1:]} & contact)


class Quest33FacingTest(unittest.TestCase):
    """A summon cast at a monster of the other side, and the abort it counts toward."""

    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]

    def cast(self, queen_cell, other_race, other_cell, turn):
        queen = monster(self.policy, 1, QUEEN, queen_cell)
        other = monster(self.policy, 2, other_race, other_cell)
        name = self.policy._monrace_knowledge[QUEEN].names[0]
        snapshot = on_floor(self.policy, self.board, (15, 38), monsters=(queen, other),
                            messages=(f"{name}が魔法でアリを召喚した。",), turn=turn)
        _navigator(self.policy, snapshot, QUEST)
        summon_response.observe(self.policy, snapshot)
        return snapshot

    def test_a_queen_in_line_of_an_evil_monster_counts(self):
        # The Queen [22,70] and a random EVIL monster [22,77] of the merged room (row 22 is open),
        # the player far out of the Queen's line: the cast was at the monster.
        self.cast((22, 70), IT, (22, 77), 1)
        self.assertEqual(summon_response.facing_casts(self.policy), 1)
        self.assertFalse(quest_alignment_split.abort_due(self.policy, self.plan))

    def test_a_wall_between_them_does_not(self):
        # [20,69] and [20,76]: the wall [20,74] stands between.
        self.cast((20, 69), IT, (20, 76), 1)
        self.assertEqual(summon_response.facing_casts(self.policy), 0)

    def test_the_third_one_gives_the_quest_up(self):
        for turn in (1, 2, 3):
            snapshot = self.cast((22, 70), IT, (22, 77), turn)
        self.assertTrue(quest_alignment_split.abort_due(self.policy, self.plan))
        with patch("hengbot.once_quest_recall.read_key", return_value="r_") as read:
            self.assertEqual(quest_alignment_split.abort_key(self.policy, snapshot, self.plan), "r_")
        self.assertTrue(read.call_args.kwargs["deliberate"])


if __name__ == "__main__":
    unittest.main()
