"""A burnt-out torch no longer splits the quest torch carry (torch-buy-deposit-1114).

n1-b life-396 (Lv8 Magic-Eater, a Brass Lantern worn, a Long Sword, no launcher) stopped on
2026-11-14 11:05 with town:blocked:stage-deadline:home.  The visit's carry plan (Q14's
required_force merged with the opening's, ``throwing_items.lit_torch`` 20) bought twenty
torches at the General Store (row 62 ``pi20``) beside a burnt-out torch already in the pack
(slot i, 松明(0ターンの寿命), before the new stack j in pack order).  The two sides of that one
carry then disagreed:

* the count (``_quest_named_item_count``, read by ``_torch_carry_requirement`` for the
  purchase and the Home take) counts torches with light left: 20 of 20;
* the item match (``_quest_carry_target_for_item``) matched every torch, so the retention's
  ``carry-strategy:lit_torch`` allocation (policy_home ``_retention_reservation_baseline_detail``,
  in pack order) gave the burnt-out torch one of the twenty and kept nineteen of stack j.

The twentieth was surplus (``reserved_stack_surplus``): Home took one ('dj1'), the count then
read 19 and the General Store sold one more ('pi1'), 41 buys and 47 deposits until the stage
deadline.  In the game only a torch with fuel is a lit torch (specific-object/torch.cpp
is_active_torch, read by torch_flags and throw-execution.cpp), so the carry's match and its
count now read that one predicate (``_is_lit_torch``): the burnt-out torch is no carry item,
stack j keeps all twenty, and the visit goes on to its errand plan's next stop, the Magic shop
sale (store 5, organization-sale / device-sale), which the recorded visit only reached at row
126 after the loop.

Recorded: the town-arrival checkpoint, its first 67 journal rows and the arrival's character
calibration (tests/extract_torch_buy_deposit_1114_fixture.py), decided through the public
choose_key; the first key outside the General Store is posted through the production executor
(_ExecutorInputPort).

DECLARED CONSTRUCTED: the town around Home (``HomeEntranceGame``: travel to Home enters it with
the recorded Home page of row 66 as its shelf; travel to another store ends the case).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import TRAVEL_MACRO_TRIGGERS, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_HOME, STORE_MAGIC, parse_snapshot
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, restore
from tests.support import recorded as harness
from tests.test_town_withdraw_pack_budget_recorded import HomeEntranceGame

FIXTURE = Path(__file__).with_name("fixtures") / "torch-buy-deposit-1114"
BUY_ROW = 62          # 'pi20' at the General Store: twenty torches bought
OUTSIDE_ROW = 65      # the first board outside the General Store (recorded: travel to Home)
HOME_ROW = 66         # the recorded Home page (recorded: 'dj1', one torch deposited)
LIT_TORCHES = 20
MAGIC_SHOP_TRAVEL = "\x1b`n&."
HOME_TRAVEL = "\x1b`n(."


class TorchBuyDeposit1114RecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.journal = lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())

    def load(self):
        scratch_dir = TemporaryDirectory()
        self.addCleanup(scratch_dir.cleanup)
        root = Path(scratch_dir.name)
        visit, scratch = root / "town-arrival", root / "scratch"
        visit.mkdir()
        scratch.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(self.journal))
        policy = restore(visit, scratch)
        policy._home_disposal.history_path = scratch / "home-history.jsonc"
        adopt_calibration(policy, FIXTURE / "calibration.json", scratch)
        return policy, list(decisions(policy, visit, scratch))

    def raw(self, row):
        entry = json.loads(self.journal.decode("utf-8").splitlines()[row])
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def replay_to_outside(self):
        """Rows 0-64 replay as recorded; the board of row 65 is returned undecided."""
        policy, rows = self.load()
        for recorded, supply in rows[:OUTSIDE_ROW]:
            key = policy.choose_key(supply())
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            policy.confirm_key_posted(key)
        self.assertEqual(rows[BUY_ROW][0]["key"], "pi20\r\r")
        # The recorded loop: to Home with the twenty, one torch deposited.
        self.assertEqual((rows[OUTSIDE_ROW][0]["key"], rows[HOME_ROW][0]["key"]),
                         (HOME_TRAVEL, "dj1\r\x1b"))
        return policy, rows[OUTSIDE_ROW][1]()

    def test_the_whole_bought_stack_is_the_carry(self):
        policy, board = self.replay_to_outside()
        burnt = next(item for item in board.inventory if item.slot == "i")
        bought = next(item for item in board.inventory if item.slot == "j")
        self.assertEqual((burnt.is_torch, burnt.fuel, bought.is_torch, bought.count),
                         (True, 0, True, LIT_TORCHES))
        strategy = policy._carry_procurement_strategy(board)
        self.assertEqual(strategy.required_force["throwing_items"]["lit_torch"], LIT_TORCHES)
        # One reading of the carry: the item match and the count agree on the lit torches.
        self.assertIsNone(
            policy._quest_carry_target_for_item(board, burnt, strategy.required_force))
        self.assertEqual(
            policy._quest_carry_target_for_item(board, bought, strategy.required_force),
            ("lit_torch", LIT_TORCHES, LIT_TORCHES))
        self.assertEqual(policy._torch_carry_requirement(board, bought, strategy),
                         (LIT_TORCHES, LIT_TORCHES))
        self.assertEqual(policy._retention_reservation_detail(board, bought),
                         (LIT_TORCHES, "carry-strategy:lit_torch"))
        self.assertEqual(policy._retention_surplus(board, bought), 0)
        self.assertFalse(policy._home_deposit_candidate(bought, board))

    def test_the_visit_goes_on_to_the_magic_shop_through_the_executor(self):
        policy, board = self.replay_to_outside()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (MAGIC_SHOP_TRAVEL, "shop:travel"))
        self.assertEqual(policy._store_visit.store_type, STORE_MAGIC)
        self.assertNotEqual(policy._store_visit.store_type, STORE_HOME)

        outside, home_page = self.raw(OUTSIDE_ROW), self.raw(HOME_ROW)
        entrance = next(grid.position for grid in board.grids.values()
                        if grid.store_number == STORE_HOME)
        shelf = copy.deepcopy(home_page["store"]["items"])
        game = HomeEntranceGame(
            pack=copy.deepcopy(outside["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(outside["equipment"])},
            pages=[shelf], inside=False, state_template=copy.deepcopy(outside),
            home_limit=home_page["store"]["capacity"])
        game.entrance = entrance.y, entrance.x
        game.position = outside["player"]["y"], outside["player"]["x"]
        game.turn = outside["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 5).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=policy)
        reasons = [(key, policy.last_reason)]
        current = board
        for _ in range(12):
            _send_new_decision_key(
                port, json.dumps(game._state()), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            self.assertEqual(port.last_result.outcome, "completed",
                             (reasons, port.last_result.reason))
            policy.confirm_key_posted(key)
            if game.left_for is not None:
                break
            current = parse_snapshot(port.last_result.board, policy._monrace_knowledge)
            key = policy.choose_key(current)
            reasons.append((key, policy.last_reason))
        # Sent once, to the Magic shop: Home never entered, no torch put away or bought.
        self.assertEqual(game.left_for, TRAVEL_MACRO_TRIGGERS[MAGIC_SHOP_TRAVEL], reasons)
        self.assertEqual(game.entries, 0, reasons)
        self.assertEqual(reasons, [(MAGIC_SHOP_TRAVEL, "shop:travel")])
        self.assertEqual(sum(item["count"] for item in game.pack
                             if item["tval"] == 39 and item["sval"] == 0
                             and item.get("light_turns", 0) > 0), LIT_TORCHES)
        self.assertFalse([item for item in game._items() if item["tval"] == 39])


if __name__ == "__main__":
    unittest.main()
