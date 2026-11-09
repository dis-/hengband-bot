"""n1-b life-316 16:06:08: the Home's last page held one long-named artifact.

Stock 53, page size 52, so page 2 holds only ★森の狩人ロビンフッドのショート・ボウ.
display-store.cpp display_entry writes the weight at column 67 over the name,
so the screen shows it up to "(+15,+17".  compose_barrier_board wanted a whole
store name somewhere on the screen; none of this page's was, so the correct
page stopped as ``phase=store-state`` "missing or mismatching current store
page" and the withdrawal never ran.

The barrier now also accepts a page that binds slot by slot, the check that
already bound the record of a resume.  A really different page is still refused.
Fixture: tests/extract_store_page_cut_name_1105_fixture.py.
DECLARED RECONSTRUCTED: the session from decision 21's transaction facts (only
its next action, the Home withdrawal); page 1's screen drawn from its record.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import STORE_HOME, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from tests.support.recorded import EDIT, _policy
from test_resume_inside_store import home_page_screen
from tests.support import recorded as executor_pins


FIXTURE = Path(__file__).with_name("fixtures") / "store-page-cut-name-1105.json.gz"
CUT_NAME = "★森の狩人ロビンフッドのショート・ボウ (x3) (1.0turn) (+15,+17"
# As wide as the recorded name, so only the text can tell the two rows apart.
OTHER_NAME = "★森の狩人ロビンフッドのロング・ボウだ (x3) (1.0turn) (+15,+17"
DEADLINE = 9999999999


class StorePageCutNameTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def recorded_screen(self, *replacements):
        screen = copy.deepcopy(self.case["screen"])
        for old, new in replacements:
            found = [y for y, line in enumerate(screen["lines"]) if old in line]
            self.assertEqual(len(found), 1, old)
            screen["lines"][found[0]] = screen["lines"][found[0]].replace(old, new)
        return screen

    def seek_page(self, screen, *, row=None, state=None):
        """Post the recorded page switch; the game then shows ``screen``."""
        page_one, page_two = self.case["pages"]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(page_one)
        game.screen = home_page_screen(page_one["store"])
        _game, _client, executor = self.make(game)
        records = [page_one]
        executor.drain = lambda: list(records)
        self.assertEqual(executor.observe_boundary(deadline=DEADLINE).outcome, "ready")
        game.states = [copy.deepcopy(state or self.case["state"])]
        game.screens = [screen]
        records.append(row or page_two)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", self.case["decision"]["key"], None, set(), in_store=True,
            decision={"sequence": 21, "reason": self.case["decision"]["reason"]},
            snapshot=None, posting_contract=PostingContract(),
        )
        return sent, port, executor

    def assert_refused(self, screen, **fields):
        sent, port, _executor = self.seek_page(screen, **fields)
        self.assertFalse(sent)
        self.assertIn("phase=store-state", port.last_result.stop_line)

    def policy_in_session(self, directory):
        policy = _policy(Path(directory), self.monrace)
        raw = self.case["pages"][0]
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        policy.prime(board)
        policy.consume_skill_knowledge(
            {**self.case["skill"], "player": {"level": board.player.level}})
        policy.consume_home_knowledge(
            tuple(_parse_items(self.case["home"]["knowledge"]["items"], protocol=3)))
        action = self.case["decision"]["transaction_next"]
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((EquipmentTransaction(
                phase=action["phase"], kind=action["kind"], item_id=action["item_id"],
                target_slot=action["target_slot"],
                item_identity=action["item_id"].split(":")[1]),), (), 0),
            physical_context="home",
        )
        session.opened_sequence = self.case["decision"]["store_visit"]["opened_sequence"]
        policy._equipment_transaction_session = session
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME,
            StoreVisitPhase.OPERATING, opened_sequence=session.opened_sequence)
        return policy, session

    def test_recorded_screen_cuts_the_only_name_of_the_page(self):
        store = self.case["pages"][1]["store"]
        self.assertEqual((store["page_top"], store["page_size"], store["stock_num"]), (52, 52, 53))
        name = store["items"][0]["name"]
        lines = self.case["screen"]["lines"]
        self.assertFalse(any(name in line for line in lines))
        self.assertTrue(name.startswith(CUT_NAME))
        self.assertTrue(any(CUT_NAME in line for line in lines))

    def test_cut_name_page_is_ready_and_the_withdrawal_follows(self):
        with TemporaryDirectory() as directory:
            policy, session = self.policy_in_session(directory)
            first = parse_snapshot(copy.deepcopy(self.case["pages"][0]), self.monrace)
            key = policy.choose_key(policy.with_known_skill_exp(first))
            self.assertEqual((key, policy.last_reason),
                             (self.case["decision"]["key"], self.case["decision"]["reason"]))
            policy.confirm_key_posted(key)

            sent, port, executor = self.seek_page(self.recorded_screen())
            self.assertTrue(sent, port.last_result.stop_line)
            self.assertEqual(executor.ready_board["store"]["page_top"], 52)

            board = parse_snapshot(copy.deepcopy(dict(executor.ready_board)), self.monrace)
            target = board.store.items[0]
            self.assertEqual(equipment_identity(target), session.current_action.item_identity)
            key = policy.choose_key(policy.with_known_skill_exp(board))
            self.assertEqual(policy.last_reason, "equipment-transaction:withdraw")
            self.assertEqual(key, "pa")

    def test_record_of_the_other_page_is_refused_on_the_recorded_screen(self):
        # A state without the store payload leaves the screen as the only guard.
        state = copy.deepcopy(self.case["state"])
        state.pop("store")
        self.assert_refused(self.recorded_screen(), row=self.case["pages"][0], state=state)

    def test_different_cut_name_in_the_slot_is_refused(self):
        self.assert_refused(self.recorded_screen((CUT_NAME, OTHER_NAME)))

    def test_page_indicator_of_another_page_is_refused(self):
        self.assert_refused(self.recorded_screen(("(2ページ)", "(1ページ)")))

    def test_game_state_on_another_page_is_refused(self):
        state = copy.deepcopy(self.case["state"])
        state["store"]["page_top"] = 0
        self.assert_refused(self.recorded_screen(), state=state)


if __name__ == "__main__":
    import unittest
    unittest.main()
