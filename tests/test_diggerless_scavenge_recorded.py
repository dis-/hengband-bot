"""D54 (Q2): n1-a life-454: no digger can be had, so scavenge 1F with the detection.

Recorded stop (2026-11-01 01:01:42, turn 86884, build bot-f9c921d32), then
town:blocked:owner-retired-burst three times and a new character: right after
Q1 the warrior (Lv8, 189 gold) held one Word of Recall of the nine it needed,
eight Treasure Detection scrolls and no digger; the General store sold none
it could pay for (one 1,436-gold shovel at 80151, none later).  Fundraising
stayed in ``prepare`` waiting for the mining kit, every shop visit was
observe-and-leave and the town owners retired.

Owner 2026-10-23 (c4-a life-016, the same shape): when the recall cannot be
bought and mining is impossible, sell the surplus, then use the carried
Treasure Detection to walk 1F and come back by the stairs within 10,000 game
turns.  The code allowed scavenging only without detection
(_detectionless_scavenge_allowed) and sent a run without a digger but with
known veins back to town; policy_fundraising._diggerless_scavenge_allowed
now admits the run and keeps it on the floor.

The town test attaches the recorded visit to tests/test_unid_deposit_recorded
.py's harness (DECLARED RECONSTRUCTED boundary; the empty Home page is
constructed from the visit's empty ~9 Home answer).  The floor test uses the
recorded Yeek cave 1F board of n1-a life-453 (tests/fixtures/idstaff-
stockout-run-20261101.json.gz) with its two diggers removed (DECLARED
CONSTRUCTED) and the scavenge run's town decision (DECLARED RECONSTRUCTED).
Every key comes from the public chooser and goes through the production
executor; the replies are constructed.  Fixture:
tests/extract_diggerless_scavenge_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import choose_past_junk_key

import copy
from pathlib import Path

from hengbot.model import STORE_GENERAL, STORE_HOME, parse_snapshot
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS
import tests.test_idstaff_stockout_run_recorded as stockout
import tests.test_unid_deposit_recorded as recorded
from hengbot.cli import _ExecutorInputPort, SendResult, _transport_key
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen


FIXTURE = Path(__file__).with_name("fixtures") / "diggerless-scavenge-20261101.json.gz"


class DiggerlessScavengeRecordedTest(recorded.UnidentifiedDepositRecordedTest):
    fixture = FIXTURE

    def setUp(self):
        super().setUp()
        # DECLARED CONSTRUCTED: the visit's ~9 Home answer is empty (a new
        # character's Home); its page has the shape of the recorded pages.
        page = copy.deepcopy(self.pages[STORE_GENERAL])
        page.update(store_type=STORE_HOME, items=[], stock_num=0, page_top=0)
        self.pages[STORE_HOME] = page

    def test_recorded_stop(self):
        decision = self.case["decision"]
        self.assertEqual((decision["turn"], decision["reason"]),
                         (86884, "town:blocked:departure-unsatisfiable"))
        self.assertIn("recall_departure_ready", decision["departure_block"]["failed"])
        self.assertEqual(self.case["home_answer"]["knowledge"]["items"], [])
        policy, raw = self.boundary()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertFalse(policy._has_withdrawable_digging_tool(board))
        self.assertEqual(policy._count_treasure_detection_scrolls(board), 8)
        general = self.pages[STORE_GENERAL]["items"]
        self.assertFalse(any(it["tval"] == 20 and it["price"] <= board.player.gold
                             for it in general))

    def test_town_chooses_the_scavenge_run(self):
        policy, raw = self.boundary()

        def departs(reason, key):
            return reason == "town:travel-entrance" or (
                key.startswith("\x1b`n") and len(key) > 3 and key[3] in TOWN_TRAVEL_STORE_SYMBOLS
                and TOWN_TRAVEL_STORE_SYMBOLS.index(key[3]) not in self.pages)

        raw, reasons = self.drive(policy, raw, limit=20, done=departs)
        self.assertEqual(reasons[-1], "town:travel-entrance", reasons)
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertTrue(policy._scavenge_without_digger)

    # The inherited Identify-staff scenarios belong to the life-427 fixture.
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None


class DiggerlessScavengeFloorTest(stockout.IdstaffStockoutRunRecordedTest):
    """The scavenge run on Yeek cave 1F reads its carried detection and stays."""

    def test_scavenge_run_reads_the_carried_detection(self):
        policy, raw = self.dungeon_policy()
        # DECLARED CONSTRUCTED: the life-453 board without its two diggers and
        # with life-454's 189 gold, and the scavenge run's town decision (no
        # digger could be had).
        raw["inventory"] = [it for it in raw["inventory"] if it["tval"] != 20]
        raw["player"]["gold"] = 189
        recorded.UnidentifiedDepositRecordedTest.relabel(raw["inventory"])
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy._identify_staff_mining_plan = False
        policy._fundraising_mode = "scavenge"
        policy._scavenge_without_digger = True
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        self.assertEqual(policy._count_treasure_detection_scrolls(board), 1)
        key = str(choose_past_junk_key(policy, board))
        self.assertEqual(policy.last_reason, "fundraise:detect-treasure", key)
        self.assertFalse(policy._returning_to_town)
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.post_read(policy, raw, key)

    def post_read(self, policy, raw, key):
        """DECLARED CONSTRUCTED: the read prompt, then the board ten turns later."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        # cmd-item.cpp do_cmd_read_scroll's item prompt.
        game.screens = [prompt_screen("(持ち物:a-z, ESCで中断) どの巻物を読みますか?"),
                        command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw), following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))

    test_recorded_stop = None
    test_stop_board_installs_the_stockout_run_again = None
    test_stockout_run_mines_instead_of_returning_on_the_gold_target = None


if __name__ == "__main__":
    import unittest
    unittest.main()
