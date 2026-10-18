"""Recorded pin (issue #68): a churn-refused Recall is a stock-out, not a restock wait.

Live soak 2026-10-18 14:42 (c4-a life-013, Level 27, 6,835 gold, capture
20261018-144235-stall-floor-dwell-town-wait-restock-temple): Word of Recall
0/10 was the only failed departure leaf.  The Temple shelf offered 19 Recall
scrolls at 229 gold and the Alchemist one at 236, yet every visit ended in
``shop:observe-and-leave`` (``observed-page-nothing-wanted``) and the bot
waited ``town:wait-restock:temple`` (R300) until the floor-dwell stall.  The
purchase selector refused the class through the sell-rebuy churn guard
(Recall had been sold earlier in the same stay; the Alchemist page closed as
``shop:sell-rebuy-churn-defect``), while the supply ledger still counted both
shelves as suppliers, so the approved recall stock-out time-pass never started
and the restock wait could never end.

Substrate: the recorded state rows (tests/extract_recall_churn_stockout_
fixture.py) replayed through the public response path on one policy from
decision row 38 (the Temple page, the first board of the state window) to
row 52.  DECLARED WALLS (constructed context; the live process state from
before the window is not in the logs): (1) the ``~f`` skill list of the same
character from an earlier capture, applied before every decision; (2) the
churn record of the stay: the Recall class is in the visit's sale signatures
(only that class reproduces both recorded store verdicts on these pages);
(3) Home and the Magic shop stay closed for this stay (the live plan held only
Temple and Black Market), re-latched before every decision.  Under these walls
99c2fa87 posts the recorded ``shop:observe-and-leave`` on the Alchemist page
(row 47) and the recorded ``R300`` ``town:wait-restock:temple`` on row 52.
The replay's Recall target is 7 (live 10: the live destination state is not
reconstructed); the shortfall is the same single failed leaf.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    DUNGEON_YEEK_CAVE, STORE_ALCHEMIST, STORE_HOME, STORE_MAGIC, STORE_TEMPLE,
    SV_SCROLL_WORD_OF_RECALL, TVAL_SCROLL,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import WAIT_KEY
from test_esp_threat_rest_recorded import EDIT, _policy
from test_supply_shortfall_owner_recorded import _segments

FIXTURE = Path(__file__).parent / "fixtures/recall-churn-stockout-20261018.json.gz"
SHA256 = "c2ee4ed41b937b61f33bfaea282015e647a620a24e1e6aa3ebe9e293e343f5da"
START, PIN, LAST = 38, 47, 52
RECALL = (TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)


class RecallChurnStockoutRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.skill = json.loads(cls.pin["skill_line"])
        assert cls.skill["knowledge"]["category"] == "skill_exp"
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, *, churn=True, stop=LAST):
        """Replay rows START..stop; return (policy, results, boards by row)."""
        lines, decisions = self.pin["lines"], self.pin["decisions"]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, self.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        ledger = root / "knowledge.jsonl"
        previous = None
        results, boards = {}, {}
        for index, start, end in _segments(lines, decisions):
            recorded = decisions[index]
            segment = lines[start:end]
            if previous is not None and previous["key"]:
                row = json.loads(segment[-1])
                row["_completed_operation_sequence"] = previous["decision_sequence"]
                row["_completed_operation_owner"] = previous["reason"]
                segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
            _, parsed = _consume_response_sequence(
                segment, policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=ledger)
            board = parsed[-1]
            if index == START:
                policy.prime(board)
                if churn:
                    policy._town_visit_sale_signatures.add(RECALL)  # Wall (2).
            policy.consume_skill_knowledge(  # Wall (1).
                {**self.skill, "player": {"level": board.player.level}})
            board = policy.with_known_skill_exp(board)
            for store in (STORE_HOME, STORE_MAGIC):  # Wall (3).
                if store not in policy._town_store_attempted:
                    policy._set_town_store_attempted(store, board.turn, "wall")
            key = policy.choose_key(board)
            results[recorded["row"]] = (
                str(key), policy.last_reason, recorded["key"], recorded["reason"])
            boards[recorded["row"]] = board
            policy.confirm_key_posted(key)
            previous = recorded
            if index == stop:
                return policy, results, boards
        raise AssertionError("replay end not reached")

    @staticmethod
    def _recall_requirement(policy, board):
        return next(row for row in policy.procurement_requirements(board)
                    if row["item"] == "Word of Recall scrolls")

    def test_captured_rows(self):
        decisions = self.pin["decisions"]
        self.assertEqual(
            [(d["row"], d["key"], d["reason"]) for d in decisions[PIN:LAST + 1]],
            [(47, "\x1b", "shop:observe-and-leave"),
             (48, "\x1b`n$.", "shop:travel"),
             (49, "\x1b", "shop:observe-and-leave"),
             (50, "\x1b`n'.", "shop:travel"),
             (51, "\x1b", "shop:observe-and-leave"),
             (52, "R300\r", "town:wait-restock:temple")],
        )
        page = json.loads(self.pin["lines"][0])["store"]
        self.assertEqual(page["store_type"], STORE_TEMPLE)
        offers = [(item["price"], item["count"]) for item in page["items"]
                  if (item["tval"], item["sval"]) == RECALL]
        self.assertEqual(offers, [(229, 19)])
        self.assertEqual(json.loads(self.pin["lines"][0])["player"]["gold"], 6835)

    def test_churn_refused_recall_starts_the_recall_stockout_time_pass(self):
        policy, results, boards = self.replay(stop=PIN)
        self.assertEqual(boards[PIN].store.store_type, STORE_ALCHEMIST)
        # 99c2fa87: ("\x1b", "shop:observe-and-leave"), then R300
        # "town:wait-restock:temple" on row 52 for as long as the stay lasted.
        self.assertEqual(results[PIN][:2], ("\x1b", "town:recall-stockout-mining"))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertTrue(policy._recall_stockout_mining_plan)
        self.assertEqual(policy._planned_mining_runs, 1)
        self.assertEqual(
            self._recall_requirement(policy, boards[PIN]).get("blocked_reason"),
            "no-actionable-supplier")
        self.assertFalse(any(reason.startswith("town:wait-restock")
                             for _key, reason, *_ in results.values()))

    def test_supply_stockout_owner_keeps_its_three_round_stop(self):
        # Control (constructed): the same classification feeds the generic
        # supply stock-out owner, which still stops visibly after three rounds.
        # Constructed: Home work resolved (live, Recall was the only failed
        # leaf; wall (3) leaves the replayed Home catalogue unscanned).
        policy, _results, boards = self.replay(stop=PIN)
        board = boards[PIN]
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        self.assertEqual(policy._departure_block_state(board)["failed"],
                         ["recall_departure_ready"])
        policy._fundraising_mode = None
        policy._recall_stockout_mining_plan = False
        policy._supply_stockout_cycles = 3
        policy._supply_stockout_mining_dispatch_key(board)
        self.assertEqual(policy._town_blocked_reason, "departure-unsatisfiable")
        self.assertIsNone(policy._fundraising_mode)
        policy._supply_stockout_cycles = 0
        self.assertEqual(policy._supply_stockout_mining_dispatch_key(board), WAIT_KEY)
        self.assertEqual(policy.last_reason, "fundraise:supply-stockout-mining")

    def test_mining_return_ends_the_churn_scope_so_the_retry_buys(self):
        # Control (constructed run): the time-pass is not a dead end.  The
        # existing floor-change reset ends the churn scope on the Yeek Cave
        # floor, so the retry after the run buys the Temple's Recall.
        policy, _results, boards = self.replay(stop=PIN)
        temple = boards[START]
        policy._town_visit_ledger.purchase_churn_class_exclusions.add(
            (STORE_ALCHEMIST, *RECALL))
        self.assertIsNone(policy._next_purchase(temple))
        # The time-pass run: Yeek Cave 1F, then the walk back into town.
        policy._fundraising_mode = "mine"
        town = boards[PIN]
        town = replace(town, store=None)
        policy._observe(replace(town, floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
                                town_flag=False, turn=town.turn + 1))
        policy._observe(replace(town, turn=town.turn + 2))
        self.assertEqual(policy._mining_runs_completed, 1)
        self.assertNotIn(RECALL, policy._town_visit_sale_signatures)
        self.assertFalse(policy._town_visit_ledger.purchase_churn_class_exclusions)
        # The completed run ends the one-run set on the next town board.
        policy._town_special_key(replace(town, turn=town.turn + 3))
        self.assertIsNone(policy._fundraising_mode)
        bought = policy._next_purchase(replace(temple, turn=town.turn + 4))
        self.assertEqual((bought.tval, bought.sval, bought.price), (*RECALL, 229))

    def test_control_an_offered_recall_without_churn_is_still_bought(self):
        # Control (constructed): without wall (2) the Temple shelf is an
        # ordinary supplier; the Recall ware is the wanted purchase and no
        # stock-out time-pass starts on the Alchemist page.
        policy, results, boards = self.replay(churn=False, stop=START)
        wanted = policy._next_purchase(boards[START])
        self.assertEqual((wanted.tval, wanted.sval, wanted.price), (*RECALL, 229))
        self.assertNotIn(
            "blocked_reason", self._recall_requirement(policy, boards[START]))
        self.assertIsNone(policy._fundraising_mode)
        self.assertFalse(policy._recall_stockout_mining_plan)


if __name__ == "__main__":
    unittest.main()
