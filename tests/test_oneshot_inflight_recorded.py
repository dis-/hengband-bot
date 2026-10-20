"""Replay the C4-A Home-relief one-shot sale that ended in an empty key.

The fixture is state rows 60-91 of the soak capture
c4a-loops-20261016/20261020-082800-no-key-exhausted, copied as-is (life-014,
Level 30, town, gold 10,214, Home full): line 0 is the recall arrival board,
line 14 the ~9 Home knowledge answer, lines 18-19 the *Remove Curse* scroll
withdrawn for the Home-full sale, lines 22-23 the Alchemist entry that
inscribed it, line 28 the outside board where the one-shot sale was composed,
line 30 the Alchemist page its entry opened and line 31 the stop board.

Live (544ce4d1, enforce_crossarea_fundraising and in_store_shop_ops on), the
outside composition ran the Home-relief seller on the observed page; that
seller commits its sale to the in-store entry ledger.  The entry page then
judged the never-sent sale as posted without effect, left with
``shop:in-store-done``, and the orphaned sale watch emitted ``''``
``shop:one-shot-in-flight`` outside, so the driver stopped (no-key-exhausted).
The restart (20261020-082847) repeated it with a Fire Bolt rod (its decision
rows are kept in the recorded json).

DECLARED CONSTRUCTED: the ~9 request answered by line 14 (the fresh policy is
marked as awaiting it), the ~f skill-exp cache, and in the control the
post-sale board (the stop board without the sold scroll; the capture has no
board after a posted sale because the sale was never sent).
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from recorded_star_reserve import pre_star_reserve_retention_replay
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "oneshot-inflight-c4a-20261020.jsonl.gz"
SHA256 = "fc7a8d7452a2f21c4c8cd7c79c52a535caf5a04379875e466239513ab68cd749"
RECORDED = FIXTURE.with_name("oneshot-inflight-c4a-20261020.recorded.json")
RECORDED_SHA256 = "7d1c503b4ac3ac727bc2629f4f09bba02ab4a68a12692b5b9d900e4b5b30b405"
INSCRIBE_PAGE = 22  # first Alchemist page (the scroll is inscribed @0)
COMPOSE_BOARD = 28  # outside board where the one-shot sale is composed
ENTRY_PAGE = 30  # the Alchemist page opened by the one-shot entry key
STOP_BOARD = 31


# declared wall: pre-2026-10-20 *Remove Curse* reserve retention
@pre_star_reserve_retention_replay
class OneShotInFlightRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.lines = gzip.decompress(payload).decode("utf-8").splitlines()
        recorded = RECORDED.read_bytes()
        assert hashlib.sha256(recorded).hexdigest() == RECORDED_SHA256
        cls.recorded = json.loads(recorded.decode("utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.temporary = TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.policy = _policy(cls.directory, cls.monrace)
        cls.policy._crossarea_fundraising_enforced = True
        cls.policy._in_store_ops_enabled = True
        cls.decisions = {}
        for index in range(ENTRY_PAGE + 1):
            decision = cls._feed(cls.lines[index])
            if decision is not None:
                cls.decisions[index] = decision
        # The policy right after the staged sale was released on the entry
        # page; each watch test continues from its own copy.
        cls.released = copy.deepcopy(cls.policy)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def _await_recorded_knowledge(policy):
        # DECLARED CONSTRUCTED: the fresh policy awaits the recorded ~9, as
        # the posted request the capture does not include would leave it.
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None

    @classmethod
    def _feed(cls, line, policy=None):
        policy = cls.policy if policy is None else policy
        knowledge = json.loads(line).get("type") == "knowledge"
        if knowledge:
            cls._await_recorded_knowledge(policy)
        _decoded, snapshots = _consume_response_sequence(
            [line], policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=cls.directory / "knowledge.jsonl",
        )
        if knowledge or not snapshots:
            return None
        board = snapshots[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return board, policy.choose_key(board), policy.last_reason

    def test_recorded_rows_left_the_entry_page_without_the_sale(self):
        decisions = self.recorded["decisions"]
        self.assertEqual(
            [(decisions[n]["key"], decisions[n]["reason"])
             for n in ("5262", "5263", "5264")],
            [("5", "shop:one-shot-sell"),
             ("\x1b", "shop:in-store-done"),
             ("", "shop:one-shot-in-flight")])
        composed = decisions["5262"]["store_visit"]
        self.assertEqual(
            (composed["owner"], composed["operation_posted"],
             composed["operation_released"]),
            ("shop-one-shot", True, False))
        self.assertIsNone(decisions["5264"]["store_visit"])
        boards = [json.loads(self.lines[n]) for n in (COMPOSE_BOARD, STOP_BOARD)]
        self.assertEqual([b["player"]["gold"] for b in boards], [10214, 10214])
        self.assertEqual([len(b["inventory"]) for b in boards], [23, 23])
        self.assertIn("*解呪*の巻物 {@0}",
                      [item["name"] for item in boards[1]["inventory"]])
        second = self.recorded["second_decisions"]
        self.assertEqual(
            [(second[n]["key"], second[n]["reason"]) for n in ("21", "22", "26")],
            [("5", "shop:travel:await-entry"),
             ("\x1b", "shop:in-store-done"),
             ("", "shop:one-shot-in-flight")])
        self.assertEqual(
            (second["21"]["store_visit"]["owner"],
             second["21"]["store_visit"]["operation_posted"],
             second["21"]["store_visit"]["operation_released"]),
            ("shop-one-shot", True, False))

    def test_replay_composes_the_recorded_one_shot_sale(self):
        board, key, reason = self.decisions[COMPOSE_BOARD]
        self.assertIsNone(board.store)
        self.assertEqual((key, reason), ("5", "shop:one-shot-sell"))

    def test_entry_page_releases_the_staged_sale(self):
        board, key, reason = self.decisions[ENTRY_PAGE]
        self.assertEqual(board.store.store_type, 4)
        self.assertEqual((key, reason), ("d0y\x1b", "shop:one-shot-sell"))

    def test_control_an_operation_posted_on_the_page_still_ends_the_entry(self):
        # The inscription was sent on the first Alchemist page; the ledger
        # still judges that entry and leaves after it.
        self.assertEqual(self.decisions[INSCRIBE_PAGE][1:],
                         ("{k@0\r", "shop:in-store-inscribe"))
        self.assertEqual(self.decisions[INSCRIBE_PAGE + 1][1:],
                         ("\x1b", "shop:in-store-done"))

    def test_control_observed_sale_completes_and_town_work_continues(self):
        policy = self.policy
        self.assertEqual(policy._batch_sell_pending["phase"], "await-sale")
        # DECLARED CONSTRUCTED: the stop board without the sold scroll, as
        # the posted d0y would leave the pack (letters close up).
        row = json.loads(self.lines[STOP_BOARD])
        inventory = [item for item in row["inventory"] if item["slot"] != "k"]
        for index, item in enumerate(inventory):
            item["slot"] = chr(ord("a") + index)
        row["inventory"] = inventory
        _board, key, reason = self._feed(json.dumps(row, ensure_ascii=False))
        self.assertIsNone(policy._batch_sell_pending)
        self.assertIsNone(policy._store_visit)
        self.assertNotEqual(key, "")
        self.assertEqual((key, reason), ("~9\x1b", "home:request-knowledge-scan"))


    def _later(self, index, turns):
        row = json.loads(self.lines[index])
        row["turn"] += turns
        return json.dumps(row, ensure_ascii=False)

    def _left_without_effect(self):
        # DECLARED CONSTRUCTED: the page after the posted d0y shows no sale
        # (the entry page again), so the entry ends and leaves; the sale
        # watch outlives the visit that held its operation.
        policy = copy.deepcopy(self.released)
        _board, key, reason = self._feed(self.lines[ENTRY_PAGE], policy)
        self.assertEqual((key, reason), ("\x1b", "shop:in-store-done"))
        self.assertIsNone(policy._store_visit)
        self.assertEqual(policy._batch_sell_pending["phase"], "await-sale")
        return policy

    def test_unposted_sale_watch_outside_is_settled(self):
        policy = self._left_without_effect()
        _board, key, reason = self._feed(self.lines[STOP_BOARD], policy)
        self.assertEqual((key, reason),
                         ("9", "equipment-transaction:acquire-home-catalog"))
        self.assertIsNone(policy._batch_sell_pending)

    def test_unposted_sale_watch_on_a_store_page_is_settled(self):
        policy = self._left_without_effect()
        # DECLARED CONSTRUCTED: the next observed board is the Alchemist page
        # again, without the outside board in between (as the restart
        # 20261020-082847 re-entered with the watch set, decisions 23-26).
        self._feed(self._later(ENTRY_PAGE, 5), policy)
        self.assertIsNone(policy._batch_sell_pending)
        _board, key, reason = self._feed(self._later(STOP_BOARD, 10), policy)
        self.assertEqual((key, reason), ("5", "shop:one-shot-sell"))

    def test_control_posted_sale_watch_still_waits(self):
        policy = copy.deepcopy(self.released)
        _board, key, reason = self._feed(self.lines[STOP_BOARD], policy)
        self.assertEqual((key, reason), ("", "shop:one-shot-in-flight"))
        visit = policy._store_visit
        self.assertEqual((visit.operation_posted, visit.operation_released),
                         (True, True))
        self.assertEqual(policy._batch_sell_pending["phase"], "await-sale")


if __name__ == "__main__":
    unittest.main()
