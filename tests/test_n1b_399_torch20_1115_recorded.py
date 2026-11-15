"""After Q1, a Magic-Eater below Lv10 no longer carries Q1's twenty torches (n1-b life-399).

n1-b life-399 (zombie Magic-Eater Lv8, build 3b52c43f0; Q34 and Q1 completed, Q14
taken) visited the Outpost on 2026-11-15 11:4x.  Below Lv10 the carry procurement
folded Q1's class-16 torch count (``throwing_items_by_class`` 16: lit_torch 20,
「松明20本はキープして」) into the next quest's force (``_carry_procurement_strategy``),
although Q1 was done: the visit walked to the General store (row 7), bought 17 torches
(row 15, 3 -> 20), and after its other errands stood at 1389 over the 1350 limit
(STR index 17, ``adj_str_wgt[17] * 50``, player-status.cpp ``calc_weight_limit``) with
every carried item retained (the torches by ``carry-strategy:lit_torch``).  Nothing was
left to sell or to deposit and the visit stopped under
town:blocked:survival:inventory_weight_ready (row 135).

Owner 2026-11-15 「Q1 の後は松明20本をやめる」: once Q1 is completed the twenty torches
are no longer carried, even below Lv10; only what the next quest asks (Q14: no torch)
and the ordinary carries stay (the shallow throwing stock, ``TORCH_THROW_TARGET``).

Recorded: the incident capture's town-arrival checkpoint and its whole journal
(tests/extract_n1b_399_torch20_1115_fixture.py), decided through the public choose_key.
The first new decision is sent through the production executor (``_ExecutorInputPort``).

DECLARED CONSTRUCTED: the policy state on rows 15 and 135 is the replay acknowledging the
recorded keys (the visit the branch would have walked differs from row 7); the control
board is row 7 with Q1 taken; the within-limit pack is the stop board's with the torches
cut to the branch's carry target.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_FINISHED, QUEST_STATUS_TAKEN
from support.town_arrival_fixture import load
from tests.test_me_nokey_1031_recorded import PostedKey

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-399-torch20-1115"
ERRAND_ROW = 7
STORE_ROW = 15
STOP_ROW = 135
STOP = "town:blocked:survival:inventory_weight_ready"
GENERAL_STORE_TRAVEL = "\x1b`n!."
MAGIC_SHOP_TRAVEL = "\x1b`n&."


class N1b399Torch201115RecordedTest(PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        cls.checkpoints = {}
        for recorded, supply in steps[:STOP_ROW + 1]:
            row = recorded["row"]
            if row in (ERRAND_ROW, STORE_ROW, STOP_ROW):
                cls.checkpoints[row] = checkpoint_bytes(policy)
            key = policy.choose_key(supply())
            if row < ERRAND_ROW:
                cls.replayed.append((row, (key, policy.last_reason),
                                     (recorded["key"], recorded["reason"])))
            # From row 7 on the policy observes each recorded board and is told the
            # recorded key was posted (DECLARED CONSTRUCTED, module docstring).
            policy.confirm_key_posted(recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def restore(self, row):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoints[row])
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy

    def supply(self, policy, row):
        """The recorded row's board, its response lines and latches delivered first
        (tests/replay_town_arrival.py ``decisions``)."""
        entry = self.journal[row]
        _consume_response_sequence(
            [line + "\n" for line in entry["inputs"]], policy, lambda _key: True,
            policy._monrace_knowledge, parse_snapshots=False,
            knowledge_ledger_path=Path(self.scratch.name) / "knowledge.jsonl")
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        return self.board(policy, self.line(row))

    def line(self, row):
        return json.loads(self.journal[row]["line"])

    @staticmethod
    def board(policy, raw):
        return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)

    @staticmethod
    def with_q1(raw, status):
        raw = copy.deepcopy(raw)
        (q1,) = [quest for quest in raw["progress"]["quests"] if quest["id"] == 1]
        q1["status"] = status
        return raw

    @staticmethod
    def lit_torch(policy, board):
        strategy = policy._carry_procurement_strategy(board, cache_fixed_quest_head=False)
        return strategy, int(strategy.required_force.get("throwing_items", {}).get("lit_torch", 0))

    def test_the_rows_before_the_torch_errand_decide_as_recorded(self):
        for row, decided, recorded in self.replayed:
            self.assertEqual(decided, recorded, row)
        journal = self.journal
        self.assertEqual((journal[ERRAND_ROW]["key"], journal[ERRAND_ROW]["reason"]),
                         (GENERAL_STORE_TRAVEL, "shop:travel"))
        self.assertEqual((journal[STORE_ROW]["key"], journal[STORE_ROW]["reason"]),
                         ("pg17\r\r", "shop:in-store-buy"))
        (bought,) = [item for item in self.line(STORE_ROW)["store"]["items"]
                     if item.get("letter") == "g"]
        self.assertEqual((bought["tval"], bought["sval"]), (39, 0))  # TV_LITE, SV_LITE_TORCH
        self.assertTrue(bought["name"].startswith("松明"), bought["name"])
        self.assertEqual(journal[STOP_ROW]["reason"], STOP)

    def test_q1_done_drops_the_twenty_torches_and_skips_the_torch_errand(self):
        policy = self.restore(ERRAND_ROW)
        raw = self.line(ERRAND_ROW)
        quests = {quest["id"]: quest["status"] for quest in raw["progress"]["quests"]}
        self.assertEqual((quests[1], quests[14], raw["player"]["level"]),
                         (QUEST_STATUS_FINISHED, QUEST_STATUS_TAKEN, 8))
        board = self.supply(policy, ERRAND_ROW)
        strategy, torches = self.lit_torch(policy, board)
        self.assertEqual((strategy.quest_id, torches), (14, 0))
        (torch,) = [item for item in board.inventory if item.is_torch]
        # The shallow throwing stock (no sling ammunition carried), not Q1's 20.
        self.assertEqual(policy._torch_carry_requirement(board, torch, strategy), (10, 3))

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), (MAGIC_SHOP_TRAVEL, "shop:travel"))
        self.post(policy, raw, key)

    def test_control_before_q1_completes_the_twenty_torches_stay(self):
        """DECLARED CONSTRUCTED: row 7's board with Q1 taken, not completed."""
        policy = self.restore(ERRAND_ROW)
        board = self.board(policy, self.with_q1(self.line(ERRAND_ROW), QUEST_STATUS_TAKEN))
        strategy, torches = self.lit_torch(policy, board)
        self.assertEqual((strategy.quest_id, torches), (1, 20))

    def test_the_general_store_page_buys_no_twenty_torch_fill(self):
        policy = self.restore(STORE_ROW)
        key = policy.choose_key(self.supply(policy, STORE_ROW))
        self.assertFalse(key.startswith("p"), (key, policy.last_reason))
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "town-progress-invariant:continue-observed-shop"))

    def test_the_stop_board_no_longer_stops_and_the_carry_fits(self):
        policy = self.restore(STOP_ROW)
        raw = self.line(STOP_ROW)
        board = self.supply(policy, STOP_ROW)
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1389, 1350))
        torches = [item for item in board.inventory if item.is_torch]
        self.assertEqual([policy._retention_reservation_detail(board, item) for item in torches],
                         [(10, "torch-carry"), (0, None)])

        key = policy.choose_key(board)

        self.assertNotEqual(policy.last_reason, STOP)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertTrue(key, policy.last_reason)

        # DECLARED CONSTRUCTED: the pack with the torches cut to the carry target.
        kept = copy.deepcopy(raw)
        kept["inventory"] = [item for item in kept["inventory"]
                             if not item["name"].startswith("松明(2300")]
        for item in kept["inventory"]:
            if item["name"].startswith("松明"):
                item["count"] = 10
        light = self.board(policy, kept)
        self.assertEqual(policy._inventory_weight(light), 1089)
        self.assertFalse(policy._inventory_overweight(light))


if __name__ == "__main__":
    unittest.main()
