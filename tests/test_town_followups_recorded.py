"""D30 follow-ups: the owner's three rules of 2026-10-31 on recorded boards.

1. 「逃げた階に戻らないための決定なので帰還後はリセットされるべき」: the
   escape-by-stairs descent cooldown ends once the character is back in town
   (n1-a life-440: status-threat:stairs from Yeek 1F, then stuck:wander
   with descent_refusal descent-cooldown until a forced departure waited out).
2. 「条件未達になったなら条件を満たすための行動を取る必要がある」: a committed
   forced departure whose minimum no longer holds is handed back to the
   ordinary owners (n1-a life-427: a town fight left HP below full and the
   repetition rungs waited until the named-block stop).
3. 「自宅にいるなら先に不要物を仕舞う」: a Home take that does not fit the town
   pack budget, the mana eater's food take included, first shelves unneeded
   stacks (n1-b life-256 Home page, 19 of 23 slots used).

Boards and catalogues are recorded; replies to newly posted keys and the
marked state below are constructed.  Every decision goes through the public
chooser, and posted keys through the production executor.
Fixture: tests/extract_town_followups_fixture.py.
"""
import tests  # noqa: F401 -- runtime-file isolation

import copy
import gzip
import hashlib
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _consume_response_sequence, _ExecutorInputPort, _send_new_decision_key,
)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy_constants import TOWN_CYCLE_BREAK_LIMIT
from tests import test_input_executor as harness
from tests.test_esp_threat_rest_recorded import _policy
from tests.test_town_withdraw_pack_budget_recorded import HomeEntranceGame


FIXTURE = Path(__file__).with_name("fixtures") / "town-followups-20261031.json.gz"
FIXTURE_SHA256 = "2f9c35484db1fc8aa4fea9d9db1f8fb590106fe651af15cdbf5d7b56941e8814"


class TownFollowupsRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
        cls.cases = json.loads(gzip.decompress(data))

    def policy(self, case):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        races = {}
        for key, facts in case["monraces"].items():
            facts = dict(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            races[int(key)] = MonraceKnowledge(**facts)
        return _policy(Path(self.directory.name), races)

    def answer(self, policy, row):
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        _consume_response_sequence([json.dumps(row)], policy, lambda key: True, {},
                                   knowledge_ledger_path=Path(self.directory.name) / "k.jsonl")

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        # DECLARED CONSTRUCTED: the skill census, as in the other town replays.
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return board, policy.choose_key(board)

    def post(self, policy, raw, key):
        """Send one town key through the production executor."""
        game = harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the next board after the posted key.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        prompts = ([harness.prompt_screen("Rest (0-9999, '*' for HP/SP, '&' as needed): ")]
                   if key.startswith("R") else [])
        game.screens = prompts + [harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in prompts] + [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract())
        self.assertTrue(sent, getattr(port.last_result, "stop_line", None))
        self.assertEqual(port.last_result.outcome, "completed")
        policy.confirm_key_posted(key)

    # Rule 1 ---------------------------------------------------------------
    def test_escape_descent_cooldown_ends_back_in_town(self):
        case = self.cases["cooldown"]
        rows = case["rows"]
        recorded = case["recorded"]
        self.assertEqual(recorded["83"][0]["reason"], "status-threat:stairs")
        self.assertEqual((recorded["84"][0]["reason"], recorded["84"][0]["descent_refusal"]),
                         ("stuck:wander", "descent-cooldown"))
        policy = self.policy(case)
        self.answer(policy, rows["home"])
        policy.prime(parse_snapshot(copy.deepcopy(rows["town"]), policy._monrace_knowledge))
        self.decide(policy, rows["town"])
        _, key = self.decide(policy, rows["dungeon"])
        # The recorded escape arms the cooldown on the fled floor.
        self.assertEqual((key, policy.last_reason), ("<", "status-threat:stairs"))
        self.assertTrue(policy._descent_blocked)
        policy.confirm_key_posted(key)
        arrival, key = self.decide(policy, rows["arrival"])
        self.assertFalse(policy._descent_blocked)
        self.assertEqual(policy._descent_block_countdown, 0)
        self.assertFalse(policy._descent_is_blocked(arrival)
                         and policy._descent_refusal_reason == "descent-cooldown")
        self.assertNotEqual(policy.last_reason, "stuck:wander")
        self.post(policy, rows["arrival"], key)

    # Rule 2 ---------------------------------------------------------------
    def test_lost_departure_minimum_is_satisfied_instead_of_waited(self):
        case = self.cases["lost-departure"]
        rows = case["rows"]
        self.assertEqual([(row["reason"], row["key"]) for row in case["recorded"]["9204"]],
                         [("town:blocked:repetition", "5")])
        policy = self.policy(case)
        fight = parse_snapshot(copy.deepcopy(rows["fight"]), policy._monrace_knowledge)
        policy.prime(fight)
        # DECLARED RECONSTRUCTED: the commitment force_visit_departure made
        # earlier in this visit (stdout "<keep-running> forced_departure
        # cause=departure-unsatisfiable"); the capture omits these fields.
        cause = "departure-unsatisfiable"
        policy._visit_departure_recorded.add(cause)
        policy._break_town_cycle(fight)
        policy._town_blocked_reason = "repetition"
        policy._town_cycle_breaks = TOWN_CYCLE_BREAK_LIMIT
        policy._visit_departure_committed = cause
        # The fight board's decision (a Home census request) precedes it.
        _, key = self.decide(policy, rows["fight"])
        policy.confirm_key_posted(key)
        board = parse_snapshot(copy.deepcopy(rows["board"]), policy._monrace_knowledge)
        self.assertLess(board.player.hp, board.player.max_hp)
        _, key = self.decide(policy, rows["board"])
        self.assertNotEqual((key, policy.last_reason), ("5", "town:blocked:repetition"))
        self.assertEqual(policy.last_reason, "town:recover")
        self.assertIsNone(policy._visit_departure_committed)
        self.assertIn(cause, policy._visit_departure_recorded)
        self.post(policy, rows["board"], key)

    # Rule 3 ---------------------------------------------------------------
    def test_mana_food_take_shelves_surplus_first(self):
        case = self.cases["mana-home"]
        rows = case["rows"]
        page = copy.deepcopy(rows["page"])
        outside = copy.deepcopy(rows["outside"])
        # DECLARED CONSTRUCTED: hungry, with every carried device spent, so
        # the Home device is the only food (19 of 23 slots stay used).
        for raw in (page, outside):
            raw["player"]["food_state"] = "hungry"
            for item in raw["inventory"]:
                if item["tval"] in (55, 65):  # TV_STAFF, TV_WAND
                    item["charges"] = item["pval"] = 0
        policy = self.policy(case)
        self.answer(policy, rows["home"])
        board = parse_snapshot(copy.deepcopy(page), policy._monrace_knowledge)
        policy.prime(board)
        self.assertEqual(len(board.inventory), 19)
        self.assertIsNone(policy._find_edible(board))
        self.assertIsNotNone(policy._home_mana_food_candidate())
        shelf = [dict(item) for item in rows["home"]["knowledge"]["items"]]
        game = HomeEntranceGame(
            pack=page["inventory"], equipment={item["slot"]: item for item in page["equipment"]},
            pages=[shelf], inside=True, state_template=outside,
            home_limit=page["store"]["capacity"])
        game.entrance = game.position = (page["player"]["y"], page["player"]["x"])
        game.turn = page["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        result = executor.observe_boundary(deadline=time.monotonic() + 5)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2, policy=policy)
        reasons = []
        for _ in range(12):
            current = parse_snapshot(result.board, policy._monrace_knowledge)
            policy._skill_exp_cache = (0, 0, current.player.level, policy._town_visit_epoch)
            key = policy.choose_key(current)
            reasons.append(policy.last_reason)
            self.assertTrue(key, reasons)
            _send_new_decision_key(
                port, json.dumps(result.board), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            result = port.last_result
            self.assertEqual(result.outcome, "completed", (reasons, result.reason))
            policy.confirm_key_posted(key)
            if policy.last_reason == "survival:mana-home-withdraw" or game.left_for:
                break
            if "request-knowledge-scan" in policy.last_reason or policy.last_reason.endswith("home-scan"):
                row = copy.deepcopy(outside)
                row.update(game._state(), type="knowledge",
                           knowledge={"category": "home", "menu_key": "9",
                                      "items": copy.deepcopy(game._items())})
                self.answer(policy, row)
        self.assertIn("home:atomic-deposit", reasons)
        self.assertEqual(reasons[-1], "survival:mana-home-withdraw", reasons)
        self.assertLess(reasons.index("home:atomic-deposit"), len(reasons) - 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
