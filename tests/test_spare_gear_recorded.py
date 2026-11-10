"""Gear the departure does not use goes to Home (owner 2026-11-04).

「使わない装備をキープしたままダンジョンに出発している。自宅に仕舞うようにしたい。」
「採掘に行かない時はシャベルも仕舞う」

* rejected-sheet (n1-c life-130, 15:27): the character sheet was rejected
  (visible-modifier-mismatch), so no optimizer target released the pack's gear
  and nothing released a good weapon; Home took two of seven items, and the
  shield, gloves and two (聖戦者) weapons left town.
* carried-shovel (n1-a life-479, 15:24): a Shovel in the pack on a recall dive,
  a Pick at Home.

Recorded: each arrival checkpoint and its journal rows
(tests/extract_spare_gear_fixtures.py), decided through the public chooser.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from hengbot import me_powerful_activation
from unittest import mock

import gzip
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot import spare_gear
from hengbot.equipment_optimizer import Loadout, OwnedEquipment, equipment_identity
from hengbot.model import (
    STORE_HOME, StoreState, TVAL_DIGGING, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from hengbot.town_terminal import gather_fundraising, gather_town_end, verdict_fundraising
from replay_town_arrival import adopt_calibration, decisions, restore
from tests.policy_fixtures import item, store_item
from tests.support.recorded import FaithfulHookGame, command_screen, store_screen
from tests.support import recorded as _executor_support

FIXTURES = Path(__file__).with_name("fixtures") / "spare-gear-1104"
LEAF = "spare_gear_stowed"


class Visit:
    def __init__(self, name, calibrated):
        source = FIXTURES / name
        self._directory = TemporaryDirectory()
        root = Path(self._directory.name)
        scratch = root / "scratch"
        scratch.mkdir()
        visit = root / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        self.journal = lzma.decompress((source / "journal.jsonl.xz").read_bytes())
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(self.journal))
        self.policy = restore(visit, scratch)
        if calibrated:
            adopt_calibration(self.policy, source / "calibration.json", scratch)
        self.rows = list(decisions(self.policy, visit, scratch))

    def close(self):
        # The arrival's long Home history must not outlive this test: another
        # module's shorter recorded history would refuse to overwrite it.
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self._directory.cleanup()

    def post(self, key):
        self.policy.confirm_key_posted(key)
        chain = self.policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            self.policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class SpareGearRecordedTest(_executor_support.ProductionHarness):
    def visit(self, name, *, calibrated=False):
        visit = Visit(name, calibrated)
        self.addCleanup(visit.close)
        # DECLARED: the Magic-Eater's *Identify* goes first on these boards (town_key)
        # and the recorded boards never show its effect; this pin is about the shelf.
        patcher = mock.patch.object(me_powerful_activation, "town_key",
                                    lambda _policy, _snapshot, _hostiles: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        return visit

    def test_rejected_sheet_shelves_every_unworn_item_through_the_executor(self):
        visit = self.visit("rejected-sheet")
        policy = visit.policy
        self.assertIsNotNone(policy._calibration_rejection)
        boards = []
        for recorded, supply in visit.rows[:-1]:
            board = supply()
            boards.append(board)
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        recorded, supply = visit.rows[-1]
        inside = supply()
        self.assertEqual(inside.store.store_type, STORE_HOME)
        # Recorded "dndl": only the Scale Mail and an amulet, for the weight.
        self.assertEqual(recorded["key"], "dndl\x1b")
        key = policy.choose_key(inside)
        self.assertEqual(policy.last_reason, "home:weight-overload-deposit")
        self.assertEqual(key, "drdqdpdodndmdl\x1b")
        letters = {item.slot: item.name for item in inside.inventory}
        shelved = [letters[letter] for letter in key[1::2] if letter in letters]
        for name in ("耐酸のナイト・シールド", "ドラゴン・グローブ", "バスタード・ソード", "ムチ"):
            self.assertTrue(any(name in item for item in shelved), name)
        # The bolts, the wands of the staple and Stone to Mud stay.
        self.assertFalse(any(item.is_ammo or item.is_wand_staff
                             for item in inside.inventory if item.slot in key[1::2]))

        # DECLARED CONSTRUCTED: the game's replies (the Home page, then the map).
        game = FaithfulHookGame()
        home_state = self.store_state(inside.turn)
        home_state["store"]["store_type"] = STORE_HOME
        game.screens = [store_screen(), command_screen(inside.turn + 1)]
        game.states = [home_state, {"turn": inside.turn + 1, "grid_map": {"runs": []}}]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        posted = set()
        sent, _ = _send_new_decision_key(
            port, "home-entrance", "5", None, posted, in_store=False,
            decision={"sequence": 1, "reason": policy.last_reason},
            snapshot=boards[-1], posting_contract=PostingContract())
        self.assertTrue(sent)
        sent, _ = _send_new_decision_key(
            port, "home", key, None, posted, in_store=True,
            decision={"sequence": 2, "reason": policy.last_reason},
            snapshot=inside, posting_contract=PostingContract())
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["5", key])

    def test_departure_waits_for_home_while_home_can_take_the_gear(self):
        visit = self.visit("rejected-sheet")
        board = visit.rows[0][1]()
        policy = visit.policy
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertFalse(policy._town_departure_conjuncts(board, commit=False)[LEAF])

    def test_gear_home_cannot_take_never_holds_the_visit(self):
        visit = self.visit("rejected-sheet")
        board = visit.rows[0][1]()
        policy = visit.policy
        policy.choose_key(board)
        # The leaf is unmet, yet the town end's verdict never names it.
        self.assertFalse(policy._town_departure_conjuncts(board, commit=False)[LEAF])
        self.assertNotIn(LEAF, gather_town_end(policy, board).unmet)
        # DECLARED CONSTRUCTED: the visit's Home ledgers, as a refused deposit,
        # a spent Home stop and a full Home record them.
        for state in ("blocked", "attempted", "full"):
            with self.subTest(state):
                saved = (set(policy._town_visit_ledger.blocked_stores),
                         policy._home_capacity_observation)
                if state == "blocked":
                    policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
                elif state == "attempted":
                    policy._town_store_attempted[STORE_HOME] = board.turn
                else:
                    policy._home_capacity_observation = (
                        70, 70, policy._effective_town_id(board))
                self.assertTrue(policy._town_departure_conjuncts(board, commit=False)[LEAF])
                policy._town_visit_ledger.blocked_stores = saved[0]
                policy._town_store_attempted.pop(STORE_HOME, None)
                policy._home_capacity_observation = saved[1]

    def test_optimizer_choice_is_not_released_with_its_siblings(self):
        # A ring or amulet the plan wears on a later step stays in the pack.
        visit = self.visit("rejected-sheet")
        board = visit.rows[0][1]()
        policy = visit.policy
        chosen = next(item for item in board.inventory if "反射のアミュレット" in item.name)
        other = next(item for item in board.inventory if "知能のアミュレット" in item.name)
        self.assertTrue(spare_gear.released(policy, board, chosen))
        # DECLARED CONSTRUCTED: the optimizer's target names the first amulet.
        target = Loadout((("neck", OwnedEquipment("pack:chosen", chosen, "pack")),), "target")
        policy._equipment_optimization_preparation = SimpleNamespace(
            result=SimpleNamespace(best=SimpleNamespace(loadout=target)))
        self.assertFalse(spare_gear.released(policy, board, chosen))
        self.assertTrue(spare_gear.released(policy, board, other))

    def shovel(self, board):
        return next(item for item in board.inventory if item.is_digging_tool)

    def test_shovel_goes_home_when_not_leaving_for_mining(self):
        visit = self.visit("carried-shovel", calibrated=True)
        board = visit.rows[0][1]()
        policy = visit.policy
        shovel = self.shovel(board)
        self.assertIsNone(policy._fundraising_mode)
        # Recorded: the Black Market first, the Shovel carried to the next dive.
        self.assertEqual(visit.rows[0][0]["key"], "\x1b`n%.")
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b`n(.", "equipment-transaction:travel-home"))
        self.assertFalse(policy._digging_tool_stays_carried(board, shovel))
        # The plan and Home's finder read the same rule.
        self.assertEqual(policy._find_home_deposit(board).slot, shovel.slot)
        deposits = [action.item_identity for action in
                    policy._equipment_transaction_session.plan.actions
                    if action.kind == "deposit"]
        self.assertEqual(deposits, [equipment_identity(shovel)])

    def test_mining_keeps_the_shovel_and_takes_the_tool_from_home_first(self):
        visit = self.visit("carried-shovel", calibrated=True)
        board = visit.rows[0][1]()
        policy = visit.policy
        shovel = self.shovel(board)
        # DECLARED CONSTRUCTED: the mining set opened on this recorded board.
        policy._fundraising_mode = "prepare"
        self.assertTrue(policy._digging_tool_stays_carried(board, shovel))
        deposit = policy._find_home_deposit(board)
        self.assertFalse(deposit is not None and deposit.is_digging_tool)
        self.assertTrue(policy._town_departure_conjuncts(board, commit=False)[LEAF])
        # DECLARED CONSTRUCTED: the Shovel already shelved; the recorded Pick
        # is the Home catalog's.
        without = replace(board, inventory=tuple(
            item for item in board.inventory if not item.is_digging_tool))
        self.assertTrue(policy._has_withdrawable_digging_tool(without))
        self.assertFalse(policy._has_digging_tool(without))
        self.assertIn("fundraising-no-digging-tool",
                      verdict_fundraising(gather_fundraising(policy, without)).codes)

    def q2_board(self, policy, inventory_extra=()):
        """The recorded n1-a life-422 Outpost board, Q2 next, its wand spent."""
        with gzip.open(FIXTURES.parent / "quest-stops-20261030.json.gz", "rt",
                       encoding="utf-8") as stream:
            raw = json.load(stream)["q2"]["outpost_board"]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        return replace(board, inventory=[*board.inventory, *inventory_extra])

    def q2_policy(self):
        game = Path("C:/hengband")
        root = Path(__file__).resolve().parents[1]
        maps = {n - 1: parse_town_map(find_town_map(n, game)) for n in range(1, 6)}
        return HengbotPolicy(
            town_map=maps[0], town_maps=maps,
            monrace_knowledge=load_monrace_knowledge(game / "lib/edit/MonraceDefinitions.jsonc"),
            quest_knowledge=load_quest_knowledge(game / "lib/edit/quests"),
            quest_strategies=load_quest_strategies(root / "strategy/quests"))

    def test_q2_takes_its_digger_back_from_home_and_does_not_bounce(self):
        policy = self.q2_policy()
        board = self.q2_board(policy)
        policy.prime(board)
        # DECLARED CONSTRUCTED: a qualifying Mattock on the Home shelf, and the
        # Home page opened on the recorded board.
        mattock = store_item("a", TVAL_DIGGING, 7, name="Mattock", pval=3, known=True,
                             fully_known=True, is_equipment=True)
        weak = store_item("b", TVAL_DIGGING, 1, name="Shovel", pval=1, known=True,
                          fully_known=True, is_equipment=True)
        policy.consume_home_knowledge((mattock, weak))
        self.assertEqual(spare_gear.quest_digger_at_home(policy, board).name, "Mattock")
        self.assertIn((STORE_HOME, "stored-digger"), [
            (need.store_type, need.category) for need in policy._town_need_candidates(board)])
        inside = replace(board, store=StoreState(STORE_HOME, [mattock, weak]))
        self.assertEqual(policy._queue_standing_home_digger(inside), "\x1b")
        self.assertEqual(policy._home_pending_item[0], "Mattock")
        # Carried, it stays out of Home even though the spent wand holds the
        # carry's one-item retention: no bounce.
        carried = item("z", TVAL_DIGGING, 7, name="Mattock", pval=3, known=True,
                       fully_known=True, is_equipment=True)
        holding = self.q2_board(policy, (carried,))
        self.assertIsNone(spare_gear.quest_digger_at_home(policy, holding))
        self.assertTrue(policy._digging_tool_stays_carried(holding, carried))
        # (The board's own weaker tools stay spare off duty.)
        deposit = policy._find_home_deposit(holding)
        self.assertFalse(deposit is not None and deposit.slot == carried.slot)


if __name__ == "__main__":
    unittest.main()
