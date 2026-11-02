"""The 2026-11-02 23:18 viewing-bot stops of n1-a life-466 (hourly-2300-1102).

Each class pins one root on its recorded board; facts the capture keeps
outside the board are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_2300_1102_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _cell_loop_guard_applies, _send_new_decision_key,
)
from tests import test_input_executor as executor_pins
from test_hourly_0700_1102_recorded import RecordedTownPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-2300-1102.json.gz"


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class VanishedIdentificationCandidateTest(RecordedTownPolicy):
    """n1-a life-466 23:18:46 town:blocked:departure-unsatisfiable.

    At 5F (decision 5107) the warrior picked up an unknown robe; back in town
    (5129) the town-item owner made it the identification candidate and
    requested a normal Identify source.  Descending again (5137) the game
    destroyed the robe after its {壊れている} pseudo-feeling.  The request
    stayed latched with no item behind it: the Identify scroll bought at 6512
    had nothing to read on, and departure failed home_candidate_resolved and
    identification_need_clear for good, each latch's release waiting for the
    other.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["identify"]

    def test_vanished_candidate_releases_the_identify_request(self):
        case = self.case
        policy = self.primed(case["stop"], case["home"]["knowledge"]["items"], case["skill"])
        board = self.board(policy, case["stop"])
        robe = ("ローブ [2]", 36, 2)
        self.assertFalse(any(policy._item_signature(item) == robe
                             for item in (*board.inventory, *board.equipment,
                                          *policy._home_knowledge_items)))
        # DECLARED RECONSTRUCTED: the latches the life's decisions record
        # from 5129 to the stop (identification_need normal,
        # home_candidate_waiting true) with the robe as candidate.
        policy._identification_need = "normal"
        policy._identification_candidate = robe
        policy._home_candidate_waiting = True

        key = policy.choose_key(board)
        # Recorded: '5' town:blocked:departure-unsatisfiable.  Departure is
        # ready: the pre-recall character dump runs.
        self.assertEqual((key, policy.last_reason), ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertIsNone(policy._identification_need)
        self.assertFalse(policy._home_candidate_waiting)
        self.assertEqual(policy._departure_block_state(board)["failed"], [])


class QuestDungeonTargetAcrossBoardsTest(RecordedTownPolicy, executor_pins.ProductionHarness):
    """n1-a life-466 23:18:56 posting-contract:recall-already-active.

    The restarted session read Word of Recall to the Yeek cave (decision 12,
    ``rgb``: quest 14, a taken kill quest there, set the target inside
    _fixed_quest_key).  On the next board (13) observation had put the
    conquest target, the Labyrinth, back before that rung ran, so the active
    recall was cancelled as town:cancel-wrong-recall-destination; the same
    read and cancel repeated (17, 18) until the posting contract stopped it.
    """

    @classmethod
    def setUpClass(cls):
        cases = _cases()
        cls.case, cls.home = cases["recall"], cases["identify"]["home"]

    def test_recall_board_keeps_the_quest_dungeon_read(self):
        case = self.case
        policy = self.primed(case["read"], self.home["knowledge"]["items"], case["skill"])
        board = self.board(policy, case["next"])
        self.assertTrue(board.player.recalling)
        self.assertEqual(list(board.entered_dungeon_ids), [1, 2, 4, 14, 18])
        # DECLARED RECONSTRUCTED: the recorded read ``rgb`` chose letter b,
        # the Yeek cave (dungeon 2).
        policy._pending_recall_dungeon_id = 2
        key = policy.choose_key(board)
        # Recorded: 'rg' town:cancel-wrong-recall-destination.
        self.assertEqual((key, policy.last_reason), ("1", "town:wait-recall-step-off"))
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason),
                         (2, "quest_dungeon"))

        raw = case["next"]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the game's reply to the step.
        moved = copy.deepcopy(raw)
        moved["turn"] += 10
        moved["player"]["y"] += 1
        moved["player"]["x"] -= 1
        game.screens = [executor_pins.command_screen(moved["turn"])]
        game.states = [moved]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": 13, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, ["1"])


class ConfusedWaitLoopGuardTest(RecordedTownPolicy):
    """n1-b life-297 22:49:45 loop-detected at 15F.

    A demon's claw confused the character (decision 544) after its last Cure
    Critical Wounds potion; with no hostile in view it rode the confusion out
    with ``5`` confused:wait.  The game counts the timer down by one each
    player turn (magic-effects-timeout-reducer.cpp), but the CLI cell guard
    counted every wait and stopped the bot at decision 713.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["confused"]

    def test_recorded_confused_wait_does_not_feed_the_cell_guard(self):
        case = self.case
        policy = self.primed(case["stop"], case["home"]["knowledge"]["items"], case["skill"])
        board = self.board(policy, case["stop"])
        self.assertTrue(board.player.confused)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5", "confused:wait"))
        self.assertFalse(_cell_loop_guard_applies(board, policy.last_reason,
                                                  board.player.position))


class FundraisingLootRouteThroughHostilesTest(RecordedTownPolicy):
    """n1-c life-111 23:15:44 loop-detected at Yeek cave 1F.

    The mining run walked to a floor item at (41,28): ``4`` from (49,37),
    where nothing was in view, and ``6`` back from (49,36), where a sleeping
    giant white louse at (43,30) came into view, until the loop detector
    stopped the bot (decisions 5273-5301).  The grid index drops a visible
    monster's cell from the walkable floor, and the fundraising loot route
    did not keep it the way the ordinary loot route does.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["loot"]

    def test_loot_route_is_the_same_with_the_louse_in_view(self):
        case = self.case
        # DECLARED CONSTRUCTED: an empty Home list (dungeon decision; the
        # capture's last Home row is in an older ring generation).
        policy = self.primed(case["west"], [], case["skill"])
        # DECLARED RECONSTRUCTED: the mining run the decisions record
        # (fundraising.mode mine).
        policy._fundraising_mode = "mine"
        west = self.board(policy, case["west"])
        key = policy.choose_key(west)
        self.assertEqual((key, policy.last_reason), ("4", "fundraise:seek-loot"))
        policy.confirm_key_posted(key)

        east = self.board(policy, case["east"])
        self.assertEqual([(m.position.y, m.position.x, m.asleep) for m in east.visible_monsters],
                         [(43, 30, True)])
        key = policy.choose_key(east)
        # Recorded: '6' fundraise:seek-loot (away from the loot).
        self.assertEqual((key, policy.last_reason), ("7", "fundraise:seek-loot"))
        self.assertEqual((policy._loot_target.y, policy._loot_target.x), (41, 28))


class UnaimedImmobileSummonerTest(RecordedTownPolicy):
    """n1-c life-110 22:44:12 loop-detected at Orc cave 22F.

    A クイルスルグ (race 342, NEVER_MOVE, INVISIBLE, S_MONSTER) was in view
    at (37,141) beside two other hostiles (1036087-1036105), so the
    immobile-summoner owner kept its line-of-fire zone.  With nothing else
    in view the safe ranged kill walked ``7`` to the shooting cell (42,141),
    where the summoner was not in view (nothing to aim at), so the zone owner
    stepped ``3`` out of the zone, and back, until the loop detector stopped
    the bot (decisions 39-51); the same loop stopped it again and the life
    retired.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["summoner"]

    def test_unaimed_summoner_is_not_walked_back_to(self):
        case = self.case
        boards = case["boards"]
        # DECLARED CONSTRUCTED: an empty Home list (dungeon decisions).
        policy = self.primed(boards[0], [], case["skill"])
        for raw in boards[:-1]:
            board = self.board(policy, raw)
            key = policy.choose_key(board)
            policy.confirm_key_posted(key)
        # On the shooting cell with the summoner out of view: step out.
        self.assertEqual((board.player.position.y, board.player.position.x), (42, 141))
        self.assertEqual((key, policy.last_reason), ("3", "explore:avoid-immobile-summoner"))
        board = self.board(policy, boards[-1])
        key = policy.choose_key(board)
        # Recorded: '7' immobile-threat:approach-to-shoot (back to (42,141)).
        self.assertNotEqual(policy.last_reason, "immobile-threat:approach-to-shoot")
        self.assertEqual((key, policy.last_reason), ("6", "seek-loot"))


if __name__ == "__main__":
    unittest.main()
