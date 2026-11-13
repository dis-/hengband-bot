"""n1-c life-166 (2026-11-08 09:35-09:36): stuck-prompt:wilderness:recall.

The Lv41 Magic-Eater was on the Zul trip (owner 2026-11-07) when the game
reloaded its save on an ambush tile of the wilderness.  The fresh process had
no trip record, so the wilderness survival rung ran: '<' was refused
(「敵がすぐ近くにいるときは広域マップに入れない！」, src/floor/wild.cpp
change_wild_mode: an awake hostile within MAX_PLAYER_SIGHT) and Word of
Recall was read (owner 2026-10-31 「帰還を読む」).  On the surface
spells-world.cpp recall_player asks which dungeon to recall *to*
(choose_dungeon); the read carried no letter because the established
destination, Angband 80, failed its depth gates (the trip's levitation ring
and the mining shovels had replaced the resist-chaos ring and Gungnir) and
no fallback landing passed either.  The executor cancelled the chooser and
stopped (D22) three times; the supervisor escalated.

Owner 2026-11-08 replaces the 10-31 rule: 「近くの敵を倒すか、敵から離れて
荒野の端へ歩き、全体地図へ出る。帰還は命が危ない時だけ、条件を満たす帰還先へ
読む。」  A refused '<' now walks away from the detected monsters toward the
nearest edge; an awake monster in view is left to the combat rules; Recall is
read only by the emergency ladder, carrying the letter of a landing that
passes the gates: the established destination, else the safe fallback, else
the Yeek cave (USER DECISION 2026-10-02 no-safe-destination place).

Fixture: tests/fixtures/wilderness-recall-1108.json.gz
(tests/extract_wilderness_recall_1108_fixture.py): the third session's first
board and its refusal board (turn 3079866) and the recorded decision rows.
Every decision goes through the public choose_key and the posted key through
the production executor port.

DECLARED CONSTRUCTED: the capture holds only the screen after the cancelling
ESC, so the chooser screen is built from choose_dungeon's layout
(dungeon-service.cpp RECALL rows at prt(row, 2 + i, 14)) for the board's
entered dungeons in DungeonId order; the skill knowledge is supplied before
each decision (the capture holds no ~f reply); the later and danger boards
are derived from the refusal board as each test declares.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import DUNGEON_YEEK_CAVE, parse_snapshot
from hengbot.policy_constants import UP_STAIRS_KEY
from hengbot import fallback_depth_floor
from tests.support import recorded as executor_pins
from tests.support.fallback_floor import floor_lifted
from tests.test_town_decision_speed_caches import build_policy

FIXTURE = Path(__file__).with_name("fixtures") / "wilderness-recall-1108.json.gz"
READ_PROMPT = "どの巻物を読みますか? "
CHOOSER = "どのダンジョンに帰還しますか:"
DUNGEON_ANGBAND = 1
ORC_CAVE = 3


def decide(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })
    return str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))


def chooser_screen(board):
    screen = executor_pins.prompt_screen(CHOOSER)
    depths = board["progress"]["dungeon_recall_depths"]
    for index, dungeon_id in enumerate(board["progress"]["entered_dungeon_ids"]):
        row = f"      {chr(ord('a') + index)})  dungeon {dungeon_id:<4} : 最大 {depths[str(dungeon_id)]} 階"
        screen["lines"][2 + index] = " " * 14 + row
    return screen


class WildernessRecallRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def boards(self):
        return [copy.deepcopy(board) for board in self.case["boards"]]

    def policy(self, first):
        policy = build_policy()
        policy.prime(parse_snapshot(first, policy._monrace_knowledge))
        self.assertEqual(decide(policy, first), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "wilderness:enter-global")
        return policy

    @staticmethod
    def later(raw, turns, **player):
        board = copy.deepcopy(raw)
        board["messages"] = []
        board["turn"] += turns
        board["player"].update(player)
        return board

    @staticmethod
    def in_danger(raw):
        # DECLARED CONSTRUCTED: the ogre the board detects stands beside the
        # player in view, HP 60/783, and the pack holds no potion and no
        # teleport or phase scroll (Recall, the rings, the gear and bolts stay).
        board = copy.deepcopy(raw)
        board["messages"] = []
        board["player"]["hp"] = 60
        ogre = dict(board["detected_monsters"][0])
        ogre.update(x=board["player"]["x"] + 1, y=board["player"]["y"], esp=False)
        board["visible_monsters"] = [ogre]
        board["inventory"] = [item for item in board["inventory"]
                              if item["slot"] in ("g", "l", "m", "n", "o")]
        return board

    def post(self, policy, raw, key, screens):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 1, messages=[])
        game.screens = [*screens, executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        result = port(key, decision={"reason": policy.last_reason,
                                     "sequence": policy._decision_sequence})
        return result, port.last_result, game.accepted

    def test_recorded_rows(self):
        rows = [(row["reason"], row["key"]) for row in self.case["decisions"]]
        self.assertEqual(rows, [("wilderness:enter-global", "<"), ("wilderness:recall", "rg")] * 3)
        first, refused = self.boards()
        self.assertEqual(first["floor"]["dungeon_id"], 0)
        self.assertTrue(refused["messages"][-1].startswith("敵がすぐ近くにいるときは広域マップに入れない"))
        self.assertEqual(refused["progress"]["recall_dungeon_id"], 2)
        self.assertEqual(refused["progress"]["dungeon_recall_depths"]["1"], 80)

    def test_angband_and_every_fallback_fail_their_gates(self):
        _first, refused = self.boards()
        policy = build_policy()
        board = parse_snapshot(refused, policy._monrace_knowledge)
        policy.prime(board)
        self.assertEqual(policy._town_recall_destination(board), (None, DUNGEON_ANGBAND))
        self.assertFalse(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        self.assertIsNone(policy._pick_alternate_dungeon(board, max_entry_depth=79))
        self.assertTrue(policy._recall_destination_safe(board, DUNGEON_YEEK_CAVE))

    def test_refused_global_map_walks_away_toward_the_edge_without_recall(self):
        first, refused = self.boards()
        policy = self.policy(first)
        key = decide(policy, refused)
        # Was "rg" (wilderness:recall): owner 2026-11-08 「敵を倒すか離れてから出る」.
        self.assertEqual((key, policy.last_reason), ("8", "wilderness:edge-walk"))
        # The ogre and the panther the board detects are south-east, the
        # apprentice north-west: north and west each walk toward one, and the
        # top edge (y 10 of 66) is the nearer of the two.
        board = parse_snapshot(refused, policy._monrace_knowledge)
        here = board.player.position
        self.assertEqual(sorted((monster.position.y > here.y, monster.position.x > here.x)
                                for monster in board.detected_monsters),
                         [(False, False), (True, True), (True, True)])
        # The refusal is remembered on the next board (no message any more).
        step = self.later(refused, 7, y=refused["player"]["y"] - 1)
        self.assertEqual((decide(policy, step), policy.last_reason), ("8", "wilderness:edge-walk"))
        # DECLARED CONSTRUCTED: the border step put the player on the next
        # tile's opposite edge (movement-execution.cpp): '<' again.
        crossed = self.later(refused, 14, y=refused["floor"]["height"] - 2)
        self.assertEqual((decide(policy, crossed), policy.last_reason),
                         (UP_STAIRS_KEY, "wilderness:enter-global"))

    def test_an_awake_monster_in_view_is_fought_by_the_combat_rules(self):
        # DECLARED CONSTRUCTED: the ogre three cells east in view, full HP,
        # the recorded pack.  The wilderness rung leaves it to the ordinary
        # rules, whose bolts shoot it (was wilderness:flee; a None returned
        # from the branch itself would end in policy:none-wait).
        first, refused = self.boards()
        policy = self.policy(first)
        board = self.in_danger(refused)
        board["player"]["hp"] = board["player"]["max_hp"]
        board["inventory"] = copy.deepcopy(refused["inventory"])
        board["visible_monsters"][0]["x"] = board["player"]["x"] + 3
        key = decide(policy, board)
        self.assertEqual((key, policy.last_reason), ("fo6", "ranged:fire"))

    def test_survival_recall_answers_the_chooser_with_a_safe_landing(self):
        first, refused = self.boards()
        policy = self.policy(first)
        board = self.in_danger(refused)
        key = decide(policy, board)
        self.assertEqual(policy.last_reason, "emergency:recall")
        snapshot = parse_snapshot(board, policy._monrace_knowledge)
        recall = next(item for item in snapshot.inventory if item.is_recall_scroll)
        letter = chr(ord("a") + snapshot.entered_dungeon_ids.index(DUNGEON_YEEK_CAVE))
        # The recorded read was "rg": no letter, the chooser cancelled.
        self.assertEqual(key, "r" + recall.slot + letter)
        self.assertNotEqual(letter, "a")  # never Angband 80, whose gates fail
        result, last, accepted = self.post(
            policy, board, key,
            [executor_pins.prompt_screen(READ_PROMPT), chooser_screen(board)])
        self.assertEqual(result, SendResult.SENT, last.reason)
        self.assertEqual(last.outcome, "completed")
        self.assertEqual(accepted, ["r", recall.slot, letter])

    def resisted_boards(self):
        # DECLARED CONSTRUCTED: fire and confusion resistance worn (as with
        # Gungnir), so the Orc cave's recall floor 23 passes its gates while
        # Angband 80 still lacks chaos.
        first, refused = self.boards()
        for board in (first, refused):
            sources = board["player"]["ability_sources"]
            for name in ("resist_fire", "resist_conf"):
                sources[name]["equipment"] = True
        return first, refused

    # DECLARED WALL (tests/support/fallback_floor.py): Angband 80 reached, the floor 60 refuses
    # the Orc cave 23 (test_the_floor_leaves_the_yeek_cave_place); this subject predates it.
    @floor_lifted()
    def test_a_safe_fallback_landing_answers_before_the_yeek_cave(self):
        # The departure read point's safe fallback picks the Orc cave ahead of the Yeek cave.
        first, refused = self.resisted_boards()
        policy = self.policy(first)
        key = decide(policy, self.in_danger(refused))
        self.assertEqual(policy.last_reason, "emergency:recall")
        board = parse_snapshot(refused, policy._monrace_knowledge)
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot + chr(ord("a") + board.entered_dungeon_ids.index(ORC_CAVE)))
        self.assertEqual(policy._target_dungeon_id, ORC_CAVE)
        self.assertEqual(policy._alternate_dungeon_reason, "safe_fallback")
    def test_the_floor_leaves_the_yeek_cave_place(self):
        """Owner 2026-11-13 「フォールバックは最新到達-20Fまでにする。」: Angband 80 is the deepest
        reached, so the Orc cave 23 is no fallback (floor 60) and the read carries the next
        rule's letter, the no-safe-destination place (USER DECISION 2026-10-02): the Yeek cave."""
        first, refused = self.resisted_boards()
        policy = self.policy(first)
        key = decide(policy, self.in_danger(refused))
        self.assertEqual(policy.last_reason, "emergency:recall")
        board = parse_snapshot(refused, policy._monrace_knowledge)
        self.assertEqual(fallback_depth_floor.floor(policy, board), 60)
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot + chr(
            ord("a") + board.entered_dungeon_ids.index(DUNGEON_YEEK_CAVE)))
        self.assertIsNone(policy._alternate_dungeon)


if __name__ == "__main__":
    unittest.main()
