"""The Telmora arena through the public chooser and the production executor (owner 2026-11-05).

Owner: 「ダンジョンに出発する前に闘技場に挑むかの判定を行う。街の移動資金が往復分あり、次の対戦
相手への勝率が90%以上なら挑戦する。勝利して報酬を得た場合は街の処理を最初からやり直す。」

Recorded: tests/fixtures/arena-live-1105.json.gz, a live capture on the Linux test environment
of a copy of a test character (Lv45 warrior): the building's menu and poster, the entry, the
first fight won, the reward, the gate, the second entry, the closed gate, the loss (a debug
command's damage in the arena: the character's real HP 0 landing) and 「敗者に用はない。」.

DECLARED: ``_skill_exp_request_key`` is off and Home is known (the ~f probe and the scan have
their own tests; the arena's keys read neither).  CONSTRUCTED where a test says so: a changed HP or gold or town on a
recorded board, and the sheet's arena line in a temporary file.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import arena, arena_odds, me_ranged_first
from hengbot.character_sheet import ArenaStanding, arena_standing
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import ARENA_FLOOR_KEY, TVAL_WAND, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from tests import test_input_executor as executor_pins

FIXTURE = Path(__file__).with_name("fixtures") / "arena-live-1105.json.gz"
KNOWLEDGE = load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))
SHEET = "  [変愚蛮怒 キャラクタ情報]\n\n 闘技場:  {}勝\n\n"


class ArenaRecorded(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def board(self, label, **player):
        raw = copy.deepcopy(self.cases[label]["board"])
        raw["player"].update(player)
        return raw

    def policy(self):
        policy = ConservativePolicy(monrace_knowledge=KNOWLEDGE)
        policy._skill_exp_request_key = lambda _snapshot: None
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        return policy

    def snap(self, policy, raw):
        return parse_snapshot(raw, policy._monrace_knowledge)

    def key(self, policy, raw, prefix="arena:"):
        """The chooser's key once the visit's bookkeeping keys are out of the way."""
        snapshot = self.snap(policy, raw)
        for _ in range(6):
            key = policy.choose_key(snapshot)
            if (policy.last_reason or "").startswith(prefix):
                return key
        self.fail(f"no {prefix} key, last {policy.last_reason} {key!r}")

    def sheet(self, policy, wins):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "sheet.txt"
        path.write_text(SHEET.format(wins), encoding="cp932")
        policy._character_dump_path = path
        policy._char_dump_done_this_visit = True

    def post(self, policy, raw, key, screens):
        game = executor_pins.FaithfulHookGame()
        game.capacity = 64
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = screens
        game.states = [copy.deepcopy(raw) for _ in screens]
        game.states[-1]["turn"] = raw["turn"] + 1
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": 7, "reason": policy.last_reason},
            snapshot=self.snap(policy, raw), posting_contract=PostingContract(),
        )
        self.assertTrue(sent)
        return game

    def menu_screen(self):
        screen = copy.deepcopy(self.cases["13-poster2"]["screen"])
        screen["lines"][0] = " " * len(screen["lines"][0])
        return screen

    # --- the floor

    def test_the_floor_is_its_own_floor_out_of_town(self):
        raw = self.cases["03-enter"]["board"]
        self.assertTrue(raw["floor"]["in_town"] and raw["floor"]["inside_arena"])  # the emitter's
        snapshot = self.snap(self.policy(), copy.deepcopy(raw))
        self.assertEqual(snapshot.floor_key, ARENA_FLOOR_KEY)
        self.assertFalse(snapshot.in_town)
        self.assertTrue(snapshot.inside_arena)

    def test_walks_up_then_strikes(self):
        policy = self.policy()
        self.assertEqual(self.key(policy, self.board("03-enter")), "2")
        self.assertEqual(policy.last_reason, arena.WALK_REASON)
        self.assertEqual(self.key(policy, self.board("09-move")), "2")
        self.assertEqual(policy.last_reason, arena.MELEE_REASON)

    def test_low_hp_keeps_fighting_and_reads_nothing(self):
        # CONSTRUCTED: HP 40 on the recorded board; the pack holds Teleport, Recall and potions,
        # all of which the game refused here (recorded 04-read-refused).
        self.assertIn("アリーナが魔法を吸収した！", self.cases["04-read-refused"]["board"]["messages"])
        policy = self.policy()
        self.assertEqual(self.key(policy, self.board("09-move", hp=40)), "2")
        self.assertEqual(policy.last_reason, arena.MELEE_REASON)

    def test_a_low_hp_walk_still_walks_up(self):
        # CONSTRUCTED: HP 40.  The low-HP walking gate would answer with a scroll.
        policy = self.policy()
        self.assertEqual(self.key(policy, self.board("03-enter", hp=40)), "2")
        self.assertEqual(policy.last_reason, arena.WALK_REASON)

    def test_a_hit_on_a_hold_keeps_the_hold(self):
        # CONSTRUCTED: an unseen monster with the gate shut, HP falling between two boards.
        policy = self.policy()
        arena.state(policy).gate_attempts = arena.GATE_ATTEMPTS
        for hp in (1137, 900):
            raw = self.board("16-gate-closed", hp=hp)
            raw["visible_monsters"] = []
            raw["messages"] = []
            key = self.key(policy, raw)
        self.assertTrue(policy._took_damage)
        self.assertEqual((key, policy.last_reason), (arena.WAIT_KEY, arena.HOLD_REASON))

    def test_a_carried_wand_and_a_throw_are_not_offered(self):
        policy = self.policy()
        snapshot = self.snap(policy, self.board("09-move"))
        # CONSTRUCTED: the recorded Stone to Mud wand as an attack wand.
        wand = next(item for item in snapshot.inventory if item.tval == TVAL_WAND and item.charges > 0)
        armed = replace(snapshot, inventory=[
            replace(item, sval=min(me_ranged_first.ATTACK_WAND_SVALS)) if item is wand else item
            for item in snapshot.inventory])
        self.assertIsNone(me_ranged_first._attack_wand(policy, armed, armed.visible_monsters[0], "2"))
        self.assertIsNotNone(me_ranged_first._attack_wand(
            policy, replace(armed, inside_arena=False), armed.visible_monsters[0], "2"))
        self.assertIsNone(me_ranged_first._throwable_torch(policy, snapshot))
        self.assertEqual(policy._ranged_projectile(replace(snapshot, inventory=[
            item for item in snapshot.inventory if item.tval not in (16, 17, 18)])), None)

    def test_reward_then_gate_then_the_menu_is_closed(self):
        policy = self.policy()
        self.assertEqual(self.key(policy, self.board("10-move")), "2")
        self.assertEqual(policy.last_reason, arena.REWARD_REASON)
        raw = self.board("11-reward-step")
        key = self.key(policy, raw)
        self.assertEqual((key, policy.last_reason), ("8", arena.GATE_REASON))
        game = self.post(policy, raw, key, [self.menu_screen(), executor_pins.command_screen(raw["turn"] + 1)])
        self.assertEqual(game.accepted, ["8", "\x1b"])

    def test_the_way_back_starts_the_town_over(self):
        policy = self.policy()
        policy._char_dump_done_this_visit = True
        self.key(policy, self.board("11-reward-step"))
        self.assertFalse(policy._char_dump_done_this_visit)  # the next departure writes a sheet
        policy._town_store_attempted[3] = 1
        snapshot = self.snap(policy, self.board("12-travel-to-gate"))
        self.assertEqual(snapshot.floor_key, (0, 0, 0))
        policy.choose_key(snapshot)
        self.assertEqual(policy._town_store_attempted, {})  # TownVisit.begin ran

    def test_a_shut_gate_does_not_walk_forever(self):
        policy = self.policy()
        raw = self.board("16-gate-closed")
        raw["visible_monsters"] = []  # CONSTRUCTED: an unseen monster with the gate shut
        record = arena.state(policy)
        record.gate_attempts = arena.GATE_ATTEMPTS
        self.assertEqual(self.key(policy, raw), arena.WAIT_KEY)
        self.assertEqual(policy.last_reason, arena.HOLD_REASON)

    # --- the building

    def trip_policy(self, expected):
        policy = self.policy()
        record = arena.state(policy)
        record.holding, record.expected, record.origin = True, expected, 0
        return policy, record

    def beside_the_building(self):
        raw = self.board("21-after-loss-off", hp=1137)  # CONSTRUCTED: full HP, not the loser
        raw["messages"] = []
        return raw

    def test_poster_then_enter_on_the_real_menu(self):
        policy, record = self.trip_policy(arena.OPPONENTS[1])
        raw = self.beside_the_building()
        key = self.key(policy, raw, "town:arena")
        self.assertEqual((key, policy.last_reason), ("4p\x1b", arena.POSTER_REASON))
        posted = self.cases["13-poster2"]["screen"]
        self.assertIs(classify_screen(posted).kind, ScreenKind.BUILDING)
        game = self.post(policy, raw, key, [self.menu_screen(), posted,
                                            executor_pins.command_screen(raw["turn"] + 1)])
        self.assertEqual(game.accepted, ["4", "p", "\x1b"])

        # The recorded board after the poster: on the building's cell, its text in the messages.
        board = self.board("13-poster2")
        board["input_context"] = {"kind": "command", "prompt": ""}
        key = self.key(policy, board, "town:arena")
        self.assertTrue(record.poster_checked)
        self.assertEqual(policy.last_reason, arena.APPROACH_REASON)

        raw = self.beside_the_building()
        key = self.key(policy, raw, "town:arena")
        self.assertEqual((key, policy.last_reason), ("4e", arena.ENTER_REASON))
        game = self.post(policy, raw, key, [self.menu_screen(), executor_pins.command_screen(raw["turn"] + 1)])
        self.assertEqual(game.accepted, ["4", "e"])

    def test_a_poster_that_disagrees_closes_the_errand(self):
        policy, record = self.trip_policy(arena.OPPONENTS[0])  # the poster names the second
        record.poster_posted = True
        board = self.board("13-poster2")
        self.assertIsNone(arena._entry_key(policy, self.snap(policy, board), record))
        self.assertTrue(record.closed)

    # --- the loss

    def test_a_loss_closes_the_arena_and_the_town_rests(self):
        policy = self.policy()
        raw = self.board("20-killed")
        self.assertEqual(raw["player"]["hp"], 0)
        self.assertEqual(self.key(policy, raw, "town:recover"), "R&\r")
        self.assertTrue(arena.over_for_good(policy))
        self.sheet(policy, 1)
        verdict = arena.judge(policy, self.snap(policy, self.board("22-loser-step")),
                              arena.state(policy), arena.TELMORA_TOWN_ID)
        self.assertEqual((verdict["go"], verdict["why"]), (False, "defeated"))

    def test_the_game_refusal_alone_is_read(self):
        policy = self.policy()
        snapshot = self.snap(policy, self.board("22-loser-step"))
        self.assertIn("「敗者に用はない。」", snapshot.messages)
        arena.observe(policy, snapshot)
        self.assertTrue(arena.over_for_good(policy))

    # --- the judgement

    def judge(self, wins, *, town=arena.TELMORA_TOWN_ID, gold=None):
        policy = self.policy()
        self.sheet(policy, wins)
        raw = self.board("13-poster2")
        raw["messages"] = []
        if gold is not None:
            raw["player"]["gold"] = gold
        snapshot = self.snap(policy, raw)
        return arena.judge(policy, snapshot, arena.state(policy), town)

    def test_the_next_opponent_from_the_sheet_decides(self):
        verdict = self.judge(1)
        self.assertEqual(verdict["race_id"], 1060)  # recorded poster: 『森トロル』 after one win
        self.assertEqual(verdict["fare"], 0)
        self.assertTrue(verdict["go"])
        self.assertGreaterEqual(verdict["chance"], arena_odds.WIN_CHANCE_LINE)

    def test_a_hopeless_opponent_is_not_fought(self):
        verdict = self.judge(40)
        self.assertFalse(verdict["go"])
        self.assertEqual(verdict["race_id"], 847)

    def test_the_round_trip_needs_two_fares_from_another_town(self):
        # CONSTRUCTED: the gold and the town on the recorded board.
        self.assertEqual(self.judge(1, town=0, gold=999)["why"], "fare")
        verdict = self.judge(1, town=0, gold=1000)
        self.assertEqual((verdict["fare"], verdict["go"]), (1000, True))
        self.assertEqual(self.judge(1, gold=0)["fare"], 0)  # in Telmora nothing to pay

    def test_finished_and_unknown_do_not_fight(self):
        self.assertEqual(self.judge(41)["why"], "finished")
        policy = self.policy()  # no sheet this visit
        snapshot = self.snap(policy, self.board("13-poster2"))
        self.assertEqual(arena.judge(policy, snapshot, arena.state(policy), 1)["why"], "standing-unknown")

    def test_the_table_is_the_game_s_order_on_the_recorded_posters(self):
        self.assertEqual(len(arena.OPPONENTS), 41)
        self.assertEqual(self.cases["03-enter"]["board"]["visible_monsters"][0]["race_id"], arena.OPPONENTS[0])
        self.assertEqual(self.cases["14-enter2"]["board"]["visible_monsters"][0]["race_id"], arena.OPPONENTS[1])

    def test_sheet_lines(self):
        self.assertEqual(arena_standing(" 闘技場:  3勝"), ArenaStanding(wins=3))
        self.assertEqual(arena_standing(" 闘技場: 3回戦で『森トロル』の前に敗北"), ArenaStanding(defeated=True))
        self.assertEqual(arena_standing(" 闘技場: チャンピオン"), ArenaStanding(champion=True))
        self.assertEqual(arena_standing(" Arena:  1 Victory"), ArenaStanding(wins=1))
        self.assertEqual(arena_standing(" Arena: Defeated by X in the 3rd fight"), ArenaStanding(defeated=True))
        self.assertIsNone(arena_standing("nothing"))


if __name__ == "__main__":
    unittest.main()
