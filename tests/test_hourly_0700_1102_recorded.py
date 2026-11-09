"""The 2026-11-02 06:10-06:49 viewing-bot stops (hourly-0700-1102).

Each class pins one root on its recorded board; only the game's replies to
newly posted keys are constructed (marked DECLARED CONSTRUCTED) and facts the
capture keeps outside the board are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_0700_1102_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _dispatch_response_lines,
    _make_jsonl_barrier_drain, _report_state_stream_rollover, _send_new_decision_key,
)
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.home_errand import HomeErrandRequest
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import RECALL_DEPTH_PROMPT_MESSAGE_PREFIXES
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO, STORE_HOME
from hengbot.policy_types import TownErrandPlan
from tests.support import recorded as executor_pins
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-0700-1102.json.gz"


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _jsonl(rows):
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


class RecordedTownPolicy(unittest.TestCase):
    """A live-configured policy primed on a recorded town board."""

    def primed(self, raw, home_items, skill):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(self.root, self.monrace)
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        policy.prime(board)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        policy.consume_home_knowledge(tuple(_parse_items(home_items, protocol=3)))
        return policy

    def board(self, policy, raw):
        return policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))


class StateStreamRolloverHomeListTest(RecordedTownPolicy):
    """n1-a life-464 06:10:25 no-key-exhausted.

    Decision 10034 posted ``~9<ESC>``; bot-json-output.cpp write_snapshot
    truncated state.jsonl at BOT_JSON_OUTPUT_MAX_BYTES before the next record,
    so the Home list written just before was never read (the stop's
    state.jsonl starts at turn 3003443).  The Home errand kept awaiting that
    reply with no command (10037 ``''``) and the bot stopped.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["rollover"]

    def test_rollover_settles_the_lost_home_list_request(self):
        request, stop = self.case["decisions"]
        self.assertEqual((request["decision_sequence"], request["key"], request["reason"]),
                         (10034, HOME_KNOWLEDGE_MACRO,
                          "home-errand:request-knowledge:identification"))
        self.assertEqual((stop["decision_sequence"], stop["key"], stop["reason"]),
                         (10037, "", "home-errand:await-fresh-knowledge:identification"))
        self.assertIn("<no-key-exhausted>", self.case["stdout_tail"][-1])
        after = self.case["after"]
        self.assertEqual(after[0]["turn"], request["turn"])
        policy = self.primed(after[0], self.case["home"]["knowledge"]["items"], self.case["skill"])
        # DECLARED RECONSTRUCTED: the errand the recorded reasons name
        # (purpose identification, waiting for a fresh Home list).
        policy._home_errand.file(HomeErrandRequest(
            signature=("recorded", 0, 0), quantity=1, origin="home-catalog",
            purpose="identification"), knowledge_current=False)
        policy.confirm_key_posted(request["key"])
        self.assertTrue(policy._home_knowledge_scan_inflight)

        # The production barrier drain attached to the pre-rollover file;
        # the emitter then truncated it and wrote the recorded rows.
        state = self.root / "state.jsonl"
        state.write_text(_jsonl(self.case["before"]), encoding="utf-8")
        drain = _make_jsonl_barrier_drain(state)
        state.write_text(_jsonl(after[:2]), encoding="utf-8")
        self.assertEqual([row["turn"] for row in drain()], [request["turn"]] * 2)
        handed = drain.take_handed_records()
        _dispatch_response_lines([json.dumps(row, ensure_ascii=False) + "\n" for row in handed],
                                 policy, lambda _key: True, decoded_lines=handed,
                                 knowledge_ledger_path=self.root / "knowledge.jsonl")
        self.assertTrue(drain.take_rollover())
        _report_state_stream_rollover(policy)

        key = policy.choose_key(self.board(policy, after[-1]))
        # Recorded: '' home-errand:await-fresh-knowledge (no-key-exhausted).
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home-errand:request-knowledge:identification"))


class EquipmentDepositAfterIdentificationWithdrawalTest(RecordedTownPolicy):
    """n1-c life-103 06:41:31 equipment-transaction:home-route-repeat-terminal.

    The identification-catalog withdrawal (1880, ``5pi<ESC>``) took the
    unknown chain mail from Home; identified, the equipment plan deposits it
    back.  Its stop was already Home, so the equipment owner kept the town
    plan whose only Home need was the finished identification-withdrawal,
    and _shopping_approach_step refused that stop while no Home errand was
    filed: home-route-unavailable, abandon-blocked, repeat-terminal.  The
    same plan stands in all five home-route-repeat-terminal stops of
    2026-11-01/02.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["home-route"]

    def test_equipment_deposit_routes_home_past_the_spent_identification_stop(self):
        decision, raw = self.case["decision"], self.case["board"]
        self.assertEqual((decision["decision_sequence"], decision["key"], decision["reason"]),
                         (1885, "5", "equipment-transaction:home-route-unavailable"))
        self.assertEqual(self.case["withdrawal"]["reason"],
                         "home-errand:atomic-withdraw:identification-catalog")
        # DECLARED RECONSTRUCTED: the last Home list (turn 1808157) less the
        # chain mail the recorded withdrawal took (now in the pack).
        home = [item for item in self.case["home"]["knowledge"]["items"]
                if (item["tval"], item["sval"]) != (37, 4)]
        policy = self.primed(raw, home, self.case["skill"])
        board = self.board(policy, raw)
        action = decision["transaction_next"]
        item = next(item for item in board.inventory
                    if f"pack:{equipment_identity(item)}:0" == action["item_id"])
        # DECLARED RECONSTRUCTED: the session and plan the decision row and
        # policy-state record (one deposit; Home stop for identification).
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((EquipmentTransaction(
                **action, item_identity=equipment_identity(item),
                move_identity=equipment_move_identity(item)),), (), len(board.inventory)))
        plan = self.case["town_errand_plan"]
        policy._town_errand_plan = TownErrandPlan(
            [int(stop) for stop in plan["stops"]],
            need_categories={int(k): tuple(v) for k, v in plan["need_categories"].items()},
            completed_this_visit=list(plan["completed_this_visit"]),
            requester_families={int(k): frozenset(v)
                                for k, v in plan["requester_families"].items()})
        self.assertFalse(policy._home_errand.active)

        key = policy._equipment_transaction_town_key(board)
        # Recorded: '5' equipment-transaction:home-route-unavailable.
        self.assertEqual(policy.last_reason, "equipment-transaction:approach-home")
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
        self.assertEqual(key, "1")  # (44,124) -> the Home entrance (45,123)


class EspThreatRecallDepthQuestionTest(executor_pins.ProductionHarness):
    """n1-c life-103 06:49:23: esp-threat:leave-recall read ``rh`` on depth 15.

    spells-world.cpp recall_player asked 「ここは最深到達階より浅い階です。
    この階に戻って来ますか？」 (underground, shallower than the saved depth, no
    recall active).  The executor answered it only for a listed set of
    recall owners, so this reader stopped as an unowned confirm.
    """

    READ_PROMPT = "どの巻物を読みますか? "

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["esp-recall"]

    def test_recorded_recall_read_answers_the_depth_question(self):
        decision, raw = self.case["decision"], self.case["board"]
        self.assertEqual((decision["decision_sequence"], decision["reason"], decision["key"]),
                         (3738, "esp-threat:leave-recall", "rh"))
        self.assertIn("owner=esp-threat:leave-recall", self.case["stuck_prompt"])
        self.assertIn("reason=unowned confirm", self.case["stuck_prompt"])
        question = RECALL_DEPTH_PROMPT_MESSAGE_PREFIXES[0]
        self.assertIn(question, self.case["stuck_prompt"])
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        snapshot = parse_snapshot(copy.deepcopy(raw), monrace)
        self.assertEqual(snapshot.floor_key[1], 15)
        self.assertFalse(snapshot.player.recalling)
        self.assertTrue(next(item for item in snapshot.inventory if item.slot == "h").is_recall_scroll)

        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [
            executor_pins.prompt_screen(self.READ_PROMPT),
            executor_pins.prompt_screen(question + " [y/n]"),
            executor_pins.command_screen(raw["turn"] + 1),
        ]
        game.states = [copy.deepcopy(raw) for _ in game.screens]
        # DECLARED CONSTRUCTED: recall_player's effect after the refusal
        # (word_recall set, 「回りの大気が張りつめてきた...」).
        game.states[-1]["turn"] = raw["turn"] + 1
        game.states[-1]["player"]["recalling"] = True
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", decision["key"], None, set(), in_store=False,
            decision={"sequence": decision["decision_sequence"], "reason": decision["reason"]},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        # Recorded: r, h, then stuck-prompt on the unowned depth question.
        self.assertEqual(game.accepted, ["r", "h", "n"])
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed")


if __name__ == "__main__":
    unittest.main()
